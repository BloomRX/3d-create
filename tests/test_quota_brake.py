"""Freio global anti-ping-pong de cota (regressao do bug do teste de campo).

Cenario real de 11/out: todas as chaves em cota -> centenas de linhas
"🔄 cota do modelo esgotou" em segundos. Agora: teto global de 6 trocas
por 10 min, compartilhado ENTRE instâncias (mesmo que o Gemini seja
recriado no meio do fluxo).

Rode: python3 tests/test_quota_brake.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from bloom_agent.llm import Gemini, LLMError  # noqa: E402


MODELOS = {"models": [{"name": "models/gemini-3.8-flash"},
                      {"name": "models/gemini-flash-latest"}]}


class TestFreioCota(unittest.TestCase):
    def setUp(self):
        Gemini._QUOTA_SWAP_TS.clear()
        self.trocas = []
        Path("/tmp/gq_brake_test.json").unlink(missing_ok=True)
        import bloom_agent.keys as keysmod
        # cota "longa" no teste: pula o caminho de espera (⏳ até 150s)
        self._orig_wait = keysmod.earliest_recovery
        keysmod.earliest_recovery = lambda data, model: 999.0

        def fake_post(url, body, timeout, headers=None):
            if "generateContent" not in url:
                return 200, MODELOS
            return 429, {"error": {"status": "RESOURCE_EXHAUSTED",
                                   "message": "quota exceeded"}}

        import bloom_agent.llm as L
        L._http_post = fake_post

    def _agente_fresco(self):
        g = Gemini(Path("/tmp/gq_brake_test.json"))
        g.data["gemini"] = ["AIza" + "A" * 30, "AIza" + "B" * 30]
        g.on_log = lambda s: self.trocas.append(s)
        return g

    def test_enxurrada_e_contida(self):
        # instancia 1: levanta erro (nao fica em loop)
        with self.assertRaises(LLMError):
            self._agente_fresco().chat(parts=[{"text": "oi"}])
        # instancia NOVA (simula recriacao no meio do fluxo): o freio
        # de classe tem que continuar valendo
        with self.assertRaises(LLMError):
            self._agente_fresco().chat(parts=[{"text": "oi"}])
        total = sum(1 for m in self.trocas if "cota do modelo" in m)
        self.assertLessEqual(total, Gemini._QUOTA_SWAP_MAX,
                             f"enchente de trocas: {total}")

    def test_mensagem_final_orienta(self):
        try:
            self._agente_fresco().chat(parts=[{"text": "oi"}])
        except LLMError as e:
            self.assertIn("Cota esgotada", str(e))

    def tearDown(self):
        import bloom_agent.keys as keysmod
        keysmod.earliest_recovery = self._orig_wait
        Path("/tmp/gq_brake_test.json").unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
