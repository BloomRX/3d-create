# util/ — motor interno do BLOOM.bat

**Você só precisa de uma coisa: `BLOOM.bat` na raiz do repo.** Ele faz,
na ordem: limpa temporários → **pull** → **reinstala o addon Bloom Agent**
(recompila o zip e liga) → **instala plugins novos**
(desligados) → **raio-X** de .blend/.vrm novos (pergunta quais) →
**ativa o CI** (só na 1ª vez) → **commit+push** do que surgir →
**pergunta se quer abrir o Blender**.

Os arquivos desta pasta são o motor que o BLOOM.bat usa:

| Arquivo | Papel |
|---|---|
| `bloom.ps1` | o cérebro da rotina (chamado pelo BLOOM.bat) |
| `instalar_plugins.py` | roda DENTRO do Blender; instala zips desligados |
| `instalar_addon.py` | roda DENTRO do Blender; reinstala e LIGA o Bloom Agent |
| `probe_vrm.py` | roda DENTRO do Blender; importa .vrm p/ o raio-X |

Relatórios de raio-X ficam em `probes/`; **o log de cada rodada fica em
`logs/`** (guarda as últimas 10) — os dois sobem no sync, então se algo der
errado basta avisar o agent na conversa: ele lê o log direto do repo.
Plugins (zips) ficam em `plugins/`. Referências de estudo em `assets/learn/`.

**.vrm sem o VRM Addon instalado?** O BLOOM pula com um recado na tela:
baixe o zip (github.com/saturday06/VRM_ADDON_FOR_BLENDER → Releases),
solte em `plugins/` e rode de novo.
