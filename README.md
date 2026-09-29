# 3d-create

Personagens 3D para VTuber/jogos, criados por um **agent dentro do Blender**:
você cola uma foto de referência + pede em português; o agent modela (ou
adapta um asset do seu acervo), rige, texturiza e exporta peças separadas
(corpo, cada roupa, cada cabelo) para **UE5 (MetaHuman)** e **VRM (Vroid)** —
com perfil simplificado tipo **Mixamo** opcional.

Fluxo local em 1º lugar; Google Colab grátis só para o que precisa de GPU
forte (geração 3D por IA, depois vídeo). Tudo sem custo.

- **Regras de engenharia e pipeline:** [`docs/PIPELINE.md`](docs/PIPELINE.md)
- **DevKit** (git seguro: sync/pull/validate/pr): `DevKit.bat` — usar como sempre.

## Estrutura

```
agent/            # o addon do Blender (o "produto")
bloom_agent/      #   core: llm (Gemini + rotação de chaves), bridge (Colab),
                  #   agent_core (loop de tools), tools/ (handlers), ui (painel N)
colab/            # notebooks Colab (test_bridge.ipynb no M0; geração 3D etc. depois)
assets/README.md  # como funciona o Asset Bank (pasta LOCAL, fora do git)
config/           # keys.local.json (fora do git) — chaves Gemini com rotação
tests/            # testes do M0 (rodam sem Blender)
jobs/ stage_backups/  # gerados em runtime, fora do git
```

## Instalação (PC do usuário — Windows)

1. **Blender 4.2+** (4.5 LTS recomendado).
2. **Chave Gemini grátis**: https://aistudio.google.com/app/apikey (1 por conta;
   funciona com várias chaves — o addon rotaciona quando a cota acaba).
3. Rode `agent\zip_addon.bat` (gera `agent\bloom_agent_addon.zip`).
4. Blender → *Edit > Preferences > Add-ons > Install…* → selecione o zip →
   habilite **Bloom Agent**.
5. Na 3D View, tecla **N** → aba **Bloom**:
   - cole a(s) chave(s) → *Adicionar chave(s)* (fica em `config/keys.local.json`,
     nunca vai pro git);
   - configure a pasta do **Asset Bank** (pode ser vazia no começo);
   - escolha o **modo**: *Passo a passo* (estágio por estágio) ou *Pleno*
     (fluxo completo com gates de aprovação).
6. Cole uma **foto de referência** + escreva o pedido → *Enviar*.

### Ponte Colab (para gerações pesadas — opcional no início)

1. Painel → *Iniciar/parar ponte* (sobe receptor na porta 8791).
2. Num terminal no PC: `ngrok http 8791` (ngrok free; o addon detecta a URL
   sozinho via *Atualizar URL*).
3. Painel → *Job de teste* → abra `colab/test_bridge.ipynb` no Colab, cole
   `job_id` + `base_url`, execute tudo → painel: *Coletar*.

> ngrok free = 1 GB/mês na direção do PC. Resultados > 150 MB vão para o
> Google Drive (`MyDrive/3d-create/jobs/<id>`) automaticamente — a ponte
> escolhe a rota.

## Problemas?

- Painel mostra "propriedades não registradas" ou a aba não aparece:
  feche o Blender por completo, pull, gere o zip de novo
  (`agent\zip_addon.bat`), remova o Bloom Agent antigo em
  *Edit > Preferences > Add-ons > Remove*, instale o zip novo e habilite.
- Ainda com problema: workspace **Scripting** > *Open* >
  `agent/diagnostico.py` > botão ▶. Copie o texto `DIAGNOSTICO_BLOOM`
  que aparece no editor e mande pra mim.

## Testes (sem Blender, sem rede)

```
python tests/test_m0.py
```

## Status

- [x] **M0** — addon + chat + Gemini (rotação de chaves) + tools básicas +
      autosave/rollback por etapa + ponte Colab (ngrok + Drive) + asset bank
      (varrer/importar)
- [ ] **M1** — foto → personagem (face 3DMM + corpo procedural + master rig)
- [ ] **M2** — texturas/UV (SDXL local) + "colar shader" (toon/semi-real/PBR)
- [ ] **M3** — roupas e cabelos como peças + variantes (shape keys) + morph de penteado
- [ ] **M4** — export UE5 (MetaHuman) / VRM 2.0 (Vroid, spring bones) / Mixamo
- [ ] **M5** — animações base + vídeo de preview
