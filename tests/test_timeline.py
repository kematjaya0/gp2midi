import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixture import simple_score, write_gp
from gp2midi import gpif
from gp2midi.convert import Options, to_midi
from gp2midi.model import Score, TempoChange
from gp2midi.timeline import TempoMap, build_timeline


def parse_fixture(gpif_xml=None):
    tmp = Path(tempfile.mkdtemp()) / "fixture.gp"
    write_gp(tmp, gpif_xml or simple_score())
    return gpif.parse(tmp)


class TestTimeline(unittest.TestCase):
    def setUp(self):
        self.score = parse_fixture()
        self.tl = build_timeline(self.score)

    def test_notes_match_convert(self):
        result = to_midi(self.score, Path(self.tmp_dir()) / "out.mid")
        total = sum(t["notes"] for t in result["tracks"])
        self.assertEqual(len(self.tl.notes), total)

    def tmp_dir(self):
        return Path(tempfile.mkdtemp())

    def test_notes_sorted(self):
        keys = [(n.start, n.pitch, n.track) for n in self.tl.notes]
        self.assertEqual(keys, sorted(keys))

    def test_note_has_channel_and_track(self):
        guitar, drums = self.score.tracks
        guitar_notes = self.tl.notes_of(guitar.index)
        drum_notes = self.tl.notes_of(drums.index)
        self.assertTrue(guitar_notes)
        self.assertTrue(drum_notes)
        for note in guitar_notes:
            self.assertEqual(note.channel, 0)
            self.assertEqual(note.track, guitar.index)
        for note in drum_notes:
            self.assertEqual(note.channel, 9)
            self.assertEqual(note.track, drums.index)

    def test_end_tick_matches_bar_grid(self):
        self.assertEqual(self.tl.end_tick, sum(b.length for b in self.tl.bars))
        for i in range(1, len(self.tl.bars)):
            self.assertEqual(self.tl.bars[i].start,
                             self.tl.bars[i - 1].start + self.tl.bars[i - 1].length)


class TestTempoMap(unittest.TestCase):
    def test_tempo_map_quarter_note(self):
        self.assertEqual(TempoMap(960, [(0, 120.0)]).ms(960), 500.0)
        self.assertEqual(TempoMap(960, [(0, 60.0)]).ms(960), 1000.0)

    def test_tempo_map_change_midway(self):
        tm = TempoMap(960, [(0, 120.0), (1920, 60.0)])
        # dua ketuk pertama pada 120 BPM = 1000 ms, lalu segmen 60 BPM
        self.assertEqual(tm.ms(1920), 1000.0)
        self.assertEqual(tm.ms(2880), 2000.0)

    def test_tempo_map_roundtrip(self):
        tm = TempoMap(960, [(0, 120.0), (1920, 60.0)])
        one_tick_ms = tm.ms(1)  # durasi satu tick tempat pertama
        for t in (0, 1, 5, 960, 1920, 2000, 2500, 4000):
            difference = abs(tm.ms(tm.tick(float(t))) - float(t))
            self.assertLess(difference, one_tick_ms, f"tick {t} tidak berbulat-ulang pas")


class TestTempoValidation(unittest.TestCase):
    def test_tempo_zero_rejected(self):
        with self.assertRaises(ValueError):
            TempoMap(960, [(0, 0.0)])

    def test_tempo_without_zero_point_gets_default(self):
        score = Score(title="", subtitle="", artist="", album="", ppq=960,
                      tempos=[TempoChange(tick=480, bpm=100.0)])
        points = TempoMap.from_score(score).points
        self.assertEqual(points[0], (0, 120.0))
        self.assertEqual(points[1], (480, 100.0))


class TestBarTick(unittest.TestCase):
    def test_bar_tick_out_of_range(self):
        tmp = Path(tempfile.mkdtemp()) / "fixture.gp"
        write_gp(tmp, simple_score())
        self.tl = build_timeline(gpif.parse(tmp))
        bars = len(self.tl.bars)
        with self.assertRaises(ValueError):
            self.tl.bar_tick(0)
        with self.assertRaises(ValueError):
            self.tl.bar_tick(bars + 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
