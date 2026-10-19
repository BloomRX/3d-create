# Asset Bank do Bloom — como alimentar (free e comprado)

A pasta é configurada no painel (padrão `J:\3d-Create\assets`) e tudo que cair
lá é **indexado sozinho** pelo `asset_scan`, com **tags automáticas pelo nome**
(roupa, cabelo, sapato, acessório, saia, calça, chibi). Tags extras? Crie um
`nomedoarquivo.fbx.meta.json` ao lado com `{"tags": ["escola"], "obs": "..."}`.

## Roupas/assets COMPRADOS (a ferramenta VESTE, não recria)
1. Compre onde quiser (Booth, Sketchfab, Superhive, marketplace do autor);
2. Jogue o `.fbx`/`.obj`/`.glb`/`.blend` dentro da pasta do bank
   (ex.: `assets\roupas\camisa_escola.fbx`);
3. No chat do Bloom: "vista a camisa_escola no corpo" — o agent usa
   `adapt_asset` (centraliza, escala pela bbox do corpo, shrinkwrap +
   corrective smooth, parenta ao rig com pesos, marca `bloom_piece`).
Nomeie com a palavra-chave do tipo (shirt/camisa, hair/cabelo…) pra tag bater.

## Assets FREE baixados PELO projeto
- **BLOOM.bat passo 4.5**: lê `plugins/asset_catalog.json` e baixa sozinho
  qualquer entrada com `url` direta + licença **CC0/CC-BY** (nunca baixa coisa
  com licença restrita); registra tudo em `assets/bank/CREDITS.md`.
- **MPFB** (CC0): add-on oficial no Blender com biblioteca de roupas — instale
  em Preferences > Extensions e exporte itens pro bank.
- Catálogo manual (páginas confiáveis CC0): Quaternius, Kenney, Sketchfab
  (filtro CC0). Licença por modelo no VRoid Hub — leia antes.
**Política**: arquivo de asset NUNCA vai pro git (peso+licença) — só probes e
o catálogo. Comprado = seu, local; free CC0 = distribuível, mas baixamos, não
commitamos (o repo continua leve).

## Formatos que o fluxo aceita (asset_scan indexa; adapt_asset importa)

| Formato | Qualidade p/ nós | Detalhes |
|---|---|---|
| **.glb** | ⭐ MELHOR | tudo embutido (malha+material+textura+rig); leve; importa 1-clique |
| **.gltf** | ótimo | idem, mas bin/texturas ficam AO LADO — mova a pasta inteira |
| **.fbx** | ótimo | o mais comum em marketplaces; texturas junto (mesma pasta) |
| **.blend** | máximo | append completo: até shape keys e materiais de nodes sobrevivem |
| .obj | limitado | SEM rig/morphs; precisa do .mtl + texturas na mesma pasta |
| .zip/.rar | — | NÃO indexa: extraia antes e jogue os arquivos |
| .vrm | — | ainda fora do bank (rota de probe apartada); import nativo é upgrade futuro |

**Regra prática**: prefira glb > fbx > blend > obj. Do Quaternius use o **glTF**;
do Sketchfab baixe **glTF**; de CGTrader/Booth, **FBX** (texturas juntas).
