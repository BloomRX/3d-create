# -*- coding: utf-8 -*-
"""Raio-X de um modelo .blend (ex.: personagem de estúdio tipo WuWa/Hsin).

COMO USAR:
1. Abra o .blend da personagem no Blender.
2. Workspace "Scripting" > Open > este arquivo > botão ▶.
3. Um arquivo model_probe.json será salvo na pasta temporária (o caminho
   aparece no console e no editor). Cole o conteúdo na conversa com o agent.

O que ele extrai: objetos, polígonos, modificadores, materiais (nós,
texturas, blend), shape keys, ossos, custom normals, UVs, drivers,
configuração de render — o "DNA" técnico do modelo pra eu estudar e
reproduzir as técnicas no Bloom Agent.

Uso privado/estudo — não redistribua o modelo nem o relatório com texturas.
"""
import json
import os
import sys

import bpy


def limpa_lista(itens, n=400):
    return [str(x) for x in list(itens)[:n]]


dados = {"blender": bpy.app.version_string, "objetos": [], "materiais": [],
         "shape_keys_global": [], "armaduras": [], "drivers": 0, "render": {}}

# ---- objetos ----
for ob in bpy.data.objects:
    info = {"nome": ob.name, "tipo": ob.type}
    if ob.type == "MESH":
        me = ob.data
        info["tris"] = len(me.polygons)
        info["verts"] = len(me.vertices)
        info["uvs"] = [u.name for u in me.uv_layers]
        info["cores"] = [c.name for c in me.color_attributes]
        info["custom_normals"] = bool(getattr(me, "has_custom_normals", False))
        info["materiais"] = limpa_lista((m.name for m in me.materials if m), 10)
        info["mods"] = [{"tipo": m.type, "nome": m.name,
                         "detalhe": (f"thickness={getattr(m, 'thickness', '')}"
                                     if m.type == 'SOLIDIFY' else
                                     f"objeto={getattr(m, 'object', '')}"
                                     if m.type == 'DATA_TRANSFER' else "")}
                        for m in ob.modifiers]
        if me.shape_keys and len(me.shape_keys.key_blocks) > 1:
            dados["shape_keys_global"].append(
                {ob.name: [k.name for k in me.shape_keys.key_blocks][:80]})
        if ob.parent and ob.parent.type == "ARMATURE":
            vg = len(ob.vertex_groups)
            info["vertex_groups"] = vg
    elif ob.type == "ARMATURE":
        ossos = [b.name for b in ob.data.bones]
        info["ossos_n"] = len(ossos)
        info["ossos"] = ossos[:400]
        twists = [b for b in ossos if "twist" in b.lower()]
        info["twist_bones"] = len(twists)
    info["oculto_render"] = ob.hide_render
    dados["objetos"].append(info)

# ---- materiais ----
for m in bpy.data.materials:
    if m.users == 0:
        continue
    mi = {"nome": m.name, "blend": str(getattr(m, "blend_method", "?")),
          "backface": str(getattr(m, "use_backface_culling", "?"))}
    if m.use_nodes:
        nos = m.node_tree.nodes
        mi["nos_n"] = len(nos)
        tipos = {}
        for n in nos:
            tipos[n.type] = tipos.get(n.type, 0) + 1
        mi["nos_tipos"] = tipos
        texturas = []
        for n in nos:
            if n.type == "TEX_IMAGE" and n.image:
                texturas.append({"img": n.image.name,
                                 "tam": list(n.image.size)[:2]})
        mi["texturas"] = texturas[:12]
    dados["materiais"].append(mi)

# ---- drivers ----
try:
    dados["drivers"] = len(bpy.data.drivers if hasattr(bpy.data, "drivers")
                           else bpy.context.scene.animation_data.drivers)
except Exception:
    try:
        n = 0
        for ob in bpy.data.objects:
            ad = ob.animation_data
            if ad:
                n += len(ad.drivers)
        dados["drivers"] = n
    except Exception:
        pass

# ---- render ----
s = bpy.context.scene
dados["render"] = {"engine": s.render.engine,
                   "res": [s.render.resolution_x, s.render.resolution_y],
                   "fps": s.render.fps}

out = json.dumps(dados, ensure_ascii=False, indent=1)
caminho = os.path.join(bpy.app.tempdir, "model_probe.json")
with open(caminho, "w", encoding="utf-8") as f:
    f.write(out)

resumo = (f"objetos: {len(dados['objetos'])} | materiais: {len(dados['materiais'])} "
          f"| ossos: {sum(o.get('ossos_n', 0) for o in dados['objetos'])} "
          f"| tris: {sum(o.get('tris', 0) for o in dados['objetos'])}")
print("=== MODEL PROBE ===")
print(resumo)
print("salvo em:", caminho)
print(">>> abra o arquivo e cole o conteúdo na conversa <<<")

try:
    sd = bpy.context.space_data
    if sd and sd.type == "TEXT_EDITOR":
        for t in list(bpy.data.texts):
            if t.name == "MODEL_PROBE":
                bpy.data.texts.remove(t)
        t = bpy.data.texts.new("MODEL_PROBE")
        t.write(f"{resumo}\nsalvo em: {caminho}\n\n")
        t.write(out[:100000])
        sd.text = t
except Exception:
    pass
