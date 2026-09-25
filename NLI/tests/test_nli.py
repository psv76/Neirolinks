"""All mutations stay inside TemporaryDirectory; fake system has no hardware API."""
import hashlib
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nli.cli import main
from nli.core import Engine
from nli.firmware import Firmware, parse_result
from nli.manifest import validate
from nli.plugins import BOILER, GAZEBO
from nli.util import Error, Lock, atomic, digest, read_json, write_json


class FakeSystem:
    def __init__(self):
        self.actions = []
        self.failures = []
        self.controls = {"pressure_makeup/active": "0", "A04/K1": "0"}
        self.busy = []
        self.logs = ""
        self.frame = {"sent_ms": time.time() * 1000, "source": "ivolga-hhm3-house", "v": 3, "seq": 1}

    def hostname(self):
        return "sandbox-wb"

    def service(self, action, name):
        self.actions.append((action, name))
        if self.failures and self.failures[0] == action:
            self.failures.pop(0)
            raise Error("Injected service " + action + " failure")

    def active(self, name):
        pass

    def control(self, path, timeout=None):
        return self.controls.get(path, "OK")

    def rules_version(self):
        return "2.46.5"

    def mqtt(self, topic, fresh=False, timeout=None):
        assert fresh
        return json.dumps(self.frame)

    def journal(self, since=None):
        return self.logs

    def firmware_busy(self):
        return self.busy

    def run(self, argv):
        if argv[:2] == ['/usr/bin/dpkg-query', '-S']:
            return 'wb-mcu-fw-updater: /usr/bin/wb-mcu-fw-updater'
        if argv[:2] == ['/usr/bin/dpkg', '--verify']:
            return ''
        return '1.99-test'


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.system = FakeSystem()
        self.component = "demo"
        self.config = dict(release_source="pinned", object="test", role="boiler", hostname="sandbox-wb", components={})
        self.base = self.manifest("1.0", b"old")
        self.new = self.manifest("1.1", b"new")
        self.setup_component()

    def tearDown(self):
        self.temp.cleanup()

    def manifest(self, version, content):
        return dict(schema=1, component="demo", version=version, object="test", role="boiler",
                    release=dict(repository="psv76/Neirolinks", commit="a" * 40),
                    files=[dict(source="demo/data.json", target="/etc/neiro/components/demo/data.json", sha256=digest(content))],
                    services=dict(stop=[], start=[]), preflight=["identity", "drift"],
                    verify=dict(controls=[], runtime_version=version, health_contract="none"),
                    rollback="previous-managed-release")

    def put(self, path, data):
        p = self.root / path.lstrip("/")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def pin(self, path, manifest):
        data = json.dumps(manifest).encode()
        self.put(path, data)
        return dict(path=path, sha256=digest(data))

    def setup_component(self):
        r = dict(plugin="files", baseline=self.pin("/mnt/data/etc/neiro/nli/base.json", self.base),
                 target=self.pin("/mnt/data/etc/neiro/nli/target.json", self.new), payload_dir="/opt/payload",
                 allowed_targets=[f["target"] for f in self.new["files"]])
        self.config["components"][self.component] = r
        self.put(self.base["files"][0]["target"], b"old")
        self.put("/opt/payload/demo/data.json", b"new")
        self.engine = Engine(self.config, self.root, self.system)

    def repin(self):
        self.config["components"][self.component]["target"] = self.pin("/mnt/data/etc/neiro/nli/target.json", self.new)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}


