"""Timeline datar: representasi publik hasil ekspansi bar (PRD K3).

Daftar not datar + grid bar + peta tempo. Kontrak bersama scheduler,
piano roll, dan eksporter. Modul ini stdlib murni — dependensi native
hanya boleh ada di `gp2midi/play/`.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field

from .model import Score, Track

DRUM_CHANNEL = 9

# velocity per dinamika, mengikuti konvensi Guitar Pro
DYNAMIC_VELOCITY = {
    "PPP": 15,
    "PP": 31,
    "P": 47,
    "MP": 55,
    "MF": 63,
    "F": 79,
    "FF": 95,
    "FFF": 111,
}

DEAD_NOTE_TICKS = 60  # ~1/64 pada PPQ 960


@dataclass
class Options:
    expand_repeats: bool = True
    gate: float = 1.0           # pengali panjang not (1.0 = legato penuh)
    include_empty: bool = False  # ikut tulis track tanpa not


@dataclass
class PlayedNote:
    """Satu not yang benar-benar berbunyi, pada timeline yang sudah di-expand."""
    pitch: int
    start: int          # tick absolut
    end: int            # tick absolut, selalu > start
    velocity: int
    channel: int = 0    # 0-based; 9 = drum
    track: int = 0      # Track.index asalnya


def playback_order(score: Score, expand_repeats: bool = True) -> list[int]:
    """Urutan indeks bar yang benar-benar dimainkan (repeat & alternate ending di-expand)."""
    total = len(score.master_bars)
    if not expand_repeats:
        return list(range(total))

    order: list[int] = []
    index = 0
    group_start = 0
    group_marker = -1
    pass_number = 1
    guard = 0
    limit = max(1000, total * 64)

    while index < total:
        guard += 1
        if guard > limit:
            raise RuntimeError("ekspansi repeat tidak berhenti; struktur bar mencurigakan")

        bar = score.master_bars[index]

        if bar.repeat_start and index != group_marker:
            group_marker = index
            group_start = index
            pass_number = 1

        if bar.alternate_endings and not (bar.alternate_endings & (1 << (pass_number - 1))):
            index += 1
            continue

        order.append(index)

        if bar.repeat_count > 1 and pass_number < bar.repeat_count:
            pass_number += 1
            index = group_start
            continue

        index += 1

    return order


def _bar_starts(score: Score, order: list[int]) -> tuple[list[int], int]:
    starts: list[int] = []
    cursor = 0
    for bar_index in order:
        starts.append(cursor)
        cursor += score.master_bars[bar_index].length
    return starts, cursor


def _velocity(dynamic: str) -> int:
    return DYNAMIC_VELOCITY.get(dynamic.upper(), 79)


def _track_notes(track: Track, order: list[int], starts: list[int],
                 options: Options, channel: int = 0) -> list[PlayedNote]:
    played: list[PlayedNote] = []
    # tie bisa menyambung antar bar, jadi status per nomor voice disimpan di luar loop bar
    open_ties_by_voice: dict[int, dict[int, int]] = {}

    for slot, bar_index in enumerate(order):
        if bar_index >= len(track.bars):
            continue
        bar = track.bars[bar_index]
        bar_start = starts[slot]

        for voice_index, voice in enumerate(bar.voices):
            cursor = bar_start
            open_ties = open_ties_by_voice.setdefault(voice_index, {})

            for beat in voice.beats:
                velocity = _velocity(beat.dynamic)

                if beat.grace:
                    # grace note mencuri waktu dari beat berikutnya, cursor tidak maju
                    length = min(beat.duration, 240)
                    start = max(bar_start, cursor - length) if beat.grace == "BeforeBeat" else cursor
                    for note in beat.notes:
                        played.append(
                            PlayedNote(note.midi, start, start + length, velocity,
                                       channel, track.index))
                    continue

                for note in beat.notes:
                    if note.tie_destination and note.midi in open_ties:
                        held = played[open_ties[note.midi]]
                        held.end += beat.duration
                        if not note.tie_origin:
                            open_ties.pop(note.midi, None)
                        continue

                    length = DEAD_NOTE_TICKS if note.muted else round(beat.duration * options.gate)
                    length = max(1, length)
                    played.append(
                        PlayedNote(note.midi, cursor, cursor + length, velocity,
                                   channel, track.index))

                    if note.tie_origin:
                        open_ties[note.midi] = len(played) - 1
                    else:
                        open_ties.pop(note.midi, None)

                cursor += beat.duration

    played.sort(key=lambda n: (n.start, n.pitch))
    return played


def _assign_channels(tracks: list[Track]) -> dict[int, int]:
    available = [c for c in range(16) if c != DRUM_CHANNEL]
    mapping: dict[int, int] = {}
    cursor = 0
    for track in tracks:
        if track.is_drums:
            mapping[track.index] = DRUM_CHANNEL
        else:
            mapping[track.index] = available[cursor % len(available)]
            cursor += 1
    return mapping


@dataclass
class TempoMap:
    """Peta tick <-> milidetik. Satu-satunya tempat konversi waktu terjadi."""
    ppq: int
    points: list[tuple[int, float]]   # (tick, bpm), urut naik, elemen pertama selalu tick 0

    def __post_init__(self) -> None:
        if not self.points:
            raise ValueError("peta tempo tidak boleh kosong")
        previous_tick = None
        for tick, bpm in self.points:
            if bpm <= 0:
                raise ValueError(f"bpm harus > 0, dapat {bpm}")
            if previous_tick is not None and tick < previous_tick:
                raise ValueError(f"titik tempo tidak urut naik: {previous_tick} lalu {tick}")
            previous_tick = tick

    @classmethod
    def from_score(cls, score: Score) -> TempoMap:
        raw = sorted(score.tempos, key=lambda t: t.tick)
        # titik berturut di tick sama buang semuanya kecuali yang terakhir
        points: list[tuple[int, float]] = [(t.tick, t.bpm) for t in raw]
        deduped: list[tuple[int, float]] = []
        for tick, bpm in points:
            if deduped and deduped[-1][0] == tick:
                deduped[-1] = (tick, bpm)
            else:
                deduped.append((tick, bpm))
        if not deduped or deduped[0][0] != 0:
            deduped.insert(0, (0, 120.0))
        return cls(score.ppq, deduped)

    def _segment_ms_per_tick_expr(self, index: int, delta_tick: int) -> float:
        # ms untuk `delta_tick` tick pada segmen ke-index; bentuk ini yang menjaga
        # hasil seperti 960 tick @120 BPM tetap persis 500.0
        return delta_tick * 60000.0 / (self.points[index][1] * self.ppq)

    def ms(self, tick: int) -> float:
        if tick <= 0:
            return 0.0
        total = 0.0
        for i in range(len(self.points)):
            start_tick, _bpm = self.points[i]
            if i + 1 < len(self.points):
                next_tick = self.points[i + 1][0]
                if tick < next_tick:
                    return total + self._segment_ms_per_tick_expr(i, tick - start_tick)
                total += self._segment_ms_per_tick_expr(i, next_tick - start_tick)
            else:
                return total + self._segment_ms_per_tick_expr(i, tick - start_tick)
        return total

    def tick(self, ms: float) -> int:
        if ms <= 0:
            return 0
        elapsed = 0.0
        for i in range(len(self.points)):
            start_tick, _bpm = self.points[i]
            if i + 1 < len(self.points):
                next_tick = self.points[i + 1][0]
            else:
                next_tick = None
            per_tick = 60000.0 / (self.points[i][1] * self.ppq)
            if next_tick is None:
                return round(start_tick + (ms - elapsed) / per_tick)
            segment_ms = (next_tick - start_tick) * per_tick
            if ms < elapsed + segment_ms:
                return round(start_tick + (ms - elapsed) / per_tick)
            elapsed += segment_ms
        return 0  # tak terjangkau: segmen terakhir selalu kembali di atas


@dataclass
class BarSlot:
    slot: int           # posisi pada timeline yang sudah di-expand (0-based)
    source: int         # indeks MasterBar aslinya
    start: int          # tick awal
    length: int         # panjang dalam tick
    numerator: int
    denominator: int


@dataclass
class Timeline:
    """Kontrak bersama scheduler, piano roll, dan eksporter (PRD K3)."""
    ppq: int
    end_tick: int                   # akhir bar terakhir
    bars: list[BarSlot]
    notes: list[PlayedNote]         # urut (start, pitch)
    tempo: TempoMap
    tracks: list[Track]             # referensi ke model, untuk nama/program/volume/pan
    channels: dict[int, int]        # Track.index -> channel 0-based

    @property
    def last_note_end(self) -> int:
        """Tick note-off terakhir. Ini akhir playback, bukan end_tick — fakta F-8:
        skor boleh punya bar kosong di ekor, playback berhenti di not terakhir."""
        return max((n.end for n in self.notes), default=0)

    @property
    def duration_ms(self) -> float:
        """ms sampai last_note_end."""
        return self.tempo.ms(self.last_note_end)

    def bar_tick(self, number: int) -> int:
        """Tick awal bar nomor `number` (1-based, dalam urutan playback).
        Di luar rentang -> ValueError dengan pesan yang menyebut jumlah bar."""
        if not 1 <= number <= len(self.bars):
            raise ValueError(
                f"bar {number} di luar rentang; ada {len(self.bars)} bar (1-{len(self.bars)})")
        return self.bars[number - 1].start

    def notes_of(self, track_index: int) -> list[PlayedNote]:
        """Not satu track, urutannya sama dengan di self.notes."""
        return [n for n in self.notes if n.track == track_index]


def build_timeline(score: Score, options: Options | None = None) -> Timeline:
    """Bentuk timeline datar dari skor ter-parsir."""
    options = options or Options()
    order = playback_order(score, options.expand_repeats)
    starts, end_tick = _bar_starts(score, order)
    channels = _assign_channels(score.tracks)

    bars = [
        BarSlot(slot=slot, source=bar_index, start=starts[slot],
                length=score.master_bars[bar_index].length,
                numerator=score.master_bars[bar_index].numerator,
                denominator=score.master_bars[bar_index].denominator)
        for slot, bar_index in enumerate(order)
    ]

    notes: list[PlayedNote] = []
    for track in score.tracks:
        notes.extend(_track_notes(track, order, starts, options, channels[track.index]))
    # kunci global menambahkan n.track sebagai pemecah seri; urutan dalam satu
    # track tetap (start, pitch) — itu yang menjaga baseline byte eksporter
    notes.sort(key=lambda n: (n.start, n.pitch, n.track))

    return Timeline(
        ppq=score.ppq,
        end_tick=end_tick,
        bars=bars,
        notes=notes,
        tempo=TempoMap.from_score(score),
        tracks=score.tracks,
        channels=channels,
    )
