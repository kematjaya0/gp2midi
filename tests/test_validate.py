"""Test tabel untuk pembatas argumen sebelum menyeberang ke C."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gp2midi.play import validate


class TestIntValidation(unittest.TestCase):
    INT_FUNCTIONS = {
        "channel": (0, 15),
        "key": (0, 127),
        "velocity": (0, 127),
        "controller": (0, 127),
        "control_value": (0, 127),
        "program": (0, 127),
        "bank": (0, 16383),
    }

    def _sub(self, name):
        return getattr(validate, name)

    def test_bounds_and_rejections(self):
        for name, (low, high) in self.INT_FUNCTIONS.items():
            func = validate.__dict__[name]
            with self.subTest(name=name, case="batas bawah sah"):
                self.assertEqual(func(low), low)
            with self.subTest(name=name, case="batas atas sah"):
                self.assertEqual(func(high), high)
            with self.assertRaises(ValueError, msg=f"{name}({low - 1})"):
                func(low - 1)
            with self.assertRaises(ValueError, msg=f"{name}({high + 1})"):
                func(high + 1)
            with self.assertRaises(TypeError, msg=f"{name}(True)"):
                func(True)
            with self.assertRaises(TypeError, msg=f'{name}("5")'):
                func("5")
            with self.assertRaises(TypeError, msg=f"{name}(None)"):
                func(None)
            with self.assertRaises(TypeError, msg=f"{name}(3.0)"):
                func(3.0)

    def test_sched_time(self):
        self.assertEqual(validate.sched_time(0), 0)
        self.assertEqual(validate.sched_time(2**31 - 1), 2**31 - 1)
        with self.assertRaises(ValueError):
            validate.sched_time(-1)
        with self.assertRaises(ValueError):
            validate.sched_time(2**31)
        with self.assertRaises(TypeError):
            validate.sched_time(True)


class TestFloatValidation(unittest.TestCase):
    def test_gain(self):
        self.assertEqual(validate.gain(0.0), 0.0)
        self.assertEqual(validate.gain(10.0), 10.0)
        self.assertEqual(validate.gain(0), 0.0)
        self.assertEqual(validate.gain(2), 2.0)
        with self.assertRaises(ValueError):
            validate.gain(-0.1)
        with self.assertRaises(ValueError):
            validate.gain(10.1)
        with self.assertRaises(TypeError):
            validate.gain(True)
        with self.assertRaises(TypeError):
            validate.gain("5")
        with self.assertRaises(TypeError):
            validate.gain(None)

    def test_unit(self):
        self.assertEqual(validate.unit(0.0), 0.0)
        self.assertEqual(validate.unit(1.0), 1.0)
        with self.assertRaises(ValueError):
            validate.unit(-0.001)
        with self.assertRaises(ValueError):
            validate.unit(1.1)
        with self.assertRaises(TypeError):
            validate.unit(True)
        with self.assertRaises(TypeError):
            validate.unit("5")
        with self.assertRaises(TypeError):
            validate.unit(None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
