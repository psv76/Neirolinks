"""Read-only evidence collection for NST diagnostics.

The collector may write only its own bundle under NST durable storage. It never
publishes MQTT, changes setpoints, restarts services, or invokes engineering
runtime mutation APIs.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import tarfile
import tempfile
import uuid

from .layout import DATA_DIR, LOG_DIR, STATE_DIR
from .platform import load_platform_state
from .util import Error, digest, read_json, require

DIAGNOSTICS_DIR = STATE_DIR + "/diagnostics"
MAX_WINDOW = timedelta(days=7)
DEFAULT_WINDOW = timedelta(hours=6)
SAFE_UNITS = {"wb-rules", "wb-mqtt-db", "wb-mqtt-serial"}
SENSITIVE_KEY = re.compile(r"(password|passwd|secret|token|credential|private[_-]?key|api[_-]?key)", re.I)
SENSITIVE_PATH = re.compile(r"(^|/)(shadow|gshadow|id_rsa|id_ed25519)(?:$|/)|\.(?:pem|key|p12|pfx)$", re.I)


def utc_now():
    return datetime.now(timezone.utc)


def iso(value):
    return value.astimezone(timezone.utc).isoformat()


def parse_since(value, end=None):
    end = end or utc_now()
    if value is None:
        return end - DEFAULT_WINDOW
    m = re.fullmatch(r"([1-9][0-9]*)([mhd])", value)
    if m:
        amount = int(m.group(1))
        delta = {"m": timedelta(minutes=amount), "h": timedelta(hours=amount),
                 "d": timedelta(days=amount)}[m.group(2)]
        require(delta <= MAX_WINDOW, "Diagnostic window exceeds 7 days")
        return end - delta
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Error("Invalid --since; use 30m, 6h, 1d or ISO-8601") from exc
    require(parsed.tzinfo is not None, "Diagnostic --since ISO timestamp requires timezone")
    parsed = parsed.astimezone(timezone.utc)
    require(parsed <= end, "Diagnostic --since is in the future")
    require(end - parsed <= MAX_WINDOW, "Diagnostic window exceeds 7 days")
    return parsed


def validate_profile(profile):
    require(type(profile) is dict, "Invalid diagnostics profile")
    required = {"schema", "name", "component", "semantics", "journals", "current_controls",
                "history_channels", "config_files", "source_files", "max_history_records"}
    require(set(profile) == required and profile["schema"] == 1, "Invalid diagnostics profile fields/schema")
    require(isinstance(profile["name"], str) and profile["name"], "Invalid diagnostics profile name")
    require(isinstance(profile["component"], str) and profile["component"], "Invalid diagnostics component")
    require(type(profile["semantics"]) is dict
            and set(profile["semantics"]) == {"command", "readback", "physical_result"},
            "Invalid diagnostics semantics")
    require(type(profile["journals"]) is list and all(u in SAFE_UNITS for u in profile["journals"]),
            "Unsafe diagnostics journal unit")
    require(len(profile["journals"]) == len(set(profile["journals"])), "Duplicate diagnostics journal unit")
    require(type(profile["current_controls"]) is list, "Invalid diagnostics current controls")
    seen = set()
    for item in profile["current_controls"]:
        require(type(item) is dict and set(item) == {"path", "kind"}, "Invalid diagnostics control")
        require(isinstance(item["path"], str) and "/" in item["path"], "Invalid diagnostics control path")
        require(item["kind"] in ("command", "readback", "measurement", "calculated"),
                "Invalid diagnostics control semantics")
        require(item["path"] not in seen, "Duplicate diagnostics control")
        seen.add(item["path"])
    for key in ("history_channels", "config_files", "source_files"):
        require(type(profile[key]) is list and all(isinstance(v, str) and v for v in profile[key]),
                "Invalid diagnostics " + key)
        require(len(profile[key]) == len(set(profile[key])), "Duplicate diagnostics " + key)
    require(type(profile["max_history_records"]) is int and 1 <= profile["max_history_records"] <= 100000,
            "Invalid diagnostics history limit")
    for path in profile["config_files"] + profile["source_files"]:
        require(path.startswith("/"), "Diagnostics file path must be absolute")
        require(SENSITIVE_PATH.search(path) is None, "Sensitive path forbidden by diagnostics policy: " + path)
    return profile


def redact_text(data):
    """Redact credential-shaped values but preserve an original SHA separately."""
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        text = data.decode("utf-8", errors="replace")
        lines = []
        for line in text.splitlines(True):
            if SENSITIVE_KEY.search(line) and any(x in line for x in ("=", ":")):
                sep = "=" if "=" in line else ":"
                key, _ = line.split(sep, 1)
                ending = "\n" if line.endswith("\n") else ""
                lines.append(key + sep + " <REDACTED>" + ending)
            else:
                lines.append(line)
        return "".join(lines).encode("utf-8"), data != "".join(lines).encode("utf-8")

    redacted = False
    def walk(item):
        nonlocal redacted
        if isinstance(item, dict):
            result = {}
            for key, val in item.items():
                if SENSITIVE_KEY.search(str(key)):
                    result[key] = "<REDACTED>"
                    redacted = True
                else:
                    result[key] = walk(val)
            return result
        if isinstance(item, list):
            return [walk(v) for v in item]
        return item
    clean = walk(value)
    if not redacted:
        return data, False
    return (json.dumps(clean, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"), True


class Diagnostics:
    def __init__(self, engine, profiles=None):
        self.engine = engine
        self.profiles = profiles or {
            "hhm": DATA_DIR + "/diagnostics/ivolga-boiler-hhm-v1.json",
        }

    def profile(self, component):
        require(component in self.profiles, "No diagnostics profile for component: " + str(component))
        source = self.profiles[component]
        if isinstance(source, dict):
            return validate_profile(source)
        return validate_profile(read_json(self.engine.target(source)))

    def _write_json(self, root, relative, value):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    def _copy_file(self, root, logical, category, inventory):
        require(SENSITIVE_PATH.search(logical) is None, "Sensitive path forbidden: " + logical)
        path = self.engine.target(logical)
        entry = {"path": logical, "status": "missing"}
        if not path.is_file():
            inventory.append(entry)
            return
        require(not path.is_symlink(), "Diagnostics refuses symlink source: " + logical)
        raw = path.read_bytes()
        entry.update(status="ok", sha256=digest(raw), size=len(raw))
        out = raw
        if category == "config":
            out, redacted = redact_text(raw)
            entry["redacted"] = redacted
            if redacted:
                entry["bundle_sha256"] = digest(out)
        bundle_path = root / category / logical.lstrip("/")
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_bytes(out)
        inventory.append(entry)

    def _audit(self, root, start, end):
        folder = self.engine.target(LOG_DIR)
        items = []
        if folder.is_dir():
            for path in sorted(folder.glob("*.json")):
                if path.is_symlink() or not path.is_file():
                    continue
                try:
                    value = read_json(path)
                    stamp = datetime.fromisoformat(value["time"].replace("Z", "+00:00")).astimezone(timezone.utc)
                except (OSError, ValueError, KeyError, TypeError):
                    continue
                if start <= stamp <= end:
                    items.append(value)
        self._write_json(root, "nst/audit.json", items)

    def _checksums(self, root):
        rows = []
        for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "checksums.sha256"):
            rows.append(digest(path.read_bytes()) + "  " + path.relative_to(root).as_posix())
        (root / "checksums.sha256").write_text("\n".join(rows) + "\n", encoding="ascii")

    def collect(self, component=None, since=None):
        require(component is not None, "Component diagnostics profile required; use e.g. 'diagnostics collect hhm'")
        profile = self.profile(component)
        end = utc_now()
        start = parse_since(since, end)
        bundle_id = end.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        destination = self.engine.target(DIAGNOSTICS_DIR + "/nst-diagnostics-" + bundle_id + ".tar.gz")
        destination.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="nst-diagnostics-") as tmp:
            root = Path(tmp) / "bundle"
            root.mkdir()
            status = self.engine.read_operation("status")
            platform = load_platform_state(self.engine)
            controller = self.engine.controller
            metadata = {
                "schema": 1,
                "bundle_id": bundle_id,
                "created_at": iso(end),
                "window": {"from": iso(start), "to": iso(end)},
                "component": component,
                "controller": controller,
                "object": status.get("object"),
                "node": (controller or {}).get("assignment", {}).get("node") if controller else None,
                "role": status.get("role"),
                "semantics": profile["semantics"],
                "warnings": [],
            }
            self._write_json(root, "meta.json", metadata)
            self._write_json(root, "nst/status.json", status)
            self._write_json(root, "nst/platform.json", platform)

            inventory = []
            for logical in profile["source_files"]:
                self._copy_file(root, logical, "sources", inventory)
            for logical in profile["config_files"]:
                self._copy_file(root, logical, "config", inventory)
            self._write_json(root, "installed-files.json", inventory)

            current = []
            for item in profile["current_controls"]:
                row = dict(item)
                try:
                    row["value"] = self.engine.system.control(item["path"], timeout=5)
                    row["status"] = "ok"
                except (Error, OSError, ValueError) as exc:
                    row.update(status="unavailable", error=str(exc))
                current.append(row)
            self._write_json(root, "current-controls.json", current)

            for unit in profile["journals"]:
                try:
                    content = self.engine.system.journal_unit(unit, iso(start), iso(end))
                except (Error, OSError, ValueError) as exc:
                    metadata["warnings"].append("journal " + unit + ": " + str(exc))
                    content = ""
                path = root / "journals" / (unit + ".log")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            try:
                history = self.engine.system.history(profile["history_channels"], iso(start), iso(end),
                                                     profile["max_history_records"])
                history_path = root / "history" / "mqtt.csv"
                history_path.parent.mkdir(parents=True, exist_ok=True)
                history_path.write_text(history, encoding="utf-8")
            except (Error, OSError, ValueError) as exc:
                metadata["warnings"].append("mqtt history: " + str(exc))
                self._write_json(root, "history/unavailable.json", {"error": str(exc)})

            self._audit(root, start, end)
            # Rewrite metadata after optional-source warnings are known.
            self._write_json(root, "meta.json", metadata)
            self._checksums(root)
            with tarfile.open(destination, "w:gz") as tar:
                for path in sorted(root.rglob("*")):
                    if path.is_file():
                        tar.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)

        return {
            "command": "diagnostics",
            "action": "collect",
            "component": component,
            "window": {"from": iso(start), "to": iso(end)},
            "bundle": str(destination),
            "sha256": digest(destination.read_bytes()),
            "warnings": metadata["warnings"],
            "final_status": "ok",
        }
