"""NST #93 repository-side acceptance for the Ivolga ABF62SL pilot."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))

from nst.controller import ControllerRegistry


class IvolgaPilotTests(unittest.TestCase):
    def setUp(self):
        self.profile_path = REPO / "Objects/05_31_Ivolga_13/controllers/ABF62SL.json"
        self.profile = json.loads(self.profile_path.read_text(encoding="utf-8"))
        self.registry = json.loads((ROOT / "generated/controller-registry.json").read_text(encoding="utf-8"))

    def test_identity_and_diagnostics_profile_are_exact(self):
        self.assertEqual(self.profile["name"], "Котельная")
        self.assertEqual((self.profile["node"], self.profile["role"], self.profile["state"]),
                         ("boiler", "boiler", "active"))
        self.assertEqual(self.profile["diagnostics_profile"], "Systems/NST/diagnostics/ivolga-boiler-hhm-v1.json")
        resolved = ControllerRegistry(self.registry).resolve(
            {"serial": "ABF62SL", "serial_source": "test", "fingerprint": None})
        self.assertEqual(resolved["state"], "active")
        self.assertEqual(resolved["assignment"]["object"], "05_31_Ivolga_13")
        self.assertEqual(resolved["assignment"]["diagnostics_profile"],
                         "Systems/NST/diagnostics/ivolga-boiler-hhm-v1.json")

    def test_object_payload_has_no_common_component_or_legacy_writer_overlap(self):
        targets = {item["target"] for item in self.profile["object_files"]}
        self.assertEqual(targets, {
            "/etc/wb-rules-modules/system.js",
            "/etc/wb-rules/090_notification_service.js",
            "/etc/wb-rules/100_power_monitor.js",
            "/etc/wb-rules/610_Boiler_state.js",
        })
        forbidden = {
            "/etc/wb-rules/500_HHM3_FSE.js",
            "/etc/wb-rules/507_Pressure_makeup.js",
            "/etc/wb-rules/600_Heat_diagnostics.js",
            "/etc/wb-rules/620_thermostats.js",
            "/etc/wb-rules/501_tp_dom_manager.js",
            "/etc/wb-rules/502_gp_dom_manager.js",
            "/etc/wb-rules/503_rad_dom_manager.js",
            "/etc/wb-rules/HM2_arbiter_request.js",
            "/etc/wb-rules/HM2_source_manager.js",
            "/etc/wb-rules/upd-wbe2-i-opentherm.js",
        }
        self.assertFalse(targets & forbidden)
        for item in self.profile["object_files"]:
            self.assertTrue((REPO / item["source"]).is_file(), item["source"])

    def test_pressure_makeup_is_capability_but_not_falsely_approved_in_pilot_deployment(self):
        self.assertIn("pressure_makeup", self.profile["capabilities"])
        self.assertNotIn("pressure_makeup", self.profile["components"])
        approved = json.loads((ROOT / "deployment/approved-components.json").read_text(encoding="utf-8"))
        self.assertFalse(any(item["component"] == "pressure_makeup" for item in approved["components"]),
                         "Do not invent approval metadata; publish an approved release first")


if __name__ == "__main__":
    unittest.main()
