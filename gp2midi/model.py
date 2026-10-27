"""Model skor hasil parsing GPIF, netral terhadap format output."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Note:
    midi: int
    tie_origin: bool = False
    tie_destination: bool = False
    muted: bool = False
    palm_muted: bool = False
    string: int | None = None
    fret: int | None = None


@dataclass
class Beat:
    duration: int               # dalam tick
    notes: list[Note] = field(default_factory=list)
    dynamic: str = "F"
    grace: str | None = None    # "OnBeat" | "BeforeBeat" bila beat ini grace note


@dataclass
class Voice:
    beats: list[Beat] = field(default_factory=list)


@dataclass
class Bar:
    voices: list[Voice] = field(default_factory=list)


@dataclass
class MasterBar:
    index: int
    numerator: int
    denominator: int
    length: int                 # panjang bar dalam tick
    start: int                  # tick awal bar pada timeline linear (belum di-expand)
    repeat_start: bool = False
    repeat_count: int = 0       # >0 berarti akhir pengulangan
    alternate_endings: int = 0  # bitmask ending 1..8
    section: str | None = None
    key_accidentals: int = 0    # negatif = flat, positif = sharp
    key_minor: bool = False


@dataclass
class Track:
    index: int
    name: str
    short_name: str
    program: int
    bank_msb: int
    bank_lsb: int
    is_drums: bool
    volume: float
    pan: float
    tuning: list[int]
    bars: list[Bar] = field(default_factory=list)

    @property
    def note_count(self) -> int:
        return sum(len(b.notes) for bar in self.bars for v in bar.voices for b in v.beats)


@dataclass
class TempoChange:
    tick: int
    bpm: float


@dataclass
class Score:
    title: str
    subtitle: str
    artist: str
    album: str
    ppq: int
    master_bars: list[MasterBar] = field(default_factory=list)
    tracks: list[Track] = field(default_factory=list)
    tempos: list[TempoChange] = field(default_factory=list)
