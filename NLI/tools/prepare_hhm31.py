#!/usr/bin/env python3
"""Неизменяемые manifests HHM 3.1/3.2/3.3; только подготовка файлов, без установки."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "NLI"))
from nli.manifest import validate
from nli.plugins import BOILER, GAZEBO, HHM


def prepare(commit, role, output, version="3.1"):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(ROOT), *args])
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or git("rev-parse", commit + "^{commit}").decode().strip() != commit:
        raise ValueError("Use the complete immutable commit SHA")
    if role not in ("boiler", "gazebo"):
        raise ValueError("Unknown HHM role")
    if version not in ("3.1", "3.2", "3.3"):
        raise ValueError("Поддерживаются только HHM 3.1, 3.2 и 3.3")
    base = "objects/05_31_Ivolga_13/HHM3_FSE/"
    entries, payload = [], {}
    for target in sorted(BOILER if role == "boiler" else GAZEBO):
        name = target.rsplit("/", 1)[1]
        source = (base + "modules/" + name if "modules/" in target else
                  "objects/05_31_Ivolga_13/Wirenboard/wb-rules/" + name if name == "600_Heat_diagnostics.js" else
                  base + role + "/wb-rules/" + name)
        data = git("show", commit + ":" + source)
        payload[source] = data
        entries.append(dict(source=source, target=target, sha256=hashlib.sha256(data).hexdigest()))
    config = payload[base + "modules/HHM3Config.js"].decode("utf-8")
    if not re.search(r"version\s*:\s*['\"]" + re.escape(version) + r"['\"]", config) or not re.search(
            r"healthContract\s*:\s*['\"]m1w2-health-v1['\"]", config):
        raise ValueError("Требуются исходники HHM " + version + " / m1w2-health-v1")
    control = ("HHM3_FSE" if role == "boiler" else "NL_combo_thermostat_504") + "/sensor_health_contract"
    manifest = dict(schema=1, component="hhm", version=version, object="05_31_Ivolga_13", role=role,
                    release=dict(repository="psv76/Neirolinks", commit=commit), files=entries,
                    services=dict(stop=["wb-rules"], start=["wb-rules"]), preflight=["identity", "drift", "hhm"],
                    verify=dict(controls=[dict(path=control, equals="m1w2-health-v1")],
                                runtime_version=version, health_contract="m1w2-health-v1"),
                    rollback="previous-managed-release")
    validate(manifest)
    HHM().validate(manifest, {})
    # Validate everything before creating output. No controller I/O or config writes.
    output.mkdir(parents=True, exist_ok=True)
    for source, data in payload.items():
        dest = output / "payload" / source
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    data = (json.dumps(manifest, indent=2) + "\n").encode()
    name = "hhm-" + role + "-" + version + ".json"
    (output / name).write_bytes(data)
    (output / (name + ".sha256")).write_text(hashlib.sha256(data).hexdigest() + "  " + name + "\n", encoding="ascii")
    print(name + " SHA256 " + hashlib.sha256(data).hexdigest())
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--role", required=True, choices=("boiler", "gazebo"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--version", default="3.1", choices=("3.1", "3.2", "3.3"))
    args = parser.parse_args()
    prepare(args.commit, args.role, args.output, args.version)
