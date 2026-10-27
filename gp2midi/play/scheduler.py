"""Thread lookahead dan transport.

Di sini tidak ada ctypes dan tidak ada parsing — hanya Timeline di satu sisi
dan Audio di sisi lain. Aritmetika waktunya berpusat pada satu field
`_epoch` (ms pada jam audio.now()): posisi lagu = now - _epoch; waktu absolut
not pada tick t = _epoch + tempo.ms(t).
"""

from __future__ import annotations

import bisect
import threading
import time
from dataclasses import dataclass

from gp2midi.timeline import Timeline

from .audio import Audio

LOOKAHEAD_MS = 300      # PRD F2
FILL_INTERVAL_MS = 100  # sepertiga lookahead; thread harus bangun 3x sebelum jendela habis


@dataclass
class Report:
    """Angka untuk kriteria selesai F2. Semua dalam ms."""
    expected_ms: float      # durasi menurut TempoMap, dari posisi mulai
    actual_ms: float        # wall clock, time.monotonic
    drift_ms: float         # actual - expected
    late_events: int        # not yang dijadwalkan padahal waktunya sudah lewat
    max_fill_lag_ms: float  # keterlambatan terbesar bangunnya thread pengisi
    notes_scheduled: int

    def ok(self, tolerance_ms: float = 50.0) -> bool:
        return abs(self.drift_ms) <= tolerance_ms and self.late_events == 0


STOPPED, PLAYING, PAUSED = "stopped", "playing", "paused"


