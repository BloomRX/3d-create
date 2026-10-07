# Prompts prontos para o Copilot (cole no Chat/Agente do VSCode)

## 1. PRIMEIRO CICLO — "começar a testar as coisas" (use este agora)

```text
Você é o Copilot deste repositório (Bloom Agent — addon do Blender). Regras:
- NÃO faça git commit nem push; NÃO altere nada em assets/; NÃO modifique um
  teste só para ele passar (conserte o código, não o teste).
- Responda sempre em PT-BR.

TAREFA: primeiro ciclo de testes do projeto.
1. Confirme o ambiente: versão do Python (precisa 3.10+).
2. Rode a suíte completa: python tests/run_all.py — cole o RESUMO final.
3. Rode também: python tools/project_cli.py validate
4. Auditoria estática (responda item a item):
   a) Toda tool registrada em agent/bloom_agent/tools_registry.py tem handler
      correspondente em agent/bloom_agent/tools/handlers.py? Liste faltando.
   b) A versão em agent/bloom_agent/blender_manifest.toml bate com a de
      agent/bloom_agent/__init__.py?
   c) Existe segredo exposto? Procure por "AIza" e "gsk_" fora de arquivos
      *.local*.json e reporte onde encontrou (sem mostrar a chave inteira).
5. Se algo falhar: causa raiz em até 3 linhas + corrija (somente código do
   projeto) e rode a suíte de novo até ficar verde.
6. Relatório final: tabela "o que testou / resultado" + pendências.
```

## 2. QUANDO ALGO ESTIVER VERMELHO

```text
Siga as instruções do repo (.github/copilot-instructions.md). Rode
python tests/run_all.py, identifique o(s) teste(s) falhando, explique o
motivo em 2 linhas cada e conserte o CÓDIGO (não o teste), preservando os
contratos de agent/bloom_agent/llm.py e tools_registry.py. Suíte verde antes
de encerrar. Sem commit/push.
```

## 3. ROTINA APÓS QUALQUER MUDANÇA (sua ou do Copilot)

```text
Siga as instruções do repo. Rode python tests/run_all.py. Verde? Digame
"PRONTO — suíte verde (N testes)". Vermelho? Aplique o fluxo do item 2.
```
