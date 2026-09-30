"""NST #91 controller cleanup policy."""
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_core as fixtures
from nst.controller_cleanup import ControllerCleanup, KEEP_DIAGNOSTIC_BUNDLES
from nst.layout import STATE_DIR
from nst.util import write_json


class CleanupTests(fixtures.Fixture):
    def bundle(self, index):
        path = self.engine.target(STATE_DIR + "/diagnostics/nst-diagnostics-{:02d}.tar.gz".format(index))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("bundle-" + str(index)).encode())
        os.utime(path, (index + 1, index + 1))
        return path

    def test_cleanup_check_is_strictly_read_only_and_lists_unknown(self):
        for i in range(7):
            self.bundle(i)
        unknown = self.engine.target(STATE_DIR + "/operator-notes.txt")
        unknown.write_text("never delete", encoding="utf-8")
        before = self.snapshot()
        result = ControllerCleanup(self.engine).check()
        self.assertEqual(result["final_status"], "ok")
        self.assertEqual(result["categories"]["diagnostic_bundles"]["prunable"], 2)
        self.assertTrue(any(x["path"].endswith("operator-notes.txt") for x in result["unknown"]))
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.system.actions, [])

    def test_cleanup_prunes_only_owned_bounded_diagnostics_and_preserves_unknown(self):
        paths = [self.bundle(i) for i in range(8)]
        unknown = self.engine.target(STATE_DIR + "/operator-notes.txt")
        unknown.write_text("never delete", encoding="utf-8")
        temp = self.engine.target(STATE_DIR + "/nst-package-stale.deb")
        temp.write_bytes(b"stale")
        result = ControllerCleanup(self.engine).execute()
        self.assertEqual(result["final_status"], "ok", result)
        remaining = list(self.engine.target(STATE_DIR + "/diagnostics").glob("nst-diagnostics-*.tar.gz"))
        self.assertEqual(len(remaining), KEEP_DIAGNOSTIC_BUNDLES)
        self.assertTrue(unknown.exists())
        self.assertFalse(temp.exists())
        self.assertTrue(any(x["path"].endswith("operator-notes.txt")
                            for x in result["cleanup"]["unknown_preserved"]))
        self.assertEqual(self.system.actions, [])

    def test_pending_blocks_pruning(self):
        for i in range(8):
            self.bundle(i)
        write_json(self.engine.pending_path, {"id": "pending", "component": "demo", "backup": None})
        before_bundles = [p.name for p in self.engine.target(STATE_DIR + "/diagnostics").iterdir()]
        result = ControllerCleanup(self.engine).execute()
        self.assertEqual(result["cleanup"]["status"], "deferred")
        self.assertEqual(before_bundles,
                         [p.name for p in self.engine.target(STATE_DIR + "/diagnostics").iterdir()])
        self.assertTrue(self.engine.pending_path.exists())

    def test_self_update_recovery_blocks_pruning(self):
        for i in range(8):
            self.bundle(i)
        marker = self.engine.target(STATE_DIR + "/self-update.json")
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("{}", encoding="utf-8")
        result = ControllerCleanup(self.engine).execute()
        self.assertEqual(result["cleanup"]["status"], "deferred")
        self.assertEqual(len(list(self.engine.target(STATE_DIR + "/diagnostics").iterdir())), 8)

    def test_cleanup_audit_failure_does_not_restore_deleted_safe_data(self):
        for i in range(8):
            self.bundle(i)
        original = self.engine.audit
        def fail(record):
            raise OSError("disk metadata write failed")
        self.engine.audit = fail
        result = ControllerCleanup(self.engine).execute()
        self.assertEqual(result["final_status"], "ok")
        self.assertIn("audit_warning", result)
        self.assertEqual(len(list(self.engine.target(STATE_DIR + "/diagnostics").glob("*.tar.gz"))),
                         KEEP_DIAGNOSTIC_BUNDLES)
        self.engine.audit = original


if __name__ == "__main__":
    unittest.main()
