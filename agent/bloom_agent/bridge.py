"""Ponte Colab <-> PC local.

- O addon sobe um receptor HTTP local (127.0.0.1:porta) em thread daemon.
- O túnel ngrok (rodado pelo usuário no PC) expõe esse receptor para a web.
- O notebook no Colab:
    GET  {base}/job/{id}            -> lê o job (JSON)
    GET  {base}/job/{id}/input/{f}  -> baixa arquivos de entrada (foto, parâmetros)
    POST {base}/job/{id}/result     -> devolve o resultado (bytes crus; o nome do
                                       arquivo vai no header X-Result-Name)
    POST {base}/job/{id}/complete   -> JSON de encerramento (status + lista de arquivos)
- Fallback Drive: se o resultado for grande (o ngrok free tem 1 GB/mês na
  direção do PC), o notebook salva em /content/drive/MyDrive/3d-create/jobs/{id}
  e envia um "pointer" pequeno via /complete. O addon usa `gdown`/instruções.

Tudo aqui é Python puro (sem bpy) para poder ser testado fora do Blender.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_PORT = 8791
NGROK_API = "http://127.0.0.1:4040/api/tunnels"
DRIVE_ROOT = "3d-create/jobs"

JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def new_job_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


class BridgeError(RuntimeError):
    pass


class _Handler(BaseHTTPRequestHandler):
    # set por BridgeServer
    bridge: "BridgeServer" = None  # type: ignore[assignment]

    def log_message(self, fmt, *args):  # silencia o stdout
        pass

    def _send(self, code: int, body: bytes, content_type: str = "application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _job_dir(self, job_id: str) -> Path | None:
        if not JOB_ID_RE.match(job_id or ""):
            return None
        d = self.bridge.jobs_root / job_id
        return d if d.is_dir() else None

    def do_GET(self):  # noqa: N802
        p = self.path.split("?")[0]
        if p == "/health":
            self._send_json(200, {"ok": True, "time": time.time()})
            return
        m = re.fullmatch(r"/job/([^/]+)", p)
        if m:
            d = self._job_dir(m.group(1))
            if not d:
                self._send_json(404, {"error": "job não encontrado"})
                return
            job = d / "job.json"
            if job.is_file():
                self._send(200, job.read_bytes(), "application/json")
            else:
                self._send_json(200, {"id": m.group(1), "files": [f.name for f in d.iterdir()]})
            return
        m = re.fullmatch(r"/job/([^/]+)/input/([^/]+)", p)
        if m:
            d = self._job_dir(m.group(1))
            f = d / "input" / m.group(2) if d else None
            if f and f.is_file():
                self._send(200, f.read_bytes(), "application/octet-stream")
            else:
                self._send_json(404, {"error": "arquivo de entrada não encontrado"})
            return
        self._send_json(404, {"error": "rota não encontrada"})

    def do_POST(self):  # noqa: N802
        p = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length", 0) or 0)
        payload = self.rfile.read(length) if length else b""
        m = re.fullmatch(r"/job/([^/]+)/result", p)
        if m:
            d = self._job_dir(m.group(1))
            if not d:
                self._send_json(404, {"error": "job não encontrado"})
                return
            name = self.headers.get("X-Result-Name", "resultado.bin")
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)[:200] or "resultado.bin"
            out = d / "results"
            out.mkdir(parents=True, exist_ok=True)
            (out / safe).write_bytes(payload)
            self._send_json(200, {"ok": True, "file": safe, "bytes": len(payload)})
            return
        m = re.fullmatch(r"/job/([^/]+)/complete", p)
        if m:
            d = self._job_dir(m.group(1))
            if not d:
                self._send_json(404, {"error": "job não encontrado"})
                return
            try:
                info = json.loads(payload.decode("utf-8") or "{}")
            except ValueError:
                info = {"raw": payload[:2000].decode("utf-8", "replace")}
            (d / "complete.json").write_text(
                json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
            self._send_json(200, {"ok": True})
            return
        self._send_json(404, {"error": "rota não encontrada"})


class BridgeServer:
    def __init__(self, root: Path, port: int = DEFAULT_PORT):
        self.root = Path(root)
        self.port = int(port)
        self.jobs_root = self.root / "jobs"
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # --- ciclo de vida ------------------------------------------------------
    def start(self) -> None:
        if self.is_running():
            return
        _Handler.bridge = self
        self._httpd = ThreadingHTTPServer(("127.0.0.1", self.port), _Handler)
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
            self._thread = None

    def is_running(self) -> bool:
        return self._httpd is not None

    @property
    def local_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    # --- jobs ----------------------------------------------------------------
    def create_job(self, kind: str, params: dict, files: dict | None = None) -> str:
        """files: {nome: bytes} | {nome: Path} -> vai para jobs/<id>/input/"""
        job_id = new_job_id()
        d = self.jobs_root / job_id
        (d / "input").mkdir(parents=True, exist_ok=True)
        input_names = []
        if files:
            for name, value in files.items():
                safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)[:200]
                if isinstance(value, Path):
                    data = value.read_bytes()
                elif isinstance(value, str):
                    data = value.encode("utf-8")
                else:
                    data = bytes(value)
                (d / "input" / safe).write_bytes(data)
                input_names.append(safe)
        job = {
            "id": job_id,
            "kind": kind,
            "params": params or {},
            "input_files": input_names,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "base_url": None,          # preenchido por refresh_job_url()
            "drive_folder": f"{DRIVE_ROOT}/{job_id}",
        }
        (d / "job.json").write_text(
            json.dumps(job, indent=2, ensure_ascii=False), encoding="utf-8")
        self.refresh_job_url(job_id)
        return job_id

    def job_dir(self, job_id: str) -> Path | None:
        if not JOB_ID_RE.match(job_id or ""):
            return None
        d = self.jobs_root / job_id
        return d if d.is_dir() else None

    def job_info(self, job_id: str) -> dict:
        d = self.job_dir(job_id)
        if not d:
            raise BridgeError(f"Job {job_id!r} não existe em {self.jobs_root}")
        job = json.loads((d / "job.json").read_text(encoding="utf-8"))
        res = sorted((d / "results").iterdir()) if (d / "results").is_dir() else []
        comp = d / "complete.json"
        job["results"] = [{"name": f.name, "bytes": f.stat().st_size} for f in res]
        job["complete"] = json.loads(comp.read_text(encoding="utf-8")) if comp.is_file() else None
        return job

    def result_file(self, job_id: str, name: str) -> Path | None:
        d = self.job_dir(job_id)
        if not d:
            return None
        f = d / "results" / name
        return f if f.is_file() else None

    # --- ngrok -----------------------------------------------------------------
    def refresh_job_url(self, job_id: str) -> str | None:
        url = ngrok_public_url(self.port)
        d = self.job_dir(job_id)
        if d:
            job = json.loads((d / "job.json").read_text(encoding="utf-8"))
            job["base_url"] = url
            (d / "job.json").write_text(
                json.dumps(job, indent=2, ensure_ascii=False), encoding="utf-8")
        return url


def ngrok_public_url(port: int, timeout: float = 3.0) -> str | None:
    """Procura a URL pública do ngrok local para a porta (API 127.0.0.1:4040)."""
    try:
        with urllib.request.urlopen(NGROK_API, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    for t in data.get("tunnels", []):
        cfg = (t.get("config") or {}).get("addr", "")
        pub = t.get("public_url")
        if pub and str(cfg).endswith(f":{int(port)}"):
            return pub
    return None


def health_check(port: int, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as r:
            return r.status == 200
    except OSError:
        return False
