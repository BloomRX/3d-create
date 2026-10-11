# -*- coding: utf-8 -*-
r"""Instala os plugins do repo no Blender — todos ficam DESLIGADOS.

Extension zips (blender_manifest.toml) vão para extensions/user_default;
addons legados (bl_info) vão pelo caminho clássico. .rar e .py legado tratados.
Rode via: blender --background --python util/instalar_plugins.py
"""
import sys
from pathlib import Path

import bpy

UTIL = Path(__file__).resolve().parent
sys.path.insert(0, str(UTIL))
import ext_install  # noqa: E402

REPO = UTIL.parent
PASTAS = [REPO / "plugins", REPO / "plugins_src", REPO / "assets" / "learn"]


def instalar_zip(caminho):
    estado, _ = ext_install.instalar_extensao(caminho, ligar=False)
    if estado:
        return estado + "; DESLIGADO"
    try:
        bpy.ops.preferences.addon_install(filepath=str(caminho), overwrite=True)
        return "ok (legado, desligado)"
    except Exception as exc:
        msg = str(exc)
        if "already" in msg.lower():
            return "ja estava instalado (nada feito)"
        return "FALHOU: " + msg.splitlines()[0][:90]


def main():
    print("=== INSTALAR PLUGINS (Bloom Agent) ===")
    feitos = []
    for pasta in PASTAS:
        if not pasta.is_dir():
            continue
        for z in sorted(pasta.glob("*.zip")):
            feitos.append((z.name, instalar_zip(z)))
            print(f"  {z.name}: {feitos[-1][1]}")
        for py in sorted(pasta.glob("*.py")):
            if py.name in ("__init__.py", "instalar_plugins.py"):
                continue
            try:
                bpy.ops.preferences.addon_install(filepath=str(py), overwrite=True)
                feitos.append((py.name, "ok (legado .py, desligado)"))
            except Exception as exc:
                msg = str(exc)
                feitos.append((py.name, "FALHOU: " + msg.splitlines()[0][:80]
                               if "already" not in msg.lower()
                               else "ja estava instalado"))
            print(f"  {py.name}: {feitos[-1][1]}")
        rar = [p.name for p in pasta.glob("*.rar")]
        if rar:
            print(f"  (pulados .rar — extrair antes e zipar: {', '.join(rar)})")
    if any(r.startswith("ok") for _, r in feitos):
        try:
            bpy.ops.wm.save_userpref()
            print("  preferencias salvas.")
        except Exception as exc:
            print(f"  AVISO: nao salvei preferencias ({exc})")
    ok = sum(1 for _, r in feitos if r.startswith(("ok", "ja")))
    print(f"=== RESUMO: {ok}/{len(feitos)} plugins prontos (todos DESLIGADOS por padrao) ===")


main()
