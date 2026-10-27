#!/usr/bin/env python3
"""Oracle peta tempo: ms(last_note_end) kita vs MidiFile.length milid mido.

Pembungkus tidak boleh menguji dirinya sendiri: di sini durasi menurut
TempoMap dibandingkan dengan akhir file MIDI yang dibaca parser independen.
Toleransi 2 ms.

Pemakaian:
    verify_tempo.py out.mid out.merged.mid ...     # file mid hasil convert
    verify_tempo.py FOLDER                          # semua .mid di folder
    verify_tempo.py lagu.gp lagu.mid                # pasangan eksplisit
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mido  # noqa: E402

from gp2midi import parse  # noqa: E402
from gp2midi.timeline import build_timeline  # noqa: E402

TOLERANCE_MS = 2.0
MEDIA_DIR = Path(__file__).resolve().parents[1] / "media"


def gp_for_mid(mid_path: Path) -> Path:
    """Menebak file .gp asal dari nama hasil convert <basename>.gp[.merged].mid."""
    name = mid_path.name
    if name.endswith(".merged.mid"):
        name = name[: -len(".merged.mid")]
    elif name.endswith(".mid"):
        name = name[: -len(".mid")]
    if not name.endswith(".gp"):
        name += ".gp"
    return MEDIA_DIR / name


def pairs_from_args(argv: list[str]) -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    args = [Path(a) for a in argv]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.is_dir():
            for mid in sorted(arg.glob("*.mid")):
                pairs.append((gp_for_mid(mid), mid))
            i += 1
        elif arg.suffix == ".gp" and i + 1 < len(args):
            pairs.append((arg, args[i + 1]))
            i += 2
        else:
            pairs.append((gp_for_mid(arg), arg))
            i += 1
    return pairs


def main(argv: list[str]) -> int:
    pairs = pairs_from_args(argv)
    if not pairs:
        print("verify_tempo: tidak ada file yang diperiksa", file=sys.stderr)
        return 1

    status = 0
    for gp_path, mid_path in pairs:
        timeline = build_timeline(parse(str(gp_path)))
        ours_ms = timeline.duration_ms
        mido_ms = mido.MidiFile(str(mid_path)).length * 1000.0
        difference = ours_ms - mido_ms
        flag = "OK" if abs(difference) <= TOLERANCE_MS else "LEWAT"
        print(
            f"  [{flag:>4}] {gp_path.name:<62} "
            f"kita {ours_ms:,.1f} ms  mido {mido_ms:,.1f} ms  selisih {difference:+.1f} ms"
        )
        if abs(difference) > TOLERANCE_MS:
            status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
