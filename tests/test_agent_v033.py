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
