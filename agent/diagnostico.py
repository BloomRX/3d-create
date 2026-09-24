# -*- coding: utf-8 -*-
"""Diagnóstico do Bloom Agent — como usar (2 passos):

1. No Blender, troque o workspace no topo para "Scripting".
2. Botão "Open" (ou "Abrir") > selecione este arquivo (agent/diagnostico.py)
   > clique no botão ▶ (Run Script / Executar Script).

O resultado aparece NO PRÓPRIO EDITOR DE TEXTO (arquivo "DIAGNOSTICO_BLOOM").
Selecione tudo (Ctrl+A), copie (Ctrl+C) e cole na conversa com o agent.
Também é impresso no Console do Sistema (Window > Toggle System Console).
"""
import importlib
import importlib.util
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

import bpy

L = []


def w(s=""):
    L.append(str(s))


w("=== DIAGNÓSTICO BLOOM AGENT (v3) ===")
w(f"gerado: {datetime.now():%d/%m/%Y %H:%M}")
w(f"Blender: {bpy.app.version_string}  (build {bpy.app.version})")
w(f"Python: {sys.version.split()[0]}")
w("")

# 1) estado do addon nas preferências --------------------------------------
w("--- 1) Instalação/habilitação ---")
prefs_mods = []
try:
    import addon_utils

    for mod in addon_utils.modules():
        if "bloom" in mod.__name__.lower():
            enabled, loaded = addon_utils.check(mod.__name__)
            prefs_mods.append(mod.__name__)
            w(f"instalado: {mod.__name__} | habilitado={enabled} carregado={loaded} "
              f"| arquivo={getattr(mod, '__file__', '?')}")
    ativos = [k for k in bpy.context.preferences.addons.keys() if "bloom" in k.lower()]
    w(f"ativas em preferences.addons: {ativos or 'NENHUMA'}")
    if len(prefs_mods) > 1:
        w("⚠️ MAIS DE UMA INSTALAÇÃO — rode agent\\limpar_instalacoes.bat")
    for p in prefs_mods:
        if enabled and not loaded:
            w(f"⚠️ '{p}' está HABILITADO mas NÃO CARREGADO = o register() deu erro "
              f"(a seção 3 abaixo mostra o traceback exato).")
except Exception:
    w(traceback.format_exc())
w("")

# 2) import do código (vale o nome de extensão OU o legado) ------------------
w("--- 2) Import do código ---")
mod = None
candidatos = prefs_mods + ["bloom_agent", "bl_ext.user_default.bloom_agent"]
vistos = []
for nome in candidatos:
    if nome in vistos:
        continue
    vistos.append(nome)
    try:
        m = importlib.import_module(nome)
        w(f"import OK: {nome} -> {getattr(m, '__file__', '?')}")
        if mod is None:
            mod = m
    except ModuleNotFoundError:
        w(f"import não disponível: {nome}")
    except Exception:
        w(f"import ERRO em {nome}:")
        w(traceback.format_exc())
if mod is None:
    w("(nenhum importável — normal p/ extensão; a seção 3 carrega do disco)")
w("")

# 3) carregar (register) COM CAPTURA DE ERRO --------------------------------
w("--- 3) Tentativa de carregar (register) ---")


def _carregar_do_disco():
    """Acha a pasta do addon no disco e importa como pacote novo."""
    raizes = [
        Path(os.environ.get("APPDATA", "")) / "Blender Foundation" / "Blender",
        Path(bpy.utils.user_resource("EXTENSIONS")).parents[1]
        if bpy.utils.user_resource("EXTENSIONS") else None,
    ]
    pastas = []
    for r in raizes:
        if not r:
            continue
        pastas += [Path(p) for p in
                   r.glob(os.path.join("*", "extensions", "user_default", "bloom_agent"))]
        pastas += [Path(p) for p in
                   r.glob(os.path.join("*", "scripts", "addons", "bloom_agent"))]
    for d in pastas:
        if (d / "__init__.py").is_file():
            return d
    return None


try:
    if mod is None:
        pasta = _carregar_do_disco()
        if pasta is None:
            w("❌ não achei a pasta do addon no disco (addon não instalado?).")
        else:
            w(f"carregando de: {pasta}")
            spec = importlib.util.spec_from_file_location(
                f"bloom_probe_{datetime.now():%H%M%S}",
                pasta / "__init__.py",
                submodule_search_locations=[str(pasta)])
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
            w("arquivos importados OK")
    if mod is not None and hasattr(mod, "register"):
        try:
            mod.register()
            w(">>> register() executou SEM ERRO <<<")
            w("Se a aba 'Bloom' não estiver visível, feche e abra a N (ou reinicie o Blender).")
        except Exception:
            w(">>> register() FALHOU — ERRO EXATO: <<<")
            w(traceback.format_exc())
except Exception:
    w("ERRO ao importar do disco:")
    w(traceback.format_exc())
w("")

# 4) resultado após a tentativa ----------------------------------------------
w("--- 4) Estado agora ---")
try:
    prop = bpy.types.Scene.bl_rna.properties.get("bloom_props")
    w(f"bloom_props registrado em Scene: {'SIM' if prop else 'NÃO'}")
    pans = [(c.bl_idname, c.__module__) for c in bpy.types.Panel.__subclasses__()
            if "BLOOM" in getattr(c, "bl_idname", "")]
    for nome, modulo in pans:
        w(f"painel: {nome}  (de: {modulo})")
    if not pans:
        w("nenhum painel BLOOM registrado")
except Exception:
    w(traceback.format_exc())
w("")

# 5) contexto da janela -------------------------------------------------------
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

try:
    caminho = os.path.join(bpy.app.tempdir, "diagnostico_bloom.txt")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto + "\n")
    l2 = f"cópia salva em: {caminho}"
except Exception:
    l2 = "(não consegui salvar cópia em arquivo)"
print(texto)
print("\n" + "=" * 60)
print(l2)
