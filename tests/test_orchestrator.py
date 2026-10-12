"""Testes do orquestrador multi-modelo (Groq texto + Gemini visão) — offline.

Rode: python3 tests/test_orchestrator.py
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import bloom_agent.llm as L                                   # noqa: E402
from bloom_agent.llm import Gemini, GroqClient, LLMError, Router  # noqa: E402
from bloom_agent import keys as K                             # noqa: E402


class Fake:
    def __init__(self, nome, falha=False):
        self.nome = nome
        self.falha = falha
        self.on_log = None
        self.calls = []

    def chat(self, parts=None, system="", tools=None, contents=None):
        if self.falha:
            raise LLMError("boom")
        self.calls.append(contents)
        return {"text": self.nome, "provider": self.nome}


class TestConversao(unittest.TestCase):
    def setUp(self):
        p = Path("/tmp/gq_test.json")
        if p.exists():
            p.unlink()
        self.g = GroqClient(p)
        self.g.data["groq"] = ["gsk_TESTE_AAAAAAAAAAAAAAAAAA"]

    def test_historico_para_openai(self):
        contents = [
            {"role": "user", "parts": [{"text": "oi"}]},
            {"role": "model", "parts": [{"functionCall": {"name": "list_scene",
                                                          "args": {}}}]},
            {"role": "user", "parts": [{"functionResponse": {
                "name": "list_scene", "response": {"ok": True}}}]},
            {"role": "user", "parts": [{"text": "vê",
                                        "inline_data": {"mime_type": "image/png",
                                                        "data": "XX"}}]},
        ]
        body = self.g._convert("sys", contents, [
            {"name": "list_scene", "description": "d",
             "parameters": {"type": "object", "properties": {}}}])
        msgs = body["messages"]
        self.assertEqual(msgs[0]["role"], "system")
        self.assertEqual(msgs[1], {"role": "user", "content": "oi"})
        tc = msgs[2]["tool_calls"][0]
        self.assertEqual(tc["function"]["name"], "list_scene")
        self.assertEqual(msgs[3]["role"], "tool")
        self.assertEqual(msgs[3]["tool_call_id"], tc["id"])
        # v0.3.5: imagem vai DE VERDADE (Groq visão llama-4-scout), não placeholder
        conteudo = msgs[4]["content"]
        self.assertIsInstance(conteudo, list)
        self.assertIn({"type": "text", "text": "vê"}, conteudo)
        self.assertIn("image_url", [p["type"] for p in conteudo])
        self.assertTrue(conteudo[-1]["image_url"]["url"].startswith("data:image/png;base64,XX"))
        self.assertEqual(body["tools"][0]["function"]["name"], "list_scene")

    def test_chat_parse_tool_call(self):
        L._http_post = lambda url, body, timeout, headers=None: (
            200, {"choices": [{"finish_reason": "tool_calls", "message": {
                "content": None,
                "tool_calls": [{"id": "x", "type": "function",
                                "function": {"name": "spawn_base_body",
                                             "arguments": "{\"gender\": \"female\"}"}}]}}]})
        r = self.g.chat(parts=[{"text": "crie"}], system="s",
                        tools=[{"name": "spawn_base_body", "description": "d",
                                "parameters": {"type": "object", "properties": {}}}])
        self.assertEqual(r["tool_calls"],
                         [{"name": "spawn_base_body", "args": {"gender": "female"}}])
        self.assertTrue(r["model"].startswith("groq:"))

    def test_chave_invalida_removida(self):
        self.g.data["groq"] = ["gsk_RUIMAAAAAAAAAAAAAAAAAAA",
                               "gsk_BOAAAAAAAAAAAAAAAAAAAA"]
        chamadas = {"n": 0}

        def post(url, body, timeout, headers=None):
            chamadas["n"] += 1
            if chamadas["n"] == 1:
                return 401, {"error": {"message": "invalid api key"}}
            return 200, {"choices": [{"finish_reason": "stop",
                                      "message": {"content": "ok"}}]}

        L._http_post = post
        r = self.g.chat(parts=[{"text": "oi"}])
        self.assertEqual(r["text"], "ok")
        self.assertEqual(len(self.g.data["groq"]), 1)


class TestRouter(unittest.TestCase):
    def test_texto_vai_para_groq(self):
        gem, gq = Fake("gemini"), Fake("groq")
        r = Router(gem, gq)
        r.on_log = lambda s: None
        out = r.chat(contents=[{"role": "user", "parts": [{"text": "só texto"}]}])
        self.assertEqual(out["provider"], "groq")

    def test_imagem_vai_para_gemini(self):
        gem, gq = Fake("gemini"), Fake("groq")
        r = Router(gem, gq)
        r.on_log = lambda s: None
        out = r.chat(contents=[{"role": "user",
                                "parts": [{"inline_data": {"data": "img"}}]}])
        self.assertEqual(out["provider"], "gemini")
        self.assertEqual(gq.calls, [])

    def test_fallback_gemini(self):
        gem, gq = Fake("gemini"), Fake("groq", falha=True)
        r = Router(gem, gq)
        r.on_log = lambda s: None
        out = r.chat(contents=[{"role": "user", "parts": [{"text": "t"}]}])
        self.assertEqual(out["provider"], "gemini")

    def test_sem_groq_tudo_gemini(self):
        gem = Fake("gemini")
        r = Router(gem, None)
        r.on_log = lambda s: None
        out = r.chat(contents=[{"role": "user", "parts": [{"text": "t"}]}])
        self.assertEqual(out["provider"], "gemini")


class TestKeys(unittest.TestCase):
    def test_prefixos_no_mesmo_arquivo(self):
        d = K._blank()
        K.add_key(d, "AIzaSyExemplo1234567890123456789012345")
        K.add_groq_key(d, "gsk_Exemplo1234567890123456789012345")
        self.assertEqual(len(d["gemini"]), 1)
        self.assertEqual(len(d["groq"]), 1)

    def test_groq_invalida_recusada(self):
        d = K._blank()
        with self.assertRaises(ValueError):
            K.add_groq_key(d, "AIzaSyNao_E_Groq123456789012345678")


if __name__ == "__main__":
    unittest.main(verbosity=2)
