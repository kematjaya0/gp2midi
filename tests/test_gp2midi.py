import struct
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixture import simple_score, write_gp
from gp2midi import convert, gpif, smf
from gp2midi.model import MasterBar, Score, Track


def parse_fixture(gpif_xml=None):
    tmp = Path(tempfile.mkdtemp()) / "fixture.gp"
    write_gp(tmp, gpif_xml or simple_score())
    return gpif.parse(tmp)


def empty_track(index: int) -> Track:
    """Track tanpa bar sama sekali — tidak ada di korpus media/, hanya di fixture."""
    return Track(index=index, name="Kosong", short_name="ksg", program=0,
                 bank_msb=0, bank_lsb=0, is_drums=False, volume=0.8, pan=0.5,
                 tuning=[], bars=[])


class TestVlq(unittest.TestCase):
    def test_known_values(self):
        self.assertEqual(smf.vlq(0), b"\x00")
        self.assertEqual(smf.vlq(127), b"\x7f")
        self.assertEqual(smf.vlq(128), b"\x81\x00")
        self.assertEqual(smf.vlq(0x3FFF), b"\xff\x7f")
        self.assertEqual(smf.vlq(0x4000), b"\x81\x80\x00")
        self.assertEqual(smf.vlq(0x100000), b"\xc0\x80\x00")
        self.assertEqual(smf.vlq(0x0FFFFFFF), b"\xff\xff\xff\x7f")

    def test_negative_rejected(self):
        with self.assertRaises(ValueError):
            smf.vlq(-1)


class TestRhythm(unittest.TestCase):
    def ticks(self, xml):
        return gpif._rhythm_ticks(ET.fromstring(xml))

    def test_plain_values(self):
        self.assertEqual(self.ticks("<Rhythm><NoteValue>Whole</NoteValue></Rhythm>"), 3840)
        self.assertEqual(self.ticks("<Rhythm><NoteValue>Quarter</NoteValue></Rhythm>"), 960)
        self.assertEqual(self.ticks("<Rhythm><NoteValue>32nd</NoteValue></Rhythm>"), 120)

    def test_dots(self):
        self.assertEqual(
            self.ticks('<Rhythm><NoteValue>Quarter</NoteValue><AugmentationDot count="1"/></Rhythm>'), 1440)
        self.assertEqual(
            self.ticks('<Rhythm><NoteValue>Half</NoteValue><AugmentationDot count="2"/></Rhythm>'), 3360)

    def test_tuplet(self):
        self.assertEqual(
            self.ticks('<Rhythm><NoteValue>Quarter</NoteValue><PrimaryTuplet num="3" den="2"/></Rhythm>'), 640)

    def test_unknown_value(self):
        with self.assertRaises(gpif.GpifError):
            self.ticks("<Rhythm><NoteValue>Bogus</NoteValue></Rhythm>")


class TestParse(unittest.TestCase):
    def setUp(self):
        self.score = parse_fixture()

    def test_metadata(self):
        self.assertEqual(self.score.title, "Fixture")
        self.assertEqual(self.score.artist, "Tester")
        self.assertEqual(self.score.ppq, 960)

    def test_tempo(self):
        self.assertEqual(len(self.score.tempos), 1)
        self.assertEqual(self.score.tempos[0].bpm, 100.0)
        self.assertEqual(self.score.tempos[0].tick, 0)

    def test_tracks(self):
        self.assertEqual(len(self.score.tracks), 2)
        guitar, drums = self.score.tracks
        self.assertEqual(guitar.name, "Gitar")
        self.assertEqual(guitar.program, 30)
        self.assertFalse(guitar.is_drums)
        self.assertEqual(guitar.tuning, [40, 45, 50, 55, 59, 64])
        self.assertAlmostEqual(guitar.volume, 0.80)
        self.assertTrue(drums.is_drums)

    def test_bars_filled(self):
        for track in self.score.tracks:
            for index, bar in enumerate(track.bars):
                for voice in bar.voices:
                    if voice.beats:
                        total = sum(b.duration for b in voice.beats)
                        self.assertEqual(total, self.score.master_bars[index].length)

    def test_shared_beat_reuse(self):
        # voice 2 memakai beat id 5 empat kali; tiap kemunculan harus jadi objek sendiri
        drum_bar = self.score.tracks[1].bars[0]
        beats = drum_bar.voices[0].beats
        self.assertEqual(len(beats), 4)
        self.assertEqual(len({id(b) for b in beats}), 4)


