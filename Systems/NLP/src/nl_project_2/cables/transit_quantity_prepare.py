"""D16: atomic, selective, approved preparation of *non-authoritative* line totals.

There is no writer to cable_length_fact, electrical CableSegment, Conduit or DWG.
This is an auditable application receipt for subsequent, independently gated
canonical quantity integration (D15 approval alone cannot safely do that).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlalchemy import Engine, select

from nl_project_2.cables.transit_line_preview import (
    TransitLineApproval,
    preview_transit_line,
    transit_line_approval_sha256,
)
from nl_project_2.cad_sync.transit_physical_store import _json_ready
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    cable_length_fact,
    cable_line,
    cable_segment,
    cable_transit_line_commit,
    cable_transit_route,
)


class TransitQuantityPreparationError(RuntimeError):
    """No partial physical line quantity changes are allowed."""


@dataclass(frozen=True, slots=True)
class TransitQuantityIntent:
    approval: TransitLineApproval
    expected_line_row_version: int
    expected_length_fact_id: str | None
    expected_length_fact_row_version: int | None
    acceptance_evidence: str


@dataclass(frozen=True, slots=True)
class PreparedTransitQuantityReceipt:
    line_id: str
    record_id: str
    approved_sha256: str
    newly_prepared: bool


def _validated_ownership(intents: tuple[TransitQuantityIntent, ...], selected: frozenset[str]) -> None:
    if not selected or not intents:
        raise TransitQuantityPreparationError("TRANSIT_SELECTION_REQUIRED")
    ids = [item.approval.transit.cable_line_id for item in intents]
    if len(ids) != len(set(ids)) or set(ids) != selected:
        raise TransitQuantityPreparationError("TRANSIT_SELECTION_NOT_EXACT")
    projects = {item.approval.transit.project_id for item in intents}
    if len(projects) != 1:
        raise TransitQuantityPreparationError("TRANSIT_MIXED_PROJECT_SELECTION")
    for intent in intents:
        if not intent.acceptance_evidence.strip() or not intent.approval.approval_evidence.strip():
            raise TransitQuantityPreparationError("TRANSIT_EXPLICIT_ACCEPTANCE_REQUIRED")
        if intent.expected_line_row_version < 1:
            raise TransitQuantityPreparationError("TRANSIT_INVALID_EXPECTED_VERSION")
        if (intent.expected_length_fact_id is None) != (
            intent.expected_length_fact_row_version is None
        ):
            raise TransitQuantityPreparationError("TRANSIT_INVALID_LENGTH_FACT_EXPECTATION")


def prepared_transit_batch_sha256(
    intents: tuple[TransitQuantityIntent, ...], *, selected_line_ids: frozenset[str]
) -> str:
    """Bind the complete selected set and all evidence; no hidden/unselected writes."""
    _validated_ownership(intents, selected_line_ids)
    body = {
        "contract": "NLP_D16_PREPARED_QUANTITY_V1",
        "selected_line_ids": sorted(selected_line_ids),
        "intents": [
            _json_ready(intent)
            for intent in sorted(intents, key=lambda x: x.approval.transit.cable_line_id)
        ],
    }
    serialized = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _decimal(value: object, *, nullable: bool = False) -> Decimal | None:
    if value is None and nullable:
        return None
    try:
        output = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise TransitQuantityPreparationError("TRANSIT_LEGACY_LENGTH_INVALID") from exc
    if not output.is_finite() or output < 0:
        raise TransitQuantityPreparationError("TRANSIT_LEGACY_LENGTH_INVALID")
    return output


def prepare_approved_transit_quantities(
    engine: Engine,
    intents: tuple[TransitQuantityIntent, ...],
    *,
    selected_line_ids: frozenset[str],
    approved_batch_sha256: str,
    confirmed: bool,
) -> tuple[PreparedTransitQuantityReceipt, ...]:
    """Atomic selected-only immutable approved receipts, no canonical quantity DML.

    This is not DWG apply or final specification publication. A failed selected
    member rolls back all newly inserted members in this batch.
    """
    _validated_ownership(intents, selected_line_ids)
    if not confirmed or approved_batch_sha256 != prepared_transit_batch_sha256(
        intents, selected_line_ids=selected_line_ids
    ):
        raise TransitQuantityPreparationError("TRANSIT_BATCH_APPROVAL_REQUIRED")
    receipts: list[PreparedTransitQuantityReceipt] = []
    with engine.begin() as connection:
        for intent in sorted(intents, key=lambda x: x.approval.transit.cable_line_id):
            approval = intent.approval
            ev = approval.transit
            line = connection.execute(
                select(cable_line).where(
                    cable_line.c.project_id == ev.project_id,
                    cable_line.c.id == ev.cable_line_id,
                    cable_line.c.lifecycle == "ACTIVE",
                )
            ).mappings().one_or_none()
            if line is None or line["row_version"] != intent.expected_line_row_version:
                raise TransitQuantityPreparationError("TRANSIT_LINE_OWNER_CHANGED")
            segment = connection.execute(
                select(cable_segment).where(
                    cable_segment.c.project_id == ev.project_id,
                    cable_segment.c.id == ev.electrical_segment_id,
                    cable_segment.c.cable_line_id == ev.cable_line_id,
                )
            ).mappings().one_or_none()
            if (
                segment is None
                or segment["row_version"] != ev.electrical_segment_row_version
                or segment["source_endpoint_id"] != ev.source_endpoint_id
                or segment["target_endpoint_id"] != ev.target_endpoint_id
            ):
                raise TransitQuantityPreparationError("TRANSIT_ELECTRICAL_OWNER_CHANGED")

            fact = connection.execute(
                select(cable_length_fact).where(
                    cable_length_fact.c.project_id == ev.project_id,
                    cable_length_fact.c.cable_line_id == ev.cable_line_id,
                )
            ).mappings().one_or_none()
            if fact is None:
                if intent.expected_length_fact_id is not None:
                    raise TransitQuantityPreparationError("TRANSIT_LENGTH_FACT_CHANGED")
                actual_additional, actual_manual = Decimal(0), None
            else:
                if (
                    fact["id"] != intent.expected_length_fact_id
                    or fact["row_version"] != intent.expected_length_fact_row_version
                ):
                    raise TransitQuantityPreparationError("TRANSIT_LENGTH_FACT_CHANGED")
                actual_additional = _decimal(fact["additional_length_m_decimal"] or "0")
                actual_manual = _decimal(
                    fact["manual_full_length_m_decimal"], nullable=True
                )
            if (
                _decimal(approval.additional_m) != actual_additional
                or _decimal(approval.manual_full_m, nullable=True) != actual_manual
            ):
                raise TransitQuantityPreparationError("TRANSIT_MANUAL_OR_ADDITIONAL_CONFLICT")

            preview = preview_transit_line(
                connection,
                approval,
                approved_sha256=transit_line_approval_sha256(approval),
                confirmed=True,
            )
            if preview.status != "APPROVED_PREVIEW_ONLY" or preview.quantity is None:
                raise TransitQuantityPreparationError(
                    "TRANSIT_QUANTITY_PREVIEW_REQUIRES_REVIEW:" + ",".join(preview.issues)
                )
            route = connection.execute(
                select(cable_transit_route.c.id).where(
                    cable_transit_route.c.project_id == ev.project_id,
                    cable_transit_route.c.electrical_segment_id == ev.electrical_segment_id,
                )
            ).scalar_one_or_none()
            if route is None:
                raise TransitQuantityPreparationError("TRANSIT_STAGED_ROUTE_DISAPPEARED")
            existing = connection.execute(
                select(cable_transit_line_commit).where(
                    cable_transit_line_commit.c.project_id == ev.project_id,
                    cable_transit_line_commit.c.cable_line_id == ev.cable_line_id,
                )
            ).mappings().one_or_none()
            if existing is not None:
                if (
                    existing["approval_sha256"] != approved_batch_sha256
                    or existing["cable_transit_route_id"] != route
                ):
                    raise TransitQuantityPreparationError("TRANSIT_PREPARED_COMMIT_CONFLICT")
                receipts.append(
                    PreparedTransitQuantityReceipt(
                        ev.cable_line_id, existing["id"], approved_batch_sha256, False
                    )
                )
                continue

            q = preview.quantity
            identity = new_id()
            connection.execute(
                cable_transit_line_commit.insert().values(
                    id=identity,
                    project_id=ev.project_id,
                    cable_line_id=ev.cable_line_id,
                    cable_transit_route_id=route,
                    electrical_segment_id=ev.electrical_segment_id,
                    line_row_version_at_approval=intent.expected_line_row_version,
                    segment_row_version_at_approval=ev.electrical_segment_row_version,
                    length_fact_id_at_approval=intent.expected_length_fact_id,
                    length_fact_row_version_at_approval=intent.expected_length_fact_row_version,
                    approval_sha256=approved_batch_sha256,
                    transit_approval_sha256=transit_line_approval_sha256(approval),
                    automatic_length_m_decimal=str(q.automatic_m),
                    final_length_m_decimal=str(q.final_m),
                    source=q.source,
                    calculation_snapshot_json=_json_ready(q),
                    approval_evidence=intent.acceptance_evidence,
                    state="PREPARED_APPROVED",
                )
            )
            receipts.append(
                PreparedTransitQuantityReceipt(ev.cable_line_id, identity, approved_batch_sha256, True)
            )
    return tuple(receipts)


def read_prepared_transit_quantities(
    connection, *, project_id: str
) -> tuple[dict[str, object], ...]:
    """Approved candidate receipts, never the live specification."""
    return tuple(
        dict(row)
        for row in connection.execute(
            select(cable_transit_line_commit)
            .where(cable_transit_line_commit.c.project_id == project_id)
            .order_by(cable_transit_line_commit.c.cable_line_id)
        ).mappings()
    )
