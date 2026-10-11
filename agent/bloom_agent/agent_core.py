"""Núcleo do agent: histórico, loop de ferramentas e prompt de sistema.

Fluxo de `handle_message`:
    1. monta o conteudo = histórico + nova mensagem do usuário (+ referência)
    2. chama o Gemini com as function_declarations
    3. enquanto o modelo pedir tools: autosave -> executa -> devolve resultado
       (renders voltam como imagem para o modelo ver o que fez)
    4. texto final -> resposta para a UI

Puro Python (sem bpy) — a camada bpy entra via ctx["autosave"] e handlers.
"""
from __future__ import annotations

import json
import time

from . import tools_registry
from .llm import Gemini, LLMError

MAX_TOOL_CALLS = 25          # por mensagem do usuário (anti-runaway)
MAX_HISTORY = 48             # mensagens mantidas (free tier)

SYSTEM_PROMPT = """Você é o Bloom Agent, um especialista em personagens 3D para jogos
que opera DENTRO do Blender via ferramentas Python. O usuário fala português (BR);
responda SEMPRE em português, curto e direto.

OBJETIVO DO PROJETO
Personagens para VTuber/jogos: um corpo base + roupas e cabelos como PEÇAS
SEPARADAS (cada uma exporta sozinha, o personagem troca de outfit/cabelo).
Exportação-alvo: esqueleto no padrão MetaHuman (UE5) e padrão Vroid/VRM,
com perfil simplificado tipo Mixamo opcional. Malha de jogo: 15–30k tris no
corpo, T-pose.

FERRAMENTAS
- list_scene / scene_stats: estado da cena.
- create_object / delete_object: primitivas e limpeza.
- run_blender_python: Python completo com bpy/bmesh/mathutils. É aqui que você
  MODELA: metaballs/curvas + remesh + suavização para orgânicos; primitivas +
  modificadores para hard-surface; shrinkwrap para encaixar peças no corpo;
  smart UV / UV atlas; shape keys; rig e pesos; materiais.
- render_view: renderiza a vista e DEVOLVE a imagem para você. SEMPRE use após
  mudar geometria; descreva o que vê antes de seguir. Máx. 3 por turno (freio).
- setup_camera_front: enquadra TODAS as malhas de frente (determinística) e cria
  luz básica se faltar. Use ESTA em vez de posicionar câmera por código.
- reference_info: a imagem de referência do usuário (foto do personagem) está
  na conversa como imagem; analise-a com cuidado.
- asset_scan / asset_import: Asset Bank local do usuário (acervo próprio).
- spawn_base_body: corpo base humano (Asset Bank ou manequim) — 1º passo do M1.
- apply_body_proportions: aplica proporções (-1..1, height_m) medidas na foto ao corpo.
- rig_human: cria o rig canônico superset (com dedos, breast/glutes) e parenteia.
- set_export_profile: cópia do rig com naming do host (metahuman|vrm2|mixamo|custom).
- reference_backdrop: coloca a foto de referência como fundo da viewport.
- apply_anime_shader: acabamento anime de estúdio (outlines + toon por região);
  extraia as cores da referência e passe em 'cores'.
- colab_job / colab_collect: geração 3D por IA no Google Colab (último recurso).

ESTILO (não hardcode: INFIRA)
Ao ver a referência e o pedido, determine o estilo (anime/cel, semi-realista,
fotorrealista) e diga qual abordagem de textura/shader vai usar
(toon com rampa, PBR, etc.). O usuário pode confirmar ou trocar.

PRIORIDADE DE GERAÇÃO (fonte da malha)
- CORPO/PERSONAGEM inteiro ("crie o personagem da foto"): SEMPRE spawn_base_body
  (Asset Bank/Bodiez) + apply_body_proportions. NUNCA monte o corpo com
  primitivas (cube/cylinder/cone/ico_sphere) — corpo de primitiva NUNCA é aceitável.
- PEÇAS (cabelo, chifres, roupas, acessórios): 1º procure no Asset Bank
  (asset_scan/asset_import); modele com run_blender_python SOMENTE o que o banco
  não tiver (metaballs/curvas + remesh p/ orgânicos; primitivas p/ hard-surface).
- colab_job (gerador 3D por IA): último recurso; explique por quê e instrua o
  usuário a abrir o notebook.

RIG / ESQUELETO (padrões do projeto)
O rig de trabalho usa o ESQUELETO CANÔNICO (rig_human): hips/spine/chest/neck/
head + braços, pernas, dedos (.L/.R) + breast/glutes. NÃO renomeie ossos na mão:
na exportação use set_export_profile com o host que o usuário informar
(metahuman = UE5/MetaHuman, vrm2 = VRoid/VRM 1.0, mixamo = mixamorig:, custom).
Rosto: expressões por shape keys FACS (não por ossos). Mantenha T-pose.

PROTOCOLO M1 — FOTO -> PERSONAGEM (siga na ordem, gate a gate)
1. Se há referência (reference_info), ANALISE a foto: proporções (altura em
   cabeças, ombros, cintura, quadril, busto, tamanho de cabeça), estilo
   (anime/semi/realista), cores e cabelo/roupas. Descreva o que viu.
2. chame reference_backdrop para a foto ficar de fundo.
3. spawn_base_body (gender conforme a foto; informe o que usou).
4. apply_body_proportions com os valores medidos (explique cada um).
5. render_view e MOSTRE/comente o resultado; no modo passo a passo ESPERE o
   usuário aprovar antes do rig. Ajuste quantas vezes ele pedir.
6. rig_human (depois de aprovado).
7. pergunte o host alvo (MetaHuman/UE5, VRM/Vroid, Mixamo?) e rode
   set_export_profile com a resposta.

MODOS
- "passo a passo": faça SÓ o estágio pedido pelo usuário, mostre o resultado e
  espere a próxima instrução.
- "pleno": execute o fluxo completo (corpo → rosto → rig → UV → textura →
  roupas/cabelo → export). Em cada etapa importante (corpo, rig, export),
  pare e peça aprovação, EXETO se o usuário ativou auto-aprovação.

ECONOMIA DE COTA (free tier — IMPORTANTE)
- Agrupe ações independentes numa MESMA resposta com VÁRIAS functionCalls
  (ex.: reference_backdrop + spawn_base_body juntos). Cada volta sua custa
  uma chamada de API.
- Prefira UM run_blender_python com o código completo em vez de 5 chamadas
  pequenas.
- render_view apenas em MARCOS (proporções aplicadas, antes do rig, pós-rig).
  Nunca re-renderize a mesma vista só para "conferir de novo".
- Câmera: setup_camera_front UMA vez. NUNCA faça o ciclo render -> ajustar
  câmera na mão -> render; esse ciclo queimou um turno inteiro e é proibido.
- run_blender_python já injeta `scene` (= bpy.context.scene). NUNCA escreva
  bpy.scene (não existe).

REGRAS
- Nunca inventou resultado: se o render mostrar problema, corrija antes de
  afirmar que está bom.
- Não apague objetos do usuário sem perguntar.
- run_blender_python não tem rede/subprocess: se precisar de download/IA,
  use colab_job.
- Ao terminar, resuma: o que foi feito, tris/UVs, e qual o próximo passo.
"""


