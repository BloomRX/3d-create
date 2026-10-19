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
import re
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
    raw = (data.get("candidates") or [{}])[0].get("content") or {}
    return {
        "text": "".join(text_parts).strip(),
        "tool_calls": tool_calls,
        "finish_reason": (data.get("candidates") or [{}])[0].get("finishReason", ""),
        # conteúdo ORIGINAL do modelo (preserva thought_signature, exigida
        # pelo Gemini 3.x quando o histórico volta com functionCall)
        "raw_content": raw,
    }


def _http_post(url: str, body: dict, timeout: int,
              headers: dict | None = None) -> tuple[int, dict | str]:
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=hdrs,
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
    # NUNCA retorna None (crashou .lower() no fallback pro Groq no momento
    # em que todas as chaves Gemini estavam inválidas — turno morreu 2x)
    if isinstance(payload, dict):
        err = payload.get("error", {})
        msg = err.get("message") or str(payload)[:300]
        return f"HTTP {status}: {msg}"
    return f"HTTP {status}: {str(payload)[:300]}"


def _is_model_gone(msg: str) -> bool:
    """404 definitivo: modelo inexistente OU fechado p/ novos usuários."""
    m = msg.lower()
    return ("no longer available" in m
            or ("404" in m and "not found" in m))


def _is_daily_quota(payload) -> bool:
    """429 com quotaId '*PerDay*' = cota DIÁRIA (não volta em minutos)."""
    if not isinstance(payload, dict):
        return False
    try:
        for d in (payload.get("error") or {}).get("details") or []:
            if "PerDay" in str(d.get("quotaId", "")):
                return True
    except Exception:
        pass
    return False


def _is_busy(msg: str) -> bool:
    """503/500 do Google = sobrecarga momentânea do modelo."""
    m = msg.lower()
    return ("503" in m or "500" in m or "overloaded" in m
            or "high demand" in m or "unavailable" in m)


