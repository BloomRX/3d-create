# -*- coding: utf-8 -*-
r"""Instala os plugins do repo no Blender — todos ficam DESLIGADOS por padrao.

Rode via: blender --background --python util/instalar_plugins.py
(zips em plugins_src/ tem prioridade; assets/learn/ entra como segundo local)
"""
import sys
from pathlib import Path

import bpy

UTIL = Path(__file__).resolve().parent
REPO = UTIL.parent
PASTAS = [REPO / "plugins", REPO / "plugins_src", REPO / "assets" / "learn"]


def instalar_zip(caminho):
    """Tenta como extensao (4.2+); cai p/ addon legado. Mantem DESLIGADO."""
    nome = caminho.name
    for kwargs in ({"overwrite": True}, {}):
        try:
            bpy.ops.preferences.extension_install_file(filepath=str(caminho), **kwargs)
            return "ok (extensao, desligado)"
        except TypeError:
            continue
        except Exception as exc:
            msg = str(exc)
            if "already" in msg.lower() or "ja instal" in msg.lower():
                return "ja estava instalado (nada feito)"
            break
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
            if any(z.name.lower().endswith(x) for x in (".rar",)):
                continue
            resultado = instalar_zip(z)
            feitos.append((z.name, resultado))
            print(f"  {z.name}: {resultado}")
    # addon legado em .py solto (ex.: wiggle_2.py do Wiggle 2)
    for pasta in PASTAS:
        if not pasta.is_dir():
            continue
        for py in sorted(pasta.glob("*.py")):
            if py.name in ("__init__.py", "instalar_plugins.py"):
                continue
            try:
                bpy.ops.preferences.addon_install(filepath=str(py), overwrite=True)
                feitos.append((py.name, "ok (legado .py, desligado)"))
            except Exception as exc:
                msg = str(exc)
                if "already" in msg.lower():
                    feitos.append((py.name, "ja estava instalado (nada feito)"))
                else:
                    feitos.append((py.name, "FALHOU: " + msg.splitlines()[0][:90]))
            print(f"  {py.name}: {feitos[-1][1]}")
    rar = [p.name for pasta in PASTAS if pasta.is_dir()
           for p in pasta.glob("*.rar")]
    if rar:
        print(f"  (pulados .rar — extrair antes e zipar: {', '.join(rar)})")
    if any("ok" in r for _, r in feitos):
        try:
            bpy.ops.wm.save_userpref()
            print("  preferencias salvas.")
        except Exception as exc:
            print(f"  AVISO: nao salvei preferencias ({exc})")
    ok = sum(1 for _, r in feitos if r.startswith(("ok", "ja")))
    print(f"=== RESUMO: {ok}/{len(feitos)} plugins prontos (todos DESLIGADOS por padrao) ===")
    print("  Ligar/desligar: Edit > Preferences > Add-ons")


main()
