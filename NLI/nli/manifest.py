"""Strict executable manifest contract. No shell hooks or executable expressions."""
import re
from .util import require, safe_relative

SHA = r"[0-9a-f]{64}"
NAME = r"[a-z][a-z0-9-]{0,63}"
SERVICES = {"wb-rules", "wb-mqtt-serial"}


def keys(obj, required, optional=()):
    require(type(obj) is dict, "Expected object")
    require(set(required) <= obj.keys() and obj.keys() <= set(required) | set(optional),
            "Missing/unknown fields: " + str(set(required) ^ obj.keys()))


def match(value, pattern, label):
    require(isinstance(value, str) and re.fullmatch(pattern, value) is not None, "Invalid " + label)


def validate(m):
    keys(m, ("schema", "component", "version", "object", "role", "release", "files",
             "services", "preflight", "verify", "rollback"))
    require(type(m["schema"]) is int and m["schema"] == 1, "Unsupported manifest schema")
    match(m["component"], NAME, "component")
    for name in ("version", "object", "role"):
        match(m[name], r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,127}", name)
    keys(m["release"], ("commit", "repository"))
    match(m["release"]["commit"], r"[0-9a-f]{40}", "immutable commit")
    match(m["release"]["repository"], r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", "repository")
    require(type(m["files"]) is list and 0 < len(m["files"]) <= 256, "Empty/oversize payload")
    targets = set()
    for f in m["files"]:
        keys(f, ("source", "target", "sha256"))
        safe_relative(f["source"])
        require(isinstance(f["target"], str) and f["target"].startswith("/etc/"), "Target must be in /etc")
        safe_relative(f["target"][1:])
        require(f["target"] not in targets, "Duplicate target")
        require("507" not in f["target"] and "PersistentStorage" not in f["target"], "Protected target")
        targets.add(f["target"])
        match(f["sha256"], SHA, "SHA-256")
    keys(m["services"], ("stop", "start"))
    for action in ("stop", "start"):
        seq = m["services"][action]
        require(type(seq) is list and all(isinstance(s, str) and s in SERVICES for s in seq), "Unsafe service")
        require(len(seq) == len(set(seq)), "Duplicate service")
    require(set(m["services"]["stop"]) == set(m["services"]["start"]), "Unbalanced services")
    require(m["preflight"] in (["identity", "drift"], ["identity", "drift", "hhm"]), "Unknown preflight")
    require(m["rollback"] == "previous-managed-release", "Unknown rollback policy")
    keys(m["verify"], ("controls", "runtime_version", "health_contract"))
    match(m["verify"]["runtime_version"], r"[A-Za-z0-9_.+-]{1,128}", "runtime version")
    require(m["verify"]["health_contract"] in ("legacy-3.0", "m1w2-health-v1", "none"), "Unknown health contract")
    require(type(m["verify"]["controls"]) is list and len(m["verify"]["controls"]) <= 100, "Invalid controls")
    for c in m["verify"]["controls"]:
        keys(c, ("path",), ("equals",))
        match(c["path"], r"[A-Za-z0-9_.-]+/[A-Za-z0-9_ .-]+", "read-only control")
        if "equals" in c:
            require(isinstance(c["equals"], str) and len(c["equals"]) < 512, "Invalid expected value")
    return m
