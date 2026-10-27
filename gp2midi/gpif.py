"""Parser GPIF (Guitar Pro 7/8) menjadi model skor."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .container import read_gpif
from .model import Bar, Beat, MasterBar, Note, Score, TempoChange, Track, Voice

PPQ = 960

# nilai not sebagai kelipatan whole note
NOTE_VALUES = {
    "Long": 4.0,
    "DoubleWhole": 2.0,
    "Whole": 1.0,
    "Half": 1 / 2,
    "Quarter": 1 / 4,
    "Eighth": 1 / 8,
    "16th": 1 / 16,
    "32nd": 1 / 32,
    "64th": 1 / 64,
    "128th": 1 / 128,
    "256th": 1 / 256,
}

DRUM_INSTRUMENT_TYPES = {"drumKit", "percussions"}


class GpifError(Exception):
    pass


def _text(el: ET.Element | None, default: str = "") -> str:
    if el is None or el.text is None:
        return default
    return el.text.strip()


def _find_text(parent: ET.Element, path: str, default: str = "") -> str:
    return _text(parent.find(path), default)


def _prop(parent: ET.Element, name: str) -> ET.Element | None:
    return parent.find(f'Properties/Property[@name="{name}"]')


def _whole_note_ticks() -> int:
    return PPQ * 4


def _rhythm_ticks(rhythm: ET.Element) -> int:
    value = _find_text(rhythm, "NoteValue", "Quarter")
    if value not in NOTE_VALUES:
        raise GpifError(f"NoteValue tidak dikenal: {value!r}")
    fraction = NOTE_VALUES[value]

    dot = rhythm.find("AugmentationDot")
    if dot is not None:
        count = int(dot.get("count", "1"))
        fraction *= 2 - 2 ** -count

    tuplet = rhythm.find("PrimaryTuplet")
    if tuplet is not None:
        num = int(tuplet.get("num", "1"))
        den = int(tuplet.get("den", "1"))
        if num > 0:
            fraction = fraction * den / num

    return round(fraction * _whole_note_ticks())


def _parse_note(el: ET.Element) -> Note | None:
    midi_el = _prop(el, "Midi")
    if midi_el is None:
        # not tanpa pitch MIDI (mis. not mati tanpa pitch) -> lewati
        return None
    midi = int(_find_text(midi_el, "Number", "-1"))
    if not 0 <= midi <= 127:
        return None

    tie = el.find("Tie")
    fret_el = _prop(el, "Fret")
    string_el = _prop(el, "String")

    return Note(
        midi=midi,
        tie_origin=tie is not None and tie.get("origin") == "true",
        tie_destination=tie is not None and tie.get("destination") == "true",
        muted=_prop(el, "Muted") is not None,
        palm_muted=_prop(el, "PalmMuted") is not None,
        fret=int(_find_text(fret_el, "Fret", "0")) if fret_el is not None else None,
        string=int(_find_text(string_el, "String", "0")) if string_el is not None else None,
    )


def _channel_strip(track_el: ET.Element) -> tuple[float, float]:
    params = _find_text(track_el, "RSE/ChannelStrip/Parameters")
    if not params:
        return 1.0, 0.5
    values = [float(x) for x in params.split()]
    pan = values[11] if len(values) > 11 else 0.5
    volume = values[12] if len(values) > 12 else 1.0
    return volume, pan


def parse(path: str | Path) -> Score:
    root = ET.fromstring(read_gpif(path))
    if root.tag != "GPIF":
        raise GpifError(f"root element {root.tag!r}, bukan GPIF")

    score_el = root.find("Score")
    if score_el is None:
        raise GpifError("tidak ada elemen <Score>")

    rhythms = {
        el.get("id"): _rhythm_ticks(el) for el in root.findall("Rhythms/Rhythm")
    }
    note_pool = {el.get("id"): el for el in root.findall("Notes/Note")}
    beat_pool = {el.get("id"): el for el in root.findall("Beats/Beat")}
    voice_pool = {el.get("id"): el for el in root.findall("Voices/Voice")}
    bar_pool = {el.get("id"): el for el in root.findall("Bars/Bar")}

    def build_beat(beat_id: str) -> Beat:
        el = beat_pool[beat_id]
        rhythm_ref = el.find("Rhythm")
        ref = rhythm_ref.get("ref") if rhythm_ref is not None else None
        if ref not in rhythms:
            raise GpifError(f"beat {beat_id} merujuk rhythm {ref!r} yang tidak ada")

        notes: list[Note] = []
        for note_id in _find_text(el, "Notes").split():
            note = _parse_note(note_pool[note_id])
            if note is not None:
                notes.append(note)

        grace = _find_text(el, "GraceNotes") or None
        return Beat(
            duration=rhythms[ref],
            notes=notes,
            dynamic=_find_text(el, "Dynamic", "F"),
            grace=grace,
        )

    def build_bar(bar_id: str) -> Bar:
        el = bar_pool[bar_id]
        voices: list[Voice] = []
        for voice_id in _find_text(el, "Voices").split():
            if voice_id == "-1":
                voices.append(Voice())
                continue
            beats = [build_beat(b) for b in _find_text(voice_pool[voice_id], "Beats").split()]
            voices.append(Voice(beats=beats))
        return Bar(voices=voices)

    # --- urutan track pada MasterTrack menentukan posisi id di <Bars> setiap MasterBar
    track_order = _find_text(root, "MasterTrack/Tracks").split()
    track_elements = root.findall("Tracks/Track")
    position_of = {tid: i for i, tid in enumerate(track_order)}

    tracks: list[Track] = []
    for index, track_el in enumerate(track_elements):
        sound_midi = track_el.find("Sounds/Sound/MIDI")
        instrument_type = _find_text(track_el, "InstrumentSet/Type")
        volume, pan = _channel_strip(track_el)
        tuning = [
            int(x)
            for x in _find_text(
                track_el, 'Staves/Staff/Properties/Property[@name="Tuning"]/Pitches'
            ).split()
        ]
        tracks.append(
            Track(
                index=index,
                name=_find_text(track_el, "Name", f"Track {index + 1}"),
                short_name=_find_text(track_el, "ShortName"),
                program=int(_find_text(sound_midi, "Program", "0")) if sound_midi is not None else 0,
                bank_msb=int(_find_text(sound_midi, "MSB", "0")) if sound_midi is not None else 0,
                bank_lsb=int(_find_text(sound_midi, "LSB", "0")) if sound_midi is not None else 0,
                is_drums=instrument_type in DRUM_INSTRUMENT_TYPES,
                volume=volume,
                pan=pan,
                tuning=tuning,
            )
        )

    master_bars: list[MasterBar] = []
    cursor = 0
    for bar_index, mb_el in enumerate(root.findall("MasterBars/MasterBar")):
        time = _find_text(mb_el, "Time", "4/4")
        try:
            numerator, denominator = (int(x) for x in time.split("/"))
        except ValueError as exc:
            raise GpifError(f"time signature tidak valid di bar {bar_index + 1}: {time!r}") from exc
        length = round(numerator * _whole_note_ticks() / denominator)

        accidentals = int(_find_text(mb_el, "Key/AccidentalCount", "0"))
        mode = _find_text(mb_el, "Key/Mode", "Major")

        repeat_el = mb_el.find("Repeat")
        alternate = _find_text(mb_el, "AlternateEndings")

        master_bars.append(
            MasterBar(
                index=bar_index,
                numerator=numerator,
                denominator=denominator,
                length=length,
                start=cursor,
                repeat_start=repeat_el is not None and repeat_el.get("start") == "true",
                repeat_count=int(repeat_el.get("count", "0")) if repeat_el is not None else 0,
                alternate_endings=_alternate_mask(alternate),
                section=_find_text(mb_el, "Section/Letter") or _find_text(mb_el, "Section/Text") or None,
                key_accidentals=accidentals,
                key_minor=mode.lower() == "minor",
            )
        )
        cursor += length

        bar_ids = _find_text(mb_el, "Bars").split()
        for track in tracks:
            track_id = track_order[track.index] if track.index < len(track_order) else str(track.index)
            slot = position_of.get(track_id, track.index)
            if slot < len(bar_ids):
                track.bars.append(build_bar(bar_ids[slot]))
            else:
                track.bars.append(Bar())

    tempos = _parse_tempos(root, master_bars)

    return Score(
        title=_find_text(score_el, "Title"),
        subtitle=_find_text(score_el, "SubTitle"),
        artist=_find_text(score_el, "Artist"),
        album=_find_text(score_el, "Album"),
        ppq=PPQ,
        master_bars=master_bars,
        tracks=tracks,
        tempos=tempos,
    )


def _alternate_mask(raw: str) -> int:
    if not raw:
        return 0
    mask = 0
    for token in raw.split():
        try:
            number = int(token)
        except ValueError:
            continue
        if 1 <= number <= 8:
            mask |= 1 << (number - 1)
    return mask


def _parse_tempos(root: ET.Element, master_bars: list[MasterBar]) -> list[TempoChange]:
    tempos: list[TempoChange] = []
    for automation in root.findall("MasterTrack/Automations/Automation"):
        if _find_text(automation, "Type") != "Tempo":
            continue
        bar_index = int(_find_text(automation, "Bar", "0"))
        position = float(_find_text(automation, "Position", "0"))
        value = _find_text(automation, "Value", "120").split()
        bpm = float(value[0])
        # unit kedua: 1=half, 2=quarter, 3=eighth, 4=quarter dotted, 5=eighth dotted
        unit = int(value[1]) if len(value) > 1 else 2
        bpm *= {1: 2.0, 2: 1.0, 3: 0.5, 4: 1.5, 5: 0.75}.get(unit, 1.0)

        if bar_index < len(master_bars):
            bar = master_bars[bar_index]
            tick = bar.start + round(position * PPQ)
        else:
            tick = 0
        tempos.append(TempoChange(tick=tick, bpm=bpm))

    if not tempos:
        tempos.append(TempoChange(tick=0, bpm=120.0))
    tempos.sort(key=lambda t: t.tick)
    if tempos[0].tick != 0:
        tempos.insert(0, TempoChange(tick=0, bpm=tempos[0].bpm))
    return tempos
