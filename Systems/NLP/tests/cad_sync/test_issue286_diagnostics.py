"""Global validation and transaction errors remain distinct and untruncated."""

from nl_project_2.cad_contract import CadObservationBatch, IssueSeverity, ValidationIssue
from nl_project_2.cad_sync.diagnostics import (
    apply_failure_evidence,
    apply_failure_message,
    preview_evidence,
)
from nl_project_2.cad_sync.models import ScanProposal, SyncSummary
from nl_project_2.operations.diagnostics import StructuredLogger


def test_global_blocker_and_full_failure_reason_survive_structured_log(tmp_path):
    proposal = ScanProposal(
        project_id="synthetic-project",
        batch=CadObservationBatch("synthetic.dwg", ()),
        changes=(),
        issues=(ValidationIssue("GLOBAL_GATE", "Rescan required", IssueSeverity.ERROR, True),),
        summary=SyncSummary(),
        project_revision=4,
        binding_id="synthetic-binding",
    )
    assert "GLOBAL_GATE [весь импорт]" in preview_evidence(proposal)
    error = RuntimeError("source evidence " * 100 + "EXACT_END")
    summary = apply_failure_evidence(proposal, {"A:$"}, error)
    event = StructuredLogger(tmp_path / "apply.jsonl").record(
        level="ERROR",
        component="dwg_sync",
        operation="decision_apply",
        result="failed",
        duration_ms=0,
        error=error,
        summary=summary,
    )
    assert event["summary"]["status"] == "NOT_APPLIED"
    assert event["summary"]["reason"].endswith("EXACT_END")
    assert apply_failure_message(error).endswith("EXACT_END")
    assert summary["selected_insertion_count"] == 0
    assert summary["binding_id"] == "synthetic-binding"
