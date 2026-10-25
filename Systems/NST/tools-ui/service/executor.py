"""Allowlisted root executor for read-only NST operations; no user-supplied CLI args."""
import hashlib
import json
import os
from pathlib import Path
try:
    import pwd
except ImportError:  # Windows-only fixture imports; WB runtime is Linux.
    pwd = None
import re
import shutil
import subprocess
import sys
import uuid

NST = "/usr/bin/nst"
SOURCE = Path("/mnt/data/var/lib/neirolinks/nst/diagnostics")
EXPORT = Path("/mnt/data/var/lib/neirolinks-tools/exports")
LIMIT = 96 * 1024 * 1024
COMMANDS = {
    "status": [NST, "--json", "status"],
    "check": [NST, "--json", "check"],
    "inventory": [NST, "--json", "onboarding", "collect"],
    "channels": [NST, "--json", "onboarding", "channels"],
    "diagnostics": [NST, "--json", "diagnostics", "collect", "--since", "6h"],
}
BUNDLES = {"inventory", "channels", "diagnostics"}
ARCHIVE_NAME = re.compile(r"nst-(?:onboarding|diagnostics)-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}\.tar\.gz")


def call(action, runner=subprocess.run):
    if action not in COMMANDS:
        raise ValueError("Operation forbidden")
    argv = COMMANDS[action]
    if action == "diagnostics":
        s = runner(COMMANDS["status"], capture_output=True, text=True, timeout=30, check=False)
        if s.returncode == 0 and len(s.stdout) < 131072:
            try:
                c = json.loads(s.stdout).get("controller") or {}
                a = c.get("assignment") or {}
                if c.get("state") == "active" and "hhm" in a.get("capabilities", []):
                    argv = [NST, "--json", "diagnostics", "collect", "hhm", "--since", "6h"]
            except (TypeError, ValueError):
                pass
    proc = runner(argv, capture_output=True, text=True,
                  timeout=240 if action in BUNDLES else 60, check=False)
    if len(proc.stdout) > 131072:
        raise RuntimeError("NST response too large")
    try:
        result = json.loads(proc.stdout)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("NST response invalid") from exc
    if not isinstance(result, dict) or proc.returncode or result.get("final_status") != "ok":
        raise RuntimeError(str(result.get("error", "NST failed") if isinstance(result, dict) else "NST failed")[:160])
    if action == "status":
        c = result.get("controller") or {}
        installed = {}
        for name, state in (result.get("components") or {}).items():
            if isinstance(state, dict):
                installed[name] = str((state.get("manifest") or {}).get("version") or "unknown")
        version_proc = runner([NST, "--json", "--version"], capture_output=True, text=True, timeout=8, check=False)
        try:
            version = str(json.loads(version_proc.stdout).get("version") or "unknown")
        except (TypeError, ValueError):
            version = "unknown"
        return {"final_status": "ok", "serial": (c.get("identity") or {}).get("serial"),
                "registration": c.get("state"), "object": result.get("object"),
                "role": result.get("role"), "nst_version": version, "components": installed}
    if action == "check":
        return {"final_status": "ok", "approved_platform": (result.get("approved_platform") or {}).get("tag"),
                "mutation_required": result.get("mutation_required"),
                "plan_status": (result.get("plan") or {}).get("status")}
    return export(result, action)


def export(result, action):
    path = Path(str(result.get("bundle") or ""))
    if path.parent != SOURCE or not ARCHIVE_NAME.fullmatch(path.name) or path.is_symlink() or not path.is_file():
        raise RuntimeError("NST archive outside allowlisted directory")
    size = path.stat().st_size
    if not 0 < size <= LIMIT:
        raise RuntimeError("NST archive too large")
    def file_sha(filename):
        h = hashlib.sha256()
        with filename.open("rb") as inp:
            for block in iter(lambda: inp.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()

    sha = file_sha(path)
    if sha != result.get("sha256"):
        raise RuntimeError("NST archive checksum mismatch")
    user = pwd.getpwnam("nst-tools")
    EXPORT.mkdir(parents=True, exist_ok=True)
    os.chown(EXPORT, 0, user.pw_gid)
    os.chmod(EXPORT, 0o730)
    name = "nst-" + uuid.uuid4().hex + ".tar.gz"
    dst = EXPORT / name
    fd = os.open(dst, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as output, path.open("rb") as inp:
            shutil.copyfileobj(inp, output, 1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        os.chown(dst, user.pw_uid, user.pw_gid)
        if file_sha(dst) != sha:
            raise RuntimeError("Export verification failed")
    except Exception:
        dst.unlink(missing_ok=True)
        raise
    return {"final_status": "ok", "export": name, "filename": path.name,
            "sha256": sha, "size": size, "mode": action,
            "warnings": (result.get("warnings") or [])[:10]}


def main(argv):
    if len(argv) != 2 or argv[1] not in COMMANDS:
        print('{"final_status":"failed","error":"Forbidden operation"}')
        return 2
    try:
        value = call(argv[1])
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        value = {"final_status": "failed", "error": str(exc)[:180]}
    print(json.dumps(value, ensure_ascii=False))
    return 0 if value["final_status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
