"""Handlers das tools expostas ao LLM (rodam DENTRO do Blender).

Convenção: cada função recebe (args, ctx) e devolve
    {"ok": bool, "text": str, "images": [(b64, mime), ...]}

ctx fornecido pela UI:
    root      -> raiz do projeto (Path)
    bank_dir  -> pasta do asset bank (Path)
    server    -> BridgeServer ou None
    session   -> dict da sessão do agent (referência, etc.)
    autosave  -> callable(label) -> caminho do backup
"""
from __future__ import annotations

import base64
import io
import json
import re
import time
import traceback
from contextlib import redirect_stdout
from pathlib import Path

from .. import bl
from .. import bridge as bridge_mod

# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------

_FORBIDDEN = [
    (r"\bsubprocess\b", "subprocess"),
    (r"\bos\.system\b", "os.system"),
    (r"\bos\.popen\b", "os.popen"),
    (r"\bsocket\b", "socket"),
    (r"\bshutil\.rmtree\b", "shutil.rmtree"),
    (r"\brequests\b", "requests"),
    (r"\burllib\b", "urllib"),
    (r"\bhttp\.client\b", "http.client"),
    (r"\bctypes\b", "ctypes"),
    (r"\beval\s*\(", "eval()"),
    (r"\bexec\s*\(", "exec()"),
]


def _guard_python(code: str) -> str | None:
    for pat, label in _FORBIDDEN:
        if re.search(pat, code):
            return (f"Código bloqueado pelo guard (usando {label!r}). "
                    "Reescreva sem I/O de rede/processos: só bpy/mathutils/path de arquivo local.")
    return None


def _ok(text: str, images=None) -> dict:
    return {"ok": True, "text": text, "images": images or []}


def _fail(text: str) -> dict:
    return {"ok": False, "text": text, "images": []}


def _ctx_bank(ctx) -> Path:
    p = ctx.get("bank_dir")
    return Path(p) if p else (Path(ctx["root"]) / "assets" / "bank")


def _read_file_b64(path: Path) -> tuple[str, str] | None:
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp", "bmp": "image/bmp"}.get(path.suffix.lower().lstrip("."))
    if not mime:
        return None
    return base64.b64encode(path.read_bytes()).decode("ascii"), mime


# ---------------------------------------------------------------------------
# tools: cena
# ---------------------------------------------------------------------------

def list_scene(args: dict, ctx: dict) -> dict:
    return _ok(bl.objects_tree())


def scene_stats(args: dict, ctx: dict) -> dict:
    return _ok(json.dumps(bl.poly_stats(), ensure_ascii=False))


def create_object(args: dict, ctx: dict) -> dict:
    ob = bl.create_primitive(
        args.get("kind", "cube"),
        args.get("name"),
        tuple(args.get("location", [0, 0, 0])),
        tuple(args.get("scale", [1, 1, 1])),
    )
    return _ok(f"Criado {ob.name} ({ob.type}).")


def delete_object(args: dict, ctx: dict) -> dict:
    bl.delete_object(args["name"])
    return _ok(f"Removido {args['name']}.")


def run_blender_python(args: dict, ctx: dict) -> dict:
    code = (args.get("code") or "").strip()
    if not code:
        return _fail("Parâmetro 'code' vazio.")
    problem = _guard_python(code)
    if problem:
        return _fail(problem)
    buf = io.StringIO()
    import mathutils  # noqa: F401
    import math  # noqa: F401
    ns = {
        "bpy": bl.bpy,
        "context": bl.bpy.context,
        "math": math,
        "mathutils": mathutils,
        "bmesh": __import__("bmesh"),
        "path": Path,
        "project_root": Path(ctx["root"]),
    }
    try:
        with redirect_stdout(buf):
            exec(compile(code, "<bloom_agent>", "exec"), ns)  # noqa: S102 (guard acima)
        out = buf.getvalue().strip()
        return _ok((f"Executado ok.\nSaída: {out[:4000]}" if out else "Executado ok. (sem saída)"))
    except Exception as e:  # devolve o erro pro LLM corrigir
        return _fail(f"Erro ao executar:\n{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}")


def render_view(args: dict, ctx: dict) -> dict:
    size = int(args.get("size", 512))
    stamp = time.strftime("%H%M%S")
    out = Path(ctx["root"]) / "jobs" / "renders" / f"view_{stamp}.png"
    b64 = bl.quick_render(out, size=size, from_viewport=True)
    return _ok(f"Render salvo em {out}.", images=[(b64, "image/png")])


def reference_info(args: dict, ctx: dict) -> dict:
    ref = (ctx.get("session") or {}).get("reference") or {}
    if not ref.get("b64"):
        return _fail("Nenhuma imagem de referência definida (use o botão no painel).")
    return _ok(f"Referência ativa: {ref.get('name')} ({ref.get('mime')}), "
               f"{len(ref['b64']) // 1024} KB em base64. Ela está visível na conversa.")


