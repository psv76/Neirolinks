"""D20: strict forced-full bridge witness and D19+D18 no-publication integration."""

from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import select, update
from test_bridge_client import _fingerprint_payload, _scan_payload
from test_issue237_d16_quantity_prepare import _intent, _prepare
from test_issue237_d19_dwg_scan_lineage import _batch_now

from nl_project_2.cad_contract import CadReadRequest
from nl_project_2.cad_sync.bridge import AutoCadBridgeClient, BridgeError
from nl_project_2.cables.service import CableService
from nl_project_2.cables.transit_activation_readiness import TransitActivationRequest
from nl_project_2.persistence.schema import field_device


_DWG = "C:/fixture/working.dwg"
_SIG = (
    '("SOCKET_IN" "POWER" (10.0 20.0 0.0) :vlax-false '
    '(("CABLE_ID" "101") ("LOAD_NAME" "Old")) '
    '("CABLE_ID" "LOAD_NAME"))'
)


def _doc(*, saved=True, dbmod=0, identity=_DWG):
    return {
        "document_identity": identity,
        "document_name": "working.dwg",
        "read_only": False,
        "saved": saved,
        "dbmod": dbmod,
    }


def _bridge(monkeypatch, *, saved=True, dbmod=0, changed=False, mismatch=False):
    bridge = AutoCadBridgeClient()
    calls = []
    fp_calls = 0

    def call(request, _deadline):
        nonlocal fp_calls
        operation = request["operation"]
        calls.append(operation)
        if operation == "document_identity":
            return _doc(saved=saved, dbmod=dbmod)
        if operation == "fingerprint":
            fp_calls += 1
            return _fingerprint_payload(
                _SIG if not changed or fp_calls == 1 else _SIG.replace('"Old"', '"Changed"')
            )
        if operation == "scan":
            return _scan_payload(load_name="Wrong" if mismatch else "Old")
        raise AssertionError(operation)

    monkeypatch.setattr(bridge, "_call", call)
    return bridge, calls


def test_fresh_bridge_forces_scan_and_independent_bracketing_not_cache(monkeypatch):
    bridge, calls = _bridge(monkeypatch)
    # A corrupt/stale incremental cache must not be used for D20.
    bridge._cached_batch = "stale"  # type: ignore[assignment]
    bridge._cached_order = ("OLD",)
    bridge._cached_signatures = {"OLD": "stale"}
    witness = bridge.read_fresh_observations_with_witness(
        CadReadRequest(_DWG, 8.0, definition_names=("SOCKET_IN",))
    )
    assert calls == [
        "document_identity",
        "fingerprint",
        "scan",
        "fingerprint",
        "document_identity",
    ]
    assert witness.scan_mode == "FORCED_FULL_SCAN"
    assert witness.batch.source_metadata["incremental_mode"] == "FORCED_FULL_SCAN"
    assert witness.batch.source_metadata["d20_source_status"] == "BRIDGE_STABLE_IN_MEMORY_ONLY"
    assert len(witness.fingerprint_sha256) == 64
    assert witness.dbmod == 0
    assert witness.document_saved
    assert not witness.proves_durable_file_identity
    assert bridge._cached_batch is None


@pytest.mark.parametrize(
    "mode,issue",
    [
        ("dirty", "D20_DOCUMENT_NOT_SAVED_OR_WRONG_OWNER"),
        ("unsaved", "D20_DOCUMENT_NOT_SAVED_OR_WRONG_OWNER"),
        ("changing", "D20_DOCUMENT_OR_FINGERPRINT_CHANGED_DURING_READ"),
        ("scan_mismatch", "D20_SCAN_DISAGREES_WITH_INDEPENDENT_FINGERPRINT"),
    ],
)
def test_bridge_scan_dirty_or_changed_or_not_equal_fingerprint_fails_closed(
    monkeypatch, mode, issue
):
    bridge, _calls = _bridge(
        monkeypatch,
        saved=mode != "unsaved",
        dbmod=1 if mode == "dirty" else 0,
        changed=mode == "changing",
        mismatch=mode == "scan_mismatch",
    )
    with pytest.raises(BridgeError, match=issue):
        bridge.read_fresh_observations_with_witness(
            CadReadRequest(_DWG, 8.0, definition_names=("SOCKET_IN",))
        )


def test_missing_identity_rejected_without_talking_to_bridge(monkeypatch):
    bridge, calls = _bridge(monkeypatch)
    with pytest.raises(BridgeError, match="D20_EXPLICIT_DOCUMENT_IDENTITY_REQUIRED"):
        bridge.read_fresh_observations_with_witness(CadReadRequest("", 8.0))
    assert calls == []


