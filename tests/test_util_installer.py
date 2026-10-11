"""Guardas da rotina única (BLOOM.bat) e da organização — offline.

Rode: python3 tests/test_util_installer.py
"""
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class TestBloom(unittest.TestCase):
    def test_bat_unico_na_raiz(self):
        raw = (REPO / "BLOOM.bat").read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), "BOM envenena o @echo off")
        raw.decode("ascii")
        self.assertTrue(raw.startswith(b"@echo off"))
        self.assertIn(b"bloom.ps1", raw)
        self.assertIn(b"pause", raw)

    def test_bloom_ps1_tem_todos_os_passos(self):
        raw = (REPO / "util" / "bloom.ps1").read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        txt = raw.decode("utf-8-sig")
        for marca in ("project_cli.py", "pull", "instalar_plugins.py",
                      "SteamLibrary", "model_probe.py", "probe_vrm.py",
                      ".vrm", "probes", "libraryfolders.vdf",
                      "tools" + chr(92) + "ci" + chr(92) + "tests.yml",
                      ".github", "sync", "Start-Process"):
            self.assertIn(marca, txt, f"bloom.ps1 perdeu: {marca}")

    def test_scripts_antigos_foram_removidos(self):
        for velho in ("util/probe_modelo.bat", "util/probe_modelo.ps1",
                      "util/instalar_plugins.bat", "util/instalar_plugins.ps1",
                      "util/ativar_ci.bat"):
            self.assertFalse((REPO / velho).exists(), f"script antigo sobrou: {velho}")

    def test_organizacao(self):
        self.assertTrue((REPO / "plugins" / "README.md").exists())
        self.assertFalse((REPO / "addons").exists(), "addons/ (notas antigas) devia ter saido")
        self.assertFalse((REPO / "plugins_src" / "README.md").exists())

    def test_python_do_motor(self):
        txt = (REPO / "util" / "instalar_plugins.py").read_text(encoding="utf-8")
        for marca in ("plugins", "extension_install_file", "addon_install",
                      "save_userpref"):
            self.assertIn(marca, txt)
        vrm = (REPO / "util" / "probe_vrm.py").read_text(encoding="utf-8")
        for marca in ("import_scene.vrm", "model_probe.py", "plugins_src"):
            self.assertIn(marca, vrm)


if __name__ == "__main__":
    unittest.main(verbosity=2)
