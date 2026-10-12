"""Interface do Bloom Agent no Blender (painel N da 3D View).

Modelo de threads:
- O loop do agent (HTTP Gemini + espera) roda em uma THREAD TRABADA (worker).
- TUDO que toca bpy (tools, autosave, ops) roda na THREAD PRINCIPAL:
  o worker posta chamadas ({token, name, args}) numa fila; um timer de 0.25s
  drena a fila, executa e guarda o resultado num dict; o worker espera por
  ele via Condition. Tokens únicos evitam colisão (a mesma tool pode ser
  chamada 2x numa mensagem).
"""
from __future__ import annotations

import base64
import queue
import threading
import time
import uuid
from typing import NamedTuple
from pathlib import Path

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup

from . import bl
from . import bridge as bridge_mod
from . import keys as keysmod
from . import tools_registry
from .agent_core import AgentSession, handle_message
from .llm import Gemini, GroqClient, LLMError, Router

REAL_RUN = tools_registry.run  # referência p/ o timer (imune a monkeypatch)
BRIDGE_PORT = 8791
MAX_BACKUPS = 20
ADDON_NAME = "bloom_agent"  # nome do package instalado (chave em preferences.addons)


class _Stopped(Exception):
    pass


class _ToolCall(NamedTuple):
    """Mensagem worker->main; os DOIS lados usam atributos."""
    token: str
    name: str
    args: dict


class _State:
    session = AgentSession()
    gem: "Gemini | None" = None
    server: "bridge_mod.BridgeServer | None" = None
    tool_queue: "queue.Queue" = queue.Queue()
    results: dict = {}
    cond = threading.Condition()
    worker: "threading.Thread | None" = None
    running = False
    worker_done = False
    stop_requested = False
    log_lines: list = []
    # estado AO VIVO (o "não sei se travou" morre aqui): fase muda a cada
    # evento e o timer redesenha — o painel sempre mostra o que roda agora
    # e há quantos segundos.
    fase: str = "pronto"          # pronto | pensando | ferramenta
    fase_detalhe: str = ""        # nome da tool / provedor
    t_fase: float = 0.0           # epoch da última troca de fase
    turno_t0: float = 0.0         # início do turno (Elapsed total)
    tool_count: int = 0           # ferramentas usadas no turno (teto 25)
    render_count: int = 0         # renders no turno (teto 3)
    run_config: dict = {"mode": "step", "auto_approve": False, "bank_path": ""}
    root: Path = Path(__file__).resolve().parents[2]  # <root>/agent/bloom_agent/ui.py


def _log(line: str):
    _State.log_lines.append(f"[{time.strftime('%H:%M:%S')}] {line}")
    if len(_State.log_lines) > 400:
        _State.log_lines = _State.log_lines[-300:]


def _fase_evento(event: str, payload: dict | None = None):
    """Atualiza o estado ao vivo a partir dos eventos do agent."""
    payload = payload or {}
    agora = time.time()
    if event == "llm_call":
        _State.fase = "pensando"
        _State.fase_detalhe = ""
        _State.t_fase = agora
    elif event == "provider":
        _State.fase_detalhe = str(payload.get("provider", ""))
    elif event == "tool_start":
        nome = str(payload.get("name", ""))
        _State.fase = "ferramenta"
        _State.fase_detalhe = nome
        _State.t_fase = agora
        _State.tool_count += 1
        if nome == "render_view":
            _State.render_count += 1
    elif event == "tool_done":
        _State.fase = "pensando"
        _State.t_fase = agora
    elif event == "done":
        _State.fase = "pronto"
        _State.fase_detalhe = ""
        _State.t_fase = agora


def _gemini() -> "Router | Gemini":
    """Retorna o ROUTER (Gemini visão + Groq texto, se houver chave gsk_)."""
    if _State.gem is None:
        caminho = keysmod.keys_path(_State.root)
        gem = Gemini(caminho)
        gem.on_log = _log  # esperas de cota / trocas de modelo no painel
        groq = None
        try:
            if keysmod.load(caminho).get("groq"):
                groq = GroqClient(caminho)
                groq.on_log = _log
                _log(f"orquestrador Groq ativo ({groq.model})")
        except Exception:
            groq = None
        _State.gem = Router(gem, groq)
        _State.gem.on_log = _log
    return _State.gem


