"""Bloom Agent — agent de personagens dentro do Blender.

Instalação (Blender 4.2+):
    1. Rode agent/zip_addon.bat (ou zipe a pasta bloom_agent manualmente).
    2. Blender > Edit > Preferences > Add-ons > Install... > selecione o zip.
    3. Habilite "Bloom Agent".
    4. Na 3D View: tecla N > aba "Bloom".

Fora do Blender (sandbox/testes): os módulos llm/keys/bridge/agent_core/
tools_registry são importáveis sem bpy — o __init__ não carrega a UI.
"""
bl_info = {
    "name": "Bloom Agent",
    "author": "BloomRX",
    "version": (0, 1, 1),
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


def register():
    if not _IN_BLENDER:
        return
    from . import ui as _ui
    for cls in _ui._CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bloom_props = bpy.props.PointerProperty(type=_ui.BloomProperties)
    bpy.app.timers.register(_ui._main_timer, first_interval=0.25)
    _ui._log("Bloom Agent registrado. Configure a chave Gemini no painel (N > Bloom).")


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
