"""Runner único das suítes locais — a porta de entrada da automação.

Usado por: tools/project_cli.py (gancho do sync), .vscode/tasks.json,
.github/workflows/tests.yml e por você mesmo: python tests\\run_all.py

Rode: python tests/run_all.py   (exit 0 = tudo verde)
"""
import sys
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent


def main() -> int:
    suite = unittest.TestLoader().discover(str(TESTS), pattern="test_*.py")
    total = suite.countTestCases()
    if total == 0:
        print("ERRO: nenhum teste descoberto em tests/test_*.py")
        return 2
    print(f"=== BLOOM: rodando {total} testes ===")
    resultado = unittest.TextTestRunner(verbosity=1).run(suite)
    rodou = total - len(resultado.skipped)
    print("=== RESUMO: {} testes | {} falhas | {} erros{} ===".format(
        rodou, len(resultado.failures), len(resultado.errors),
        f" | {len(resultado.skipped)} pulados" if resultado.skipped else ""))
    if resultado.wasSuccessful():
        print("VERDE: tudo certo.")
        return 0
    print("VERMELHO: existe teste falhando — avise o agent na conversa.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
