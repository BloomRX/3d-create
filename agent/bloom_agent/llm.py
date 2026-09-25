"""Cliente Gemini (REST, sem dependências externas) com rotação de chaves.

Uso:
    gem = Gemini(keys_path)
    resp = gem.chat(parts=[{"text": "oi"}], system="...", tools=[...])
    resp -> {"text": str, "tool_calls": [{"name","args"}], "model", "key_masked"}

Formatos de "parts" aceitos em chat():
    {"text": "..."}
    {"image_b64": "...", "mime": "image/png", "caption": "opcional"}

A resposta do modelo pode trazer "functionCall"; eles vêm em tool_calls.
Erro de cota (429 / RESOURCE_EXHAUSTED) -> chave vai p/ cooldown e a
próxima da lista tenta. Se todas estiverem em cooldown, LLMError com o
tempo estimado para a próxima liberar.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import keys as keysmod

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_TIMEOUT = 180


class LLMError(RuntimeError):
    pass


def build_request(system: str, contents: list, tools: list, model: str,
                  temperature: float = 0.2, max_output_tokens: int = 8192) -> dict:
    body: dict = {"contents": contents, "model": model}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if tools:
        body["tools"] = [{"function_declarations": tools}]
    body["generationConfig"] = {
        "temperature": temperature,
        "maxOutputTokens": max_output_tokens,
    }
    return body


def parts_to_wire(parts: list) -> list:
    """Converte parts internas (text/image_b64) para o formato da API."""
    out = []
    for p in parts:
        if "image_b64" in p:
            out.append({
                "inline_data": {
                    "mime_type": p.get("mime", "image/png"),
                    "data": p["image_b64"],
                }
            })
            if p.get("caption"):
                out.append({"text": p["caption"]})
        else:
            out.append({"text": p["text"]})
    return out


def parse_response(data: dict) -> dict:
    """Extrai texto + chamadas de função de uma resposta v1beta."""
    text_parts = []
    tool_calls = []
    for cand in data.get("candidates", []):
        content = cand.get("content", {})
        for part in content.get("parts", []):
            if "text" in part:
                text_parts.append(part["text"])
            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append({
                    "name": fc.get("name", ""),
                    "args": fc.get("args", {}) or {},
                })
    return {
        "text": "".join(text_parts).strip(),
        "tool_calls": tool_calls,
        "finish_reason": (data.get("candidates") or [{}])[0].get("finishReason", ""),
    }


def _http_post(url: str, body: dict, timeout: int) -> tuple[int, dict | str]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw[:2000]
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise LLMError(f"Falha de rede ao chamar a API: {e}") from e


def _is_quota_error(status: int, payload) -> bool:
    if status == 429:
        return True
    if isinstance(payload, dict):
        err = payload.get("error", {})
        code = str(err.get("code", ""))
        msg = str(err.get("message", "")).lower()
        return code in ("RESOURCE_EXHAUSTED", 429) or "quota" in msg or "rate limit" in msg
    return False


def _error_message(status: int, payload) -> str:
    if isinstance(payload, dict):
        err = payload.get("error", {})
        return f"HTTP {status}: {err.get('message', 'erro desconhecido')}"
        return f"HTTP {status}: {str(payload)[:300]}"


def _is_busy(msg: str) -> bool:
    """503/500 do Google = sobrecarga momentânea do modelo."""
    m = msg.lower()
    return ("503" in m or "500" in m or "overloaded" in m
            or "high demand" in m or "unavailable" in m)


class Gemini:
    def __init__(self, keys_path: Path, model: str | None = None, timeout: int = DEFAULT_TIMEOUT):
        self.keys_path = Path(keys_path)
        self.data = keysmod.load(self.keys_path)
        self.model = model or self.data.get("model") or keysmod.DEFAULT_MODEL
        self.timeout = timeout
        self.last_key_masked: str | None = None
        self._model_ok = False  # confirmado via ListModels?

    # --- chaves -----------------------------------------------------------
    def status(self) -> dict:
        ks = self.data["gemini"]
        return {
            "keys": [keysmod.mask(k) for k in ks],
            "active_index": keysmod.pick_key(self.data),
            "model": self.model,
            "cooldown_seconds": int(keysmod.earliest_recovery(self.data)),
        }

    def _persist(self) -> None:
        try:
            self.data.pop("_test_now", None)
            keysmod.save(self.keys_path, self.data)
        except OSError:
            pass

    def _call_once(self, url: str, body: dict) -> tuple[int, dict | str]:
        idx = keysmod.pick_key(self.data)
        if idx is None:
            wait = keysmod.earliest_recovery(self.data)
            raise LLMError(
                f"Todas as {len(self.data['gemini'])} chaves estão em cooldown. "
                f"Próxima libera em ~{int(wait)}s (ou adicione outra chave no painel)."
            )
        key = self.data["gemini"][idx]
        self.last_key_masked = keysmod.mask(key)
        status, payload = _http_post(f"{url}?key={key}", body, self.timeout)
        if _is_quota_error(status, payload):
            keysmod.mark_cooldown(self.data, idx, seconds=90)
            keysmod.advance(self.data)
            self._persist()
            raise LLMError(f"quota:{status}")  # sinal interno: tentar próxima chave
        if status != 200:
            raise LLMError(_error_message(status, payload))
        return status, payload

    # --- modelo -----------------------------------------------------------
    def list_models(self) -> list:
        """IDs de modelos que suportam generateContent com as chaves atuais."""
        last = None
        for key in self.data["gemini"]:
            try:
                with urllib.request.urlopen(
                        f"{API_BASE}/models?key={key}",
                        timeout=self.timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                out = []
                for m in payload.get("models", []):
                    if "generateContent" in (m.get("supportedGenerationMethods") or []):
                        out.append((m.get("name") or "").split("models/")[-1])
                return out
            except Exception as e:
                last = e
        raise LLMError(f"ListModels falhou: {last}")

    def _confirm_model(self):
        """Garante que self.model existe p/ a chave; se não, escolhe um
        fallback disponível e salva a escolha."""
        if self._model_ok:
            return
        try:
            ids = set(self.list_models())
        except Exception:
            self._model_ok = True  # não bloqueia: o generate dirá o erro real
            return
        if self.model in ids:
            self._model_ok = True
            return
        pick = next((p for p in keysmod.FALLBACK_MODELS
                     if p != self.model and p in ids), None)
        if pick is None:
            raise LLMError(
                f"modelo '{self.model}' não disponível p/ sua chave e nenhum "
                "fallback conhecido também. Disponíveis: "
                + ", ".join(sorted(ids)[:25]))
        old = self.model
        self.model = pick
        self._model_ok = True
        self.data["model"] = pick
        self._persist()
        print(f"bloom_agent: modelo '{old}' indisponível -> usando '{pick}'",
              flush=True)

    def _switch_model(self, motivo: str) -> bool:
        """Troca self.model por outro disponível (usado em 404 e 503 insistente)."""
        try:
            ids = set(self.list_models())
        except Exception:
            return False
        pick = next((p for p in keysmod.FALLBACK_MODELS
                     if p != self.model and p in ids), None)
        if pick is None:
            return False
        old = self.model
        self.model = pick
        self._model_ok = True
        self.data["model"] = pick
        self._persist()
        print(f"bloom_agent: {motivo}: '{old}' -> '{pick}'", flush=True)
        return True

    # --- chat ---------------------------------------------------------------
    def chat(self, parts: list | None = None, system: str = "", tools: list | None = None,
             contents: list | None = None) -> dict:
        """Uma chamada de chat com rotação automática de chaves.

        `parts` (mensagens novas, conversão interna) OU `contents` (contêiner
        já no formato da API, ex.: histórico + functionResponse).
        """
        if contents is None:
            if not parts:
                raise ValueError("chat(): informe `parts` ou `contents`")
            contents = [{"role": "user", "parts": parts_to_wire(parts)}]

        tried = set()
        last_err = None
        busy = 0  # tentativas sob 503/sobrecarga no modelo atual
        while True:
            idx = keysmod.pick_key(self.data)
            if idx is None or idx in tried:
                if last_err and str(last_err).startswith("quota:"):
                    wait = keysmod.earliest_recovery(self.data)
                    raise LLMError(
                        "Todas as chaves estouraram cota por agora. "
                        f"Tente de novo em ~{int(wait)}s ou adicione outra chave."
                    )
                raise last_err or LLMError("Nenhuma chave configurada.")
            tried.add(idx)
            self._confirm_model()
            body = build_request(system, contents, tools or [], self.model)
            url = f"{API_BASE}/models/{self.model}:generateContent"
            try:
                _, payload = self._call_once(url, body)
                self._model_ok = True
                return {**parse_response(payload), "model": self.model,
                        "key_masked": self.last_key_masked}
            except LLMError as e:
                msg = str(e)
                if msg.startswith("quota:"):
                    last_err = e  # tenta a próxima chave
                    continue
                if "404" in msg and "not found" in msg:
                    tried.discard(idx)  # 404 não gasta cota
                    if self._switch_model("modelo indisponível"):
                        continue
                    raise
                if _is_busy(msg):
                    busy += 1
                    if busy <= 2:
                        time.sleep(3 * busy)  # 3s, 6s — sobrecarga costuma passar
                        tried.discard(idx)
                        continue
                    tried.discard(idx)
                    if self._switch_model("modelo sobrecarregado"):
                        busy = 0
                        continue
                    raise LLMError(
                        "o modelo está sobrecarregado no lado do Google (503) "
                        "e não achei alternativo livre. Espere ~1 minuto e "
                        "mande a mensagem de novo.")
                raise

    # --- histórico -----------------------------------------------------------
    @staticmethod
    def function_response(name: str, response: dict) -> dict:
        return {"role": "user", "parts": [{"functionResponse": {
            "name": name, "response": response}}]}

    @staticmethod
    def user_image(b64: str, mime: str = "image/png", caption: str = "") -> dict:
        parts = [{"inline_data": {"mime_type": mime, "data": b64}}]
        if caption:
            parts.append({"text": caption})
        return {"role": "user", "parts": parts}

    @staticmethod
    def user_parts(parts: list) -> dict:
        """parts internos ({text}/{image_b64,caption,mime}) -> conteúdo 'user' da API."""
        out = []
        for p in parts:
            if "image_b64" in p:
                out.append({"inline_data": {"mime_type": p.get("mime", "image/png"),
                                            "data": p["image_b64"]}})
                if p.get("caption"):
                    out.append({"text": p["caption"]})
            else:
                out.append({"text": p["text"]})
        return {"role": "user", "parts": out}

    @staticmethod
    def model_parts(text: str = "", calls: list | None = None) -> dict:
        parts = []
        if text:
            parts.append({"text": text})
        for c in calls or []:
            parts.append({"functionCall": {"name": c["name"], "args": c["args"]}})
        return {"role": "model", "parts": parts or [{"text": ""}]}
