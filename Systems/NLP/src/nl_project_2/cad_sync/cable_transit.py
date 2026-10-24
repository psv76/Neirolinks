"""D11: deterministic read-only preview of uninterrupted ordinary-cable transit.

This module does not materialize CableSegments, calculate lengths, assign
Conduits or mutate DWG/SQLite. A CANDIDATE is evidence for review, not consent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

_TRANSIT_TOKEN = re.compile(r"^(?P<base>[1-8][0-9]{2})(?:-(?P<order>[1-9][0-9]*))?$")
_BOX_ID = re.compile(r"^BOX\.[0-9]{3}$")


@dataclass(frozen=True, slots=True)
class TransitIssue:
    code: str
    handle: str
    value: str
    cable_base: str | None = None


@dataclass(frozen=True, slots=True)
class TransitWaypoint:
    cable_base: str
    box_id: str
    handle: str
    ordinal: int | None
    x: Any
    y: Any
    mount_height_mm: str


@dataclass(frozen=True, slots=True)
class TransitRoutePreview:
    cable_base: str
    status: str
    waypoints: tuple[TransitWaypoint, ...]
    source_point_key: str | None
    target_point_key: str | None
    issue_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TransitAudit:
    routes: tuple[TransitRoutePreview, ...] = ()
    issues: tuple[TransitIssue, ...] = ()

    @property
    def requires_review(self) -> bool:
        return bool(self.issues) or any(route.status == "REVIEW" for route in self.routes)


def analyze_cable_transit(
    observations: Iterable[Any],
    ordinary_segments: Iterable[Any],
) -> TransitAudit:
    """Inspect physical BOX waypoints without inferring routes or cable metres.

    D11 may describe a candidate chain only for a single accepted electrical
    segment. Multiple electrical segments are left for a later, explicit
    branch/path ownership stage; their INSERT order or coordinates never choose
    a route. A missing or malformed token cannot silently disappear.
    """
    grouped: dict[str, list[TransitWaypoint]] = {}
    issues: list[TransitIssue] = []
    for item in sorted(observations, key=lambda row: row.observation.handle):
        if item.ignored_project_data or item.read_payload is None:
            continue
        if item.read_payload.block_name != "EL_BOX_OUT_100x100":
            continue
        raw = str(item.normalized_attributes.get("CABLE_TRANSIT") or "").strip()
        if not raw:
            continue
        box_id = str(item.normalized_attributes.get("BOX_ID") or "").strip()
        for entry in raw.split(";"):
            token = entry.strip()
            match = _TRANSIT_TOKEN.fullmatch(token)
            if match is None:
                issues.append(
                    TransitIssue("TRANSIT_TOKEN_INVALID", item.observation.handle, token)
                )
                continue
            base = match.group("base")
            order = match.group("order")
            grouped.setdefault(base, []).append(
                TransitWaypoint(
                    cable_base=base,
                    box_id=box_id,
                    handle=item.observation.handle,
                    ordinal=int(order) if order is not None else None,
                    x=item.observation.x,
                    y=item.observation.y,
                    mount_height_mm=str(
                        item.normalized_attributes.get("MOUNT_HEIGHT") or ""
                    ),
                )
            )

    by_base: dict[str, list[Any]] = {}
    for segment in ordinary_segments:
        by_base.setdefault(segment.base, []).append(segment)

    routes: list[TransitRoutePreview] = []
    for base, values in sorted(grouped.items()):
        local: set[str] = set()
        if any(not _BOX_ID.fullmatch(point.box_id) for point in values):
            local.add("TRANSIT_BOX_ID_INVALID")
        if len({point.handle for point in values}) != len(values):
            local.add("TRANSIT_DUPLICATE_BOX_ENTRY")
        if len({point.box_id for point in values}) != len(values):
            local.add("TRANSIT_DUPLICATE_PHYSICAL_BOX")

        indexed = [point.ordinal for point in values if point.ordinal is not None]
        if len(values) > 1 and len(indexed) != len(values):
            local.add("TRANSIT_ORDER_AMBIGUOUS")
        if indexed and sorted(indexed) != list(range(1, len(values) + 1)):
            local.add("TRANSIT_ORDER_NOT_CONTIGUOUS")

        candidates = by_base.get(base, [])
        if not candidates:
            local.add("TRANSIT_CABLE_LINE_NOT_PRESENT")
        elif len(candidates) != 1:
            local.add("TRANSIT_PATH_REQUIRES_REVIEW")
        elif (
            candidates[0].source_reference is not None
            and candidates[0].source_point_key is None
        ):
            local.add("TRANSIT_SOURCE_UNRESOLVED")

        waypoints = tuple(
            sorted(
                values,
                key=lambda point: (
                    point.ordinal is None,
                    point.ordinal or 0,
                    point.box_id,
                    point.handle,
                ),
            )
        )
        candidate = candidates[0] if len(candidates) == 1 and not local else None
        routes.append(
            TransitRoutePreview(
                cable_base=base,
                status="CANDIDATE" if not local else "REVIEW",
                waypoints=waypoints,
                source_point_key=candidate.source_point_key if candidate else None,
                target_point_key=candidate.target_point_key if candidate else None,
                issue_codes=tuple(sorted(local)),
            )
        )
    return TransitAudit(
        routes=tuple(routes),
        issues=tuple(
            sorted(
                issues,
                key=lambda issue: (
                    issue.handle,
                    issue.code,
                    issue.value,
                ),
            )
        ),
    )

