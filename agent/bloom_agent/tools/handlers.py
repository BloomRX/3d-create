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
from .. import rig_profiles

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
        "scene": bl.bpy.context.scene,
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
        dica = ""
        if "has no attribute 'scene'" in f"{type(e).__name__}: {e}":
            dica = ("\nDICA: bpy.scene NAO existe. Use a variavel `scene` "
                    "(ja disponivel) ou bpy.context.scene.")
        return _fail(f"Erro ao executar:\n{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}{dica}")


MAX_RENDERS_PER_TURN = 3   # freio anti-loop de câmera (queimou um turno inteiro)


def render_view(args: dict, ctx: dict) -> dict:
    sess = ctx.get("session") or {}
    feitos = int(sess.get("renders_turn", 0))
    if feitos >= MAX_RENDERS_PER_TURN:
        return _fail(f"Limite de {MAX_RENDERS_PER_TURN} renders por turno é FIXO "
                     f"({feitos} usados) — edições de geometria NÃO resetam o contador. "
                     "Descreva o resultado pelo que já viu, conclua o turno e espere "
                     "o usuário (o turno seguinte recomeça os renders).")
    sess["renders_turn"] = feitos + 1
    size = int(args.get("size", 512))
    stamp = time.strftime("%H%M%S")
    out = Path(ctx["root"]) / "jobs" / "renders" / f"view_{stamp}.png"
    # com câmera na cena (setup_camera_front cria a BloomCam), renderiza ELA —
    # determinístico. Renderizar a viewport do usuário era a raiz do loop de
    # câmera: o agent via um ângulo arbitrário e brigava pra "consertar".
    tem_cam = bl.bpy.context.scene.camera is not None
    b64 = bl.quick_render(out, size=size, from_viewport=not tem_cam)
    via = "câmera BloomCam" if tem_cam else "viewport do usuário"
    return _ok(f"Render {sess['renders_turn']}/{MAX_RENDERS_PER_TURN} do turno ({via}) "
               f"salvo em {out}.", images=[(b64, "image/png")])


def setup_camera_front(args: dict, ctx: dict) -> dict:
    """Câmera frontal DETERMINÍSTICA: enquadra as malhas pela bounding box
    (lente 50mm, margem 25%) + luz básica se a cena não tiver nenhuma."""
    bpy = bl.bpy
    from mathutils import Vector
    from math import atan, radians, tan

    malhas = [o for o in bpy.data.objects if o.type == "MESH"
              and not o.name.startswith(("BLOOM_REF", "Outline"))]
    if not malhas:
        return _fail("Nenhuma malha para enquadrar.")
    bpy.context.view_layer.update()
    cantos = [o.matrix_world @ Vector(c) for o in malhas for c in o.bound_box]
    vmin = Vector((min(c.x for c in cantos), min(c.y for c in cantos),
                   min(c.z for c in cantos)))
    vmax = Vector((max(c.x for c in cantos), max(c.y for c in cantos),
                   max(c.z for c in cantos)))
    centro = (vmin + vmax) / 2
    altura = max(0.5, vmax.z - vmin.z)
    largura = max(0.3, vmax.x - vmin.x)
    velha = bpy.data.objects.get("BloomCam")
    if velha:
        bpy.data.objects.remove(velha, do_unlink=True)
    cam_data = bpy.data.cameras.new("BloomCam")
    cam_data.lens = 50
    cam = bpy.data.objects.new("BloomCam", cam_data)
    bpy.context.collection.objects.link(cam)
    half_fov = atan(18.0 / 50.0)  # sensor 36mm
    dist = (max(altura, largura * 1.2) / (2 * tan(half_fov))) * 1.25
    cam.location = (centro.x, centro.y - dist, centro.z)
    cam.rotation_euler = (centro - cam.location).to_track_quat("-Z", "Y").to_euler()
    if not any(o.type == "LIGHT" for o in bpy.data.objects):
        sol = bpy.data.lights.new("BloomSol", "SUN")
        sol.energy = 3.0
        luz = bpy.data.objects.new("BloomSol", sol)
        luz.rotation_euler = (radians(50), 0, radians(20))
        bpy.context.collection.objects.link(luz)
    cena = bpy.context.scene
    cena.camera = cam
    return _ok(f"Câmera frontal a {dist:.2f} m enquadra {altura:.2f} m "
               f"(centro z={centro.z:.2f}, base z={vmin.z:.2f}). "
               "Agora UM render_view para ver o personagem inteiro.")


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


# ---------------------------------------------------------------------------
# tools: M1 — corpo, proporções, rig, export
# ---------------------------------------------------------------------------

_BODY_HINTS = ("bodiez", "base_mesh", "base-mesh", "basebody", "base_body",
               "corpo", "female_base", "male_base", "modular")


def _find_body_in_bank(bank: Path, gender: str) -> Path | None:
    try:
        entries = bl.list_bank_files(bank)
    except Exception:
        return None
    pref = {"female": ("female", "fem", "mulher"), "male": ("male", "masc", "homem")}.get(
        gender, ())
    scored = []
    for e in entries:
        if e.get("type") != "blend":
            continue
        hay = (e["name"] + " " + " ".join(e.get("tags", []))).lower()
        score = sum(2 for h in _BODY_HINTS if h in hay)
        if not score:
            continue
        if pref and any(h in hay for h in pref):
            score += 3
        scored.append((score, e))
    if not scored:
        return None
    scored.sort(key=lambda t: -t[0])
    return bank / scored[0][1]["rel"]


