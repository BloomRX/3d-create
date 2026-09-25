# Asset Bank (local, fora do git)

O banco de assets **não vai no repositório** (é pesado). Ele fica numa pasta
locais do seu PC, cujo caminho você configura no painel do addon
(Preferences → Bloom Agent, ou botão "Configurar pasta" no painel).

## Estrutura esperada

```
D:\3d-create-assets\            <- a pasta que você apontar
├── cabelos\
│   ├── longuinho.glb
│   ├── longuinho.meta.json     <- { "tags": ["anime", "feminino", "longo"], "obs": "..." }
│   ├── maria_chiquinhas.glb
│   └── maria_chiquinhas.meta.json
├── roupas\
├── acessorios\
├── corpos\
└── index.json                  <- GERADO automaticamente pelo botão "Varrer pasta"
```

- Formatos aceitos: `.glb`, `.gltf`, `.fbx`, `.obj`, `.blend`.
- Cada arquivo pode ter um `.meta.json` ao lado com `tags` (lista) e `obs`
  (texto livre). Sem meta.json o asset entra sem tags.
- **index.json** é regenerado a qualquer momento pelo botão "Varrer pasta" —
  nunca edite à mão.

O agent lê o `index.json` (é leve) e importa o arquivo pelo nome via
`asset_import`. Nada dos assets passa por rede: tudo é local.
