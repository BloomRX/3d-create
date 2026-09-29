# PIPELINE — Bloom Agent (especificação de engenharia)

Este documento é o **plano que o desenvolvimento segue** (referência interna,
não tutorial). Regras de decisão que aparecem aqui estão também codificadas no
`SYSTEM_PROMPT` de `agent/bloom_agent/agent_core.py`.

## 1. Alvo do produto

Personagens 3D para VTuber/jogos (foco inicial: **anime/toon**, mas estilo é
inferido da referência, nunca hardcoded):

- **Personagem = corpo base + peças plugáveis**: cada roupa e cada cabelo é
  malha separada, com o MESMO esqueleto, exportada individualmente.
  O personagem troca de outfit/cabelo sem re-rig.
- **Cabelos**: variantes = shape keys (morph entre penteados, ex.: cabelo
  solto → maria-chiquinhas) + cadeias de ossos próprios por mecha.
- **Consumidores**: Project Airi (VRM + WYPL), Vroid/UniVRM, viewers VRM
  genéricos, UE5 (skeleton MetaHuman) e ferramentas Mixamo.

## 2. Prioridade de geração (regra de ouro do agent)

| # | Método | Onde | Quando |
|---|---|---|---|
| 1 | **Modelar no Blender** (`run_blender_python`: metaballs/curvas + remesh + smooth + shrinkwrap) | local, grátis | sempre tentar primeiro — topologia de jogo nativa (15–30k tris) |
| 2 | **Adaptar asset do Asset Bank** (`asset_import` + shrinkwrap + re-UV + retextura) | local, grátis | peça existe no acervo do usuário |
| 3 | **Face por foto: Blender 3DMM** (fit de modelo facial estatístico; devolve malha + coeficientes FACS) | local, CPU | rosto a partir da foto — o "mais próximo possível" |
| 4 | **Gerador 3D por IA** (Trellis 2 / Hunyuan3D 2.x) | Colab grátis | último recurso: orgânicos complexos, drapejos difíceis |

Motivação: malha de IA é sopa de 100–500k tris (retopo caro, topologia
imprevisível); malha construída pelo agent já nasce no alvo e consistente.

## 3. Master rig (núcleo do projeto)

Uma única armadura **superset**, construída 1x, mapeada por tabelas JSON ao
exportar. Perfis de exportação:

| Perfil | Uso | Naming |
|---|---|---|
| `metahuman` | UE5 / MetaHuman | UE4 mannequin + sub-ossos de cabeça; rosto via **FACS** (blendshapes → parâmetros FACS do MetaHuman) |
| `vroid` / `vrm2` | Project Airi, Vroid, viewers | ossos Vroid/VRM 1.0 + **custom bones VRM 2.0** (seios L/R, glúteos L/R, cadeias de cabelo) + **spring bones** (→ WYPL no Airi) |
| `mixamo` | retarget simples | `mixamorig:*` (7 dedos/3 falanges, sem extras) |
| `custom` | qualquer outro | usuário edita a tabela |

Convenções internas (independentes do perfil):

- **T-pose** obrigatória; corpo 15–30k tris.
- **Rosto = FACS em blendshapes** (~52 AU), nunca ossos de face (portável
  entre VRM 2.0, Vroid e MetaHuman).
- **Extras** (seios, glúteos, cabelo) são ossos avulsos que só aparecem nos
  perfis que suportam (mixamo os descarta).
- Malhas separadas: `corpo`, `cabeça` (se o perfil pedir), cada `roupa_*`,
  `cabelo_*` — shape keys só onde existem (incham arquivo VRM).
- Tabelas: `agent/bloom_agent/mappings/{metahuman,vroid,vrm2,mixamo}.json`
  (criadas no M4; editar um nome de osso = editar 1 linha).

## 4. Estágios (o que o agent executa)

| Estágio | Entrada | Saída | Ferramentas |
|---|---|---|---|
| `referencia` | foto + texto | análise de estilo (anime/semi-real/PBR) proposta ao usuário | visão do Gemini |
| `corpo` | estilo aprovado | malha de corpo rigged (metaballs/remesh ou asset) | run_blender_python, asset_import |
| `rosto` | foto | face 3DMM encaixada + FACS iniciais | (M1) Blender 3DMM |
| `rig` | corpo | master rig + pesos (transferidos da base) + shape keys | run_blender_python |
| `uv_textura` | rigado | UVs + mapas (local: ComfyUI-ZLUDA + SDXL UV-aware + IPAdapter da foto; inpaint por região) | (M2) |
| `peca_roupa` / `peca_cabelo` | foto/operação | peça separada, mesmo esqueleto, UV/textura próprias | colab_job (se IA) + shrinkwrap |
| `shader` | texturas | preset aplicado: **toon anime** (MToon com rampa), semi-real, PBR — portado p/ VRM_MToon e FBX | (M2/M4) |
| `export` | tudo | `.fbx` (perfil metahuman/mixamo) + `.vrm` (perfil vroid/vrm2) por peça | (M4) |
| `anim` (M5) | rig | walk/idle (agent+IK ou motion do Colab) + morph de penteado | (M5) |

