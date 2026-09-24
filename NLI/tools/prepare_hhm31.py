#!/usr/bin/env python3
"""Build reviewed HHM 3.1 role manifests from immutable Git blobs, offline only."""
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


def prepare(commit, role, output):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(ROOT), *args])
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or git("rev-parse", commit + "^{commit}").decode().strip() != commit:
        raise ValueError("Use the complete immutable commit SHA")
    if role not in ("boiler", "gazebo"):
        raise ValueError("Unknown HHM role")
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
    if not re.search(r"version\s*:\s*['\"]3\.1\.0['\"]", config) or not re.search(
            r"healthContract\s*:\s*['\"]m1w2-health-v1['\"]", config):
        raise ValueError("This builder requires reviewed HHM 3.1.0 / m1w2-health-v1 source")
    control = ("HHM3_FSE" if role == "boiler" else "NL_combo_thermostat_504") + "/sensor_health_contract"
    manifest = dict(schema=1, component="hhm", version="3.1.0+" + commit[:12], object="05_31_Ivolga_13", role=role,
                    release=dict(repository="psv76/Neirolinks", commit=commit), files=entries,
                    services=dict(stop=["wb-rules"], start=["wb-rules"]), preflight=["identity", "drift", "hhm"],
                    verify=dict(controls=[dict(path=control, equals="m1w2-health-v1")],
                                runtime_version="3.1.0", health_contract="m1w2-health-v1"),
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
    name = "hhm-" + role + "-3.1.json"
    (output / name).write_bytes(data)
    (output / (name + ".sha256")).write_text(hashlib.sha256(data).hexdigest() + "  " + name + "\n", encoding="ascii")
    print(name + " SHA256 " + hashlib.sha256(data).hexdigest())
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--role", required=True, choices=("boiler", "gazebo"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    prepare(args.commit, args.role, args.output)
