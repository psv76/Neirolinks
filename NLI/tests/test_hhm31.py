"""Offline release/attestation verification against the accepted NLI 0.1.6 policy."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "NLI"))
from nli.manifest import validate
from nli.plugins import HHM
from nli.util import Error
from tools.prepare_hhm31 import prepare
from test_nli import FakeSystem


class HHM31Release(unittest.TestCase):
    def manifests(self):
        for role in ("boiler", "gazebo"):
            path = ROOT / "NLI/releases" / ("hhm-" + role + "-3.1.json")
            yield path, json.loads(path.read_bytes())

    def test_pinned_payload_matches_current_runtime_and_hashes(self):
        for path, manifest in self.manifests():
            validate(manifest)
            HHM().validate(manifest, {})
            expected = path.with_suffix(".json.sha256").read_text().split()[0]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)
            for item in manifest["files"]:
                data = subprocess.check_output(["git", "-C", str(ROOT), "show",
                                                manifest["release"]["commit"] + ":" + item["source"]])
                self.assertEqual(hashlib.sha256(data).hexdigest(), item["sha256"])
                self.assertEqual(data, (ROOT / item["source"]).read_bytes(), item["source"])
                self.assertNotIn("507", item["target"])

    def test_builder_is_reproducible_and_rejects_legacy(self):
        with tempfile.TemporaryDirectory() as temp:
            for path, manifest in self.manifests():
                output = Path(temp) / manifest["role"]
                result = prepare(manifest["release"]["commit"], manifest["role"], output)
                self.assertEqual(result, manifest)
                self.assertEqual((output / path.name).read_bytes(), path.read_bytes())
            output = Path(temp) / "legacy"
            with self.assertRaisesRegex(ValueError, "requires reviewed"):
                prepare("d75710dad93906af8869dcce48d26e14673b63fb", "boiler", output)
            self.assertFalse(output.exists())

    def test_both_roles_require_runtime_attestation_and_reject_wrong_or_missing(self):
        for _, manifest in self.manifests():
            system = FakeSystem()
            if manifest["role"] == "gazebo":
                system.frame.update(source="ivolga-besedka-504", v=2)
            control = manifest["verify"]["controls"][0]["path"]
            for value in ("", "legacy-3.0", "m1w2-health-v1"):
                system.controls[control] = value
                if value == "m1w2-health-v1":
                    HHM().runtime(SimpleNamespace(system=system), manifest)
                else:
                    with self.assertRaises(Error):
                        HHM().runtime(SimpleNamespace(system=system), manifest)
            for health in ("none", "legacy-3.0"):
                broken = copy.deepcopy(manifest)
                broken["verify"]["health_contract"] = health
                with self.assertRaises(Error):
                    HHM().validate(broken, {})


if __name__ == "__main__":
    unittest.main()
