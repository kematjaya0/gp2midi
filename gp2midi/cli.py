"""Antarmuka command line gp2midi."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .container import UnsupportedContainer
from .convert import Options, playback_order, to_midi, to_midi_merged, to_midi_per_track
from .gpif import GpifError, parse


def _load(path: str):
    try:
        return parse(path)
    except (UnsupportedContainer, GpifError) as exc:
        print(f"gp2midi: {exc}", file=sys.stderr)
        raise SystemExit(2)


def _cmd_info(args) -> int:
    score = _load(args.input)
    order = playback_order(score, not args.no_expand_repeats)

    if args.json:
        print(json.dumps({
            "title": score.title,
            "artist": score.artist,
            "album": score.album,
            "ppq": score.ppq,
            "bars": len(score.master_bars),
            "bars_played": len(order),
            "tempos": [{"tick": t.tick, "bpm": t.bpm} for t in score.tempos],
            "tracks": [{
                "index": t.index,
                "name": t.name,
                "program": t.program,
                "drums": t.is_drums,
                "notes": t.note_count,
                "tuning": t.tuning,
            } for t in score.tracks],
        }, indent=2, ensure_ascii=False))
        return 0

    print(f"Judul    : {score.title}")
    print(f"Artis    : {score.artist}")
    print(f"Bar      : {len(score.master_bars)} (dimainkan {len(order)})")
    print(f"Tempo    : " + ", ".join(f"{t.bpm:g} BPM @tick {t.tick}" for t in score.tempos))
    print(f"Track    : {len(score.tracks)}")
    for track in score.tracks:
        kind = "drums" if track.is_drums else f"prog {track.program}"
        tuning = " ".join(str(x) for x in track.tuning) or "-"
        print(f"  [{track.index}] {track.name:<28} {kind:<10} not={track.note_count:<5} tuning={tuning}")
    return 0


def _cmd_convert(args) -> int:
    score = _load(args.input)
    options = Options(
        expand_repeats=not args.no_expand_repeats,
        gate=args.gate,
        include_empty=args.include_empty,
    )

    if args.merge:
        out_path = Path(args.output) if args.output else Path(args.input).with_suffix(".mid")
        result = to_midi_merged(score, out_path, options)
        print(f"{result['path']}  type {result['format']}, PPQ {result['ppq']}, {result['bars_played']} bar")
        for item in result["tracks"]:
            if item["written"]:
                print(f"  ch{item['channel']:<3} {item['track']:<28} {item['notes']} not")
            else:
                print(f"  --   {item['track']:<28} dilewati (kosong)")
        for name, other, channel in result["collisions"]:
            print(f"gp2midi: {name} berbagi channel {channel} dengan {other}", file=sys.stderr)
        return 0

    if args.split:
        out_dir = Path(args.output) if args.output else Path(args.input).with_suffix("")
        results = to_midi_per_track(score, out_dir, options)
        if not results:
            print("gp2midi: tidak ada track dengan not", file=sys.stderr)
            return 1
        for item in results:
            print(f"{item['path']}  ({item['notes']} not)")
        return 0

    out_path = Path(args.output) if args.output else Path(args.input).with_suffix(".mid")
    result = to_midi(score, out_path, options)
    print(f"{result['path']}  type {result['format']}, PPQ {result['ppq']}, {result['bars_played']} bar")
    for item in result["tracks"]:
        if item["written"]:
            print(f"  ch{item['channel']:<3} {item['track']:<28} {item['notes']} not")
        else:
            print(f"  --   {item['track']:<28} dilewati (kosong)")
    return 0


def _cmd_play(args) -> int:
    try:
        from .play.cli import run   # lazy: info/convert/check tetap jalan tanpa FluidSynth
        return run(args)
    except ImportError:
        print('gp2midi: playback butuh FluidSynth; pasang dengan pip install "gp2midi[play]"',
              file=sys.stderr)
        return 2


def _cmd_check(args) -> int:
    """Deteksi bar yang durasi beat-nya tidak pas dengan time signature."""
    score = _load(args.input)
    problems = []
    for track in score.tracks:
        for index, bar in enumerate(track.bars):
            expected = score.master_bars[index].length
            for voice_index, voice in enumerate(bar.voices):
                if not voice.beats:
                    continue
                total = sum(b.duration for b in voice.beats if not b.grace)
                if total != expected:
                    problems.append((track.name, index + 1, voice_index + 1, total, expected))

    if not problems:
        print(f"OK: {len(score.master_bars)} bar x {len(score.tracks)} track, semua durasi pas")
        return 0

    for name, bar, voice, total, expected in problems[:50]:
        print(f"bar {bar:<4} {name:<28} voice {voice}: {total} tick, seharusnya {expected}")
    if len(problems) > 50:
        print(f"... dan {len(problems) - 50} lainnya")
    print(f"{len(problems)} voice tidak pas", file=sys.stderr)
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gp2midi",
        description="Konversi file Guitar Pro 7/8 (.gp) menjadi Standard MIDI File multi-track.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("input", help="file .gp atau .gpif")
    common.add_argument("--no-expand-repeats", action="store_true",
                        help="jangan expand tanda ulang / alternate ending")

    info = sub.add_parser("info", parents=[common], help="tampilkan isi skor")
    info.add_argument("--json", action="store_true", help="keluaran JSON")
    info.set_defaults(func=_cmd_info)

    convert = sub.add_parser("convert", parents=[common], help="tulis file MIDI")
    convert.add_argument("-o", "--output",
                         help="file .mid tujuan (dipakai oleh mode normal maupun --merge; folder bila --split)")
    mode = convert.add_mutually_exclusive_group()
    mode.add_argument("--split", action="store_true",
                      help="tulis satu file MIDI per track, bukan satu file multi-track")
    mode.add_argument("--merge", action="store_true",
                      help="tulis satu file MIDI type 0, semua track digabung jadi satu")
    convert.add_argument("--gate", type=float, default=1.0,
                         help="pengali panjang not, 1.0 = legato penuh (default 1.0)")
    convert.add_argument("--include-empty", action="store_true",
                         help="ikut tulis track yang tidak punya not")
    convert.set_defaults(func=_cmd_convert)

    play = sub.add_parser("play", parents=[common], help="mainkan file langsung lewat FluidSynth")
    play.add_argument("--from", dest="from_bar", type=int, default=1, metavar="BAR",
                      help="mulai dari bar ke-BAR (1-based, urutan playback; default 1)")
    play.add_argument("--seconds", type=float, default=None, metavar="N",
                      help="berhenti setelah N detik playback (default: sampai habis)")
    play.add_argument("--soundfont", default=None, metavar="PATH",
                      help="file .sf2 (default: kandidat sistem, coba /usr/share/sounds/sf2/TimGM6mb.sf2 dst)")
    play.add_argument("--driver", default=None, metavar="NAME",
                      help="paksa driver audio tertentu (default: pulseaudio lalu alsa di Linux)")
    play.add_argument("--gain", type=float, default=0.5, metavar="G",
                      help="0.0-10.0 (default 0.5)")
    play.add_argument("--silent", action="store_true",
                      help="gain 0.0; driver tetap dibuka dan jam tetap nyata, jadi "
                           "pengukuran drift tetap sah tanpa mengeluarkan suara")
    play.add_argument("--report", action="store_true",
                      help="cetak Report di akhir; exit 1 kalau drift > 50 ms atau late_events > 0")
    play.add_argument("--gate", type=float, default=1.0,
                      help="pengali panjang not, 1.0 = legato penuh (default 1.0)")
    play.set_defaults(func=_cmd_play)

    check = sub.add_parser("check", parents=[common],
                           help="periksa kecocokan durasi beat dengan time signature")
    check.set_defaults(func=_cmd_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
