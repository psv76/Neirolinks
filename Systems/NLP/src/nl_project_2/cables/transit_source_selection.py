"""D21: reversible in-request cable quantity shadow selection.

D21 cannot enable a production source: D20 in-memory CAD witness does not
attest durable DWG identity, and legacy recalculation remains authoritative.
No persistent ACTIVE flag, canonical writer, hidden fallback or quantity DML.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from .transit_activation_readiness import TransitActivationRequest

ShadowMode = Literal["PREPARED_SHADOW", "LEGACY_ONLY"]


@dataclass(frozen=True, slots=True)
class ShadowLineQuantity:
    cable_line_id: str
    status: str
    issues: tuple[str, ...]
    legacy_effective_m: Decimal | None
    prepared_candidate_m: Decimal | None
    preview_effective_m: Decimal | None
    preview_source: str
    d16_batch_sha256: str
    authorizes_publication: bool = False


@dataclass(frozen=True, slots=True)
class ShadowQuantitySelection:
    mode: ShadowMode
    status: str
    line_ids: tuple[str, ...]
    selection_sha256: str
    lines: tuple[ShadowLineQuantity, ...]
    can_publish: bool = False

    def preview_m_for(self, cable_line_id: str) -> Decimal | None:
        return next(
            row.preview_effective_m for row in self.lines if row.cable_line_id == cable_line_id
        )


def selection_sha256(
    requests: tuple[TransitActivationRequest, ...],
    selected_line_ids: frozenset[str],
    *,
    mode: ShadowMode,
) -> str:
    if mode not in {"PREPARED_SHADOW", "LEGACY_ONLY"}:
        raise ValueError("D21_SHADOW_MODE_UNKNOWN")
    ids = [request.approval.transit.cable_line_id for request in requests]
    if not ids or len(ids) != len(set(ids)) or set(ids) != selected_line_ids:
        raise ValueError("D21_SELECTION_NOT_EXACT")
    if len({request.approval.transit.project_id for request in requests}) != 1:
        raise ValueError("D21_SELECTION_MIXED_PROJECTS")
    payload = {
        "contract": "NLP_D21_REQUEST_SCOPED_SOURCE_V2",
        "project_id": requests[0].approval.transit.project_id,
        "mode": mode,
        "line_ids": sorted(selected_line_ids),
        "batches": sorted(
            (request.approval.transit.cable_line_id, request.d16_batch_sha256)
            for request in requests
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def make_shadow_selection(
    requests: tuple[TransitActivationRequest, ...],
    *,
    selected_line_ids: frozenset[str],
    mode: ShadowMode,
    expected_selection_sha256: str,
    confirmed: bool,
    legacy_effective_m: dict[str, Decimal | None],
    readbacks: dict[str, object],
) -> ShadowQuantitySelection:
    """Select the *entire* request-scoped shadow or nothing; fail closed.

    `readbacks` are freshly computed D17 reviews by CableService, not trusted
    serialized snapshots from the user. The per-request mode can be revoked
    by issuing LEGACY_ONLY, with zero persistence or cache invalidation.
    """
    digest = selection_sha256(requests, selected_line_ids, mode=mode)
    if digest != expected_selection_sha256 or not confirmed:
        raise ValueError("D21_EXPLICIT_SELECTION_APPROVAL_REQUIRED")
    if set(legacy_effective_m) != selected_line_ids:
        raise ValueError("D21_LEGACY_SELECTION_INCOMPLETE")
    if mode == "PREPARED_SHADOW" and set(readbacks) != selected_line_ids:
        raise ValueError("D21_D17_SELECTION_INCOMPLETE")
    rows = []
    review_issues: dict[str, tuple[str, ...]] = {}
    if mode == "PREPARED_SHADOW":
        for line_id in selected_line_ids:
            review = readbacks[line_id]
            issues = set(getattr(review, "issues", ()))
            if getattr(review, "cable_line_id", None) != line_id:
                issues.add("D22_READBACK_OWNER_MISMATCH")
            if getattr(review, "status", None) != "VERIFIED_READBACK_ONLY":
                issues.add("D21_BATCH_MEMBER_REQUIRES_REVIEW")
            candidate = getattr(review, "prepared_final_m", None)
            if not isinstance(candidate, Decimal) or not candidate.is_finite() or candidate < 0:
                issues.add("D22_READBACK_QUANTITY_INVALID")
            review_issues[line_id] = tuple(sorted(issues))
    blocked = any(review_issues.values())
    for request in sorted(requests, key=lambda value: value.approval.transit.cable_line_id):
        line_id = request.approval.transit.cable_line_id
        legacy = legacy_effective_m[line_id]
        review = readbacks.get(line_id)
        if mode == "LEGACY_ONLY":
            status, issues = "LEGACY_ONLY", ()
            candidate, effective, source = None, legacy, "LEGACY"
        elif blocked:
            status = "REVIEW"
            issues = review_issues[line_id] or ("D21_BATCH_MEMBER_REQUIRES_REVIEW",)
            candidate, effective, source = None, legacy, "LEGACY"
        else:
            status, issues = "SHADOW_PREVIEW_ONLY", ()
            candidate = review.prepared_final_m
            effective, source = candidate, "PREPARED_SHADOW"
        rows.append(
            ShadowLineQuantity(
                cable_line_id=line_id,
                status=status,
                issues=issues,
                legacy_effective_m=legacy,
                prepared_candidate_m=candidate,
                preview_effective_m=effective,
                preview_source=source,
                d16_batch_sha256=request.d16_batch_sha256,
            )
        )
    return ShadowQuantitySelection(
        mode=mode,
        status="REVIEW"
        if blocked
        else "SHADOW_PREVIEW_ONLY"
        if mode == "PREPARED_SHADOW"
        else "LEGACY_ONLY",
        line_ids=tuple(sorted(selected_line_ids)),
        selection_sha256=digest,
        lines=tuple(rows),
    )
