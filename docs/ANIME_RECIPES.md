# Receituário estilo anime 3D (padrão estúdio — WuWa/Hsin)

Fonte: "A Pro Anime Game Studio Sent Me Their 3D Models" (Vertex Arcade,
out/2026) — dissecou o modelo OFICIAL da Hsin (Kuro Games/Wuthering Waves).
Cada técnica: o que é, como o Bloom Agent implementa (determinístico, sem
LLM por passo), e a que milestone pertence.

## 1. Sombreamento de rosto — M2 (shader toon)

| Técnica | O que é | Implementação do agent |
|---|---|---|
| **Custom normals via face shell** ✅ | Rosto fica "liso" (sem sombras feias de nariz/boca): cria uma casca suja ao redor do rosto e COPIA as normais dela (modifier Data Transfer > face corner > custom normals) | `run_python`: duplicar rosto → subir/moldar casca → Data Transfer → apply. 100% scriptável, ~30 linhas. **Entrar no "colar shader"** |
| **SDF de sombra facial** ⭐ (avançado) | Textura Signed-Distance-Field com as posições da sombra conforme o sol gira; driver no ângulo do sol escolhe a faixa do gradiente | Fase 2 do M2: gerar máscaras (paint ou inferir) + conversor (numpy no próprio Blender). V1 usa só custom normals; SDF é o upgrade de qualidade |
| 3 níveis: normais default / custom normals / SDF | trade-off esforço×qualidade | agent pergunta/infere pelo estilo pedido |

## 2. Outlines — M2

Receita oficial (a do vídeo): modifier **Solidify** com `offset=1` + **Flip
Normals** + material **Background** (cor chapada) + **backface culling**.
Variação de espessura (fino no rosto/franja, grosso em roupa/cabelo) via
**vertex group** no thickness do solidify.
→ `run_python`: cria modifier + material outline + pesos por região.
Totalmente automatizável. **Entrar no "colar shader".**

## 3. Materiais — M2

Estilo WuWa: cores chapadas + rampas de luz + specular controlado
(anel de brilho no cabelo). Base = nosso "colar shader" (Genshin Shader
blend que o usuário mandou) + esses parâmetros por região (pele/olho/
cabelo/roupa/metal). Agent ajusta cores a partir da referência.

## 4. Pelo (fur) shell-based — M3 (cabelo/detalhes)

Pêlos de roupa/pele como **cascas interpoladas** (não hair particles):
duplicar malha N vezes com offset pequeno + alpha.
→ `run_python`: gera cascas de um vertex group ("regiões de pelo").
Cabelo principal continua = meshes card/triângulo (padrão WuWa também).

## 5. "Revealing What's Underneath" — M3

Camadas empilhadas com ordem de render/máscaras (corpo sob roupa sem
interpenetrar visivelmente): separar peças + ocultação por camada.
→ Já é nosso design de PEÇAS SEPARADAS; técnica = shrinkwrap leve +
offsets de espessura para evitar z-fighting.

## 6. Olhos visíveis através do cabelo — M3

Truque do WuWa: franja com **alpha/máscara na altura dos olhos** (ou
duplicado de cílios/franja com material invisível na câmera frontal).
→ `run_python`: máscara UV na franja; opcional "olhos ghost" p/ render.

## 7. Shape keys — 3 usos — M1/M5

O modelo oficial usa shape keys para: (a) expressões faciais, (b)
correções de deformação (muscle/jiggle fix), (c) ajustes de peça.
→ Confirma nosso desenho: FACS por shape keys (já no prompt) +
correction keys pós-rig (M5).

## 8. Rig da Hsin — M1/M5

Capítulo 13:51 (transcrição incompleta na fonte). Padrão esperado de
WuWa: esqueleto humano padrão + twist bones + dedos + ossos de cabelo/
peça + correções. Nosso superset canônico cobre; ossos de cabelo entram
como cadeias extras por peça (M3/M5). **Pedir resumo do usuário** se
quiser espelhar detalhes.

