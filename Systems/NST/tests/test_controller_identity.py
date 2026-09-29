"""NST #86: hardware identity, generated registry and lifecycle mutation guard."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from build_controller_registry import build_registry
from nli.controller import ControllerRegistry, read_hardware_identity
from nli.core import Engine
from nli.firmware import Firmware
from nli.self_update import SelfUpdate


class NoTouchSystem:
    def hostname(self):
        return "renamed-hostname"

    def firmware_busy(self):
        return []


def identity(serial="ABF62SL", fingerprint=None):
    return {"serial": serial, "serial_source": "/var/lib/wirenboard/short_sn", "fingerprint": fingerprint}


def entry(state="active", serial="ABF62SL", node="boiler", role="boiler", fingerprint=None):
    value = {
        "object": "05_31_Ivolga_13",
        "name": "Котельная",
        "node": node,
        "role": role,
        "state": state,
        "capabilities": ["hhm", "pressure_makeup"],
        "diagnostics_profile": "NLI/diagnostics/controller-default-v1.json",
        "profile": "objects/05_31_Ivolga_13/controllers/" + serial + ".json",
    }
    if fingerprint is not None:
        value["fingerprint_sha256"] = fingerprint
    return value


def registry(entries):
    return ControllerRegistry({"schema": 1, "source": "fixture", "controllers": entries})


class IdentityTests(unittest.TestCase):
    def test_reads_short_sn_without_hostname_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "var/lib/wirenboard/short_sn"
            path.parent.mkdir(parents=True)
            path.write_text("ABF62SL\n", encoding="utf-8")
            result = read_hardware_identity(root)
            self.assertEqual(result["serial"], "ABF62SL")
            self.assertEqual(result["serial_source"], "/var/lib/wirenboard/short_sn")

    def test_short_sn_conf_is_accepted_as_compatibility_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "var/lib/wirenboard/short_sn.conf"
            path.parent.mkdir(parents=True)
            path.write_text("abf62sl\n", encoding="utf-8")
            self.assertEqual(read_hardware_identity(root)["serial"], "ABF62SL")

    def test_fingerprint_uses_cpu_and_emmc_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cpu = root / "proc/cpuinfo"
            cpu.parent.mkdir(parents=True)
            cpu.write_text("Processor : test\nSerial : 00000000ABCDEF12\n", encoding="utf-8")
            mmc = root / "sys/class/mmc_host/mmc0/mmc0:0001/serial"
            mmc.parent.mkdir(parents=True)
            mmc.write_text("1234ABCD\n", encoding="utf-8")
            fp = read_hardware_identity(root)["fingerprint"]
            self.assertEqual(fp["sources"], ["cpu_serial", "emmc_serial"])
            self.assertEqual(len(fp["sha256"]), 64)


class RegistryLifecycleTests(unittest.TestCase):
    def test_unknown_identity_is_readable_but_mutation_denied(self):
        context = registry({}).resolve(identity("ZZZZ999"))
        self.assertEqual(context["state"], "unknown")
        self.assertFalse(context["mutation_allowed"])
        self.assertIn("CONTROLLER_NOT_REGISTERED", context["reason"])

    def test_planned_active_retired_lifecycle(self):
        for state, allowed in (("planned", False), ("active", True), ("retired", False)):
            context = registry({"ABF62SL": entry(state)}).resolve(identity())
            self.assertEqual(context["state"], state)
            self.assertEqual(context["mutation_allowed"], allowed)

    def test_pinned_fingerprint_mismatch_denies_active_mutation(self):
        expected = "0" * 64
        observed = {"sha256": "1" * 64, "sources": ["cpu_serial"]}
        context = registry({"ABF62SL": entry("active", fingerprint=expected)}).resolve(identity(fingerprint=observed))
        self.assertEqual(context["fingerprint_status"], "mismatch")
        self.assertFalse(context["mutation_allowed"])

    def test_engine_blocks_unknown_and_retired_before_lock_or_component_lookup(self):
        config = {"object": "05_31_Ivolga_13", "role": "boiler",
                  "hostname": "anything", "components": {}}
        for context in (
            registry({}).resolve(identity("ZZZZ999")),
            registry({"ABF62SL": entry("retired")}).resolve(identity()),
        ):
            with tempfile.TemporaryDirectory() as tmp:
                engine = Engine(config, root=tmp, system=NoTouchSystem(), controller=context)
                result = engine.mutate("update", "demo")
                self.assertEqual(result["final_status"], "failed")
                self.assertIn("CONTROLLER_", result["error"])
                self.assertFalse((Path(tmp) / "mnt/data/var/lib/neiro/nli").exists())

    def test_all_mutation_entry_points_are_blocked_for_unknown_controller(self):
        context = registry({}).resolve(identity("ZZZZ999"))
        config = {"object": "05_31_Ivolga_13", "role": "boiler",
                  "hostname": "anything", "components": {}}
        with tempfile.TemporaryDirectory() as tmp:
            engine = Engine(config, root=tmp, system=NoTouchSystem(), controller=context)
            self.assertIn("CONTROLLER_NOT_REGISTERED", engine.mutate("rollback", "demo")["error"])
            self.assertIn("CONTROLLER_NOT_REGISTERED", Firmware(engine).execute("update")["error"])
            self.assertIn("CONTROLLER_NOT_REGISTERED", SelfUpdate(engine).execute()["error"])
            self.assertFalse((Path(tmp) / "mnt/data/var/lib/neiro/nli").exists())

    def test_active_assignment_allows_guard_and_does_not_depend_on_hostname(self):
        context = registry({"ABF62SL": entry("active")}).resolve(identity())
        config = {"object": "05_31_Ivolga_13", "role": "boiler",
                  "hostname": "old-or-renamed-host", "components": {}}
        with tempfile.TemporaryDirectory() as tmp:
            engine = Engine(config, root=tmp, system=NoTouchSystem(), controller=context)
            engine.require_controller_mutation("update")


class RegistryBuilderTests(unittest.TestCase):
    def fixture(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        diag = root / "NLI/diagnostics/controller-default-v1.json"
        diag.parent.mkdir(parents=True)
        diag.write_text('{"schema":1}\n', encoding="utf-8")
        return tmp, root

    def write_profile(self, root, object_name, serial, **changes):
        data = {
            "schema": 1,
            "name": "Controller",
            "node": "boiler",
            "role": "boiler",
            "state": "active",
            "capabilities": [],
            "diagnostics_profile": "NLI/diagnostics/controller-default-v1.json",
        }
        data.update(changes)
        path = root / "objects" / object_name / "controllers" / (serial + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_abf62sl_pilot_registry(self):
        tmp, root = self.fixture()
        self.addCleanup(tmp.cleanup)
        self.write_profile(root, "05_31_Ivolga_13", "ABF62SL")
        built = build_registry(root)
        self.assertEqual(built["controllers"]["ABF62SL"]["object"], "05_31_Ivolga_13")

    def test_duplicate_serial_fails(self):
        tmp, root = self.fixture()
        self.addCleanup(tmp.cleanup)
        self.write_profile(root, "obj_a", "ABF62SL")
        self.write_profile(root, "obj_b", "ABF62SL")
        with self.assertRaisesRegex(Exception, "Duplicate WB serial"):
            build_registry(root)

    def test_invalid_schema_and_role_fail(self):
        tmp, root = self.fixture()
        self.addCleanup(tmp.cleanup)
        self.write_profile(root, "obj_a", "AAAA111", schema=2)
        with self.assertRaisesRegex(Exception, "schema"):
            build_registry(root)
        (root / "objects/obj_a/controllers/AAAA111.json").unlink()
        self.write_profile(root, "obj_a", "AAAA111", role="invented")
        with self.assertRaisesRegex(Exception, "role"):
            build_registry(root)

    def test_missing_diagnostics_reference_fails(self):
        tmp, root = self.fixture()
        self.addCleanup(tmp.cleanup)
        self.write_profile(root, "obj_a", "AAAA111", diagnostics_profile="NLI/diagnostics/missing.json")
        with self.assertRaisesRegex(Exception, "Missing diagnostics"):
            build_registry(root)

    def test_conflicting_active_assignment_fails_but_planned_replacement_is_allowed(self):
        tmp, root = self.fixture()
        self.addCleanup(tmp.cleanup)
        self.write_profile(root, "obj_a", "AAAA111")
        self.write_profile(root, "obj_a", "BBBB222")
        with self.assertRaisesRegex(Exception, "Conflicting active"):
            build_registry(root)
        self.write_profile(root, "obj_a", "BBBB222", state="planned")
        built = build_registry(root)
        self.assertEqual(built["controllers"]["BBBB222"]["state"], "planned")


if __name__ == "__main__":
    unittest.main()
