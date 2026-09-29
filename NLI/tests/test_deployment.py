"""NST #87 deployment resolution and offline verification."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from build_deployment import encode, resolve
from nli.deployment import validate_deployment, verify_offline
from nli.util import Error


def sha(data):
    return hashlib.sha256(data).hexdigest()


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.source = "1" * 40
        self.manifest_commit = "2" * 40
        self.payload_commit = "3" * 40
        self.profile_path = "objects/test_object/controllers/ABCDE12.json"
        self.profile = {
            "schema": 1,
            "name": "Test",
            "node": "boiler",
            "role": "boiler",
            "state": "active",
            "capabilities": ["demo"],
            "components": {"demo": {"track": "stable"}},
            "object_files": [{"source": "objects/test_object/object.js", "target": "/etc/wb-rules/object.js"}],
            "diagnostics_profile": "NLI/diagnostics/controller-default-v1.json",
        }
        self.profile_raw = (json.dumps(self.profile, sort_keys=True) + "\n").encode()
        self.component_manifest = {
            "schema": 1,
            "component": "demo",
            "version": "1.1",
            "object": "test_object",
            "role": "boiler",
            "release": {"repository": "psv76/Neirolinks", "commit": self.payload_commit},
            "files": [{
                "source": "components/demo.js",
                "target": "/etc/wb-rules/demo.js",
                "sha256": sha(b"demo payload"),
            }],
            "services": {"stop": ["wb-rules"], "start": ["wb-rules"]},
            "preflight": ["identity", "drift"],
            "verify": {"controls": [], "runtime_version": "1.1", "health_contract": "none"},
            "rollback": "previous-managed-release",
        }
        self.manifest_raw = (json.dumps(self.component_manifest, sort_keys=True) + "\n").encode()
        self.approvals = {
            "schema": 1,
            "repository": "psv76/Neirolinks",
            "components": [
                self.approval("1.0", "4" * 40, "0" * 64),
                self.approval("1.1", self.manifest_commit, sha(self.manifest_raw)),
                dict(self.approval("1.2", "5" * 40, "f" * 64), release_state="draft", draft=True),
            ],
        }
        self.approvals_raw = (json.dumps(self.approvals, sort_keys=True) + "\n").encode()
        self.blobs = {
            (self.source, self.profile_path): self.profile_raw,
            (self.source, "NLI/diagnostics/controller-default-v1.json"): b'{"schema":1}\n',
            (self.source, "objects/test_object/object.js"): b"object payload",
            (self.manifest_commit, "NLI/releases/demo-1.1.json"): self.manifest_raw,
            (self.payload_commit, "components/demo.js"): b"demo payload",
        }

    def approval(self, version, manifest_commit, manifest_sha):
        return {
            "component": "demo",
            "object": "test_object",
            "role": "boiler",
            "track": "stable",
            "version": version,
            "approved": True,
            "release_state": "stable",
            "draft": False,
            "prerelease": False,
            "minimum_nst": "1.0.0",
            "approval": {
                "kind": "github_release",
                "tag": "nli-approved-demo-" + version,
                "published_at": "2026-09-29T00:00:00Z",
                "catalog_sha256": "a" * 64,
                "release_commit": manifest_commit,
            },
            "manifest": {
                "commit": manifest_commit,
                "path": "NLI/releases/demo-" + version + ".json",
                "sha256": manifest_sha,
            },
        }

    def read(self, commit, path):
        return self.blobs[(commit, path)]

    def build(self, approvals=None):
        raw = self.approvals_raw if approvals is None else (json.dumps(approvals, sort_keys=True) + "\n").encode()
        return resolve("ABCDE12", self.source, self.profile_path, self.profile_raw, raw, self.read)

    def test_stable_resolves_latest_and_ignores_draft(self):
        deployment = self.build()
        self.assertEqual(deployment["components"][0]["version"], "1.1")
        self.assertEqual(deployment["components"][0]["manifest"]["commit"], self.manifest_commit)
        self.assertEqual(deployment["source"]["commit"], self.source)
        self.assertEqual(deployment["services"], {"stop": ["wb-rules"], "start": ["wb-rules"]})

    def test_missing_approved_component_blocks_publication(self):
        approvals = copy.deepcopy(self.approvals)
        for item in approvals["components"]:
            item["approved"] = False
        with self.assertRaisesRegex(Error, "Missing approved compatible component"):
            self.build(approvals)

    def test_only_draft_component_blocks_publication(self):
        approvals = copy.deepcopy(self.approvals)
        approvals["components"] = [dict(self.approval("1.2", "5" * 40, "f" * 64),
                                         release_state="draft", draft=True)]
        with self.assertRaisesRegex(Error, "Missing approved compatible component"):
            self.build(approvals)

    def test_conflicting_duplicate_latest_blocks_publication(self):
        approvals = copy.deepcopy(self.approvals)
        duplicate = copy.deepcopy(approvals["components"][1])
        duplicate["approval"]["tag"] = "nli-approved-demo-1.1-other"
        approvals["components"].append(duplicate)
        with self.assertRaisesRegex(Error, "Duplicate approved component version"):
            self.build(approvals)

    def test_malformed_approval_entry_blocks_publication(self):
        approvals = copy.deepcopy(self.approvals)
        del approvals["components"][0]["manifest"]["sha256"]
        with self.assertRaisesRegex(Error, "Invalid approved manifest reference"):
            self.build(approvals)

    def test_manifest_checksum_mismatch_blocks_publication(self):
        approvals = copy.deepcopy(self.approvals)
        approvals["components"][1]["manifest"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(Error, "manifest checksum mismatch"):
            self.build(approvals)

    def test_exact_object_file_sha_is_resolved(self):
        deployment = self.build()
        self.assertEqual(deployment["object_files"][0]["sha256"], sha(b"object payload"))

    def test_offline_verification_uses_only_exact_local_bytes(self):
        deployment = self.build()
        self.assertTrue(verify_offline(deployment, self.read))
        changed = dict(self.blobs)
        changed[(self.payload_commit, "components/demo.js")] = b"changed"
        with self.assertRaisesRegex(Error, "payload checksum mismatch"):
            verify_offline(deployment, lambda commit, path: changed[(commit, path)])

    def test_output_is_deterministic(self):
        self.assertEqual(encode(self.build()), encode(self.build()))

    def test_signatures_field_is_forward_compatible(self):
        deployment = self.build()
        deployment["signatures"] = [{
            "key_id": "future-neirolinks-key",
            "algorithm": "future",
            "value": "placeholder",
        }]
        self.assertIs(validate_deployment(deployment), deployment)


if __name__ == "__main__":
    unittest.main()
