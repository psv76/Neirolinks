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


@pytest.mark.parametrize("use_fingerprint", [True, False])
@pytest.mark.parametrize(
    "layer,name",
    [
        ("300_Light", "DALI_GROUP"),
        ("400_LED", "DALI_GROUP"),
        ("ARCH", "UNRELATED_BLOCK"),
        ("POWER", "SOCKET_IN"),
        ("350_X", "SOCKET_IN"),
        ("300_", "SOCKET_IN"),
    ],
)
def test_c7c_default_keeps_all_layers_on_both_read_paths(monkeypatch, use_fingerprint, layer, name):
    from nl_project_2.cad_sync.reconciliation_safety import is_authoritative_scan_metadata

    client = AutoCadBridgeClient()
    calls = []
    signature = f'("{name}" "{layer}" (10.0 20.0 0.0) :vlax-false () ())'

    def fake_call(request, _deadline):
        calls.append(request["operation"])
        assert "include_layer" not in request
        assert "layer_filter_applied" not in request
        if request["operation"] == "fingerprint":
            return _fingerprint_payload(signature if use_fingerprint else "unparseable")
        assert request["operation"] == "scan"
        payload = _scan_payload()
        payload["observations"][0].update(layer=layer, effective_name=name)
        return payload

    monkeypatch.setattr(client, "_call", fake_call)
    batch = client.read_observations(CadReadRequest("C:/fixture/working.dwg", 10.0))
    assert [item.layer for item in batch.observations] == [layer]
    assert batch.observations[0].effective_name == name
    assert is_authoritative_scan_metadata(batch.source_metadata)
    assert calls == (
        ["fingerprint", "fingerprint"]
        if use_fingerprint
        else ["fingerprint", "scan", "fingerprint"]
    )


def test_c7c_incremental_move_off_numeric_layer_keeps_insertion(monkeypatch):
    client = AutoCadBridgeClient()
    calls = []
    signatures = iter(["old", "old", "moved", "moved"])

    def fake_call(request, _deadline):
        operation = request["operation"]
        calls.append(operation)
        assert "include_layer" not in request
        if operation == "fingerprint":
            return _fingerprint_payload(next(signatures))
        payload = _scan_payload()
        if operation == "scan":
            payload["observations"][0]["layer"] = "100_Power"
        else:
            assert operation == "scan_handles"
            assert request["handles"] == ["A10"]
            payload["observations"][0]["layer"] = "ARCH"
        return payload

    monkeypatch.setattr(client, "_call", fake_call)
    request = CadReadRequest("C:/fixture/working.dwg", 10.0)
    client.read_observations(request)
    batch = client.read_observations(request)
    assert [(item.handle, item.layer) for item in batch.observations] == [("A10", "ARCH")]
    assert batch.source_metadata["incremental_mode"] == "DELTA"
    assert calls == [
        "fingerprint",
        "scan",
        "fingerprint",
        "fingerprint",
        "scan_handles",
        "fingerprint",
    ]


@pytest.mark.parametrize("mode", ["FILTERED_FINGERPRINT", "FILTERED_COM_FALLBACK"])
def test_explicit_filtered_read_preserves_presence_and_c6_gate(monkeypatch, mode):
    from types import SimpleNamespace

    from nl_project_2.cad_sync import DwgSyncError, DwgSyncService

    client = AutoCadBridgeClient()
    cached = object()
    client._cached_batch = cached
    calls = []

    def fake_call(request, _deadline):
        calls.append(request)
        assert request["operation"] == "scan_working_layers"
        assert request["tracked_handles"] == ["A10", "DEAD"]
        payload = _scan_payload()
        payload.update(
            read_id=request["read_id"],
            census_before={"A10": "ARCH", "B1": "350_X"},
            census_after={"A10": "ARCH", "B1": "350_X"},
            selected_handles=["A10"],
            tracked_handles=["A10", "DEAD"],
        )
        payload["observations"][0]["layer"] = "ARCH"
        payload["source_metadata"].update(
            layer_filter_applied=True,
            scan_is_complete_for_reconciliation=False,
            skipped_block_references=1,
            scan_mode=mode,
        )
        if mode == "FILTERED_FINGERPRINT":
            payload["handles"] = ["A10"]
            payload["signatures"] = {"A10": '("SOCKET_IN" "ARCH" (10 20 0) :vlax-false () ())'}
            del payload["observations"]
        return payload

    monkeypatch.setattr(client, "_call", fake_call)
    result = client.read_layer_filtered_observations(
        CadReadRequest("C:/fixture/working.dwg", 1), tracked_handles=("A10", "DEAD")
    )
    assert result.status == "REQUIRES_ATTENTION"
    assert result.present_excluded_handles == ("A10",)
    assert result.absent_unknown_handles == ("DEAD",)
    assert [(o.handle, o.layer) for o in result.batch.observations] == [("A10", "ARCH")]
    assert client._cached_batch is cached
    assert len(calls) == 1

    def forbidden(*args, **kwargs):
        pytest.fail("Diagnostic filtered read reached database")

    service = DwgSyncService(SimpleNamespace(connect=forbidden, begin=forbidden))
    with pytest.raises(DwgSyncError, match="SCAN_NOT_AUTHORITATIVE"):
        service.preview(project_id="synthetic", batch=result.batch)
    with pytest.raises(DwgSyncError, match="SCAN_NOT_AUTHORITATIVE"):
        service.apply_dwg_to_project(
            SimpleNamespace(batch=result.batch), selected_paths=(), confirmed=True
        )