class Player:
    """Transport di atas Timeline + Audio, dengan thread pengisi antrian."""

    def __init__(self, timeline: Timeline, audio: Audio,
                 lookahead_ms: int = LOOKAHEAD_MS) -> None:
        self._timeline = timeline
        self._audio = audio
        self._lookahead_ms = lookahead_ms

        # daftar start not, urut naik sejajar dengan timeline.notes — untuk bisect
        self._starts = [n.start for n in timeline.notes]
        self._n_notes = len(timeline.notes)
        self._duration_ms = timeline.duration_ms

        self._lock = threading.Lock()
        self._state = STOPPED
        self._position_ms = 0.0
        self._epoch = audio.now() - 0.0
        self._start_offset_ms = 0.0   # posisi lagu saat play(), acuan batas limit
        self._cursor = 0
        self._limit_ms = None

        self._late = 0
        self._scheduled = 0
        self._max_fill_lag = 0.0
        self._report = None
        self._wall_start = None

        self._thread = None
        self._quit = threading.Event()
        self._done = threading.Event()

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def position_ms(self) -> float:
        with self._lock:
            if self._state == PLAYING:
                return self._audio.now() - self._epoch
            if self._state == PAUSED:
                return self._position_ms
            return 0.0

    @property
    def position_tick(self) -> int:
        return self._timeline.tempo.tick(self.position_ms)

    def setup_instruments(self) -> None:
        """Untuk tiap track: select_program + CC7/CC10 dari model.

        Fakta F-5: tanpa program_select, channel senyap. Dipanggil sekali
        sebelum play()."""
        for track in self._timeline.tracks:
            channel = self._timeline.channels[track.index]
            self._audio.select_program(channel, track.program,
                                       bank=track.bank_msb, drums=track.is_drums)
            self._audio.cc(channel, 7, round(track.volume * 127))
            self._audio.cc(channel, 10, round(track.pan * 127))

    def play(self, from_tick: int = 0, limit_ms: float | None = None) -> None:
        """Mulai (atau mulai ulang) playback di posisi `from_tick` tick."""
        t0 = self._audio.now()
        with self._lock:
            self._position_ms = self._timeline.tempo.ms(from_tick)
            # epoch selalu memakai pembacaan jam yang sama dengan pengisian pertama,
            # supaya not di posisi awal tidak terkira telat oleh jarak beberapa ms
            self._epoch = t0 - self._position_ms
            self._start_offset_ms = self._position_ms
            self._cursor = bisect.bisect_left(self._starts, from_tick)
            self._limit_ms = limit_ms
            self._state = PLAYING
            self._reset_counters()
            self._wall_start = time.monotonic()
            self._done.clear()
            self._quit.clear()
        self._fill(t0)
        self._ensure_thread()

    def pause(self) -> None:
        """Catat posisi, buang antrian, tanggalkan pengisian. Thread tidak dimatikan."""
        with self._lock:
            if self._state != PLAYING:
                return
            self._position_ms = self._audio.now() - self._epoch
            self._state = PAUSED
        self._audio.panic()

    def resume(self) -> None:
        """Lanjutkan dari posisi saat pause. Not yang sudah lewat tidak dijadwalkan ulang."""
        t0 = self._audio.now()
        with self._lock:
            if self._state != PAUSED:
                return
            self._epoch = t0 - self._position_ms
            self._cursor = bisect.bisect_left(self._starts,
                                              self._timeline.tempo.tick(self._position_ms))
            self._state = PLAYING
            self._done.clear()
        self._fill(t0)
        self._ensure_thread()

    def stop(self) -> None:
        """Berhenti bersih; idempoten, boleh dipanggil kapan pun."""
        with self._lock:
            self._state = STOPPED
            self._position_ms = 0.0
            self._cursor = 0
            self._start_offset_ms = 0.0
            self._limit_ms = None
            self._wall_start = None
        self._audio.panic()
        self._done.set()

    def seek(self, tick: int) -> None:
        """Lompat ke tick. Saat PLAYING posisi berlanjut; saat PAUSED tetap berhenti."""
        with self._lock:
            self._audio.panic()
            self._position_ms = self._timeline.tempo.ms(tick)
            self._cursor = bisect.bisect_left(self._starts, tick)
            if self._state == PLAYING:
                self._epoch = self._audio.now() - self._position_ms

    def wait(self, timeout: float | None = None) -> Report:
        """Blok sampai lagu habis, stop(), atau timeout. Mengembalikan Report.

        Polling pendek alih-alih satu `Event.wait` panjang: acquire C tanpa
        timeout tidak memutus sinyal, jadi Ctrl-C tidak akan terbaca.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        while not self._done.wait(0.1):
            if deadline is not None and time.monotonic() >= deadline:
                break
        return self._report or self._current_report()

    def close(self) -> None:
        """Matikan thread pengisi. Wajib sebelum Audio.close()."""
        self.stop()
        self._quit.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _reset_counters(self) -> None:
        self._late = 0
        self._scheduled = 0
        self._max_fill_lag = 0.0
        self._report = None

    def _ensure_thread(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def _loop(self) -> None:
        last_now = self._audio.now()
        while not self._quit.is_set():
            if self.state == PLAYING:
                now = self._audio.now()
                lag = (now - last_now) - FILL_INTERVAL_MS
                with self._lock:
                    self._max_fill_lag = max(self._max_fill_lag, lag)
                last_now = now
                self._fill(now)
                if self._finished(now):
                    self._finish()
            self._quit.wait(FILL_INTERVAL_MS / 1000.0)

    def _fill(self, now: int) -> None:
        """Jadwalkan seluruh not yang jatuh di dalam jendela lookahead."""
        with self._lock:
            epoch = self._epoch
            cursor = self._cursor
            notes = self._timeline.notes
            horizon = (now - epoch) + self._lookahead_ms     # dalam ms lagu
            tempo = self._timeline.tempo
            while cursor < len(notes):
                note = notes[cursor]
                on_ms = tempo.ms(note.start)
                if on_ms > horizon:
                    break
                at_on = epoch + on_ms                        # ms sequencer
                late = at_on < now
                if late:
                    at_on = now
                at_off = max(round(epoch + tempo.ms(note.end)), round(at_on) + 1)
                self._audio.note_on(round(at_on), note.channel, note.pitch, note.velocity)
                self._audio.note_off(at_off, note.channel, note.pitch)
                if late:
                    self._late += 1
                cursor += 1
                self._scheduled += 1
            self._cursor = cursor

    def _finished(self, now: int) -> bool:
        """Fakta F-8: durasi diukur sampai last_note_end (duration_ms), bukan end_tick."""
        with self._lock:
            position = now - self._epoch
            done = self._cursor >= len(self._timeline.notes)
            if done and position >= self._duration_ms:
                return True
            if self._limit_ms is not None and (
                position - self._start_offset_ms) >= self._limit_ms:
                return True
        return False

    def _expected_ms_locked(self) -> float:
        # pemanggil wajib sudah memegang self._lock — versi lock-free ini mencegah
        # jam antrean ganda (jendela antri) terjadi bila _finish memanggil dari dalam
        full = self._duration_ms - self._start_offset_ms
        if self._limit_ms is not None:
            return min(full, self._limit_ms)
        return full

    def _current_report(self) -> Report:
        with self._lock:
            expected = self._expected_ms_locked()
            actual = 0.0 if self._wall_start is None else (
                time.monotonic() - self._wall_start) * 1000.0
            report = Report(
                expected_ms=expected,
                actual_ms=actual,
                drift_ms=actual - expected,
                late_events=self._late,
                max_fill_lag_ms=self._max_fill_lag,
                notes_scheduled=self._scheduled,
            )
        return report

    def _finish(self) -> None:
        with self._lock:
            self._state = STOPPED
            self._position_ms = self._duration_ms
            self._cursor = len(self._timeline.notes)
            expected = self._expected_ms_locked()
            actual = 0.0 if self._wall_start is None else (
                time.monotonic() - self._wall_start) * 1000.0
            self._report = Report(
                expected_ms=expected,
                actual_ms=actual,
                drift_ms=actual - expected,
                late_events=self._late,
                max_fill_lag_ms=self._max_fill_lag,
                notes_scheduled=self._scheduled,
            )
        self._done.set()
