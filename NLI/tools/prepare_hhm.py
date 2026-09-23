#!/usr/bin/env python3
"""Build a role manifest from immutable Git blobs; never inspect a real controller."""
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
from nli.plugins import BOILER, GAZEBO


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def prepare(commit, role, output):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Use the complete immutable commit SHA")
    if git("rev-parse", commit + "^{commit}").decode().strip() != commit:
        raise ValueError("Commit does not resolve exactly")
    base = "objects/05_31_Ivolga_13/HHM3_FSE/"
    entries = []
    runtime = None
    for target in sorted(BOILER if role == "boiler" else GAZEBO):
        name = target.rsplit("/", 1)[1]
        if "modules/" in target:
            source = base + "modules/" + name
        elif name == "600_Heat_diagnostics.js":
            source = "objects/05_31_Ivolga_13/Wirenboard/wb-rules/" + name
        else:
            source = base + role + "/wb-rules/" + name
        data = git("show", commit + ":" + source)
        dest = output / "payload" / source
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        if name == "HHM3Config.js":
            runtime = re.search(rb"version\s*:\s*['\"]([^'\"]+)", data).group(1).decode()
        entries.append(dict(source=source, target=target, sha256=hashlib.sha256(data).hexdigest()))
    if not runtime.startswith("3.0."):
        raise ValueError("For HHM >=3.1 supply a reviewed manifest with runtime sensor_health_contract attestation; "
                         "the legacy importer must not invent the #68 contract")
    manifest = dict(schema=1, component="hhm", version=runtime + "+" + commit[:12],
                    object="05_31_Ivolga_13", role=role,
                    release=dict(repository="psv76/Neirolinks", commit=commit), files=entries,
                    services=dict(stop=["wb-rules"], start=["wb-rules"]),
                    preflight=["identity", "drift", "hhm"],
                    verify=dict(controls=[], runtime_version=runtime, health_contract="legacy-3.0"),
                    rollback="previous-managed-release")
    validate(manifest)
    data = (json.dumps(manifest, indent=2) + "\n").encode()
    output.mkdir(parents=True, exist_ok=True)
    (output / (role + ".json")).write_bytes(data)
    print(role + " manifest SHA256 " + hashlib.sha256(data).hexdigest())
    return manifest


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--commit", required=True)
    p.add_argument("--role", choices=("boiler", "gazebo"), required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    prepare(args.commit, args.role, args.output)
