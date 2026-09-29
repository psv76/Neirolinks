#!/usr/bin/env python3
"""Resolve one controller profile into an exact deterministic NST deployment manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
sys.path.insert(0, str(ROOT))

from nli.controller import validate_profile
from nli.deployment import validate_deployment
from nli.manifest import validate as validate_component_manifest
from nli.releases import REPO, version
from nli.util import decode, digest, require, safe_relative

APPROVALS_PATH = "Systems/NST/deployment/approved-components.json"


def git_blob(repo_root, commit, path):
    safe_relative(path)
    return subprocess.check_output(["git", "-C", str(repo_root), "show", commit + ":" + path])


def _latest(entries):
    require(entries, "Missing approved compatible component")
    seen = set()
    for item in entries:
        require(item["version"] not in seen, "Duplicate approved component version: " + item["version"])
        seen.add(item["version"])
    ranked = sorted(((version(item["version"]), item) for item in entries), key=lambda x: x[0], reverse=True)
    return ranked[0][1]


def _validate_approval_entry(item):
    fields = {
        "component", "object", "role", "track", "version", "approved",
        "release_state", "draft", "prerelease", "minimum_nst", "approval", "manifest",
    }
    require(type(item) is dict and set(item) == fields, "Invalid approved component entry")
    for key in ("component", "object", "role"):
        require(isinstance(item[key], str) and item[key], "Invalid approved component " + key)
    require(item["track"] == "stable", "Invalid approved component track")
    version(item["version"])
    version(item["minimum_nst"])
    require(type(item["approved"]) is bool and type(item["draft"]) is bool and type(item["prerelease"]) is bool,
            "Invalid approved component flags")
    require(item["release_state"] in ("stable", "draft", "prerelease", "unapproved"),
            "Invalid approved component release state")
    approval = item["approval"]
    require(type(approval) is dict and set(approval) == {
        "kind", "tag", "published_at", "catalog_sha256", "release_commit"
    }, "Invalid approved component provenance")
    require(approval["kind"] == "github_release", "Invalid approved component provenance kind")
    require(isinstance(approval["tag"], str) and approval["tag"].startswith("nli-approved-"),
            "Invalid approved release tag")
    require(isinstance(approval["published_at"], str) and approval["published_at"], "Missing approval timestamp")
    require(len(approval["catalog_sha256"]) == 64, "Invalid approved catalog SHA256")
    require(len(approval["release_commit"]) == 40, "Invalid approved release commit")
    manifest = item["manifest"]
    require(type(manifest) is dict and set(manifest) == {"commit", "path", "sha256"},
            "Invalid approved manifest reference")
    require(len(manifest["commit"]) == 40 and len(manifest["sha256"]) == 64,
            "Invalid approved manifest identity")
    safe_relative(manifest["path"])
    return item


def resolve(serial, source_commit, profile_path, profile_raw, approvals_raw, read_blob):
    profile = validate_profile(decode(profile_raw), serial)
    require(profile["state"] == "active", "Deployment publication requires active controller")
    approvals = decode(approvals_raw)
    require(type(approvals) is dict and approvals.get("schema") == 1
            and approvals.get("repository") == REPO and type(approvals.get("components")) is list,
            "Invalid approved components snapshot")
    requested = profile.get("components", {})
    require(type(requested) is dict and requested, "Controller profile has no desired components")
    for item in approvals["components"]:
        _validate_approval_entry(item)

    resolved = []
    for component_name in sorted(requested):
        request = requested[component_name]
        require(type(request) is dict and set(request) == {"track"} and request["track"] == "stable",
                "Unsupported component request: " + component_name)
        candidates = []
        for item in approvals["components"]:
            require(type(item) is dict, "Invalid approved component entry")
            if (item.get("component"), item.get("object"), item.get("role"), item.get("track")) != (
                    component_name, profile_path.split("/")[1], profile["role"], "stable"):
                continue
            if item.get("approved") is not True or item.get("release_state") != "stable":
                continue
            if item.get("draft") is not False or item.get("prerelease") is not False:
                continue
            candidates.append(item)
        selected = _latest(candidates)
        version(selected["minimum_nst"])
        approval = selected["approval"]
        require(type(approval) is dict and approval.get("kind") == "github_release",
                "Component lacks stable GitHub approval")

        manifest_ref = selected["manifest"]
        raw = read_blob(manifest_ref["commit"], manifest_ref["path"])
        require(digest(raw) == manifest_ref["sha256"], "Approved component manifest checksum mismatch")
        manifest = validate_component_manifest(decode(raw))
        require((manifest["component"], manifest["version"], manifest["object"], manifest["role"]) ==
                (component_name, selected["version"], profile_path.split("/")[1], profile["role"]),
                "Approved component manifest identity mismatch")
        require(manifest["release"]["repository"] == REPO, "Foreign component payload repository")
        resolved.append({
            "component": component_name,
            "track": "stable",
            "version": selected["version"],
            "minimum_nst": selected["minimum_nst"],
            "approval": approval,
            "manifest": manifest_ref,
            "release": manifest["release"],
            "files": manifest["files"],
            "services": manifest["services"],
        })

    object_files = []
    for item in profile.get("object_files", []):
        require(type(item) is dict and set(item) == {"source", "target"}, "Invalid object file request")
        raw = read_blob(source_commit, item["source"])
        object_files.append({"source": item["source"], "target": item["target"], "sha256": digest(raw)})
    object_files.sort(key=lambda x: (x["target"], x["source"]))

    diagnostic_path = profile["diagnostics_profile"]
    diagnostic_raw = read_blob(source_commit, diagnostic_path)
    profile_sha = digest(profile_raw)

    minimum_nst = max((version(item["minimum_nst"]), item["minimum_nst"]) for item in resolved)[1]
    services = {
        action: sorted({service for component in resolved for service in component["services"][action]})
        for action in ("stop", "start")
    }
    deployment = {
        "schema": 1,
        "controller_serial": serial,
        "object": profile_path.split("/")[1],
        "node": profile["node"],
        "role": profile["role"],
        "state": profile["state"],
        "source": {"repository": REPO, "commit": source_commit},
        "profile": {"path": profile_path, "sha256": profile_sha},
        "minimum_nst": minimum_nst,
        "diagnostics_profile": {"path": diagnostic_path, "sha256": digest(diagnostic_raw)},
        "object_files": object_files,
        "components": resolved,
        "services": services,
        "signatures": [],
    }
    return validate_deployment(deployment)


def encode(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def build(repo_root, serial, source_commit):
    profile_path = "objects/05_31_Ivolga_13/controllers/" + serial + ".json"
    profile_raw = git_blob(repo_root, source_commit, profile_path)
    approvals_raw = git_blob(repo_root, source_commit, APPROVALS_PATH)
    return resolve(serial, source_commit, profile_path, profile_raw, approvals_raw,
                   lambda commit, path: git_blob(repo_root, commit, path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="ABF62SL")
    parser.add_argument("--source-commit")
    parser.add_argument("--output", type=Path, default=ROOT / "deployments/ABF62SL.json")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        require(args.output.is_file(), "Deployment output is missing")
        existing = decode(args.output.read_bytes())
        source_commit = existing["source"]["commit"]
    else:
        require(args.source_commit is not None, "--source-commit is required")
        source_commit = args.source_commit
    require(len(source_commit) == 40 and all(c in "0123456789abcdef" for c in source_commit),
            "Full immutable source commit required")
    data = encode(build(REPO_ROOT, args.serial, source_commit))
    if args.check:
        require(args.output.read_bytes() == data, "Deployment manifest is stale or non-deterministic")
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
