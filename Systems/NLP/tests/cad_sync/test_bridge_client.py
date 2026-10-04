from __future__ import annotations

import json
from pathlib import Path

import pytest

from nl_project_2.cad_contract import CadReadRequest
from nl_project_2.cad_sync import AutoCadBridgeClient, BridgeError, BridgeTimeout
from nl_project_2.operations import StructuredLogger
from nl_project_2.runtime_resources import CAD_BRIDGE_MODE


def test_read_payload_preserves_new_contract_attributes_without_interpretation(monkeypatch):
    client = AutoCadBridgeClient()
    payload = {
        "document_identity": "fixture-dwg",
        "source_metadata": {"protocol_version": "fixture", "cable_type_conductors": {"UTP": 8}},
        "observations": [
            {
                "effective_name": "EL_BOX_OUT_100x100",
                "layer": "LIGHTING_230V",
                "raw_attributes": {
                    "DEVICE_TYPE": "EL_BOX",
                    "CABLE_ID": "301.RK1",
                    "OUT_1": "301.01",
                    "OUT_2": "",
                    "LED_TYPE": "",
                    "MOUNT_WAY": "В стене",
                    "GOFRA_ID": "",
                },
                "x": 10,
                "y": 20,
                "handle": "A10",
                "definition_tags": ["DEVICE_TYPE", "CABLE_ID", "OUT_1", "OUT_2"],
                "is_dynamic": False,
            }
        ],
    }
    monkeypatch.setattr(client, "_call", lambda request, deadline: payload)
    batch = client.read_observations(CadReadRequest("fixture-dwg", 1.0))
    attrs = {item.tag: item.value for item in batch.observations[0].raw_attributes}
    assert attrs["OUT_1"] == "301.01"
    assert attrs["MOUNT_WAY"] == "В стене"
    assert batch.source_metadata["cable_type_conductors"]["UTP"] == 8


def test_bridge_process_failure_is_controlled(tmp_path: Path):
    script = tmp_path / "fail_bridge.py"
    script.write_text("raise SystemExit('controlled bridge failure')\n", encoding="utf-8")
    client = AutoCadBridgeClient(script)
    with pytest.raises(BridgeError, match="controlled bridge failure"):
        client.read_observations(CadReadRequest("", 2.0))


def test_bridge_timeout_kills_short_lived_process(tmp_path: Path):
    script = tmp_path / "hang_bridge.py"
    script.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    client = AutoCadBridgeClient(script)
    with pytest.raises(BridgeTimeout):
        client.read_observations(CadReadRequest("", 0.2))


def test_frozen_bridge_starts_as_a_separate_executable_mode(monkeypatch, tmp_path: Path):
    import nl_project_2.runtime_resources as resources

    executable = tmp_path / "NLProject3.exe"
    monkeypatch.setattr(resources.sys, "frozen", True, raising=False)
    monkeypatch.setattr(resources.sys, "executable", str(executable))

    assert resources.sta_bridge_command(r"\\.\pipe\test") == [
        str(executable),
        CAD_BRIDGE_MODE,
        "--pipe",
        r"\\.\pipe\test",
    ]


def test_progress_identifies_timeout_stage_logs_safely_and_next_process_reconnects(
    tmp_path: Path,
):
    slow = tmp_path / "slow_bridge.py"
    slow.write_text(
        "from multiprocessing.connection import Listener\n"
        "import json,time\n"
        "import argparse\n"
        "p=argparse.ArgumentParser(); p.add_argument('--pipe',required=True); a=p.parse_args()\n"
        "with Listener(a.pipe,family='AF_PIPE') as listener:\n"
        " with listener.accept() as c:\n"
        "  c.recv_bytes()\n"
        "  c.send_bytes(json.dumps("
        "{'type':'progress','stage':'scan_modelspace_progress_250'}).encode())\n"
        "  time.sleep(60)\n",
        encoding="utf-8",
    )
    logger = StructuredLogger(tmp_path / "operations.jsonl")
    with pytest.raises(BridgeTimeout, match="scan_modelspace_progress_250"):
        AutoCadBridgeClient(slow, logger=logger).read_observations(
            CadReadRequest("C:/private/target.dwg", 0.4)
        )
    log = (tmp_path / "operations.jsonl").read_text(encoding="utf-8")
    events = [json.loads(line) for line in log.splitlines()]
    assert any(row["summary"].get("stage") == "scan_modelspace_progress_250" for row in events)
    assert any(row["result"] == "terminated" for row in events)
    assert "C:/private/target.dwg" not in log

    success = tmp_path / "success_bridge.py"
    success.write_text(
        "from multiprocessing.connection import Listener\n"
        "import json,argparse\n"
        "p=argparse.ArgumentParser(); p.add_argument('--pipe',required=True); a=p.parse_args()\n"
        "with Listener(a.pipe,family='AF_PIPE') as listener:\n"
        " with listener.accept() as c:\n"
        "  c.recv_bytes()\n"
        "  result={'document_identity':'C:/target.dwg','document_name':'target.dwg',"
        "'read_only':False,'saved':True,'dbmod':0}\n"
        "  c.send_bytes(json.dumps({'type':'response','ok':True,'result':result}).encode())\n",
        encoding="utf-8",
    )
    info = AutoCadBridgeClient(success).inspect_active_document(deadline_seconds=2)
    assert info.document_identity == "C:/target.dwg"
