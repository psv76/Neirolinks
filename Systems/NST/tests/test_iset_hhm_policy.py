"""NST HHM Iset package policy regression. Fake manifest, no controller."""
import json
import sys
import unittest
from pathlib import Path

NST = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(NST))
from nst.plugins import HHM, ISET_HOUSE, BOILER, GAZEBO
from nst.manifest import validate
from nst.util import Error


def manifest(object_name, role, targets):
    return {
        "schema": 1,
        "component": "hhm",
        "version": "0.1",
        "object": object_name,
        "role": role,
        "release": {"commit": "a" * 40, "repository": "psv76/Neirolinks"},
        "files": [
            {"source": "Objects/test/" + str(i) + ".js",
             "target": target, "sha256": "b" * 64}
            for i, target in enumerate(sorted(targets))
        ],
        "services": {"stop": ["wb-rules"], "start": ["wb-rules"]},
        "preflight": ["identity", "drift", "hhm"],
        "verify": {"controls": [], "runtime_version": "0.1",
                   "health_contract": "none"},
        "rollback": "previous-managed-release",
    }


class IsetHHMPolicyTests(unittest.TestCase):
    def test_iset_map_exactly_matches_plugin_targets(self):
        repo_root = NST.parent.parent
        src = json.loads((repo_root / "Objects/05_16_Iset/HHM"
                           / "wb_install_map.json").read_text(encoding="utf-8"))
        targets = {src["main"]["target"]} | {m["target"] for m in src["modules"]}
        self.assertEqual(targets, ISET_HOUSE)
        self.assertEqual(len(targets), 16)

    def test_iset_complete_house_package_accepted(self):
        m = validate(manifest("05_16_Iset", "house", ISET_HOUSE))
        HHM().validate(m, {})

    def test_iset_wrong_role_rejected(self):
        with self.assertRaises(Error):
            HHM().validate(manifest("05_16_Iset", "boiler", ISET_HOUSE), {})

    def test_iset_one_missing_module_rejected(self):
        incomplete = set(ISET_HOUSE)
        incomplete.remove("/etc/wb-rules-modules/IsetSource.js")
        with self.assertRaises(Error):
            HHM().validate(manifest("05_16_Iset", "house", incomplete), {})

    def test_iset_unrelated_rule_not_owned_by_hhm(self):
        extra = set(ISET_HOUSE) | {"/etc/wb-rules/Light_4.js"}
        with self.assertRaises(Error):
            HHM().validate(manifest("05_16_Iset", "house", extra), {})

    def test_iset_old_shadow_rule_not_owned_by_hhm(self):
        extra = set(ISET_HOUSE) | {"/etc/wb-rules/28_hhm_rooms_shadow.js"}
        with self.assertRaises(Error):
            HHM().validate(manifest("05_16_Iset", "house", extra), {})

    def test_unknown_house_object_rejected(self):
        with self.assertRaises(Error):
            HHM().validate(manifest("05_17_Somewhere", "house", ISET_HOUSE), {})

    def test_ivolga_boiler_unchanged(self):
        HHM().validate(manifest("05_31_Ivolga_13", "boiler", BOILER), {})

    def test_ivolga_gazebo_unchanged(self):
        HHM().validate(manifest("05_31_Ivolga_13", "gazebo", GAZEBO), {})

    def test_ivolga_wrong_house_role_still_rejected(self):
        with self.assertRaises(Error):
            HHM().validate(manifest("05_31_Ivolga_13", "house", ISET_HOUSE), {})


if __name__ == "__main__":
    unittest.main()
