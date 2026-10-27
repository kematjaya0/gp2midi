"""Penulis Standard MIDI File (type 0/1) tanpa dependensi eksternal."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field


def vlq(value: int) -> bytes:
    """Variable-length quantity seperti pada spesifikasi SMF."""
    if value < 0:
        raise ValueError("delta time tidak boleh negatif")
    out = bytearray([value & 0x7F])
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))


@dataclass(order=True)
class Event:
    tick: int
    order: int          # tie-break agar event pada tick sama tetap deterministik
    data: bytes = field(compare=False)


class MidiTrack:
    """Satu MTrk. Event dikumpulkan dengan tick absolut lalu diurutkan saat serialisasi."""

    #  urutan prioritas pada tick yang sama
    ORDER_META = 0
    ORDER_CONTROL = 1
    ORDER_NOTE_OFF = 2
    ORDER_NOTE_ON = 3

    def __init__(self) -> None:
        self._events: list[Event] = []
        self._seq = 0

    def _add(self, tick: int, order: int, data: bytes) -> None:
        self._seq += 1
        self._events.append(Event(tick, order * 1_000_000 + self._seq, data))

    # --- meta events
    def meta(self, tick: int, kind: int, payload: bytes) -> None:
        self._add(tick, self.ORDER_META, bytes([0xFF, kind]) + vlq(len(payload)) + payload)

    def track_name(self, name: str) -> None:
        self.meta(0, 0x03, name.encode("utf-8")[:127])

    def text(self, tick: int, value: str) -> None:
        self.meta(tick, 0x01, value.encode("utf-8"))

    def marker(self, tick: int, value: str) -> None:
        self.meta(tick, 0x06, value.encode("utf-8"))

    def tempo(self, tick: int, bpm: float) -> None:
        micros = max(1, min(0xFFFFFF, round(60_000_000 / bpm)))
        self.meta(tick, 0x51, micros.to_bytes(3, "big"))

    def time_signature(self, tick: int, numerator: int, denominator: int) -> None:
        power = max(0, denominator.bit_length() - 1)
        self.meta(tick, 0x58, bytes([numerator, power, 24, 8]))

    def key_signature(self, tick: int, accidentals: int, minor: bool) -> None:
        self.meta(tick, 0x59, bytes([accidentals & 0xFF, 1 if minor else 0]))

    # --- channel events
    def program_change(self, tick: int, channel: int, program: int) -> None:
        self._add(tick, self.ORDER_CONTROL, bytes([0xC0 | channel, program & 0x7F]))

    def control_change(self, tick: int, channel: int, controller: int, value: int) -> None:
        self._add(tick, self.ORDER_CONTROL, bytes([0xB0 | channel, controller & 0x7F, value & 0x7F]))

    def note_on(self, tick: int, channel: int, note: int, velocity: int) -> None:
        self._add(tick, self.ORDER_NOTE_ON, bytes([0x90 | channel, note & 0x7F, velocity & 0x7F]))

    def note_off(self, tick: int, channel: int, note: int) -> None:
        self._add(tick, self.ORDER_NOTE_OFF, bytes([0x80 | channel, note & 0x7F, 0]))

    def serialize(self) -> bytes:
        body = bytearray()
        previous = 0
        for event in sorted(self._events):
            body += vlq(event.tick - previous)
            body += event.data
            previous = event.tick
        body += vlq(0) + b"\xff\x2f\x00"
        return b"MTrk" + struct.pack(">I", len(body)) + bytes(body)

    @property
    def is_empty(self) -> bool:
        return not self._events


def write_file(path, tracks: list[MidiTrack], ppq: int) -> None:
    fmt = 1 if len(tracks) > 1 else 0
    header = b"MThd" + struct.pack(">IHHH", 6, fmt, len(tracks), ppq)
    with open(path, "wb") as handle:
        handle.write(header)
        for track in tracks:
            handle.write(track.serialize())
