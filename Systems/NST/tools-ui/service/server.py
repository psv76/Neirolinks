"""Loopback-only, read-only Web UI for NST. Authentication lives in WB's admin service gate."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import subprocess
import threading
import time
from urllib.parse import urlsplit, parse_qs

WEB = Path("/usr/share/neirolinks-tools/web")
EXPORT = Path("/mnt/data/var/lib/neirolinks-tools/exports")
EXECUTOR = "/usr/lib/neirolinks-tools/executor.py"
ACTIONS = ("status", "check", "inventory", "channels", "diagnostics")
BUNDLES = ("inventory", "channels", "diagnostics")
MAX_EXPORT = 96 * 1024 * 1024
TTL = 15 * 60


class Jobs:
    def __init__(self, executor=None):
        self.executor = executor or self._execute
        self.lock = threading.RLock()
        self.jobs = {}
        self.busy = None

    @staticmethod
    def _execute(action):
        argv = ["/usr/bin/sudo", "-n", "/usr/bin/python3", "-I", EXECUTOR, action]
        result = subprocess.run(argv, capture_output=True, text=True, timeout=280, check=False)
        if len(result.stdout) > 131072:
            raise RuntimeError("Executor output too large")
        data = json.loads(result.stdout)
        if result.returncode or data.get("final_status") != "ok":
            raise RuntimeError(str(data.get("error") or "NST failed")[:180])
        return data

    def _expire(self):
        now = time.monotonic()
        for key, value in list(self.jobs.items()):
            if value.get("done") and now - value["created"] > TTL:
                name = (value.get("payload") or {}).get("export", "")
                if re.fullmatch(r"nst-[0-9a-f]{32}\.tar\.gz", name):
                    candidate = EXPORT / name
                    if candidate.is_file() and not candidate.is_symlink():
                        try:
                            candidate.unlink()
                        except OSError:
                            pass
                del self.jobs[key]

    def start(self, action):
        if action not in ACTIONS:
            raise ValueError("Forbidden action")
        with self.lock:
            self._expire()
            if self.busy:
                raise RuntimeError("NST operation already in progress")
            job_id = secrets.token_hex(16)
            self.jobs[job_id] = {"id": job_id, "action": action, "created": time.monotonic(),
                                 "state": "running", "done": False, "token": secrets.token_urlsafe(32)}
            self.busy = job_id
        threading.Thread(target=self._run, args=(job_id, action), daemon=True).start()
        return job_id

    def _run(self, job_id, action):
        try:
            payload = self.executor(action)
            with self.lock:
                job = self.jobs[job_id]
                job["state"] = "complete"
                job["payload"] = payload
        except Exception as exc:
            with self.lock:
                job = self.jobs[job_id]
                job["state"] = "failed"
                job["error"] = str(exc)[:180]
        finally:
            with self.lock:
                self.jobs[job_id]["done"] = True
                self.busy = None

    def get(self, job_id):
        with self.lock:
            self._expire()
            job = self.jobs.get(job_id)
            if not job:
                return None
            result = {"id": job_id, "action": job["action"], "state": job["state"]}
            if job.get("error"):
                result["error"] = job["error"]
            payload = job.get("payload")
            if payload:
                result["result"] = {k: v for k, v in payload.items() if k != "export"}
                if job["action"] in BUNDLES:
                    result["download"] = "/api/download/" + job_id + "?token=" + job["token"]
            return result

    def download(self, job_id, token):
        with self.lock:
            self._expire()
            job = self.jobs.get(job_id)
            if not job or job["state"] != "complete" or job["action"] not in BUNDLES:
                return None
            if not token or not secrets.compare_digest(job["token"], token):
                return None
            payload = job.get("payload") or {}
            name = payload.get("export", "")
            if not re.fullmatch(r"nst-[0-9a-f]{32}\.tar\.gz", name):
                return None
            path = EXPORT / name
            if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_EXPORT:
                return None
            return path, str(payload.get("filename") or "nst-diagnostics.tar.gz")


class Handler(BaseHTTPRequestHandler):
    jobs = Jobs()
    server_version = "NEIROLINKS-Tools/1.0"
    sys_version = ""

    def log_message(self, *_args):
        # No query-string logs; download tokens are sensitive.
        pass

    def headers_common(self, code=200, mime="application/json; charset=utf-8", size=None):
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        if size is not None:
            self.send_header("Content-Length", str(size))
        self.end_headers()

    def send_json(self, code, data):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.headers_common(code, size=len(raw))
        self.wfile.write(raw)

    def do_GET(self):
        url = urlsplit(self.path)
        name = url.path
        if name in ("/", "/index.html", "/app.js", "/style.css"):
            filename = "index.html" if name == "/" else name[1:]
            path = WEB / filename
            if not path.is_file() or path.is_symlink():
                return self.send_json(404, {"error": "Page not found"})
            raw = path.read_bytes()
            mime = {"index.html": "text/html; charset=utf-8", "app.js": "application/javascript; charset=utf-8",
                    "style.css": "text/css; charset=utf-8"}[filename]
            self.headers_common(mime=mime, size=len(raw))
            return self.wfile.write(raw)
        if re.fullmatch(r"/api/jobs/[0-9a-f]{32}", name):
            result = self.jobs.get(name.rsplit("/", 1)[-1])
            return self.send_json(200 if result else 404, result or {"error": "Not found"})
        if re.fullmatch(r"/api/download/[0-9a-f]{32}", name):
            target = self.jobs.download(name.rsplit("/", 1)[-1], parse_qs(url.query).get("token", [""])[0])
            if not target:
                return self.send_json(404, {"error": "Archive unavailable"})
            path, filename = target
            self.send_response(200)
            self.send_header("Content-Type", "application/gzip")
            self.send_header("Content-Disposition", 'attachment; filename="' +
                             re.sub(r"[^a-zA-Z0-9_.-]", "_", filename) + '"')
            self.send_header("Content-Length", str(path.stat().st_size))
            self.send_header("Cache-Control", "private, no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            try:
                with path.open("rb") as f:
                    while chunk := f.read(65536):
                        self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionError):
                pass
            return
        self.send_json(404, {"error": "Unknown endpoint"})

    def do_POST(self):
        url = urlsplit(self.path)
        match = re.fullmatch(r"/api/jobs/(status|check|inventory|channels|diagnostics)", url.path)
        if not match:
            return self.send_json(404, {"error": "Unknown operation"})
        origin = urlsplit(self.headers.get("Origin", ""))
        host = self.headers.get("Host", "")
        if (self.headers.get("X-NST-Intent") != "ui" or origin.scheme not in ("http", "https")
                or origin.netloc != host or self.headers.get("Sec-Fetch-Site", "same-origin") != "same-origin"
                or self.headers.get("Content-Length") not in ("0", "2")
                or self.headers.get("Content-Type", "") not in ("", "application/json")):
            return self.send_json(403, {"error": "Origin or request rejected"})
        if self.headers.get("Content-Length") == "2" and self.rfile.read(2) != b"{}":
            return self.send_json(400, {"error": "Body not allowed"})
        try:
            job_id = self.jobs.start(match.group(1))
        except RuntimeError as exc:
            return self.send_json(409, {"error": str(exc)})
        self.send_json(202, {"job": job_id})


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 18415), Handler)
    server.daemon_threads = True
    server.serve_forever(poll_interval=0.25)


if __name__ == "__main__":
    main()
