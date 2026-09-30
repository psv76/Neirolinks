"""Wiren Board hardware identity and generated controller-registry policy."""
import hashlib
from pathlib import Path
import re

from .layout import DATA_DIR
from .util import Error, decode, require, safe_relative

SERIAL_PATHS = (
    "/var/lib/wirenboard/short_sn",
    "/var/lib/wirenboard/short_sn.conf",
)
REGISTRY_PATH = DATA_DIR + "/controller-registry.json"
SERIAL_RE = re.compile(r"^[A-Z0-9]{5,32}$")
NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_STATES = frozenset(("planned", "active", "retired"))
ALLOWED_ROLES = frozenset(("boiler", "gazebo", "house", "service", "infrastructure"))


def _fixed(root, logical):
    return Path(root).absolute() / logical.lstrip("/")


def _text(path):
    try:
        return path.read_text(encoding="utf-8", errors="strict").strip()
    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError, UnicodeError):
        return ""


def read_hardware_identity(root="/"):
    """Read operational WB serial locally. Hostname/IP/MQTT are deliberately ignored."""
    serial = None
    serial_source = None
    for logical in SERIAL_PATHS:
        value = _text(_fixed(root, logical)).upper()
        if not value:
            continue
        if SERIAL_RE.fullmatch(value):
            serial, serial_source = value, logical
            break

    fingerprint_parts = []
    cpuinfo = _text(_fixed(root, "/proc/cpuinfo"))
    for line in cpuinfo.splitlines():
        if ":" in line and line.split(":", 1)[0].strip().lower() == "serial":
            value = line.split(":", 1)[1].strip().lower()
            if value:
                fingerprint_parts.append(("cpu_serial", value))
            break

    mmc_root = _fixed(root, "/sys/class/mmc_host/mmc0")
    try:
        serial_files = sorted(mmc_root.glob("mmc*/serial")) if mmc_root.is_dir() else []
    except OSError:
        serial_files = []
    for path in serial_files:
        value = _text(path).lower()
        if value:
            fingerprint_parts.append(("emmc_serial", value))

    fingerprint = None
    if fingerprint_parts:
        canonical = "\n".join(name + "=" + value for name, value in fingerprint_parts).encode("utf-8")
        fingerprint = {
            "sha256": hashlib.sha256(canonical).hexdigest(),
            "sources": sorted({name for name, _ in fingerprint_parts}),
        }

    return {
        "serial": serial,
        "serial_source": serial_source,
        "fingerprint": fingerprint,
    }


def validate_profile(profile, serial=None):
    require(type(profile) is dict, "Controller profile must be an object")
    allowed = {
        "schema", "name", "node", "role", "state", "capabilities",
        "components", "object_files", "diagnostics_profile", "fingerprint_sha256",
    }
    required = {
        "schema", "name", "node", "role", "state", "capabilities",
        "diagnostics_profile",
    }
    require(set(profile).issubset(allowed) and required.issubset(profile), "Invalid controller profile fields")
    require(profile["schema"] == 1, "Invalid controller profile schema")
    require(isinstance(profile["name"], str) and bool(profile["name"].strip()), "Invalid controller human name")
    require(isinstance(profile["node"], str) and NAME_RE.fullmatch(profile["node"]) is not None, "Invalid controller node")
    require(profile["role"] in ALLOWED_ROLES, "Invalid controller role: " + str(profile["role"]))
    require(profile["state"] in ALLOWED_STATES, "Invalid controller state: " + str(profile["state"]))
    capabilities = profile["capabilities"]
    require(type(capabilities) is list and len(capabilities) == len(set(capabilities)), "Invalid controller capabilities")
    for capability in capabilities:
        require(isinstance(capability, str) and NAME_RE.fullmatch(capability) is not None,
                "Invalid controller capability: " + str(capability))
    components = profile.get("components", {})
    require(type(components) is dict, "Invalid desired components")
    for component, request in components.items():
        require(NAME_RE.fullmatch(component) is not None, "Invalid desired component: " + str(component))
        require(type(request) is dict and set(request) == {"track"} and request["track"] == "stable",
                "Invalid desired component request: " + component)
    object_files = profile.get("object_files", [])
    require(type(object_files) is list, "Invalid object_files")
    for item in object_files:
        require(type(item) is dict and set(item) == {"source", "target"}, "Invalid object file request")
        safe_relative(item["source"])
        require(isinstance(item["target"], str) and item["target"].startswith("/"), "Invalid object file target")
    diagnostic = profile["diagnostics_profile"]
    require(isinstance(diagnostic, str) and diagnostic.endswith(".json")
            and not diagnostic.startswith("/") and ".." not in diagnostic.split("/"),
            "Invalid diagnostics profile reference")
    if "fingerprint_sha256" in profile:
        require(isinstance(profile["fingerprint_sha256"], str)
                and SHA256_RE.fullmatch(profile["fingerprint_sha256"]) is not None,
                "Invalid controller fingerprint")
    if serial is not None:
        require(SERIAL_RE.fullmatch(serial) is not None, "Invalid WB serial: " + str(serial))
    return profile


