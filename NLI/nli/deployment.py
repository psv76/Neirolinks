"""NST approved deployment manifest: strict validation and offline byte verification."""
import re
from .manifest import validate as validate_component_manifest
from .releases import REPO, version
from .util import digest, require, safe_relative

SERIAL_RE = re.compile(r"^[A-Z0-9]{5,32}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def _sha(value, label):
    require(isinstance(value, str) and SHA_RE.fullmatch(value) is not None, "Invalid " + label)


def _commit(value, label):
    require(isinstance(value, str) and COMMIT_RE.fullmatch(value) is not None, "Invalid " + label)


def _file_entry(item, object_file=False):
    require(type(item) is dict, "Invalid deployment file entry")
    required = {"source", "target", "sha256"}
    require(set(item) == required, "Invalid deployment file fields")
    require(isinstance(item["source"], str), "Invalid deployment source")
    safe_relative(item["source"])
    require(isinstance(item["target"], str) and item["target"].startswith("/"), "Invalid deployment target")
    _sha(item["sha256"], "deployment file SHA256")
    return item


def validate_deployment(data):
    require(type(data) is dict, "Deployment manifest must be an object")
    required = {
        "schema", "controller_serial", "object", "node", "role", "state",
        "source", "profile", "minimum_nst", "diagnostics_profile",
        "object_files", "components", "services", "signatures",
    }
    require(set(data) == required, "Invalid deployment manifest fields")
    require(data["schema"] == 1, "Invalid deployment schema")
    require(isinstance(data["controller_serial"], str)
            and SERIAL_RE.fullmatch(data["controller_serial"]) is not None,
            "Invalid deployment controller serial")
    for key in ("object", "node", "role"):
        require(isinstance(data[key], str) and bool(data[key]), "Invalid deployment " + key)
    require(data["state"] == "active", "Only active controller may have production deployment")
    version(data["minimum_nst"])

    source = data["source"]
    require(type(source) is dict and set(source) == {"repository", "commit"}, "Invalid deployment source")
    require(source["repository"] == REPO, "Foreign deployment repository")
    _commit(source["commit"], "deployment source commit")

    for key in ("profile", "diagnostics_profile"):
        ref = data[key]
        require(type(ref) is dict and set(ref) == {"path", "sha256"}, "Invalid " + key + " reference")
        safe_relative(ref["path"])
        _sha(ref["sha256"], key + " SHA256")

    require(type(data["object_files"]) is list, "Invalid object files")
    for item in data["object_files"]:
        _file_entry(item, True)

    require(type(data["components"]) is list and data["components"], "Deployment requires components")
    seen_components = set()
    targets = {}
    for item in data["object_files"]:
        require(item["target"] not in targets, "Duplicate deployment target: " + item["target"])
        targets[item["target"]] = "object"
    for component in data["components"]:
        require(type(component) is dict, "Invalid deployment component")
        fields = {
            "component", "track", "version", "minimum_nst", "approval",
            "manifest", "release", "files", "services",
        }
        require(set(component) == fields, "Invalid deployment component fields")
        name = component["component"]
        require(isinstance(name, str) and name and name not in seen_components, "Duplicate/invalid deployment component")
        seen_components.add(name)
        require(component["track"] == "stable", "Unsupported deployment track")
        version(component["version"])
        version(component["minimum_nst"])

        approval = component["approval"]
        require(type(approval) is dict and set(approval) == {
            "kind", "tag", "published_at", "catalog_sha256", "release_commit"
        }, "Invalid component approval")
        require(approval["kind"] == "github_release"
                and isinstance(approval["tag"], str) and approval["tag"].startswith("nli-approved-"),
                "Invalid component approval source")
        require(isinstance(approval["published_at"], str) and approval["published_at"], "Missing approval timestamp")
        _sha(approval["catalog_sha256"], "approved catalog SHA256")
        _commit(approval["release_commit"], "approved release commit")

        manifest = component["manifest"]
        require(type(manifest) is dict and set(manifest) == {"commit", "path", "sha256"},
                "Invalid component manifest reference")
        _commit(manifest["commit"], "component manifest commit")
        safe_relative(manifest["path"])
        _sha(manifest["sha256"], "component manifest SHA256")

        release = component["release"]
        require(type(release) is dict and set(release) == {"repository", "commit"}, "Invalid component release")
        require(release["repository"] == REPO, "Foreign component release")
        _commit(release["commit"], "component payload commit")

        require(type(component["files"]) is list and component["files"], "Component has no payload files")
        for file_item in component["files"]:
            _file_entry(file_item)
            require(file_item["target"] not in targets, "Duplicate deployment target: " + file_item["target"])
            targets[file_item["target"]] = name

        services = component["services"]
        require(type(services) is dict and set(services) == {"stop", "start"}, "Invalid component services")
        for action in ("stop", "start"):
            require(type(services[action]) is list and len(services[action]) == len(set(services[action])),
                    "Invalid component service list")

    services = data["services"]
    require(type(services) is dict and set(services) == {"stop", "start"}, "Invalid deployment services")
    for action in ("stop", "start"):
        require(type(services[action]) is list and services[action] == sorted(set(services[action])),
                "Deployment services must be sorted/unique")

    require(type(data["signatures"]) is list, "Invalid signatures field")
    for signature in data["signatures"]:
        require(type(signature) is dict, "Invalid signature record")
        require({"key_id", "algorithm", "value"}.issubset(signature), "Incomplete signature record")
    return data


def verify_offline(data, read_blob):
    """Verify deployment only from local bytes supplied by (commit, path) -> bytes."""
    validate_deployment(data)
    source_commit = data["source"]["commit"]

    for key in ("profile", "diagnostics_profile"):
        ref = data[key]
        require(digest(read_blob(source_commit, ref["path"])) == ref["sha256"],
                key + " checksum mismatch")

    for item in data["object_files"]:
        require(digest(read_blob(source_commit, item["source"])) == item["sha256"],
                "Object payload checksum mismatch: " + item["source"])

    for component in data["components"]:
        ref = component["manifest"]
        raw = read_blob(ref["commit"], ref["path"])
        require(digest(raw) == ref["sha256"], "Component manifest checksum mismatch: " + component["component"])
        manifest = validate_component_manifest(__import__("json").loads(raw))
        require((manifest["component"], manifest["version"], manifest["object"], manifest["role"]) ==
                (component["component"], component["version"], data["object"], data["role"]),
                "Component manifest identity mismatch")
        require(manifest["release"] == component["release"], "Component release identity mismatch")
        require(manifest["files"] == component["files"], "Component file set mismatch")
        require(manifest["services"] == component["services"], "Component services mismatch")
        for item in component["files"]:
            require(digest(read_blob(component["release"]["commit"], item["source"])) == item["sha256"],
                    "Component payload checksum mismatch: " + item["source"])
    return True
