from dataclasses import replace
from types import SimpleNamespace

import pytest

from nl_project_2.cad_contract import CadObservation, CadObservationBatch
from nl_project_2.cad_contract.layer_names import parse_working_layer_name
from nl_project_2.cad_sync import DwgSyncError, DwgSyncService
from nl_project_2.cad_sync.reconciliation_safety import is_authoritative_scan_metadata
from nl_project_2.cad_sync.scan_layer_safety import (
    AbsenceProof,
    CensusEntry,
    InsertCensus,
    assess_layer_scan,
)

DOC = "C:/fixture/synthetic.dwg"


DEFAULT_ENTRIES = (CensusEntry("A1", "300_Light"),)


def inputs(entries=DEFAULT_ENTRIES, observed=True):
    census = InsertCensus(DOC, "read-1", "revision-1", entries, complete=True, unfiltered=True)
    observations = (
        tuple(
            CadObservation.from_mapping(
                effective_name="DALI_GROUP",
                layer=entry.layer,
                handle=entry.handle,
                raw_attributes={"DALI_GROUP_ID": "D.001"},
                x=1,
                y=2,
            )
            for entry in entries
        )
        if observed
        else ()
    )
    return dict(
        expected_document_identity=DOC,
        expected_read_id="read-1",
        before=census,
        after=census,
        batch=CadObservationBatch(
            DOC,
            observations,
            {"layer_filter_applied": True, "scan_is_complete_for_reconciliation": False},
        ),
        batch_read_id="read-1",
        batch_revision="revision-1",
        tracked_handles=("A1",),
    )


@pytest.mark.parametrize(
    "layer", ["ARCH", "POWER", "DALI_GROUPS", "350_X", "300_", "300_ Light", "400_Light "]
)
def test_moved_off_layer_is_present_and_requires_heavy_read(layer):
    args = inputs((CensusEntry("A1", layer),), observed=False)
    result = assess_layer_scan(**args)
    assert result.status == "REQUIRES_ATTENTION"
    assert result.heavy_read_handles == result.missing_observation_handles == ("A1",)
    assert result.present_excluded_handles == ("A1",)
    assert result.proven_absent_handles == result.absent_unknown_handles == ()
    assert "including tracked inserts" in result.next_action


def test_absence_is_unknown_without_explicit_proof():
    result = assess_layer_scan(**inputs((), observed=False))
    assert result.absent_unknown_handles == ("A1",)
    assert result.proven_absent_handles == ()
    assert result.status == "REQUIRES_ATTENTION"


def test_true_deletion_requires_fresh_unfiltered_individual_proof():
    args = inputs((), observed=False)
    args["absence_proofs"] = (AbsenceProof(DOC, "read-1", "revision-1", "A1", True),)
    result = assess_layer_scan(**args)
    assert result.proven_absent_handles == ("A1",)
    assert result.absent_unknown_handles == ()
    assert result.status == "STAGED_ONLY"
    assert not is_authoritative_scan_metadata(args["batch"].source_metadata)


@pytest.mark.parametrize(
    "changes",
    [
        {"read_id": "stale"},
        {"revision": "old"},
        {"document_identity": "other.dwg"},
        {"confirmed_absent": False},
        {"confirmed_absent": 1},
        {"errors": ("COM lookup failed",)},
        {"handle": "B2"},
    ],
)
def test_bad_absence_proof_cannot_delete(changes):
    args = inputs((), observed=False)
    args["absence_proofs"] = (
        replace(AbsenceProof(DOC, "read-1", "revision-1", "A1", True), **changes),
    )
    result = assess_layer_scan(**args)
    assert result.status == "REQUIRES_ATTENTION"
    assert result.proven_absent_handles == ()
    assert "INVALID_ABSENCE_PROOF" in result.problems


def test_present_handle_overrules_claimed_deletion():
    args = inputs((CensusEntry("A1", "ARCH"),), observed=False)
    args["absence_proofs"] = (AbsenceProof(DOC, "read-1", "revision-1", "A1", True),)
    assert assess_layer_scan(**args).proven_absent_handles == ()
    assert "INVALID_ABSENCE_PROOF" in assess_layer_scan(**args).problems


@pytest.mark.parametrize(
    "layer",
    [
        "100_Power",
        "200_Keys",
        "300_Свет",
        "400_DALI",
        "500_Sensors",
        "600_HVAC",
        "700_AV",
        "800_SCS",
        "900_Bus",
        "300__",
        "ARCH",
        "POWER",
        "350_X",
        "300_",
        "300_ Light",
        "400_Light ",
    ],
)
def test_numeric_selection_uses_c1_and_does_not_assume_block_ownership(layer):
    args = inputs((CensusEntry("B2", layer),), observed=False)
    args["tracked_handles"] = ()
    result = assess_layer_scan(**args)
    assert result.heavy_read_handles == (
        ("B2",) if parse_working_layer_name(layer) is not None else ()
    )
    assert result.proven_absent_handles == ()