class Gemini:
    # Freio GLOBAL de trocas por cota (compartilhado entre instâncias):
    # mata ping-pong mesmo se a instância for recriada no meio do fluxo.
    _QUOTA_SWAP_TS: list = []
    _QUOTA_SWAP_MAX = 6         # trocas por cota...
    _QUOTA_SWAP_WINDOW = 600.0  # ...a cada 10 minutos, no máximo
    def __init__(self, keys_path: Path, model: str | None = None, timeout: int = DEFAULT_TIMEOUT):
        self.keys_path = Path(keys_path)
        self.data = keysmod.load(self.keys_path)
        self.model = model or self.data.get("model") or keysmod.DEFAULT_MODEL
        self.timeout = timeout
        self.last_key_masked: str | None = None
        self._model_ok = False  # confirmado via ListModels?
        self._dead_models: set = set()  # aprendidos como mortos nesta sessão
        self._quota_waited = False  # já esperamos a cota liberar 1x?
        self._quota_daily = False  # 429 de cota DIÁRIA detectado
        self._quota_switches = 0   # trocas de modelo por cota (anti-ping-pong)
        self.on_log = None  # callback opcional p/ log da UI

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
        status, payload = _http_post(url, body, self.timeout,
                                     headers={"x-goog-api-key": key})
        if _is_quota_error(status, payload):
            keysmod.mark_cooldown(self.data, idx, seconds=90, model=self.model)
            keysmod.advance(self.data)
            self._persist()
            if _is_daily_quota(payload):
                self._quota_daily = True
            raise LLMError(f"quota:{status}")  # sinal interno: tentar próxima chave
        if status != 200:
            texto = _error_message(status, payload)
            baixo = texto.lower()
            if (status in (401, 403) or "api key not valid" in baixo
                    or "invalid authentication credentials" in baixo):
                raise LLMError(f"auth:{idx}")  # sinal interno: chave inválida
            raise LLMError(texto)
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

    def _switch_model(self, motivo: str, require_free: bool = False) -> bool:
        """Troca self.model por outro disponível. Com require_free=True (cota),
        só aceita candidato que tenha ALGUMA chave fora de cooldown — evita
        ping-pong entre dois modelos igualmente esgotados."""
        try:
            ids = set(self.list_models())
        except Exception:
            return False

        def _score(i: str):
            nums = re.findall(r"(\d+(?:\.\d+)?)", i)
            return ("latest" in i, float(nums[0]) if nums else 0.0)

        preferidos = [p for p in keysmod.FALLBACK_MODELS
                      if p != self.model and p in ids
                      and p not in self._dead_models]
        amplos = sorted(
            (i for i in ids if "flash" in i and not any(
                t in i for t in ("image", "tts", "thinking", "exp",
                                 "robotics", "live", "computer"))
             and i != self.model and i not in self._dead_models
             and i not in preferidos),
            key=_score, reverse=True)
        for pick in preferidos + amplos:
            if require_free and keysmod.pick_key(self.data, model=pick) is None:
                continue  # também esgotado nas chaves — trocar não resolve
            old = self.model
            self.model = pick
            self._model_ok = True
            self.data["model"] = pick
            self._persist()
            msg = f"🔄 {motivo}: '{old}' -> '{pick}'"
            print(f"bloom_agent: {msg}", flush=True)
            if self.on_log:
                try: self.on_log(msg)
                except Exception: pass
            return True
        return False

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
            idx = keysmod.pick_key(self.data, model=self.model)
            if idx is None or idx in tried:
                if last_err and str(last_err).startswith("quota:"):
                    cls = type(self)
                    agora = time.monotonic()
                    cls._QUOTA_SWAP_TS[:] = [
                        t for t in cls._QUOTA_SWAP_TS
                        if agora - t < cls._QUOTA_SWAP_WINDOW]
                    if (self._quota_switches < 4
                            and len(cls._QUOTA_SWAP_TS) < cls._QUOTA_SWAP_MAX
                            and self._switch_model(
                                "cota do modelo esgotou em todas as chaves",
                                require_free=True)):
                        self._quota_switches += 1
                        cls._QUOTA_SWAP_TS.append(agora)
                        tried.clear()
                        busy = 0
                        continue
                    if self._quota_daily:
                        raise LLMError(
                            "cota DIÁRIA esgotada em todas as chaves. Ela reseta "
                            "à meia-noite do horário do Pacífico (~04h–05h no "
                            "Brasil). Adicione outra chave ou continue amanhã.")
                    wait = keysmod.earliest_recovery(self.data, self.model)
                    if (not self._quota_waited) and 0 < wait <= 150:
                        # free tier: cooldowns são curtos — espera 1x em vez de abortar
                        self._quota_waited = True
                        total = int(min(wait + 2, 150))
                        msg = f"⏳ cota esgotada: aguardando ~{total}s (rotação de chaves)…"
                        print(f"bloom_agent: {msg}", flush=True)
                        if self.on_log:
                            try: self.on_log(msg)
                            except Exception: pass
                        for _ in range(total):
                            time.sleep(1)
                        tried.clear()
                        continue
                    raise LLMError(
                        f"Cota esgotada nas {len(self.data['gemini'])} chaves "
                        f"(modelo {self.model}). O agent PAROU p/ não queimar "
                        f"requisições à toa — tente de novo em ~{int(wait)}s, "
                        "adicione outra chave AIza, ou uma gsk_ do Groq "
                        "(texto via Groq não gasta cota Gemini)."
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
                if msg.startswith("auth:"):
                    try:
                        ruim = int(msg.split(":", 1)[1])
                    except ValueError:
                        ruim = idx
                    masked = self.last_key_masked or "?"
                    try:
                        keysmod.remove_key(self.data, ruim)
                        self._persist()
                    except IndexError:
                        pass
                    tried.clear()  # índices mudaram
                    if self.on_log:
                        try: self.on_log(f"🔑 chave {masked} removida (inválida)")
                        except Exception: pass
                    if not self.data["gemini"]:
                        raise LLMError(
                            "todas as chaves eram inválidas. Gere novas em "
                            "aistudio.google.com/app/apikey (começam com 'AIza').")
                    continue  # próxima chave
                if _is_model_gone(msg):
                    self._dead_models.add(self.model)
                    tried.discard(idx)  # 404 não gasta cota
                    if self._switch_model("modelo indisponível"):
                        continue
                    raise LLMError(
                        f"modelo '{self.model}' indisponível p/ sua chave e "
                        "nenhum alternativo livre. Erro: " + msg[:200])
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


# ===========================================================================
# Groq (orquestrador texto) + Router multi-modelo
# ===========================================================================

class GroqClient:
    """Cliente OpenAI-compatible do Groq (llama etc.) com a MESMA interface
    do Gemini.chat — recebe o histórico no formato interno e converte.
    SEM visão: imagens do histórico viram placeholders de texto."""

    API = "https://api.groq.com/openai/v1/chat/completions"
    MODEL_PADRAO = "llama-3.3-70b-versatile"
    VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"  # aceita imagens

    def __init__(self, keys_path: Path, model: str | None = None,
                 timeout: int = DEFAULT_TIMEOUT):
        self.keys_path = Path(keys_path)
        self.data = keysmod.load(self.keys_path)
        self.model = model or self.data.get("groq_model") or self.MODEL_PADRAO
        self.timeout = timeout
        self.on_log = None
        self.last_key_masked: str | None = None

    # --- chaves (cooldown próprio: g<i>|modelo) ---------------------------
    def _pick(self) -> int | None:
        ks = self.data.get("groq") or []
        now = time.time()
        for i in range(len(ks)):
            until = float(self.data["cooldowns"].get(f"g{i}|{self.model}", 0) or 0)
            if now >= until:
                return i
        return None

    def _persist(self) -> None:
        try:
            keysmod.save(self.keys_path, self.data)
        except OSError:
            pass

    def status(self) -> dict:
        return {"keys": [keysmod.mask(k) for k in (self.data.get("groq") or [])],
                "model": self.model}

    # --- conversão interno -> OpenAI ---------------------------------------
    def _convert(self, system: str, contents: list, tools: list) -> dict:
        msgs = [{"role": "system", "content": system or "Você é o Bloom Agent."}]
        pendentes: list[str] = []  # ids das tool_calls à espera de resposta
        for c in contents:
            parts = c.get("parts") or []
            texto = "".join(p.get("text", "") for p in parts
                            if isinstance(p, dict) and "text" in p)
            fcs = [p["functionCall"] for p in parts
                   if isinstance(p, dict) and "functionCall" in p]
            frs = [p["functionResponse"] for p in parts
                   if isinstance(p, dict) and "functionResponse" in p]
            tem_img = any(isinstance(p, dict) and "inline_data" in p for p in parts)
            if fcs:
                tcs = []
                for j, fc in enumerate(fcs):
                    cid = f"c{len(msgs)}_{j}"
                    tcs.append({"id": cid, "type": "function",
                                "function": {"name": fc.get("name", ""),
                                             "arguments": json.dumps(
                                                 fc.get("args") or {},
                                                 ensure_ascii=False)}})
                    pendentes.append(cid)
                msgs.append({"role": "assistant", "content": texto or None,
                             "tool_calls": tcs})
            elif frs:
                for fr in frs:
                    cid = pendentes.pop(0) if pendentes else "c_resp"
                    msgs.append({"role": "tool", "tool_call_id": cid,
                                 "name": fr.get("name", ""),
                                 "content": json.dumps(
                                     fr.get("response") or {},
                                     ensure_ascii=False)[:8000]})
            else:
                role = "assistant" if c.get("role") == "model" else "user"
                if tem_img:
                    conteudo = [{"type": "text", "text": texto or "(veja a imagem)"}]
                    for p2 in parts:
                        if isinstance(p2, dict) and "inline_data" in p2:
                            d = p2["inline_data"]
                            conteudo.append({"type": "image_url", "image_url": {
                                "url": f"data:{d.get('mime_type', 'image/png')};"
                                       f"base64,{d.get('data', '')}"}})
                    msgs.append({"role": role, "content": conteudo})
                else:
                    msgs.append({"role": role, "content": texto or "(vazio)"})
        tem_imagem = self._tem_imagem(contents)
        body = {"model": self.VISION_MODEL if tem_imagem else self.model,
                "messages": msgs, "temperature": 0.4}
        if tools:
            body["tools"] = [{"type": "function",
                              "function": {"name": t["name"],
                                           "description": t["description"],
                                           "parameters": t["parameters"]}}
                             for t in tools]
        return body

    @staticmethod
    def _tem_imagem(contents) -> bool:
        for c in contents or []:
            for p in c.get("parts") or []:
                if isinstance(p, dict) and "inline_data" in p:
                    return True
        return False

    # --- chat (mesma assinatura do Gemini) ---------------------------------
    def chat(self, parts: list | None = None, system: str = "",
             tools: list | None = None, contents: list | None = None) -> dict:
        if contents is None:
            if not parts:
                raise ValueError("chat(): informe `parts` ou `contents`")
            contents = [{"role": "user", "parts": parts_to_wire(parts)}]
        body = self._convert(system, contents, tools or [])
        ks = self.data.get("groq") or []
        if not ks:
            raise LLMError("groq: nenhuma chave cadastrada (começam com 'gsk_').")
        tried: set = set()
        while True:
            i = self._pick()
            if i is None or i in tried:
                raise LLMError(f"groq: sem chave livre agora ({len(ks)} cadastrada(s)).")
            tried.add(i)
            key = ks[i]
            self.last_key_masked = keysmod.mask(key)
            status, payload = _http_post(self.API, body, self.timeout,
                                         headers={"Authorization": f"Bearer {key}"})
            if status == 429:
                self.data["cooldowns"][f"g{i}|{self.model}"] = time.time() + 60
                self._persist()
                continue
            if status != 200:
                msg = _error_message(status, payload) or f"HTTP {status}"
                baixo = str(msg).lower()
                if status in (401, 403) or "invalid" in baixo and "key" in baixo:
                    self.data["groq"].pop(i)
                    self._persist()
                    tried.clear()
                    if self.on_log:
                        try: self.on_log(f"🔑 groq {self.last_key_masked} removida (inválida)")
                        except Exception: pass
                    if not self.data["groq"]:
                        raise LLMError("groq: todas as chaves eram inválidas.")
                    continue
                raise LLMError(f"groq: {msg}")
            msg = (payload.get("choices") or [{}])[0].get("message") or {}
            tcs = []
            for tc in msg.get("tool_calls") or []:
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                except ValueError:
                    args = {}
                tcs.append({"name": tc["function"].get("name", ""), "args": args})
            return {"text": msg.get("content") or "", "tool_calls": tcs,
                    "finish_reason": (payload.get("choices") or [{}])[0].get("finish_reason", ""),
                    "raw_content": None, "model": f"groq:{self.model}",
                    "key_masked": self.last_key_masked}


class Router:
    """Orquestrador multi-modelo: chamadas COM imagem vão p/ o subagente de
    visão (Gemini); texto puro vai pro orquestrador rápido (Groq) — roteamento
    pelo payload, sem gastar chamada de classificação. Groq falhou? Gemini."""

    def __init__(self, gem: Gemini, groq: "GroqClient | None" = None):
        self.gem = gem
        self.groq = groq
        self.on_log = None

    def _tem_imagem(self, contents) -> bool:
        for c in contents or []:
            for p in c.get("parts") or []:
                if isinstance(p, dict) and ("inline_data" in p or "image_b64" in p):
                    return True
        return False

    def chat(self, parts=None, system="", tools=None, contents=None) -> dict:
        alvo_contents = contents
        if alvo_contents is None and parts is not None:
            alvo_contents = [{"role": "user", "parts": parts_to_wire(parts)}]
        erro_gem: LLMError | None = None
        if self.groq is not None and not self._tem_imagem(alvo_contents):
            try:
                r = self.groq.chat(parts=parts, system=system, tools=tools,
                                   contents=contents)
                r["provider"] = "groq"
                return r
            except LLMError as e:
                erro_gem = e
                if self.on_log:
                    try: self.on_log(f"🔁 groq indisponível ({e}); usando Gemini")
                    except Exception: pass
        try:
            r = self.gem.chat(parts=parts, system=system, tools=tools, contents=contents)
            r["provider"] = "gemini"
            return r
        except LLMError as e:
            erro_gem = e
        # Gemini caiu (cota/rede) e a chamada TEM imagem: o Groq entra com o
        # modelo de visão em vez de deixar o turno morrer.
        if self.groq is not None:
            if self.on_log:
                try: self.on_log(f"🔁 gemini indisponível ({str(erro_gem)[:80]}) "
                                 "-> groq visão; distribuindo a carga")
                except Exception: pass
            r = self.groq.chat(parts=parts, system=system, tools=tools,
                               contents=contents)
            r["provider"] = "groq"
            return r
        raise erro_gem

    def status(self) -> dict:
        st = self.gem.status()
        try:
            st["groq"] = self.groq.status() if self.groq else None
        except Exception:
            st["groq"] = None
        return st
