"""Validasi tipe dan rentang di batas pembungkus pyfluidsynth (R2).

pyfluidsynth itu ctypes: argumen yang salah bukan exception, melainkan
segfault yang tidak bisa ditangkap. Maka semua nilai diperiksa di sini,
sebelum menyeberang ke C. bool ditolak sebagai int (isinstance(True, int)
itu True di Python), float ditolak di fungsi yang menuntut int — pembulatan
diam-diam adalah cara bug masuk ke C.
"""

from __future__ import annotations


def _int(name: str, value: int, low: int, high: int) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{name} harus int, dapat bool {value!r}")
    if not isinstance(value, int):
        raise TypeError(f"{name} harus int, dapat {value!r} ({type(value).__name__})")
    if not low <= value <= high:
        raise ValueError(f"{name} harus {low}-{high}, dapat {value}")
    return value


def _float(name: str, value: float, low: float, high: float) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{name} harus angka, dapat bool {value!r}")
    if not isinstance(value, (int, float)):
        raise TypeError(f"{name} harus angka (int/float), dapat {value!r} ({type(value).__name__})")
    result = float(value)
    if not low <= result <= high:
        raise ValueError(f"{name} harus {low}-{high}, dapat {result}")
    return result


def channel(value: int) -> int:
    """Nomor channel MIDI 0-15 (0-based; 9 = drum)."""
    return _int("channel", value, 0, 15)


def key(value: int) -> int:
    """Nomor not 0-127."""
    return _int("key", value, 0, 127)


def velocity(value: int) -> int:
    """Velocity 0-127."""
    return _int("velocity", value, 0, 127)


def controller(value: int) -> int:
    """Nomor controller CC 0-127."""
    return _int("controller", value, 0, 127)


def control_value(value: int) -> int:
    """Nilai controller CC 0-127."""
    return _int("control_value", value, 0, 127)


def program(value: int) -> int:
    """Nomor program GM 0-127."""
    return _int("program", value, 0, 127)


def bank(value: int) -> int:
    """Nomor bank 0-16383; bank 128 khusus drum."""
    return _int("bank", value, 0, 16383)


def sched_time(value: int) -> int:
    """Waktu absolut sequencer dalam ms: int >= 0, < 2**31."""
    return _int("sched_time", value, 0, 2**31 - 1)


def gain(value: float) -> float:
    """Gain FluidSynth 0.0-10.0."""
    return _float("gain", value, 0.0, 10.0)


def unit(value: float) -> float:
    """Nilai ternormalisasi 0.0-1.0, untuk volume dan pan dari model."""
    return _float("unit", value, 0.0, 1.0)
