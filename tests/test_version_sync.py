"""A versao do addon tem que ser UMA so — em todos os lugares.

Bug historico: usuario com 0.2.5 instalado enquanto o repo ja ia em 0.3.x.
Rode: python3 tests/test_version_sync.py
"""
import re
import sys
import tomllib
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "agent" / "bloom_agent"
sys.path.insert(0, str(PKG.parent))


class TestVersaoUnica(unittest.TestCase):
    def test_init_bl_info_e_constante(self):
        import bloom_agent
        self.assertEqual(bloom_agent.__version__, "0.4.4")
        self.assertEqual(tuple(bloom_agent.bl_info["version"]),
                         tuple(int(x) for x in bloom_agent.__version__.split(".")))

    def test_manifest_bate_com_init(self):
        m = tomllib.loads((PKG / "blender_manifest.toml").read_text(encoding="utf-8"))
        import bloom_agent
        self.assertEqual(m["version"], bloom_agent.__version__)

    def test_bloom_ps1_compara_instalado_vs_repo(self):
        txt = (Path(__file__).resolve().parents[1] / "util" / "bloom.ps1"
               ).read_bytes().decode("utf-8-sig")
        for marca in ("Versao-Manifesto", "user_default", "CONFIRMADO",
                      "Remove-Item $InstDir", "version\\s*="):
            self.assertIn(marca, txt, f"bloom.ps1 perdeu: {marca}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
