"""NST #90 diagnostic bundle safety and completeness."""
import io
import json
from pathlib import Path
import sys
import tarfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_nli as fixtures
from nli.diagnostics import Diagnostics, parse_since, validate_profile
from nli.util import Error, digest


def profile():
    return {
        "schema": 1,
        "name": "test diagnostics",
        "component": "demo",
        "semantics": {
            "command": "command is not physical result",
            "readback": "readback is not physical result",
            "physical_result": "requires independent measurement",
        },
        "journals": ["wb-rules", "wb-mqtt-db"],
        "current_controls": [
            {"path": "demo/command", "kind": "command"},
            {"path": "demo/readback", "kind": "readback"},
        ],
        "history_channels": ["demo/command", "demo/readback"],
        "config_files": ["/etc/wb-mqtt-db.conf"],
        "source_files": [],
        "max_history_records": 1000,
    }


class DiagnosticSystem(fixtures.FakeSystem):
    def __init__(self):
        super().__init__()
        self.read_calls = []

    def control(self, path, timeout=None):
        self.read_calls.append(("control", path, timeout))
        return {"demo/command": "1", "demo/readback": "1"}.get(path, "0")

    def journal_unit(self, unit, since, until):
        self.read_calls.append(("journal", unit, since, until))
        return unit + " evidence\n"

    def history(self, channels, since, until, limit):
        self.read_calls.append(("history", tuple(channels), since, until, limit))
        return "timestamp;channel;value\n1;demo/command;1\n"

    def diagnostic_info(self):
        self.read_calls.append(("system",))
        return {
            "os": {"ID": "debian"},
            "uptime_seconds": 123.0,
            "packages": {"neiro-nst": "1.0.0"},
            "resources": {"status": "ok"},
        }


class DiagnosticsTests(fixtures.Fixture):
    def setUp(self):
        super().setUp()
        self.system = DiagnosticSystem()
        self.engine.system = self.system
        self.put("/etc/wb-mqtt-db.conf", b'{"password":"dont-copy-me","groups":[]}\n')

    def members(self, result):
        path = Path(result["bundle"])
        self.assertEqual(digest(path.read_bytes()), result["sha256"])
        with tarfile.open(path, "r:gz") as tar:
            return {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}

    def test_component_bundle_contains_sources_controls_history_journals_and_checksums(self):
        result = Diagnostics(self.engine, {"demo": profile()}).collect("demo", "30m")
        self.assertEqual(result["final_status"], "ok", result)
        files = self.members(result)
        self.assertIn("meta.json", files)
        self.assertIn("system.json", files)
        self.assertIn("journals/wb-rules.log", files)
        self.assertIn("journals/wb-mqtt-db.log", files)
        self.assertIn("history/mqtt.csv", files)
        self.assertIn("current-controls.json", files)
        self.assertIn("sources/etc/neiro/components/demo/data.json", files)
        self.assertEqual(files["sources/etc/neiro/components/demo/data.json"], b"old")
        self.assertIn("checksums.sha256", files)
        controls = json.loads(files["current-controls.json"])
        self.assertEqual([c["kind"] for c in controls], ["command", "readback"])
        self.assertEqual(self.system.actions, [], "diagnostics must not call service mutation")

    def test_config_secret_is_redacted_but_original_hash_is_recorded(self):
        result = Diagnostics(self.engine, {"demo": profile()}).collect("demo", "1h")
        files = self.members(result)
        config = files["config/etc/wb-mqtt-db.conf"]
        self.assertNotIn(b"dont-copy-me", config)
        inventory = json.loads(files["installed-files.json"])
        entry = next(x for x in inventory if x["path"] == "/etc/wb-mqtt-db.conf")
        self.assertTrue(entry["redacted"])
        self.assertEqual(entry["sha256"], digest(b'{"password":"dont-copy-me","groups":[]}\n'))
        self.assertNotEqual(entry["bundle_sha256"], entry["sha256"])

    def test_common_bundle_requires_no_component_profile_and_includes_managed_source(self):
        result = Diagnostics(self.engine, {}).collect(None, "1h")
        files = self.members(result)
        self.assertIn("sources/etc/neiro/components/demo/data.json", files)
        self.assertNotIn("history/mqtt.csv", files)
        self.assertEqual(self.system.actions, [])

    def test_history_unavailable_is_warning_not_unsafe_fallback(self):
        def unavailable(*args):
            raise Error("db history unavailable")
        self.system.history = unavailable
        result = Diagnostics(self.engine, {"demo": profile()}).collect("demo", "1h")
        self.assertEqual(result["final_status"], "ok")
        self.assertTrue(any("db history unavailable" in x for x in result["warnings"]))
        files = self.members(result)
        self.assertIn("history/unavailable.json", files)
        self.assertEqual(self.system.actions, [])

    def test_window_is_bounded_and_sensitive_paths_are_rejected(self):
        with self.assertRaisesRegex(Error, "7 days"):
            parse_since("8d")
        bad = profile()
        bad["config_files"] = ["/root/.ssh/id_rsa"]
        with self.assertRaisesRegex(Error, "Sensitive path"):
            validate_profile(bad)

    def test_ivolga_hhm_profile_has_reproducible_502_evidence_channels(self):
        data = json.loads((ROOT / "diagnostics/ivolga-boiler-hhm-v1.json").read_text(encoding="utf-8"))
        validate_profile(data)
        channels = set(data["history_channels"])
        required = {
            "A03/K2", "A03/Real State K2",
            "A05/Channel 2 Dimming Level", "A05/Channel 2 Switch",
            "wb-m1w2_167/External Sensor 1", "wb-m1w2_167/External Sensor 2",
            "wb-m1w2_170/External Sensor 1", "wbe2-i-opentherm_11/Heating Setpoint",
            "wb-w1/28-0000108fbbe1", "HHM3_FSE/diag_request_502",
        }
        self.assertTrue(required.issubset(channels))
        for zone in range(606, 615):
            self.assertIn("NL_simple_thermostat_{}/current_state".format(zone), channels)
        self.assertEqual(set(data["journals"]), {"wb-rules", "wb-mqtt-db", "wb-mqtt-serial"})
        self.assertIn("/etc/wb-rules/500_HHM3_FSE.js", data["source_files"])
        self.assertIn("/etc/wb-rules/620_thermostats.js", data["source_files"])


if __name__ == "__main__":
    unittest.main()
