"""Scan de segredos pula binários; apps executáveis não versionam.

Cenário real (11/out): Qt5Network.dll do app Face SDF Generator gerou
falso positivo de credencial e bloqueou o sync inteiro.
Rode: python3 tests/test_devkit_binarios.py
"""
import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pc", REPO / "tools" / "project_cli.py")
pc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pc)


class TestBinarios(unittest.TestCase):
    def test_extensoes_binarias_cobertas(self):
        for ext in (".dll", ".exe", ".pyd", ".so", ".dylib", ".pak"):
            self.assertIn(ext, pc.BINARY_EXTS)

    def test_dll_nao_passa_pelo_scan_de_texto(self):
        # simples: a lógica de skip é por extensão — basta conferir que .dll
        # não está nos TEXTOS
        self.assertNotIn(".dll", pc.TEXT_EXTS)

    def test_gitignore_tem_o_app_sdf(self):
        gi = (REPO / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("Face_SDF_Generator_Old/", gi)

    def test_bloom_tem_self_heal(self):
        txt = (REPO / "util" / "bloom.ps1").read_bytes().decode("utf-8-sig")
        self.assertIn("Get-FileHash $PSCommandPath", txt)
        self.assertIn("reiniciando com a versao nova", txt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
