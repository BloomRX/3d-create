"""Perfis de esqueleto do Bloom Agent (M1+).

Conceito: o rig TRABALHADO no Blender usa nomes CANÔNICOS (estilo Rigify,
lado como sufixo .L/.R). Na exportação, remapeamos para o naming do host:
  - metahuman : esqueleto UE5/MetaHuman (idêntico ao gerado pelo Magic Bone)
  - vrm2      : humanoid padrão VRM 1.0 (Vroid/Project Airi)
  - mixamo    : prefixo mixamorig: (Auto-Rig / Adobe Mixamo)
  - custom    : mantém os nomes canônicos

Este módulo é PURO (sem bpy) — testável fora do Blender.
"""
from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# esqueleto canônico (ordem de criação no rig_human)
# ---------------------------------------------------------------------------

CANONICAL_BONES = [
    "hips", "spine", "chest", "neck", "head", "head_top",
    "shoulder.L", "upper_arm.L", "forearm.L", "hand.L",
    "shoulder.R", "upper_arm.R", "forearm.R", "hand.R",
    "thigh.L", "shin.L", "foot.L", "toe.L",
    "thigh.R", "shin.R", "foot.R", "toe.R",
    # dedos (1=proximal, 2=médio, 3=distal)
    "thumb.1.L", "thumb.2.L", "thumb.3.L",
    "index.1.L", "index.2.L", "index.3.L",
    "middle.1.L", "middle.2.L", "middle.3.L",
    "ring.1.L", "ring.2.L", "ring.3.L",
    "pinky.1.L", "pinky.2.L", "pinky.3.L",
    "thumb.1.R", "thumb.2.R", "thumb.3.R",
    "index.1.R", "index.2.R", "index.3.R",
    "middle.1.R", "middle.2.R", "middle.3.R",
    "ring.1.R", "ring.2.R", "ring.3.R",
    "pinky.1.R", "pinky.2.R", "pinky.3.R",
    # extras estilo VRoid/VRM (opcionais no rig, ignorados se ausentes)
    "breast.L", "breast.R", "glute.L", "glute.R",
]

_CORE = ["hips", "spine", "chest", "neck", "head",
         "shoulder", "upper_arm", "forearm", "hand",
         "thigh", "shin", "foot", "toe"]
_FINGERS = ["thumb", "index", "middle", "ring", "pinky"]
_SIDES = ["L", "R"]

# ---------------------------------------------------------------------------
# mapas canônico -> perfil
# ---------------------------------------------------------------------------

_METAHUMAN = {
    "hips": "pelvis", "spine": "spine_01", "chest": "spine_02",
    "neck": "neck_01", "head": "head", "head_top": "head_top_end",
    "shoulder.L": "clavicle_l", "upper_arm.L": "upperarm_l",
    "forearm.L": "lowerarm_l", "hand.L": "hand_l",
    "shoulder.R": "clavicle_r", "upper_arm.R": "upperarm_r",
    "forearm.R": "lowerarm_r", "hand.R": "hand_r",
    "thigh.L": "thigh_l", "shin.L": "calf_l", "foot.L": "foot_l", "toe.L": "ball_l",
    "thigh.R": "thigh_r", "shin.R": "calf_r", "foot.R": "foot_r", "toe.R": "ball_r",
}
for _f in _FINGERS:
    for _n, _seg in (("1", "01"), ("2", "02"), ("3", "03")):
        _METAHUMAN[f"{_f}.{_n}.L"] = f"{_f}_{_seg}_l"
        _METAHUMAN[f"{_f}.{_n}.R"] = f"{_f}_{_seg}_r"

_VRM2 = {
    "hips": "hips", "spine": "spine", "chest": "chest",
    "neck": "neck", "head": "head", "head_top": "head_top",
    "shoulder.L": "leftShoulder", "upper_arm.L": "leftUpperArm",
    "forearm.L": "leftLowerArm", "hand.L": "leftHand",
    "shoulder.R": "rightShoulder", "upper_arm.R": "rightUpperArm",
    "forearm.R": "rightLowerArm", "hand.R": "rightHand",
    "thigh.L": "leftUpperLeg", "shin.L": "leftLowerLeg",
    "foot.L": "leftFoot", "toe.L": "leftToes",
    "thigh.R": "rightUpperLeg", "shin.R": "rightLowerLeg",
    "foot.R": "rightFoot", "toe.R": "rightToes",
    "breast.L": "leftBreast", "breast.R": "rightBreast",
}
_VRM_FING = {"thumb": "Thumb", "index": "Index", "middle": "Middle",
             "ring": "Ring", "pinky": "Little"}