class CoreTests(Fixture):
    def test_success_update_and_rollback(self):
        result = self.engine.mutate("update", "demo")
        self.assertEqual(result["final_status"], "ok", result)
        self.assertEqual(self.engine.current("demo")["version"], "1.1")
        result = self.engine.mutate("rollback", "demo")
        self.assertEqual(result["final_status"], "ok", result)
        self.assertEqual(self.engine.current("demo")["version"], "1.0")
        self.assertFalse(self.engine.pending())

    def test_read_only_commands_do_not_change_any_file(self):
        before = self.snapshot()
        for command in ("status", "check", "verify"):
            r = self.engine.read_operation(command, None if command == "status" else "demo")
            self.assertEqual(r["final_status"], "ok", r)
        self.assertEqual(before, self.snapshot())

    def test_cli_contract(self):
        for args in (["status"], ["check", "demo"], ["update", "demo"], ["verify", "demo"], ["rollback", "demo"]):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = main(["--json", *args], engine=self.engine)
            self.assertEqual(code, 0, output.getvalue())
            self.assertEqual(json.loads(output.getvalue())["final_status"], "ok")

    def test_unknown_component(self):
        self.assertEqual(self.engine.read_operation("check", "other")["final_status"], "failed")

    def test_role_mismatch(self):
        self.new["role"] = "gazebo"
        self.repin()
        self.assertEqual(self.engine.mutate("update", "demo")["final_status"], "failed")
        self.assertEqual(self.system.actions, [])

    def test_hostname_mismatch(self):
        self.config["hostname"] = "wrong"
        self.assertEqual(self.engine.mutate("update", "demo")["final_status"], "failed")

    def test_manifest_hash_mismatch(self):
        self.put("/mnt/data/etc/neiro/nli/target.json", b"{}")
        self.assertIn("Manifest checksum", self.engine.mutate("update", "demo")["error"])

    def test_payload_checksum_mismatch_before_mutation(self):
        self.put("/opt/payload/demo/data.json", b"truncated")
        result = self.engine.mutate("update", "demo")
        self.assertEqual(result["final_status"], "failed")
        self.assertIsNone(self.engine.pending())
        self.assertEqual(self.engine.target(self.base["files"][0]["target"]).read_bytes(), b"old")

    def test_network_unavailable_and_interrupted_download(self):
        del self.config["components"]["demo"]["payload_dir"]
        for failure in (OSError("network unavailable"), OSError("connection interrupted")):
            with patch("urllib.request.OpenerDirector.open", side_effect=failure):
                result = self.engine.mutate("update", "demo")
                self.assertEqual(result["final_status"], "failed")
                self.assertIn("download failed", result["error"])
        self.assertFalse(self.engine.pending())

    def test_drift_blocks_before_backup(self):
        self.put(self.base["files"][0]["target"], b"unknown live")
        result = self.engine.mutate("update", "demo")
        self.assertEqual(result["final_status"], "failed")
        self.assertIsNone(result["backup"])

    def test_install_failure_rolls_back(self):
        original = self.engine.install
        count = []
        def fail_once(*args):
            count.append(1)
            if len(count) == 1:
                self.put(self.base["files"][0]["target"], b"partial")
                raise OSError("injected disk error")
            return original(*args)
        with patch.object(self.engine, "install", side_effect=fail_once):
            result = self.engine.mutate("update", "demo")
        self.assertEqual(result["final_status"], "rolled_back", result)
        self.assertEqual(self.engine.target(self.base["files"][0]["target"]).read_bytes(), b"old")

    def test_verify_failure_rolls_back(self):
        with patch.object(self.engine, "verify", side_effect=[Error("verify failed"), None]):
            result = self.engine.mutate("update", "demo")
        self.assertEqual(result["final_status"], "rolled_back", result)

    def test_rollback_failure_is_durable(self):
        with patch.object(self.engine, "install", side_effect=OSError("disk full")):
            result = self.engine.mutate("update", "demo")
        self.assertEqual(result["final_status"], "partial_failure")
        self.assertEqual(self.engine.read_operation("status")["final_status"], "recovery_required")
        self.assertEqual(self.engine.mutate("update", "demo")["final_status"], "failed")
        self.assertEqual(self.engine.mutate("rollback", "demo")["final_status"], "ok")

    def test_ctrl_c_restores(self):
        with patch.object(self.engine, "verify", side_effect=[KeyboardInterrupt(), None]):
            result = self.engine.mutate("update", "demo")
        self.assertEqual(result["final_status"], "rolled_back")

    def test_no_previous_release(self):
        self.assertIn("No previous", self.engine.mutate("rollback", "demo")["error"])

    def test_corrupted_backup_rejected_before_install(self):
        result = self.engine.mutate("update", "demo")
        backup = result["backup"]["id"]
        self.put("/mnt/data/var/lib/neiro/nli/backups/" + backup + "/0.bin", b"corrupt")
        result = self.engine.mutate("rollback", "demo")
        self.assertEqual(result["final_status"], "failed")
        self.assertIn("Corrupted backup", result["error"])
        self.assertEqual(self.engine.current("demo")["version"], "1.1")

    def test_corrupted_backup_metadata(self):
        result = self.engine.mutate("update", "demo")
        self.put("/mnt/data/var/lib/neiro/nli/backups/" + result["backup"]["id"] + "/metadata.json", b"{}")
        self.assertIn("Corrupted backup", self.engine.mutate("rollback", "demo")["error"])

    def test_lock_concurrent_update(self):
        path = self.engine.target("/mnt/data/var/lib/neiro/nli/mutation.lock")
        with Lock(path):
            with self.assertRaisesRegex(Error, "NLI_BUSY"):
                self.engine.mutate("update", "demo")

    def test_manifest_rejects_unsafe_values(self):
        for field, values in (("target", ["/etc/../root/file", "/etc/wb-rules/507_Pressure_makeup.js", "/tmp/test", "/etc/a\\b"]),
                              ("source", ["../escape", "/absolute", "https://arbitrary", "a//b"]),
                              ("sha256", ["x", "a" * 63])):
            for value in values:
                with self.subTest(field=field, value=value):
                    m = copy.deepcopy(self.new)
                    m["files"][0][field] = value
                    with self.assertRaises(Error):
                        validate(m)

    def test_manifest_rejects_hooks_services_mutable_release(self):
        mutations = [lambda m: m.update(shell="rm -rf /"),
                     lambda m: m["services"]["stop"].append("ssh"),
                     lambda m: m["release"].update(commit="main"),
                     lambda m: m["files"].append(m["files"][0]),
                     lambda m: m.update(schema=True)]
        for mutate in mutations:
            m = copy.deepcopy(self.new)
            mutate(m)
            with self.assertRaises(Error):
                validate(m)

    def test_local_whitelist_cannot_be_escaped(self):
        self.new["files"][0]["target"] = "/etc/passwd"
        self.repin()
        self.assertEqual(self.engine.mutate("update", "demo")["final_status"], "failed")

    def test_no_dynamic_file_deletion_in_v01(self):
        self.new["files"][0]["target"] = "/etc/neiro/components/demo/new.json"
        self.config["components"]["demo"]["allowed_targets"].append(self.new["files"][0]["target"])
        self.repin()
        self.assertIn("stable managed file set", self.engine.mutate("update", "demo")["error"])

    def test_symlink_target_rejected(self):
        target = self.engine.target(self.base["files"][0]["target"])
        target.unlink()
        outside = self.put("/outside", b"old")
        try:
            target.symlink_to(outside)
        except OSError:
            self.skipTest("Windows symlink privilege unavailable; Linux CI covers this")
        with self.assertRaisesRegex(Error, "Symlink"):
            self.engine.current("demo")

    def test_metadata_and_previous_release_chain(self):
        self.engine.mutate("update", "demo")
        self.new["version"] = "1.2"
        self.repin()
        self.engine.mutate("update", "demo")
        self.engine.mutate("rollback", "demo")
        self.assertEqual(self.engine.current("demo")["version"], "1.1")
        self.engine.mutate("rollback", "demo")
        self.assertEqual(self.engine.current("demo")["version"], "1.0")

    def test_process_death_after_replacement_leaves_recoverable_intent(self):
        config = self.put("/test-config.json", json.dumps(self.config).encode())
        code = """
import os, sys
sys.path[:0] = [sys.argv[1], sys.argv[2]]
from test_nli import FakeSystem
from nli.core import Engine
from nli.util import read_json
e = Engine(read_json(sys.argv[3]), sys.argv[4], FakeSystem())
original = e.install
def crash(*args):
    original(*args)
    os._exit(73)
e.install = crash
e.mutate('update', 'demo')
"""
        p = subprocess.run([sys.executable, "-B", "-c", code, str(ROOT), str(ROOT / "tests"), str(config), str(self.root)])
        self.assertEqual(p.returncode, 73)
        self.assertEqual(self.engine.read_operation("status")["final_status"], "recovery_required")
        result = self.engine.mutate("rollback", "demo")
        self.assertEqual(result["final_status"], "ok", result)
        self.assertEqual(self.engine.target(self.base["files"][0]["target"]).read_bytes(), b"old")

    def test_process_lock_is_exclusive(self):
        path = self.engine.target("/mnt/data/var/lib/neiro/nli/mutation.lock")
        code = """
import sys
sys.path.insert(0, sys.argv[1])
from nli.util import Lock, Error
try:
    with Lock(sys.argv[2]):
        sys.exit(7)
except Error:
    sys.exit(0)
"""
        with Lock(path):
            p = subprocess.run([sys.executable, "-B", "-c", code, str(ROOT), str(path)])
        self.assertEqual(p.returncode, 0)

    def test_automatic_restore_recreates_missing_managed_file(self):
        original = self.engine.install
        count = []
        def interrupted(*args):
            count.append(1)
            if len(count) == 1:
                self.engine.target(self.base["files"][0]["target"]).unlink()
                raise OSError("injected missing target during failure")
            return original(*args)
        with patch.object(self.engine, "install", side_effect=interrupted):
            result = self.engine.mutate("update", "demo")
        self.assertEqual(result["final_status"], "rolled_back", result)
        self.assertEqual(self.engine.target(self.base["files"][0]["target"]).read_bytes(), b"old")

    def test_duplicate_json_keys_rejected(self):
        from nli.util import decode
        with self.assertRaisesRegex(Error, "Duplicate"):
            decode('{"schema":1,"schema":2}')


