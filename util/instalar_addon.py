# -*- coding: utf-8 -*-
r"""Instala (e LIGA) o addon Bloom Agent no Blender — atualizacao sem dor.

Rode via: blender --background --python util/instalar_addon.py -- --zip CAMINHO
Se o Blender ja estava aberto, feche e abra de novo p/ carregar a versao nova.
"""
import sys
from pathlib import Path

import addon_utils
import bpy

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ZIP = args[args.index("--zip") + 1] if "--zip" in args else ""
if not ZIP or not Path(ZIP).exists():
    print(f"[X] zip do addon nao encontrado: {ZIP}")
    sys.exit(1)

for kwargs in ({"overwrite": True}, {}):
    try:
        bpy.ops.preferences.extension_install_file(filepath=str(Path(ZIP).resolve()), **kwargs)
        print("  addon instalado (extensao).")
        break
    except TypeError:
        continue
    except Exception as exc:
        msg = str(exc)
        if "already" in msg.lower():
            print("  addon ja instalado — atualizando de qualquer forma falhou?")
            break
        try:
            bpy.ops.preferences.addon_install(filepath=str(Path(ZIP).resolve()), overwrite=True)
            print("  addon instalado (legado).")
            break
        except Exception:
            print(f"[X] falhou instalar: {msg.splitlines()[0][:100]}")
            sys.exit(1)

ligou = False
for mod in ("bl_ext.user_default.bloom_agent", "bloom_agent"):
    try:
        if addon_utils.enable(mod, default_set=True, persistent=True):
            print(f"  addon LIGADO: {mod}")
            ligou = True
            break
    except Exception:
        continue
if not ligou:
    print("  [!] nao consegui ligar sozinho — ligue em Edit > Preferences > Add-ons (Bloom Agent).")

try:
    bpy.ops.wm.save_userpref()
    print("  preferencias salvas.")
except Exception as exc:
    print(f"  AVISO: nao salvei preferencias ({exc})")
print("=== ADDON BLOOM AGENT ATUALIZADO ===")
