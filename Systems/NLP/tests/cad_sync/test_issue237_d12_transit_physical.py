"""D12 physical transit length/conduit planning: no implicit electrical edits."""

from __future__ import annotations

from decimal import Decimal

import pytest
from test_issue237_d11_transit_readonly import _segment, _transit_box

from nl_project_2.cables.domain import CablePointInput
from nl_project_2.cad_sync.cable_transit import analyze_cable_transit
from nl_project_2.cad_sync.transit_physical import (
    ApprovedSpanRoute,
    TransitCalculationPolicy,
    VerifiedLocation,
    build_physical_transit_routes,
    measure_physical_transit,
)


def _route(*boxes, base="301"):
    audit = analyze_cable_transit(boxes, (_segment(base),))
    return build_physical_transit_routes(audit)[0]


def _point(x, y, *, height=2300, base_mark=-250, room_height=3):
    return CablePointInput.from_values(
        x_mm=x,
        y_mm=y,
        mount_height_mm=height,
        base_mark_mm=base_mark,
        room_height_m=room_height,
    )


def _where(x, y, *, height=2300):
    return VerifiedLocation(
        _point(x, y, height=height), evidence="verified-room-and-CAD", confirmed=True
    )


def _policy():
    return TransitCalculationPolicy(
        p_nonlinearity=Decimal("0.05"),
        p_bypass=Decimal("0.10"),
        rounding_m=Decimal("1"),
        board_reserve_m=Decimal("3"),
        terminated_ends_reserve_m=Decimal("0.3"),
        additional_m=Decimal("0"),
    )


def _decisions(route, *, method="В стене", conduit=True):
    return {
        span.physical_key: ApprovedSpanRoute(
            mount_way=method,
            gofra_type="ПНД25" if conduit else "",
            gofra_color="чёрная" if conduit else "",
            gofra_id=f"{index:03d}.PND25" if conduit else "",
            confirmed=True,
        )
        for index, span in enumerate(route.spans, start=1)
    }


def test_unspliced_box_creates_two_distinct_physical_spans_and_one_end_allowance():
    route = _route(_transit_box("A", "301", "BOX.010"))
    assert route.status == "CANDIDATE"
    assert [(span.start, span.finish) for span in route.spans] == [
        ("301/$SOURCE", "BOX.010"),
        ("BOX.010", "301/301"),
    ]
    readings = {
        "301/$SOURCE": _where(0, 0),
        "BOX.010": _where(100, 200),
        "301/301": _where(1100, 200),
    }
    result = measure_physical_transit(
        (route,),
        locations=readings,
        decisions=_decisions(route),
        policy=_policy(),
    )[0]
    assert result.status == "MEASURED"
    assert [part.geometry_m for part in result.measured] == [
        Decimal("0.3"),
        Decimal("1"),
    ]
    assert result.cable_length_m == Decimal("5")
    assert [(item.designation, item.measured_m) for item in result.conduits] == [
        ("001.PND25", Decimal("1")),
        ("002.PND25", Decimal("2")),
    ]
    # There is no physical splice at BOX.010. The 0.20 m box
    # termination allowance cannot be inferred from a transit waypoint.
    assert not hasattr(result, "box_splice_allowance_m")


def test_ceiling_uses_clean_floor_R_not_negative_concrete_B():
    route = _route(_transit_box("A", "301", "BOX.010"))
    where = {
        "301/$SOURCE": _where(100, 200, height=1000),
        "BOX.010": _where(100, 200),
        "301/301": _where(1100, 200, height=1000),
    }
    measured = measure_physical_transit(
        (route,),
        locations=where,
        decisions=_decisions(route, method="По потолку", conduit=False),
        policy=_policy(),
    )[0]
    assert measured.status == "MEASURED"
    assert [p.geometry_m for p in measured.measured] == [
        Decimal("2.7"),
        Decimal("3.7"),
    ]
    assert measured.cable_length_m == Decimal("11")


