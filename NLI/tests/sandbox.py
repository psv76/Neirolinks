#!/usr/bin/env python3
"""Acceptance CLI with real pinned HHM Git blobs and a fake WB backend, never SSH."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nli.cli import main
from nli.core import Engine
from nli.firmware import Firmware
from nli.util import digest
from test_nli import FakeSystem

REPO = Path(__file__).resolve().parents[2]


def run(role):
    with tempfile.TemporaryDirectory(prefix="nli-sandbox-") as folder:
        root = Path(folder)
        def put(path, data):
            p = root / path.lstrip("/")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        manifest = json.loads((REPO / "NLI/examples" / ("hhm-" + role + "-3.0.json")).read_bytes())
        for f in manifest["files"]:
            data = subprocess.check_output(["git", "-C", str(REPO), "show", manifest["release"]["commit"] + ":" + f["source"]])
            put(f["target"], data)
            put("/payload/" + f["source"], data)
        raw = json.dumps(manifest).encode()
        put("/mnt/data/etc/neiro/nli/release.json", raw)
        ref = dict(path="/mnt/data/etc/neiro/nli/release.json", sha256=digest(raw))
        config = dict(object=manifest["object"], role=role, hostname="sandbox-wb", components={
            "hhm": dict(plugin="hhm", baseline=ref, target=ref, payload_dir="/payload", unmanaged_rules={})})
        system = FakeSystem()
        if role == "gazebo":
            system.frame.update(source="ivolga-besedka-504", v=2)
        engine = Engine(config, root, system)
        for command in (["status"], ["check", "hhm"], ["update", "hhm"], ["verify", "hhm"], ["rollback", "hhm"]):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                rc = main(command, engine=engine)
            print(role + " nli " + " ".join(command) + ": " + str(rc))
            assert rc == 0, output.getvalue()
        source = b"# sandbox only update-all recover-all"
        put("/usr/bin/wb-mcu-fw-updater", source)
        config["firmware"] = dict(approved_executable_sha256=digest(source), approved_package_version="1.99-test")
        result = Firmware(engine).execute("check")
        assert result["final_status"] == "unavailable", result
        print(role + " nli firmware check: unavailable (honest read-only result)")
        for action, summary in [("update", "1 upgraded, 0 skipped upgrade, 0 bootloader updates available, 0 stuck in bootloader, 0 disconnected, 0 foreign and 0 too old"),
                                ("recover", "1 recovered, 0 was already working, 0 not recovered and 0 not answered")]:
            result = Firmware(engine, lambda *args: (summary, 0)).execute(action)
            assert result["final_status"] == "ok", result
            print(role + " fake firmware " + action + ": ok")


if __name__ == "__main__":
    run("boiler")
    run("gazebo")