@pytest.mark.parametrize(
    "field,changes,code",
    [
        ("before", {"complete": False}, "CENSUS_NOT_COMPLETE_UNFILTERED"),
        ("after", {"complete": 1}, "CENSUS_NOT_COMPLETE_UNFILTERED"),
        ("after", {"unfiltered": False}, "CENSUS_NOT_COMPLETE_UNFILTERED"),
        ("before", {"errors": ("LISP failed",)}, "CENSUS_NOT_COMPLETE_UNFILTERED"),
        ("after", {"errors": ("COM failed",)}, "CENSUS_NOT_COMPLETE_UNFILTERED"),
        ("after", {"read_id": "old"}, "STALE_READ"),
        ("after", {"document_identity": "other"}, "DOCUMENT_IDENTITY_MISMATCH"),
        ("after", {"revision": "new"}, "REVISION_DRIFT"),
        ("before", {"entries": ()}, "CENSUS_DRIFT"),
        ("after", {"entries": (CensusEntry("A1", "ARCH"),)}, "CENSUS_DRIFT"),
        ("after", {"entries": (CensusEntry("A1", "300_Light"),) * 2}, "CENSUS_HANDLES_INVALID"),
        ("after", {"entries": (CensusEntry("", "300_Light"),)}, "CENSUS_HANDLES_INVALID"),
    ],
)
def test_failed_stale_or_duplicate_census_fails_closed(field, changes, code):
    args = inputs()
    args[field] = replace(args[field], **changes)
    result = assess_layer_scan(**args)
    assert code in result.problems
    assert result.status == "REQUIRES_ATTENTION"
    assert result.heavy_read_handles == result.proven_absent_handles == ()


@pytest.mark.parametrize(
    "change", ["layer", "handle", "duplicate", "document", "revision", "read_id"]
)
def test_heavy_payload_drift_is_blocking(change):
    args = inputs()
    if change in {"layer", "handle", "duplicate"}:
        observation = args["batch"].observations[0]
        observations = (
            (observation, observation)
            if change == "duplicate"
            else (replace(observation, **{change: "OTHER"}),)
        )
        args["batch"] = replace(args["batch"], observations=observations)
    elif change == "document":
        args["batch"] = replace(args["batch"], document_identity="other")
    else:
        args[f"batch_{change}"] = "stale"
    assert assess_layer_scan(**args).status == "REQUIRES_ATTENTION"
    assert assess_layer_scan(**args).proven_absent_handles == ()


def test_complete_synthetic_match_never_upgrades_filtered_batch_or_bypasses_c6():
    args = inputs()
    batch = args["batch"]
    metadata = dict(batch.source_metadata)
    result = assess_layer_scan(**args)
    assert result.status == "STAGED_ONLY"
    assert batch.source_metadata == metadata
    assert not is_authoritative_scan_metadata(batch.source_metadata)

    def forbidden(*args, **kwargs):
        pytest.fail("Filtered census assessment reached DB or validator")

    service = DwgSyncService(SimpleNamespace(connect=forbidden, begin=forbidden))
    with pytest.raises(DwgSyncError, match="SCAN_NOT_AUTHORITATIVE"):
        service.preview(project_id="synthetic", batch=batch)
    with pytest.raises(DwgSyncError, match="SCAN_NOT_AUTHORITATIVE"):
        service.apply_dwg_to_project(
            SimpleNamespace(batch=batch), selected_paths=(), confirmed=True
        )


@pytest.mark.parametrize("handle", ["a1", " A1", "A1 ", "", "NOT-HEX"])
def test_noncanonical_owner_handles_fail_closed(handle):
    args = inputs()
    args["tracked_handles"] = (handle,)
    result = assess_layer_scan(**args)
    assert "TRACKED_HANDLES_INVALID" in result.problems
    assert result.proven_absent_handles == ()


def test_duplicate_proofs_and_duplicate_tracked_owners_fail_closed():
    args = inputs((), observed=False)
    proof = AbsenceProof(DOC, "read-1", "revision-1", "A1", True)
    args["absence_proofs"] = (proof, proof)
    assert "DUPLICATE_ABSENCE_PROOF" in assess_layer_scan(**args).problems
    args["absence_proofs"] = ()
    args["tracked_handles"] = ("A1", "A1")
    assert "TRACKED_HANDLES_INVALID" in assess_layer_scan(**args).problems


@pytest.mark.parametrize("key", ["expected_document_identity", "expected_read_id"])
def test_missing_explicit_read_context_never_proves_deletion(key):
    args = inputs((), observed=False)
    args[key] = ""
    assert assess_layer_scan(**args).status == "REQUIRES_ATTENTION"
    assert assess_layer_scan(**args).proven_absent_handles == ()
