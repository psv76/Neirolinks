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


def _scan_payload(*, load_name: str = "Old"):
    return {
        "document_identity": "C:/fixture/working.dwg",
        "source_metadata": {"protocol_version": "1.1"},
        "observations": [
            {
                "effective_name": "SOCKET_IN",
                "layer": "POWER",
                "raw_attributes": {
                    "CABLE_ID": "101",
                    "LOAD_NAME": load_name,
                },
                "x": 10,
                "y": 20,
                "handle": "A10",
                "definition_tags": ["CABLE_ID", "LOAD_NAME"],
                "is_dynamic": False,
            }
        ],
    }


def _fingerprint_payload(signature: str):
    return {
        "document_identity": "C:/fixture/working.dwg",
        "handles": ["A10"],
        "signatures": {"A10": signature},
        "source_metadata": {
            "protocol_version": "1.1",
            "adapter_version": "1.1",
            "dbmod": 1,
        },
    }


def test_repeat_read_uses_fingerprint_cache_without_full_rescan(monkeypatch):
    client = AutoCadBridgeClient()
    calls = []

    def fake_call(request, _deadline):
        calls.append(request["operation"])
        if request["operation"] == "scan":
            return _scan_payload()
        if request["operation"] == "fingerprint":
            return _fingerprint_payload("sig-1")
        raise AssertionError(request)

    monkeypatch.setattr(client, "_call", fake_call)
    request = CadReadRequest("C:/fixture/working.dwg", 10.0)

    first = client.read_observations(request)
    second = client.read_observations(request)

    assert calls == ["fingerprint", "scan", "fingerprint", "fingerprint"]
    assert first.observations == second.observations
    assert second.source_metadata["incremental_mode"] == "CACHE_HIT"


def test_changed_handle_reads_only_delta_and_verifies_snapshot(monkeypatch):
    client = AutoCadBridgeClient()
    calls = []
    fingerprints = iter(
        (
            _fingerprint_payload("sig-1"),
            _fingerprint_payload("sig-1"),
            _fingerprint_payload("sig-2"),
            _fingerprint_payload("sig-2"),
        )
    )

    def fake_call(request, _deadline):
        calls.append(request["operation"])
        if request["operation"] == "scan":
            return _scan_payload()
        if request["operation"] == "fingerprint":
            return next(fingerprints)
        if request["operation"] == "scan_handles":
            assert request["handles"] == ["A10"]
            return _scan_payload(load_name="Changed")
        raise AssertionError(request)

    monkeypatch.setattr(client, "_call", fake_call)
    request = CadReadRequest("C:/fixture/working.dwg", 10.0)

    client.read_observations(request)
    changed = client.read_observations(request)

    assert calls == [
        "fingerprint",
        "scan",
        "fingerprint",
        "fingerprint",
        "scan_handles",
        "fingerprint",
    ]
    attrs = {item.tag: item.value for item in changed.observations[0].raw_attributes}
    assert attrs["LOAD_NAME"] == "Changed"
    assert changed.source_metadata["incremental_mode"] == "DELTA"
    assert changed.source_metadata["incremental_changed_handles"] == 1


def test_full_scan_rejects_snapshot_if_dwg_changes_while_reading(monkeypatch):
    client = AutoCadBridgeClient()
    fingerprints = iter(
        (
            _fingerprint_payload("sig-before"),
            _fingerprint_payload("sig-after"),
        )
    )

    def fake_call(request, _deadline):
        if request["operation"] == "fingerprint":
            return next(fingerprints)
        if request["operation"] == "scan":
            return _scan_payload()
        raise AssertionError(request)

    monkeypatch.setattr(client, "_call", fake_call)

    with pytest.raises(BridgeError, match="changed while full observations were being read"):
        client.read_observations(CadReadRequest("C:/fixture/working.dwg", 10.0))

    assert client._cached_batch is None
    assert client._cached_signatures is None
    assert client._cached_order is None


def test_cold_read_builds_observations_from_fingerprint_without_full_scan(monkeypatch):
    client = AutoCadBridgeClient()
    calls = []
    signature = (
        '("SOCKET_IN" "POWER" (10.0 20.0 0.0) :vlax-false '
        '(("CABLE_ID" "101") ("LOAD_NAME" "General sockets")) '
        '("CABLE_ID" "LOAD_NAME"))'
    )

    def fake_call(request, _deadline):
        calls.append(request["operation"])
        if request["operation"] == "fingerprint":
            return _fingerprint_payload(signature)
        raise AssertionError(request)

    monkeypatch.setattr(client, "_call", fake_call)
    request = CadReadRequest(
        "C:/fixture/working.dwg",
        10.0,
        definition_names=("SOCKET_IN",),
    )

    batch = client.read_observations(request)

    assert calls == ["fingerprint", "fingerprint"]
    assert len(batch.observations) == 1
    observation = batch.observations[0]
    assert observation.effective_name == "SOCKET_IN"
    assert observation.layer == "POWER"
    assert observation.handle == "A10"
    assert observation.x == 10.0
    assert observation.y == 20.0
    attrs = {item.tag: item.value for item in observation.raw_attributes}
    assert attrs == {"CABLE_ID": "101", "LOAD_NAME": "General sockets"}
    assert observation.definition.attribute_definition_tags == ("CABLE_ID", "LOAD_NAME")
    assert observation.definition.is_dynamic is False
    assert batch.source_metadata["incremental_mode"] == "FINGERPRINT_COLD"
