"""v0.4.0 — FERRAMENTA COMPLETA (M1–M5 fechados, usuário testa no fim).

O que não pode mais faltar:
- export_character: .vrm REAL (enable da extensão) + glb/fbx, escala assada.
- make_piece: peças separadas com bloom_piece (requisito 3 do projeto).
- uv_and_bake: Smart UV + bake DIFFUSE CPU preservando outline (requisito 5).
- make_idle_animation: idle loop 96f @30fps (o "animate" do objetivo).
- prompt: PIPELINE COMPLETO em 8 voltas.
"""
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "agent" / "bloom_agent"


class TestV040Export(unittest.TestCase):
    def setUp(self):
        self.h = (PKG / "tools" / "handlers.py").read_text(encoding="utf-8")
        self.reg = (PKG / "tools_registry.py").read_text(encoding="utf-8")

    def test_export_real_existe(self):
        for marca in ("def export_character", "export_scene.vrm",
                      "bl_ext.user_default.io_scene_vrm", 'export_format="GLB"',
                      "export_scene.fbx", "transform_apply", "use_selection=True",
                      '/ "jobs" / "exports"'):
            self.assertIn(marca, self.h, f"export incompleto: {marca}")

    def test_fallback_vrm_para_glb(self):
        self.assertIn("extensão VRM não disponível", self.h)
        self.assertIn('with_suffix(".glb")', self.h)

    def test_pecas_separadas(self):
        for marca in ("def make_piece", 'mesh.separate(type="LOOSE")',
                      "bloom_piece", "ARMATURE_AUTO"):
            self.assertIn(marca, self.h, f"make_piece incompleto: {marca}")
        self.assertIn('"enum": ["cabelo", "top",', self.reg)

    def test_uv_e_bake(self):
        for marca in ("def uv_and_bake", "uv.smart_project", 'type="DIFFUSE"',
                      'pass_filter={"COLOR"}', '"CYCLES"', '"CPU"',
                      "material_offset_rim = 1", "Bloom_outline"):
            self.assertIn(marca, self.h, f"uv_and_bake incompleto: {marca}")

    def test_idle_animation(self):
        for marca in ("def make_idle_animation", "frame_end = 96", "render.fps = 30",
                      "keyframe_insert", "rotation_mode", "upper_arm.L"):
            self.assertIn(marca, self.h, f"idle incompleto: {marca}")

    def test_registry_tem_as_quatro(self):
        for nome in ("export_character", "make_piece", "uv_and_bake",
                     "make_idle_animation"):
            self.assertIn(f'"name": "{nome}"', self.reg)
            self.assertIn(f'"fn": "{nome}"', self.reg)


class TestV040Prompt(unittest.TestCase):
    def test_pipeline_completo_no_prompt(self):
        core = (PKG / "agent_core.py").read_text(encoding="utf-8")
        for marca in ("PIPELINE COMPLETO", "export_character (vrm | glb | fbx | blend)",
                      "make_piece para cabelo/roupas", "uv_and_bake (M4)"):
            self.assertIn(marca, core, f"prompt do pipeline faltando: {marca}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
