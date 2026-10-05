# util/ — utilitários de apoio (a saída daqui o agent lê no repo)

## probe_modelo.bat — raio-X de um .blend (2 cliques, sem abrir o Blender)

Gera o `model_probe.json` que o agent precisa para estudar um modelo
(ex.: personagem estilo WuWa/Hsin): ossos, shape keys, modificadores,
materiais/nós/texturas, UVs, drivers, render.

**Como usar:**
1. Feche o Blender (não precisa, mas evita confusão de arquivo travado).
2. Dê dois cliques em `util\probe_modelo.bat`.
3. Ele acha sozinho o Blender e o .blend mais recente no banco
   `J:\3d-Create` (e Desktop/Downloads/Documentos). Se achar vários,
   ele lista e você cola o caminho do certo (ou **arrasta o .blend
   pra dentro da janela preta**).
4. Quando terminar, aparece `util\model_probe.json` e ele pergunta
   se já quer enviar pro repo → **Enter = sim** (commit+push pelo
   project_cli, mesmo mecanismo do DevKit).
5. Volte na conversa com o agent e escreva: **"probe enviado"**.

**Atalhos:** você também pode ARRASTAR um .blend em cima do .bat, ou
usar o modo manual (abrir o .blend no Blender e rodar
`tools\model_probe.py` no workspace Scripting).

> O .blend nunca vai pro repo — só o relatório JSON (alguns KB).
