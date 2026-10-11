"""Guardas v0.3.3 — lições do FIELD RUN #2 (turno queimado em câmera).

Bugs de campo que não podem voltar:
- rig_human: bound_box devolve Vectors (sem .co) em coords locais.
- agent modelou CORPO com primitivas em vez de spawn_base_body.
- ciclo render -> ajustar câmera -> render queimou as 25 tools do turno.
- LLM escreveu bpy.scene (não existe) e perdeu uma volta de API.
"""
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "agent" / "bloom_agent"


class TestV033(unittest.TestCase):
    def test_prompt_proibe_corpo_de_primitiva(self):
        core = (PKG / "agent_core.py").read_text(encoding="utf-8")
        self.assertIn("NUNCA monte o corpo com", core)
        self.assertIn('"name": "spawn_base_body"', (PKG / "tools_registry.py").read_text(encoding="utf-8"))

    def test_setup_camera_front_registrada(self):
        reg = (PKG / "tools_registry.py").read_text(encoding="utf-8")
        self.assertIn('"name": "setup_camera_front"', reg)
        self.assertIn('"fn": "setup_camera_front"', reg)
        core = (PKG / "agent_core.py").read_text(encoding="utf-8")
        self.assertIn("setup_camera_front UMA vez", core)

    def test_freio_de_render_por_turno(self):
        h = (PKG / "tools" / "handlers.py").read_text(encoding="utf-8")
        self.assertIn("MAX_RENDERS_PER_TURN", h)
        self.assertIn('sess["renders_turn"] = feitos + 1', h)
        core = (PKG / "agent_core.py").read_text(encoding="utf-8")
        self.assertIn("session.renders_turn = 0", core)

    def test_rig_human_bound_box_com_vector(self):
        h = (PKG / "tools" / "handlers.py").read_text(encoding="utf-8")
        self.assertIn("Vector(c)", h)
        self.assertNotIn("for v in o.bound_box", h)

    def test_helpers_do_run_blender_python(self):
        h = (PKG / "tools" / "handlers.py").read_text(encoding="utf-8")
        self.assertIn('"scene": bl.bpy.context.scene', h)
        self.assertIn("NAO existe", h)  # dica no erro


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestV034(unittest.TestCase):
    """Lianções do FIELD RUN #3: kit de 147 objetos, rig 0 malhas, corpo recriado."""

    def test_spawn_limpa_kit(self):
        h = (PKG / "tools" / "handlers.py").read_text(encoding="utf-8")
        for marca in ("_LIXO_PREFIXOS", '"CS_UI_", "WGT-"', '"LIGHT", "CAMERA", "FONT", "EMPTY"',
                      "len(ob.data.polygons) < 50"):
            self.assertIn(marca, h, f"filtro de kit faltando: {marca}")

    def test_geo_e_prefixo_do_projeto(self):
        h = (PKG / "tools" / "handlers.py").read_text(encoding="utf-8")
        self.assertEqual(h.count('"Geo_"'), 3, "Geo_ precisa estar em altura, rig E filtro do spawn")

    def test_rig_fallback_e_honesto(self):
        h = (PKG / "tools" / "handlers.py").read_text(encoding="utf-8")
        self.assertIn("max(malhas, key=lambda m: len(m.data.polygons))", h)
        self.assertIn("NÃO chame \"\n                     \"set_export_profile", h)

    def test_export_recusa_rig_sem_malha(self):
        h = (PKG / "tools" / "handlers.py").read_text(encoding="utf-8")
        self.assertIn("não tem NENHUMA malha parentada", h)
        self.assertIn('src.children', h)

    def test_waist_tem_mapeamento(self):
        h = (PKG / "tools" / "handlers.py").read_text(encoding="utf-8")
        self.assertIn('"waist": {"Fat": True, "Thin": False}', h)

    def test_prompt_integridade_da_cena(self):
        core = (PKG / "agent_core.py").read_text(encoding="utf-8")
        for marca in ("corpo é INTOCÁVEL", '"malhas rigadas: 0" ou qualquer ✗',
                      "Nunca anuncie"):
            self.assertIn(marca, core, f"prompt integridade faltando: {marca}")
