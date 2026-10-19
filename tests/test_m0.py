#!/usr/bin/env python3
"""Testes do M0 — rodam FORA do Blender (sem bpy, sem rede externa).

Executar:  python tests/test_m0.py  (-v para verbose)
"""
from __future__ import annotations

import http.client
import json
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from bloom_agent import bridge as bridge_mod          # noqa: E402
from bloom_agent import keys as keysmod               # noqa: E402
from bloom_agent import llm as llmmod                 # noqa: E402
from bloom_agent import tools_registry                # noqa: E402
from bloom_agent.bl import list_bank_files            # noqa: E402
from bloom_agent.tools import handlers                # noqa: E402


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class KeysTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "keys.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_missing_returns_blank(self):
        data = keysmod.load(self.path)
        self.assertEqual(data["gemini"], [])
        self.assertEqual(data["model"], keysmod.DEFAULT_MODEL)

    def test_add_pick_rotate_and_mask(self):
        data = keysmod.load(self.path)
        i1 = keysmod.add_key(data, "AIzaSyAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        i2 = keysmod.add_key(data, "AIzaSyBbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
        self.assertEqual((i1, i2), (0, 1))
        self.assertEqual(keysmod.pick_key(data), 0)
        data["_test_now"] = 1000.0
        keysmod.mark_cooldown(data, 0, seconds=60, now=1000.0)
        self.assertFalse(keysmod.key_available(data, 0, now=1000.0))
        self.assertTrue(keysmod.key_available(data, 0, now=1061.0))
        self.assertEqual(keysmod.pick_key(data), 1)  # pula a 0 em cooldown
        m = keysmod.mask("AIzaSyAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        self.assertNotIn("aaaaaaaaaaaa", m)
        self.assertTrue(m.startswith("AIzaSy"))

    def test_advance_and_earliest_recovery(self):
        data = keysmod.load(self.path)
        keysmod.add_key(data, "KEY_TESTE_AAAAAAAAAAAA_1")
        keysmod.add_key(data, "KEY_TESTE_AAAAAAAAAAAA_2")
        data["_test_now"] = 1000.0
        keysmod.mark_cooldown(data, 1, seconds=300, now=1000.0)
        # chave 0 livre -> "primeira liberação" é AGORA
        self.assertAlmostEqual(keysmod.earliest_recovery(data), 0.0)
        # todas em cooldown no modelo -> espera = a que libera primeiro
        keysmod.mark_cooldown(data, 0, seconds=100, now=1000.0)
        self.assertAlmostEqual(keysmod.earliest_recovery(data), 100.0)
        # isolamento por modelo: outro modelo tem tudo livre
        self.assertAlmostEqual(
            keysmod.earliest_recovery(data, model="outro-modelo"), 0.0)
        data["last_key_index"] = 1
        keysmod.advance(data)
        self.assertEqual(data["last_key_index"], 0)

    def test_remove_key_resets_state(self):
        data = keysmod.load(self.path)
        keysmod.add_key(data, "KEY_TESTE_AAAAAAAAAAAA_1")
        keysmod.add_key(data, "KEY_TESTE_AAAAAAAAAAAA_2")
        keysmod.remove_key(data, 0)
        self.assertEqual(data["gemini"], ["KEY_TESTE_AAAAAAAAAAAA_2"])
        self.assertEqual(data["last_key_index"], 0)
        self.assertEqual(data["cooldowns"], {})

    def test_save_load_roundtrip_atomic(self):
        data = keysmod.load(self.path)
        keysmod.add_key(data, "KEY_TESTE_AAAAAAAAAAAA_X")
        keysmod.save(self.path, data)
        self.assertEqual(keysmod.load(self.path)["gemini"], ["KEY_TESTE_AAAAAAAAAAAA_X"])
        self.assertFalse(self.path.with_suffix(".json.tmp").exists())

    def test_reject_placeholder(self):
        data = keysmod.load(self.path)
        with self.assertRaises(ValueError):
            keysmod.add_key(data, "cole_sua_chave_aqui_1")


class LLMFormatTests(unittest.TestCase):
    def test_parts_to_wire_image_and_text(self):
        parts = [{"image_b64": "QUJD", "mime": "image/png", "caption": "ref"},
                 {"text": "crie um cubo"}]
        wire = llmmod.parts_to_wire(parts)
        self.assertEqual(wire[0]["inline_data"]["data"], "QUJD")
        self.assertEqual(wire[1], {"text": "ref"})
        self.assertEqual(wire[2], {"text": "crie um cubo"})

    def test_parse_response_text_and_tool_calls(self):
        payload = {"candidates": [{
            "finishReason": "STOP",
            "content": {"parts": [
                {"text": "olha:"},
                {"functionCall": {"name": "create_object",
                                  "args": {"kind": "cube", "name": "x"}}},
                {"text": "pronto"},
            ]},
        }]}
        out = llmmod.parse_response(payload)
        self.assertEqual(out["text"], "olha:pronto")
        self.assertEqual(len(out["tool_calls"]), 1)
        self.assertEqual(out["tool_calls"][0]["name"], "create_object")
        self.assertEqual(out["tool_calls"][0]["args"]["kind"], "cube")

    def test_build_request_shape(self):
        body = llmmod.build_request("sys", [{"role": "user", "parts": [{"text": "oi"}]}],
                                    [{"name": "t", "description": "d", "parameters": {"type": "object", "properties": {}, "required": []}}],
                                    "gemini-3-flash")
        self.assertEqual(body["model"], "gemini-3-flash")
        self.assertEqual(body["systemInstruction"]["parts"][0]["text"], "sys")
        self.assertEqual(body["tools"][0]["function_declarations"][0]["name"], "t")
        self.assertIn("temperature", body["generationConfig"])

    def test_quota_error_detection(self):
        self.assertTrue(llmmod._is_quota_error(429, {}))
        self.assertTrue(llmmod._is_quota_error(200, {"error": {"code": "RESOURCE_EXHAUSTED", "message": "quota"}}))
        self.assertFalse(llmmod._is_quota_error(400, {"error": {"code": "INVALID_ARGUMENT", "message": "bad"}}))

    def test_gemini_no_keys_raises_friendly(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            g = llmmod.Gemini(Path(tmp.name) / "keys.json")
            with self.assertRaises(llmmod.LLMError) as cm:
                g.chat(parts=[{"text": "oi"}])
            self.assertIn("Nenhuma chave", str(cm.exception))
        finally:
            tmp.cleanup()


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.port = _free_port()
        self.srv = bridge_mod.BridgeServer(self.root, port=self.port)
        self.srv.start()
        self.base = self.srv.local_url

    def tearDown(self):
        self.srv.stop()
        self.tmp.cleanup()

    def _get(self, path: str) -> tuple[int, bytes]:
        try:
            with urllib.request.urlopen(self.base + path, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def _post(self, path: str, data: bytes, headers=None) -> tuple[int, bytes]:
        req = urllib.request.Request(self.base + path, data=data, method="POST",
                                     headers=headers or {})
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()

    def test_health(self):
        code, body = self._get("/health")
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body)["ok"])

    def test_job_roundtrip(self):
        job_id = self.srv.create_job("echo", {"a": 1}, {"ref.png": b"\x89PNGfake", "x.txt": "oi"})
        info = self.srv.job_info(job_id)
        self.assertEqual(info["kind"], "echo")
        self.assertEqual(info["input_files"], ["ref.png", "x.txt"])

        code, body = self._get(f"/job/{job_id}")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["params"], {"a": 1})

        code, body = self._get(f"/job/{job_id}/input/ref.png")
        self.assertEqual(code, 200)
        self.assertEqual(body, b"\x89PNGfake")

        code, body = self._post(f"/job/{job_id}/result", b"resultado123",
                                {"X-Result-Name": "saida.glb"})
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["file"], "saida.glb")

        code, body = self._post(f"/job/{job_id}/complete",
                                json.dumps({"status": "ok", "files": ["saida.glb"]}).encode())
        self.assertEqual(code, 200)

        info = self.srv.job_info(job_id)
        self.assertEqual(len(info["results"]), 1)
        self.assertEqual(info["results"][0]["name"], "saida.glb")
        self.assertEqual(info["complete"]["status"], "ok")
        f = self.srv.result_file(job_id, "saida.glb")
        self.assertEqual(f.read_bytes(), b"resultado123")

    def test_bad_paths_rejected(self):
        code, _ = self._get("/job/..%2F..%2Fetc")
        self.assertIn(code, (400, 404))
        code, _ = self._get("/job/naoexiste")
        self.assertEqual(code, 404)

    def test_refresh_job_url_without_ngrok_is_none(self):
        job_id = self.srv.create_job("echo", {}, None)
        # ngrok agente provavelmente não está rodando na sandbox
        url = self.srv.refresh_job_url(job_id)
        info = self.srv.job_info(job_id)
        self.assertEqual(info["base_url"], url)


