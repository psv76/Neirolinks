"""D8: read-only inventory / deterministic review plan for accepted legacy DALI.

This module never writes data, never creates a migration, and never infers
missing ownership, BUS_ID, protocol addresses, route or lengths. A candidate
means "sufficient evidence for human review", NOT approval for backfill.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import Connection, select

from nl_project_2.persistence.schema import (
    bus,
    bus_endpoint,
    bus_physical_link,
    bus_physical_node,
    bus_segment,
    field_device,
)

_BUS = re.compile(r"^9[0-9]{2}$")
_ADDRESS = re.compile(r"^(9[0-9]{2})\.[0-9]{3}$")
_PHYSICAL = re.compile(r"^(BOX|TRACK)\.[0-9]{3}$")
_PASSIVE_KINDS = frozenset({"EL_BOX_OUT_100x100", "TRACK_DALI"})


@dataclass(frozen=True, slots=True)
class LegacyDaliReviewRow:
    field_device_id: str
    dwg_binding_id: str | None
    handle: str | None
    block_name: str
    bus_designation: str
    identity: str
    identity_kind: str
    source: str
    disposition: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LegacyDaliAudit:
    project_id: str
    fingerprint_sha256: str
    rows: tuple[LegacyDaliReviewRow, ...]
    summary: tuple[tuple[str, int], ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, indent=2)


def audit_accepted_dali_project(connection: Connection, *, project_id: str) -> LegacyDaliAudit:
    """Inspect one Project at revision 15 without DML or DWG/API interaction.

    Input is only accepted Project persistence evidence. Every record remains
    explicitly REVIEW until parent identity, bus and owner are unambiguous.
    No caller should mutate persistence based solely on this result.
    """
    buses = {
        str(row["designation"]): dict(row)
        for row in connection.execute(
            select(bus).where(bus.c.project_id == project_id, bus.c.lifecycle == "ACTIVE")
        ).mappings()
    }
    physical_rows = list(
        connection.execute(
            select(bus_physical_node).where(bus_physical_node.c.project_id == project_id)
        ).mappings()
    )
    physical_by_owner = defaultdict(list)
    for row in physical_rows:
        physical_by_owner[row["field_device_id"]].append(dict(row))
    links_by_target = defaultdict(list)
    for link in connection.execute(
        select(bus_physical_link).where(bus_physical_link.c.project_id == project_id)
    ).mappings():
        target = link["target_physical_node_id"] or link["target_bus_endpoint_id"]
        links_by_target[target].append(dict(link))
    endpoints = list(
        connection.execute(
            select(bus_endpoint).where(bus_endpoint.c.project_id == project_id)
        ).mappings()
    )
    endpoint_by_device = defaultdict(list)
    endpoint_by_address = defaultdict(list)
    for ep in endpoints:
        if ep["field_device_id"]:
            endpoint_by_device[ep["field_device_id"]].append(dict(ep))
        if ep["address"]:
            endpoint_by_address[(ep["bus_id"], ep["address"])].append(dict(ep))
    segments_by_endpoint = defaultdict(list)
    for seg in connection.execute(
        select(bus_segment).where(bus_segment.c.project_id == project_id)
    ).mappings():
        segments_by_endpoint[seg["target_endpoint_id"]].append(dict(seg))

    candidates: list[dict[str, Any]] = []
    for row in connection.execute(
        select(field_device).where(
            field_device.c.project_id == project_id,
            field_device.c.lifecycle == "ACTIVE",
        )
    ).mappings():
        values = dict(row["normalized_fields_json"] or {})
        block_name = str(row["block_kind"])
        passive = block_name in _PASSIVE_KINDS
        source = str(values.get("BUS_SOURCE") or "").strip()
        raw_bus = str(values.get("BUS_ID") or "").strip()
        raw_address = str(values.get("BUS_POINT_ID") or "").strip()
        physical_tag = "BOX_ID" if block_name == "EL_BOX_OUT_100x100" else "TRACK_ID"
        identity = str(values.get(physical_tag) or "").strip() if passive else raw_address
        # Exclude ordinary/RS485/KNX insertions; keep all anomalous passive
        # BOX/TRACK records with any bus evidence so defects remain visible.
        if not passive:
            address_match = _ADDRESS.fullmatch(raw_address)
            if not (
                (raw_bus in buses and buses[raw_bus]["bus_kind"] == "DALI")
                or (address_match and address_match.group(1) in buses
                    and buses[address_match.group(1)]["bus_kind"] == "DALI")
                or source.startswith(("BOX.", "TRACK."))
            ):
                continue
        elif not (raw_bus or source or raw_address or identity):
            continue
        if not passive and not raw_address:
            # An addressless ordinary BUS-capable device is not a physical
            # DALI topology target; don't invent a target identity for it.
            continue
        if not passive and not source.startswith(("BOX.", "TRACK.")):
            # An ordinary addressable DALI circuit belongs to the existing
            # bus_endpoint/bus_segment model, not legacy physical mapping,
            # unless it already has an explicit typed physical link.
            existing = any(
                links_by_target.get(ep["id"])
                for ep in endpoint_by_device.get(row["id"], [])
            )
            if not existing:
                continue
        candidates.append({
            "row": dict(row),
            "fields": values,
            "passive": passive,
            "bus": raw_bus,
            "address": raw_address,
            "identity": identity,
            "source": source,
        })

    physical_identity_counts = Counter(
        c["identity"] for c in candidates if c["passive"] and c["identity"]
    )
    physical_by_identity = defaultdict(list)
    for item in candidates:
        if item["passive"] and item["identity"]:
            physical_by_identity[item["identity"]].append(item)
    # Detect physical-only cycles in *accepted legacy evidence*. Never
    # repair the cycle by guessing an upstream or allowing a DFS root.
    cyclic: set[str] = set()
    for item in candidates:
        if not item["passive"] or not item["identity"]:
            continue
        seen: list[str] = []
        cursor = item
        while True:
            identity = cursor["identity"]
            if identity in seen:
                cyclic.update(seen[seen.index(identity):])
                break
            seen.append(identity)
            parent_identity = cursor["source"]
            parents = physical_by_identity.get(parent_identity, [])
            if len(parents) != 1 or parents[0]["bus"] != cursor["bus"]:
                break
            cursor = parents[0]

    results: list[LegacyDaliReviewRow] = []
    for candidate in candidates:
        row = candidate["row"]
        bus_name = candidate["bus"]
        identity = candidate["identity"]
        source = candidate["source"]
        passive = candidate["passive"]
        reasons: set[str] = set()
        bus_row = buses.get(bus_name)
        if not _BUS.fullmatch(bus_name or ""):
            reasons.add("BUS_ID_MISSING_OR_MALFORMED")
        elif bus_row is None:
            reasons.add("BUS_ROOT_NOT_ACCEPTED")
        elif bus_row["bus_kind"] != "DALI":
            reasons.add("BUS_KIND_NOT_DALI")
        address = candidate["address"]
        if passive:
            expected = "BOX" if row["block_kind"] == "EL_BOX_OUT_100x100" else "TRACK"
            match = _PHYSICAL.fullmatch(identity)
            if not match or match.group(1) != expected:
                reasons.add("PHYSICAL_ID_MISSING_OR_MALFORMED")
            if physical_identity_counts[identity] > 1:
                reasons.add("PHYSICAL_ID_DUPLICATE_ACROSS_ACCEPTED")
            if identity in cyclic:
                reasons.add("BUS_SOURCE_CYCLE")
            if address:
                reasons.add("PASSIVE_HAS_PROTOCOL_ADDRESS")
        else:
            addr = _ADDRESS.fullmatch(address)
            if not addr or addr.group(1) != bus_name or address.endswith(".000"):
                reasons.add("ADDRESS_MISSING_OR_CROSS_BUS")
        if not row["dwg_document_binding_id"] or not row["entity_handle"]:
            reasons.add("OWNER_DWG_BINDING_OR_HANDLE_MISSING")
        if not source:
            reasons.add("BUS_SOURCE_MISSING")
        elif bus_row is not None and bus_row["bus_kind"] == "DALI":
            if source == f"{bus_name}.000":
                pass
            elif _PHYSICAL.fullmatch(source):
                owners = physical_by_identity.get(source, [])
                if len(owners) != 1:
                    reasons.add("SOURCE_PHYSICAL_MISSING_OR_AMBIGUOUS")
                elif owners[0]["bus"] != bus_name:
                    reasons.add("SOURCE_PHYSICAL_OTHER_BUS")
            elif _ADDRESS.fullmatch(source):
                if source.split(".", 1)[0] != bus_name:
                    reasons.add("SOURCE_ADDRESSED_OTHER_BUS")
                elif len(endpoint_by_address[(bus_row["id"], source)]) != 1:
                    reasons.add("SOURCE_ADDRESS_NOT_CANONICAL")
            else:
                reasons.add("BUS_SOURCE_FORMAT_UNKNOWN")

        actual_owner = row["id"]
        owned_physical = physical_by_owner.get(actual_owner, [])
        owned_endpoints = endpoint_by_device.get(actual_owner, [])
        if passive:
            if len(owned_physical) > 1:
                reasons.add("MULTIPLE_PERSISTED_PHYSICAL_OWNERS")
            elif owned_physical:
                stored = owned_physical[0]
                if (
                    stored["physical_id"] != identity
                    or bus_row is None
                    or stored["bus_id"] != bus_row["id"]
                ):
                    reasons.add("PERSISTED_PHYSICAL_ID_OR_BUS_CONFLICT")
            if owned_endpoints:
                reasons.add("PASSIVE_OWNS_ADDRESSABLE_ENDPOINT")
            stored_target = owned_physical[0]["id"] if len(owned_physical) == 1 else None
        else:
            matching = [
                ep for ep in owned_endpoints
                if bus_row is not None
                and ep["bus_id"] == bus_row["id"]
                and ep["address"] == address
            ]
            if len(matching) != 1:
                reasons.add("ADDRESSABLE_ENDPOINT_MISSING_OR_AMBIGUOUS")
            if len(owned_endpoints) > 1:
                reasons.add("MULTIPLE_ADDRESSABLE_OWNERS")
            stored_target = matching[0]["id"] if len(matching) == 1 else None
            if stored_target and segments_by_endpoint.get(stored_target) and source.startswith(
                ("BOX.", "TRACK.")
            ):
                reasons.add("LEGACY_ADDRESSABLE_BUS_SEGMENT_REQUIRES_REVIEW")

        existing_links = links_by_target.get(stored_target, []) if stored_target else []
        if len(existing_links) > 1:
            reasons.add("MULTIPLE_PERSISTED_PHYSICAL_LINKS")
        stored_bus = bus_row["id"] if bus_row else None
        if existing_links and stored_bus and existing_links[0]["bus_id"] != stored_bus:
            reasons.add("PERSISTED_LINK_OTHER_BUS")
        if existing_links:
            existing = existing_links[0]
            if source == f"{bus_name}.000":
                consistent = existing["source_kind"] == "ROOT"
            elif source.startswith(("BOX.", "TRACK.")):
                parent = [
                    x for x in physical_rows
                    if x["physical_id"] == source and x["bus_id"] == stored_bus
                ]
                consistent = (
                    len(parent) == 1
                    and existing["source_kind"] == "PHYSICAL"
                    and existing["source_physical_node_id"] == parent[0]["id"]
                )
            else:
                parents = endpoint_by_address.get((stored_bus, source), [])
                consistent = (
                    len(parents) == 1
                    and existing["source_kind"] == "ADDRESSED"
                    and existing["source_bus_endpoint_id"] == parents[0]["id"]
                )
            if not consistent:
                reasons.add("PERSISTED_LINK_SOURCE_CONFLICT")

        if reasons:
            disposition = "REVIEW"
        elif existing_links:
            disposition = "ALREADY_MAPPED"
        else:
            # Candidate is a *review-only plan*, not an executable update.
            disposition = "CANDIDATE"
        results.append(
            LegacyDaliReviewRow(
                field_device_id=actual_owner,
                dwg_binding_id=row["dwg_document_binding_id"],
                handle=row["entity_handle"],
                block_name=row["block_kind"],
                bus_designation=bus_name,
                identity=identity,
                identity_kind="PHYSICAL" if passive else "ADDRESSED",
                source=source,
                disposition=disposition,
                reasons=tuple(sorted(reasons)),
            )
        )
    ordered = tuple(
        sorted(results, key=lambda x: (x.bus_designation, x.identity, x.field_device_id))
    )
    counts = Counter(x.disposition for x in ordered)
    counts.update({"TOTAL": len(ordered)})
    canonical = json.dumps(
        {"project_id": project_id, "rows": [asdict(x) for x in ordered]},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return LegacyDaliAudit(
        project_id=project_id,
        fingerprint_sha256=hashlib.sha256(canonical).hexdigest(),
        rows=ordered,
        summary=tuple(sorted(counts.items())),
    )
