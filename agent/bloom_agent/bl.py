"""Camada fina sobre bpy — o ÚNICO módulo do core que importa Blender.

Se um dia precisarmos testar o core fora do Blender, nada além disso aqui
deve importar bpy.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

try:
    import bpy
except ImportError:  # fora do Blender (testes de sandbox)
    bpy = None  # type: ignore[assignment]


class BlenderMissing(RuntimeError):
    pass


def _need_bpy():
    if bpy is None:
        raise BlenderMissing("bpy indisponível (este código só roda dentro do Blender).")


def scene():
    _need_bpy()
    return bpy.context.scene


def objects_tree() -> str:
    _need_bpy()
    lines = []
    for ob in bpy.context.scene.objects:
        par = ob.parent.name if ob.parent else "-"
        poly = ""
        if ob.type == "MESH" and ob.data is not None:
            poly = f" verts={len(ob.data.vertices)} faces={len(ob.data.polygons)}"
        mods = ",".join(m.type for m in ob.modifiers) or "-"
        lines.append(f"- {ob.name} [{ob.type}] parent={par} mods={mods}{poly}")
    return "\n".join(lines) or "(cena vazia)"


def poly_stats() -> dict:
    _need_bpy()
    tris = verts = 0
    for ob in bpy.context.scene.objects:
        if ob.type != "MESH" or ob.data is None:
            continue
        for p in ob.data.polygons:
            tris += max(len(p.vertices) - 2, 1)
        verts += len(ob.data.vertices)
    return {"objects": len(bpy.context.scene.objects), "tris": tris, "verts": verts}


def create_primitive(kind: str, name: str, location=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)):
    _need_bpy()
    scn = scene()
    kind = (kind or "cube").lower()
    name = name or f"obj_{kind}"
    # guarda: ops de mesh exigem OBJECT mode
    ativo = bpy.context.object
    if ativo is not None and ativo.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    ops_mesh = bpy.ops.mesh  # no Blender 5.x NÃO cachear além do 1º nível
    if kind in ("cube", "cubo"):
        ops_mesh.primitive_cube_add(size=1.0, location=location)
    elif kind in ("ico_sphere", "sphere", "esfera"):
        ops_mesh.primitive_ico_sphere_add(subdivisions=3, radius=0.5, location=location)
    elif kind in ("cylinder", "cilindro"):
        ops_mesh.primitive_cylinder_add(vertices=32, radius=0.5, depth=1.0, location=location)
    elif kind in ("cone", "cone2"):
        ops_mesh.primitive_cone_add(vertices=32, radius1=0.5, radius2=0.0, depth=1.0, location=location)
    elif kind in ("plane", "plano"):
        ops_mesh.primitive_plane_add(size=1.0, location=location)
    elif kind == "metaball":
        me = bpy.data.metaballs.new(name)
        me.resolution = 0.05
        el = me.elements.new()
        el.co = (0.0, 0.0, 0.0)
        el.radius = 0.5
        ob = bpy.data.objects.new(name, me)
        scn.collection.objects.link(ob)
        ob.location = location
        ob.scale = scale
        return ob
    else:
        raise ValueError(f"Tipo primitivo desconhecido: {kind!r}")
    ob = bpy.context.active_object
    if ob is None:
        raise RuntimeError("A primitiva não foi criada.")
    ob.name = name
    ob.location = location
    ob.scale = scale
    return ob


def delete_object(name: str):
    _need_bpy()
    ob = bpy.data.objects.get(name)
    if ob is None:
        raise KeyError(f"Objeto {name!r} não existe.")
    data = ob.data
    for coll in list(ob.users_collection):
        coll.objects.unlink(ob)
    bpy.data.objects.remove(ob, do_unlink=True)
    if data is not None:
        try:
            if data.users == 0:
                kind = {bpy.types.Mesh: bpy.data.meshes,
                        bpy.types.Curve: bpy.data.curves,
                        bpy.types.Metaball: bpy.data.metaballs}.get(type(data))
                if kind and data.name in kind:
                    kind.remove(data)
        except (ReferenceError, RuntimeError, TypeError):
            pass


def save_blend(path: Path):
    _need_bpy()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_mainfile(filepath=str(path))
    return str(path)


def _pick_engine(scn) -> str:
    try:
        engines = {e.identifier for e in type(scn.render.engine).enum_items}
    except (AttributeError, RuntimeError):
        engines = set()
    if "BLENDER_EEVEE_NEXT" in engines:
        return "BLENDER_EEVEE_NEXT"
    if "BLENDER_EEVEE" in engines:
        return "BLENDER_EEVEE"
    return scn.render.engine  # último caso: usa o que já estiver


def quick_render(path: Path, size: int = 512, from_viewport: bool = True) -> str:
    """Render rápido (Eevee) em PNG. `from_viewport` posiciona câmera no view atual."""
    _need_bpy()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    scn = scene()
    old_engine = scn.render.engine
    old_cam = scn.camera
    tmp_cam = None
    cam_data = None
    try:
        if from_viewport:
            window = bpy.context.window_manager.windows[0]
            area = next((a for a in window.screen.areas if a.type == "VIEW_3D"), None)
            if area is not None:
                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                with bpy.context.temp_override(window=window, area=area, region=region):
                    r3d = area.spaces.active.region_3d
                    cam_data = bpy.data.cameras.new("bloom_tmp_cam")
                    tmp_cam = bpy.data.objects.new("bloom_tmp_cam", cam_data)
                    scn.collection.objects.link(tmp_cam)
                    try:
                        tmp_cam.matrix_world = r3d.view_perspective_matrix
                    except AttributeError:
                        tmp_cam.location = (3.5, -3.5, 1.8)
                        tmp_cam.rotation_euler = (1.05, 0.0, 0.78)
                    scn.camera = tmp_cam
        scn.render.engine = _pick_engine(scn)
        scn.render.resolution_x = int(size)
        scn.render.resolution_y = int(size)
        scn.render.resolution_percentage = 100
        scn.render.image_settings.file_format = "PNG"
        scn.render.filepath = str(path)
        window = bpy.context.window_manager.windows[0]
        with bpy.context.temp_override(window=window, scene=scn):
            bpy.ops.render.render(write_still=True)
    finally:
        if tmp_cam is not None:
            try:
                scn.collection.objects.unlink(tmp_cam)
                bpy.data.objects.remove(tmp_cam, do_unlink=True)
            except (ReferenceError, RuntimeError):
                pass
        if cam_data is not None:
            try:
                if cam_data.users == 0:
                    bpy.data.cameras.remove(cam_data)
            except (ReferenceError, RuntimeError):
                pass
        scn.camera = old_cam
        try:
            scn.render.engine = old_engine
        except (TypeError, RuntimeError):
            pass
    return base64.b64encode(path.read_bytes()).decode("ascii")


def import_asset(path: Path, target_name: str | None = None):
    """Importa glb/gltf/fbx/obj/blend a partir de um caminho local."""
    _need_bpy()
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Asset não encontrado: {path}")
    ext = path.suffix.lower()
    window = bpy.context.window_manager.windows[0]
    scn = bpy.context.scene
    with bpy.context.temp_override(window=window, scene=scn):
        if ext in (".glb", ".gltf"):
            bpy.ops.import_scene.gltf(filepath=str(path))
        elif ext == ".fbx":
            bpy.ops.import_scene.fbx(filepath=str(path))
        elif ext == ".obj":
            bpy.ops.wm.obj_import(filepath=str(path))
        elif ext == ".blend":
            libs = bpy.data.libraries.load(str(path), link=False, directories=["Object"])
            if libs.objects:
                names = [o.name for o in libs.objects]
                for n in names:
                    try:
                        bpy.ops.wm.append(filepath=str(path), directory=f"Object/{n}")
                    except RuntimeError:
                        pass
        else:
            raise ValueError(f"Formato não suportado para import: {ext}")
    if target_name:
        for ob in scn.objects:
            if ob.get("bloom_just_imported"):
                ob.name = target_name


def list_bank_files(bank_dir: Path, exts=(".glb", ".gltf", ".fbx", ".obj", ".blend")) -> list:
    """Varre a pasta do asset bank (pure Python, testável sem bpy)."""
    bank_dir = Path(bank_dir)
    out = []
    if not bank_dir.is_dir():
        return out
    for f in sorted(bank_dir.rglob("*")):
        if f.suffix.lower() in exts and f.is_file():
            meta_file = f.with_name(f.name + ".meta.json")
            tags, obs = [], ""
            if meta_file.is_file():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    tags = meta.get("tags", []) or []
                    obs = meta.get("obs", "") or ""
                except (OSError, ValueError):
                    pass
            out.append({
                "id": f.name,
                "name": f.stem,
                "rel": str(f.relative_to(bank_dir)),
                "type": f.suffix.lower().lstrip("."),
                "size": f.stat().st_size,
                "tags": tags,
                "obs": obs,
            })
    return out