def _mannequin(height: float, gender: str) -> str:
    """Corpo placeholder estilizado (se não houver Bodiez no banco)."""
    bpy = bl.bpy
    h = float(height)
    partes = [
        ("MAN_pelve", "cube", (0, 0, 0.55 * h), (0.17 * h, 0.11 * h, 0.10 * h)),
        ("MAN_torso", "cube", (0, 0, 0.72 * h), (0.16 * h, 0.10 * h, 0.17 * h)),
        ("MAN_peito", "cube", (0, 0, 0.78 * h), (0.20 * h, 0.11 * h, 0.08 * h)),
        ("MAN_cabeca", "ico_sphere", (0, 0, 0.935 * h), (0.055 * h, 0.06 * h, 0.065 * h)),
        ("MAN_pescoco", "cylinder", (0, 0, 0.87 * h), (0.03 * h, 0.03 * h, 0.03 * h)),
    ]
    for side in ("L", "R"):
        sx = -1 if side == "L" else 1
        partes += [
            (f"MAN_braco_{side}", "cylinder", (sx * 0.24 * h, 0, 0.70 * h),
             (0.035 * h, 0.035 * h, 0.13 * h)),
            (f"MAN_antebraco_{side}", "cylinder", (sx * 0.24 * h, 0, 0.50 * h),
             (0.03 * h, 0.03 * h, 0.12 * h)),
            (f"MAN_mao_{side}", "cube", (sx * 0.24 * h, 0, 0.38 * h),
             (0.03 * h, 0.05 * h, 0.045 * h)),
            (f"MAN_coxa_{side}", "cylinder", (sx * 0.075 * h, 0, 0.42 * h),
             (0.055 * h, 0.055 * h, 0.14 * h)),
            (f"MAN_canela_{side}", "cylinder", (sx * 0.075 * h, 0, 0.17 * h),
             (0.045 * h, 0.045 * h, 0.13 * h)),
            (f"MAN_pe_{side}", "cube", (sx * 0.075 * h, 0.045 * h, 0.03 * h),
             (0.045 * h, 0.11 * h, 0.03 * h)),
        ]
    if gender != "male":
        partes.append(("MAN_busto", "ico_sphere", (0, 0.05 * h, 0.77 * h),
                       (0.11 * h, 0.05 * h, 0.06 * h)))
    nomes = []
    for nome, kind, loc, scl in partes:
        ob = bl.create_primitive(kind, nome, loc, scl)
        nomes.append(ob.name)
    return f"manequim placeholder com {len(nomes)} partes"


# lixo de kit/base modular que NUNCA deve vir com o corpo (probe real:
# modular_female_base vem com 147 objetos, 133 deles widgets WGT-*)
_LIXO_PREFIXOS = ("CS_UI_", "WGT-", "MAN_ui")
_LIXO_TIPOS = {"LIGHT", "CAMERA", "FONT", "EMPTY"}


def spawn_base_body(args: dict, ctx: dict) -> dict:
    bpy = bl.bpy
    gender = (args.get("gender") or "any").lower()
    bank = _ctx_bank(ctx)
    achado = _find_body_in_bank(bank, gender)
    if achado:
        novos = bl.import_asset(achado, None)
        # snapshot ANTES de remover: do_unlink invalida a referência do objeto
        # (ReferenceError: StructRNA removed) — decidir tudo pelos dados, nunca
        # reapontar `novos` depois da faxina.
        meta = [(ob.name, ob.type,
                 len(ob.data.polygons) if ob.type == "MESH" else 10 ** 9)
                for ob in novos]
        mantidos, lixo = [], []
        for nome, tipo, polys in meta:
            if (tipo in _LIXO_TIPOS or nome.startswith(_LIXO_PREFIXOS)
                    or (tipo == "MESH" and polys < 50
                        and not nome.startswith("Geo_"))):
                lixo.append(nome)
            else:
                mantidos.append(nome)
        for nome in lixo:
            ob = bpy.data.objects.get(nome)
            if ob is not None:
                bpy.data.objects.remove(ob, do_unlink=True)
        malhas = [nome for nome, tipo, _ in meta
                  if tipo == "MESH" and nome in mantidos]
        rigs = [nome for nome, tipo, _ in meta
                if tipo == "ARMATURE" and nome in mantidos]
        return _ok(f"Corpo base '{achado.name}' importado: mantidos "
                   f"{len(mantidos)} ({', '.join(malhas[:4]) or 'sem malha'}; "
                   f"armatures: {rigs or 'nenhum'}); removidos {len(lixo)} "
                   "de kit/UI (WGT-*, luzes, câmera, planos). "
                   "(data.shape_keys das malhas) antes de "
                   "apply_body_proportions.")
    h = 1.70 if gender != "female" else 1.65
    resumo = _mannequin(h, "any" if gender not in ("female", "male") else gender)
    return _ok(f"Nenhum corpo base no Asset Bank ({bank}). Criei {resumo}. "
               "Dica: o usuário pode baixar Bodiez/HumGen3D e soltar o .blend no banco "
               "para um corpo de qualidade com shape keys.")


# nomes REAIS do Bodiez modular_female_base (vistos no Blender do usuário):
# Basis, Thin_old, Regular, Thin, Muscular, Fat, Hip_Wide, Breast_Small, Breast_Big
_BODIEZ_PAIRS = {
    "breast": {"Breast_Big": True, "Breast_Small": False},   # True = com +v, False = com -v
    "hips_w": {"Hip_Wide": True},
    "muscle": {"Muscular": True, "Fat": False},
    "waist": {"Fat": True, "Thin": False},  # aproximação: corpo inteiro
}
# eixo massa do Bodiez é EXCLUSIVO (sliders de rádio no painel): Fat+Thin
# juntos deformam o corpo — só o maior pedido vale (resolvido no handler)
_MASSA = ("Thin", "Thin_old", "Regular", "Muscular", "Fat")
# head_size/shoulder_w/leg_len não têm shape key: agora são ESTRUTURAIS
# (escalam vértices da malha real — ver _proporcao_vertices)
_SEM_KEY = []