def _cad_bridge_for_batch(monkeypatch, batch, *, after_scan=None):
    bridge = AutoCadBridgeClient()
    calls = []

    def quoted(value):
        return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'

    signatures = {}
    observations = []
    for obs in batch.observations:
        attrs = {attr.tag: attr.value for attr in obs.raw_attributes}
        attrs_sig = " ".join(f"({quoted(k)} {quoted(v)})" for k, v in attrs.items())
        tags = " ".join(quoted(k) for k in attrs)
        signature = (
            f"({quoted(obs.effective_name)} {quoted(obs.layer)} "
            f"({obs.x} {obs.y} 0.0) :vlax-false ({attrs_sig}) ({tags}))"
        )
        signatures[obs.handle] = signature
        observations.append(
            {
                "effective_name": obs.effective_name,
                "layer": obs.layer,
                "raw_attributes": attrs,
                "x": obs.x,
                "y": obs.y,
                "handle": obs.handle,
                "definition_tags": list(attrs),
                "is_dynamic": False,
            }
        )

    def call(request, _deadline):
        operation = request["operation"]
        calls.append(operation)
        if operation == "document_identity":
            return _doc(identity=batch.document_identity)
        if operation == "fingerprint":
            return {
                "document_identity": batch.document_identity,
                "handles": [obs.handle for obs in batch.observations],
                "signatures": signatures,
                "source_metadata": {"adapter_version": "synthetic", "dbmod": 0},
            }
        if operation == "scan":
            if after_scan is not None:
                after_scan()
            return {
                "document_identity": batch.document_identity,
                "source_metadata": {"protocol_version": "synthetic"},
                "observations": observations,
            }
        raise AssertionError(request)

    monkeypatch.setattr(bridge, "_call", call)
    return bridge, calls


def test_d20_composes_fresh_scan_and_d19_but_never_publishes(database, monkeypatch):
    intent = _intent(database)
    (prepared,) = _prepare(database, intent)
    ev = intent.approval.transit
    batch = _batch_now()
    bridge, calls = _cad_bridge_for_batch(monkeypatch, batch)
    result = CableService(database.engine).review_live_transit_from_bridge(
        bridge,
        (TransitActivationRequest(intent.approval, prepared.approved_sha256),),
        selected_line_ids=frozenset({ev.cable_line_id}),
        expected_document_identity=batch.document_identity,
        confirmed=True,
    )
    assert result.status == "BLOCKED"
    assert not result.can_publish
    assert not result.proves_disk_dwg_freshness
    assert result.scan_mode == "FORCED_FULL_SCAN"
    assert len(result.full_scan_fingerprint_sha256) == 64
    assert "D20_DISK_DWG_SOURCE_PROVENANCE_NOT_ESTABLISHED" in result.issues
    assert "D20_CANONICAL_SOURCE_ACTIVATION_NOT_IMPLEMENTED" in result.issues
    assert "D19_APPROVED_ENDPOINT_GEOMETRY_DIFFERS_DWG" in result.issues
    assert not result.composed.can_publish
    assert calls == [
        "document_identity",
        "fingerprint",
        "scan",
        "fingerprint",
        "document_identity",
    ]


def test_project_mutation_while_bridge_scans_is_reviewed(database, monkeypatch):
    intent = _intent(database)
    (prepared,) = _prepare(database, intent)
    ev = intent.approval.transit

    def change_project():
        with database.engine.begin() as connection:
            row = connection.execute(
                select(field_device).where(
                    field_device.c.project_id == ev.project_id,
                    field_device.c.block_kind == "EL_BOX_OUT_100x100",
                )
            ).mappings().one()
            fields = dict(row["normalized_fields_json"])
            fields["DEVICE_NAME"] = "changed while scanning"
            connection.execute(
                update(field_device)
                .where(field_device.c.id == row["id"])
                .values(
                    normalized_fields_json=fields,
                    row_version=field_device.c.row_version + 1,
                )
            )

    bridge, _calls = _cad_bridge_for_batch(monkeypatch, _batch_now(), after_scan=change_project)
    result = CableService(database.engine).review_live_transit_from_bridge(
        bridge,
        (TransitActivationRequest(intent.approval, prepared.approved_sha256),),
        selected_line_ids=frozenset({ev.cable_line_id}),
        expected_document_identity=_batch_now().document_identity,
        confirmed=True,
    )
    assert "D20_PROJECT_CHANGED_DURING_CAD_SCAN" in result.issues
    assert result.status == "BLOCKED"
    assert not result.can_publish


def test_unconfirmed_or_wrong_client_is_rejected_before_cad_scan(database, monkeypatch):
    intent = _intent(database)
    (prepared,) = _prepare(database, intent)
    bridge, calls = _cad_bridge_for_batch(monkeypatch, _batch_now())
    kwargs = {
        "selected_line_ids": frozenset({intent.approval.transit.cable_line_id}),
        "expected_document_identity": _batch_now().document_identity,
    }
    from nl_project_2.cables.transit_live_bridge_gate import review_transit_from_active_bridge

    with pytest.raises(ValueError, match="D20_EXPLICIT_SELECTION_CONFIRMATION_REQUIRED"):
        review_transit_from_active_bridge(
            database.engine,
            bridge,
            (TransitActivationRequest(intent.approval, prepared.approved_sha256),),
            definition_names=("TRACK_DALI",),
            confirmed=False,
            **kwargs,
        )
    with pytest.raises(ValueError, match="D20_REAL_BRIDGE_CLIENT_REQUIRED"):
        review_transit_from_active_bridge(
            database.engine,
            object(),  # type: ignore[arg-type]
            (TransitActivationRequest(intent.approval, prepared.approved_sha256),),
            definition_names=("TRACK_DALI",),
            confirmed=True,
            **kwargs,
        )
    assert calls == []
