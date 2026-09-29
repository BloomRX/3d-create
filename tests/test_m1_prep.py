"""Testes M1-prep: rig_profiles + tools registradas (sem bpy, sem rede).

Rode: python3 tests/test_m1_prep.py
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from bloom_agent import rig_profiles as rp          # noqa: E402
from bloom_agent import tools_registry as tr        # noqa: E402


class TestRigProfiles(unittest.TestCase):
    def test_perfis_conhecidos(self):
        self.assertEqual(rp.profiles_available(),
                         ["metahuman", "vrm2", "mixamo", "custom"])

    def test_canonica_cobre_core(self):
        for b in ("hips", "spine", "chest", "neck", "head", "hand.L", "foot.R"):
            self.assertIn(b, rp.CANONICAL_BONES)

    def test_nomes_unicos_por_perfil(self):
        for perfil in rp.PROFILES:
            bones = rp.bones_for(perfil)
            self.assertEqual(len(bones), len(set(bones)), perfil)

    def test_metahuman_cobre_core_e_dedos(self):
        m = rp.PROFILES["metahuman"]
        self.assertEqual(m["hips"], "pelvis")
        self.assertEqual(m["upper_arm.L"], "upperarm_l")
        self.assertEqual(m["shin.R"], "calf_r")
        self.assertEqual(m["thumb.1.L"], "thumb_01_l")
        self.assertEqual(m["pinky.3.R"], "pinky_03_r")
        for b in ("spine_01", "spine_02", "clavicle_l", "ball_l"):
            self.assertIn(b, m.values())

    def test_vrm2_naming(self):
        v = rp.PROFILES["vrm2"]
        self.assertEqual(v["shoulder.L"], "leftShoulder")
        self.assertEqual(v["upper_arm.L"], "leftUpperArm")
        self.assertEqual(v["index.2.R"], "rightIndexIntermediate")
        self.assertEqual(v["pinky.1.L"], "leftLittleProximal")

    def test_mixamo_naming(self):
        x = rp.PROFILES["mixamo"]
        self.assertTrue(x["hips"].startswith("mixamorig:"))
        self.assertEqual(x["forearm.L"], "mixamorig:LeftForeArm")
        self.assertEqual(x["middle.2.R"], "mixamorig:RightHandMiddle2")

    def test_custom_mantem_canonico(self):
        for c in rp.CANONICAL_BONES:
            self.assertEqual(rp.remap(c, "custom"), c)

    def test_remap_desconhecido(self):
        self.assertIsNone(rp.remap("inexistente", "metahuman"))
        with self.assertRaises(ValueError):
            rp.bones_for("nao_existe")

    def test_profile_json_valido(self):
        dados = json.loads(rp.profile_json("metahuman"))
        self.assertEqual(dados["profile"], "metahuman")
        self.assertGreaterEqual(len(dados["bones"]), 50)
        self.assertTrue(all("canonical" in b and "bone" in b for b in dados["bones"]))


class TestPosicoes(unittest.TestCase):
    def test_altura_plausivel(self):
        pos = rp.bone_positions(1.70)
        self.assertAlmostEqual(pos["head_top"][2], 1.70, places=6)
        self.assertLess(pos["hips"][2], pos["chest"][2])
        self.assertLess(pos["chest"][2], pos["neck"][2])

    def test_lados_espelhados(self):
        pos = rp.bone_positions(1.8)
        self.assertAlmostEqual(pos["hand.L"][0], -pos["hand.R"][0], places=6)
        self.assertAlmostEqual(pos["thigh.L"][2], pos["thigh.R"][2], places=6)

    def test_tails(self):
        pos = rp.bone_positions(1.7)
        self.assertEqual(rp.tail_for("spine", pos), pos["chest"])
        self.assertEqual(rp.tail_for("upper_arm.L", pos), pos["forearm.L"])
        self.assertIsNone(rp.tail_for("head_top", pos))


class TestRegistroM1(unittest.TestCase):
    def test_tools_m1_registradas(self):
        nomes = {t["name"] for t in tr.TOOLS}
        for t in ("spawn_base_body", "apply_body_proportions", "rig_human",
                  "set_export_profile", "reference_backdrop"):
            self.assertIn(t, nomes)

    def test_enum_de_perfis_no_schema(self):
        t = next(t for t in tr.TOOLS if t["name"] == "set_export_profile")
        self.assertEqual(t["parameters"]["properties"]["profile"]["enum"],
                         ["metahuman", "vrm2", "mixamo", "custom"])

    def test_schemas_validos(self):
        for t in tr.TOOLS:
            self.assertIn(t["parameters"]["type"], ("object",))
            self.assertIn("properties", t["parameters"])
        # function_declarations não podem levar 'fn'
        for s in tr.schemas_for_llm():
            self.assertNotIn("fn", s)

    def test_despacho_tool_desconhecida(self):
        res = tr.run("nao_existe", {}, {"root": "/tmp"})
        self.assertFalse(res["ok"])
        self.assertIn("desconhecida", res["text"])

    def test_busca_corpo_no_banco_pura(self):
        from bloom_agent.tools import handlers as h
        vazio = Path("/tmp/bank-vazio-inexistente")
        self.assertIsNone(h._find_body_in_bank(vazio, "any"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
