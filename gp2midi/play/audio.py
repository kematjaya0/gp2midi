"""Pembungkus thin pyfluidsynth. Satu-satunya tempat yang menyentuh ctypes.

Tidak ada logika musik di sini — tidak kenal bar, tempo, atau timeline.
Tugas tiga: pilih driver & soundfont, validasi argumen sebelum menyeberang
ke C (R2: segfault tidak bisa ditangkap try/except), dan sediakan satu
now() sebagai sumber jam.
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

import fluidsynth

from . import validate

# pyfluidsynth 1.4.0 tidak mem-bind fungsi ini, padahal ini satu-satunya cara
# membatalkan event yang sudah dijadwalkan. type = -1 berarti semua jenis event.
_remove_events = fluidsynth.cfunc(
    "fluid_sequencer_remove_events", None,
    ("seq", ctypes.c_void_p, 1),
    ("source", ctypes.c_short, 1),
    ("dest", ctypes.c_short, 1),
    ("type", ctypes.c_int, 1),
)

FLUID_FAILED = -1

# fakta F-5: rak instrumen drum ada di bank 128, bukan bank 0
DRUM_BANK = 128

SOUNDFONT_CANDIDATES = (
    "/usr/share/sounds/sf2/TimGM6mb.sf2",
    "/usr/share/sounds/sf2/default-GM.sf2",
    "/usr/share/soundfonts/default.sf2",
)

_MIN_SAMPLERATE, _MAX_SAMPLERATE = 8000, 192000


class AudioError(RuntimeError):
    pass


def default_drivers() -> tuple[str, ...]:
    """Kandidat driver menurut platform, urut dari yang paling disukai."""
    if sys.platform == "darwin":
        return ("coreaudio",)
    if sys.platform.startswith("linux"):
        return ("pulseaudio", "alsa")
    return ()


def find_soundfont(explicit: str | None = None) -> str:
    """Path soundfont yang dipakai: yang diminta, atau kandidat sistem pertama."""
    if explicit is not None:
        if not Path(explicit).is_file():
            raise FileNotFoundError(f"soundfont tidak ada: {explicit}")
        return explicit
    for candidate in SOUNDFONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    raise AudioError(
        "tidak ada soundfont; berikan lewat --soundfont. Kandidat: "
        + ", ".join(SOUNDFONT_CANDIDATES)
    )


class Audio:
    """Pembungkus Synth + Sequencer."""

    def __init__(self, soundfont: str | None = None, gain: float = 0.5,
                 samplerate: int = 44100, driver: str | None = None,
                 realtime: bool = True) -> None:
        # diset paling awal supaya close() aman dipanggil bila __init__ gagal separuh jalan
        self._synth = None
        self._seq = None
        self._dest = None
        self._sfid = None
        self._closed = False
        self.driver: str | None = None
        self.warnings: list[str] = []

        self._gain = validate.gain(gain)
        if isinstance(samplerate, bool) or not isinstance(samplerate, int):
            raise TypeError(
                f"samplerate harus int, dapat {samplerate!r} ({type(samplerate).__name__})")
        if not _MIN_SAMPLERATE <= samplerate <= _MAX_SAMPLERATE:
            raise ValueError(
                f"samplerate harus {_MIN_SAMPLERATE}-{_MAX_SAMPLERATE}, dapat {samplerate}")
        self._samplerate = samplerate

        sf_path = find_soundfont(soundfont)
        self._open_driver(driver)
        try:
            self._sfid = self._synth.sfload(sf_path)
        except Exception as exc:
            raise AudioError(f"soundfont gagal dimuat: {sf_path}: {exc}") from exc
        if self._sfid == FLUID_FAILED:
            raise AudioError(f"soundfont gagal dimuat: {sf_path}")
        self._seq = fluidsynth.Sequencer(time_scale=1000, use_system_timer=realtime)
        self._dest = self._seq.register_fluidsynth(self._synth)

    def _open_driver(self, driver: str | None) -> None:
        candidates: tuple[str | None, ...]
        if driver is not None:
            candidates = (driver,)
        else:
            platform_candidates = default_drivers()
            candidates = platform_candidates or (None,)
        attempts: list[str] = []
        for candidate in candidates:
            try:
                self._synth = fluidsynth.Synth(gain=self._gain, samplerate=self._samplerate)
                self._synth.start(driver=candidate)
            except Exception as exc:
                attempts.append(f"{candidate or '<default>'}: {exc}")
                if self._synth is not None:
                    self._synth.delete()
                    self._synth = None
                continue
            self.driver = candidate
            return
        raise AudioError(
            "semua kandidat driver audio gagal dibuka: " + "; ".join(attempts))

    # --- jam
    def now(self) -> int:
        """Waktu sequencer dalam ms. Satu-satunya sumber waktu untuk scheduler."""
        return self._seq.get_tick()

    # --- instrumen
    def select_program(self, channel: int, program: int, bank: int = 0,
                       drums: bool = False) -> None:
        """Drum -> bank 128, melodis -> bank yang diminta.

        Fakta F-5: channel tanpa program_select itu senyap, jadi kegagalan tidak
        boleh dilewatkan diam-diam — dicatat ke self.warnings. Fallback: bank 0,
        lalu program 0, karena program_select yang gagal hanya mencetak ke stderr.
        """
        channel = validate.channel(channel)
        program = validate.program(program)
        requested_bank = DRUM_BANK if drums else validate.bank(bank)

        for try_bank, try_program in (
            (requested_bank, program),
            (0, program),
            (0, 0),
        ):
            if self._synth.program_select(channel, self._sfid, try_bank, try_program) != FLUID_FAILED:
                if (try_bank, try_program) != (requested_bank, program):
                    self.warnings.append(
                        f"channel {channel}: program {program} bank {requested_bank} tidak ada; "
                        f"fallback ke bank {try_bank} program {try_program}")
                return
        self.warnings.append(
            f"channel {channel}: program_select gagal (bank {requested_bank}, program {program}); "
            "channel akan senyap")

    def cc(self, channel: int, controller: int, value: int) -> None:
        self._synth.cc(
            validate.channel(channel),
            validate.controller(controller),
            validate.control_value(value),
        )

    # --- penjadwalan (waktu absolut, ms)
    def note_on(self, at_ms: int, channel: int, key: int, velocity: int) -> None:
        self._seq.note_on(
            validate.sched_time(at_ms),
            validate.channel(channel),
            validate.key(key),
            validate.velocity(velocity),
            dest=self._dest,
        )

    def note_off(self, at_ms: int, channel: int, key: int) -> None:
        self._seq.note_off(
            validate.sched_time(at_ms),
            validate.channel(channel),
            validate.key(key),
            dest=self._dest,
        )

    # --- pembatalan
    def clear_scheduled(self) -> None:
        """Buang seluruh event terjadwal. Membuang antrian tidak mematikan not
        yang sudah berbunyi — panggilan ini wajib disusul all_notes_off."""
        if self._seq is None:
            return
        _remove_events(self._seq.sequencer, -1, -1, -1)

    def all_notes_off(self) -> None:
        """all_notes_off untuk channel 0-15."""
        if self._synth is None:
            return
        for channel in range(16):
            self._synth.all_notes_off(validate.channel(channel))

    def panic(self) -> None:
        """clear_scheduled lalu all_notes_off, dalam urutan itu."""
        self.clear_scheduled()
        self.all_notes_off()

    # --- umur objek
    def close(self) -> None:
        """Idempoten. Urutannya: panic, delete sequencer, delete synth."""
        if self._closed:
            return
        self._closed = True
        if self._synth is not None or self._seq is not None:
            self.panic()
        if self._seq is not None:
            self._seq.delete()
            self._seq = None
        if self._synth is not None:
            self._synth.delete()
            self._synth = None

    def __enter__(self) -> "Audio":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
