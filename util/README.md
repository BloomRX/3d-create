# util/ — motor interno do BLOOM.bat

**Você só precisa de uma coisa: `BLOOM.bat` na raiz do repo.** Ele faz,
na ordem: limpa temporários → **pull** → **instala plugins novos**
(desligados) → **raio-X** de .blend/.vrm novos (pergunta quais) →
**ativa o CI** (só na 1ª vez) → **commit+push** do que surgir →
**pergunta se quer abrir o Blender**.

Os arquivos desta pasta são o motor que o BLOOM.bat usa:

| Arquivo | Papel |
|---|---|
| `bloom.ps1` | o cérebro da rotina (chamado pelo BLOOM.bat) |
| `instalar_plugins.py` | roda DENTRO do Blender; instala zips desligados |
| `probe_vrm.py` | roda DENTRO do Blender; importa .vrm p/ o raio-X |

Relatórios de raio-X ficam em `probes/` (o agent lê no repo).
Plugins (zips) ficam em `plugins/`. Referências de estudo em `assets/learn/`.
