# plugins/ — zips dos plugins (instalados pelo BLOOM.bat)

Os 4 externos (SKkeeper, Wiggle 2, mmd_tools, VRM Addon) já estão
empacotados aqui, no mesmo formato das releases oficiais.
O **BLOOM.bat** instala tudo daqui automaticamente — **todos DESLIGADOS por
padrão** (regra do projeto: o agent diz o que ligar em cada milestone).
Uso pessoal/estudo; não redistribuir.

**Auditoria out/2026 (agent):** versões verificadas nas fontes oficiais;
removidos: Jiggle_Maker_2_0 (duplicado — ficou o 2.2.2), jigglegen2.rar
(.rar não é instalável — se precisar, extrair e zipar localmente),
onion_skinning_3d (sem papel no pipeline; Grease Pencil nativo + motion paths
cobrem o estudo), BlendAuUn (propósito incerto, sem marco no roadmap).

| Plugin no repo | Versão | Veredito da auditoria | Milestone |
|---|---|---|---|
| SKkeeper | 1.8.2 | ✅ atual (2025, GPL) | M2/M3 |
| Wiggle Bones | 1.1.2 | ✅ atual (set/2026; substitui o Wiggle 2 abandonado) | M5 |
| mmd_tools | 4.5.14 | ✅ atual (set/2026) | estudo MMD |
| VRM Addon | 4.10.2 | ✅ atual (out/2026; oficial 4.2–5.3) | M3/export |
| SquishyFX | 3.3.0 | ✅ atual — requer Blender 5.1–5.2 (o seu!) | M5 |
| Voxel Heat Diffuse Skinning | 3.5.3 | ✅ última oficial (abr/2024); ⚠️ homologada só até 4.2 — se reclamar no 5.2, nosso plano B (Data Transfer + Corrective Smooth, receita 2AM) cobre | M3 |
| RetopoFlow | 4.0.2 | ⚠️ existe 4.3.0 PAGO c/ suporte 5.2 — se a sua reclamar no 5.2, alternativa GRATUITA oficial: 3.4.9 no GitHub da CG Cookie (suporta 5.0) | M2/M3 |
| Stylized Asset Suite | 4.0 Pro | ⚠️ existe 4.2 Pro PAGO (dez/2025) — troque o zip aqui se um dia adquirir | M2/M3 |
| SUPERTABs | 1.3.0 | ⚠️ existe 1.3.3 PAGO (testada 4.2–5.2) — UX, baixa prioridade | — |
| Jiggle Maker | 2.2.2 | ✅ atual (gumroad lewdineer) | M5 |

> Política: eu NÃO baixo versões pagas de sites não-oficiais. Se você possui
> uma licença e atualizar algum zip, é só substituir aqui e rodar o BLOOM.bat.

Referências de estudo (modelos/texturas) ficam em `assets/learn/`.

> **Nota sobre o Wiggle 2:** o original (shteeve3d, `wiggle_2.py`) foi
> abandonado em 2023 e não suporta Blender 4.2+. Substituído pelo
> **Wiggle Bones** (Hans_Xwh, refactor oficialmente corrigido p/ Blender 5,
> mantém o comportamento da física e traz migração de settings antigos).
> Alternativas conhecidas, caso um dia precisemos: "Wiggle 2: RTX Edition"
> (reescreva completa, 4.2+) e "Jiggle Physics" (naelstrof, algoritmo Verlet).
