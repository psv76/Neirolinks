import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nli.manifest import validate
from nli.plugins import HHM


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PackageTests(unittest.TestCase):
    def test_examples_validate_and_pins_match_git_blobs(self):
        for role in ("boiler", "gazebo"):
            path = ROOT / "examples" / ("hhm-" + role + "-3.0.json")
            data = path.read_bytes()
            m = validate(json.loads(data))
            HHM().validate(m, {})
            config = json.loads((ROOT / "examples" / ("config-" + role + ".json")).read_bytes())
            self.assertEqual(config["components"]["hhm"]["target"]["sha256"], hashlib.sha256(data).hexdigest())
            for entry in m["files"]:
                blob = subprocess.check_output(["git", "-C", str(ROOT.parent), "show",
                                                m["release"]["commit"] + ":" + entry["source"]])
                self.assertEqual(hashlib.sha256(blob).hexdigest(), entry["sha256"])
        validate(json.loads((ROOT / "examples/notifications.json").read_bytes()))

    def test_deb_reproducible_layout_modes_no_service_hooks(self):
        tool = load_tool("build_deb")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "nli.deb"
            tool.build(path)
            data = path.read_bytes()
            tool.build(path)
            self.assertEqual(data, path.read_bytes())
            self.assertTrue(data.startswith(b"!<arch>\n"))
            members = {}
            pos = 8
            while pos < len(data):
                header = data[pos:pos + 60]
                size = int(header[48:58])
                name = header[:16].decode().strip().rstrip("/")
                members[name] = data[pos + 60:pos + 60 + size]
                pos += 60 + size + size % 2
            self.assertEqual(members["debian-binary"], b"2.0\n")
            with tarfile.open(fileobj=io.BytesIO(members["control.tar.gz"]), mode="r:gz") as tar:
                self.assertEqual(set(tar.getnames()), {"./control"})
            with tarfile.open(fileobj=io.BytesIO(members["data.tar.gz"]), mode="r:gz") as tar:
                for item in tar.getmembers():
                    for parent in PurePosixPath(item.name).parents:
                        if str(parent) != ".":
                            self.assertTrue(tar.getmember("./" + str(parent)).isdir(), str(parent))
                self.assertEqual(tar.getmember("./usr/bin/nli").mode, 0o755)
                self.assertIn("./usr/lib/neiro-nli/nli/core.py", tar.getnames())
                for name in ("default-config.json", "manifest.schema.json", "WB_SMOKE.md",
                             "examples/config-boiler.json", "examples/hhm-boiler-3.0.json"):
                    self.assertIn("./usr/share/neiro-nli/" + name, tar.getnames())
                self.assertFalse(any(p.startswith(("./etc", "./mnt", "./var")) for p in tar.getnames()))
                self.assertFalse(any("507" in p or "systemd" in p for p in tar.getnames()))


if __name__ == "__main__":
    unittest.main()
