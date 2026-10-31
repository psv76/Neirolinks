"""Q216 guarded full-BOM dry run: replace legacy physical tube sources only."""

from decimal import Decimal

import pytest

from nl_project_2.specification.conduit_source_preview import (
    ConduitSpecificationDecision,
)
from nl_project_2.specification.domain import SpecificationSource, group_sources
from nl_project_2.specification.integrated_conduit_cutover_preview import (
    compose_integrated_conduit_cutover,
)
from nl_project_2.specification.service import SpecificationService


def source(kind: str, sid: str, quantity: str | None = "10") -> SpecificationSource:
    return SpecificationSource(
        kind,
        sid,
        "CONDUIT:PP20:20" if kind in {"CONDUIT", "BUS_SEGMENT_CONDUIT"} else "CABLE:UTP",
        "Труба PP20" if kind in {"CONDUIT", "BUS_SEGMENT_CONDUIT"} else "Кабель UTP",
        None,
        Decimal(quantity) if quantity is not None else None,
        "m",
        "NEIROLINKS",
        True,
        True,
    )


def decision(name: str, q: str | None, status: str = "KNOWN_SINGLE"):
    return ConduitSpecificationDecision(
        conduit_id=name,
        designation=name + ".PP20",
        status=status,
        quantity_m=Decimal(q) if q is not None else None,
        stored_m=Decimal(q) if q is not None else None,
        ordinary_count=1 if status == "KNOWN_SINGLE" else 0,
        bus_count=1 if status == "CANDIDATE_BUS" else 0,
        issues=(),
    )


def trial(legacy=None, replacement=None, decisions=None, linked=None):
    if legacy is None:
        legacy = (
            source("CABLE_LINE", "line-1", "20"),
            source("CONDUIT", "tube-1", "12"),
            source("BUS_SEGMENT_CONDUIT", "bus-segment-1", "7"),
        )
    if replacement is None:
        replacement = (
            source("CONDUIT", "tube-1", "12"),
            source("CONDUIT", "tube-2", "8"),
        )
    if decisions is None:
        decisions = (decision("tube-1", "12"), decision("tube-2", "8", "CANDIDATE_BUS"))
    return compose_integrated_conduit_cutover(
        baseline_sources=legacy,
        replacement_conduits=replacement,
        decisions=decisions,
        assigned_bus_segment_ids=frozenset({"bus-segment-1"} if linked is None else linked),
    )


def test_preserves_cable_sources_replaces_raw_bus_with_one_conduit_and_no_double_count():
    result = trial()
    assert result.preview_only and not result.can_publish
    assert result.legacy_tube_source_count == 2
    assert result.replacement_conduit_source_count == 2
    assert result.orphan_bus_source_ids == ()
    assert not result.issues
    assert [(s.source_kind, s.source_id) for s in result.sources] == [
        ("CABLE_LINE", "line-1"),
        ("CONDUIT", "tube-1"),
        ("CONDUIT", "tube-2"),
    ]
    assert result.sources[0] == source("CABLE_LINE", "line-1", "20")
    rows, issues = group_sources(result.sources)
    assert not issues
    assert next(row for row in rows if row.item_key == "CONDUIT:PP20:20").quantity == Decimal("20")


def test_unlinked_legacy_bus_is_reported_not_silently_lost():
    result = trial(linked=())
    assert result.orphan_bus_source_ids == ("bus-segment-1",)
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.code == "BUS_SEGMENT_WITHOUT_ACTIVE_CONDUIT"
    assert issue.blocking
    assert result.can_publish is False


def test_shared_tube_blocker_has_unknown_quantity_and_explicit_issue():
    replace = (source("CONDUIT", "tube-1", "12"), source("CONDUIT", "tube-2", None))
    decisions = (
        decision("tube-1", "12"),
        decision("tube-2", None, "BLOCKED_UNRESOLVED"),
    )
    result = trial(replacement=replace, decisions=decisions)
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.code == "PHYSICAL_CONDUIT_QUANTITY_BLOCKED"
    assert issue.source_id == "tube-2"
    assert issue.blocking
    rows, _ = group_sources(result.sources)
    assert next(row for row in rows if row.item_key == "CONDUIT:PP20:20").quantity is None


@pytest.mark.parametrize(
    ("replacement", "decisions", "expected"),
    [
        ((source("BUS_SEGMENT_CONDUIT", "tube-1"),), (decision("tube-1", "10"),), "Only"),
        ((source("CONDUIT", "tube-1"),) * 2, (decision("tube-1", "10"),), "Duplicate"),
        ((source("CONDUIT", "tube-1"),), (decision("tube-2", "10"),), "cover"),
        ((source("CONDUIT", "tube-1", "8"),), (decision("tube-1", None, "BLOCKED_UNRESOLVED"),), "Blocked"),
    ],
)
def test_cutover_refuses_malformed_or_falsely_approved_sources(replacement, decisions, expected):
    with pytest.raises(ValueError, match=expected):
        trial(replacement=replacement, decisions=decisions)


def test_integrated_preview_keeps_production_build_unchanged(database):
    service = SpecificationService(database.engine)
    pid = database.test_project_id
    before = service.build(pid)
    preview = service.preview_integrated_conduit_specification(pid)
    assert preview["preview_only"] is True and preview["can_publish"] is False
    assert preview["legacy_tube_source_count"] == 0
    assert preview["physical_conduit_source_count"] == 0
    assert preview["blocked_conduit_ids"] == ()
    assert preview["orphan_bus_segment_ids"] == ()
    assert tuple(preview["sources"]) == tuple(preview["baseline_sources"])
    assert preview["rows"] == before["rows"]
    assert service.build(pid) == before
