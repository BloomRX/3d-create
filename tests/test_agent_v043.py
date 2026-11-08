"""v0.4.3 — ponte com o LIA FORGE (3DSpritesheet).

Contrato lido do repositório deles (scripts/blender_spritesheet.py):
- consome .blend/.glb/.fbx; ações casadas por nome exato ou TOKENS;
- 8 frames por animação pedida em asset.animations (task schema v2).
Nosso lado: ações nomeadas Bloom_<nome> que sobrevivem ao save (fake_user),
export .blend, destino no workspace, peça avulsa e manifest .lia.json.
"""
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "agent" / "bloom_agent"


class TestV043LiaForge(unittest.TestCase):
    def setUp(self):
        self.h = (PKG / "tools" / "handlers.py").read_text(encoding="utf-8")
        self.reg = (PKG / "tools_registry.py").read_text(encoding="utf-8")

    def test_acao_tem_nome_e_sobrevive(self):
        self.assertIn('act.name = f"Bloom_{nome_acao}"', self.h)
        self.assertIn("use_fake_user = True", self.h)
        self.assertIn("Lia Forge casa ações por TOKEN", self.h)

    def test_export_blend_destino_e_peca(self):
        for marca in ('fmt not in ("vrm", "glb", "fbx", "blend")',
                      "save_as_mainfile(filepath=str(destino), copy=True)",
                      "Path(args.get(\"destino\"))", "bloom_piece\") == peca_f",
                      "bloom-lia-1", ".lia.json"):
            self.assertIn(marca, self.h, f"ponte Lia faltando: {marca}")

    def test_manifest_lista_acoes(self):
        self.assertIn('"animacoes": acoes', self.h)
        self.assertIn("casa por token, ex.: idle", self.h)

    def test_registry_atualizado(self):
        self.assertIn('"enum": ["vrm", "glb", "fbx", "blend"]', self.reg)
        self.assertIn('"nome": {"type": "string"', self.reg)

    def test_prompt_fala_do_lia(self):
        core = (PKG / "agent_core.py").read_text(encoding="utf-8")
        self.assertIn("Para o LIA FORGE (spritesheet 2D)", core)
        self.assertIn("casa por token", core)


if __name__ == "__main__":
    unittest.main(verbosity=2)
