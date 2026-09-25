# Levantamento dos addons (lido em 2026-09-24)

Os zips foram removidos do repo após leitura (peso). Links dos muito grandes
estão em `OutrosMaisPesados.txt`. Este arquivo registra o que cada um é e
**como o Bloom Agent vai usar**.

## Núcleo do pipeline (M1–M3)

| Addon | O que é | Uso no Bloom Agent |
|---|---|---|
| **Bodiez Base Meshes** | 2 .blend (fem/masc) modulares, **metarig Rigify embutido** + shape keys de customização (`Breast_Size`, `Head_Size`, `Arm_Short`, `Shoulder_Type`, `ACdeform_*`…) | Base humana do M1: agent instancia, ajusta proporções via shape keys conforme a foto, gera rig Rigify e remapeia pros perfis de export |
| **Magic Bone UE5 Rig Creator Pro** | Gera esqueleto padrão UE5 (`spine_01..03`, `upperarm_twist_01_l`, `index_01_l`, `_l/_r`…) | Referência da tabela de ossos do perfil **metahuman/UE5** (naming real, twist joints, dedos) |
| **Auto-Rig Pro 3.76** | Auto-rig completo (+ Quick Rig, rig library c/ humanos e animais, glTF exporter modificado p/ export UE/Unity) | Motor de rig avançado opcional: se instalado no Blender do usuário, agent pode usá-lo p/ rig com melhor qualidade e export |
| **Genshin Shader v2.2.2** | .blend com shader toon estilo Genshin | Base do recurso "colar shader" (estilo anime) — agent copia nodes/material e adapta cores da foto |
| **RLX Auto Fit** | Encaixa roupas no corpo automaticamente | M3: roupas do Asset Bank ajustadas ao corpo gerado |
| **Retopoflow 4** | Retopologia manual/assistida | Pós-escultura (se o fluxo passar por sculpt) |
| **SpeedSculpt** | Blocos de escultura / base meshes | Modelagem assistida no M1 |

## Cabelo (M3)

| Addon | Uso |
|---|---|
| **Braids Generator v5 (CTools Braids)** | Tranças procedurais — variantes de cabelo |
| **HairCard Studio** | Cabelo estilo jogo (cards) — export leve |
| **Pro Hair Suite** | Curvas de cabelo — complemento |

## Física secundária (M5 — peito/glúteos/cabelo, estilo VRM)

| Addon | Uso |
|---|---|
| **JiggleMaker 2.x** (2 versões) + **JiggleGen2** | Física de peito/glúteos/correntes |
| **Goo Physics** / **SquishyFX** | Softbody simples p/ cabelo/roupa |

## Sim e animação (M5)

| Addon | Uso |
|---|---|
| **Cloth Next 2.4** (binário Windows) | Sim de roupa rápida na máquina do usuário |
| **AnimationSnapper Pro** (v1–v2, Blender 5) | Ajuste/snapping de animações |
| **Voxel Heat Diffuse Skinning** | Conserta pesos de skinning (roupa/corpo) |
| **Onion Skinning 3D** | Referência visual de frames na animação |

## Fora do pipeline de personagem (mantidos só p/ referência)

CAD/Seamless CAD (x2), Dovetail Key, Projection Modeling, Palette Grid —
hard-surface/UX, o agent não usa.

## Links pendentes (OutrosMaisPesados.txt)

- **HumGen3D** (superhivemarket) — gerador humano free c/ roupa/cabelo pronto → forte candidato a base alternativa do M1 e fornecedor de roupas pro Asset Bank.
- **MPFB / MakeHuman** — humano paramétrico open-source (se preciso, só os assets).
- **Invisigal (DiSoDS)** — modelo 3D pronto → bom **caso de teste** p/ rig/anim/export.
- **Sanctus Library — Procedural Shaders** — materiais procedurais → texturização M2.
