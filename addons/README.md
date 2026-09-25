# Addons / Plugins (para o agent ler e integrar)

Coloque aqui os addons do seu Blender que podem auxiliar o pipeline
(Bodiez e afins). Um zip por addon ou uma subpasta com os `.py`:

```
addons/
├── bodiez.zip            # ou:
├── bodiez/
│   └── *.py
├── outro_plugin.zip
└── ...
```

Regras:
- **máx. ~90 MB por arquivo** (limite do DevKit/GitHub — se passar, zipe só
  os `.py`, sem texturas/assets);
- nada de **assets 3D** aqui (isso vai no Asset Bank local, ver
  `assets/README.md`);
- são opcionais: o Bloom Agent roda sem eles (usa base embutida); aqui estão
  para o agent conhecer o naming de ossos/topologia e aproveitar quando
  detectar o plugin instalado no Blender.