def _server() -> bridge_mod.BridgeServer:
    if _State.server is None:
        _State.server = bridge_mod.BridgeServer(_State.root, port=BRIDGE_PORT)
    return _State.server


def _props():
    # as propriedades são registradas em bpy.types.Scene (ver __init__.register);
    # ler de preferences.addons dava sempre None (o AddonPreferences não tem
    # bloom_props) -> painel mostrava "propriedades não registradas".
    scn = getattr(bpy.context, "scene", None)
    if scn is None:
        return None
    return getattr(scn, "bloom_props", None)


def _props_or(props):
    return props if props is not None else _props()


# ---------------------------------------------------------------------------
# propriedades
# ---------------------------------------------------------------------------

class BloomProperties(PropertyGroup):
    user_input: StringProperty(default="", description="Mensagem para o agent")
    log_text: StringProperty(default="")
    mode: EnumProperty(
        items=[("step", "Passo a passo", "Faça só o estágio pedido e espere a próxima instrução"),
               ("full", "Pleno", "Roda o fluxo completo (corpo→rig→UV→textura→peças→export) com gates")],
        default="step")
    auto_approve: BoolProperty(default=False, description="No modo pleno: não parar em gates de aprovação")
    ref_image: StringProperty(default="", subtype="FILE_PATH",
                              description="Imagem de referência (foto do personagem-alvo)")
    keys_text: StringProperty(default="",
        description="Chave(s), uma por linha: AIza... = Gemini (visao) | gsk_... = Groq (texto/visor gratuito em console.groq.com)")
    bank_path: StringProperty(default="", subtype="FILE_PATH",
                              description="Pasta do Asset Bank no seu PC")
    ngrok_url_text: StringProperty(default="")
    status_text: StringProperty(default="")
    act_collect_id: StringProperty(default="")


# ---------------------------------------------------------------------------
# execução na main thread
# ---------------------------------------------------------------------------

def _autosave_main(label: str) -> dict:
    backups = _State.root / "stage_backups"
    try:
        backups.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        safe = "".join(c for c in (label or "step")[:20] if c.isalnum() or c in ("_",)) or "step"
        target = backups / f"step_{ts}_{safe}.blend"
        bl.save_blend(target)
        files = sorted(backups.glob("step_*.blend"))
        for old in files[:-MAX_BACKUPS]:
            try:
                old.unlink()
            except OSError:
                pass
        return {"ok": True, "text": f"backup: {target.name}", "images": []}
    except Exception as e:
        return {"ok": True, "text": f"(autosave falhou: {e})", "images": []}


def _ensure_timer():
    """Garante que o timer da main thread existe (se ele morrer uma vez,
    o Blender o desregistra — aqui a gente recria quando precisar dele)."""
    try:
        if not bpy.app.timers.is_registered(_main_timer):
            bpy.app.timers.register(_main_timer, first_interval=0.1)
    except (ValueError, RuntimeError):
        pass


def _main_timer() -> float:
    try:
        # 1) drena a fila de tools (aqui, na main thread)
        while True:
            try:
                call = _State.tool_queue.get_nowait()
            except queue.Empty:
                break
            try:
                if call.name == "__autosave__":
                    res = _autosave_main(call.args.get("label", "step"))
                else:
                    res = REAL_RUN(call.name, call.args, _ctx())
            except Exception as e:
                res = {"ok": False, "text": f"erro interno: {type(e).__name__}: {e}", "images": []}
            with _State.cond:
                _State.results[call.token] = res
                _State.cond.notify_all()
        # 2) status da UI
        props = _props()
        if props is not None:
            _refresh_status(props)
        # 3) heartbeat: força redraw da viewport p/ o status TICKAR ao vivo
        if _State.running:
            for w in bpy.context.window_manager.windows:
                for area in w.screen.areas:
                    if area.type == "VIEW_3D":
                        area.tag_redraw()
        # 4) limpeza pós-worker
        if not _State.running and _State.worker_done:
            _State.worker_done = False
            _State.worker = None
            _State.stop_requested = False
    except Exception as e:
        # o timer NUNCA pode morrer: um erro aqui desregistra ele no Blender
        try:
            _log(f"⚠️ timer: {type(e).__name__}: {e}")
        except Exception:
            pass
    return 0.25