# ---------------------------------------------------------------------------
# tools: asset bank
# ---------------------------------------------------------------------------

def asset_scan(args: dict, ctx: dict) -> dict:
    bank = _ctx_bank(ctx)
    entries = bl.list_bank_files(bank)
    index = bank / "index.json"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(json.dumps({"bank": str(bank), "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                                 "assets": entries}, indent=2, ensure_ascii=False), encoding="utf-8")
    if not entries:
        return _ok(f"Pasta vazia ou inexistente: {bank}. Defina o caminho certo no painel.")
    lines = [f"{e['id']} [{e['type']}] tags={','.join(e['tags']) or '-'} {e['size'] // 1024}KB"
             for e in entries]
    return _ok(f"{len(entries)} assets indexados em {bank}:\n" + "\n".join(lines[:200]))


def asset_import(args: dict, ctx: dict) -> dict:
    bank = _ctx_bank(ctx)
    name = (args.get("file") or "").strip()
    target = args.get("name")
    # resolve por id/rel exato ou por stem
    candidate = None
    direct = (bank / name)
    if direct.is_file():
        candidate = direct
    else:
        entries = bl.list_bank_files(bank)
        for e in entries:
            if e["id"] == name or e["name"] == name or e["rel"] == name:
                candidate = bank / e["rel"]
                break
        if candidate is None:
            # busca fuzzy por substring nas tags/nome
            hits = [e for e in entries if name.lower() in (e["name"] + " " + " ".join(e["tags"])).lower()]
            if len(hits) == 1:
                candidate = bank / hits[0]["rel"]
            elif hits:
                return _fail(f"Vários assets contêm {name!r}: " +
                             ", ".join(h["id"] for h in hits[:10]) + ". Informe o nome exato.")
    if candidate is None:
        return _fail(f"Asset {name!r} não encontrado em {bank}. Rode asset_scan primeiro.")
    bl.import_asset(candidate, target)
    return _ok(f"Importado {candidate.name} de {candidate}")


# ---------------------------------------------------------------------------
# tools: colab
# ---------------------------------------------------------------------------

def colab_job(args: dict, ctx: dict) -> dict:
    server = ctx.get("server")
    if server is None or not server.is_running():
        return _fail("Ponte local não está ativa. O usuário precisa iniciar a ponte no painel "
                     "(botão 'Iniciar ponte').")
    kind = (args.get("kind") or "echo").strip()
    params = args.get("params") or {}
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except ValueError:
            params = {"raw": params}
    files = {}
    ref = (ctx.get("session") or {}).get("reference") or {}
    if ref.get("b64") and ref.get("name"):
        files[ref["name"]] = base64.b64decode(ref["b64"])
    job_id = server.create_job(kind, params, files or None)
    job_dir = server.jobs_root / job_id
    info = server.job_info(job_id)
    ngrok = info.get("base_url")
    if ngrok:
        where = ngrok
    else:
        where = ("ngrok NÃO detectado — o usuário precisa rodar `ngrok http "
                 f"{server.port}` no PC e clicar em 'Atualizar URL'. "
                 "Alternativa: modo manual (Drive).")
    input_dir = job_dir / "input"
    inputs = [f.name for f in sorted(input_dir.iterdir())] if input_dir.is_dir() else []
    return _ok(
        f"Job {job_id} criado (kind={kind}).\n"
        f"Arquivos de entrada: {', '.join(inputs) if inputs else 'nenhum'}\n"
        f"O usuário deve abrir colab/test_bridge.ipynb (ou o notebook do kind) com:\n"
        f"  job_id = {job_id!r}\n  base_url = {where!r}\n"
        f"Quando terminar, clique em 'Coletar resultados'.\n"
        f"Pasta local: {job_dir}"
    )


def colab_collect(args: dict, ctx: dict) -> dict:
    server = ctx.get("server")
    if server is None:
        return _fail("Ponte local indisponível.")
    job_id = (args.get("job_id") or "").strip()
    try:
        info = server.job_info(job_id)
    except bridge_mod.BridgeError as e:
        return _fail(str(e))
    res = info.get("results", [])
    if not res:
        status = "aguardando o Colab" if not info.get("complete") else "concluído sem resultados"
        return _ok(f"Job {job_id}: {status}.\nParams: {json.dumps(info.get('params', {}), ensure_ascii=False)[:500]}")
    lines = []
    for r in res:
        f = server.result_file(job_id, r["name"])
        lines.append(f"- {f} ({r['bytes'] // 1024} KB)")
    extra = ""
    if info.get("complete"):
        extra = f"\ncomplete: {json.dumps(info['complete'], ensure_ascii=False)[:500]}"
    return _ok(f"Job {job_id} tem {len(res)} resultado(s):\n" + "\n".join(lines) + extra)
