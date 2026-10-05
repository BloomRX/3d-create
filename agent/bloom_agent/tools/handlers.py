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


def spawn_base_body(args: dict, ctx: dict) -> dict:
    gender = (args.get("gender") or "any").lower()
    bank = _ctx_bank(ctx)
    achado = _find_body_in_bank(bank, gender)
    if achado:
        novos = bl.import_asset(achado, None)
        malhas = [n.name for n in novos if n.type == "MESH"]
        rigs = [n.name for n in novos if n.type == "ARMATURE"]
        return _ok(f"Corpo base '{achado.name}' importado: {len(novos)} objeto(s); "
                   f"malhas: {malhas[:6]}; armatures: {rigs or 'nenhum'}. "
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
}
# sem shape key no Bodiez (agent resolve por modelagem/escala depois):
_SEM_KEY = ["head_size", "shoulder_w", "waist", "leg_len"]


def apply_body_proportions(args: dict, ctx: dict) -> dict:
    bpy = bl.bpy
    lines = []
    objs = [o for o in bpy.data.objects if o.type == "MESH"
            and o.data.shape_keys is not None]
    if objs:
        aplicados = 0
        for arg, pares in _BODIEZ_PAIRS.items():
            if arg not in args:
                continue
            v = max(-1.0, min(1.0, float(args[arg])))
            for kb_name, com_positivo in pares.items():
                val = max(0.0, v) if com_positivo else max(0.0, -v)
                for o in objs:
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
    height = args.get("height_m")
    if height:
        alvos = [o for o in bpy.data.objects if o.type in {"MESH", "ARMATURE"}
                 and o.name.startswith(("MAN_", "Bodiez", "body", "body_base", "Base"))]
        if alvos:
            zmin = min((o.matrix_world @ v.co).z
                       for o in alvos if o.type == "MESH"
                       for v in o.bound_box)
            zmax = max((o.matrix_world @ v.co).z
                       for o in alvos if o.type == "MESH"
                       for v in o.bound_box)
            atual = zmax - zmin
            if atual > 0.01:
                f = float(height) / atual
                for o in alvos:
                    if o.parent is None:
                        o.scale = (o.scale[0] * f, o.scale[1] * f, o.scale[2] * f)
                lines.append(f"altura: {atual:.2f}m -> {height:.2f}m (escala {f:.3f})")
    return _ok("Proporções aplicadas:\n" + "\n".join(lines))


def rig_human(args: dict, ctx: dict) -> dict:
    bpy = bl.bpy
    malhas = [o for o in bpy.data.objects if o.type == "MESH"
              and not o.name.startswith("BLOOM_REF")]
    if not malhas:
        return _fail("Nenhuma malha na cena para rigar (spawne o corpo antes).")
    zmin = min((o.matrix_world @ v.co).z for o in malhas for v in o.bound_box)
    zmax = max((o.matrix_world @ v.co).z for o in malhas for v in o.bound_box)
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
    pesados = [m for m in malhas if m.name.startswith(("MAN_", "Bodiez", "body", "Base"))]
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
    rel = f"rig canônico '{arm.name}' com {len(criados)} ossos; malhas rigadas: {len(pesados) - len(falhas)}"
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