class TestTempoUnit(unittest.TestCase):
    def test_unit_scaling(self):
        xml = simple_score().replace("<Value>100 2</Value>", "<Value>100 1</Value>")
        self.assertEqual(parse_fixture(xml).tempos[0].bpm, 200.0)
        xml = simple_score().replace("<Value>100 2</Value>", "<Value>100 3</Value>")
        self.assertEqual(parse_fixture(xml).tempos[0].bpm, 50.0)


class TestPlaybackOrder(unittest.TestCase):
    def score_with(self, specs):
        bars = []
        for i, (start, count, endings) in enumerate(specs):
            bars.append(MasterBar(index=i, numerator=4, denominator=4, length=3840,
                                  start=i * 3840, repeat_start=start,
                                  repeat_count=count, alternate_endings=endings))
        return Score(title="x", subtitle="", artist="", album="", ppq=960, master_bars=bars)

    def test_no_repeats(self):
        score = self.score_with([(False, 0, 0)] * 4)
        self.assertEqual(convert.playback_order(score), [0, 1, 2, 3])

    def test_simple_repeat(self):
        score = self.score_with([(False, 0, 0), (True, 0, 0), (False, 2, 0), (False, 0, 0)])
        self.assertEqual(convert.playback_order(score), [0, 1, 2, 1, 2, 3])

    def test_repeat_disabled(self):
        score = self.score_with([(False, 0, 0), (True, 0, 0), (False, 2, 0), (False, 0, 0)])
        self.assertEqual(convert.playback_order(score, expand_repeats=False), [0, 1, 2, 3])

    def test_alternate_endings(self):
        # bar0 awal ulang, bar1 ending 1 + tanda tutup 2x, bar2 ending 2
        score = self.score_with([(True, 0, 0), (False, 2, 0b01), (False, 0, 0b10)])
        self.assertEqual(convert.playback_order(score), [0, 1, 0, 2])

    def test_two_repeat_groups(self):
        score = self.score_with([
            (True, 0, 0), (False, 2, 0),
            (True, 0, 0), (False, 2, 0),
        ])
        self.assertEqual(convert.playback_order(score), [0, 1, 0, 1, 2, 3, 2, 3])


class TestConvert(unittest.TestCase):
    def setUp(self):
        self.score = parse_fixture()
        self.out = Path(tempfile.mkdtemp())

    def test_multitrack_file(self):
        result = convert.to_midi(self.score, self.out / "out.mid")
        self.assertEqual(result["format"], 1)
        self.assertEqual(result["bars_played"], 2)
        self.assertEqual([t["channel"] for t in result["tracks"]], [1, 10])
        raw = (self.out / "out.mid").read_bytes()
        self.assertTrue(raw.startswith(b"MThd"))
        _, fmt, ntrk, ppq = struct.unpack(">IHHH", raw[4:14])
        self.assertEqual((fmt, ntrk, ppq), (1, 3, 960))

    def test_track_count_matches_source(self):
        result = convert.to_midi(self.score, self.out / "out.mid")
        written = [t for t in result["tracks"] if t["written"]]
        self.assertEqual(len(written), len(self.score.tracks))

    def test_drums_on_channel_ten(self):
        channels = convert._assign_channels(self.score.tracks)
        self.assertEqual(channels[1], convert.DRUM_CHANNEL)

    def test_tie_merges_into_one_note(self):
        order = convert.playback_order(self.score)
        starts, _ = convert._bar_starts(self.score, order)
        notes = convert._track_notes(self.score.tracks[0], order, starts, convert.Options())
        tied = [n for n in notes if n.pitch == 71]
        self.assertEqual(len(tied), 1)
        # quarter di beat 4 + whole note bar berikutnya
        self.assertEqual(tied[0].start, 2880)
        self.assertEqual(tied[0].end, 2880 + 960 + 3840)

    def test_dead_note_shortened(self):
        order = convert.playback_order(self.score)
        starts, _ = convert._bar_starts(self.score, order)
        notes = convert._track_notes(self.score.tracks[0], order, starts, convert.Options())
        dead = next(n for n in notes if n.pitch == 69)
        self.assertEqual(dead.end - dead.start, convert.DEAD_NOTE_TICKS)

    def test_dynamic_velocity(self):
        order = convert.playback_order(self.score)
        starts, _ = convert._bar_starts(self.score, order)
        notes = convert._track_notes(self.score.tracks[0], order, starts, convert.Options())
        self.assertEqual(next(n for n in notes if n.pitch == 64).velocity, 79)
        self.assertEqual(next(n for n in notes if n.pitch == 69).velocity, 47)

    def test_gate_shortens_notes(self):
        order = convert.playback_order(self.score)
        starts, _ = convert._bar_starts(self.score, order)
        notes = convert._track_notes(self.score.tracks[0], order, starts, convert.Options(gate=0.5))
        plain = next(n for n in notes if n.pitch == 64)
        self.assertEqual(plain.end - plain.start, 480)

    def test_split_writes_one_file_per_track(self):
        results = convert.to_midi_per_track(self.score, self.out / "split")
        self.assertEqual(len(results), 2)
        for item in results:
            raw = Path(item["path"]).read_bytes()
            _, fmt, ntrk, _ = struct.unpack(">IHHH", raw[4:14])
            self.assertEqual((fmt, ntrk), (0, 1))

    def test_note_off_precedes_note_on_at_same_tick(self):
        track = smf.MidiTrack()
        track.note_on(0, 0, 60, 80)
        track.note_off(960, 0, 60)
        track.note_on(960, 0, 60, 80)
        body = track.serialize()
        self.assertLess(body.index(b"\x80\x3c\x00"), body.rindex(b"\x90\x3c\x50"))