class AgentSession:
    def __init__(self):
        self.history: list = []          # conteúdo no formato da API (wire)
        self.reference: dict = {}        # {name, path, b64, mime}
        self.reference_sent = False
        self.mode = "step"               # "step" | "full"
        self.auto_approve = False
        self.tool_log: list = []         # entradas para a UI
        self.created_at = time.strftime("%Y-%m-%d %H:%M:%S")

    def log(self, who: str, text: str):
        self.tool_log.append((time.strftime("%H:%M"), who, text))

    def reset(self):
        self.history = []
        self.reference = {}
        self.reference_sent = False
        self.tool_log = []


def _trim(history: list) -> None:
    if len(history) > MAX_HISTORY:
        del history[: len(history) - MAX_HISTORY]


def _slim_images(history: list, keep: int = 2) -> int:
    """Substitui imagens antigas do histórico por placeholders (cada chamada
    re-envia TUDO; imagem já vista não precisa voltar — economiza cota).
    Mantém as `keep` mais recentes (último render + referência)."""
    imgs = []
    for c in reversed(history):
        if not isinstance(c, dict):
            continue
        for i, p in enumerate(c.get("parts") or []):
            if isinstance(p, dict) and "inline_data" in p:
                imgs.append((c, i))
    cortadas = 0
    for c, i in imgs[keep:]:
        c["parts"][i] = {"text": "[imagem antiga removida p/ economizar cota]"}
        cortadas += 1
    return cortadas


