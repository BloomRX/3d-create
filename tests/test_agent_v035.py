"""v0.3.5 — orquestrador multi-free + UI viva.

Roteamento por payload tem que valer em COMPORTAMENTO (fakes), não só em texto:
- imagem -> Gemini; Gemini caiu -> Groq VISÃO (llama-4-scout), nunca turno morto.
- texto -> Groq primeiro; Groq caiu -> Gemini.
UI viva: fase/timer/contadores no painel (marcadores — ui.py precisa de bpy).
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "agent"))

from bloom_agent.llm import GroqClient, LLMError, Router  # noqa: E402

PKG = REPO / "agent" / "bloom_agent"


class _Fake:
    def __init__(self, resultado=None, erro=None):
        self.resultado = resultado or {}
        self.erro = erro
        self.chamadas = []

    def chat(self, parts=None, system="", tools=None, contents=None):
        self.chamadas.append({"parts": parts, "contents": contents})
        if self.erro:
            raise LLMError(self.erro)
        return dict(self.resultado)


def _conteudo_com_imagem():
    return [{"role": "user", "parts": [{"inline_data": {"mime_type": "image/png",
                                                        "data": "QUJD"}}]}]


class TestRouter(unittest.TestCase):
    def test_texto_vai_para_o_groq_primeiro(self):
        gem, groq = _Fake({"text": "g"}), _Fake({"text": "q"})
        r = Router(gem, groq)
        resp = r.chat(parts=[{"text": "oi"}])
        self.assertEqual(resp["provider"], "groq")
        self.assertEqual(len(groq.chamadas), 1)
        self.assertEqual(len(gem.chamadas), 0)

    def test_texto_groq_caiu_gemini_entra(self):
        gem, groq = _Fake({"text": "g"}), _Fake(erro="sem chave")
        resp = Router(gem, groq).chat(parts=[{"text": "oi"}])
        self.assertEqual(resp["provider"], "gemini")

    def test_imagem_vai_para_o_gemini(self):
        gem, groq = _Fake({"text": "g"}), _Fake({"text": "q"})
        resp = Router(gem, groq).chat(contents=_conteudo_com_imagem())
        self.assertEqual(resp["provider"], "gemini")
        self.assertEqual(len(groq.chamadas), 0)

    def test_imagem_gemini_caiu_groq_visao_entra(self):
        """O coração do 'não sobrecarrega': cota do Gemini morta não mata o turno."""
        gem, groq = _Fake(erro="quota"), _Fake({"text": "q"})
        router = Router(gem, groq)
        router.on_log = lambda *_: None
        resp = router.chat(contents=_conteudo_com_imagem())
        self.assertEqual(resp["provider"], "groq")
        self.assertEqual(len(groq.chamadas), 1)

    def test_sem_groq_erro_do_gemini_propaga(self):
        gem = _Fake(erro="quota")
        with self.assertRaises(LLMError):
            Router(gem, None).chat(parts=[{"text": "oi"}])


class TestGroqVisao(unittest.TestCase):
    def test_imagem_vira_image_url_e_troca_o_modelo(self):
        cli = GroqClient(Path(tempfile.gettempdir()) / "nao_existe_keys.json")
        cli.data["groq"] = ["gsk_" + "x" * 40]
        body = cli._convert("sys", _conteudo_com_imagem(), [])
        self.assertEqual(body["model"], GroqClient.VISION_MODEL)
        msg = body["messages"][1]
        tipos = [p["type"] for p in msg["content"]]
        self.assertIn("image_url", tipos)
        url = next(p["image_url"]["url"] for p in msg["content"]
                   if p["type"] == "image_url")
        self.assertTrue(url.startswith("data:image/png;base64,QUJD"))

    def test_texto_puro_mantem_modelo_de_texto(self):
        cli = GroqClient(Path(tempfile.gettempdir()) / "nao_existe_keys.json")
        body = cli._convert("sys", [{"role": "user", "parts": [{"text": "oi"}]}], [])
        self.assertEqual(body["model"], GroqClient.MODEL_PADRAO)

    def test_tools_gemini_viram_formato_openai(self):
        cli = GroqClient(Path(tempfile.gettempdir()) / "nao_existe_keys.json")
        body = cli._convert("sys", [{"role": "user", "parts": [{"text": "oi"}]}],
                            [{"name": "rig_human", "description": "d",
                              "parameters": {"type": "object", "properties": {}}}])
        self.assertEqual(body["tools"][0]["type"], "function")
        self.assertEqual(body["tools"][0]["function"]["name"], "rig_human")


class TestUIVivaMarcadores(unittest.TestCase):
    """ui.py precisa de bpy (não importa no sandbox) — marcadores de texto."""

    def test_log_com_segundos(self):
        ui = (PKG / "ui.py").read_text(encoding="utf-8")
        self.assertIn("'%H:%M:%S'", ui)
        core = (PKG / "agent_core.py").read_text(encoding="utf-8")
        self.assertIn('"%H:%M:%S"', core)

    def test_estado_ao_vivo(self):
        ui = (PKG / "ui.py").read_text(encoding="utf-8")
        for marca in ("_fase_evento", "tag_redraw", "tool_count += 1",
                      "render_count += 1", "🔧", "🧠", "▮", "⚠ lento",
                      'fase = "pronto"'):
            self.assertIn(marca, ui, f"UI viva perdeu: {marca}")

    def test_campo_de_chaves_explica_groq(self):
        ui = (PKG / "ui.py").read_text(encoding="utf-8")
        self.assertIn("gsk_", ui)
        self.assertIn("console.groq.com", ui)


if __name__ == "__main__":
    unittest.main(verbosity=2)