_VRM_SEG = {"1": "Proximal", "2": "Intermediate", "3": "Distal"}
for _f, _F in _VRM_FING.items():
    for _n, _S in _VRM_SEG.items():
        _VRM2[f"{_f}.{_n}.L"] = f"left{_F}{_S}"
        _VRM2[f"{_f}.{_n}.R"] = f"right{_F}{_S}"

_MIXAMO = {
    "hips": "mixamorig:Hips", "spine": "mixamorig:Spine", "chest": "mixamorig:Spine1",
    "neck": "mixamorig:Neck", "head": "mixamorig:Head", "head_top": "mixamorig:HeadTop_End",
    "shoulder.L": "mixamorig:LeftShoulder", "upper_arm.L": "mixamorig:LeftArm",
    "forearm.L": "mixamorig:LeftForeArm", "hand.L": "mixamorig:LeftHand",
    "shoulder.R": "mixamorig:RightShoulder", "upper_arm.R": "mixamorig:RightArm",
    "forearm.R": "mixamorig:RightForeArm", "hand.R": "mixamorig:RightHand",
    "thigh.L": "mixamorig:LeftUpLeg", "shin.L": "mixamorig:LeftLeg",
    "foot.L": "mixamorig:LeftFoot", "toe.L": "mixamorig:LeftToeBase",
    "thigh.R": "mixamorig:RightUpLeg", "shin.R": "mixamorig:RightLeg",
    "foot.R": "mixamorig:RightFoot", "toe.R": "mixamorig:RightToeBase",
}
_MIX_FING = {"thumb": "Thumb", "index": "Index", "middle": "Middle",
             "ring": "Ring", "pinky": "Pinky"}
for _f, _F in _MIX_FING.items():
    for _n in ("1", "2", "3"):
        _MIXAMO[f"{_f}.{_n}.L"] = f"mixamorig:LeftHand{_F}{_n}"
        _MIXAMO[f"{_f}.{_n}.R"] = f"mixamorig:RightHand{_F}{_n}"

# ossos EXTRA típicos de cada perfil (não vêm do canônico; info p/ export)
PROFILE_EXTRAS = {
    "metahuman": ["spine_03", "neck_02", "clavicle_l_twist_01",
                  "upperarm_twist_01_l", "upperarm_twist_02_l",
                  "lowerarm_twist_01_l", "lowerarm_twist_02_l",
                  "calf_twist_01_l", "calf_twist_02_l", "thigh_twist_01_l"],
    "vrm2": ["upperChest", "leftUpperLegTwist", "j_sec"] ,
    "mixamo": ["mixamorig:Spine2", "mixamorig:LeftForeArmTwist",
               "mixamorig:LeftLegTwist"],
    "custom": [],
}

PROFILES = {
    "metahuman": _METAHUMAN,
    "vrm2": _VRM2,
    "mixamo": _MIXAMO,
    "custom": {b: b for b in CANONICAL_BONES},
}


def profiles_available() -> list:
    return list(PROFILES.keys())


def remap(canonical: str, profile: str) -> str | None:
    """Nome do osso no perfil (None se o perfil não o tiver)."""
    return PROFILES.get(profile, {}).get(canonical)


def bones_for(profile: str) -> list:
    """Nomes ordenados dos ossos do perfil (apenas os mapeados)."""
    prof = PROFILES.get(profile)
    if not prof:
        raise ValueError(f"perfil desconhecido: {profile!r} "
                         f"(use {profiles_available()})")
    return [prof[c] for c in CANONICAL_BONES if c in prof]


def mapping_table(profile: str) -> list:
    """[(canônico, perfil), ...] na ordem canônica — p/ relatório e renomear."""
    prof = PROFILES.get(profile)
    if not prof:
        raise ValueError(f"perfil desconhecido: {profile!r}")
    return [(c, prof[c]) for c in CANONICAL_BONES if c in prof]