def _ctx() -> dict:
    cfg = _State.run_config
    bank = cfg.get("bank_path") or ""
    return {
        "root": _State.root,
        "bank_dir": Path(bank) if bank else None,
        "server": _State.server,
        "session": _State.session.__dict__,
        "autosave": None,  # o worker injeta sua própria autosave (via fila)
    }


def _dispatch(name: str, args: dict, timeout: float = 3600.0) -> dict:
    """Worker -> main: posta a chamada e bloqueia até o resultado."""
    if _State.stop_requested:
        raise _Stopped()
    token = uuid.uuid4().hex
    call = _ToolCall(token=token, name=name, args=args or {})
    deadline = time.time() + timeout
    with _State.cond:
        _State.tool_queue.put(call)
        while token not in _State.results:
            if _State.stop_requested or time.time() > deadline:
                break
            _State.cond.wait(timeout=0.5)
        if token in _State.results:
            return _State.results.pop(token)
    raise _Stopped()


# ---------------------------------------------------------------------------
# worker (thread)
# ---------------------------------------------------------------------------

def _run_agent(message: str):
    try:
        _State.running = True
        _State.turno_t0 = time.time()
        _State.t_fase = time.time()
        _State.fase = "pensando"
        _State.tool_count = 0
        _State.render_count = 0
        gem = _gemini()
        if not gem.status()["keys"]:
            raise LLMError("Nenhuma chave Gemini configurada. Adicione no painel "
                           "(a chave do AI Studio grátis basta).")
        cfg = _State.run_config
        if cfg.get("bank_path"):
            _bank_save(cfg["bank_path"])
        _State.session.mode = cfg.get("mode", "step")
        _State.session.auto_approve = cfg.get("auto_approve", False)

        def on_event(event, payload=None):
            payload = payload or {}
            _fase_evento(event, payload)
            if event == "tool_start":
                _log(f"⚙ {payload.get('label', payload.get('name', ''))}")
            elif event == "tool_done":
                mark = "✓" if payload.get("ok") else "✗"
                _log(f"{mark} {str(payload.get('text', ''))[:200]}")
            elif event == "llm_call":
                _log("… pensando")
            elif event == "provider":
                _log(f"🧠 {payload.get('provider', '?')}")
            elif event == "done":
                _log(f"agent: {str(payload.get('reply', ''))[:600]}")

        ctx = _ctx()
        # autosave também passa pela main (é bpy.ops)
        def autosave_via_main(label: str) -> str:
            return _dispatch("__autosave__", {"label": label}).get("text", "")
        ctx["autosave"] = autosave_via_main

        # o handle_message chama tools_registry.run; durante o worker,
        # redirecionamos para a main thread
        def guarded_run(name, args, ctx_):
            return _dispatch(name, args)

        tools_registry.run = guarded_run
        try:
            handle_message(_State.session, gem, message, ctx, on_event=on_event)
        finally:
            tools_registry.run = REAL_RUN
    except _Stopped:
        _log("■ parado pelo usuário.")
    except LLMError as e:
        _log(f"⚠️ {e}")
    except Exception as e:
        _log(f"⚠️ erro: {type(e).__name__}: {e}")
    finally:
        _State.running = False
        _State.fase = "pronto"
        _State.fase_detalhe = ""
        with _State.cond:
            _State.worker_done = True
            _State.cond.notify_all()


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def _bank_prefs_path():
    try:
        return _State.root / "ui_prefs.json"
    except Exception:
        return None


