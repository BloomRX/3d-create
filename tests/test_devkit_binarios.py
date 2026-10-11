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

    def test_stage_usa_check_ignore_do_git(self):
        txt = (REPO / "tools" / "project_cli.py").read_text(encoding="utf-8")
        self.assertIn("def git_ignorados", txt)
        self.assertIn("check-ignore", txt)
        self.assertIn("rel in ignorados_git", txt)

    def test_bloom_acha_blender_antes_do_passo3(self):
        txt = (REPO / "util" / "bloom.ps1").read_bytes().decode("utf-8-sig")
        passo3 = txt.index("[3/7] Addon Bloom Agent")
        self.assertIn("Achar-Blender", txt[:passo3 + 60],
                      "passo 3 precisa do $Blender resolvido antes de usar")

    def test_regex_de_versao_ancorada(self):
        # 'schema_version = "1.0.0"' NÃO pode ser lido como a versão do addon
        # (bug real: comparou 1.0.0 com 1.0.0 e pulou a atualização do 0.2.5)
        txt = (REPO / "util" / "bloom.ps1").read_bytes().decode("utf-8-sig")
        self.assertIn("'^\\s*version", txt, "regex precisa de ancora ^")

    def test_stage_auto_remove_ignorado(self):
        txt = (REPO / "tools" / "project_cli.py").read_text(encoding="utf-8")
        self.assertIn("desversionado (agora ignorado)", txt)
        self.assertIn('"rm", "-r", "--cached"', txt)
        self.assertIn("fora do stage (git diz ignorado)", txt)

    def test_bloom_compativel_powershell_51(self):
        # o .bat chama powershell.exe (5.1): nada de operadores do PS7
        txt = (REPO / "util" / "bloom.ps1").read_bytes().decode("utf-8-sig")
        self.assertNotIn("??", txt, "operador ?? e do PowerShell 7")
        self.assertNotIn(" ? ", txt.split("Write-Host")[0], "ternario ? : e do PS7")

    def test_bloom_tem_self_heal(self):
        txt = (REPO / "util" / "bloom.ps1").read_bytes().decode("utf-8-sig")
        self.assertIn("Get-FileHash $PSCommandPath", txt)
        self.assertIn("reiniciando com a versao nova", txt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
