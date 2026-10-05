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