class HHMTests(Fixture):
    def setUp(self):
        super().setUp()
        self.component = "hhm"
        self.config["object"] = "05_31_Ivolga_13"
        self.config["components"] = {}
        self.base = self.hhm_manifest("boiler")
        self.new = copy.deepcopy(self.base)
        self.new["version"] = "3.0.0-FSE+new"
        self.config["components"]["hhm"] = dict(plugin="hhm", payload_dir="/opt/payload", unmanaged_rules={})
        for f in self.base["files"]:
            data = b"version:'3.0.0-FSE'" if f["target"].endswith("HHM3Config.js") else b"// rule"
            self.put(f["target"], data)
            self.put("/opt/payload/" + f["source"], data)
        r = self.config["components"]["hhm"]
        r["baseline"] = self.pin("/mnt/data/etc/neiro/nli/base.json", self.base)
        r["target"] = self.pin("/mnt/data/etc/neiro/nli/target.json", self.new)
        self.engine = Engine(self.config, self.root, self.system)

    def hhm_manifest(self, role):
        m = self.manifest("3.0.0-FSE+base", b"unused")
        m.update(component="hhm", object="05_31_Ivolga_13", role=role, preflight=["identity", "drift", "hhm"],
                 services=dict(stop=["wb-rules"], start=["wb-rules"]))
        m["verify"] = dict(controls=[], runtime_version="3.0.0-FSE", health_contract="legacy-3.0")
        m["files"] = [dict(source="payload/" + p.rsplit("/", 1)[1], target=p,
                           sha256=digest(b"version:'3.0.0-FSE'" if p.endswith("HHM3Config.js") else b"// rule"))
                      for p in sorted(BOILER if role == "boiler" else GAZEBO)]
        return m

    def test_hhm_success_service_order(self):
        result = self.engine.mutate("update", "hhm")
        self.assertEqual(result["final_status"], "ok", result)
        self.assertEqual(self.system.actions, [("stop", "wb-rules"), ("start", "wb-rules")])
        self.assertEqual(self.engine.mutate("rollback", "hhm")["final_status"], "ok")

    def test_pressure_value_not_gate(self):
        for value in ("0", "-999", "NaN", "100"):
            self.system.controls["pressure_makeup/pressure_bar"] = value
            self.assertEqual(self.engine.read_operation("check", "hhm")["final_status"], "ok")

    def test_active_makeup_and_k1_block(self):
        for control in ("pressure_makeup/active", "A04/K1"):
            for value in ("1", "", "unknown"):
                self.system.controls[control] = value
                result = self.engine.mutate("update", "hhm")
                self.assertEqual(result["final_status"], "failed")
                self.assertEqual(self.system.actions, [])
            self.system.controls[control] = "0"

    def test_stop_and_start_failure_roll_back(self):
        for failure in ("stop", "start"):
            self.system.failures = [failure]
            result = self.engine.mutate("update", "hhm")
            self.assertEqual(result["final_status"], "rolled_back", result)
            self.assertIn("failed_or_interrupted", [s["result"] for s in result["services"]])

    def test_unknown_second_writer_blocks(self):
        self.put("/etc/wb-rules/another-writer.js", b"dev['A03/K1']=1")
        result = self.engine.mutate("update", "hhm")
        self.assertIn("possible writer", result["error"])
        self.assertEqual(self.system.actions, [])

    def test_507_untouched_not_backed_up(self):
        data = b"// protected production 507"
        self.put("/etc/wb-rules/507_Pressure_makeup.js", data)
        self.config["components"]["hhm"]["unmanaged_rules"]["/etc/wb-rules/507_Pressure_makeup.js"] = digest(data)
        before = self.engine.target("/etc/wb-rules/507_Pressure_makeup.js").read_bytes()
        r = self.engine.mutate("update", "hhm")
        self.assertEqual(r["final_status"], "ok", r)
        meta, _ = self.engine.load_backup(r["backup"], "hhm")
        self.assertFalse(any("507" in f["target"] for f in meta["files"]))
        self.assertEqual(before, self.engine.target("/etc/wb-rules/507_Pressure_makeup.js").read_bytes())

    def test_gazebo_payload_is_separate(self):
        gazebo = self.hhm_manifest("gazebo")
        with self.assertRaisesRegex(Error, "role mismatch"):
            self.engine.validate(gazebo, "hhm")
        self.config["role"] = "gazebo"
        self.engine.validate(gazebo, "hhm")
        self.assertNotIn("/etc/wb-rules/500_HHM3_FSE.js", {f["target"] for f in gazebo["files"]})

    def test_verify_is_read_only_and_runtime_errors_fail(self):
        before = self.snapshot()
        self.assertEqual(self.engine.read_operation("verify", "hhm")["final_status"], "ok")
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.system.actions, [])
        self.system.logs = "SyntaxError: 500_HHM3_FSE.js"
        self.assertEqual(self.engine.read_operation("verify", "hhm")["final_status"], "failed")



    def test_interlock_rechecked_after_download(self):
        original = self.engine.payload
        def changed(m, **kwargs):
            data = original(m, **kwargs)
            self.system.controls["pressure_makeup/active"] = "1"
            return data
        with patch.object(self.engine, "payload", side_effect=changed):
            r = self.engine.mutate("update", "hhm")
        self.assertEqual(r["final_status"], "failed")
        self.assertEqual(self.system.actions, [])

    def test_rollback_interlock_failure_is_not_silenced(self):
        def failed_verify(*args):
            self.system.controls["A04/K1"] = "1"
            raise Error("verify error")
        with patch.object(self.engine, "verify", side_effect=failed_verify):
            r = self.engine.mutate("update", "hhm")
        self.assertEqual(r["final_status"], "partial_failure")
        self.assertIsNotNone(self.engine.pending())


