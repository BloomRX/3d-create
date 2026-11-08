"""v0.4.4 — HAIRDECK ponte completa + Motion2MixamoRig empacotado (M5).

HairDeck (arXiv 2610.40599): foto -> cartas de cabelo animation-ready (spring
bones) -> GLB/VRM com cores da foto. Rota: colab_job kind=hairdeck ->
colab/hairdeck_bloom.ipynb (T4) -> coleção importa GLB e vira peça cabelo.
"""
import json
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PKG = REPO / "agent" / "bloom_agent"


class TestNotebookHairDeck(unittest.TestCase):
    def setUp(self):
        self.nb = json.loads((REPO / "colab" / "hairdeck_bloom.ipynb")
                             .read_text(encoding="utf-8"))
        self.src = "\n".join("".join(c["source"]) for c in self.nb["cells"])

    def test_celulas_essenciais(self):
        for marca in ("image_to_hair.py", "hairdeck.vrm.export",
                      "download_weights.py", "facebook/sam3",
                      "dinov3", "/job/{job_id}/result",
                      "/job/{job_id}/complete", "X-Result-Name"):
            self.assertIn(marca, self.src, f"notebook hairdeck perdeu: {marca}")

    def test_protocolo_igual_ao_test_bridge(self):
        self.assertIn('base_url + "/health"', self.src)

    def test_json_valido(self):
        self.assertEqual(self.nb["nbformat"], 4)


class TestPonteNoAddon(unittest.TestCase):
    def setUp(self):
        self.h = (PKG / "tools" / "handlers.py").read_text(encoding="utf-8")

    def test_job_hairdeck_instrui(self):
        self.assertIn('if kind == "hairdeck":', self.h)
        self.assertIn("colab/hairdeck_bloom.ipynb", self.h)
        self.assertIn("facebook/sam3", self.h)

    def test_coletar_importa_cabelo(self):
        for marca in ("_importar_cabelo_hairdeck", "Bloom_HairCards",
                      'bloom_piece"] = "cabelo"', "SPRING BONES", "linha do pescoço"):
            self.assertIn(marca, self.h, f"coleta hairdeck perdeu: {marca}")


class TestMotion2MixamoRig(unittest.TestCase):
    def test_zip_empacotado(self):
        z = zipfile.ZipFile(REPO / "plugins" / "Motion2MixamoRig-v0.1.8.zip")
        nomes = z.namelist()
        self.assertTrue(any(n.endswith("blender_manifest.toml") for n in nomes))
        manifest = z.read("motion2mixamorig_blender/blender_manifest.toml").decode("utf-8")
        self.assertIn('id = "motion2mixamorig"', manifest)
        self.assertIn('version = "0.1.8"', manifest)
        self.assertIn("Apache-2.0", manifest)

    def test_proveniencia_no_readme(self):
        r = (REPO / "plugins" / "README.md").read_text(encoding="utf-8")
        self.assertIn("Motion2MixamoRig v0.1.8", r)
        self.assertIn("Apache-2.0", r)


if __name__ == "__main__":
    unittest.main(verbosity=2)