def _proporcao_vertices(corpo, head_size=0.0, shoulder_w=0.0, leg_len=0.0) -> list:
    """Ajustes que o Bodiez NÃO tem shape key para — escala VÉRTICES da malha
    real (a cabeça verdadeira cresce/encolhe; nunca criar bola nova por cima)."""
    import bmesh
    me = corpo.data
    bm = bmesh.new()
    bm.from_mesh(me)
    try:
        zs = [v.co.z for v in bm.verts]
        zmin, zmax = min(zs), max(zs)
        h = max(1e-6, zmax - zmin)
        xs = [v.co.x for v in bm.verts]
        cx0 = (min(xs) + max(xs)) / 2.0
        out = []
        if head_size:
            esc = 1.0 + 0.45 * max(-1.0, min(1.0, float(head_size)))
            corte = zmin + 0.78 * h                      # linha do pescoço
            alvo = [v for v in bm.verts if v.co.z > corte]
            if alvo:
                cx = sum(v.co.x for v in alvo) / len(alvo)
                cy = sum(v.co.y for v in alvo) / len(alvo)
                for v in alvo:
                    v.co.x = cx + (v.co.x - cx) * esc
                    v.co.y = cy + (v.co.y - cy) * esc
                    v.co.z = corte + (v.co.z - corte) * esc
                out.append(f"head_size: cabeça real {esc:.2f}x "
                           f"({len(alvo)} vértices acima do pescoço)")
        if shoulder_w:
            esc = 1.0 + 0.25 * max(-1.0, min(1.0, float(shoulder_w)))
            z0, z1 = zmin + 0.68 * h, zmin + 0.85 * h    # banda dos ombros
            n = 0
            for v in bm.verts:
                if z0 < v.co.z < z1:
                    v.co.x = cx0 + (v.co.x - cx0) * esc
                    n += 1
            if n:
                out.append(f"shoulder_w: ombros {esc:.2f}x em X ({n} vértices)")
        if leg_len:
            esc = 1.0 + 0.35 * max(-1.0, min(1.0, float(leg_len)))
            corte = zmin + 0.48 * h
            n = 0
            for v in bm.verts:
                if v.co.z < corte:
                    v.co.z = zmin + (v.co.z - zmin) * esc
                    n += 1
            if n:
                out.append(f"leg_len: pernas {esc:.2f}x ({n} vértices)")
        bm.to_mesh(me)
        me.update()
        return out
    finally:
        bm.free()


def apply_body_proportions(args: dict, ctx: dict) -> dict:
    bpy = bl.bpy
    from mathutils import Vector
    lines = []
    objs = [o for o in bpy.data.objects if o.type == "MESH"
            and o.data.shape_keys is not None]
    if objs:
        pedidos = {}   # shape key -> valor (o maior pedido vence)
        for arg, pares in _BODIEZ_PAIRS.items():
            if arg not in args:
                continue
            v = max(-1.0, min(1.0, float(args[arg])))
            for kb_name, com_positivo in pares.items():
                val = max(0.0, v) if com_positivo else max(0.0, -v)
                pedidos[kb_name] = max(pedidos.get(kb_name, 0.0), val)
        massa = {k: v for k, v in pedidos.items() if k in _MASSA}
        if len(massa) > 1:  # ex.: muscle -0.5 (Fat .5) + waist -0.3 (Thin .3)
            ganhou = max(massa, key=massa.get)
            pedidos = {k: v for k, v in pedidos.items()
                       if k not in massa or k == ganhou}
        aplicados = 0
        for o in objs:
            for kb_name, val in pedidos.items():
                kb = o.data.shape_keys.key_blocks.get(kb_name)
                if kb is not None:
                    kb.value = val
                    aplicados += 1
        lines.append(f"shape keys Bodiez ajustadas: {aplicados}")
        sem = [a for a in _SEM_KEY if a in args]
        if sem:
            lines.append("sem shape key no corpo (resolver por modelagem/escala): "
                         + ", ".join(sem))
    else:
        lines.append("corpo sem shape keys (manequim) — pule esta etapa ou importe um corpo melhor")
    if any(a in args for a in ("head_size", "shoulder_w", "leg_len")):
        corpo = max((o for o in bpy.data.objects if o.type == "MESH"),
                    key=lambda o: len(o.data.polygons), default=None)
        if corpo is not None:
            try:
                lines.extend(_proporcao_vertices(
                    corpo,
                    head_size=float(args.get("head_size") or 0.0),
                    shoulder_w=float(args.get("shoulder_w") or 0.0),
                    leg_len=float(args.get("leg_len") or 0.0)))
            except Exception as exc:
                lines.append(f"proporções estruturais falharam: {exc}")
    height = args.get("height_m")
    if height:
        alvos = [o for o in bpy.data.objects if o.type in {"MESH", "ARMATURE"}
                 and o.name.startswith(("MAN_", "Bodiez", "body", "body_base",
                                        "Base", "Geo_", "rig_"))]
        if alvos:
            zmin = min((o.matrix_world @ Vector(c)).z
                       for o in alvos if o.type == "MESH"
                       for c in o.bound_box)
            zmax = max((o.matrix_world @ Vector(c)).z
                       for o in alvos if o.type == "MESH"
                       for c in o.bound_box)
            atual = zmax - zmin
            if atual > 0.01:
                f = float(height) / atual
                raizes = {o.name for o in alvos}
                escalados = 0
                for o in alvos:
                    # raiz = sem pai OU pai fora do conjunto (ex.: corpo filho
                    # da armadura: escala a ARMADURA e o corpo acompanha)
                    if o.parent is None or o.parent.name not in raizes:
                        o.scale = (o.scale[0] * f, o.scale[1] * f, o.scale[2] * f)
                        escalados += 1
                if escalados == 0:
                    lines.append("altura: NADA foi escalado (sem raiz entre "
                                 + ", ".join(o.name for o in alvos[:4]) + ") — relate como falha")
                else:
                    lines.append(f"altura: {atual:.2f}m -> {height:.2f}m "
                                 f"(escala {f:.3f}, {escalados} objeto(s))")
    return _ok("Proporções aplicadas:\n" + "\n".join(lines))


