"""Staged census assessment; never turns filtered observations into a full snapshot.

No scanner emits this evidence yet. Callers must establish a fresh read_id and a
stable revision around a complete, unfiltered INSERT census and heavy read.
DBMOD is not a revision token. These DTOs describe evidence, not an attestation
that a caller actually obtained it from AutoCAD. No preview/apply wiring exists.
"""

import re
from dataclasses import dataclass

from nl_project_2.cad_contract import CadObservationBatch
from nl_project_2.cad_contract.layer_names import parse_working_layer_name

_HANDLE = re.compile(r"[0-9A-F]+")


def _valid_handle(handle: str) -> bool:
    # AutoCAD emits canonical uppercase hex. Reject aliases rather than letting
    # a lower-case duplicate masquerade as a deleted owner.
    return isinstance(handle, str) and _HANDLE.fullmatch(handle) is not None


@dataclass(frozen=True, slots=True)
class CensusEntry:
    handle: str
    layer: str


@dataclass(frozen=True, slots=True)
class InsertCensus:
    document_identity: str
    read_id: str
    revision: str
    entries: tuple[CensusEntry, ...]
    complete: bool = False
    unfiltered: bool = False
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AbsenceProof:
    """Explicit successful unfiltered absence check, never a failed COM lookup."""

    document_identity: str
    read_id: str
    revision: str
    handle: str
    confirmed_absent: bool = False
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CensusAssessment:
    problems: tuple[str, ...]
    heavy_read_handles: tuple[str, ...] = ()
    missing_observation_handles: tuple[str, ...] = ()
    present_excluded_handles: tuple[str, ...] = ()
    absent_unknown_handles: tuple[str, ...] = ()
    proven_absent_handles: tuple[str, ...] = ()

    @property
    def status(self) -> str:
        if self.problems or self.missing_observation_handles or self.absent_unknown_handles:
            return "REQUIRES_ATTENTION"
        return "STAGED_ONLY"

    @property
    def next_action(self) -> str:
        if self.problems:
            return "Repeat an unfiltered read with fresh document/revision evidence."
        if self.missing_observation_handles:
            return "Read every missing handle, including tracked inserts on excluded layers."
        if self.absent_unknown_handles:
            return "Obtain explicit unfiltered absence proof; do not classify these as deleted."
        return "Keep filtered payload out of preview/apply; end-to-end authority is not wired."


def assess_layer_scan(
    *,
    expected_document_identity: str,
    expected_read_id: str,
    before: InsertCensus,
    after: InsertCensus,
    batch: CadObservationBatch,
    batch_read_id: str,
    batch_revision: str,
    tracked_handles: tuple[str, ...],
    absence_proofs: tuple[AbsenceProof, ...] = (),
) -> CensusAssessment:
    """Plan heavy reads and distinguish present/excluded from proven absence.

    Numeric selection uses C1 exactly; legacy selection is intentionally not
    inferred. Every surviving tracked insertion is selected regardless of layer.
    No stale observation is merged, no metadata flags are set and no authoritative
    batch is returned, even when the synthetic evidence is internally consistent.
    """
    problems: list[str] = []
    if not expected_document_identity or not expected_read_id:
        problems.append("EXPLICIT_DOCUMENT_AND_FRESH_READ_REQUIRED")
    if any(
        identity.casefold() != expected_document_identity.casefold()
        for identity in (before.document_identity, after.document_identity, batch.document_identity)
    ):
        problems.append("DOCUMENT_IDENTITY_MISMATCH")
    if any(
        read_id != expected_read_id for read_id in (before.read_id, after.read_id, batch_read_id)
    ):
        problems.append("STALE_READ")
    if not before.revision or not (before.revision == after.revision == batch_revision):
        problems.append("REVISION_DRIFT")
    for census in (before, after):
        if census.complete is not True or census.unfiltered is not True or census.errors:
            problems.append("CENSUS_NOT_COMPLETE_UNFILTERED")
        handles = [entry.handle for entry in census.entries]
        if any(not _valid_handle(h) for h in handles) or len(handles) != len(set(handles)):
            problems.append("CENSUS_HANDLES_INVALID")
        if any(not isinstance(entry.layer, str) for entry in census.entries):
            problems.append("CENSUS_LAYER_INVALID")
    current = {entry.handle: entry.layer for entry in after.entries}
    if {entry.handle: entry.layer for entry in before.entries} != current:
        problems.append("CENSUS_DRIFT")
    if any(not _valid_handle(h) for h in tracked_handles) or len(tracked_handles) != len(
        set(tracked_handles)
    ):
        problems.append("TRACKED_HANDLES_INVALID")
    observed = {item.handle: item.layer for item in batch.observations}
    if len(observed) != len(batch.observations):
        problems.append("DUPLICATE_OBSERVATION_HANDLE")
    if any(handle not in current or current[handle] != layer for handle, layer in observed.items()):
        problems.append("OBSERVATION_CENSUS_DRIFT")
    proof_handles = [proof.handle for proof in absence_proofs]
    if len(proof_handles) != len(set(proof_handles)):
        problems.append("DUPLICATE_ABSENCE_PROOF")
    for proof in absence_proofs:
        if (
            proof.document_identity.casefold() != expected_document_identity.casefold()
            or proof.read_id != expected_read_id
            or proof.revision != after.revision
            or proof.confirmed_absent is not True
            or proof.errors
            or proof.handle not in tracked_handles
            or proof.handle in current
        ):
            problems.append("INVALID_ABSENCE_PROOF")
    if problems:
        # Failed evidence must not contribute either deletion or a heavy-read plan.
        return CensusAssessment(
            tuple(sorted(set(problems))), absent_unknown_handles=tuple(sorted(set(tracked_handles)))
        )

    tracked = set(tracked_handles)
    numeric = {
        handle for handle, layer in current.items() if parse_working_layer_name(layer) is not None
    }
    required = numeric | (tracked & current.keys())
    absent = tracked - current.keys()
    proven = set(proof_handles)
    return CensusAssessment(
        problems=(),
        heavy_read_handles=tuple(sorted(required)),
        missing_observation_handles=tuple(sorted(required - observed.keys())),
        present_excluded_handles=tuple(sorted((tracked & current.keys()) - numeric)),
        absent_unknown_handles=tuple(sorted(absent - proven)),
        proven_absent_handles=tuple(sorted(proven)),
    )


@dataclass(frozen=True, slots=True)
class FilteredSyncContext:
    """Canonical DB owners captured before diagnostic CAD I/O; not write authority."""

    project_id: str
    project_revision: int
    binding_id: str
    document_identity: str
    binding_facts: tuple[tuple[str, str], ...]
    tracked_handles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FilteredSyncReview:
    context: FilteredSyncContext
    batch: CadObservationBatch
    present_excluded_handles: tuple[str, ...]
    absent_unknown_handles: tuple[str, ...]
    status: str = "REQUIRES_ATTENTION"
    next_action: str = (
        "Obtain an authoritative unfiltered preview; excluded insertion ownership "
        "is not established by a layer-selected subset."
    )


@dataclass(frozen=True, slots=True)
class PragmaticApplyCheck:
    """Session-local full-preview context, not atomic or cryptographic DWG proof."""

    project_id: str
    document_identity: str
    project_revision: int
    binding_facts: tuple[tuple[str, str], ...]
    census: tuple[tuple[str, str], ...]
    batch: CadObservationBatch
