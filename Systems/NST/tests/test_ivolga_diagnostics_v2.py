"""Contract: Ivolga HHM diagnostics must cover all configured heating circuits.

This is an engineering profile test, not proof of live MQTT retention.
"""
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class IvolgaEvidenceProfileV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original=json.loads((ROOT / "diagnostics/ivolga-boiler-hhm-v1.json").read_text(encoding="utf-8"))
        cls.updated=json.loads((ROOT / "diagnostics/ivolga-boiler-hhm-v2.json").read_text(encoding="utf-8"))

    def test_preserves_all_existing_502_evidence(self):
        for key in ("history_channels", "source_files", "config_files", "journals"):
            self.assertTrue(set(self.original[key]).issubset(set(self.updated[key])),key)
        old_controls={(item["path"],item["kind"]) for item in self.original["current_controls"]}
        new_controls={(item["path"],item["kind"]) for item in self.updated["current_controls"]}
        self.assertTrue(old_controls.issubset(new_controls))

    def test_501_pump_mixer_temperatures_and_demand(self):
        required={
            "A03/K1", "A05/Channel 1 Dimming Level", "A05/Channel 1 Switch",
            "wb-m1w2_141/External Sensor 1", "wb-m1w2_141/External Sensor 2",
            "wb-m1w2_170/External Sensor 1", "HHM3_FSE/diag_request_501",
        }
        self.assertTrue(required.issubset(set(self.updated["history_channels"])))
        self.assertTrue(required.issubset({x["path"] for x in self.updated["current_controls"]}))

    def test_other_circuits_and_unique_channels(self):
        channels=self.updated["history_channels"]
        self.assertEqual(len(channels),len(set(channels)))
        for circuit in range(501,506):
            self.assertIn(f"HHM3_FSE/diag_request_{circuit}",channels)
            self.assertIn(f"HHM3_FSE/circuit_{circuit}",channels)
            self.assertIn(f"A03/K{circuit-500}",channels)
        self.assertEqual(self.updated["component"],"hhm")
        self.assertEqual(self.updated["max_history_records"],self.original["max_history_records"])


if __name__=="__main__":unittest.main()
