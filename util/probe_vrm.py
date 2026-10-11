# -*- coding: utf-8 -*-
r"""Raio-X de um .vrm: importa com o addon VRM e roda o model_probe.

Rode via: blender --background --python util/probe_vrm.py -- --vrm ARQUIVO --out SAIDA
"""
import sys
from pathlib import Path

import addon_utils
import bpy

UTIL = Path(__file__).resolve().parent
REPO = UTIL.parent
args = sys.argv[sys.argv.index("--") + 1:]
VRM = args[args.index("--vrm") + 1]
SAIDA = args[args.index("--out") + 1]


def liga_vrm():
    """O addon VRM fica desligado por padrao; liga so nesta sessao."""
    for mod in ("bl_ext.user_default.vrm", "bl_ext.user_default.io_scene_vrm",
                "vrm", "io_scene_vrm", "bl_ext.user_default.vrm_addon"):
        try:
            if addon_utils.enable(mod):
                return True
        except Exception:
            continue
    return any(m.__name__.endswith("vrm") for m in addon_utils.modules()
               if addon_utils.check(m.__name__)[1])


bpy.ops.wm.read_homefile(use_empty=True)
if not liga_vrm():
    print("[X] Addon VRM nao instalado/nao ligou.")
    print("    Baixe o zip (VRM Addon for Blender - github saturday06),")
    print("    solte em plugins_src, rode instalar_plugins.bat e tente de novo.")
    sys.exit(1)

try:
    bpy.ops.import_scene.vrm(filepath=VRM)
except Exception as exc:
    print("[X] Falhou importar o .vrm: " + str(exc).splitlines()[0][:120])
    sys.exit(1)

sys.argv = [sys.argv[0], "--", "--out", SAIDA]
import runpy
runpy.run_path(str(REPO / "tools" / "model_probe.py"), run_name="__main__")