def rig_human(args: dict, ctx: dict) -> dict:
    bpy = bl.bpy
    malhas = [o for o in bpy.data.objects if o.type == "MESH"
              and not o.name.startswith("BLOOM_REF")]
    if not malhas:
        return _fail("Nenhuma malha na cena para rigar (spawne o corpo antes).")
    from mathutils import Vector
    zmin = min((o.matrix_world @ Vector(c)).z for o in malhas for c in o.bound_box)
    zmax = max((o.matrix_world @ Vector(c)).z for o in malhas for c in o.bound_box)
    height = max(0.5, zmax - zmin)
    pos = rig_profiles.bone_positions(height)
    arm_data = bpy.data.armatures.new("BloomRig")
    arm = bpy.data.objects.new("BloomRig", arm_data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    edit = arm_data.edit_bones
    criados = []
    for canônico in rig_profiles.CANONICAL_BONES:
        if canônico not in pos:
            continue
        eb = edit.new(canônico)
        eb.head = pos[canônico]
        tail = rig_profiles.tail_for(canônico, pos)
        eb.tail = tail if tail else (pos[canônico][0], pos[canônico][1] + 0.03 * height,
                                     pos[canônico][2])
        criados.append(canônico)
    # parentes por convenção de nome
    pais = {"spine": "hips", "chest": "spine", "neck": "chest", "head": "neck",
            "head_top": "head"}
    for eb in edit:
        base = eb.name.rsplit(".", 1)[0]
        lado = eb.name.rsplit(".", 1)[1] if "." in eb.name else ""
        pai = None
        if eb.name in pais:
            pai = pais[eb.name]
        elif base in ("shoulder", "upper_arm", "forearm", "hand", "thigh", "shin",
                      "foot", "toe", "breast", "glute") and lado:
            cadeia = {"shoulder": "chest", "upper_arm": "shoulder", "forearm": "upper_arm",
                      "hand": "forearm", "thigh": "hips", "shin": "thigh",
                      "foot": "shin", "toe": "foot", "breast": "chest", "glute": "hips"}
            pai = cadeia[base] + "." + lado
        elif ".1." in eb.name:
            pai = "hand." + lado
        elif ".2." in eb.name:
            pai = eb.name.replace(".2.", ".1.")
        elif ".3." in eb.name:
            pai = eb.name.replace(".3.", ".2.")
        if pai and pai in edit:
            eb.parent = edit[pai]
            eb.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    pesados = [m for m in malhas if m.name.startswith(
        ("MAN_", "Bodiez", "body", "body_base", "Base", "Geo_"))]
    if not pesados:  # fallback: a maior malha da cena é o corpo
        pesados = [max(malhas, key=lambda m: len(m.data.polygons))]
    falhas = []
    for m in pesados:
        m.parent = arm
        try:
            bpy.context.view_layer.objects.active = m
            mod = m.modifiers.new("Armature", "ARMATURE")
            mod.object = arm
            bpy.ops.object.parent_set(type="ARMATURE_AUTO")
        except Exception as e:
            falhas.append(f"{m.name}: {e}")
    rigadas = len(pesados) - len(falhas)
    if rigadas == 0:
        return _fail("rig criado mas NENHUMA malha foi rigada — NÃO chame "
                     "set_export_profile; verifique o corpo na cena.")
    rel = f"rig canônico '{arm.name}' com {len(criados)} ossos; malhas rigadas: {rigadas}"
    if falhas:
        rel += "; pesos automáticos falharam em: " + "; ".join(falhas[:3])
    rel += ". Quando o usuário aprovar, chame set_export_profile com o host alvo."
    return _ok(rel)


def set_export_profile(args: dict, ctx: dict) -> dict:
    bpy = bl.bpy
    profile = (args.get("profile") or "").strip()
    if profile not in rig_profiles.PROFILES:
        return _fail(f"perfil {profile!r} inválido; use {rig_profiles.profiles_available()}")
    origem = args.get("rig_name") or "BloomRig"
    src = bpy.data.objects.get(origem)
    if src is None or src.type != "ARMATURE":
        rigs = [o.name for o in bpy.data.objects if o.type == "ARMATURE"]
        return _fail(f"armature {origem!r} não encontrada; rigs na cena: {rigs or 'nenhum'}")
    if not [o for o in src.children if o.type == "MESH"]:
        return _fail(f"rig '{src.name}' não tem NENHUMA malha parentada — rode "
                     "rig_human com o corpo na cena ANTES de exportar. Nada foi criado.")
    tabela = rig_profiles.mapping_table(profile)
    copia = src.copy()
    copia.data = src.data.copy()
    copia.name = f"Rig_{profile}"
    bpy.context.collection.objects.link(copia)
    renomeados = []
    mapa_renomeio = {}
    for canônico, alvo in tabela:
        b = copia.data.bones.get(canônico)
        if b is not None:
            mapa_renomeio[b.name] = alvo
    for velho, novo in sorted(mapa_renomeio.items(), key=lambda t: -len(t[0])):
        b = copia.data.bones.get(velho)
        if b is not None:
            b.name = novo
            renomeados.append(novo)
    saida = Path(ctx["root"]) / "jobs" / "exports"
    saida.mkdir(parents=True, exist_ok=True)
    arquivo = saida / f"rig_{profile}.json"
    arquivo.write_text(rig_profiles.profile_json(profile), encoding="utf-8")
    return _ok(f"rig '{copia.name}' criado com naming {profile} ({len(renomeados)} ossos "
               f"renomeados). Mapa salvo em {arquivo}. "
               f"Primeiros pares: {renomeados[:8]}")


def reference_backdrop(args: dict, ctx: dict) -> dict:
    bpy = bl.bpy
    ref = (ctx.get("session") or {}).get("reference") or {}
    if not ref.get("b64"):
        return _fail("Nenhuma imagem de referência definida no painel.")
    altura = float(args.get("height_m") or 1.7)
    pasta = Path(ctx["root"]) / "jobs" / "ref"
    pasta.mkdir(parents=True, exist_ok=True)
    ext = {"image/png": ".png", "image/jpeg": ".jpg"}.get(ref.get("mime"), ".png")
    arquivo = pasta / f"reference{ext}"
    arquivo.write_bytes(base64.b64decode(ref["b64"]))
    img = bpy.data.images.load(str(arquivo), check_existing=True)
    empty = bpy.data.objects.new("BLOOM_REF", None)
    empty.empty_display_type = "IMAGE"
    empty.data = img
    empty.empty_display_size = altura
    empty.location = (0.0, -1.4, altura / 2.0)
    empty.rotation_euler = (1.5708, 0.0, 0.0)  # de frente (vista frontal)
    bpy.context.collection.objects.link(empty)
    return _ok(f"Referência '{img.name}' colocada como backdrop frontal "
               f"(altura {altura:.2f} m). Objeto: BLOOM_REF.")


# ---------------------------------------------------------------------------
# tool: shader anime (receitas WuWa — docs/ANIME_RECIPES.md)
# ---------------------------------------------------------------------------

_CORES_PADRAO = {"pele": (0.95, 0.82, 0.74, 1.0), "cabelo": (0.25, 0.2, 0.3, 1.0),
                 "roupa": (0.6, 0.65, 0.75, 1.0), "outline": (0.05, 0.05, 0.07, 1.0)}


def _sombra_hue(rgb) -> tuple:
    """Sombra estilo anime de estúdio: desloca a matiz (padrão LUT WuWa:
    sombra de pele puxa p/ roxo, sombra de roupa satura) — não é só 'escurecer'."""
    r, g, b = (float(c) for c in rgb[:3])
    return tuple(max(0.0, min(1.0, 0.62 * c + 0.38 * (1.0 - c))) for c in (r, g, b))


def _region(nome: str, cores: dict) -> str:
    n = nome.lower()
    if any(t in n for t in ("pele", "skin", "face", "rosto", "head", "cabeca", "body", "corpo")):
        return "pele"
    if any(t in n for t in ("hair", "cabelo", "franja", "bang")):
        return "cabelo"
    if any(t in n for t in ("olho", "eye", "iris")):
        return "olho"
    return "roupa"


def apply_anime_shader(args: dict, ctx: dict) -> dict:
    """Receita WuWa: outlines (solidify invertido + material chapado +
    backface culling) e materiais toon por região (pele/cabelo/roupa).
    Zero dependência de LLM — determinístico."""
    bpy = bl.bpy
    esp = float(args.get("espessura", 0.004))
    cores = {**_CORES_PADRAO, **(args.get("cores") or {})}
    alvos = [o for o in bpy.data.objects if o.type == "MESH"
             and not o.name.startswith(("BLOOM_REF", "MAN_ui", "WGT", "CS_UI"))]
    if not alvos:
        return _fail("nenhuma malha para aplicar shader (spawne o corpo antes)")

    # materiais toon por região (rampa luz/sombra simples)
    mats = {}
    for regiao in ("pele", "cabelo", "roupa", "olho"):
        m = bpy.data.materials.get(f"Bloom_{regiao}") or bpy.data.materials.new(
            f"Bloom_{regiao}")
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        saida = nt.nodes.new("ShaderNodeOutputMaterial")
        diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
        rampa = nt.nodes.new("ShaderNodeValToRGB")
        cor = nt.nodes.new("ShaderNodeRGB")
        cor.outputs[0].default_value = cores.get(regiao, cores["roupa"])
        rampa.color_ramp.elements[0].color = _sombra_hue(
            cores.get(regiao, cores["roupa"])[:3]) + (1.0,)
        rampa.color_ramp.elements[1].color = cores.get(regiao, cores["roupa"])
        nt.links.new(cor.outputs[0], diff.inputs["Color"])
        nt.links.new(diff.outputs[0], rampa.inputs["Fac"])
        nt.links.new(rampa.outputs[0], saida.inputs["Surface"])
        m.use_backface_culling = True
        mats[regiao] = m
    # outline: cor chapada, sem luz (emissão) + backface culling
    mo = bpy.data.materials.get("Bloom_outline") or bpy.data.materials.new(
        "Bloom_outline")
    mo.use_nodes = True
    nt = mo.node_tree
    nt.nodes.clear()
    saida = nt.nodes.new("ShaderNodeOutputMaterial")
    emis = nt.nodes.new("ShaderNodeEmission")
    emis.inputs[0].default_value = cores["outline"]
    emis.inputs[1].default_value = 1.0
    nt.links.new(emis.outputs[0], saida.inputs["Surface"])
    mo.use_backface_culling = True
    mats["outline"] = mo

    feitos, outlines = 0, 0
    for o in alvos:
        # material por região conforme o nome do objeto
        reg = _region(o.name, cores)
        me = o.data
        if len(me.materials) == 0 or (
                len(me.materials) == 1 and me.materials[0] is None):
            me.materials.append(mats[reg])
        elif not any(m and m.name.startswith("Bloom_") for m in me.materials):
            me.materials.append(mats[reg])
        idx_out = None
        for i, m in enumerate(me.materials):
            if m is None:
                continue
            if m.name.startswith("Bloom_outline"):
                idx_out = i
            elif not m.name.startswith("Bloom_"):
                pass  # preserva materiais existentes do usuário
        if idx_out is None:
            me.materials.append(mats["outline"])
            idx_out = len(me.materials) - 1
        # smooth shading
        for poly in me.polygons:
            poly.use_smooth = True
        # outline via solidify invertido (receita WuWa)
        mod = o.modifiers.get("Bloom_Outline")
        if mod is None:
            mod = o.modifiers.new("Bloom_Outline", "SOLIDIFY")
        mod.thickness = esp
        mod.offset = 1
        mod.use_flip_normals = True
        mod.material_offset_rim = idx_out
        mod.use_rim = True
        mod.show_render = True
        mod.show_in_editmode = False
        outlines += 1
        feitos += 1
    resumo_cores = ", ".join(f"{k}={tuple(round(c, 2) for c in v[:3])}"
                             for k, v in cores.items())
    return _ok(f"shader anime aplicado em {feitos} malha(s); outlines: {outlines}; "
               f"regiões: pele/cabelo/roupa/olho + outline (cores: {resumo_cores}). "
               "Custom normals de rosto entram com o probe do modelo de estudo.")


# reexport p/ registry


# ---------------------------------------------------------------------------
# tools: pipeline completo (M3 export/peças, M4 UV+textura, M5 animação)
# ---------------------------------------------------------------------------

def _corpo_do_rig(bpy, rig) -> list:
    return [o for o in bpy.data.objects if o.type == "MESH"
            and not o.name.startswith(("BLOOM_REF", "Bloom_Tex"))
            and (o.parent == rig or any(m.type == "ARMATURE" and m.object == rig
                                        for m in o.modifiers))]


def _achar_rig(bpy):
    return (bpy.data.objects.get("BloomRig")
            or next((o for o in bpy.data.objects if o.type == "ARMATURE"
                     and o.name.startswith(("BloomRig", "rig_"))), None))


def export_character(args: dict, ctx: dict) -> dict:
    """EXPORT REAL do personagem: vrm (add-on VRM, enable automático), glb ou fbx.
    Aplica escala, seleciona só rig+malhas do personagem e grava em jobs/exports."""
    bpy = bl.bpy
    from math import radians
    fmt = (args.get("formato") or "glb").lower()
    if fmt not in ("vrm", "glb", "fbx"):
        return _fail("formato deve ser vrm, glb ou fbx (vrm2 do painel = vrm).")
    rig = _achar_rig(bpy)
    if rig is None:
        return _fail("sem rig na cena — rode rig_human antes de exportar.")
    malhas = _corpo_do_rig(bpy, rig)
    if not malhas:
        return _fail("nenhuma malha ligada ao rig — nada a exportar.")
    try:
        bpy.ops.object.select_all(action="DESELECT")
        rig.select_set(True)
        for m in malhas:
            m.select_set(True)
        bpy.context.view_layer.objects.active = rig
        # a altura foi aplicada como escala na armadura: assa ANTES do export
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    except Exception as exc:
        return _fail(f"falha ao aplicar escala antes do export: {exc}")
    pasta = Path(ctx["root"]) / "jobs" / "exports"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"personagem_{time.strftime('%Y%m%d-%H%M%S')}.{fmt}"
    bpy.ops.object.select_all(action="DESELECT")
    for o in [rig] + malhas:
        o.select_set(True)
    bpy.context.view_layer.objects.active = rig
    try:
        if fmt == "glb":
            bpy.ops.export_scene.gltf(filepath=str(destino), export_format="GLB",
                                      use_selection=True)
        elif fmt == "fbx":
            bpy.ops.export_scene.fbx(filepath=str(destino), use_selection=True,
                                     add_leaf_bones=False)
        else:  # vrm — habilita a extensão VRM se estiver desligada (milestone M3)
            try:
                import addon_utils
                try:
                    addon_utils.enable("bl_ext.user_default.io_scene_vrm",
                                       default_set=True, persistent=True)
                except Exception:
                    pass
            except Exception:
                pass
            try:
                bpy.ops.export_scene.vrm(filepath=str(destino), use_selection=True)
            except Exception:
                destino = destino.with_suffix(".glb")
                bpy.ops.export_scene.gltf(filepath=str(destino), export_format="GLB",
                                          use_selection=True)
                return _ok(f"[!] extensão VRM não disponível — exportei GLB em "
                           f"{destino} (ligue 'VRM' em Preferences > Extensions e "
                           "peça de novo para .vrm nativo).")
        return _ok(f"EXPORTADO: {destino} ({len(malhas)} malha(s) + rig {rig.name}). "
                   "Entregue ao host (Project Airi aceita .vrm direto).")
    except Exception as exc:
        return _fail(f"export falhou: {type(exc).__name__}: {exc}")


_PECA_OSSO = {"hair": "head", "cabelo": "head", "top": "spine", "roupa": "spine",
              "bottom": "hips", "calca": "hips", "shoes": "foot.L",
              "sapato": "foot.L", "accessory": "head", "acessorio": "head"}


def make_piece(args: dict, ctx: dict) -> dict:
    """Separa peças do personagem (requisito 3: cabelo/roupas exportam SOZINHOS).
    Quebra ilhas separadas (mesh.separate LOOSE), parenteia ao rig com pesos
    automáticos e marca custom prop bloom_piece p/ export por peça."""
    bpy = bl.bpy
    peca = (args.get("peca") or "").lower()
    if peca not in _PECA_OSSO:
        return _fail("peca inválida; use cabelo/hair, top/roupa, bottom/calca, "
                     "shoes/sapato, accessory/acessorio")
    nome_alvo = (args.get("objeto") or "").strip()
    origem = (bpy.data.objects.get(nome_alvo) if nome_alvo else
              max((o for o in bpy.data.objects if o.type == "MESH"
                   and not o.name.startswith(("BLOOM_REF", "WGT", "CS_UI"))),
                  key=lambda o: len(o.data.polygons), default=None))
    if origem is None:
        return _fail("objeto não encontrado para virar peça.")
    rig = _achar_rig(bpy)
    if rig is None:
        return _fail("rigue o personagem antes de separar peças (rig_human).")
    antes = set(bpy.data.objects.keys())
    try:
        bpy.ops.object.select_all(action="DESELECT")
        origem.select_set(True)
        bpy.context.view_layer.objects.active = origem
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.separate(type="LOOSE")
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception as exc:
        return _fail(f"separação falhou: {exc}")
    pecas = [bpy.data.objects[n] for n in bpy.data.objects.keys()
             if n not in antes and bpy.data.objects[n].type == "MESH"]
    if not pecas:
        pecas = [origem]
    feitas, tris = [], 0
    for i, ob in enumerate(pecas):
        ob.name = (f"Bloom_{peca}" if len(pecas) == 1 else f"Bloom_{peca}_{i + 1:02d}")
        try:
            bpy.ops.object.select_all(action="DESELECT")
            ob.select_set(True)
            bpy.context.view_layer.objects.active = rig
            bpy.ops.object.parent_set(type="ARMATURE_AUTO")
        except Exception:
            ob.parent = rig
            mod = ob.modifiers.new("Armature", "ARMATURE")
            mod.object = rig
        ob["bloom_piece"] = peca
        tris += len(ob.data.polygons)
        feitas.append(ob.name)
    return _ok(f"peça '{peca}': {len(feitas)} objeto(s) ({', '.join(feitas)}), "
               f"{tris} tris, parentado ao rig {rig.name} com pesos automáticos e "
               f"marcado bloom_piece='{peca}' (exporta separado em export_character "
               "e no glb/fbx por objeto).")


def uv_and_bake(args: dict, ctx: dict) -> dict:
    """M4: Smart UV Project nas malhas sem UV + bake DIFFUSE (cor toon) em
    textura 1024 (Cycles CPU — RX 580 não precisa) e troca a superfície pela
    textura assada PRESERVANDO o outline (material_offset_rim reindexado)."""
    bpy = bl.bpy
    from math import radians
    so_uv = bool(args.get("so_uv", False))
    rig = _achar_rig(bpy)
    malhas = _corpo_do_rig(bpy, rig) if rig else []
    if not malhas:
        return _fail("nada para UV/bake (spawne o corpo e rigue antes).")
    sem_uv = [m.name for m in malhas if not m.data.uv_layers]
    try:
        for m in malhas:
            if m.data.uv_layers:
                continue
            bpy.ops.object.select_all(action="DESELECT")
            m.select_set(True)
            bpy.context.view_layer.objects.active = m
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.uv.smart_project(angle_limit=radians(66), island_margin=0.02)
            bpy.ops.object.mode_set(mode="OBJECT")
    except Exception as exc:
        return _fail(f"UV falhou: {exc}")
    lines = [f"UV pronta em {len(malhas)} malha(s) "
             f"({len(sem_uv)} precisaram de Smart UV: {', '.join(sem_uv[:5])})"]
    if so_uv:
        return _ok("\n".join(lines))
    sc = bpy.context.scene
    eng = sc.render.engine
    pasta = Path(ctx["root"]) / "jobs" / "textures"
    pasta.mkdir(parents=True, exist_ok=True)
    assadas = []
    try:
        sc.render.engine = "CYCLES"
        sc.cycles.device = "CPU"        # RX 580 = sem CUDA: bake por CPU é rápido
        sc.cycles.samples = 8
        for m in malhas:
            me = m.data
            if not me.materials or me.materials[0] is None:
                continue
            img = bpy.data.images.new(f"Bloom_Tex_{m.name[:24]}", 1024, 1024)
            nt = me.materials[0].node_tree
            tex = nt.nodes.new("ShaderNodeTexImage")
            tex.image = img
            nt.nodes.active = tex
            tex.select = True
            me.uv_layers.active = me.uv_layers[0]
            bpy.ops.object.select_all(action="DESELECT")
            m.select_set(True)
            bpy.context.view_layer.objects.active = m
            bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"},
                                use_clear=True, margin=8)
            img.filepath_raw = str(pasta / f"{m.name}.png")
            img.file_format = "PNG"
            try:
                img.save()
            except Exception:
                pass
            # troca a superfície pela textura assada, PRESERVANDO o outline
            idx_out = next((i for i, mm in enumerate(me.materials)
                            if mm and mm.name.startswith("Bloom_outline")), None)
            mod = m.modifiers.get("Bloom_Outline")
            baked = (bpy.data.materials.get("Bloom_Baked")
                     or bpy.data.materials.new("Bloom_Baked"))
            baked.use_nodes = True
            bnt = baked.node_tree
            bnt.nodes.clear()
            saida = bnt.nodes.new("ShaderNodeOutputMaterial")
            emis = bnt.nodes.new("ShaderNodeEmission")
            it = bnt.nodes.new("ShaderNodeTexImage")
            it.image = img
            bnt.links.new(it.outputs[0], emis.inputs["Color"])
            bnt.links.new(emis.outputs[0], saida.inputs["Surface"])
            mats_base = [mm for mm in me.materials
                         if mm and not mm.name.startswith("Bloom_outline")]
            me.materials.clear()
            me.materials.append(baked)
            if idx_out is not None:
                mat_out = bpy.data.materials.get("Bloom_outline")
                if mat_out is not None:
                    me.materials.append(mat_out)
                    if mod is not None:
                        mod.material_offset_rim = 1
            assadas.append(m.name)
        lines.append(f"textura assada 1024px em {len(assadas)} malha(s) "
                     f"({', '.join(assadas[:5])}); PNGs em jobs/textures/")
    except Exception as exc:
        lines.append(f"bake falhou (UV continua pronta): {exc}")
    finally:
        sc.render.engine = eng
    return _ok("\n".join(lines))