def _bank_autodetect() -> str:
    """Onde esta o Asset Bank? Salvo > J:\\3d-Create\\assets > vazio."""
    import json as _json
    pp = _bank_prefs_path()
    if pp and pp.exists():
        try:
            salvo = _json.loads(pp.read_text(encoding="utf-8")).get("bank_path", "")
            if salvo and Path(salvo).exists():
                return salvo
        except Exception:
            pass
    for cand in ("J:\\3d-Create\\assets", "J:/3d-Create/assets"):
        if Path(cand).exists():
            return cand
    return ""


def _bank_save(caminho: str):
    import json as _json
    pp = _bank_prefs_path()
    if not pp or not caminho:
        return
    try:
        dados = {}
        if pp.exists():
            dados = _json.loads(pp.read_text(encoding="utf-8"))
        dados["bank_path"] = caminho
        pp.write_text(_json.dumps(dados, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    except Exception:
        pass


def _refresh_status(props: "BloomProperties"):

    if not props.bank_path:
        auto = _bank_autodetect()
        if auto:
            props.bank_path = auto
    bits = []
    try:
        from . import __version__
        bits.append("v" + __version__)
        st = _gemini().status()
        bits.append(st["model"])
        bits.append(f"{len(st['keys'])} chave(s)")
        gq = st.get("groq")
        if gq:
            bits.append(f"groq:{gq['model'].split('-')[0]}x{len(gq['keys'])}")
        if st["cooldown_seconds"] > 0:
            bits.append(f"cooldown ~{st['cooldown_seconds']}s")
    except Exception:
        bits.append("sem gemini")
    if _State.server is not None and _State.server.is_running():
        bits.append("ponte ON")
        ngrok = bridge_mod.ngrok_public_url(BRIDGE_PORT)
        props.ngrok_url_text = ngrok or f"(rode: ngrok http {BRIDGE_PORT})"
    else:
        bits.append("ponte OFF")
        props.ngrok_url_text = ""
    if _State.running:
        agora = time.time()
        el = int(agora - _State.t_fase) if _State.t_fase else 0
        tot = int(agora - _State.turno_t0) if _State.turno_t0 else 0
        if _State.fase == "ferramenta":
            bits.append(f"🔧 {_State.fase_detalhe or 'tool'} ha {el}s")
        elif _State.fase == "pensando":
            quem = f" ({_State.fase_detalhe})" if _State.fase_detalhe else ""
            bits.append(f"🧠 pensando{quem} ha {el}s")
        else:
            bits.append("⚙ trabalhando…")
        bits.append(f"tools {_State.tool_count}/25 · renders {_State.render_count}/3 · {tot}s")
        if tot >= 75:
            bits.append("⚠ lento — 'Parar' disponivel")
    else:
        bits.append("🟢 pronto")
    props.status_text = " | ".join(bits)
    props.log_text = "\n".join(_State.log_lines[-120:])


# ---------------------------------------------------------------------------
# ações
# ---------------------------------------------------------------------------

def _action_send(props):
    props = _props_or(props)
    msg = props.user_input.strip()
    if not msg or _State.running:
        return
    if props.ref_image:
        p = Path(props.ref_image)
        if p.is_file():
            mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "webp": "image/webp", "bmp": "image/bmp"}.get(
                        p.suffix.lower().lstrip("."), "image/png")
            data = p.read_bytes()
            _State.session.reference = {
                "name": p.name, "path": str(p),
                "b64": base64.b64encode(data).decode("ascii"), "mime": mime}
            _State.session.reference_sent = False
            _log(f"referência: {p.name} ({len(data) // 1024} KB)")
    # lê tudo que é bpy.props na MAIN (aqui) antes de abrir a thread
    _State.run_config = {
        "mode": props.mode,
        "auto_approve": props.auto_approve,
        "bank_path": props.bank_path,
    }
    _State.stop_requested = False
    props.user_input = ""
    _State.running = True
    _log(f"▶ {msg}")
    _State.worker = threading.Thread(target=_run_agent, args=(msg,), daemon=True)
    _State.worker.start()
    # feedback IMEDIATO + timer garantido (não depende de ele estar vivo)
    _ensure_timer()
    _refresh_status(props)


def _action_reset(props):
    props = _props_or(props)
    _State.session.reset()
    _State.log_lines.clear()
    _log("chat reiniciado (cena e referência continuam).")
    props.log_text = ""


def _action_clear_log(props):
    props = _props_or(props)
    _State.log_lines.clear()
    props.log_text = ""


def _action_add_key(props):
    props = _props_or(props)
    try:
        path = keysmod.keys_path(_State.root)
        data = keysmod.load(path)
        added, added_g, erros = 0, 0, []
        for line in props.keys_text.splitlines():
            line = line.strip()
            if not line or line.startswith(("SUBSTITUA", "cole_sua")):
                continue
            try:
                if line.startswith("gsk_"):        # Groq (orquestrador texto)
                    keysmod.add_groq_key(data, line)
                    added_g += 1
                else:                               # Gemini (visão)
                    keysmod.add_key(data, line)
                    added += 1
            except ValueError as e:
                erros.append(f"· {e}")
        if added or added_g:   # groq sozinha TAMBÉM grava (bug: era descartada)
            keysmod.save(path, data)
        _State.gem = None      # Router renasce e monta o GroqClient na próxima
        st = _gemini().status()
        msg = f"chaves: +{added} gemini; total {len(st['keys'])}"
        if added_g:
            msg += f"; +{added_g} groq; total {len((st.get('groq') or {}).get('keys', []))}"
        if erros:
            msg += f"; {len(erros)} recusada(s):\n" + "\n".join(erros[:4])
        _log(msg)
        props.keys_text = ""
        _refresh_status(props)
    except Exception as e:
        _log(f"⚠️ chaves: {e}")


def _action_scan(props):
    props = _props_or(props)
    bank = Path(props.bank_path) if props.bank_path else None
    res = REAL_RUN("asset_scan", {}, {**_ctx(), "bank_dir": bank})
    _log(f"asset_scan: {res['text'][:300]}")


def _action_bridge_toggle(props):
    props = _props_or(props)
    srv = _server()
    if srv.is_running():
        srv.stop()
        _log("ponte parada.")
    else:
        try:
            srv.start()
            _log(f"ponte em {srv.local_url} — rode: ngrok http {BRIDGE_PORT}")
        except OSError as e:
            _log(f"⚠️ ponte: {e}")
    _refresh_status(props)


def _action_bridge_refresh(props):
    props = _props_or(props)
    srv = _server()
    url = bridge_mod.ngrok_public_url(BRIDGE_PORT)
    if url:
        jobs = sorted(srv.jobs_root.iterdir()) if srv.jobs_root.is_dir() else []
        for j in jobs:
            if (j / "job.json").is_file():
                srv.refresh_job_url(j.name)
        _log(f"ngrok: {url} ({len(jobs)} job(s) atualizados)")
        props.ngrok_url_text = url
    else:
        _log(f"ngrok não detectado. Rode: ngrok http {BRIDGE_PORT}")


def _action_test_job(props):
    props = _props_or(props)
    srv = _server()
    if not srv.is_running():
        _log("Inicie a ponte primeiro (botão acima).")
        return
    job_id = srv.create_job("echo", {"nota": "teste de bridge"}, None)
    url = bridge_mod.ngrok_public_url(BRIDGE_PORT)
    _log(f"job teste {job_id} criado. base_url: {url or f'RODE ngrok http {BRIDGE_PORT}'}")
    _log("Abra colab/test_bridge.ipynb, cole job_id + base_url, execute, depois clique Coletar.")


def _action_collect(props):
    props = _props_or(props)
    job_id = props.act_collect_id.strip()
    if not job_id:
        _log("Informe o job_id para coletar.")
        return
    res = REAL_RUN("colab_collect", {"job_id": job_id}, _ctx())
    _log(f"coletar {job_id}: {res['text'][:400]}")
    if res["ok"]:
        props.act_collect_id = ""


def _action_restore(props):
    props = _props_or(props)
    backups = _State.root / "stage_backups"
    files = sorted(backups.glob("step_*.blend")) if backups.is_dir() else []
    if not files:
        _log("Nenhum backup ainda (são criados a cada tool do agent).")
        return
    try:
        bpy.ops.wm.open_mainfile(filepath=str(files[-1]))
        _log(f"restaurado {files[-1].name}")
    except Exception as e:
        _log(f"⚠️ restore: {e}")


# ---------------------------------------------------------------------------
# operadores + painel
# ---------------------------------------------------------------------------

def _label(parent, text: str, icon: str | None = None):
    """label com ícone OPCIONAL — ícone inexistente no Blender da pessoa não
    pode derrubar o desenho do painel (ex.: 'CHAT' não existe no 5.x)."""
    if icon:
        try:
            parent.label(text=text, icon=icon)
            return
        except TypeError:
            pass
    try:
        parent.label(text=text)
    except Exception:
        pass


def _safe_box(layout, fn, *args):
    """Desenha uma seção do painel; se ela levantar, mostra o erro DENTRO do
    painel (em vez de cortar o resto silenciosamente)."""
    box = layout.box()
    try:
        fn(box, *args)
    except Exception as e:
        b2 = box.box()
        try:
            b2.alert = True
        except Exception:
            pass
        _label(b2, f"⚠️ seção com erro: {type(e).__name__}: {e}")


class BLOOM_OT_Send(Operator):
    bl_idname = "bloom.send"
    bl_label = "Enviar"

    def execute(self, context):
        _action_send(_props())
        return {"FINISHED"}


class BLOOM_OT_Stop(Operator):
    bl_idname = "bloom.stop"
    bl_label = "Parar"
    bl_description = "Pára o agent na próxima pausa"

    def execute(self, context):
        _State.stop_requested = True
        _log("stop solicitado.")
        return {"FINISHED"}


class BLOOM_OT_Reset(Operator):
    bl_idname = "bloom.reset"
    bl_label = "Limpar chat"

    def execute(self, context):
        _action_reset(_props())
        return {"FINISHED"}


class BLOOM_OT_ClearLog(Operator):
    bl_idname = "bloom.clear_log"
    bl_label = "Limpar log"

    def execute(self, context):
        _action_clear_log(_props())
        return {"FINISHED"}


class BLOOM_OT_CopyLog(Operator):
    bl_idname = "bloom.copy_log"
    bl_label = "Copiar log"
    bl_description = "Copia o log inteiro para a área de transferência (cole na conversa)"

    def execute(self, context):
        context.window_manager.clipboard = "\n".join(_State.log_lines)
        self.report({"INFO"}, f"log copiado ({len(_State.log_lines)} linha(s))")
        return {"FINISHED"}


class BLOOM_OT_AddKey(Operator):
    bl_idname = "bloom.add_key"
    bl_label = "Adicionar chave(s)"

    def execute(self, context):
        _action_add_key(_props())
        return {"FINISHED"}


class BLOOM_OT_ScanBank(Operator):
    bl_idname = "bloom.scan_bank"
    bl_label = "Varrer pasta"

    def execute(self, context):
        _action_scan(_props())
        return {"FINISHED"}


class BLOOM_OT_BridgeToggle(Operator):
    bl_idname = "bloom.bridge_toggle"
    bl_label = "Iniciar/parar ponte"

    def execute(self, context):
        _action_bridge_toggle(_props())
        return {"FINISHED"}


class BLOOM_OT_BridgeRefresh(Operator):
    bl_idname = "bloom.bridge_refresh"
    bl_label = "Atualizar URL"

    def execute(self, context):
        _action_bridge_refresh(_props())
        return {"FINISHED"}


class BLOOM_OT_TestJob(Operator):
    bl_idname = "bloom.test_job"
    bl_label = "Job de teste"

    def execute(self, context):
        _action_test_job(_props())
        return {"FINISHED"}


class BLOOM_OT_CollectJob(Operator):
    bl_idname = "bloom.collect_job"
    bl_label = "Coletar"

    def execute(self, context):
        _action_collect(_props())
        return {"FINISHED"}


class BLOOM_OT_RestoreLast(Operator):
    bl_idname = "bloom.restore_last"
    bl_label = "Restaurar último backup"
    bl_description = "Reabre o último .blend de etapa (perde edições não salvas após ele)"

    def execute(self, context):
        _action_restore(_props())
        return {"FINISHED"}


class BLOOM_PT_Main(Panel):
    bl_idname = "BLOOM_PT_Main"
    bl_label = "🌸 Bloom Agent"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Bloom"

    def draw(self, context):
        layout = self.layout
        props = _props()
        if props is None:
            layout.label(text="propriedades não registradas")
            return
        txt = props.status_text
        icone = "INFO"
        if "🔧" in txt or "🧠" in txt or "⚙" in txt:
            icone = "TIME"
        elif "⚠" in txt or "✗" in txt:
            icone = "ERROR"
        elif "pronto" in txt:
            icone = "CHECKMARK"
        try:
            layout.label(text=txt, icon=icone)
        except TypeError:
            layout.label(text=txt)
        if _State.running:
            n = max(0, min(_State.tool_count, 25))
            layout.label(text="▮" * n + "▯" * (25 - n) + "  ferramentas do turno")
        _safe_box(layout, self._sec_chat, props)
        _safe_box(layout, self._sec_log, props)
        _safe_box(layout, self._sec_keys, props)
        _safe_box(layout, self._sec_bank, props)
        _safe_box(layout, self._sec_bridge, props)
        _safe_box(layout, self._sec_backups, props)

    # ---- seções (cada uma pode falhar sem matar as demais) ----

    def _sec_chat(self, box, props):
        _label(box, "Chat", "CHAT")
        box.prop(props, "mode", expand=True)
        if props.mode == "full":
            box.prop(props, "auto_approve", toggle=True, text="Auto-aprovar gates")
        box.prop(props, "user_input")
        row = box.row(align=True)
        row.operator("bloom.send")
        row.operator("bloom.stop")
        row.operator("bloom.reset")
        box.prop(props, "ref_image")
        _label(box, "A referência vai com a PRÓXIMA mensagem.", "IMAGE_DATA")

    def _sec_log(self, box, props):
        _label(box, "Log", "TEXT")
        lines = _State.log_lines[-14:]
        if not lines:
            _label(box, "(sem mensagens ainda)")
        for ln in lines:
            row = box.row()
            row.scale_y = 0.85
            row.label(text=ln[:120])
        row = box.row(align=True)
        row.operator("bloom.copy_log", icon="COPYDOWN")
        row.operator("bloom.clear_log", icon="X")

    def _sec_keys(self, box, props):
        _label(box, "Chaves Gemini (local, fora do git)", "KEYS")
        box.prop(props, "keys_text")
        box.operator("bloom.add_key")

    def _sec_bank(self, box, props):
        _label(box, "Asset Bank (pasta local)", "FILE_FOLDER")
        box.prop(props, "bank_path")
        box.operator("bloom.scan_bank")

    def _sec_bridge(self, box, props):
        _label(box, f"Ponte Colab (porta {BRIDGE_PORT})", "INTERNET")
        row = box.row(align=True)
        row.operator("bloom.bridge_toggle")
        row.operator("bloom.bridge_refresh")
        _label(box, props.ngrok_url_text or "ponte OFF", "URL")
        box.operator("bloom.test_job")
        row = box.row(align=True)
        row.prop(props, "act_collect_id", text="job_id")
        row.operator("bloom.collect_job")
        _label(box, "notebook: colab/test_bridge.ipynb", "FILE_TEXT")

    def _sec_backups(self, box, props):
        _label(box, "Backups de etapa", "TIME")
        box.operator("bloom.restore_last")


_CLASSES = [
    BloomProperties,
    BLOOM_OT_Send, BLOOM_OT_Stop, BLOOM_OT_Reset, BLOOM_OT_ClearLog, BLOOM_OT_CopyLog,
    BLOOM_OT_AddKey, BLOOM_OT_ScanBank, BLOOM_OT_BridgeToggle,
    BLOOM_OT_BridgeRefresh, BLOOM_OT_TestJob, BLOOM_OT_CollectJob, BLOOM_OT_RestoreLast,
    BLOOM_PT_Main,
]

