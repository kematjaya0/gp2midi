"""Pengambilan score.gpif dari berbagai pembungkus Guitar Pro."""

from __future__ import annotations

import zipfile
from pathlib import Path


class UnsupportedContainer(Exception):
    pass


GPIF_MEMBER_CANDIDATES = ("Content/score.gpif", "score.gpif")


def read_gpif(path: str | Path) -> bytes:
    """Kembalikan isi XML score.gpif dari file .gp, .gpif, atau folder hasil unzip."""
    path = Path(path)

    if path.is_dir():
        for candidate in GPIF_MEMBER_CANDIDATES:
            member = path / candidate
            if member.is_file():
                return member.read_bytes()
        raise UnsupportedContainer(f"tidak ada score.gpif di dalam {path}")

    with path.open("rb") as handle:
        head = handle.read(4)

    if head[:2] == b"PK":
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            for candidate in GPIF_MEMBER_CANDIDATES:
                if candidate in names:
                    return zf.read(candidate)
            for name in names:
                if name.endswith("score.gpif"):
                    return zf.read(name)
        raise UnsupportedContainer(
            f"{path.name}: arsip tanpa score.gpif (kemungkinan .gpx lama atau bukan file Guitar Pro)"
        )

    if head[:4] == b"BCFZ" or head[:4] == b"BCFS":
        raise UnsupportedContainer(
            f"{path.name}: container .gpx (Guitar Pro 6) belum didukung"
        )

    if head.lstrip()[:1] == b"<":
        return path.read_bytes()

    raise UnsupportedContainer(
        f"{path.name}: format tidak dikenal (hanya .gp / .gpif yang didukung; .gp3/.gp4/.gp5 biner belum)"
    )