class TestMerged(unittest.TestCase):
    def setUp(self):
        self.score = parse_fixture()
        self.out = Path(tempfile.mkdtemp())

    def test_type_zero_single_track(self):
        convert.to_midi_merged(self.score, self.out / "m.mid")
        raw = (self.out / "m.mid").read_bytes()
        self.assertTrue(raw.startswith(b"MThd"))
        _, fmt, ntrk, _ = struct.unpack(">IHHH", raw[4:14])
        self.assertEqual((fmt, ntrk), (0, 1))

    def test_exactly_one_track_name(self):
        # meta track name (FF 03) hanya dari konduktor — setup track tidak boleh menambah lagi
        convert.to_midi_merged(self.score, self.out / "m.mid")
        raw = (self.out / "m.mid").read_bytes()
        self.assertEqual(raw.count(b"\xff\x03"), 1)

    def test_channels_preserved(self):
        result = convert.to_midi_merged(self.score, self.out / "m.mid")
        self.assertEqual([t["channel"] for t in result["tracks"]], [1, 10])
        raw = (self.out / "m.mid").read_bytes()
        self.assertIn(b"\x90", raw)  # note-on channel 1
        self.assertIn(b"\x99", raw)  # note-on channel 10 (drum)

    def test_note_count_matches_multitrack(self):
        multi = convert.to_midi(self.score, self.out / "a.mid")
        merged = convert.to_midi_merged(self.score, self.out / "m.mid")
        def total(summary):
            return sum(t["notes"] for t in summary["tracks"])
        self.assertEqual(total(merged), total(multi))

    def test_tempo_and_timesig_present(self):
        convert.to_midi_merged(self.score, self.out / "m.mid")
        raw = (self.out / "m.mid").read_bytes()
        self.assertIn(b"\xff\x51", raw)  # FF 51 = set tempo
        self.assertIn(b"\xff\x58", raw)  # FF 58 = time signature


    def test_empty_track_skipped(self):
        # regresi: jalur merged pernah memanggil helper yang tidak ada, jadi satu
        # track tanpa not cukup untuk membuat --merge mati dengan NameError
        self.score.tracks.append(empty_track(len(self.score.tracks)))
        result = convert.to_midi_merged(self.score, self.out / "m.mid")
        last = result["tracks"][-1]
        self.assertEqual((last["notes"], last["written"]), (0, False))
        self.assertIsNone(last["channel"])

    def test_empty_track_written_when_requested(self):
        self.score.tracks.append(empty_track(len(self.score.tracks)))
        result = convert.to_midi_merged(
            self.score, self.out / "m.mid", convert.Options(include_empty=True))
        self.assertTrue(result["tracks"][-1]["written"])


class TestContainerErrors(unittest.TestCase):
    def test_unknown_format(self):
        from gp2midi.container import UnsupportedContainer, read_gpif
        path = Path(tempfile.mkdtemp()) / "x.gp"
        path.write_bytes(b"\x00\x01\x02\x03rubbish")
        with self.assertRaises(UnsupportedContainer):
            read_gpif(path)

    def test_gpx_rejected_with_hint(self):
        from gp2midi.container import UnsupportedContainer, read_gpif
        path = Path(tempfile.mkdtemp()) / "x.gpx"
        path.write_bytes(b"BCFZ" + b"\x00" * 16)
        with self.assertRaisesRegex(UnsupportedContainer, "gpx"):
            read_gpif(path)

    def test_plain_gpif_xml(self):
        path = Path(tempfile.mkdtemp()) / "score.gpif"
        path.write_text(simple_score())
        self.assertEqual(gpif.parse(path).title, "Fixture")


if __name__ == "__main__":
    unittest.main(verbosity=2)
