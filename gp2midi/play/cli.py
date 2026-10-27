"""Eksekusi subcommand `play`. Parser definisinya di gp2midi/cli.py (stdlib)."""

from __future__ import annotations

import sys


def _fmt_duration(ms: float) -> str:
    total = int(ms / 1000)
    return f"{total // 60}:{total % 60:02d}"


def run(args) -> int:
    from gp2midi import parse
    from gp2midi.container import UnsupportedContainer
    from gp2midi.convert import Options
    from gp2midi.gpif import GpifError
    from gp2midi.play.audio import Audio, AudioError
    from gp2midi.play.scheduler import Player
    from gp2midi.timeline import build_timeline

    try:
        score = parse(args.input)
    except (OSError, UnsupportedContainer, GpifError) as exc:
        print(f"gp2midi: {exc}", file=sys.stderr)
        return 2

    timeline = build_timeline(score, Options(
        expand_repeats=not args.no_expand_repeats,
        gate=args.gate,
        include_empty=False,
    ))
    print(f"{score.title or args.input} — {len(timeline.bars)} bar, "
          f"{len(timeline.notes)} not, {_fmt_duration(timeline.duration_ms)}")

    gain = 0.0 if args.silent else args.gain
    try:
        audio = Audio(soundfont=args.soundfont, gain=gain, driver=args.driver, realtime=True)
    except (AudioError, FileNotFoundError, TypeError, ValueError) as exc:
        print(f"gp2midi: {exc}", file=sys.stderr)
        return 2

    player = Player(timeline, audio)
    try:
        from_tick = timeline.bar_tick(args.from_bar)   # ValueError bila di luar rentang
        player.setup_instruments()
        limit_ms = args.seconds * 1000.0 if args.seconds is not None else None
        player.play(from_tick, limit_ms=limit_ms)
        report = player.wait()
    except ValueError as exc:
        print(f"gp2midi: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        # Ctrl-C harus berhenti bersih: tanpa not nyangkut
        print(file=sys.stderr)
        player.close()
        audio.close()
        return 130

    player.close()
    audio.close()
    for warning in audio.warnings:
        print(f"gp2midi: {warning}", file=sys.stderr)

    if args.report:
        print(f"expected {report.expected_ms:.1f} ms  actual {report.actual_ms:.1f} ms  "
              f"drift {report.drift_ms:+.1f} ms  late {report.late_events}  "
              f"max_fill_lag {report.max_fill_lag_ms:.1f} ms  notes {report.notes_scheduled}")
        if not report.ok():
            return 1
    return 0
