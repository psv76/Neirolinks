"""NST 1.0 persistent platform metadata compatibility."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_core as fixtures
from nst.layout import DATA_DIR, STATE_DIR
from nst.platform import PLATFORM_STATE, default_platform_state, load_platform_state, save_platform_state
from nst.util import Error


class PlatformStateTests(fixtures.Fixture):
    def test_status_default_is_read_only_and_creates_no_platform_file(self):
        before = self.snapshot()
        result = self.engine.read_operation("status")
        self.assertEqual(result["platform"], default_platform_state())
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.engine.target(PLATFORM_STATE).exists())

    def test_explicit_platform_state_roundtrip_uses_preserved_state_root(self):
        value = {
            "schema": 1,
            "controller": {"serial": "ABF62SL"},
            "registry": {"commit": "1" * 40},
            "deployment": {"sha256": "2" * 64},
            "desired_state": {"status": "exact"},
        }
        save_platform_state(self.engine, value)
        self.assertEqual(load_platform_state(self.engine), value)
        self.assertTrue(self.engine.target(PLATFORM_STATE).as_posix().endswith("mnt/data/var/lib/neirolinks/nst/platform.json"))

    def test_legacy_packaged_payload_dir_resolves_to_nst_data_without_rewriting_config(self):
        registration = self.config["components"][self.component]
        registration["payload_dir"] = "/usr/share/neiro-nli/payload"
        source = self.new["files"][0]["source"]
        self.put(DATA_DIR + "/payload/" + source, b"new")
        before = self.snapshot()

        payload = self.engine.payload(self.new)

        self.assertEqual(payload[self.new["files"][0]["target"]], b"new")
        self.assertEqual(registration["payload_dir"], "/usr/share/neiro-nli/payload")
        self.assertEqual(before, self.snapshot())

    def test_platform_schema_rejects_unknown_fields(self):
        value = default_platform_state()
        value["future_without_schema_bump"] = {}
        with self.assertRaisesRegex(Error, "fields"):
            save_platform_state(self.engine, value)


if __name__ == "__main__":
    unittest.main()
