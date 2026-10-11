# -*- coding: utf-8 -*-
"""Instalação de zips EXTENSÃO (com blender_manifest.toml) direto no
repositório user_default — o caminho que o Blender 4.2+ de fato lê.
O operador extension_install_file falha em silêncio em background; unzip não."""
import shutil
import zipfile
from pathlib import Path

import addon_utils
import bpy


def pasta_extensoes() -> Path:
    try:
        base = bpy.utils.user_resource("EXTENSIONS")
    except Exception:
        base = None
    if not base or not str(base).strip():
        base = str(Path(bpy.utils.resource_path("USER")) / "extensions")
    return Path(base) / "user_default"


def _id_do_manifest(z: zipfile.ZipFile):
    for nome in z.namelist():
        if nome.endswith("blender_manifest.toml"):
            for linha in z.read(nome).decode("utf-8", "replace").splitlines():
                l = linha.strip()
                if l.startswith("id") and "=" in l:
                    return l.split("=", 1)[1].strip().strip("\"'")
    return None


def instalar_extensao(zip_path, ligar: bool):
    """Extrai um zip de extensão em user_default/<id>. Retorna (msg, id)."""
    with zipfile.ZipFile(zip_path) as z:
        nomes = [n for n in z.namelist() if not n.endswith("/")]
        if not any(n.endswith("blender_manifest.toml") for n in nomes):
            return None, None  # não é extensão
        addon_id = _id_do_manifest(z) or Path(zip_path).stem
        alvo = pasta_extensoes() / addon_id
        if alvo.exists():
            shutil.rmtree(alvo, ignore_errors=True)
        alvo.mkdir(parents=True, exist_ok=True)
        tops = {n.split("/")[0] for n in nomes}
        if len(tops) == 1:
            prefixo = list(tops)[0] + "/"
        else:
            prefixo = ""  # arquivos na raiz do zip
        for n in nomes:
            if prefixo and not n.startswith(prefixo):
                continue
            rel = n[len(prefixo):] if prefixo else n
            destino = alvo / rel
            destino.parent.mkdir(parents=True, exist_ok=True)
            with z.open(n) as src, open(destino, "wb") as dst:
                shutil.copyfileobj(src, dst)
    mod = f"bl_ext.user_default.{addon_id}"
    estado = "ok (extensao em " + str(alvo.parent.name) + ")"
    if ligar:
        try:
            addon_utils.modules_refresh()
        except Exception:
            pass
        try:
            if addon_utils.enable(mod, default_set=True, persistent=True):
                estado = f"ok (extensao {addon_id} INSTALADA E LIGADA)"
            else:
                estado = (f"ok (extensao {addon_id} instalada; ligue em "
                          "Preferences > Add-ons se nao aparecer)")
        except Exception as exc:
            estado = (f"ok (extensao {addon_id} instalada; ligar falhou: "
                      f"{str(exc).splitlines()[0][:60]})")
    return estado, addon_id
