#!/usr/bin/env python3
"""Stage pinned, hash-verified Iset HHM Draft only. Never talks to WB."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "Systems/NST"))
from nst.manifest import validate
from nst.plugins import HHM, ISET_HOUSE
from nst.releases import software_version


def git(*args):
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *args], stderr=subprocess.PIPE)


def build(commit, output, physical=False):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Require full immutable Git commit SHA")
    if git("rev-parse", commit + "^{commit}").decode().strip() != commit:
        raise ValueError("Commit does not exist in local repository")
    map_path = "Objects/05_16_Iset/HHM/wb_install_map.json"
    spec = json.loads(git("show", commit + ":" + map_path))
    if spec.get("object") != "05_16_Iset" or spec.get("status") != "DRAFT_NEVER_DEPLOYED":
        raise ValueError("Only reviewed draft Iset installation map is accepted")
    source_targets = [(spec["main"]["source"], spec["main"]["target"])] + [
        (m["source"], m["target"]) for m in spec["modules"]
    ]
    targets = {t for _, t in source_targets}
    if len(source_targets) != 16 or targets != ISET_HOUSE:
        raise ValueError("Iset payload must contain EXACTLY 1 rule and 15 approved modules")
    if len(targets) != len(source_targets):
        raise ValueError("Duplicate physical target")
    file_entries, blobs = [], {}
    for source, target in sorted(source_targets, key=lambda item: item[1]):
        data = git("show", commit + ":" + source)
        blobs[source] = data
        file_entries.append({
            "source": source, "target": target,
            "sha256": hashlib.sha256(data).hexdigest()
        })
    main = blobs[spec["main"]["source"]].decode("utf-8")
    expected = "var HHM_PHYSICAL_OUTPUTS=" + ("true;" if physical else "false;")
    if expected not in main:
        raise ValueError("Wrong output mode: expected " + expected)
    for forbidden in ("HHMRoomMqttReadEvidence", "HHMRoomSensorEvidence",
                      "RoomSerialLoadEvidence"):
        if any(forbidden in m["source"] for m in file_entries):
            raise ValueError("Experimental sensor-attestation module in install set")
    manifest = dict(
        schema=1, component="hhm",
        version="0.1",
        object="05_16_Iset", role="house",
        release=dict(repository="psv76/Neirolinks", commit=commit),
        files=file_entries,
        services=dict(stop=["wb-rules"], start=["wb-rules"]),
        preflight=["identity", "drift", "hhm"],
        verify=dict(controls=[],
                    runtime_version="0.1",
                    health_contract="iset-local-v1"),
        rollback="previous-managed-release"
    )
    validate(manifest)
    software_version(manifest["version"])
    HHM().validate(manifest, {})
    # No file or controller changes until EVERY input has been validated.
    output.mkdir(parents=True, exist_ok=True)
    for source, data in blobs.items():
        dest = output / "payload" / source
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        if hashlib.sha256(dest.read_bytes()).hexdigest() != next(
                entry["sha256"] for entry in file_entries if entry["source"] == source):
            raise ValueError("Staged payload verification failed")
    encoded = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    filename = ("iset-hhm-house-0.1-PHYSICAL.json" if physical
                else "iset-hhm-house-0.1-DRAFT.json")
    (output / filename).write_bytes(encoded)
    (output / (filename + ".sha256")).write_text(
        hashlib.sha256(encoded).hexdigest() + "  " + filename + "\n",
        encoding="ascii"
    )
    print("PRODUCTION_CANDIDATE_NOT_APPROVED" if physical
          else "DRAFT_ONLY - NOT APPROVED; physical outputs disabled")
    print("STAGED", len(file_entries), "FILES")
    print("COMMIT", commit)
    print("MANIFEST_SHA256", hashlib.sha256(encoded).hexdigest())
    print("OUTPUT", output.resolve())
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--physical", action="store_true",
                        help="Require explicitly enabled physical output source")
    args = parser.parse_args()
    build(args.commit, args.output, physical=args.physical)
