import importlib.util
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixture import build_gpif, write_gp
from gp2midi import gpif
from gp2midi.timeline import build_timeline

HAS_FLUID = importlib.util.find_spec("fluidsynth") is not None


def eight_bar_score_xml() -> str:
    """Delapan bar 4/4 pada 100 BPM; tiap bar empat not quarter (midi 60), drum senyap."""
    master_bars = "\n".join(
        f"""    <MasterBar>
      <Key><AccidentalCount>0</AccidentalCount><Mode>Major</Mode></Key>
      <Time>4/4</Time>
      <Bars>{i} {8 + i}</Bars>
    </MasterBar>""" for i in range(8))
    bars = "\n".join(
        f'    <Bar id="{i}"><Clef>G2</Clef><Voices>{i} -1 -1 -1</Voices></Bar>' for i in range(8)
    ) + "\n" + "\n".join(
        f'    <Bar id="{8 + i}"><Clef>Neutral</Clef><Voices>{8 + i} -1 -1 -1</Voices></Bar>'
        for i in range(8))
    voices = "\n".join(
        f'    <Voice id="{i}"><Beats>{4 * i} {4 * i + 1} {4 * i + 2} {4 * i + 3}</Beats></Voice>'
        for i in range(8)
    ) + "\n" + "\n".join(
        f'    <Voice id="{8 + i}"><Beats>{32 + i}</Beats></Voice>' for i in range(8))
    beats = "\n".join(
        f'    <Beat id="{k}"><Rhythm ref="0"/><Dynamic>F</Dynamic><Notes>{k}</Notes></Beat>'
        for k in range(32)
    ) + "\n" + "\n".join(
        f'    <Beat id="{32 + i}"><Rhythm ref="1"/><Dynamic>F</Dynamic></Beat>'
        for i in range(8))
    notes = "\n".join(
        f"""    <Note id="{k}"><InstrumentArticulation>0</InstrumentArticulation><Properties>
      <Property name="Midi"><Number>60</Number></Property>
    </Properties></Note>""" for k in range(32))
    rhythms = """
    <Rhythm id="0"><NoteValue>Quarter</NoteValue></Rhythm>
    <Rhythm id="1"><NoteValue>Whole</NoteValue></Rhythm>"""
    return build_gpif(master_bars, bars, voices, beats, notes, rhythms)


@unittest.skipUnless(HAS_FLUID, "butuh pyfluidsynth (.venv-app)")
class TestScheduler(unittest.TestCase):
    """realtime=True (jam sequencer nyata, F-4) dan gain=0.0 — terukur tapi senyap."""

    def setUp(self):
        score_path = Path(tempfile.mkdtemp()) / "eight.gp"
        write_gp(score_path, eight_bar_score_xml())
        self.score = gpif.parse(score_path)
        self.timeline = build_timeline(self.score)

    def make_player(self):
        from gp2midi.play.audio import Audio
        from gp2midi.play.scheduler import Player
        audio = Audio(realtime=True, gain=0.0)
        player = Player(self.timeline, audio)
        self.addCleanup(audio.close)
        self.addCleanup(player.close)
        return player

    # 100 BPM -> satu bar 4/4 = 2400 ms; delapan bar = 19200 ms
    def test_short_excerpt_drift(self):
        player = self.make_player()
        player.play(limit_ms=5000)
        report = player.wait(timeout=30.0)
        self.assertLessEqual(abs(report.drift_ms), 50, f"report: {report}")
        self.assertEqual(report.late_events, 0, f"report: {report}")
        self.assertLess(report.max_fill_lag_ms, 500.0)

    def test_pause_resume_no_stuck_notes(self):
        player = self.make_player()
        player.play(limit_ms=10000)
        time.sleep(1.0)
        player.pause()
        self.assertEqual(player.state, "paused")
        first = player.position_ms
        time.sleep(0.3)
        second = player.position_ms
        self.assertAlmostEqual(first, second, delta=2.0,
                               msg="posisi harus diam saat paused")
        player.resume()
        self.assertEqual(player.state, "playing")
        time.sleep(0.3)
        self.assertGreater(player.position_ms, second, msg="posisi harus jalan lagi setelah resume")

    def test_from_bar_starts_later(self):
        player = self.make_player()
        bar_five = self.timeline.bar_tick(5)
        player.play(from_tick=bar_five, limit_ms=2000)
        self.assertGreaterEqual(player.position_tick, bar_five)
        self.assertGreater(player._cursor, 0, msg="not sebelum bar 5 jangan dijadwalkan ulang")

    def test_stop_is_idempotent(self):
        player = self.make_player()
        player.stop()
        player.stop()  # tanpa play() sebelumnya
        self.assertEqual(player.state, "stopped")

        player.play(limit_ms=1500)
        player.wait(timeout=10.0)
        player.stop()
        player.stop()

        player.close()
        self.assertFalse(player._thread.is_alive(), "thread pengisi harus mati setelah close")


if __name__ == "__main__":
    unittest.main(verbosity=2)
