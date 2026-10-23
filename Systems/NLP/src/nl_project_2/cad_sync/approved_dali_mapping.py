"""D9 — explicitly approved, backup-gated legacy DALI graph backfill.

A D8 CANDIDATE is not approval. PREVIEW never changes SQLite. APPLY requires
an exact plan digest, affirmative confirmation and a new verified SQLite online
backup before any data changes. No device address, existing link, old segment,
cable length, conduit or field_device evidence is modified or inferred.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import Engine, select

from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.migration import (
    HEAD_REVISION,
    BackupReceipt,
    create_verified_backup,
    current_revision_read_only,
)
from nl_project_2.persistence.schema import (
    bus,
    bus_endpoint,
    bus_physical_link,
    bus_physical_node,
    field_device,
)

from .legacy_dali_audit import (
    LegacyDaliAudit,
    LegacyDaliReviewRow,
    audit_accepted_dali_project,
)
from .project_bus_context import load_project_bus_context


class LegacyDaliMappingError(RuntimeError):
    """The selected owner, Project evidence or explicit approval is unsafe."""


@dataclass(frozen=True, slots=True)
class LegacyDaliMappingAction:
    field_device_id: str
    identity: str
    bus_designation: str
    source: str
    kind: str
    operation: str


@dataclass(frozen=True, slots=True)
class LegacyDaliMappingPlan:
    project_id: str
    audit_sha256: str
    selected: tuple[LegacyDaliReviewRow, ...]
    actions: tuple[LegacyDaliMappingAction, ...]
    plan_sha256: str

    @property
    def changes(self) -> tuple[LegacyDaliMappingAction, ...]:
        return tuple(a for a in self.actions if a.operation != "NOOP")

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)


@dataclass(frozen=True, slots=True)
class LegacyDaliApplyReceipt:
    project_id: str
    plan_sha256: str
    backup: BackupReceipt
    inserted_physical_nodes: int
    inserted_links: int


def _digest(data: object) -> str:
    encoded = json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _selected_rows(
    audit: LegacyDaliAudit, owner_ids: tuple[str, ...]
) -> tuple[LegacyDaliReviewRow, ...]:
    if not owner_ids or len(owner_ids) != len(set(owner_ids)):
        raise LegacyDaliMappingError("DALI_MAPPING_SELECTION_EMPTY_OR_DUPLICATE")
    owners = {row.field_device_id: row for row in audit.rows}
    if any(owner not in owners for owner in owner_ids):
        raise LegacyDaliMappingError("DALI_MAPPING_OWNER_NOT_IN_AUDIT")
    selected = tuple(sorted((owners[owner] for owner in owner_ids), key=lambda r: r.field_device_id))
    if any(row.disposition == "REVIEW" for row in selected):
        raise LegacyDaliMappingError("DALI_MAPPING_REVIEW_BLOCKED")
    return selected


def _preview_from_audit(
    audit: LegacyDaliAudit, owner_ids: tuple[str, ...]
) -> LegacyDaliMappingPlan:
    selected = _selected_rows(audit, owner_ids)
    physical_ready = {
        row.identity
        for row in audit.rows
        if row.identity_kind == "PHYSICAL" and row.disposition == "ALREADY_MAPPED"
    }
    physical_ready.update(
        row.identity for row in selected if row.identity_kind == "PHYSICAL"
    )
    if any(
        row.source.startswith(("BOX.", "TRACK.")) and row.source not in physical_ready
        for row in selected
    ):
        raise LegacyDaliMappingError("DALI_MAPPING_PARENT_NOT_SELECTED_OR_ACCEPTED")
    actions: list[LegacyDaliMappingAction] = []
    for row in selected:
        operation = (
            "NOOP"
            if row.disposition == "ALREADY_MAPPED"
            else "INSERT_PHYSICAL_NODE_AND_LINK"
            if row.identity_kind == "PHYSICAL"
            else "INSERT_ADDRESSED_LINK"
        )
        actions.append(
            LegacyDaliMappingAction(
                row.field_device_id, row.identity,
                row.bus_designation, row.source, row.identity_kind, operation
            )
        )
    stable_actions = tuple(sorted(actions, key=lambda a: a.field_device_id))
    fingerprint = _digest(
        {
            "project_id": audit.project_id,
            "audit_sha256": audit.fingerprint_sha256,
            "selected": [asdict(row) for row in selected],
            "actions": [asdict(action) for action in stable_actions],
        }
    )
    return LegacyDaliMappingPlan(
        audit.project_id, audit.fingerprint_sha256, selected, stable_actions, fingerprint
    )


def preview_legacy_dali_mapping(
    engine: Engine,
    *,
    project_id: str,
    selected_field_device_ids: tuple[str, ...],
) -> LegacyDaliMappingPlan:
    """Read-only exact-owner candidate/NOOP plan; not an approval."""
    with engine.connect() as connection:
        audit = audit_accepted_dali_project(connection, project_id=project_id)
        return _preview_from_audit(audit, selected_field_device_ids)


def _canonical_source(connection, *, project_id: str, bus_row, source: str):
    if source == f"{bus_row['designation']}.000":
        return "ROOT", None, None
    if source.startswith(("BOX.", "TRACK.")):
        parents = connection.execute(
            select(bus_physical_node).where(
                bus_physical_node.c.project_id == project_id,
                bus_physical_node.c.bus_id == bus_row["id"],
                bus_physical_node.c.physical_id == source,
            )
        ).mappings().all()
        if len(parents) != 1:
            raise LegacyDaliMappingError(f"DALI_MAPPING_PARENT_UNRESOLVED:{source}")
        return "PHYSICAL", parents[0]["id"], None
    endpoints = connection.execute(
        select(bus_endpoint).where(
            bus_endpoint.c.project_id == project_id,
            bus_endpoint.c.bus_id == bus_row["id"],
            bus_endpoint.c.address == source,
        )
    ).mappings().all()
    if len(endpoints) != 1:
        raise LegacyDaliMappingError(f"DALI_MAPPING_ADDRESS_SOURCE_UNRESOLVED:{source}")
    return "ADDRESSED", None, endpoints[0]["id"]


def _apply_exact_mapping(connection, plan: LegacyDaliMappingPlan) -> tuple[int, int]:
    context = load_project_bus_context(connection, plan.project_id)
    bus_rows = {
        row["designation"]: row
        for row in connection.execute(
            select(bus).where(
                bus.c.project_id == plan.project_id,
                bus.c.lifecycle == "ACTIVE",
                bus.c.bus_kind == "DALI",
            )
        ).mappings()
    }
    nodes_inserted = 0
    links_inserted = 0
    for action in plan.actions:
        if action.operation == "NOOP":
            continue
        if f"{action.bus_designation}.000" not in context.verified_dali_roots:
            raise LegacyDaliMappingError("DALI_MAPPING_ROOT_NOT_VERIFIED")
        bus_row = bus_rows.get(action.bus_designation)
        if bus_row is None:
            raise LegacyDaliMappingError("DALI_MAPPING_BUS_NOT_FOUND")
        fields = connection.execute(
            select(field_device).where(
                field_device.c.id == action.field_device_id,
                field_device.c.project_id == plan.project_id,
                field_device.c.lifecycle == "ACTIVE",
            )
        ).mappings().one_or_none()
        if fields is None:
            raise LegacyDaliMappingError("DALI_MAPPING_OWNER_LOST")
        values = dict(fields["normalized_fields_json"] or {})
        if (
            str(values.get("BUS_ID") or "").strip() != action.bus_designation
            or str(values.get("BUS_SOURCE") or "").strip() != action.source
        ):
            raise LegacyDaliMappingError("DALI_MAPPING_OWNER_CHANGED")
        if action.kind == "PHYSICAL":
            owner_tag = "BOX_ID" if fields["block_kind"] == "EL_BOX_OUT_100x100" else "TRACK_ID"
            if str(values.get(owner_tag) or "").strip() != action.identity:
                raise LegacyDaliMappingError("DALI_MAPPING_PHYSICAL_OWNER_CHANGED")
            existing = connection.execute(
                select(bus_physical_node).where(
                    bus_physical_node.c.project_id == plan.project_id,
                    bus_physical_node.c.physical_id == action.identity,
                )
            ).mappings().one_or_none()
            if existing is not None:
                if (
                    existing["bus_id"] != bus_row["id"]
                    or existing["field_device_id"] != action.field_device_id
                ):
                    raise LegacyDaliMappingError("DALI_MAPPING_PHYSICAL_OWNER_CONFLICT")
                target_id = existing["id"]
            else:
                target_id = new_id()
                connection.execute(
                    bus_physical_node.insert().values(
                        id=target_id,
                        project_id=plan.project_id,
                        bus_id=bus_row["id"],
                        field_device_id=action.field_device_id,
                        physical_id=action.identity,
                        physical_kind="BOX" if action.identity.startswith("BOX.") else "TRACK",
                    )
                )
                nodes_inserted += 1
        else:
            target = connection.execute(
                select(bus_endpoint).where(
                    bus_endpoint.c.project_id == plan.project_id,
                    bus_endpoint.c.bus_id == bus_row["id"],
                    bus_endpoint.c.field_device_id == action.field_device_id,
                    bus_endpoint.c.address == action.identity,
                )
            ).mappings().one_or_none()
            if target is None:
                raise LegacyDaliMappingError("DALI_MAPPING_ADDRESS_OWNER_NOT_FOUND")
            target_id = target["id"]

    for action in plan.actions:
        if action.operation == "NOOP":
            continue
        bus_row = bus_rows[action.bus_designation]
        source_kind, physical_parent, addressed_parent = _canonical_source(
            connection, project_id=plan.project_id, bus_row=bus_row, source=action.source
        )
        target_col = (
            bus_physical_link.c.target_physical_node_id
            if action.kind == "PHYSICAL"
            else bus_physical_link.c.target_bus_endpoint_id
        )
        if action.kind == "PHYSICAL":
            target_id = connection.execute(
                select(bus_physical_node.c.id).where(
                    bus_physical_node.c.project_id == plan.project_id,
                    bus_physical_node.c.bus_id == bus_row["id"],
                    bus_physical_node.c.field_device_id == action.field_device_id,
                    bus_physical_node.c.physical_id == action.identity,
                )
            ).scalar_one()
        else:
            target_id = connection.execute(
                select(bus_endpoint.c.id).where(
                    bus_endpoint.c.project_id == plan.project_id,
                    bus_endpoint.c.bus_id == bus_row["id"],
                    bus_endpoint.c.field_device_id == action.field_device_id,
                    bus_endpoint.c.address == action.identity,
                )
            ).scalar_one()
        occupied = connection.execute(
            select(bus_physical_link.c.id).where(
                bus_physical_link.c.project_id == plan.project_id,
                target_col == target_id,
            )
        ).scalar_one_or_none()
        if occupied:
            raise LegacyDaliMappingError("DALI_MAPPING_TARGET_LINK_ALREADY_EXISTS")
        connection.execute(
            bus_physical_link.insert().values(
                id=new_id(),
                project_id=plan.project_id,
                bus_id=bus_row["id"],
                source_kind=source_kind,
                source_physical_node_id=physical_parent,
                source_bus_endpoint_id=addressed_parent,
                target_kind=action.kind,
                target_physical_node_id=target_id if action.kind == "PHYSICAL" else None,
                target_bus_endpoint_id=target_id if action.kind == "ADDRESSED" else None,
                link_kind=(
                    "TRACK" if action.kind == "ADDRESSED" and action.source.startswith("TRACK.")
                    else "CABLE"
                ),
            )
        )
        links_inserted += 1
    return nodes_inserted, links_inserted


def apply_approved_legacy_dali_mapping(
    engine: Engine,
    plan: LegacyDaliMappingPlan,
    *,
    approved_plan_sha256: str,
    confirmed: bool,
    backup_directory: Path,
) -> LegacyDaliApplyReceipt:
    """Explicit opt-in gate. Never call on a production DB without authorization.

    The backup is created before the first DML, using the existing online
    SQLite backup API. A changed audit or a mismatched consent aborts atomically.
    Restoring from the verified backup is an explicit operator operation,
    never automatic overwriting of a working Project.
    """
    if not confirmed or not approved_plan_sha256 or approved_plan_sha256 != plan.plan_sha256:
        raise LegacyDaliMappingError("DALI_MAPPING_EXPLICIT_APPROVAL_REQUIRED")
    database_name = engine.url.database
    if not database_name or database_name == ":memory:":
        raise LegacyDaliMappingError("DALI_MAPPING_VERSIONED_FILE_REQUIRED")
    path = Path(database_name).resolve()
    if current_revision_read_only(path) != HEAD_REVISION:
        raise LegacyDaliMappingError("DALI_MAPPING_SCHEMA_HEAD_REQUIRED")
    if not plan.actions:
        raise LegacyDaliMappingError("DALI_MAPPING_EMPTY_PLAN")

    # Precheck before producing a backup; after backup, recheck again inside
    # the transaction (including all fields and accepted link owners).
    ids = tuple(row.field_device_id for row in plan.selected)
    if preview_legacy_dali_mapping(
        engine, project_id=plan.project_id, selected_field_device_ids=ids
    ) != plan:
        raise LegacyDaliMappingError("DALI_MAPPING_PLAN_STALE")
    receipt = create_verified_backup(path, backup_directory)
    if receipt.source_revision != HEAD_REVISION or not receipt.path.is_file():
        raise LegacyDaliMappingError("DALI_MAPPING_VERIFIED_BACKUP_REQUIRED")
    with engine.begin() as connection:
        current = _preview_from_audit(
            audit_accepted_dali_project(connection, project_id=plan.project_id), ids
        )
        if current != plan:
            raise LegacyDaliMappingError("DALI_MAPPING_PLAN_STALE")
        nodes, links = _apply_exact_mapping(connection, plan)
    return LegacyDaliApplyReceipt(plan.project_id, plan.plan_sha256, receipt, nodes, links)
