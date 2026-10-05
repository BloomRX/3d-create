# util/ — utilitários de apoio (a saída daqui o agent lê no repo)

## probe_modelo.bat — raio-X de QUALQUER .blend (2 cliques, sem abrir o Blender)

Gera o `model_probe_<personagem>.json` que o agent precisa para estudar um
modelo: ossos, shape keys, modificadores, materiais/nós/texturas, UVs,
drivers, render. **Funciona com qualquer personagem** — Hsin/WuWa ou de
outros jogos do mesmo autor; quanto mais modelos mapeados, melhores as
receitas genéricas do agent.

**Como usar:**
1. Dê dois cliques em `util\probe_modelo.bat`.
2. Ele acha o Blender sozinho e lista os .blend encontrados no banco
   `J:\3d-Create` e nas pastas de usuário (mais recente primeiro).
3. **Digite o número** do personagem que quer escanear.
   - Prefere outro arquivo? **Enter** = colar caminho, ou **arraste o
     .blend pra dentro da janela preta**. Arrastar direto em cima do .bat
     também funciona.
4. Cada modelo gera **seu próprio** relatório em `util\` (não sobrescreve
   os outros). Pode rodar o .bat várias vezes, um personagem de cada vez.
5. Ao fim ele pergunta se já envia pro repo → **Enter = sim**
   (commit+push pelo project_cli, mesmo mecanismo do DevKit).
6. Volte na conversa e escreva: **"probe enviado: \<nome do personagem\>"**.

**Modo manual (alternativo):** abrir o .blend no Blender, workspace
Scripting > Open > `tools\model_probe.py` > ▶.

> O .blend nunca vai pro repo — só os relatórios JSON (alguns KB cada).
