# Instruções do projeto para o Copilot (lidas automaticamente)

Projeto: **Bloom Agent** — addon do Blender (Python) com um agente de IA dentro
do Blender 5.2 (usuário é leigo em Blender; painel e mensagens em PT-BR).

## Comandos
- **Testes (obrigatório antes de dizer "pronto")**: `python tests/run_all.py`
  (exit 0 = verde). No VSCode: task "Bloom: rodar todos os testes" ou painel Testing.
- Validação leve de sintaxe: `python tools/project_cli.py validate`

## Regras duras (não negociáveis)
1. **NÃO rode `git commit` nem `git push`.** Quem sincroniza é o usuário, pelo
   `DevKit.bat` (que roda os testes de novo antes de commitar).
2. **NÃO criar/modificar/apagar nada em `assets/learn/`** (referências grandes
   de estudo) e nenhum `.blend`/`.fbx`/textura binária.
3. Testes são **offline**: sem rede, sem GPU, sem bpy real. Use stubs como em
   `tests/test_probe_cli.py`. Novos testes: `tests/test_<assunto>.py`, unittest.
4. O código do addon roda DENTRO do Blender 5.2 (Python 3.11, extensão
   `blender_manifest.toml`). Sem dependências novas sem avisar antes.
5. Não quebrar contratos existentes: `chat()`/`GroqClient`/`Router` em
   `agent/bloom_agent/llm.py`; registro de tools em `tools_registry.py` +
   handlers em `tools/handlers.py`; chaves em `keys.py` (nunca logar chaves).
6. Painel/log do usuário: **uma linha por evento, curta e legível**, PT-BR.
7. Commits (feitos pelo usuário via DevKit) seguem `tipo: descrição` em PT-BR.

## Ao terminar qualquer mudança
Rode `python tests/run_all.py`. Só reporte "pronto" com a suíte VERDE.
Se um teste falhar por causa da sua mudança, conserte antes.