@pytest.mark.parametrize(
    "fault",
    [
        "stale_read",
        "document",
        "census",
        "layer",
        "missing",
        "duplicate",
        "forged_authority",
        "selected",
        "tracked",
    ],
)
def test_explicit_filtered_read_rejects_bad_transport_evidence(monkeypatch, fault):
    client = AutoCadBridgeClient()

    def fake_call(request, _deadline):
        payload = _scan_payload()
        payload.update(
            read_id=request["read_id"],
            census_before={"A10": "POWER"},
            census_after={"A10": "POWER"},
            selected_handles=["A10"],
            tracked_handles=["A10"],
        )
        payload["source_metadata"].update(
            layer_filter_applied=True,
            scan_is_complete_for_reconciliation=False,
            skipped_block_references=0,
            scan_mode="FILTERED_COM_FALLBACK",
        )
        if fault == "stale_read":
            payload["read_id"] = "old"
        elif fault == "document":
            payload["document_identity"] = "other"
        elif fault == "census":
            payload["census_after"] = {}
        elif fault == "layer":
            payload["observations"][0]["layer"] = "ARCH"
        elif fault == "missing":
            payload["observations"] = []
        elif fault == "duplicate":
            payload["observations"] *= 2
        elif fault == "forged_authority":
            payload["source_metadata"]["scan_is_complete_for_reconciliation"] = True
        elif fault == "selected":
            payload["selected_handles"] = []
        elif fault == "tracked":
            payload["tracked_handles"] = []
        return payload

    monkeypatch.setattr(client, "_call", fake_call)
    with pytest.raises(BridgeError, match="FILTERED_READ_INVALID"):
        client.read_layer_filtered_observations(
            CadReadRequest("C:/fixture/working.dwg", 1), tracked_handles=("A10",)
        )


@pytest.mark.parametrize(
    "fault", [None, "read_id", "document", "incomplete", "filtered", "handle", "layer"]
)
def test_lightweight_census_transport_is_fresh_and_strict(monkeypatch, fault):
    from nl_project_2.cad_sync.bridge import AutoCadBridgeClient

    client = AutoCadBridgeClient()
    calls = []

    def fake_call(request, deadline):
        calls.append(request["operation"])
        payload = {
            "document_identity": "C:/fixture/working.dwg",
            "read_id": request["read_id"],
            "complete": True,
            "unfiltered": True,
            "census": {"A1": "ARCH", "B2": "300_DALI"},
        }
        if fault == "read_id":
            payload["read_id"] = "stale"
        elif fault == "document":
            payload["document_identity"] = "other.dwg"
        elif fault == "incomplete":
            payload["complete"] = False
        elif fault == "filtered":
            payload["unfiltered"] = False
        elif fault == "handle":
            payload["census"] = {"bad": "ARCH"}
        elif fault == "layer":
            payload["census"] = {"A1": None}
        return payload

    monkeypatch.setattr(client, "_call", fake_call)
    request = CadReadRequest("C:/fixture/working.dwg", 1)
    if fault:
        with pytest.raises(BridgeError, match="CENSUS_INVALID"):
            client.read_insert_census(request)
    else:
        assert client.read_insert_census(request) == (("A1", "ARCH"), ("B2", "300_DALI"))
    assert calls == ["insert_census"]