def make_idle_animation(args: dict, ctx: dict) -> dict:
    """M5: idle loop 96 frames @30fps (respiração, balanço de cabeça/braços)
    no rig canônico — exporte com export_character formato glb p/ levar a animação."""
    bpy = bl.bpy
    rig = _achar_rig(bpy)
    if rig is None:
        return _fail("rig não encontrado.")
    sc = bpy.context.scene
    sc.frame_start = 1
    sc.frame_end = 96
    sc.render.fps = 30
    moves = {"spine": ("x", 0.020), "chest": ("x", 0.015),
             "neck": ("y", 0.020), "head": ("y", 0.045),
             "upper_arm.L": ("z", 0.05), "upper_arm.R": ("z", -0.05)}
    criados = []
    try:
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode="POSE")
        if rig.animation_data:
            rig.animation_data_clear()
        idx_eixo = {"x": 0, "y": 1, "z": 2}
        for nome, (eixo, amp) in moves.items():
            pb = rig.pose.bones.get(nome)
            if pb is None:
                continue
            if pb.rotation_mode == "QUATERNION":
                pb.rotation_mode = "XYZ"
            idx = idx_eixo[eixo]
            for f, val in ((1, 0.0), (48, amp), (96, 0.0)):
                pb.rotation_euler[idx] = val
                pb.keyframe_insert(data_path="rotation_euler", index=idx, frame=f)
            criados.append(nome)
        bpy.ops.object.mode_set(mode="OBJECT")
        sc.frame_set(1)
    except Exception as exc:
        return _fail(f"animação falhou: {exc}")
    if not criados:
        return _fail("nenhum osso canônico encontrado para animar.")
    return _ok(f"idle 96 frames @30fps criado em {len(criados)} osso(s) "
               f"({', '.join(criados)}); loop 1→96. Use export_character "
               "formato=glb para levar a animação embutida.")


