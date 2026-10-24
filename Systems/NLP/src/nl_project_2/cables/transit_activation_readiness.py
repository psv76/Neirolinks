"""D18: read-only activation-readiness plan, not a production source switch.

D17 verifies approved Project quantities, but no D17 record proves a *current*
external DWG scan, real-end freshness, or revision-aware downstream consumers.
This gate makes the accepted Project input fingerprint auditable while always
refusing automatic publication until those independently tested contracts exist.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Connection, Engine, select

from nl_project_2.persistence.schema import (
    cable_point,
    cable_point_field_device,
    cable_topology_endpoint,
    dwg_document_binding,
    field_device,
)

if TYPE_CHECKING:
    from .transit_line_preview import TransitLineApproval


# Each of these is a live canonical consumer; D17 validates input but does not
# yet connect a source-selection/revocation contract to any of these paths.
_CANONICAL_CONSUMERS = (
    "cables.recalculation.recalculate_segments",
    "cables.service.effective_length",
    "cables.service.line_cards",
    "specification.service._effective_cable_length",
    "specification.service._cable_sources",
    "cables.service.auto_select_hdmi",
    "cables.service.select_hdmi_manually",
    "cables.service.select_speaker_product",
    "cables.service.hdmi_selection_status",
)

_UNMET_RELEASE_GATES = (
    "D18_CAD_LIVE_SCAN_AND_ROUNDTRIP_NOT_VERIFIED",
    "D18_TERMINATION_SOURCE_FRESHNESS_NOT_VERIFIED",
    "D18_CANONICAL_RECALCULATION_SOURCE_SWITCH_NOT_IMPLEMENTED",
    "D18_ALL_QUANTITY_CONSUMERS_NOT_REVISION_AWARE",
    "D18_CONDUIT_ORDINARY_BUS_SHARED_OWNER_NOT_VERIFIED",
    "D18_LIVE_ACCEPTANCE_AND_RESTORE_NOT_PERFORMED",
)


@dataclass(frozen=True, slots=True)
class TransitActivationRequest:
    approval: TransitLineApproval
    d16_batch_sha256: str


@dataclass(frozen=True, slots=True)
class TransitLineActivationReadiness:
    cable_line_id: str
    status: str
    issues: tuple[str, ...]
    project_source_sha256: str
    project_source_device_count: int
    project_source_binding_count: int
    prepared_final_m: Decimal | None
    legacy_calculated_m: Decimal | None
    # Readiness does not make this amount usable by an existing specification.
    authoritative_cable_m: None = None
    authoritative_conduit_m: None = None


@dataclass(frozen=True, slots=True)
class TransitActivationPlan:
    status: str
    selected_line_ids: tuple[str, ...]
    plan_sha256: str
    lines: tuple[TransitLineActivationReadiness, ...]
    outstanding_consumers: tuple[str, ...] = _CANONICAL_CONSUMERS
    # There is deliberately no apply/commit activation operation in D18.
    can_publish: bool = False


def _digest(payload: object) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _record(row) -> dict:
    """Stable accepted Project evidence; never asserts DWG freshness."""
    return {
        "id": row["id"],
        "row_version": row["row_version"],
        "project_id": row["project_id"],
        "kind": row["block_kind"],
        "room_id": row["room_id"],
        "fields": row["normalized_fields_json"],
        "binding_id": row["dwg_document_binding_id"],
        "handle": row["entity_handle"],
        "lifecycle": row["lifecycle"],
    }


def _accepted_project_source(
    connection: Connection, request: TransitActivationRequest
) -> tuple[str, int, int, tuple[str, ...]]:
    ev = request.approval.transit
    issues: set[str] = set()
    members: dict[str, dict] = {}
    end_points: list[dict] = []
    for endpoint_id in (ev.source_endpoint_id, ev.target_endpoint_id):
        endpoint = (
            connection.execute(
                select(cable_topology_endpoint).where(
                    cable_topology_endpoint.c.project_id == ev.project_id,
                    cable_topology_endpoint.c.id == endpoint_id,
                    cable_topology_endpoint.c.cable_line_id == ev.cable_line_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if endpoint is None:
            issues.add("D18_CANONICAL_ENDPOINT_MISSING")
            continue
        record = {
            "endpoint_id": endpoint["id"],
            "kind": endpoint["endpoint_kind"],
            "row_version": endpoint["row_version"],
            "point_id": endpoint["cable_point_id"],
            "port_id": endpoint["field_port_id"],
            "resource_id": endpoint["instance_resource_id"],
        }
        point_id = endpoint["cable_point_id"]
        if point_id is not None:
            point = (
                connection.execute(
                    select(cable_point).where(
                        cable_point.c.project_id == ev.project_id,
                        cable_point.c.id == point_id,
                        cable_point.c.cable_line_id == ev.cable_line_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if point is None:
                issues.add("D18_CANONICAL_POINT_MISSING")
            else:
                record["point"] = {
                    "id": point["id"],
                    "logical_identity": point["logical_identity"],
                    "point_kind": point["point_kind"],
                    "origin_kind": point["origin_kind"],
                    "migration_state": point["migration_state"],
                    "location_json": point["location_json"],
                    "dwg_observation_id": point["dwg_observation_id"],
                    "row_version": point["row_version"],
                }
                member_ids = list(
                    connection.execute(
                        select(cable_point_field_device.c.field_device_id).where(
                            cable_point_field_device.c.project_id == ev.project_id,
                            cable_point_field_device.c.cable_point_id == point_id,
                        )
                    ).scalars()
                )
                record["field_device_ids"] = sorted(member_ids)
                if member_ids:
                    for row in connection.execute(
                        select(field_device).where(
                            field_device.c.project_id == ev.project_id,
                            field_device.c.id.in_(member_ids),
                        )
                    ).mappings():
                        members[row["id"]] = _record(row)
                        if row["lifecycle"] != "ACTIVE":
                            issues.add("D18_FIELD_DEVICE_NOT_ACTIVE")
        end_points.append(record)

    # Physical boxes are only waypoints, not electrical endpoints. Their
    # Project facts may be hashed, but this does not prove the DWG is current.
    boxes = list(
        connection.execute(
            select(field_device).where(
                field_device.c.project_id == ev.project_id,
                field_device.c.block_kind == "EL_BOX_OUT_100x100",
                field_device.c.lifecycle == "ACTIVE",
            )
        ).mappings()
    )
    for box_id, *_unused in ev.route.box_positions:
        matches = [
            row
            for row in boxes
            if str((row["normalized_fields_json"] or {}).get("BOX_ID") or "") == box_id
        ]
        if len(matches) != 1:
            issues.add("D18_PHYSICAL_BOX_OWNER_AMBIGUOUS")
        for row in matches:
            members[row["id"]] = _record(row)

    binding_ids = {row["binding_id"] for row in members.values() if row["binding_id"] is not None}
    bindings = [
        {
            "id": row["id"],
            "row_version": row["row_version"],
            "fingerprint": row["fingerprint"],
            "document_signature": row["document_signature"],
            "status": row["status"],
        }
        for row in connection.execute(
            select(dwg_document_binding).where(
                dwg_document_binding.c.project_id == ev.project_id,
                dwg_document_binding.c.id.in_(binding_ids),
            )
        ).mappings()
    ]
    if len(bindings) != len(binding_ids):
        issues.add("D18_ACCEPTED_DOCUMENT_BINDING_MISSING")
    if not binding_ids:
        issues.add("D18_DWG_DOCUMENT_BINDING_UNPROVEN")
    if len(binding_ids) > 1:
        issues.add("D18_MULTIPLE_DOCUMENT_BINDINGS_REQUIRE_REVIEW")
    payload = {
        "contract": "NLP_D18_ACCEPTED_PROJECT_SOURCE_V1",
        "project_id": ev.project_id,
        "cable_line_id": ev.cable_line_id,
        "box_ids": sorted(item[0] for item in ev.route.box_positions),
        "endpoints": sorted(end_points, key=lambda x: x["endpoint_id"]),
        "devices": [members[key] for key in sorted(members)],
        "bindings": sorted(bindings, key=lambda x: x["id"]),
    }
    return _digest(payload), len(members), len(binding_ids), tuple(sorted(issues))


def plan_transit_activation(
    engine: Engine,
    requests: tuple[TransitActivationRequest, ...],
    *,
    selected_line_ids: frozenset[str],
    confirmed: bool = False,
) -> TransitActivationPlan:
    """Produce a bounded, read-only plan. It has NO activation action.

    A project-state SHA and D16 batch SHA are *not* live DWG attestation.
    A subsequent stage must implement an independent accepted scan/roundtrip
    and consumer source switch before any action can publish these metres.
    """
    from .transit_canonical_readback import review_prepared_transit_for_canonical

    if not selected_line_ids or len(requests) != len(selected_line_ids):
        raise ValueError("D18_SELECTION_NOT_EXACT")
    owners = [req.approval.transit.cable_line_id for req in requests]
    if len(set(owners)) != len(owners) or set(owners) != selected_line_ids:
        raise ValueError("D18_SELECTION_NOT_EXACT")
    if len({req.approval.transit.project_id for req in requests}) != 1:
        raise ValueError("D18_SELECTION_MIXED_PROJECTS")
    results: list[TransitLineActivationReadiness] = []
    with engine.connect() as connection:
        for req in sorted(requests, key=lambda x: x.approval.transit.cable_line_id):
            check = review_prepared_transit_for_canonical(
                connection,
                req.approval,
                expected_batch_sha256=req.d16_batch_sha256,
                confirmed=confirmed,
            )
            state_sha, device_count, binding_count, source_issues = _accepted_project_source(
                connection, req
            )
            reasons = set(_UNMET_RELEASE_GATES) | set(source_issues)
            if check.status != "VERIFIED_READBACK_ONLY":
                reasons.add("D18_D17_READBACK_REQUIRES_REVIEW")
                reasons.update(check.issues)
            results.append(
                TransitLineActivationReadiness(
                    cable_line_id=req.approval.transit.cable_line_id,
                    status="BLOCKED",
                    issues=tuple(sorted(reasons)),
                    project_source_sha256=state_sha,
                    project_source_device_count=device_count,
                    project_source_binding_count=binding_count,
                    prepared_final_m=check.prepared_final_m,
                    legacy_calculated_m=check.legacy_calculated_m,
                )
            )
    selected = tuple(sorted(selected_line_ids))
    plan_digest = _digest(
        {
            "contract": "NLP_D18_READONLY_ACTIVATION_PLAN_V1",
            "selected": selected,
            "confirmed": confirmed,
            "lines": [
                {
                    "line": row.cable_line_id,
                    "source_sha256": row.project_source_sha256,
                    "d16_batch_sha256": next(
                        req.d16_batch_sha256
                        for req in requests
                        if req.approval.transit.cable_line_id == row.cable_line_id
                    ),
                    "issues": row.issues,
                }
                for row in results
            ],
        }
    )
    return TransitActivationPlan("BLOCKED", selected, plan_digest, tuple(results))
