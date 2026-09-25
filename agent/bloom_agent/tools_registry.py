"""Registro de tools: schemas (p/ o Gemini) + despacho (roda o handler).

Os schemas são JSON Schema simples (function_declarations do Gemini v1beta).
O despacho importa os handlers sob demanda — assim este módulo e os schemas
são utilizáveis FORA do Blender (testes).
"""
from __future__ import annotations

import importlib

TOOLS = [
    {
        "name": "list_scene",
        "description": "Lista os objetos da cena (nome, tipo, pai, modificadores, polígonos).",
        "parameters": {"type": "object", "properties": {}, "required": []},
        "fn": "list_scene",
    },
    {
        "name": "scene_stats",
        "description": "Contagem total de objetos/tris/verts da cena.",
        "parameters": {"type": "object", "properties": {}, "required": []},
        "fn": "scene_stats",
    },
    {
        "name": "create_object",
        "description": ("Cria uma primitiva (cube, ico_sphere, cylinder, cone, plane, metaball) "
                        "na cena. Use metaball para orgânicos: combine várias, depois remesh via "
                        "run_blender_python."),
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["cube", "ico_sphere", "cylinder", "cone", "plane", "metaball"]},
                "name": {"type": "string"},
                "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "scale": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
            },
            "required": ["kind"],
        },
        "fn": "create_object",
    },
    {
        "name": "delete_object",
        "description": "Remove um objeto da cena pelo nome. Confirme com o usuário antes de apagar algo importante.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        "fn": "delete_object",
    },
    {
        "name": "run_blender_python",
        "description": ("Executa Python com acesso a bpy/bmesh/mathutils (modelagem, remesh, sculpt, "
                        "UV, materiais, rig, shape keys...). É a tool principal para modelar. "
                        "Sem rede/subprocess (guard). Descreva o objetivo em 'note'."),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Código Python a executar."},
                "note": {"type": "string", "description": "Resumo do objetivo (aparece no log)."},
            },
            "required": ["code"],
        },
        "fn": "run_blender_python",
    },
    {
        "name": "render_view",
        "description": ("Renderiza a vista atual (Eevee, 512px) e DEVOLVE a imagem para você analisar. "
                        "Sempre chame após mudar geometria para verificar o resultado."),
        "parameters": {
            "type": "object",
            "properties": {"size": {"type": "integer", "default": 512}},
            "required": [],
        },
        "fn": "render_view",
    },
    {
        "name": "reference_info",
        "description": "Informa se há imagem de referência do usuário ativa na conversa.",
        "parameters": {"type": "object", "properties": {}, "required": []},
        "fn": "reference_info",
    },
    {
        "name": "asset_scan",
        "description": ("Re-escaneia a pasta local do Asset Bank e regenera o index.json. "
                        "Chame antes de procurar assets quando o usuário tiver adicionado arquivos."),
        "parameters": {"type": "object", "properties": {}, "required": []},
        "fn": "asset_scan",
    },
    {
        "name": "asset_import",
        "description": ("Importa um asset do Asset Bank (glb/gltf/fbx/obj/blend) para a cena, "
                        "pelo nome exato ou termo nas tags. Depois de importar, adapte "
                        "(escala, posição, shrinkwrap) com run_blender_python."),
        "parameters": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Nome/rel do asset no banco."},
                "name": {"type": "string", "description": "Nome do objeto após importar (opcional)."},
            },
            "required": ["file"],
        },
        "fn": "asset_import",
    },
    {
        "name": "colab_job",
        "description": ("Cria um job para rodar no Colab (geração 3D etc.). ÚLTIMO RECURSO: só se "
                        "modelar no Blender (run_blender_python) e o Asset Bank não resolverem. "
                        "O usuário abre o notebook no Colab; o resultado volta pela ponte. "
                        "Informe 'kind' (ex.: 'echo' p/ teste, 'gen3d' p/ geração)."),
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string"},
                "params": {"type": "object"},
                "note": {"type": "string"},
            },
            "required": ["kind"],
        },
        "fn": "colab_job",
    },
    {
        "name": "colab_collect",
        "description": "Lista resultados baixados de um job do Colab (job_id).",
        "parameters": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]},
        "fn": "colab_collect",
    },
]


def schemas_for_llm() -> list:
    """No formato function_declarations do Gemini."""
    return [{
        "name": t["name"],
        "description": t["description"],
        "parameters": t["parameters"],
    } for t in TOOLS]


def _find(name: str) -> dict | None:
    for t in TOOLS:
        if t["name"] == name:
            return t
    return None


def run(name: str, args: dict, ctx: dict) -> dict:
    """Despacha uma tool. Nunca lança: erros viram {"ok": False, ...}."""
    t = _find(name)
    if t is None:
        return {"ok": False, "text": f"Tool desconhecida: {name!r}.", "images": []}
    try:
        # relativo: como extensão o pacote se chama bl_ext.user_default.bloom_agent
        mod = importlib.import_module(".tools.handlers", package=__package__)
        fn = getattr(mod, t["fn"])
        result = fn(args or {}, ctx)
    except Exception as e:
        return {"ok": False,
                "text": f"Falha interna em {name}: {type(e).__name__}: {e}",
                "images": []}
    if not isinstance(result, dict):
        result = {"ok": True, "text": str(result), "images": []}
    result.setdefault("ok", True)
    result.setdefault("text", "")
    result.setdefault("images", [])
    return result
