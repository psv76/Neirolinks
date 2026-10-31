"""Q216 one physical Conduit -> one non-publishable specification source."""

from decimal import Decimal

import pytest

from nl_project_2.cables.bus_conduit_preview import BusConduitQuantityPreview
from nl_project_2.cables.conduit_audit import ConduitAudit
from nl_project_2.cables.physical_conduit import PhysicalBoundary, PhysicalSpan
from nl_project_2.specification.conduit_source_preview import plan_conduit_specification
from nl_project_2.specification.service import SpecificationService


def uid(n):
    return f"00000000-0000-4000-8000-{n:012d}"


SPAN = PhysicalSpan(
    PhysicalBoundary("BOARD", uid(1)),
    PhysicalBoundary("FIELD_DEVICE", uid(2)),
)


def tube(n=10, *, geometry="12", origin="AUTO_SEGMENT"):
    return {
        "id": uid(n),
        "designation": f"{n:03d}.PP20",
        "length_m_decimal": geometry,
        "path_json": {"origin": origin},
    }


def audit(n=10, *, status="PHYSICAL_MATCH", members=None, span=SPAN):
    if members is None:
        members = (("CABLE", uid(30)),)
    return ConduitAudit(
        uid(n),
        status,
        tuple(members),
        span if status == "PHYSICAL_MATCH" else None,
        (),
    )


def bus_preview(n=20, *, status="CANDIDATE", amount=Decimal("8")):
    return BusConduitQuantityPreview(
        conduit_id=uid(n),
        designation=f"{n:03d}.PP20",
        status=status,
        bus_segment_id=uid(40),
        geometry_m=Decimal("7.02656"),
        automatic_m=amount,
        issues=() if status == "CANDIDATE" else ("BUS_GEOMETRY_MISSING",),
    )


def plan(tubes, audits, previews=()):
    return plan_conduit_specification(
        conduits=tuple(tubes),
        audits=tuple(audits),
        bus_previews=tuple(previews),
    )


def test_single_ordinary_and_single_bus_have_distinct_conduit_sources():
    ordinary = tube()
    bus = tube(20, geometry=None, origin="AUTO_BUS_SEGMENT")
    decisions = plan(
        (ordinary, bus),
        (audit(), audit(20, members=(("BUS", uid(40)),))),
        (bus_preview(),),
    )
    assert len(decisions) == 2
    assert len({d.conduit_id for d in decisions}) == 2
    assert {d.status for d in decisions} == {"KNOWN_SINGLE", "CANDIDATE_BUS"}
    assert {d.conduit_id: d.quantity_m for d in decisions} == {
        uid(10): Decimal("12"),
        uid(20): Decimal("8"),
    }
    assert all(d.can_publish is False for d in decisions)


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", None])
def test_invalid_or_missing_ordinary_length_never_turns_to_zero(value):
    result = plan((tube(geometry=value),), (audit(),))[0]
    assert result.status == "BLOCKED_UNKNOWN_LENGTH"
    assert result.quantity_m is None
    assert not result.can_publish


def test_empty_ordinary_with_stored_length_and_empty_bus_are_blocked():
    decisions = plan(
        (tube(geometry="15"), tube(20, geometry=None, origin="AUTO_BUS_SEGMENT")),
        (audit(status="EMPTY", members=()), audit(20, status="EMPTY", members=())),
    )
    assert len(decisions) == 2
    assert all(d.status == "BLOCKED_EMPTY" and d.quantity_m is None for d in decisions)
    assert decisions[0].stored_m == Decimal("15")
    assert "EMPTY_WITH_SAVED_LENGTH" in decisions[0].issues
    assert "EMPTY_WITHOUT_MEMBER" in decisions[1].issues


def test_shared_ordinary_and_bus_never_double_count_even_when_span_matches():
    result = plan(
        (tube(),),
        (audit(members=(("CABLE", uid(30)), ("BUS", uid(40)))),),
    )[0]
    assert result.status == "BLOCKED_SHARED"
    assert result.quantity_m is None
    assert "MULTIPLE_MEMBERS_REQUIRE_Q03_Q06_COMPATIBILITY" in result.issues


@pytest.mark.parametrize("status", ["BOUNDARY_CONFLICT", "UNRESOLVED"])
def test_unresolved_canonical_owners_block_even_with_stored_number(status):
    result = plan((tube(),), (audit(status=status),))[0]
    assert result.status == "BLOCKED_UNRESOLVED"
    assert result.quantity_m is None
    assert f"Q03_{status}" in result.issues


def test_malformed_physical_match_without_span_blocks():
    result = plan((tube(),), (audit(span=None),))[0]
    assert result.status == "BLOCKED_UNRESOLVED"
    assert result.quantity_m is None


def test_bus_must_have_explicit_candidate_not_existing_or_guessed_number():
    target = tube(20, geometry=None, origin="AUTO_BUS_SEGMENT")
    bus_audit = audit(20, members=(("BUS", uid(40)),))
    for previews in ((), (bus_preview(status="BLOCKED", amount=None),)):
        result = plan((target,), (bus_audit,), previews)[0]
        assert result.status == "BLOCKED_BUS"
        assert result.quantity_m is None
        assert not result.can_publish
    result = plan(
        (tube(20, geometry="7", origin="AUTO_BUS_SEGMENT"),),
        (bus_audit,),
        (bus_preview(),),
    )[0]
    assert result.status == "BLOCKED_BUS"
    assert result.quantity_m is None


def test_bus_origin_with_ordinary_member_is_not_trusted():
    result = plan(
        (tube(origin="AUTO_BUS_SEGMENT"),),
        (audit(),),
    )[0]
    assert result.status == "BLOCKED_BUS"
    assert result.quantity_m is None


@pytest.mark.parametrize(
    ("tubes", "audits", "previews", "message"),
    [
        ((tube(), tube()), (audit(),), (), "Duplicate active"),
        ((tube(),), (audit(), audit()), (), "Duplicate Q03"),
        ((tube(),), (), (), "cover exactly"),
        ((tube(),), (audit(),), (bus_preview(),), "unknown Conduit"),
        ((tube(),), (audit(),), (bus_preview(10), bus_preview(10)), "Duplicate Q03"),
    ],
)
def test_stale_or_duplicate_snapshot_is_refused(tubes, audits, previews, message):
    with pytest.raises(ValueError, match=message):
        plan(tubes, audits, previews)


def test_shadow_api_does_not_modify_existing_specification(database):
    service = SpecificationService(database.engine)
    project_id = database.test_project_id
    original = service.build(project_id)
    candidate = service.preview_single_conduit_specification(project_id)
    assert candidate["preview_only"] is True
    assert candidate["can_publish"] is False
    assert candidate["decisions"] == ()
    assert candidate["sources"] == ()
    assert candidate["blocked_conduit_ids"] == ()
    assert service.build(project_id) == original