def adapt_asset(args: dict, ctx: dict) -> dict:
    """REQUISITO 6 — veste um asset do Asset Bank (roupa/cabelo comprado ou free)
    no corpo atual: importa, centraliza, escala pela bbox, shrinkwrap + corrective
    smooth, parenteia ao rig com pesos e marca bloom_piece. NÃO modela do zero."""
    bpy = bl.bpy
    from mathutils import Vector
    nome = (args.get("arquivo") or "").strip()
    peca = (args.get("peca") or "roupa").lower()
    if peca not in _PECA_OSSO:
        return _fail(f"peca inválida; use {sorted(set(_PECA_OSSO))}")
    bank = _ctx_bank(ctx)
    alvo_arq = None
    if nome:
        direto = bank / nome
        if direto.is_file():
            alvo_arq = direto
        else:
            for e in bl.list_bank_files(bank):
                alvo = nome.lower()
                if (alvo in e["id"].lower() or alvo in e["name"].lower()
                        or alvo in (e.get("tags") or [])):
                    alvo_arq = bank / e["rel"]
                    break
    else:  # sem nome: primeiro asset com a tag da peça
        tag = {"cabelo": "cabelo", "top": "roupa", "roupa": "roupa",
               "bottom": "calca", "calca": "calca", "shoes": "sapato",
               "sapato": "sapato", "accessory": "acessorio",
               "acessorio": "acessorio"}.get(peca)
        for e in bl.list_bank_files(bank):
            if tag in (e.get("tags") or []):
                alvo_arq = bank / e["rel"]
                break
    if alvo_arq is None:
        return _fail(f"asset '{nome or peca}' não encontrado no banco ({bank}). "
                     "Use asset_scan para ver o que existe.")
    corpo = max((o for o in bpy.data.objects if o.type == "MESH"
                 and not o.name.startswith(("BLOOM_REF", "Outline"))),
                key=lambda o: len(o.data.polygons), default=None)
    if corpo is None:
        return _fail("spawne o corpo base antes de vestir o asset.")
    rig = _achar_rig(bpy)
    novos = bl.import_asset(alvo_arq, f"Bloom_{peca}")
    malhas = [o for o in novos if o.type == "MESH"]
    if not malhas:
        return _fail(f"'{alvo_arq.name}' não tem malhas para vestir.")
    bpy.context.view_layer.update()
    zs = [v for m in malhas for v in m.bound_box]
    # bbox do asset em mundo
    cantos = [m.matrix_world @ Vector(c) for m in malhas for c in m.bound_box]
    amin = Vector((min(c.x for c in cantos), min(c.y for c in cantos),
                   min(c.z for c in cantos)))
    amax = Vector((max(c.x for c in cantos), max(c.y for c in cantos),
                   max(c.z for c in cantos)))
    acentro = (amin + amax) / 2
    aalt = max(1e-4, amax.z - amin.z)
    # corpo: referência de altura/centro
    czs = [corpo.matrix_world @ Vector(c) for c in corpo.bound_box]
    cmin = Vector((min(c.x for c in czs), min(c.y for c in czs), min(c.z for c in czs)))
    cmax = Vector((max(c.x for c in czs), max(c.x for c in czs), max(c.z for c in czs)))
    calt = max(1e-4, cmax.z - cmin.z)
    ccentro = (cmin + cmax) / 2
    # fração do corpo que a peça cobre (roupa ~torso, cabelo ~cabeça, etc.)
    fracao = {"cabelo": 0.30, "top": 0.35, "roupa": 0.60, "bottom": 0.45,
              "calca": 0.45, "shoes": 0.12, "sapato": 0.12,
              "accessory": 0.20, "acessorio": 0.20}.get(peca, 0.5)
    esc = (calt * fracao) / aalt
    for m in malhas:
        m.scale = (m.scale[0] * esc, m.scale[1] * esc, m.scale[2] * esc)
        m.location = (ccentro.x, ccentro.y,
                      cmin.z + calt * (0.5 + {"cabelo": 0.42, "top": 0.22,
                                              "roupa": 0.0, "bottom": -0.15,
                                              "calca": -0.15, "shoes": -0.44,
                                              "sapato": -0.44,
                                              "accessory": 0.45,
                                              "acessorio": 0.45}.get(peca, 0.0))
                      - (acentro.z - amin.z) * esc)
    bpy.context.view_layer.update()
    feitos = []
    for m in malhas:
        m.parent = rig if rig else corpo
        try:
            sw = m.modifiers.new("Bloom_Fit", "SHRINKWRAP")
            sw.target = corpo
            sw.wrap_method = "WRAP"
            sw.offset = 0.004
            cs = m.modifiers.new("Bloom_SmoothFit", "CORRECTIVE_SMOOTH")
            cs.factor = 0.5
        except Exception:
            pass
        m["bloom_piece"] = peca
        feitos.append(m.name)
    return _ok(f"asset '{alvo_arq.name}' vestido como '{peca}': {len(feitos)} malha(s) "
               f"({', '.join(feitos)}), escala {esc:.2f}x, shrinkwrap em "
               f"{corpo.name} + corrective smooth, parent ao "
               f"{rig.name if rig else corpo.name}, marcado bloom_piece='{peca}'. "
               "Confira com render_view; ajuste fino de posição/escala se a peça "
               "flutuar ou afundar.")
