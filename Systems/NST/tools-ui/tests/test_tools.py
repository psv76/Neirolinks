"""NST Tools packaging, authorization surfaces and read-only adapter contracts."""
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(ROOT/path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ToolsTests(unittest.TestCase):
    def test_gate_is_admin_loopback_and_menu_has_three_children(self):
        gate = json.loads((ROOT/"config/gate.json").read_text())
        menu = json.loads((ROOT/"config/menu.json").read_text())
        self.assertEqual(gate["role"], "admin")
        self.assertEqual((gate["internalPort"], gate["externalPort"]), (18415, 28415))
        self.assertNotIn("menu", gate)
        self.assertEqual([x["title"]["en"] for x in menu[0]["children"]],
                         ["Service", "Sprut", "Docs"])
        for item in menu[0]["children"]:
            self.assertEqual(item["requiredRole"], "admin")
            self.assertEqual(item["url"].split("#")[0], "/open-neirolinks-tools")
            self.assertTrue(item["isExternal"])

    def test_allowlist_fixed_and_only_read_only_nst(self):
        e = load("nst_tools_executor", "service/executor.py")
        self.assertEqual(sorted(e.COMMANDS), ["channels", "check", "diagnostics", "inventory", "status"])
        for argv in e.COMMANDS.values():
            self.assertEqual(argv[:2], ["/usr/bin/nst", "--json"])
            self.assertNotIn("sync", argv)
            self.assertNotIn("update", argv)
        with self.assertRaises(ValueError):
            e.call("sync")

    def test_onboarding_calls_exact_cli_without_registration(self):
        e = load("nst_tools_exec_test", "service/executor.py")
        seen = []
        def runner(argv, **kwargs):
            seen.append(argv)
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({
                "final_status": "ok", "bundle": "/mnt/data/var/lib/neirolinks/nst/diagnostics/"
                "nst-onboarding-20261025T110000Z-00000000.tar.gz",
                "sha256": "f"*64}))
        with mock.patch.object(e, "export", return_value={"final_status": "ok", "export": "test"}) as export:
            result = e.call("channels", runner)
        self.assertEqual(seen, [["/usr/bin/nst", "--json", "onboarding", "channels"]])
        self.assertEqual(export.call_args.args[1], "channels")
        self.assertEqual(result["final_status"], "ok")

    def test_malformed_nst_and_action_rejected(self):
        e = load("nst_tools_exec_bad", "service/executor.py")
        def runner(argv, **_):
            return subprocess.CompletedProcess(argv, 0, stdout="{not json")
        with self.assertRaisesRegex(RuntimeError, "invalid"):
            e.call("inventory", runner)
        self.assertEqual(e.main(["executor", "sync"]), 2)

    def test_job_reentrancy_and_download_restrictions(self):
        srv = load("nst_tools_server_tests", "service/server.py")
        import threading
        started = threading.Event()
        release = threading.Event()
        def fake(action):
            started.set()
            release.wait(3)
            return {"final_status": "ok", "serial": "WB"}
        jobs = srv.Jobs(executor=fake)
        job_id = jobs.start("status")
        self.assertTrue(started.wait(2))
        with self.assertRaises(RuntimeError):
            jobs.start("channels")
        release.set()
        for _ in range(20):
            if jobs.get(job_id)["state"] != "running":
                break
            threading.Event().wait(0.05)
        self.assertEqual(jobs.get(job_id)["state"], "complete")
        self.assertIsNone(jobs.get("0"*32))
        self.assertIsNone(jobs.download(job_id, "invalid"))
        with self.assertRaises(ValueError):
            jobs.start("sync")

    def test_package_build_and_permissions(self):
        builder = load("nst_tools_build", "tools/build_deb.py")
        with tempfile.TemporaryDirectory() as d:
            deb = builder.build(Path(d)/"neirolinks-tools_1.0_all.deb")
            content = deb.read_bytes()
            self.assertTrue(content.startswith(b"!<arch>\n"))
            parts = {}
            index = 8
            while index < len(content):
                h = content[index:index+60]
                name = h[:16].decode().strip().rstrip("/")
                size = int(h[48:58].decode().strip())
                index += 60
                parts[name] = content[index:index+size]
                index += size + size % 2
            import gzip
            with tarfile.open(fileobj=io.BytesIO(parts["data.tar.gz"]), mode="r:gz") as tar:
                names = {m.name.lstrip("./"): m for m in tar.getmembers() if m.isfile()}
                self.assertIn("usr/share/wb-mqtt-homeui/custom-menu/neirolinks.json", names)
                self.assertIn("usr/share/wb-mqtt-homeui/gates.d/neirolinks-tools.json", names)
                self.assertIn("lib/systemd/system/neirolinks-tools.service", names)
                self.assertIn("usr/lib/neirolinks-tools/executor.py", names)
                self.assertEqual(names["etc/sudoers.d/neirolinks-tools"].mode, 0o440)
            with tarfile.open(fileobj=io.BytesIO(parts["control.tar.gz"]), mode="r:gz") as tar:
                names = {m.name.lstrip("./"):m for m in tar.getmembers() if m.isfile()}
                self.assertEqual({*names}, {"control", "preinst", "postinst", "prerm", "postrm"})
                self.assertTrue(all(names[x].mode == 0o755 for x in ("preinst","postinst","prerm","postrm")))

    def test_no_engineering_service_restart_in_scripts(self):
        scripts = "".join((ROOT/"packaging"/x).read_text() for x in ("preinst","postinst","prerm","postrm"))
        self.assertNotIn("wb-rules", scripts)
        self.assertNotIn("nst sync", scripts)
        self.assertNotIn("wb-mqtt-serial", scripts)
        self.assertIn("wb-homeui-gates apply", scripts)
        self.assertIn("wb-homeui-users list", scripts)
        self.assertIn("Configure a WB WebUI administrator", scripts)
        self.assertIn("neirolinks-tools.service", scripts)


if __name__ == "__main__":
    unittest.main()