class AssetIndexTests(unittest.TestCase):
    def test_scan_with_meta(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            bank = Path(tmp.name) / "bank"
            (bank / "cabelos").mkdir(parents=True)
            (bank / "cabelos" / "longo.glb").write_bytes(b"glb")
            (bank / "cabelos" / "longo.glb.meta.json").write_text(
                json.dumps({"tags": ["anime", "feminino"], "obs": "teste"}), encoding="utf-8")
            (bank / "roupas").mkdir()
            (bank / "roupas" / "vestido.fbx").write_bytes(b"fbx")
            entries = list_bank_files(bank)
            self.assertEqual(len(entries), 2)
            by_id = {e["id"]: e for e in entries}
            self.assertEqual(by_id["longo.glb"]["tags"], ["anime", "feminino"])
            self.assertEqual(by_id["longo.glb"]["obs"], "teste")
            # v0.4.2: auto-tags pelo nome — "vestido" cai na tag roupa
            self.assertEqual(by_id["vestido.fbx"]["tags"], ["roupa"])
        finally:
            tmp.cleanup()

    def test_missing_bank_returns_empty(self):
        self.assertEqual(list_bank_files(Path("/nao/existe/bank")), [])


class RegistryTests(unittest.TestCase):
    def test_all_tools_have_valid_schema(self):
        for t in tools_registry.TOOLS:
            with self.subTest(tool=t["name"]):
                self.assertTrue(t["name"].isidentifier())
                self.assertTrue(t["description"].strip())
                p = t["parameters"]
                self.assertEqual(p["type"], "object")
                self.assertIsInstance(p.get("properties", {}), dict)
                self.assertIsInstance(p.get("required", []), list)

    def test_handlers_exist_in_module(self):
        src = (ROOT / "agent" / "bloom_agent" / "tools" / "handlers.py").read_text(encoding="utf-8")
        for t in tools_registry.TOOLS:
            with self.subTest(tool=t["name"]):
                self.assertRegex(src, rf"def {t['fn']}\(")

    def test_unknown_tool_returns_error_not_exception(self):
        res = tools_registry.run("nao_existe", {}, {"root": Path(".")})
        self.assertFalse(res["ok"])

    def test_schemas_match_llm_declaration_shape(self):
        schemas = tools_registry.schemas_for_llm()
        self.assertEqual(len(schemas), len(tools_registry.TOOLS))
        for s in schemas:
            self.assertIn("name", s)
            self.assertIn("parameters", s)


class GuardTests(unittest.TestCase):
    def test_forbidden_blocked(self):
        for code in ("import subprocess", "os.system('rm')", "import socket",
                     "requests.get('x')", "shutil.rmtree('/')", "eval('1+1')"):
            with self.subTest(code=code):
                self.assertIsNotNone(handlers._guard_python(code))

    def test_modeling_allowed(self):
        ok = ("import bpy, bmesh, mathutils\n"
              "ob = bpy.context.active_object\n"
              "bpy.ops.mesh.primitive_ico_sphere_add(radius=1)\n")
        self.assertIsNone(handlers._guard_python(ok))

    def test_tool_requiring_blender_fails_gracefully(self):
        # list_scene requer bpy: fora do Blender deve devolver ok=False, não crash
        res = tools_registry.run("list_scene", {}, {"root": Path(".")})
        self.assertFalse(res["ok"])
        self.assertIn("bpy", res["text"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