class ControllerRegistry:
    def __init__(self, data):
        require(type(data) is dict and data.get("schema") == 1, "Invalid controller registry schema")
        require(set(data).issubset({"schema", "source", "controllers"}), "Invalid controller registry fields")
        require(type(data.get("controllers")) is dict, "Invalid controller registry")
        self.data = data
        for serial, entry in data["controllers"].items():
            require(SERIAL_RE.fullmatch(serial) is not None, "Invalid registry serial: " + str(serial))
            require(type(entry) is dict, "Invalid controller registry entry")
            required = {
                "object", "name", "node", "role", "state", "capabilities",
                "diagnostics_profile", "profile",
            }
            require(required.issubset(entry), "Incomplete controller registry entry")
            validate_profile({
                "schema": 1,
                "name": entry["name"],
                "node": entry["node"],
                "role": entry["role"],
                "state": entry["state"],
                "capabilities": entry["capabilities"],
                "diagnostics_profile": entry["diagnostics_profile"],
                **({"fingerprint_sha256": entry["fingerprint_sha256"]}
                   if "fingerprint_sha256" in entry else {}),
            }, serial)
            require(isinstance(entry["object"], str) and bool(entry["object"]), "Invalid registry object")
            require(isinstance(entry["profile"], str) and entry["profile"].endswith(".json"),
                    "Invalid registry profile reference")

    @classmethod
    def from_path(cls, path):
        return cls(decode(Path(path).read_bytes()))

    def resolve(self, identity):
        serial = identity.get("serial") if isinstance(identity, dict) else None
        if not serial:
            return {
                "state": "identity_unavailable",
                "identity": identity,
                "assignment": None,
                "mutation_allowed": False,
                "reason": "CONTROLLER_IDENTITY_UNAVAILABLE: WB serial could not be read locally",
            }
        entry = self.data["controllers"].get(serial)
        if entry is None:
            return {
                "state": "unknown",
                "identity": identity,
                "assignment": None,
                "mutation_allowed": False,
                "reason": "CONTROLLER_NOT_REGISTERED: " + serial,
            }

        assignment = dict(entry)
        expected = assignment.get("fingerprint_sha256")
        observed = (identity.get("fingerprint") or {}).get("sha256")
        if expected is None:
            fingerprint_status = "not_pinned"
        elif observed is None:
            fingerprint_status = "unavailable"
        elif observed == expected:
            fingerprint_status = "match"
        else:
            fingerprint_status = "mismatch"

        state = assignment["state"]
        allowed = state == "active" and fingerprint_status not in ("unavailable", "mismatch")
        if state == "planned":
            reason = "CONTROLLER_PLANNED: production mutation is disabled"
        elif state == "retired":
            reason = "CONTROLLER_RETIRED: controller is out of service"
        elif fingerprint_status == "unavailable":
            reason = "CONTROLLER_FINGERPRINT_UNAVAILABLE: pinned hardware fingerprint cannot be verified"
        elif fingerprint_status == "mismatch":
            reason = "CONTROLLER_FINGERPRINT_MISMATCH: hardware differs from registered controller"
        else:
            reason = None
        return {
            "state": state,
            "identity": identity,
            "assignment": assignment,
            "fingerprint_status": fingerprint_status,
            "mutation_allowed": allowed,
            "reason": reason,
        }


def load_controller_context(root="/", registry_path=None):
    from .layout import CONFIG_DIR, target
    identity = read_hardware_identity(root)
    saved = CONFIG_DIR + '/controller-registry.json'
    logical = registry_path or (saved if target(root, saved).is_file() else REGISTRY_PATH)
    path = _fixed(root, logical) if str(logical).startswith("/") else Path(logical)
    try:
        registry = ControllerRegistry.from_path(path)
    except (Error, OSError, ValueError, KeyError, TypeError) as exc:
        return {
            "state": "registry_unavailable",
            "identity": identity,
            "assignment": None,
            "mutation_allowed": False,
            "reason": "CONTROLLER_REGISTRY_UNAVAILABLE: " + str(exc),
        }
    return registry.resolve(identity)
