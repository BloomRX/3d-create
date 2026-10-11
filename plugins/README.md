# plugins/ — zips dos plugins (instalados pelo BLOOM.bat)

Os 4 externos (SKkeeper, Wiggle 2, mmd_tools, VRM Addon) já estão
empacotados aqui, no mesmo formato das releases oficiais.
O **BLOOM.bat** instala tudo daqui automaticamente — **todos DESLIGADOS por
padrão** (regra do projeto: o agent diz o que ligar em cada milestone).
Uso pessoal/estudo; não redistribuir.

| Plugin | Uso previsto | Milestone |
|---|---|---|
| SKkeeper ✅ incluído | aplicar mods mantendo shape keys | M2/M3 |
| Wiggle Bones 1.1.2 ✅ incluído | física de mola por osso (refactor do Wiggle 2, mantido; oficial Blender 4.5+) | M5 |
| mmd_tools ✅ incluído | importar PMX/MMD (probes #7) | estudo |
| VRM Addon ✅ incluído | importar/exportar VRM + probe de .vrm | M3/export |
| JiggleMaker / jigglegen2 / SquishyFX | física de peito/glúteos/cabelo | M5 |
| Voxel Heat Diffuse Skinning | conserto de pesos de skinning | M3 |
| Retopoflow 4 | retopologia assistida | M2/M3 |
| BlendAuUn | utilitário de .blend | sob demanda |
| SUPERTABs | UX (não prioritário) | — |
| Stylized Asset Suite | bases/materiais estilizados | M2/M3 |
| onion_skinning | referência de animação | M5 |

Referências de estudo (modelos/texturas) ficam em `assets/learn/`.

> **Nota sobre o Wiggle 2:** o original (shteeve3d, `wiggle_2.py`) foi
> abandonado em 2023 e não suporta Blender 4.2+. Substituído pelo
> **Wiggle Bones** (Hans_Xwh, refactor oficialmente corrigido p/ Blender 5,
> mantém o comportamento da física e traz migração de settings antigos).
> Alternativas conhecidas, caso um dia precisemos: "Wiggle 2: RTX Edition"
> (reescreva completa, 4.2+) e "Jiggle Physics" (naelstrof, algoritmo Verlet).