class FirmwareTests(Fixture):
    def setUp(self):
        super().setUp()
        self.source = b"--debug # official fixture commands: update-all recover-all"
        self.put("/usr/bin/wb-mcu-fw-updater", self.source)
        blob = hashlib.sha1(b'blob ' + str(len(self.source)).encode() + b'\0' + self.source).hexdigest()
        supported = patch('nli.firmware.SUPPORTED', {'1.99-test': blob})
        supported.start()
        self.addCleanup(supported.stop)
        self.calls = []

    def runner(self, action, log_path):
        self.calls.append(action)
        text = ("Device /dev/ttyRS485-1 slave 12: Done\n1 upgraded, 0 skipped upgrade, 0 bootloader updates available, "
                "0 stuck in bootloader, 0 disconnected, 0 foreign and 0 too old for any updates.") if action == "update" else (
                "Device /dev/ttyRS485-1 slave 12: Done\n1 recovered, 2 was already working, 0 not recovered and 0 not answered to recover cmd.")
        log_path.write_text(text)
        return text, 0

    def test_absent(self):
        self.engine.target("/usr/bin/wb-mcu-fw-updater").unlink()
        self.assertIn("UPDATER_ABSENT", Firmware(self.engine).execute("check")["error"])

    def test_busy(self):
        self.system.busy = ["123"]
        r = Firmware(self.engine, self.runner).execute("update")
        self.assertIn("UPDATER_BUSY", r["error"])
        self.assertEqual(self.calls, [])

    def test_check_strictly_read_only_no_fake_inventory(self):
        before = self.snapshot()
        r = Firmware(self.engine, self.runner).execute("check")
        self.assertEqual(r["final_status"], "unavailable")
        self.assertEqual(self.calls, [])
        self.assertEqual(before, self.snapshot())

    def test_update_and_recover_flow(self):
        for action in ("update", "recover"):
            r = Firmware(self.engine, self.runner).execute(action)
            self.assertEqual(r["final_status"], "ok", r)
            self.assertTrue(r["device_report"])
        self.assertEqual(self.calls, ["update", "recover"])
        self.assertFalse(self.engine.pending())

    def test_partial_failure_despite_zero_exit(self):
        text = "1 upgraded, 0 skipped upgrade, 0 bootloader updates available, 1 stuck in bootloader, 0 disconnected, 0 foreign and 0 too old"
        r = Firmware(self.engine, lambda *args: (text, 0)).execute("update")
        self.assertEqual(r["final_status"], "partial_failure")

    def test_unknown_summary_is_not_success(self):
        self.assertEqual(parse_result("update", "new unknown format", 0)["final_status"], "unverified")

    def test_package_change_requires_review(self):
        self.put("/usr/bin/wb-mcu-fw-updater", self.source + b"changed")
        self.assertEqual(Firmware(self.engine, self.runner).execute("update")["final_status"], "failed")
        self.assertEqual(self.calls, [])

    def test_official_debian_shebang_and_missing_docs_are_accepted(self):
        source = b"#! /usr/bin/python3\n--debug # official fixture commands: update-all recover-all"
        canonical = b"#!/usr/bin/env python3\n--debug # official fixture commands: update-all recover-all"
        self.put("/usr/bin/wb-mcu-fw-updater", source)
        blob = hashlib.sha1(b'blob ' + str(len(canonical)).encode() + b'\0' + canonical).hexdigest()

        def run(argv):
            if argv[:2] == ['/usr/bin/dpkg-query', '-S']:
                return 'wb-mcu-fw-updater: /usr/bin/wb-mcu-fw-updater'
            if argv[:2] == ['/usr/bin/dpkg', '--verify']:
                return 'missing     /usr/share/doc/wb-mcu-fw-updater/changelog.gz'
            return '1.99-test'

        with patch('nli.firmware.SUPPORTED', {'1.99-test': blob}), patch.object(self.system, 'run', side_effect=run):
            result = Firmware(self.engine, self.runner).execute("check")
        self.assertEqual(result["final_status"], "unavailable", result)
        self.assertEqual(result["compatibility"], "supported")
        self.assertNotIn("error", result)

    def test_runtime_package_verify_issue_still_blocks(self):
        original = self.system.run

        def run(argv):
            if argv[:2] == ['/usr/bin/dpkg', '--verify']:
                return '??5?????? /usr/lib/python3/dist-packages/wb_mcu_fw_updater/update_monitor.py'
            return original(argv)

        with patch.object(self.system, 'run', side_effect=run):
            result = Firmware(self.engine, self.runner).execute("check")
        self.assertEqual(result["final_status"], "failed", result)
        self.assertIn("package verification failed", result["error"])

    def test_firmware_wrong_controller_blocks(self):
        self.config["hostname"] = "different-wb"
        r = Firmware(self.engine, self.runner).execute("update")
        self.assertEqual(r["final_status"], "failed")
        self.assertIn("hostname", r["error"])
        self.assertEqual(self.calls, [])

    def test_interrupted_updater_does_not_automatically_retry(self):
        def interrupted(*args):
            raise KeyboardInterrupt()
        result = Firmware(self.engine, interrupted).execute("update")
        self.assertEqual(result["final_status"], "partial_failure")
        self.assertIsNotNone(self.engine.pending())
        self.assertEqual(Firmware(self.engine, self.runner).execute("update")["final_status"], "failed")
        self.system.busy = ["123"]
        self.assertEqual(Firmware(self.engine, self.runner).execute("recover")["final_status"], "failed")
        self.system.busy = []
        self.assertEqual(Firmware(self.engine, self.runner).execute("recover")["final_status"], "ok")


if __name__ == "__main__":
    unittest.main()
