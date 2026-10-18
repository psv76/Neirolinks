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


if __name__ == "__main__":
    unittest.main()
