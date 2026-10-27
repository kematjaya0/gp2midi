#!/usr/bin/env python3
"""Oracle: baca .mid dengan mido (parser independen) dan uji invariannya.

Dipakai supaya hasil gp2midi.smf tidak pernah divalidasi oleh pembacanya sendiri.
"""

from __future__ import annotations

import collections
import struct
import sys
from pathlib import Path

try:
    import mido
except ModuleNotFoundError:
    sys.exit("verify_midi: butuh mido. Jalankan tools/verify.sh, bukan skrip ini langsung.")


def check(path: Path) -> list[str]:
    errors: list[str] = []

    raw = path.read_bytes()
    if not raw.startswith(b"MThd"):
        return [f"{path.name}: bukan Standard MIDI File"]
    _, fmt, ntrk, ppq = struct.unpack(">IHHH", raw[4:14])

    midi = mido.MidiFile(path)
    if midi.ticks_per_beat != ppq:
        errors.append(f"{path.name}: PPQ header {ppq} != mido {midi.ticks_per_beat}")
    if len(midi.tracks) != ntrk:
        errors.append(f"{path.name}: header klaim {ntrk} track, mido lihat {len(midi.tracks)}")
    if fmt == 0 and ntrk != 1:
        errors.append(f"{path.name}: type 0 harus tepat 1 track, ada {ntrk}")

    tempos: list[tuple[int, float]] = []
    total_notes = 0
    for index, track in enumerate(midi.tracks):
        open_notes: collections.Counter = collections.Counter()
        tick = 0
        for message in track:
            tick += message.time
            if message.type == "set_tempo":
                tempos.append((tick, mido.tempo2bpm(message.tempo)))
            elif message.type == "note_on" and message.velocity > 0:
                open_notes[(message.channel, message.note)] += 1
                total_notes += 1
            elif message.type == "note_off" or (message.type == "note_on" and message.velocity == 0):
                open_notes[(message.channel, message.note)] -= 1

        stuck = {k: v for k, v in open_notes.items() if v}
        if stuck:
            errors.append(f"{path.name}: track {index} ({track.name!r}) not nyangkut {stuck}")

    if not tempos:
        errors.append(f"{path.name}: tidak ada set_tempo")
    if total_notes == 0:
        errors.append(f"{path.name}: nol not")

    tempo_text = ", ".join(f"{bpm:.0f}@{tick}" for tick, bpm in tempos)
    print(f"  {path.name}: type {fmt}, {ntrk} trk, PPQ {ppq}, "
          f"{total_notes} not, {midi.length:.1f}s, tempo {tempo_text}")
    return errors


def main(argv: list[str]) -> int:
    if not argv:
        sys.exit("pakai: verify_midi.py FILE.mid [FILE.mid ...]")

    errors: list[str] = []
    for name in argv:
        errors.extend(check(Path(name)))

    for error in errors:
        print(f"GAGAL {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
