# util/ — utilitários de apoio (a saída daqui o agent lê no repo)

## probe_modelo.bat — raio-X de QUALQUER .blend (2 cliques, sem abrir o Blender)

Gera o `model_probe_<personagem>.json` que o agent precisa para estudar um
modelo: ossos, shape keys, modificadores, materiais/nós/texturas, UVs,
drivers, render. **Funciona com qualquer personagem** — Hsin/WuWa ou de
outros jogos do mesmo autor; quanto mais modelos mapeados, melhores as
receitas genéricas do agent.

**Como usar:**
1. Dê dois cliques em `util\probe_modelo.bat` (ele só chama o
   `probe_modelo.ps1`, onde vive toda a lógica).
2. Ele acha o Blender sozinho: PATH, Program Files (5.2→4.2),
   **Steam/SteamLibrary em qualquer disco** e bibliotecas cadastradas
   (libraryfolders.vdf); se não achar, pergunta o caminho.
3. A lista de .blend (banco `J:\3d-Create` + Desktop/Downloads/Documentos,
   mais recente primeiro) abre numa **janelinha de seleção do Windows**
   (colunas Nº/Modificado/MB/Caminho). Sem essa janela, vira menu
   numerado no console. Você sempre pode **colar o caminho** ou
   **arrastar o arquivo** pra dentro da janela.
4. Cada modelo gera **seu próprio** relatório `model_probe_<nome>.json`
   em `util\` (não sobrescreve). Pode rodar várias vezes.
5. Ao fim pergunta se já envia pro repo → **Enter = sim**
   (commit+push pelo project_cli, mesmo mecanismo do DevKit).
6. Volte na conversa e escreva: **"probe enviado: \<nome do personagem\>"**.

**Modo manual (alternativo):** abrir o .blend no Blender, workspace
Scripting > Open > `tools\model_probe.py` > ▶.

> O .blend nunca vai pro repo — só os relatórios JSON (alguns KB cada).

## instalar_plugins.bat — instala os plugins do repo no Blender (2 cliques)

Instala todos os `.zip` de `plugins_src\` e `assets\learn\` no seu Blender
(achado sozinho, Steam inclusive). **Todos ficam DESLIGADOS por padrão** —
eu digo qual ligar em cada milestone (regra do projeto).

- Já instalado? Ele avisa e pula. `.rar` é pulado (extrair antes).
- Novo plugin? Solte o `.zip` em `plugins_src\` e rode o .bat de novo.
  Fila sugerida: SKkeeper, Wiggle 2, mmd_tools, VRM Addon for Blender.

## .vrm (ex.: Arcana do Wulong) — suportado pelo probe_modelo.bat

O menu agora lista `.blend` **e** `.vrm`. Escolheu um `.vrm`? Ele importa
com o **VRM Addon** (só nessa sessão; o addon continua desligado) e faz o
raio-X normal, gerando o `model_probe_<nome>.json`.
Se o addon VRM não estiver instalado, ele ensina na tela: baixe o zip
(github saturday06 / VRM Addon for Blender) → `plugins_src\` →
`instalar_plugins.bat` → probe de novo.
