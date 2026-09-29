#!/usr/bin/env python3
"""Build the deterministic NST controller registry from object-local profiles."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))

from nli.controller import SERIAL_RE, validate_profile
from nli.util import decode, require, safe_relative


def build_registry(repo_root=REPO):
    repo_root = Path(repo_root)
    controllers = {}
    active_assignments = {}
    for path in sorted(repo_root.glob("objects/*/controllers/*.json")):
        object_name = path.parents[1].name
        serial = path.stem.upper()
        require(SERIAL_RE.fullmatch(serial) is not None, "Invalid WB serial filename: " + path.as_posix())
        profile = validate_profile(decode(path.read_bytes()), serial)
        require(serial not in controllers, "Duplicate WB serial: " + serial)

        diagnostic_rel = safe_relative(profile["diagnostics_profile"])
        diagnostic = repo_root.joinpath(*diagnostic_rel.parts)
        require(diagnostic.is_file(), "Missing diagnostics profile reference: " + profile["diagnostics_profile"])
        diagnostic_data = decode(diagnostic.read_bytes())
        require(type(diagnostic_data) is dict and diagnostic_data.get("schema") == 1,
                "Invalid diagnostics profile: " + profile["diagnostics_profile"])

        profile_rel = path.relative_to(repo_root).as_posix()
        entry = {
            "object": object_name,
            "name": profile["name"],
            "node": profile["node"],
            "role": profile["role"],
            "state": profile["state"],
            "capabilities": profile["capabilities"],
            "diagnostics_profile": profile["diagnostics_profile"],
            "profile": profile_rel,
        }
        if "fingerprint_sha256" in profile:
            entry["fingerprint_sha256"] = profile["fingerprint_sha256"]

        if profile["state"] == "active":
            assignment = (object_name, profile["node"], profile["role"])
            require(assignment not in active_assignments,
                    "Conflicting active controller assignment: " + "/".join(assignment))
            active_assignments[assignment] = serial
        controllers[serial] = entry
    return {"schema": 1, "source": "objects/*/controllers/*.json", "controllers": controllers}


def encode_registry(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "generated/controller-registry.json")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    data = encode_registry(build_registry())
    if args.check:
        require(args.output.is_file() and args.output.read_bytes() == data,
                "Generated controller registry is stale; run build_controller_registry.py")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(data)
    print(str(args.output))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
