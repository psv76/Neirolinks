"""D20: compose real bridge forced-full in-memory CAD scan with D19/D18 preflight.

D20 prepares a trustworthy *method of acquisition* for later Windows acceptance,
not a cryptographic DWG disk signature or a canonical quantity publisher.
No live adapters are available in cloud CI; those tests mock the bridge IPC.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from nl_project_2.cad_contract import CadReadRequest
from nl_project_2.cad_sync.bridge import AutoCadBridgeClient

from .transit_activation_readiness import (
    TransitActivationRequest,
    plan_transit_activation,
)
from .transit_dwg_scan_lineage import (
    DwgTransitRevalidationPlan,
    plan_dwg_transit_revalidation,
)

if TYPE_CHECKING:
    from sqlalchemy import Engine


@dataclass(frozen=True, slots=True)
class TransitLiveBridgeReview:
    status: str
    selected_line_ids: tuple[str, ...]
    document_identity: str
    full_scan_fingerprint_sha256: str
    scan_mode: str
    composed: DwgTransitRevalidationPlan
    issues: tuple[str, ...]
    can_publish: bool = False
    proves_disk_dwg_freshness: bool = False


def review_transit_from_active_bridge(
    engine: Engine,
    bridge: AutoCadBridgeClient,
    requests: tuple[TransitActivationRequest, ...],
    *,
    selected_line_ids: frozenset[str],
    expected_document_identity: str,
    definition_names: tuple[str, ...],
    confirmed: bool = False,
    deadline_seconds: float = 120.0,
) -> TransitLiveBridgeReview:
    """Full forced COM bridge read bracketed by Project readback; no write path.

    No caller-supplied CadObservationBatch is accepted. Source is obtained via
    the actual AutoCadBridgeClient (full IPC scan, not its incremental cache).
    """
    if not isinstance(bridge, AutoCadBridgeClient):
        raise ValueError("D20_REAL_BRIDGE_CLIENT_REQUIRED")
    if not confirmed:
        raise ValueError("D20_EXPLICIT_SELECTION_CONFIRMATION_REQUIRED")
    if not expected_document_identity.strip():
        raise ValueError("D20_DOCUMENT_IDENTITY_REQUIRED")
    if not definition_names:
        raise ValueError("D20_CAD_CONTRACT_DEFINITIONS_REQUIRED")

    before = plan_transit_activation(
        engine,
        requests,
        selected_line_ids=selected_line_ids,
        confirmed=True,
    )
    if not before.selected_line_ids:
        raise ValueError("D20_LINE_SELECTION_REQUIRED")
    witness = bridge.read_fresh_observations_with_witness(
        CadReadRequest(
            expected_document_identity=expected_document_identity,
            deadline_seconds=deadline_seconds,
            definition_names=definition_names,
        )
    )
    # All requests refer to the same explicitly selected document. D19 rejects
    # a missing/foreign per-line Project binding and mismatched CAD identity.
    composition = plan_dwg_transit_revalidation(
        engine,
        requests,
        selected_line_ids=selected_line_ids,
        supplied_batches={line_id: witness.batch for line_id in before.selected_line_ids},
        confirmed=True,
    )
    after = plan_transit_activation(
        engine,
        requests,
        selected_line_ids=selected_line_ids,
        confirmed=True,
    )
    issues = set(composition.issues)
    if before.plan_sha256 != after.plan_sha256:
        issues.add("D20_PROJECT_CHANGED_DURING_CAD_SCAN")
    if witness.scan_mode != "FORCED_FULL_SCAN" or not witness.document_saved:
        issues.add("D20_BRIDGE_WITNESS_NOT_FULL_OR_SAVED")
    issues.add("D20_DISK_DWG_SOURCE_PROVENANCE_NOT_ESTABLISHED")
    issues.add("D20_CANONICAL_SOURCE_ACTIVATION_NOT_IMPLEMENTED")
    return TransitLiveBridgeReview(
        status="BLOCKED",
        selected_line_ids=before.selected_line_ids,
        document_identity=witness.document_identity,
        full_scan_fingerprint_sha256=witness.fingerprint_sha256,
        scan_mode=witness.scan_mode,
        composed=composition,
        issues=tuple(sorted(issues)),
    )
