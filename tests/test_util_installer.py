"""Guardas do instalador de plugins e do suporte a .vrm — offline.

Rode: python3 tests/test_util_installer.py
"""
import unittest
from pathlib import Path

UTIL = Path(__file__).resolve().parents[1] / "util"


class TestInstalador(unittest.TestCase):
    def test_bat_lancador_minimo(self):
        raw = (UTIL / "instalar_plugins.bat").read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        raw.decode("ascii")
        self.assertTrue(raw.startswith(b"@echo off"))
        self.assertIn(b"instalar_plugins.ps1", raw)
        self.assertIn(b"pause", raw)

    def test_ps1_aponta_blender_e_plugins(self):
        raw = (UTIL / "instalar_plugins.ps1").read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        txt = raw.decode("utf-8-sig")
        for marca in ("SteamLibrary", "libraryfolders.vdf", "plugins_src",
                      "assets", "instalar_plugins.py", "--background"):
            self.assertIn(marca, txt, f"ps1 perdeu: {marca}")

    def test_py_instala_desligado_e_pula_rar(self):
        txt = (UTIL / "instalar_plugins.py").read_text(encoding="utf-8")
        for marca in ("extension_install_file", "addon_install",
                      "save_userpref", "plugins_src", "assets", "glob"):
            self.assertIn(marca, txt, f"py perdeu: {marca}")
        self.assertNotIn('enable=True', txt)  # nunca ligar por padrao

    def test_probe_vrm_roteia(self):
        txt = (UTIL / "probe_vrm.py").read_text(encoding="utf-8")
        for marca in ("import_scene.vrm", "addon_utils", "model_probe.py",
                      "--out", "plugins_src"):
            self.assertIn(marca, txt, f"probe_vrm perdeu: {marca}")

    def test_probe_modelo_suporta_vrm(self):
        raw = (UTIL / "probe_modelo.ps1").read_bytes()
        txt = raw.decode("utf-8-sig")
        self.assertIn("*.vrm", txt)
        self.assertIn("probe_vrm.py", txt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
