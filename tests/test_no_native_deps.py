"""Penjaga Keputusan 1: `gp2midi/*.py` stdlib murni; native hanya di `gp2midi/play/`."""

import ast
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixture import simple_score, write_gp  # noqa: E402

FORBIDDEN_ABSOLUTE_ROOTS = ("fluidsynth", "numpy")

# Satu-satunya titik sambung yang diizinkan: `gp2midi/cli.py` boleh mengimpor
# `.play.cli` di DALAM fungsi `_cmd_play` — import lazy itu mekanismenya, bukan
# pelanggaran (Keputusan 3): info/convert/check tetap jalan tanpa FluidSynth.
LAZY_PLAY_IMPORTS = {("cli.py", "play.cli")}


def _imports_of(path: Path) -> list[tuple[int, str]]:
    """Semua (level, module) yang diberi import, termasuk yang bersarang di dalam fungsi."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                result.append((0, alias.name))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            # import tanpa module (contoh: `from . import play`) diwakili level-nya
            result.append((node.level, module))
    return result


class TestNoNativeDeps(unittest.TestCase):
    def test_core_modules_import_only_stdlib(self):
        violations = []
        for path in sorted((ROOT / "gp2midi").glob("*.py")):
            for level, module in _imports_of(path):
                if level == 0:
                    root = module.split(".")[0]
                    if root in FORBIDDEN_ABSOLUTE_ROOTS:
                        violations.append(f"{path.name}: import {module}")
                    elif root == "gp2midi" and module.split(".")[1] == "play":
                        violations.append(f"{path.name}: import {module}")
                else:
                    # import relatif di dalam paket gp2midi: batasnya direktori itu sendiri
                    if module.split(".")[0] == "play":
                        if path.name == "cli.py" and module == "play.cli" and (path.name, module) in LAZY_PLAY_IMPORTS:
                            continue
                        violations.append(f"{path.name}: import {module}")
        self.assertEqual(violations, [])

    def test_engine_usable_without_fluidsynth(self):
        blocker = Path(tempfile.mkdtemp()) / "blocker"
        blocker.mkdir()
        (blocker / "fluidsynth.py").write_text("raise ImportError('diblokir test')\n")
        (blocker / "numpy.py").write_text("raise ImportError('diblokir test')\n")

        score_path = Path(tempfile.mkdtemp()) / "fixture.gp"
        write_gp(score_path, simple_score())
        out_path = Path(tempfile.mkdtemp()) / "out.mid"

        env = dict(os.environ)
        env["PYTHONPATH"] = str(blocker) + (
            ":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
        )
        result = subprocess.run(
            [sys.executable, "-m", "gp2midi", "convert", str(score_path), "-o", str(out_path)],
            capture_output=True, text=True, cwd=str(ROOT), env=env, timeout=60,
        )
        self.assertEqual(result.returncode, 0, f"stderr:\n{result.stderr}")
        self.assertTrue(out_path.exists() and out_path.stat().st_size > 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
