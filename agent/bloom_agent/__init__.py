"""Bloom Agent — agent de personagens dentro do Blender.

Instalação (Blender 4.2+):
    1. Rode agent/zip_addon.bat (ou zipe a pasta bloom_agent manualmente).
    2. Blender > Edit > Preferences > Add-ons > Install... > selecione o zip.
    3. Habilite "Bloom Agent".
    4. Na 3D View: tecla N > aba "Bloom".

Fora do Blender (sandbox/testes): os módulos llm/keys/bridge/agent_core/
tools_registry são importáveis sem bpy — o __init__ não carrega a UI.
"""
__version__ = "0.4.1"

bl_info = {
    "name": "Bloom Agent",
    "author": "BloomRX",
    "version": (0, 4, 1),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar (N) > Bloom",
    "description": "Agent que modela, rige, texturiza e exporta personagens (UE5/VRM) dentro do Blender",
    "category": "3D View",
}

try:
    import bpy
except ImportError:  # ambiente sem Blender (testes de sandbox)
    bpy = None

_IN_BLENDER = bpy is not None

from pathlib import Path  # noqa: E402  (usado nas assinaturas)


def _data_root() -> "Path":
    """Pasta de dados gravável (chaves/jobs/backups), à prova de mudanças de API."""
    import os
    try:
        r = Path(bpy.utils.user_resource("CONFIG")) / "bloom_agent"
        r.mkdir(parents=True, exist_ok=True)
        if os.access(r, os.W_OK):
            return r
    except Exception:
        pass
    try:
        r = Path(os.environ.get("APPDATA", "")) / "Blender Foundation" / "BloomAgent"
        r.mkdir(parents=True, exist_ok=True)
        return r
    except Exception:
        return Path(__file__).resolve().parent


def _migrate_keys(nova_raiz: Path):
    """Se a chave foi gravada na raiz antiga (junto da extensão), traz pra nova."""
    from . import ui as _ui
    from . import keys as keysmod
    nova = keysmod.keys_path(nova_raiz)
    if nova.exists():
        return
    antiga = Path(__file__).resolve().parents[2]  # raiz default antiga
    velha = keysmod.keys_path(antiga)
    if velha.is_file():
        try:
            nova.parent.mkdir(parents=True, exist_ok=True)
            nova.write_bytes(velha.read_bytes())
            print("bloom_agent: chaves migradas da pasta antiga", flush=True)
        except OSError:
            pass


def register():
    if not _IN_BLENDER:
        return
    from . import ui as _ui
    try:
        raiz = _data_root()
        _ui._State.root = raiz
        _migrate_keys(raiz)
    except Exception as _e:
        print(f"bloom_agent: pasta de dados padrão ({_e})", flush=True)
    for cls in _ui._CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bloom_props = bpy.props.PointerProperty(type=_ui.BloomProperties)
    try:
        _ui._ensure_timer()
    except Exception as _e:  # timer não pode impedir o registro do addon
        print(f"bloom_agent: timer não registrado ({_e})", flush=True)
    _ui._log(f"Bloom Agent registrado. Dados em: {_ui._State.root}")
    _ui._log("Chave Gemini no painel (N > Bloom > Chaves Gemini).")


def unregister():
    if not _IN_BLENDER:
        return
    from . import ui as _ui
    try:
        bpy.app.timers.unregister(_ui._main_timer)
    except (ValueError, RuntimeError):
        pass
    if bpy.context.scene and hasattr(bpy.context.scene, "bloom_props"):
        del bpy.types.Scene.bloom_props
    for cls in reversed(_ui._CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except (ReferenceError, RuntimeError):
            pass