def test_timbers_have_no_legacy_half_metre_added_per_span():
    route = _route(_transit_box("A", "301", "BOX.010"))
    where = {
        "301/$SOURCE": _where(0, 200),
        "BOX.010": _where(100, 200),
        "301/301": _where(1100, 200),
    }
    decisions = {
        span.physical_key: ApprovedSpanRoute(
            mount_way="В брусе", gofra_type="ППЛ20",
            gofra_id=f"{idx:03d}.PP20", confirmed=True,
        )
        for idx, span in enumerate(route.spans, start=1)
    }
    measured = measure_physical_transit(
        (route,), locations=where, decisions=decisions, policy=_policy()
    )[0]
    assert measured.status == "MEASURED"
    assert sum((x.geometry_m for x in measured.measured), Decimal(0)) == Decimal("1.1")
    assert measured.cable_length_m == Decimal("5")


@pytest.mark.parametrize("problem", ["approval", "location", "box_mismatch", "conduit"])
def test_no_guessed_route_or_conduit_when_evidence_missing(problem):
    route = _route(_transit_box("A", "301", "BOX.010"))
    locations = {
        "301/$SOURCE": _where(0, 0),
        "BOX.010": _where(100, 200),
        "301/301": _where(1100, 200),
    }
    decisions = _decisions(route)
    if problem == "approval":
        decisions[route.spans[0].physical_key] = ApprovedSpanRoute(mount_way="В стене")
    elif problem == "location":
        locations.pop("301/301")
    elif problem == "box_mismatch":
        locations["BOX.010"] = _where(999, 999)
    elif problem == "conduit":
        decisions[route.spans[0].physical_key] = ApprovedSpanRoute(
            mount_way="По полу", gofra_type="ПНД25", confirmed=True,
        )
    result = measure_physical_transit(
        (route,), locations=locations, decisions=decisions, policy=_policy()
    )[0]
    assert result.status == "REVIEW"
    assert result.cable_length_m is None
    assert result.conduits == ()


def test_repeated_conduit_id_across_different_boundaries_refuses_entire_line():
    route = _route(_transit_box("A", "301", "BOX.010"))
    decisions = _decisions(route)
    decisions[route.spans[1].physical_key] = ApprovedSpanRoute(
        mount_way="В стене", gofra_type="ПНД25",
        gofra_color="чёрная", gofra_id="001.PND25", confirmed=True,
    )
    result = measure_physical_transit(
        (route,),
        locations={
            "301/$SOURCE": _where(0, 0),
            "BOX.010": _where(100, 200),
            "301/301": _where(1100, 200),
        },
        decisions=decisions,
        policy=_policy(),
    )[0]
    assert result.status == "REVIEW"
    assert "TRANSIT_CONDUIT_BOUNDARY_CONFLICT" in result.issue_codes
    assert result.cable_length_m is None


def test_branch_ambiguity_produces_no_physical_spans():
    audit = analyze_cable_transit(
        (_transit_box("A", "301", "BOX.010"),),
        (_segment("301"), _segment("301")),
    )
    route = build_physical_transit_routes(audit)[0]
    assert route.status == "REVIEW"
    assert route.spans == ()
    assert "TRANSIT_PATH_REQUIRES_REVIEW" in route.issue_codes


def test_invalid_policy_rejected_before_any_measurement():
    route = _route(_transit_box("A", "301", "BOX.010"))
    policy = TransitCalculationPolicy(
        p_nonlinearity=Decimal("0.05"),
        p_bypass=Decimal("0.10"),
        rounding_m=Decimal("0"),
        board_reserve_m=Decimal("3"),
        terminated_ends_reserve_m=Decimal("0.3"),
        additional_m=Decimal(0),
    )
    with pytest.raises(ValueError, match="TRANSIT_POLICY_UNVERIFIED"):
        measure_physical_transit((route,), locations={}, decisions={}, policy=policy)
