"""Iset draft release is content-addressed and intentionally non-actuating."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "Systems/NST"))
from nst.manifest import validate
from nst.plugins import HHM, ISET_HOUSE

BASE = "Objects/05_16_Iset/HHM"
MANIFEST = BASE + "/release_candidates/iset-hhm-house-0.1.0-rc1-DRAFT.json"


def git_blob(ref, name):
    return subprocess.check_output(
        ["git", "-C", str(ROOT), "show", ref + ":" + name])


class IsetDraftReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = git_blob("HEAD", MANIFEST)
        cls.data = json.loads(cls.raw)
        cls.commit = cls.data["release"]["commit"]

    def test_candidate_blob_matches_sha256_file(self):
        expected = git_blob("HEAD", MANIFEST + ".sha256").decode().split()[0]
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), expected)

    def test_draft_is_exactly_sixteen_approved_paths(self):
        validate(self.data)
        HHM().validate(self.data, {})
        self.assertEqual({f["target"] for f in self.data["files"]}, ISET_HOUSE)
        self.assertEqual(len(self.data["files"]), 16)

    def test_all_sources_are_pinned_to_immutable_git_commit(self):
        for entry in self.data["files"]:
            data = git_blob(self.commit, entry["source"])
            self.assertEqual(hashlib.sha256(data).hexdigest(),
                             entry["sha256"], entry["source"])

    def test_draft_does_not_energize_real_outputs(self):
        paths = {f["target"]: f["source"] for f in self.data["files"]}
        source = git_blob(self.commit,
                          paths["/etc/wb-rules/29_hhm_iset.js"]).decode()
        self.assertIn("var HHM_PHYSICAL_OUTPUTS=false;", source)

    def test_unmanaged_draft_matches_all_backup_inventory_sha(self):
        unmanaged = json.loads(git_blob(
            "HEAD", BASE + "/release_candidates/nst_unmanaged_rules_DRAFT.json"))
        inventory = json.loads(git_blob("HEAD", BASE + "/nst_preserve_inventory.json"))
        expected = {f["target"]: f["sha256"] for f in inventory["files"]}
        self.assertEqual(unmanaged["unmanaged_rules"], expected)
        self.assertEqual(len(expected), 16)


    def test_physical_candidate_pins_separate_immutable_writer(self):
        path = (BASE + "/release_candidates/"
                "iset-hhm-house-0.1.0-PHYSICAL.json")
        raw = git_blob("HEAD", path)
        want = git_blob("HEAD", path + ".sha256").decode().split()[0]
        self.assertEqual(hashlib.sha256(raw).hexdigest(), want)
        m = json.loads(raw)
        validate(m)
        HHM().validate(m, {})
        self.assertEqual(m["version"], "0.1.0")
        self.assertEqual(len(m["files"]), 16)
        source = {entry["target"]: entry["source"] for entry in m["files"]}
        main = git_blob(m["release"]["commit"],
                        source["/etc/wb-rules/29_hhm_iset.js"]).decode()
        self.assertIn("var HHM_PHYSICAL_OUTPUTS=true;", main)
        self.assertNotIn("var HHM_PHYSICAL_OUTPUTS=false;", main)

    def test_new_canonical_x_y_candidate_is_immutable_and_compatible_with_nst(self):
        from nst.releases import software_version
        path = BASE + "/release_candidates/iset-hhm-house-0.1-PHYSICAL.json"
        raw = git_blob("HEAD", path)
        pinned = git_blob("HEAD", path + ".sha256").decode().split()[0]
        self.assertEqual(hashlib.sha256(raw).hexdigest(), pinned)
        manifest = json.loads(raw)
        validate(manifest)
        HHM().validate(manifest, {})
        self.assertEqual(manifest["version"], "0.1")
        self.assertEqual(manifest["verify"]["runtime_version"], "0.1")
        self.assertEqual(software_version(manifest["version"]), (0, 1, 0))
        self.assertEqual({f["target"] for f in manifest["files"]}, ISET_HOUSE)
        for entry in manifest["files"]:
            source = git_blob(manifest["release"]["commit"], entry["source"])
            self.assertEqual(hashlib.sha256(source).hexdigest(), entry["sha256"])
        main_source = next(f["source"] for f in manifest["files"]
                           if f["target"] == "/etc/wb-rules/29_hhm_iset.js")
        main = git_blob(manifest["release"]["commit"], main_source).decode()
        self.assertIn("var HHM_PHYSICAL_OUTPUTS=true;", main)
        self.assertIn("io_unconfirmed", main)
        self.assertIn("CIRCULATING", git_blob(
            manifest["release"]["commit"],
            "Objects/05_16_Iset/HHM/isethhm_floor_hydraulics.js").decode())

    def test_physical_and_historical_preview_are_both_content_pinned(self):
        physical = json.loads(git_blob(
            "HEAD", BASE + "/release_candidates/iset-hhm-house-0.1.0-PHYSICAL.json"))
        preview = self.data
        one = {x["target"]: x["sha256"] for x in physical["files"]}
        two = {x["target"]: x["sha256"] for x in preview["files"]}
        self.assertEqual(set(one), set(two))
        self.assertEqual(len(one), 16)
        # The historical preview was built before the observed K3 hysteresis
        # correction and editable WB setpoint fix. It is not the proposed
        # physical release, so do not accidentally claim module identity.
        changed = {target for target in one if one[target] != two[target]}
        self.assertEqual(changed, {
            "/etc/wb-rules/29_hhm_iset.js",
            "/etc/wb-rules-modules/IsetDemand.js",
        })

    def test_post_cutover_unmanaged_rules_keep_only_independent_functions(self):
        post = json.loads(git_blob(
            "HEAD", BASE + "/release_candidates/nst_unmanaged_POST_CUTOVER_DRAFT.json"))
        targets = set(post["unmanaged_rules"])
        self.assertEqual(len(targets), 9)
        self.assertIn("/etc/wb-rules/Light_4.js", targets)
        self.assertIn("/etc/wb-rules/AHU_preheat_pump_manager.js", targets)
        self.assertIn("/etc/wb-rules/DHW_recirculation_manager.js", targets)
        self.assertIn("/etc/wb-rules-modules/WBHelpers.js", targets)
        self.assertFalse(any("Heating_" in x or "/2" in x for x in targets))


    def test_iset_diagnostic_profile_matches_hhm_sources_and_actual_channels(self):
        diagnostic = json.loads(git_blob(
            "HEAD", "Systems/NST/diagnostics/iset-house-hhm-v1.json"))
        self.assertEqual(diagnostic["schema"], 1)
        self.assertEqual(diagnostic["component"], "hhm")
        self.assertEqual(set(diagnostic["source_files"]), ISET_HOUSE)
        self.assertEqual(len(diagnostic["source_files"]), 16)
        channels = {x["path"]: x["kind"]
                    for x in diagnostic["current_controls"]}
        self.assertEqual(len(channels), len(diagnostic["current_controls"]))
        self.assertEqual(channels["wb-mr6cu_37/K2"], "readback")
        self.assertEqual(channels["wb-m1w2_67/External Sensor 1"],
                         "measurement")
        self.assertEqual(channels["iset_hhm/io_unconfirmed"], "calculated")
        self.assertTrue(set(diagnostic["history_channels"]) <= set(channels))


    def test_real_iset_planned_profile_pins_live_unmanaged_rules(self):
        profile = json.loads(git_blob(
            "HEAD", "Objects/05_16_Iset/controllers/AFMEUYOT.json"))
        registry = json.loads(git_blob(
            "HEAD", "Systems/NST/generated/controller-registry.json"))
        from nst.controller import validate_profile, ControllerRegistry
        validate_profile(profile, "AFMEUYOT")
        self.assertEqual(profile["state"], "planned")
        self.assertEqual(profile["role"], "house")
        self.assertEqual(profile["components"], {"hhm": {"track": "stable"}})
        self.assertEqual(profile["diagnostics_profile"],
                         "Systems/NST/diagnostics/iset-house-hhm-v1.json")
        expected = json.loads(git_blob(
            "HEAD", BASE + "/release_candidates/nst_unmanaged_POST_CUTOVER_DRAFT.json"))
        self.assertEqual(profile["unmanaged_rules"], expected["unmanaged_rules"])
        self.assertEqual(len(profile["unmanaged_rules"]), 9)
        identity = dict(serial="AFMEUYOT", fingerprint=None)
        context = ControllerRegistry(registry).resolve(identity)
        self.assertFalse(context["mutation_allowed"])
        self.assertEqual(context["state"], "planned")
        self.assertEqual(context["assignment"]["object"], "05_16_Iset")

    def test_deployment_inventory_refuses_unmanaged_collision_with_hhm(self):
        from nst.deployment import validate_deployment
        from nst.util import Error
        import test_deployment
        fixture = test_deployment.DeploymentTests()
        fixture.setUp()
        deployment = fixture.build()
        target = deployment["components"][0]["files"][0]["target"]
        deployment["unmanaged_rules"] = {target: "a" * 64}
        with self.assertRaisesRegex(Error, "ownership conflict"):
            validate_deployment(deployment)

if __name__ == "__main__":
    unittest.main()