**Gates de aprovação**: nos modos, cada estágio termina com resumo + render;
modo *pleno* pergunta antes de seguir (a menos que auto-aprovar esteja ligado);
modo *passo a passo* só avança quando o usuário pede.

## 5. Automação de segurança (pontos de melhoria vs. o vídeo de referência)

1. **Autosave/rollback por etapa**: antes de cada tool, o `.blend` é salvo em
   `stage_backups/` (máx. 20). Botão *Restaurar último backup*. No vídeo de
   referência salvar o arquivo levou ~10 min e travou o fluxo — aqui é
   incremental e silencioso.
2. **Agent vê o que fez**: `render_view` devolve a imagem ao LLM (Eevee 512px,
   câmera na viewport) — correção guiada por visão, não por "confio".
3. **Guard no Python do agent**: sem rede/subprocess/eval — I/O de máquina
   só pelas tools dedicadas.
4. **Orçamento por turno**: máx. 25 tools por mensagem do usuário.
5. **Estilo inferido, não hardcoded**: o Gemini classifica a referência e
   propõe o preset de textura/shader; o usuário confirma ou troca.
6. **Colab como fallback medido**: job JSON + ponte; a cota de 1 GB/mês do
   ngrok free é contornada por rota automática (> 150 MB → Drive).
7. **Asset bank first-class**: pasta local + `index.json` (tags/obs por
   asset); o agent procura por nome/tags antes de gastar IA.

## 6. Hardware (PC do usuário)

| Tarefa | Onde | Por quê |
|---|---|---|
| Blender (viewport, Eevee, ops de modelagem) | local (RX 580, Vulkan) | dá conta com folga |
| LLM (cabeça do agent) | API Gemini free (3–4 chaves = ~6.000 req/dia) | 10 RPM/1.500 RPD por chave; rotação automática |
| Texturas (SDXL) | local — ComfyUI **ZLUDA** (Vulkan/AMD) | 8 GB roda SDXL; Polaris não tem ROCm/PyTorch |
| Geração 3D por IA | Colab (T4 16GB → Hunyuan3D; A100/L4 → Trellis 2) | 12–22 GB VRAM |
| Vídeo (Wan 2.x) — M5 | Colab | VRAM |

## 7. Milestones

| M | Entrega | Aceite | Status |
|---|---|---|---|
| 0 | addon: painel, Gemini (rotação), tools básicas, autosave/rollback, ponte Colab (ngrok+Drive), asset bank | 24 testes locais OK; round-trip Colab↔PC no notebook | ✅ |
| 1 | foto → personagem: 3DMM (face) + corpo procedural + master rig + UV auto | 1 foto → personagem rigged no viewport; usuário só ajusta | ⬜ |
| 2 | texturas/UV editáveis + colar shader (toon/semi-real/PBR) | textura com cara da referência; inpaint de região por chat | ⬜ |
| 3 | roupas + cabelos plugáveis; variantes; morph solto→maria-chiquinhas | 1 personagem × 2 roupas × 2 cabelos, separados e animáveis | ⬜ |
| 4 | export: VRM 2.0 (Vroid, springs, MToon, FACS) p/ Airi + FBX metahuman/mixamo | abre no Project Airi e viewer VRM; UE5 lê o skeleton | ⬜ |
| 5 | anims base (walk/idle) + vídeo Wan de preview | 1 anim jogável + mp4 | ⬜ |

## 8. Pendências de validação (pesquisa pontual durante M1–M4)

- Blender 3DMM: compatibilidade com a versão do Blender do usuário e pipeline
  de fit a partir de foto única (fallback: face procedural + textura).
- Project Airi: versão de VRM aceita (1.0 vs 2.0), requisitos de WYPL
  (naming de spring bones, limites de ossos) e conversão p/ UE5.
- MetaHuman: conjunto exato de parâmetros FACS para o mapeamento `metahuman`.
- Hunyuan3D 2.x / Trellis 2: VRAM real no T4 16 GB e tempo por geração.
