"""NST #92 firmware/self-update migration safety regressions."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_core as fixtures
from nst.firmware import Firmware
from nst.self_update import SelfUpdate


class PackageReleases:
    def __init__(self, package=None):
        self._package = package
        self.asset_calls = 0

    def package(self):
        return self._package

    def asset(self, *args, **kwargs):
        self.asset_calls += 1
        raise AssertionError("mutation payload must not be fetched in this test")


def unknown_controller():
    return {
        "state": "unknown",
        "identity": {"serial": "UNKNOWN1", "fingerprint_sha256": None},
        "assignment": None,
        "mutation_allowed": False,
        "reason": "CONTROLLER_NOT_REGISTERED",
    }


class FirmwareSelfUpdateNSTTests(fixtures.Fixture):
    def test_firmware_update_and_recover_are_explicit_mutations_and_block_unknown_controller(self):
        self.engine.controller = unknown_controller()
        calls = []

        def runner(*args):
            calls.append(args)
            raise AssertionError("official updater must not start")

        for action in ("update", "recover"):
            before = self.snapshot()
            result = Firmware(self.engine, runner).execute(action)
            self.assertEqual(result["final_status"], "failed", result)
            self.assertIn("CONTROLLER_NOT_REGISTERED", result["error"])
            self.assertEqual(before, self.snapshot())
        self.assertEqual(calls, [])

    def test_firmware_check_rejects_unsupported_official_updater_without_mutation(self):
        self.put("/usr/bin/wb-mcu-fw-updater", b"--debug update-all recover-all")
        before = self.snapshot()
        with patch.object(self.system, "run", return_value="99.99-test"):
            result = Firmware(self.engine, lambda *args: ("", 0)).execute("check")
        self.assertEqual(result["final_status"], "failed", result)
        self.assertIn("UPDATER_UNSUPPORTED", result["error"])
        self.assertEqual(before, self.snapshot())

    def test_self_update_check_is_read_only_even_for_unknown_controller(self):
        self.engine.controller = unknown_controller()
        package = {
            "version": "2.1",
            "approved": True,
            "sha256": "0" * 64,
            "asset": {"id": 1, "digest": "sha256:" + "0" * 64},
            "package_name": "nst",
            "executable": "/usr/bin/nst",
        }
        releases = PackageReleases(package)
        self.engine.releases = releases
        before = self.snapshot()
        result = SelfUpdate(self.engine).execute(check=True)
        self.assertEqual(result["final_status"], "ok", result)
        self.assertTrue(result["update_available"])
        self.assertEqual(before, self.snapshot())
        self.assertEqual(releases.asset_calls, 0)

    def test_self_update_mutation_blocks_unknown_controller_before_download_or_state_write(self):
        self.engine.controller = unknown_controller()
        releases = PackageReleases({
            "version": "2.1",
            "approved": True,
            "sha256": "0" * 64,
            "asset": {"id": 1, "digest": "sha256:" + "0" * 64},
            "package_name": "nst",
            "executable": "/usr/bin/nst",
        })
        self.engine.releases = releases
        before = self.snapshot()
        result = SelfUpdate(self.engine).execute(check=False)
        self.assertEqual(result["final_status"], "failed", result)
        self.assertIn("CONTROLLER_NOT_REGISTERED", result["error"])
        self.assertEqual(before, self.snapshot())
        self.assertEqual(releases.asset_calls, 0)


if __name__ == "__main__":
    unittest.main()
