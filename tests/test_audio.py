import importlib.util
import unittest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

HAS_FLUID = importlib.util.find_spec("fluidsynth") is not None


@unittest.skipUnless(HAS_FLUID, "butuh pyfluidsynth (.venv-app)")
class TestAudio(unittest.TestCase):
    # realtime=False supaya tidak berbunyi dan tidak butuh kartu suara;
    # gain=0.0 sebagai pengaman kedua (kecuali test yang mengukur sampel)
    def open_audio(self, gain: float = 0.0):
        from gp2midi.play.audio import Audio
        audio = Audio(realtime=False, gain=gain)
        self.addCleanup(audio.close)
        return audio

    def test_open_and_close(self):
        from gp2midi.play.audio import Audio
        audio = Audio(realtime=False, gain=0.0)
        audio.close()
        audio.close()  # idempoten
        self.assertIsNone(audio._synth)
        self.assertIsNone(audio._seq)

    def test_validation_rejects_before_c(self):
        audio = self.open_audio()
        # kalau salah satu malah membuat proses mati, validasinya tidak jalan
        with self.assertRaises(ValueError):
            audio.note_on(0, 16, 60, 100)
        with self.assertRaises(ValueError):
            audio.note_on(0, 0, 60, 200)
        with self.assertRaises(ValueError):
            audio.note_on(-1, 0, 60, 100)

    def test_drum_bank_128(self):
        audio = self.open_audio(gain=0.2)
        audio.select_program(9, 0, drums=True)
        self.assertEqual(audio.warnings, [],
                         f"program drum bank 128 jangan menambah warning: {audio.warnings}")

        # render manual (fakta F-5): ambang aman, TimGM6mb snare diharapkan > 100
        audio._synth.noteon(9, 38, 100)
        peak = 0
        for _ in range(20):
            samples = audio._synth.get_samples(2048)
            peak = max(peak, int(abs(samples).max()))
        audio._synth.noteoff(9, 38)
        self.assertGreater(peak, 100)

    def test_clear_scheduled_is_safe(self):
        audio = self.open_audio()
        now = audio.now()
        # jadwalkan not jauh di depan
        audio.note_on(now + 5000, 0, 60, 100)
        audio.note_off(now + 5500, 0, 60)
        audio.panic()  # tidak crash
        self.assertIsInstance(audio.now(), int)


if __name__ == "__main__":
    unittest.main(verbosity=2)
