# -*- coding: utf-8 -*-
"""Diagnóstico do Bloom Agent — como usar (2 passos):

1. No Blender, troque o workspace no topo para "Scripting".
2. Botão "Open" (ou "Abrir") > selecione este arquivo (agent/diagnostico.py)
   > clique no botão ▶ (Run Script / Executar Script).

O resultado aparece NO PRÓPRIO EDITOR DE TEXTO (arquivo "DIAGNOSTICO_BLOOM").
Selecione tudo (Ctrl+A), copie (Ctrl+C) e cole na conversa com o agent.
Também é impresso no Console do Sistema (Window > Toggle System Console).
"""
import sys
import traceback
from datetime import datetime

import bpy

L = []


def w(s=""):
    L.append(str(s))


w("=== DIAGNÓSTICO BLOOM AGENT ===")
w(f"gerado: {datetime.now():%d/%m/%Y %H:%M}")
w(f"Blender: {bpy.app.version_string}  (build {bpy.app.version})")
w(f"Python: {sys.version.split()[0]}")
try:
    w(f"Sistema: {bpy.app.build_platform.decode() if isinstance(bpy.app.build_platform, bytes) else bpy.app.build_platform}")
except Exception:
    pass
w("")

# 1) estado do addon nas preferências --------------------------------------
w("--- 1) Instalação/habilitação ---")
try:
    import addon_utils

    for mod in addon_utils.modules():
        if "bloom" in mod.__name__.lower():
            enabled, loaded = addon_utils.check(mod.__name__)
            info = getattr(mod, "__bl_info__", {}) or {}
            w(f"instalado: {mod.__name__} | habilitado={enabled} carregado={loaded} "
              f"| versão={info.get('version')} | arquivo={getattr(mod, '__file__', '?')}")
    ativos = [k for k in bpy.context.preferences.addons.keys() if "bloom" in k.lower()]
    w(f"chaves ativas em preferences.addons: {ativos or 'NENHUMA'}")
except Exception:
    w(traceback.format_exc())
w("")

# 2) import do package -------------------------------------------------------
w("--- 2) Import do código ---")
try:
    import bloom_agent

    w(f"import OK | {bloom_agent.__file__}")
    w(f"_IN_BLENDER = {getattr(bloom_agent, '_IN_BLENDER', '?')}")
except Exception:
    w("import FALHOU:")
    w(traceback.format_exc())
w("")

# 3) registro das propriedades na cena ---------------------------------------
w("--- 3) Propriedades (Scene.bloom_props) ---")
try:
    import bloom_agent.ui as _u

    w(f"ui import OK | _State.root = {_u._State.root}")
except Exception:
    w(traceback.format_exc())
try:
    prop = bpy.types.Scene.bl_rna.properties.get("bloom_props")
    w(f"registrado em Scene: {'SIM' if prop else 'NÃO'}")
    scn = bpy.context.scene
    p = getattr(scn, "bloom_props", None) if scn else None
    w(f"instância acessível na cena atual: {'SIM' if p is not None else 'NÃO'}")
except Exception:
    w(traceback.format_exc())
w("")

# 4) painel e operadores ------------------------------------------------------
w("--- 4) Painel/operadores registrados ---")
try:
    pans = [(c.bl_idname, c.__module__) for c in bpy.types.Panel.__subclasses__()
            if "BLOOM" in getattr(c, "bl_idname", "")]
    for nome, modulo in pans:
        w(f"painel: {nome}  (vem de: {modulo})")
    if len(pans) > 1:
        w("⚠️ painel duplicado — confirma a instalação dupla (seção 1).")
    ops = [a for a in dir(bpy.ops.bloom) if not a.startswith("_")]
    w(f"bpy.ops.bloom.*: {ops or 'NENHUM'}")
except Exception:
    w(traceback.format_exc())
w("")

# 5) contexto da janela atual -------------------------------------------------
w("--- 5) Onde você está olhando ---")
try:
    win = bpy.context.window_manager.windows[0] if bpy.context.window_manager.windows else None
    if win:
        achou = False
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                achou = True
                regioes = [r.type for r in area.regions]
                w(f"3D View encontrada — região N (UI) presente: {'SIM' if 'UI' in regioes else 'NÃO'}")
                break
        if not achou:
            w("NENHUMA 3D View neste workspace (a aba Bloom só existe nela).")
except Exception:
    w(traceback.format_exc())
w("")
w(">>> COPIE ESTE ARQUIVO INTEIRO E COLE NA CONVERSA <<<")

texto = "\n".join(L)

# mostra no editor de texto atual
try:
    sd = bpy.context.space_data
    if sd is not None and sd.type == "TEXT_EDITOR":
        for t in list(bpy.data.texts):
            if t.name == "DIAGNOSTICO_BLOOM":
                bpy.data.texts.remove(t)
        t = bpy.data.texts.new("DIAGNOSTICO_BLOOM")
        t.write(texto)
        sd.text = t
except Exception:
    pass

# salva cópia em arquivo
try:
    import os

    caminho = os.path.join(bpy.app.tempdir, "diagnostico_bloom.txt")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto + "\n")
    L2 = f"cópia salva em: {caminho}"
    print(L2)
except Exception:
    L2 = "(não consegui salvar cópia em arquivo)"
print(texto)
print("\n" + "=" * 60)
print(L2)
