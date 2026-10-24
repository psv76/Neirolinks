"""D19: compare supplied current CAD observations to accepted DWG/Project evidence.

No live AutoCAD adapter is executed here. A batch supplied by a caller is
untrusted input and can be replayed; even a perfect match is NOT a live file
attestation or authorization to publish a cable quantity.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING
from collections.abc import Mapping

from sqlalchemy import Connection, select

from nl_project_2.persistence.schema import (
    cable_point,
    cable_point_field_device,
    cable_topology_endpoint,
    dwg_document_binding,
    dwg_observation,
    dwg_scan,
    field_device,
)

if TYPE_CHECKING:
    from nl_project_2.cad_contract import CadObservationBatch
    from .transit_line_preview import TransitLineApproval
    from .transit_activation_readiness import TransitActivationRequest, TransitActivationPlan


@dataclass(frozen=True, slots=True)
class DwgScanLineageReview:
    cable_line_id: str
    status: str
    issues: tuple[str, ...]
    accepted_scan_id: str | None
    source_binding_id: str | None
    observed_handles: tuple[str, ...]
    compared_input_sha256: str | None
    accepted_observation_sha256: str | None
    # No caller can turn a supplied in-memory batch into authenticated live CAD.
    proves_live_dwg_freshness: bool = False
    authorizes_quantity_publication: bool = False


def _decimal(value: object) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return None
    return number if number.is_finite() else None


def _hash(data: object) -> str:
    serialized = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _geometry(x: object, y: object) -> tuple[Decimal | None, Decimal | None]:
    return _decimal(x), _decimal(y)


def compare_current_dwg_observations(
    connection: Connection,
    approval: TransitLineApproval,
    *,
    current_batch: CadObservationBatch | None,
    confirmed: bool = False,
) -> DwgScanLineageReview:
    """Strict selected-owner comparison; no DWG writes, no quantity source flip.

    `dwg_scan.content_sha256` hashes the whole historic CAD batch and cannot
    establish that a disk DWG is still identical. This verifier checks the
    exact accepted owner handles against an independently supplied batch.
    """
    ev = approval.transit
    issues: set[str] = set()
    if current_batch is None or not confirmed:
        return DwgScanLineageReview(
            ev.cable_line_id,
            "REVIEW",
            ("D19_CURRENT_CAD_SCAN_REQUIRED",),
            None,
            None,
            (),
            None,
            None,
        )

    # For this restricted stage the approved route must be a simple physical
    # BOX chain with one source and one target, as in D12–D18.
    if ev.route.status not in {"CANDIDATE", "MEASURED"} or not ev.route.spans:
        issues.add("D19_APPROVED_PHYSICAL_ROUTE_UNPROVEN")

    # Project accepted field-device ownership is the only safe handle map.
    accepted: dict[str, tuple[dict, str]] = {}
    boxes = list(
        connection.execute(
            select(field_device).where(
                field_device.c.project_id == ev.project_id,
                field_device.c.lifecycle == "ACTIVE",
                field_device.c.block_kind == "EL_BOX_OUT_100x100",
            )
        ).mappings()
    )
    for box_id, _x, _y, _height in ev.route.box_positions:
        matches = [
            row for row in boxes
            if str((row["normalized_fields_json"] or {}).get("BOX_ID") or "") == box_id
        ]
        if len(matches) != 1:
            issues.add("D19_ACCEPTED_BOX_OWNER_AMBIGUOUS")
            continue
        accepted[matches[0]["id"]] = (dict(matches[0]), f"BOX:{box_id}")

    endpoint_point_by_device: dict[str, str] = {}
    for endpoint_id, boundary in (
        (ev.source_endpoint_id, ev.route.spans[0].start),
        (ev.target_endpoint_id, ev.route.spans[-1].finish),
    ):
        endpoint = connection.execute(
            select(cable_topology_endpoint).where(
                cable_topology_endpoint.c.id == endpoint_id,
                cable_topology_endpoint.c.project_id == ev.project_id,
                cable_topology_endpoint.c.cable_line_id == ev.cable_line_id,
            )
        ).mappings().one_or_none()
        if endpoint is None or endpoint["endpoint_kind"] != "TOPOLOGY_POINT":
            issues.add("D19_ENDPOINT_CANONICAL_OWNER_MISSING")
            continue
        point = connection.execute(
            select(cable_point).where(
                cable_point.c.project_id == ev.project_id,
                cable_point.c.id == endpoint["cable_point_id"],
                cable_point.c.cable_line_id == ev.cable_line_id,
            )
        ).mappings().one_or_none()
        if point is None:
            issues.add("D19_ENDPOINT_CANONICAL_POINT_MISSING")
            continue
        if point["point_kind"] == "INTERNAL_SOURCE":
            continue
        members = list(
            connection.execute(
                select(field_device)
                .join(
                    cable_point_field_device,
                    cable_point_field_device.c.field_device_id == field_device.c.id,
                )
                .where(
                    cable_point_field_device.c.cable_point_id == point["id"],
                    cable_point_field_device.c.project_id == ev.project_id,
                    field_device.c.project_id == ev.project_id,
                    field_device.c.lifecycle == "ACTIVE",
                )
            ).mappings()
        )
        if len(members) != 1:
            issues.add("D19_ENDPOINT_DWG_OWNER_AMBIGUOUS")
            continue
        owner = dict(members[0])
        accepted[owner["id"]] = (owner, f"END:{boundary}")
        endpoint_point_by_device[owner["id"]] = boundary
    if not accepted:
        issues.add("D19_NO_DWG_OWNERS")

    binding_ids = {row["dwg_document_binding_id"] for row, _label in accepted.values()}
    if None in binding_ids or len(binding_ids) != 1:
        issues.add("D19_BINDING_OWNERSHIP_UNPROVEN")
    binding_id = next(iter(binding_ids)) if len(binding_ids) == 1 else None
    binding = None
    latest = None
    if binding_id is not None:
        binding = connection.execute(
            select(dwg_document_binding).where(
                dwg_document_binding.c.project_id == ev.project_id,
                dwg_document_binding.c.id == binding_id,
            )
        ).mappings().one_or_none()
        if (
            binding is None
            or binding["status"] != "CONFIRMED"
            or binding["document_signature"] != current_batch.document_identity
        ):
            issues.add("D19_CURRENT_DOCUMENT_BINDING_MISMATCH")
        latest = connection.execute(
            select(dwg_scan)
            .where(
                dwg_scan.c.project_id == ev.project_id,
                dwg_scan.c.dwg_document_binding_id == binding_id,
                dwg_scan.c.status == "ACCEPTED",
            )
            .order_by(dwg_scan.c.completed_at_utc.desc(), dwg_scan.c.id.desc())
        ).mappings().first()
        if latest is None or not latest["content_sha256"]:
            issues.add("D19_ACCEPTED_SCAN_LINEAGE_MISSING")

    observed = {}
    for observation in current_batch.observations:
        if observation.handle in observed:
            issues.add("D19_DUPLICATE_DWG_HANDLE")
        observed[observation.handle] = observation
    expected: dict[str, dict] = {}
    actual: dict[str, dict] = {}
    for row, boundary_kind in accepted.values():
        handle = str(row["entity_handle"] or "").strip()
        if not handle or handle in expected:
            issues.add("D19_ACCEPTED_DWG_HANDLE_AMBIGUOUS")
            continue
        if row["dwg_document_binding_id"] != binding_id:
            issues.add("D19_ACCEPTED_OWNER_BINDING_CHANGED")
        prior = None
        if latest is not None:
            prior = connection.execute(
                select(dwg_observation).where(
                    dwg_observation.c.project_id == ev.project_id,
                    dwg_observation.c.dwg_scan_id == latest["id"],
                    dwg_observation.c.entity_handle == handle,
                )
            ).mappings().one_or_none()
        if prior is None:
            issues.add("D19_OWNER_ABSENT_FROM_LAST_ACCEPTED_SCAN")
            continue
        obs = observed.get(handle)
        if obs is None:
            issues.add("D19_CURRENT_DWG_OWNER_MISSING")
            continue
        prior_attrs = dict(prior["raw_attributes_json"] or {})
        current_attrs = {attr.tag: attr.value for attr in obs.raw_attributes}
        prior_xy = _geometry(
            (prior["geometry_json"] or {}).get("x"),
            (prior["geometry_json"] or {}).get("y"),
        )
        actual_xy = _geometry(obs.x, obs.y)
        if None in (*prior_xy, *actual_xy):
            issues.add("D19_DWG_COORDINATES_INVALID")
        if (
            prior["effective_block_name"] != obs.effective_name
            or prior["layer_name"] != obs.layer
            or prior_attrs != current_attrs
            or prior_xy != actual_xy
        ):
            issues.add("D19_DWG_OWNER_OBSERVATION_CHANGED")
        if prior["diagnostics_json"] and any(
            item.get("blocks_acceptance") for item in prior["diagnostics_json"]
            if isinstance(item, dict)
        ):
            issues.add("D19_ACCEPTED_SCAN_HAS_BLOCKING_DIAGNOSTIC")

        fields = dict(row["normalized_fields_json"] or {})
        if boundary_kind.startswith("BOX:"):
            box_id = boundary_kind.split(":", 1)[1]
            box_coords = [
                (x, y, height)
                for name, x, y, height in ev.route.box_positions if name == box_id
            ]
            if (
                len(box_coords) != 1
                or actual_xy != _geometry(box_coords[0][0], box_coords[0][1])
                or _decimal(current_attrs.get("MOUNT_HEIGHT")) != _decimal(box_coords[0][2])
            ):
                issues.add("D19_APPROVED_BOX_GEOMETRY_DIFFERS_DWG")
            if (
                str(current_attrs.get("BOX_ID") or "") != box_id
                or str(current_attrs.get("CABLE_TRANSIT") or "")
                != str(fields.get("CABLE_TRANSIT") or "")
            ):
                issues.add("D19_APPROVED_BOX_ATTRIBUTES_DIFFER")
        else:
            boundary = endpoint_point_by_device.get(row["id"])
            location = ev.locations.get(boundary) if boundary else None
            if (
                location is None
                or actual_xy != (location.point.x_mm, location.point.y_mm)
                or _decimal(current_attrs.get("MOUNT_HEIGHT"))
                != location.point.mount_height_mm
            ):
                issues.add("D19_APPROVED_ENDPOINT_GEOMETRY_DIFFERS_DWG")
        expected[handle] = {
            "name": prior["effective_block_name"],
            "layer": prior["layer_name"],
            "x": str(prior_xy[0]),
            "y": str(prior_xy[1]),
            "attrs": prior_attrs,
        }
        actual[handle] = {
            "name": obs.effective_name,
            "layer": obs.layer,
            "x": str(actual_xy[0]),
            "y": str(actual_xy[1]),
            "attrs": current_attrs,
        }

    if not observed or len(expected) != len(accepted) or len(actual) != len(accepted):
        issues.add("D19_DWG_SELECTED_OWNER_COVERAGE_INCOMPLETE")
    return DwgScanLineageReview(
        cable_line_id=ev.cable_line_id,
        status="REVIEW" if issues else "HISTORICAL_LINEAGE_MATCH_ONLY",
        issues=tuple(sorted(issues)),
        accepted_scan_id=latest["id"] if latest is not None else None,
        source_binding_id=binding_id,
        observed_handles=tuple(sorted(actual)),
        compared_input_sha256=_hash(actual),
        accepted_observation_sha256=_hash(expected),
    )


@dataclass(frozen=True, slots=True)
class DwgTransitRevalidationPlan:
    """Selected-line D18 readiness plus supplied DWG comparisons."""

    status: str
    selected_line_ids: tuple[str, ...]
    activation_readiness: TransitActivationPlan
    dwg_comparisons: tuple[DwgScanLineageReview, ...]
    issues: tuple[str, ...]
    can_publish: bool = False


def plan_dwg_transit_revalidation(
    engine,
    requests: tuple[TransitActivationRequest, ...],
    *,
    selected_line_ids: frozenset[str],
    supplied_batches: Mapping[str, CadObservationBatch | None],
    confirmed: bool = False,
) -> DwgTransitRevalidationPlan:
    """Evaluate input CAD observations together with the D18 canonical gate.

    This does NOT attest where a supplied batch came from. Only the actual
    Windows AutoCAD bridge can produce independent source provenance later.
    """
    from .transit_activation_readiness import plan_transit_activation

    if set(supplied_batches) != selected_line_ids:
        raise ValueError("D19_CAD_BATCH_SELECTION_NOT_EXACT")
    readiness = plan_transit_activation(
        engine,
        requests,
        selected_line_ids=selected_line_ids,
        confirmed=confirmed,
    )
    reports: list[DwgScanLineageReview] = []
    with engine.connect() as connection:
        for request in sorted(requests, key=lambda item: item.approval.transit.cable_line_id):
            reports.append(
                compare_current_dwg_observations(
                    connection,
                    request.approval,
                    current_batch=supplied_batches[request.approval.transit.cable_line_id],
                    confirmed=confirmed,
                )
            )
    issues: set[str] = set()
    for entry in readiness.lines:
        issues.update(entry.issues)
    for review in reports:
        issues.update(review.issues)
    issues.add("D19_LIVE_CAD_BATCH_PROVENANCE_NOT_ATTESTED")
    issues.add("D19_ALL_QUANTITY_CONSUMERS_NOT_ACTIVATED")
    return DwgTransitRevalidationPlan(
        status="BLOCKED",
        selected_line_ids=readiness.selected_line_ids,
        activation_readiness=readiness,
        dwg_comparisons=tuple(reports),
        issues=tuple(sorted(issues)),
    )
