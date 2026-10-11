# -*- coding: utf-8 -*-
r"""Instala (e LIGA) o addon Bloom Agent — formato extensão, no lugar certo.

Rode via: blender --background --python util/instalar_addon.py -- --zip CAMINHO
Se o Blender já estava aberto, feche e abra de novo p/ carregar a versão nova.
"""
import re
import sys
from pathlib import Path

import bpy

UTIL = Path(__file__).resolve().parent
sys.path.insert(0, str(UTIL))
import ext_install  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ZIP = args[args.index("--zip") + 1] if "--zip" in args else ""
if not ZIP or not Path(ZIP).exists():
    print(f"[X] zip do addon nao encontrado: {ZIP}")
    sys.exit(1)

estado, addon_id = ext_install.instalar_extensao(Path(ZIP), ligar=True)
if not estado:
    # não é extensão (sem manifest) — tenta legado
    try:
        bpy.ops.preferences.addon_install(filepath=str(Path(ZIP).resolve()),
                                          overwrite=True)
        estado, addon_id = "ok (legado)", "bloom_agent"
    except Exception as exc:
        print(f"[X] falhou instalar: {str(exc).splitlines()[0][:100]}")
        sys.exit(1)
print(f"  {estado}")

# versão no disco, lida do lugar certo
def versao_manifesto(pasta):
    m = pasta / "blender_manifest.toml"
    if m.exists():
        for linha in m.read_text(encoding="utf-8", errors="replace").splitlines():
            l = linha.strip()
            if l.startswith("version") and "=" in l:
                v = l.split("=", 1)[1].strip().strip("\"'")
                if re.match(r"^\d+\.\d+", v):
                    return v
    return None

v = versao_manifesto(ext_install.pasta_extensoes() / (addon_id or "bloom_agent"))
print(f"=== ADDON BLOOM AGENT: instalado {v or '?'} ===")
if v:
    print(f"VERSAO_INSTALADA={v}")
try:
    bpy.ops.wm.save_userpref()
    print("  preferencias salvas.")
except Exception as exc:
    print(f"  AVISO: nao salvei preferencias ({exc})")
