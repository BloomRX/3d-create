"""Armazenamento e rotação de chaves de API (Gemini) — 100% local, fora do git.

O arquivo padrão é config/keys.local.json (gitignored). Estrutura:
    {
      "gemini": ["chave1", "chave2"],
      "model": "gemini-flash-latest",
      "last_key_index": 0,
      "cooldowns": {"0": 1735690000.0}   # index -> epoch até quando a chave descansa
    }

Rotação: quando uma chave estoura cota (429), ela vai para cooldown e a
próxima da lista é usada. O estado (índice + cooldowns) é persistido no
mesmo arquivo, então a rotação sobrevive a reinícios do Blender.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

DEFAULT_MODEL = "gemini-flash-latest"
FALLBACK_MODELS = ["gemini-flash-latest", "gemini-3-flash", "gemini-2.5-flash",
                   "gemini-flash-lite-latest", "gemini-2.5-flash-lite",
                   "gemini-2.0-flash"]

KEYS_FILE_REL = "config/keys.local.json"


def keys_path(root: Path) -> Path:
    return Path(root) / KEYS_FILE_REL


def _blank() -> dict:
    return {"gemini": [], "model": DEFAULT_MODEL, "last_key_index": 0, "cooldowns": {}}


def load(path: Path) -> dict:
    """Carrega o arquivo de chaves; ausente/corrompido -> estado vazio."""
    data = _blank()
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            for k, v in data.items():
                if k in raw:
                    data[k] = raw[k]
    except (OSError, ValueError):
        pass
    if not isinstance(data.get("gemini"), list):
        data["gemini"] = []
    if not isinstance(data.get("cooldowns"), dict):
        data["cooldowns"] = {}
    return data


def save(path: Path, data: dict) -> None:
    """Grava atomicamente e restringe permissões (melhor esforço)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(path)


def add_key(data: dict, key: str) -> int:
    key = key.strip()
    if not key or key.startswith("SUBSTITUA") or key.startswith("cole_sua"):
        raise ValueError("Chave vazia ou ainda o placeholder do exemplo.")
    data["gemini"].append(key)
    return len(data["gemini"]) - 1


def remove_key(data: dict, index: int) -> None:
    if not (0 <= index < len(data["gemini"])):
        raise IndexError("Índice de chave inválido.")
    data["gemini"].pop(index)
    data["cooldowns"] = {}  # índices mudaram: reseta
    data["last_key_index"] = 0


def mask(key: str) -> str:
    key = key.strip()
    if len(key) <= 10:
        return key[:2] + "…"
    return key[:6] + "…" + key[-4:]


def _now(data: dict) -> float:
    # gancho de teste: "_test_now" no dict permite injetar o relógio
    return float(data.get("_test_now", time.time()))


def key_available(data: dict, index: int, now: float | None = None) -> bool:
    now = _now(data) if now is None else now
    until = float(data["cooldowns"].get(str(index), 0) or 0)
    return now >= until


def pick_key(data: dict) -> int | None:
    """Primeira chave fora de cooldown, partindo de last_key_index."""
    keys = data["gemini"]
    n = len(keys)
    if n == 0:
        return None
    start = int(data.get("last_key_index", 0) or 0) % n
    for step in range(n):
        i = (start + step) % n
        if key_available(data, i):
            return i
    return None


def earliest_recovery(data: dict) -> float:
    """Quando a chave mais "bloqueada" volta (0 se todas livres)."""
    now = _now(data)
    best = 0.0
    for i, until in data["cooldowns"].items():
        try:
            idx = int(i)
            until = float(until)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(data["gemini"]) and until > now and until > best:
            best = until
    return best - now


def mark_cooldown(data: dict, index: int, seconds: float = 60.0, now: float | None = None) -> None:
    now = _now(data) if now is None else now
    data["cooldowns"][str(index)] = now + seconds


def advance(data: dict) -> None:
    n = len(data.get("gemini", []))
    if n == 0:
        return
    data["last_key_index"] = (int(data.get("last_key_index", 0) or 0) + 1) % n
