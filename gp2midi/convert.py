"""Konversi model skor menjadi Standard MIDI File."""

from __future__ import annotations

from pathlib import Path

from .model import Score, Track
from .smf import MidiTrack, write_file
from .timeline import (
    DEAD_NOTE_TICKS,
    DRUM_CHANNEL,
    DYNAMIC_VELOCITY,
    Options,
    PlayedNote,
    Timeline,
    _assign_channels,
    _bar_starts,
    _track_notes,
    build_timeline,
    playback_order,
)

# Pemanggil lama (CLI, test) mengimpor jalur hitung dari sini. Sekarang jalur
# itu milik timeline.py — di-re-export supaya tidak ada yang perlu diubah.
__all__ = [
    "DEAD_NOTE_TICKS",
    "DRUM_CHANNEL",
    "DYNAMIC_VELOCITY",
    "Options",
    "PlayedNote",
    "Timeline",
    "build_timeline",
    "playback_order",
    "to_midi",
    "to_midi_merged",
    "to_midi_per_track",
]


def _write_channel_setup(midi: MidiTrack, track: Track, channel: int) -> None:
    """Bank, program, volume, pan. Tanpa nama track, supaya aman dipakai di SMF type 0."""
    if track.bank_msb or track.bank_lsb:
        midi.control_change(0, channel, 0, track.bank_msb)
        midi.control_change(0, channel, 32, track.bank_lsb)
    midi.program_change(0, channel, 0 if track.is_drums else track.program)
    midi.control_change(0, channel, 7, max(0, min(127, round(track.volume * 127))))
    midi.control_change(0, channel, 10, max(0, min(127, round(track.pan * 127))))


def _write_setup(midi: MidiTrack, track: Track, channel: int) -> None:
    midi.track_name(track.name or f"Track {track.index + 1}")
    _write_channel_setup(midi, track, channel)


def _emit(midi: MidiTrack, notes: list[PlayedNote], channel: int) -> None:
    for note in notes:
        midi.note_on(note.start, channel, note.pitch, note.velocity)
        midi.note_off(note.end, channel, note.pitch)


def _conductor(timeline: Timeline, score: Score) -> MidiTrack:
    midi = MidiTrack()
    midi.track_name(score.title or "Score")
    if score.artist:
        midi.text(0, f"Artist: {score.artist}")

    for tempo in score.tempos:
        midi.tempo(min(tempo.tick, timeline.end_tick), tempo.bpm)

    previous_time = None
    previous_key = None
    for bar in timeline.bars:
        master = score.master_bars[bar.source]
        time = (master.numerator, master.denominator)
        if time != previous_time:
            midi.time_signature(bar.start, master.numerator, master.denominator)
            previous_time = time
        key = (master.key_accidentals, master.key_minor)
        if key != previous_key:
            midi.key_signature(bar.start, master.key_accidentals, master.key_minor)
            previous_key = key
        if master.section:
            midi.marker(bar.start, master.section)
    return midi


def to_midi(score: Score, out_path: str | Path, options: Options | None = None) -> dict:
    """Tulis satu SMF type 1: track konduktor + satu MTrk per track Guitar Pro."""
    timeline = build_timeline(score, options)
    options = options or Options()

    midi_tracks = [_conductor(timeline, score)]
    summary = []

    for track in score.tracks:
        notes = timeline.notes_of(track.index)
        if not notes and not options.include_empty:
            summary.append({"track": track.name, "notes": 0, "channel": None, "written": False})
            continue
        channel = timeline.channels[track.index]
        midi = MidiTrack()
        _write_setup(midi, track, channel)
        _emit(midi, notes, channel)
        midi_tracks.append(midi)
        summary.append(
            {"track": track.name, "notes": len(notes), "channel": channel + 1, "written": True}
        )

    write_file(out_path, midi_tracks, score.ppq)
    return {
        "path": str(out_path),
        "format": 1,
        "ppq": score.ppq,
        "bars_played": len(timeline.bars),
        "end_tick": timeline.end_tick,
        "tracks": summary,
    }


def to_midi_merged(score: Score, out_path: str | Path, options: Options | None = None) -> dict:
    """Tulis satu SMF type 0: semua track digabung ke satu MTrk, channel tetap terpisah."""
    timeline = build_timeline(score, options)
    options = options or Options()

    # konduktor di-ulang: satu-satunya track_name di file ini (nama judul lagu)
    midi = _conductor(timeline, score)
    summary = []
    collisions: list[tuple[str, str, int]] = []
    used: dict[int, str] = {}  # channel 1-based sudah dipakai track mana

    for track in score.tracks:
        notes = timeline.notes_of(track.index)
        if not notes and not options.include_empty:
            summary.append({"track": track.name, "notes": 0, "channel": None, "written": False})
            continue
        channel = timeline.channels[track.index]
        if channel + 1 in used:
            # di satu MTrk, dua track pada channel sama berarti program change saling menimpa
            collisions.append((track.name, used[channel + 1], channel + 1))
        used[channel + 1] = track.name
        _write_channel_setup(midi, track, channel)
        _emit(midi, notes, channel)
        summary.append(
            {"track": track.name, "notes": len(notes), "channel": channel + 1, "written": True}
        )

    write_file(out_path, [midi], score.ppq)
    return {
        "path": str(out_path),
        "format": 0,
        "ppq": score.ppq,
        "bars_played": len(timeline.bars),
        "end_tick": timeline.end_tick,
        "tracks": summary,
        "collisions": collisions,
    }


def to_midi_per_track(score: Score, out_dir: str | Path, options: Options | None = None) -> list[dict]:
    """Tulis satu file SMF type 0 per track Guitar Pro."""
    timeline = build_timeline(score, options)
    options = options or Options()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for track in score.tracks:
        notes = timeline.notes_of(track.index)
        if not notes and not options.include_empty:
            continue
        # mode split sengaja memakai channel sendiri (drum tetap 10, lainnya 1)
        channel = DRUM_CHANNEL if track.is_drums else 0
        midi = MidiTrack()
        for tempo in score.tempos:
            midi.tempo(min(tempo.tick, timeline.end_tick), tempo.bpm)

        previous_time = None
        for bar in timeline.bars:
            master = score.master_bars[bar.source]
            time = (master.numerator, master.denominator)
            if time != previous_time:
                midi.time_signature(bar.start, master.numerator, master.denominator)
                previous_time = time

        _write_setup(midi, track, channel)
        _emit(midi, notes, channel)

        name = _safe_filename(f"{track.index + 1:02d}-{track.name or 'track'}") + ".mid"
        path = out_dir / name
        write_file(path, [midi], score.ppq)
        results.append({"path": str(path), "track": track.name, "notes": len(notes)})
    return results


def _safe_filename(value: str) -> str:
    keep = []
    for char in value.strip():
        keep.append(char if char.isalnum() or char in " -_()" else "_")
    return "".join(keep).strip() or "track"
