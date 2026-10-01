"""NST #89 desired-state operator workflow."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_core as fixtures
from nst.controller import ControllerRegistry
from nst.desired import DesiredState
from nst.platform import default_platform_state, save_platform_state
from nst.releases import RAW, TransportError
from nst.util import digest


def registry(state="active"):
    return {
        "schema": 1,
        "source": {"kind": "test"},
        "controllers": {
            "ABCDE": {
                "object": "test",
                "name": "Test controller",
                "node": "boiler",
                "role": "boiler",
                "state": state,
                "capabilities": ["demo"],
                "diagnostics_profile": "NLI/diagnostics/controller-default-v1.json",
                "profile": "objects/test/controllers/ABCDE.json",
            }
        },
    }


class Source:
    def __init__(self, deployment, manifest, unavailable=False):
        self.deployment = deployment
        self.manifest = manifest
        self.unavailable = unavailable

    def latest(self, serial):
        if self.unavailable:
            raise TransportError("offline")
        assert serial == "ABCDE"
        return {
            "tag": "nst-approved-platform-test",
            "published_at": "2026-09-29T00:00:00Z",
            "registry": registry(),
            "registry_sha256": "1" * 64,
            "deployment": self.deployment,
            "deployment_sha256": digest((json.dumps(self.deployment, sort_keys=True) + "\n").encode()),
        }

    def component_manifest(self, desired):
        raw = json.dumps(self.manifest).encode()
        assert digest(raw) == desired["manifest"]["sha256"]
        return raw, self.manifest


class PayloadReleases:
    def __init__(self, payload):
        self.payload = payload

    def fetch(self, url, *args):
        if url.startswith(RAW):
            return self.payload
        raise AssertionError(url)


class DesiredStateTests(fixtures.Fixture):
    def setUp(self):
        super().setUp()
        identity = {"serial": "ABCDE", "serial_source": "/var/lib/wirenboard/short_sn", "fingerprint": None}
        self.engine.controller = ControllerRegistry(registry()).resolve(identity)
        self.engine.releases = PayloadReleases(b"new")

    def deployment(self, manifest):
        raw = json.dumps(manifest).encode()
        return {
            "schema": 1,
            "controller_serial": "ABCDE",
            "object": "test",
            "node": "boiler",
            "role": "boiler",
            "state": "active",
            "source": {"repository": "psv76/Neirolinks", "commit": "b" * 40},
            "profile": {"path": "objects/test/controllers/ABCDE.json", "sha256": "2" * 64},
            "minimum_nst": "1.0.0",
            "diagnostics_profile": {"path": "NLI/diagnostics/controller-default-v1.json", "sha256": "3" * 64},
            "object_files": [],
            "components": [{
                "component": "demo",
                "track": "stable",
                "version": manifest["version"],
                "minimum_nst": "1.0.0",
                "approval": {
                    "kind": "github_release",
                    "tag": "nli-approved-demo",
                    "published_at": "2026-09-29T00:00:00Z",
                    "catalog_sha256": "4" * 64,
                    "release_commit": "c" * 40,
                },
                "manifest": {"commit": "d" * 40, "path": "NLI/releases/demo.json", "sha256": digest(raw)},
                "release": manifest["release"],
                "files": manifest["files"],
                "services": manifest["services"],
            }],
            "services": {"stop": [], "start": []},
            "signatures": [],
        }

    def test_status_is_offline_and_read_only_with_local_deployment_drift(self):
        deployment = self.deployment(self.new)
        platform = default_platform_state()
        platform["deployment"] = {"manifest": deployment, "sha256": "5" * 64}
        save_platform_state(self.engine, platform)
        before = self.snapshot()
        result = DesiredState(self.engine, Source(deployment, self.new, unavailable=True)).status()
        self.assertEqual(result["deployment_state"]["status"], "changes_required")
        self.assertEqual(before, self.snapshot())

    def test_check_offline_is_unavailable_and_read_only(self):
        deployment = self.deployment(self.new)
        before = self.snapshot()
        result = DesiredState(self.engine, Source(deployment, self.new, unavailable=True)).check()
        self.assertEqual(result["final_status"], "unavailable")
        self.assertEqual(before, self.snapshot())

    def test_check_exact_is_noop_without_payload_fetch_or_writes(self):
        deployment = self.deployment(self.base)
        before = self.snapshot()
        result = DesiredState(self.engine, Source(deployment, self.base)).check()
        self.assertEqual(result["final_status"], "ok")
        self.assertFalse(result["mutation_required"])
        self.assertEqual(result["plan"]["status"], "exact")
        self.assertEqual(before, self.snapshot())

    def test_check_reports_drift_and_exact_change_plan(self):
        deployment = self.deployment(self.new)
        result = DesiredState(self.engine, Source(deployment, self.new)).check()
        self.assertTrue(result["mutation_required"])
        self.assertEqual(result["plan"]["components"][0]["action"], "sync")
        self.assertEqual(result["plan"]["components"][0]["changed_files"],
                         [self.new["files"][0]["target"]])

    def test_planned_controller_cannot_check_or_sync_production_desired_state(self):
        identity = {"serial": "ABCDE", "serial_source": "test", "fingerprint": None}
        self.engine.controller = ControllerRegistry(registry("planned")).resolve(identity)
        deployment = self.deployment(self.new)
        desired = DesiredState(self.engine, Source(deployment, self.new))
        before = self.snapshot()
        self.assertEqual(desired.check()["final_status"], "failed")
        self.assertEqual(desired.sync()["final_status"], "failed")
        self.assertEqual(before, self.snapshot())

    def test_sync_uses_existing_transaction_engine_and_records_exact_deployment(self):
        deployment = self.deployment(self.new)
        result = DesiredState(self.engine, Source(deployment, self.new)).sync()
        self.assertEqual(result["final_status"], "ok", result)
        self.assertEqual(self.engine.target(self.new["files"][0]["target"]).read_bytes(), b"new")
        self.assertEqual(result["deployment_state"]["status"], "exact")
        status = DesiredState(self.engine, Source(deployment, self.new, unavailable=True)).status()
        self.assertEqual(status["platform"]["deployment"]["manifest"], deployment)
        self.assertEqual(status["deployment_state"]["status"], "exact")
        self.assertFalse(self.engine.pending())


if __name__ == "__main__":
    unittest.main()