def profile_json(profile: str, positions: dict | None = None) -> str:
    """Descrição JSON do esqueleto no perfil (p/ export/inspeção)."""
    prof = PROFILES.get(profile)
    if not prof:
        raise ValueError(f"perfil desconhecido: {profile!r}")
    bones = []
    for c in CANONICAL_BONES:
        if c in prof:
            item = {"canonical": c, "bone": prof[c]}
            if positions and c in positions:
                item["head"] = [round(v, 4) for v in positions[c]]
            bones.append(item)
    return json.dumps({"profile": profile, "bones": bones,
                       "extras": PROFILE_EXTRAS.get(profile, [])},
                      indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# posições heurísticas do rig (Z-up, metros) — PURO, usado por rig_human
# ---------------------------------------------------------------------------

def bone_positions(height: float = 1.70) -> dict:
    """Posição da CABEÇA de cada osso canônico para uma figura humana.

    Proporções clássicas de 7.5 cabeças, ajustáveis pelo parâmetro.
    X = lateral (esq +Y? não: +X), Y = frente/trás, Z = cima.
    """
    h = float(height)
    sh_w = 0.235 * h      # meia-largura de ombros
    hip_w = 0.11 * h
    arm_r = 0.055 * h     # raio do braço (afastamento do corpo)
    pos = {
        "hips": (0.0, 0.0, 0.545 * h),
        "spine": (0.0, 0.0, 0.635 * h),
        "chest": (0.0, 0.0, 0.74 * h),
        "neck": (0.0, 0.0, 0.845 * h),
        "head": (0.0, 0.0, 0.895 * h),
        "head_top": (0.0, 0.0, 1.0 * h),
        "breast.L": (-0.075 * h, 0.07 * h, 0.72 * h),
        "breast.R": (0.075 * h, 0.07 * h, 0.72 * h),
        "glute.L": (-0.07 * h, -0.03 * h, 0.52 * h),
        "glute.R": (0.07 * h, -0.03 * h, 0.52 * h),
    }
    for side, sx in (("L", -1.0), ("R", 1.0)):
        x = lambda v: sx * v
        pos[f"shoulder.{side}"] = (x(sh_w * 0.55), 0.0, 0.83 * h)
        pos[f"upper_arm.{side}"] = (x(sh_w), -0.01 * h, 0.82 * h)
        pos[f"forearm.{side}"] = (x(sh_w + arm_r), 0.0, 0.615 * h)
        pos[f"hand.{side}"] = (x(sh_w + arm_r * 1.1), 0.0, 0.435 * h)
        pos[f"thigh.{side}"] = (x(hip_w), 0.0, 0.52 * h)
        pos[f"shin.{side}"] = (x(hip_w * 0.95), 0.005 * h, 0.29 * h)
        pos[f"foot.{side}"] = (x(hip_w * 0.95), 0.0, 0.045 * h)
        pos[f"toe.{side}"] = (x(hip_w * 0.95), 0.12 * h, 0.02 * h)
        for i, f in enumerate(_FINGERS):
            spread = (i - 2) * 0.011 * h
            base_z = 0.415 * h
            pos[f"{f}.1.{side}"] = (x(sh_w + arm_r * 1.1 + spread), 0.0, base_z)
            pos[f"{f}.2.{side}"] = (x(sh_w + arm_r * 1.1 + spread), 0.0, base_z - 0.033 * h)
            pos[f"{f}.3.{side}"] = (x(sh_w + arm_r * 1.1 + spread), 0.0, base_z - 0.062 * h)
    return pos


# caudas (tail) de cada osso canônico — direção aproximada
BONE_TAILS = {
    "hips": "spine", "spine": "chest", "chest": "neck", "neck": "head",
    "head": "head_top", "head_top": None,
    "breast.L": None, "breast.R": None, "glute.L": None, "glute.R": None,
}


def tail_for(canonical: str, pos: dict) -> tuple | None:
    """Osso-destino da cauda; default: espelha a direção do pai."""
    t = BONE_TAILS.get(canonical, "?")
    if t == "?":  # padrão: membro aponta p/ o próximo da cadeia
        chain = {"shoulder": "upper_arm", "upper_arm": "forearm",
                 "forearm": "hand", "hand": None,
                 "thigh": "shin", "shin": "foot", "foot": "toe", "toe": None}
        base = canonical.rsplit(".", 1)[0]
        if base in chain and chain[base]:
            return pos.get(chain[base] + "." + canonical.rsplit(".", 1)[1],
                           pos.get(chain[base]))
        return None
    return pos.get(t) if t else None
