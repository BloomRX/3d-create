"""Teste do model_probe.py em modo CLI (--out) com bpy fake — offline.

Rode: python3 tests/test_probe_cli.py
"""
import json
import runpy
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

PROBE = Path(__file__).resolve().parents[1] / "tools" / "model_probe.py"


def fake_bpy(tempdir):
    ob = types.SimpleNamespace(name="Corpo", type="EMPTY",
                               hide_render=False, parent=None)
    scene = types.SimpleNamespace(
        render=types.SimpleNamespace(engine="BLENDER_EEVEE_NEXT",
                                     resolution_x=1920, resolution_y=1080,
                                     fps=24),
        animation_data=types.SimpleNamespace(drivers=[1, 2]))
    return types.SimpleNamespace(
        app=types.SimpleNamespace(version_string="5.2.0 STUB", tempdir=tempdir),
        data=types.SimpleNamespace(objects=[ob], materials=[]),
        context=types.SimpleNamespace(scene=scene, space_data=None))


class TestProbeCli(unittest.TestCase):
    def test_flag_out_escreve_no_caminho(self):
        with tempfile.TemporaryDirectory() as tmp:
            saida = Path(tmp) / "sub" / "model_probe.json"
            argv = ["blender", "--background", "x.blend",
                    "--python", "probe.py", "--", "--out", str(saida)]
            with mock.patch.dict(sys.modules, {"bpy": fake_bpy(tmp)}):
                with mock.patch.object(sys, "argv", argv):
                    runpy.run_path(str(PROBE), run_name="__main__")
            d = json.loads(saida.read_text(encoding="utf-8"))
            self.assertEqual(d["objetos"][0]["nome"], "Corpo")
            self.assertEqual(d["drivers"], 2)
            self.assertIn("blender", d)

    def test_sem_out_vai_pro_tempdir(self):
        with tempfile.TemporaryDirectory() as tmp:
            argv = ["blender", "--background", "x.blend",
                    "--python", "probe.py"]
            with mock.patch.dict(sys.modules, {"bpy": fake_bpy(tmp)}):
                with mock.patch.object(sys, "argv", argv):
                    runpy.run_path(str(PROBE), run_name="__main__")
            self.assertTrue((Path(tmp) / "model_probe.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