def handle_message(session: AgentSession, gem: Gemini, text: str, ctx: dict,
                   on_event=None) -> dict:
    """Roda uma mensagem do usuário até a resposta final do agent.

    on_event(event: str, payload: dict) -> callback opcional p/ a UI
        ("tool_start", "tool_done", "llm_call", "done", "error")
    """
    def emit(event: str, payload: dict | None = None):
        if on_event:
            on_event(event, payload or {})

    text = (text or "").strip()
    if not text:
        return {"reply": "Mensagem vazia.", "calls": 0}

    # ---- mensagem nova do usuário (com referência, se for a primeira vez) ----
    parts: list = []
    ref = session.reference
    if ref.get("b64") and not session.reference_sent:
        parts.append({"image_b64": ref["b64"], "mime": ref.get("mime", "image/png"),
                      "caption": f"Imagem de referência do usuário ({ref.get('name')}). "
                                 "Ela define o personagem-alvo."})
        session.reference_sent = True
    parts.append({"text": text})
    session.history.append(Gemini.user_parts(parts))
    _trim(session.history)
    _slim_images(session.history)

    tools = tools_registry.schemas_for_llm()
    calls = 0
    session.renders_turn = 0   # freio por turno (render_view lê via ctx["session"])
    reply = ""
    try:
        while calls < MAX_TOOL_CALLS:
            emit("llm_call")
            resp = gem.chat(contents=session.history, system=SYSTEM_PROMPT, tools=tools)
            if resp.get("provider"):
                emit("provider", {"provider": resp["provider"]})
            raw = resp.get("raw_content")
            if raw and raw.get("parts"):
                session.history.append(raw)  # mantém thought_signature
            else:
                session.history.append(Gemini.model_parts(resp.get("text", ""), resp.get("tool_calls")))
            tcs = resp.get("tool_calls") or []
            if not tcs:
                reply = resp.get("text") or "(sem texto)"
                break
            for tc in tcs:
                calls += 1
                name, args = tc["name"], tc.get("args") or {}
                label = f"{name} {json.dumps(args, ensure_ascii=False)[:120]}"
                session.log("tool", label)
                emit("tool_start", {"name": name, "label": label})
                # autosave antes de cada mutação
                try:
                    backup = ctx.get("autosave")
                    if backup:
                        backup(name)
                except Exception:
                    pass
                result = tools_registry.run(name, args, ctx)
                session.log("tool" + ("" if result["ok"] else " ✗"),
                            str(result.get("text", ""))[:500])
                emit("tool_done", {"name": name, "ok": result["ok"],
                                   "text": str(result.get("text", ""))[:500]})
                session.history.append(Gemini.function_response(
                    name, {"ok": result["ok"], "result": str(result.get("text", ""))[:6000]}))
                for b64, mime in result.get("images", []):
                    session.history.append(Gemini.user_image(
                        b64, mime, caption=f"Render após {name}. Analise o que você vê e siga."))
                _trim(session.history)
                _slim_images(session.history)
        else:
            reply = (f"⚠️ Bati no limite de {MAX_TOOL_CALLS} ferramentas deste turno "
                     "(a cena está salva por autosave). Escreva \"continue\" que eu retomo "
                     "do mesmo ponto; se eu estava ajustando câmera, da próxima uso "
                     "setup_camera_front.")
    except LLMError as e:
        reply = f"⚠️ Erro na API: {e}"
    session.log("agent", reply)
    emit("done", {"reply": reply, "calls": calls})
    return {"reply": reply, "calls": calls}