## Priorização no projeto

1. **Agora (M2 "colar shader" v2):** custom normals do rosto + outlines
   solidify c/ espessura variável + materiais por região. Zero cota,
   puro bpy — vira UMA tool `apply_anime_shader(reference_colors)`.
2. **M3:** fur shells, olhos-atrás-da-franja, camadas.
3. **M5 upgrade:** correction shape keys pós-rig + SDF facial.

## Vídeos relacionados úteis (detectados na mesma sessão)

- "3D AI Models Are Finally Watertight (6GB VRAM, Free & Local)" —
  desvio A (imagem→3D local/Colab), checar método depois.
- "I Studied How Guilty Gear Makes 3D Look Perfectly 2D" (Noggi) —
  técnicas toon complementares (bone-driven face posing).

## PROBE — achados reais do modelo Hsin (texturas em assets/learn, out/2026)

Analisadas com decodificador PNG (uso de estudo — métodos, não assets):

1. **SDF facial** (`T_FemaleMFace_SDF.png`, 1024²): CONFIRMADA a estrutura de
   **ilhas por região** (testa/nariz/bochechas/boca/queixo) em magenta puro
   (#ff00ff) sobre branco, com gradientes de anti-alias entre elas. O shader
   usa o ângulo do sol p/ amostrar a faixa certa. Nosso plano: v2 do
   `apply_anime_shader` inclui gerador de SDF (máscaras pintadas → gradiente).
   Magenta provavelmente marca zona "especial" (fluxo/ativação), branco = luz.
2. **LUT global** (`LUT_WUWA.png`, 1024×32 RGBA): **alpha=0 em TODOS os
   pixels** (textura de DADOS, não imagem). RGB = atlas de rampas com ~190
   níveis — cada material amostra sua LINHA (sombras coloridas, não
   preto→cor). Lição p/ nosso toon: **sombras com matiz deslocada**
   (azuladas em pele clara, escuras saturadas em roupa) em vez de
   multiplicação por 0.55 — ajustar os defaults do `apply_anime_shader`.
3. Texturas por peça: Face/Eye/Hair(Bangs)/Up/Down/Cloth com sufixos
   _D (difusa), _N (normal), _FTM/_HM/_HN (máscaras de lightmap/hair),
   _RGID — confirma o pipeline de MÁSCARAS por canal, não só cor.
4. MatCapAtlas, Face_Blush, EyesSecondHighlight — detalhes de acabamento
   facial (bochecha/brilho de olho) — fase 2 do rosto.

### Ação imediata incorporada
- `apply_anime_shader`: sombras com hue-shift (2x parâmetro `matiz_sombra`);
- backlog: gerador de SDF + atlas de rampas por material (M2 fase 2).

### Proveniência e liberação (out/2026)
O SDF facial (`T_FemaleMFace_SDF.png`) e a LUT são **criações genéricas do
youtuber** para simular o estilo do jogo (não são assets do Wuwa) — uso
liberado pelo autor do repo como base/exemplo. Texturas mantidas em
`assets/learn/Aplaybox_Hsin/textures` como referência do pipeline. Plugins
movidos p/ `plugins_src/` (o agent pode modificá-los — uso privado).

## PIPELINE RÁPIDO — Stefan 3D AI, "From Idea to Game in ONE Day" (06/out/2026)
Fonte: youtube.com/watch?v=CgslUZIAl4s (13:15; seções de rig/animação/VFX
7:30+ NÃO estavam na transcrição pública — revisitar depois).

1. **Separação de peças ANTES de gerar** (essencial p/ animação): head, body,
   legs, armor, accessories, hair, wings — tudo em **A-pose** antes da geração.
   → valida nossa arquitetura (roupas/cabelos exportados separados).
2. **Tripo P2 + Smart UV**: 1 geração devolve **4 variantes de poly-count**;
   escolher a melhor densidade/wireframe; UV "smart" ANTES de texturizar é o
   que HABILITA editar mapas por cima (normal/roughness/metallic gerados
   depois). 4 retries → escolher o melhor layout de UV.
3. **Hack das asas** (peças muito detalhadas): NÃO gerar o 3D a partir da
   imagem com detalhe proeminente (o gerador vira cada pena em geometria);
   gerar com imagem "acalmada" → 3D com wireframe limpo → TEXTURIZAR com a
   imagem detalhada → normal map derivado do color map.
4. **Mapas por IA a partir do color map**: normal/roughness/metallic/emission
   gerados por modelo de imagem (API) — sem sculpt high-poly nem bake.
   Substitui o pipeline high→low→bake p/ personagens de jogo (não-cinema).
   → candidato direto pra nossa etapa de texturas (M4) com ComfyUI-ZLUDA.
5. **Montagem manual 12 min** (ele mesmo diz: agent até faz, mas 1–2h e
   tokens; Elastic Grab resolve ajuste de encaixe) — confirma nossa tese:
   determinístico no Blender + agent nos passos de risco/visão.
6. Modelos citados: GPT-6 Astra, Opus 5.5 (multimodais pagos).

**Leads relacionados (mesma busca):** "AI Can Do Everything in Blender Now —
Mixar" (Z8xhELifAVs, fork do Blender com IA espacial — vigiar de perto);
"New Open-Source AI Animation is Here!" (x-WSSlHNcJQ, PixelArtistry+Stefan —
M5); "3D AI Models Are Finally Watertight (6GB VRAM, Free & Local)"
(dmDrktqyT5o — desvio A local); "Easy Clothing with AI for Any Character"
(gSHON893CCI — roupas, requisito nosso #3).

## PROBE — DNA dos 5 modelos reais (raio-X out/2026, arquivos em util/model_probe_*.json)

### Aplaybox_Hsin (WuWa, produção real — MODELO-DE-OURO)
- Blender 5.2.2 LTS | 133 meshes | 117k tris | 59 materiais | 112 drivers | EEVEE 1440×2560@24.
- **2 armaduras**: `R2T1XinMd10011_LOD0_Skeleton` (498 ossos, jogo) + `RIG-…` (823, **Rigify**
  por cima: ORG-/MCH-/VIS/tweak) → padrão: **esqueleto do jogo + Rigify como controle**.
- Nomes: **Bip001** (export 3ds Max Biped) + Bone_* (289) + Facial (29) + ZSpring (10, molas).
- **Twist**: UpArmTwist ×3 segmentos, ForeTwist ×2, HandTwist, ThighTwist ×2, CalfTwist —
  por lado. NOSSO SUPERSET precisa disso (decidido).
- **80 shape keys = biblioteca canônica de expressões**: B_* (sobrancelha, ±L/R + Add),
  E_* (olho: Close/Smile/Squint/Anger/Sad/Focus/Insipid/Stare), Pupil_* (8 direções + Scale),
  M_* (boca: Smile/Ennui/Squint/OpenSmall/Laugh/Scared/ScaredTooth/Anger/Puff/Trapezoid/O),
  **visemas Aa/A/E/I/O/U/UTooth** (lip-sync pronto!), Default.
- **Outlines = GEOMETRY NODES** (`Outline`, `Outline By Distance`, `Outline And Rim`,
  `Outline And ShrinkWarp`) + material `Outline` = EMISSION + NEW_GEOMETRY(backfacing) +
  MIX w/ TRANSPARENT (blend BLEND). **ZERO SOLIDIFY no arquivo.**
- **Face**: mat `Gathering Wives - Face Xin` = Face_D + Face_HET + **T_FemaleMFace_SDF.png** +
  Face_Blush + 8 node GROUPS + ATTRIBUTE(máscaras) — SDF facial CONFIRMADA em produção.
- **Hair Xin**: _D+_FTM+_HM+_HN + SEPARATE_COLOR + ATTRIBUTE + 7 groups (sufixos que já temos!).
- **Fur**: geonodes `FurImprove` no corpo (shells). **Custom normals**: mod DATA_TRANSFER
  "Custom Normal" (shell de face). 12 NODES no total.
→ DECISÕES: (1) shader v2.5 ganha outline modo "backfacing" (emission+mix, sem modificador)
  além do Solidify; geonodes por-distância = fase 3. (2) Nosso rig canônico: twist conforme
  acima; controle via Rigify; export no esqueleto do jogo. (3) Vocabulário de expressões:
  adotar Hsin como biblioteca-alvo (map p/ FACS abaixo). (4) SDF/LUT/blush = fase 2 do shader.

### Invisigal_v1_3 (Genesis 9 toon — kit facial overlay)
- 52 meshes | 384k tris | 53 materiais | 238 drivers | 497 ossos (24 twist) — esqueleto **Genesis 9**.
- **FACS shape keys** (`facs_BrowDownLeft`, `facs_bs_EyeBlinkLeft`, `facs_bs_MouthSmileLeft`,
  língua completa, JawOpen…) repetidas em CADA mesh overlay toon: Brows Paint, Eye Socket,
  Eyelashes, **Floating Iris** (2 keys: dilata), Mouth, **Shadow Plane** (sombra do rosto!).
- **Roupas**: SURFACE_DEFORM×19 + CORRECTIVE_SMOOTH×8 (pilha roupa-sobre-corpo).
- **Outline por MATERIAL** (14 nós): EMISSION + TRANSPARENT + MIX×2 + NEW_GEOMETRY +
  LIGHT_PATH — um por peça (body/jacket/top/hair) p/ espessura por parte.
- Cabelo com **UDIM** (hair_BaseColor.<UDIM>.png); olhos: eye.png + HUE_SAT + ADD_SHADER.
→ DECISÕES: (5) receita de roupa separada = SURFACE_DEFORM + CORRECTIVE_SMOOTH (+SHRINKWRAP
  quando precisar) — entra no M3. (6) FACS = segundo vocabulário suportado; map Hsin↔FACS/ARKit.
- Obs: Artist_a1 = base com morphs de corpo (Thicc, Plane breast…) + rig 612 (.l/.r, _twk)
  + PARTICLE_SYSTEM(4) p/ cabelo + CLOTH(2) → cabelo por partículas segue vivo como alternativa.

### modular_female_base (segunda base modular — NOMES RIGIFY!)
- 135 meshes | só 5.6k tris | 2 materiais | 74 ossos com nomes **Rigify puros**
  (spine.001, shoulder.L, upper_arm.L, palm.01.L, f_index.01.L…) + **controles-slider**
  (UI_Panel, Body_Type, Hip_Wide, Tall_Short, Breast_Size, Head_Size…).
→ DECISÕES: (7) CONFIRMA a arquitetura Bloom: base modular + sliders de proporção +
  Rigify; nossos _BODIEZ_PAIRS já falam a língua certa (Hip_Wide/Breast_*). (8) AssetBank:
  aceitar esta base como segunda base física (leve, 5.6k tris).

### SquishBulge_GeoNodes (estudo M5)
- 7 ossos (Thighs_Rig) + NODES×3 + SOLIDIFY×6 → bulge suave por geometry nodes, sem simulação.
→ DECISÃO: (9) M5: efeitos de "carne" via geonodes dirigidos por osso (barato, sem bake).

## RIG ANIME COMPLETO — 2AM "How to Rig EVERYTHING" (blgGcbZzsWM, 509K views, mai/2023)
A seção de rig que FALTAVA no dossiê (Hsin não narrava rig). Canal 2AM
(@2amgoodnight). Receita extraída da narração:

- **Cabelo — preparação**: separar partes MÓVEIS (franja) das estáticas;
  fechar pontas recortadas (preencher face + bridge edge loops) →
  **voxel remesh** → **decimate** (tri→quads opcional). Motivo: clipping
  entre mechas quebra o auto-weights; remesh elimina vértices internos.
- **Rosto = SHAPE KEYS, sem ossos faciais** (mesma decisão do Hsin!);
  no metarig: DELETAR face bones e extrusar 1 osso de cabeça extra.
- **Corpo**: Metarig humano escalado/rotacionado; ossos de peito empurrados
  pra frente (acompanhar a forma); dedos conferidos em múltiplos ângulos.
- **Regras de weight paint (AUTOMATIZÁVEL — futura tool `auto_weights_anime`):**
  1. dedos/pé: vermelho total no osso do pé;
  2. peito: osso Breast só no seio (subtract geral → add só a região);
  3. **segredo anti-jiggle: passada de subtract com strength 0.7 no peito**
     (amortece a física — regra determinística!);
  4. pescoço: subtract FULL no crânio E no interior da boca (dentes/língua);
  5. cabeça: tudo vermelho, INCLUINDO olhos externos/peças (auto-rig pega).
  6. cabelo estático: parented ao osso da cabeça, 100% vermelho.
- **Roupas: auto-rig via DATA TRANSFER do corpo** (+consertos manuais) —
  a MESMA técnica do arquivo WuWa/Hsin. É o padrão da indústria; entra
  na nossa tool de roupas (M3) junto de SurfaceDeform+CorrectiveSmooth.
- Correntes/strapas: ossos extras dedicados. Cabelo móvel: ossos próprios +
  combinar rigs. Saia: seção dedicada (ossos em anel).
- **Física**: Blender = addon **Wiggle 2** (github shteeve3d/blender-wiggle-2,
  grátis, spring physics por osso SEM simulação/bake — ideal p/ RX 580);
  **VRM/Unity = UniVRM spring bones** (padrão VRM!) → blueprint direto do
  nosso perfil de export vrm2: ossos de física viram SpringBones no VRM.
- Leads: 2AM "Secret 3D Jiggle Physics — 4 Bones" (jk8_7dqoTv8, M5);
  2AM playlist processo completo + "Make Hands EASY" (3CTSpfS_gCo);
  Noggi: rigging basics + "Hair Bone Generator" grátis (80.lv, set/2026).

## WULONG3D — timelapse "Arcana" (D4R8_UsavtE, 10/out/2026, 1h32)
Timelapse SEM narração (nada verbal p/ extrair). O valor está na estrutura:
- Ordem do workflow: Face → Body → Hair → Cloth → **Texture (59 dos 92 min!)**
  → Rigging (5min) → Blend shapes (6min) → Showcase no **Warudo** (app de
  VTuber/puppeteering = alvo realtime VRM). Confirma: texturas = a parte
  longa (onde nosso agent+ComfyUI mais economiza tempo).
- **MODELO COMPLETO DISPONÍVEL P/ DOWNLOAD** (Google Drive na descrição)
  com rig + blend shapes — candidato a PROBE #6: personagem anime realtime
  (Warudo/VRM) feito por artista solo → exatamente nosso perfil-alvo.
  → AÇÃO: usuário baixa, roda o probe_modelo.bat e envia o JSON.

## RADAR — arsenal 2AM enviado pelo usuário (out/2026) + ferramentas
Prioridade de extração de transcrição (alta→baixa):

1. **PjNtczZzSBk — "Reverse Engineering WuWa's Premium Look + Angel Ring"** (2AM)
   → técnica do ANGEL RING (anel de brilho do cabelo anime) + look WuWa.
   COLIDE DIRETO com nosso apply_anime_shader (fase 2). PRIORIDADE MÁXIMA.
2. **-Ot5TzGMwrA — "Perfect 3D Shadows Like Genshin & Wuwa (Free Shader!)"** (2AM)
   → shader GRATUITO com sombras Genshin/WuWa — referência/validação do nosso
   toon por rampa + hue-shift. Comparar abordagens nó-a-nó se possível.
3. **Anw8vuEX9xU — "Face SDF Generator" (MeshBites)** → GERADOR de SDF facial!
   É exatamente a nossa "fase 2 do shader" (gerar SDF própria em vez da
   recreação genérica). Estudar método (provavelmente bake de distância).
4. **Qyrz4JoMP28 — "Blinking & Lip Sync + Final EXPORT"** (2AM) → piscada,
   lip-sync e passos de EXPORTAÇÃO (provavelmente VRM) — alimenta M3/M5.
5. **75ujnFHAaHQ — "20+ details I noticed" (2AM)** → catálogo de detalhes de
   modelos de estúdio — checagem de qualidade p/ M1/M2 (proporções/estilo).
6. **NO7a5AUef7U — "Beautiful 3D Bodies Like a Pro"** (2AM) → modelagem de
   corpo — alimenta proporções do M1 e a base do AssetBank.
7. **3guG5h5jX-E — "Beautiful 3D Hair"** (2AM, playlist processo completo
   PL2BaVeFyzn9U77sZmVX478-mJ6wuAYuzD) → método curves p/ cabelo (M2/M3).
8. **L0WyWY4pmvs — "Feet." (2AM)** → pés (ponto cego clássico de rigs anime).

### FERRAMENTAS (regra: tudo desabilitado por padrão; habilito por milestone)
| Tool | O que é | Quando habilitamos |
|---|---|---|
| **SKkeeper** (smokejohn, GPL, v1.8.2) | Aplica modificadores MANTENDO shape keys (3 ops no menu Object; limitações com Decimate/Weld) | **M2/M3** — crítico: aplicar proporções/roupas sem destruir as 80 shape keys de expressão |
| **Wiggle 2** (shteeve3d) | Física de mola por osso, sem bake | M5 (física cabelo/peito) |
| **mmd_tools** v2.10.3 (MMD-Blender) | Import/export PMX (MikuMikuDance): morphs, física rigid-body | Estudo de modelos MMD (abaixo) e bases MMD; não entra no produto final |

### MODELOS MMD OFICIAIS — HoYoLAB 33521446 (UnknownStar)
A HoYoverse distribui OFICIALMENTE modelos MMD dos personagens de **Zenless
Zone Zero** (páginas bilibili "blackboard/era"; zips diretos nos comentários).
Inclui **Astra Yao 1.5** (a nossa referência "Astra"!) + Ellen, Miyabi,
Burnice, Jane Doe etc. Uso regido pelas MMD Guidelines da HoYoverse
(não-comercial) — serve a ESTUDO igual nosso dossiê atual.
**PROTOCOLO:** NÃO commitar os modelos (peso+licença) — apenas o probe JSON.
Fluxo: baixar zip PMX → importar no Blender COM mmd_tools → salvar .blend →
probe_modelo.bat → enviar JSON. Isso vira probe #7 (modelo oficial HoYoverse,
física MMD, morphs PMX — comparação com WuWa/Hsin).

### VÍDEO STefan 3D AI — CFA8Pfw6OIs "Modular 3D Character Without Blender" (out/2026)
O autor testou o **agente V5 do AssetHub.io** (vídeo = paid partnership, publi
editorializada — tratar afirmações com ceticismo; NÃO vira dependência).
Conceito: você dá 1 conceito/foto e o agente (a) divide o personagem em peças,
(b) gera cada peça com o modelo de IA que LHE CONVÉM, (c) escolhe o polycount
de cada parte, (d) monta tudo. É EXATAMENTE o Bloom Agent vendendo como
serviço na nuvem — validação de mercado do que a gente constrói de graça,
local, no PC do usuário. **O que roubamos do método** (ideias, não produto):
1. **Roteamento POR PEÇA**: cada peça (cabelo/roupa/acessório) pode usar um
   gerador diferente — nosso Router já roteia por payload; M5 pode estender
   para "por peça, escolhe gen3d vs modelagem vs AssetBank".
2. **Polycount automático por peça**: nosso export profile já tem 15–30k no
   corpo; falta orçamento POR PEÇA no M3 (roupa 3–8k, cabelo 5–15k, acessório <2k).
3. **Montagem automática por pontos de encaixe**: peças nascem na bbox da
   peça-alvo (v0.3.7 já põe na cabeça real; formalizar "sockets" por osso no M3).

### BÔNUS DA BUSCA — stack 100% FREE do mesmo autor (TkP-_LyacMI, fev/2026)
Hy3D (Hunyuan3D, multiview) + Blender (montagem) + Modddif (textura IA) +
Mixamo (rig) — "game-ready em 1h, zero assinatura". Mapeado:
- **Hy3D multiview** → candidato a SUBSTITUIR/compor o Trellis no colab gen3d
  (M5): multiview a partir da foto de referência = mais fidelidade de peça.
- **Modddif** → textura IA grátis (requisito 5 — texture+UV, M4).
- **AccuRIG** (outro vídeo do canal, mai/2026: Tripo 3.1 + AccuRIG + UE5) →
  auto-rig grátis; comparar pesos com o rig_human nosso (M2) — se os pesos
  do AccuRIG ganharem, vira receita de export (FBX → Mixamo compatível).
Regra mantida: métodos OK por licença; personagens/outputs de terceiros NUNCA
commitados; nada pago entra (AssetHub = referência de produto concorrente).

### VÍDEO 3d8u3fJJrMg — "Blender's NEW Character System" (Avatar Creator, out/2026)
NÃO é sistema oficial da Blender Foundation: é o **Avatar Creator** (avcsuite.com,
suíte PAGA — política: métodos OK, produto não entra). O que ele vende e o que
INSPIRA:
1. **AVC Wrap**: trazer malha externa (scan, mesh de IA) e "wrapar" numa
   TOPOLOGIA CONSISTENTE editável ("one topology, unlimited characters") —
   é EXATAMENTE o que falta pro nosso gen3d do Colab: malha suja do Trellis/
   Hy3D → wrap na topologia do corpo base → vira personagem editável
   (**M3/M4**: receita shrinkwrap+Data Transfer+retopo parcial sobre base fixa).
2. **Sync nativo MetaHuman / Genesis 9**: transferir FORMA e TEXTURA em passos
   separados para a base nativa do host — nosso set_export_profile hoje só
   renomeia ossos; o passo 2 real é "transfer shape para a base MetaHuman"
   (**M2/M3**: shape keys do corpo → alvos da base do host + bake de textura).
3. Pacote dele (150+ morphs, cabelo geonodes, 50+ roupas auto-rig, Rigify+Face
   Widget) = confirma nosso desenho: corpo base paramétrico + peças + Rigify.

### ACHADOS GRÁTIS da mesma busca (candidatos a base de corpo)
- **MPFB 2.0.18** (MakeHuman, GRÁTIS, extensions.blender.org, Blender 4.2+,
  out/2026): gerador humano paramétrico + Rigify + materiais procedurais +
  biblioteca de roupas/peças. Candidato a SUBSTITUIR o manequim de primitivas
  do spawn_base_body quando o AssetBank estiver vazio (**M1.5**: add-on fica
  DESLIGADO por padrão; habilito só nesse caminho).
- **CharMorph v0.4+** (open source, sucessor do MB-Lab, modelo CC0 "Vitruvian",
  Blender 4.4): personagem realista paramétrico GRATUITO e licença limpa p/ jogo
  comercial — segunda opção de corpo-base de qualidade zero-custo.
Regra mantida: nada pago/pirata (site de crack do CC5 que apareceu na busca:
IGNORADO por política — CC5/Headshot 2 ficam só como referência de método).
