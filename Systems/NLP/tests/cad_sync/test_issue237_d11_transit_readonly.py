"""D11 read-only transit evidence; physical route application is not authorized."""

from __future__ import annotations

from types import SimpleNamespace

from test_issue237_d10_track_internal_power import _mounted_light
from test_issue237_passive_physical_ownership import _batch, _box, _track
from test_issue237_physical_dali_storage import _change_observation
from test_issue237_project_bus_context import _insert_root, _project

from nl_project_2.cad_sync import DwgSyncService
from nl_project_2.cad_sync.cable_transit import analyze_cable_transit


def _transit_box(handle: str, transit: str, box_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        ignored_project_data=False,
        read_payload=SimpleNamespace(block_name="EL_BOX_OUT_100x100"),
        normalized_attributes={
            "BOX_ID": box_id,
            "CABLE_TRANSIT": transit,
            "MOUNT_HEIGHT": "2300",
        },
        observation=SimpleNamespace(handle=handle, x=100.0, y=200.0),
    )


def _segment(base: str, *, source: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        base=base,
        source_point_key=source,
        source_reference=None,
        target_point_key=f"{base}/{base}",
    )


def _codes(audit, base: str) -> set[str]:
    return set(next(route for route in audit.routes if route.cable_base == base).issue_codes)


def test_unbroken_single_box_is_only_a_readonly_candidate():
    audit = analyze_cable_transit((_transit_box("A", "301", "BOX.010"),), (_segment("301"),))
    assert not audit.requires_review
    assert audit.issues == ()
    assert len(audit.routes) == 1
    route = audit.routes[0]
    assert route.status == "CANDIDATE"
    assert route.source_point_key is None
    assert route.target_point_key == "301/301"
    assert [(point.box_id, point.ordinal) for point in route.waypoints] == [("BOX.010", None)]
    assert route.waypoints[0].mount_height_mm == "2300"
    assert not hasattr(route, "length_m_decimal")
    assert not hasattr(route, "conduit_id")


def test_numbered_chain_is_deterministic_independent_of_insert_order():
    boxes = (
        _transit_box("B", "301-2", "BOX.020"),
        _transit_box("A", "301-1", "BOX.010"),
    )
    forward = analyze_cable_transit(boxes, (_segment("301"),))
    reverse = analyze_cable_transit(reversed(boxes), (_segment("301"),))
    assert forward == reverse
    assert forward.routes[0].status == "CANDIDATE"
    assert [point.box_id for point in forward.routes[0].waypoints] == [
        "BOX.010",
        "BOX.020",
    ]


def test_empty_transit_is_allowed_and_does_not_create_geometry():
    assert (
        analyze_cable_transit((_transit_box("A", "", "BOX.010"),), (_segment("301"),)).routes == ()
    )


def test_two_power_lines_are_independent_in_one_transit_box():
    audit = analyze_cable_transit(
        (_transit_box("A", "301;302", "BOX.010"),), (_segment("301"), _segment("302"))
    )
    assert [route.status for route in audit.routes] == ["CANDIDATE", "CANDIDATE"]
    assert [route.cable_base for route in audit.routes] == ["301", "302"]


def test_duplicate_or_missing_transit_order_requires_review():
    for boxes, expected in (
        (
            (_transit_box("A", "301-1", "BOX.010"), _transit_box("B", "301-1", "BOX.020")),
            "TRANSIT_ORDER_NOT_CONTIGUOUS",
        ),
        (
            (_transit_box("A", "301", "BOX.010"), _transit_box("B", "301-2", "BOX.020")),
            "TRANSIT_ORDER_AMBIGUOUS",
        ),
        (
            (_transit_box("A", "301-2", "BOX.010"),),
            "TRANSIT_ORDER_NOT_CONTIGUOUS",
        ),
        (
            (_transit_box("A", "301;301", "BOX.010"),),
            "TRANSIT_DUPLICATE_BOX_ENTRY",
        ),
        (
            (_transit_box("A", "301-1", "BOX.010"), _transit_box("B", "301-2", "BOX.010")),
            "TRANSIT_DUPLICATE_PHYSICAL_BOX",
        ),
    ):
        audit = analyze_cable_transit(boxes, (_segment("301"),))
        assert audit.requires_review
        assert expected in _codes(audit, "301")


def test_ambiguous_branch_does_not_create_a_guessed_path():
    audit = analyze_cable_transit(
        (_transit_box("A", "301", "BOX.010"),),
        (_segment("301"), _segment("301", source="301/301")),
    )
    assert audit.routes[0].status == "REVIEW"
    assert "TRANSIT_PATH_REQUIRES_REVIEW" in _codes(audit, "301")
    assert audit.routes[0].source_point_key is None
    assert audit.routes[0].target_point_key is None


def test_missing_line_only_blocks_that_line_not_independent_route():
    audit = analyze_cable_transit((_transit_box("A", "301;302", "BOX.010"),), (_segment("301"),))
    assert [route.status for route in audit.routes] == ["CANDIDATE", "REVIEW"]
    assert "TRANSIT_CABLE_LINE_NOT_PRESENT" in _codes(audit, "302")


def test_invalid_legacy_tokens_are_reported_not_silently_dropped():
    audit = analyze_cable_transit(
        (_transit_box("A", "301@1;;905;303-0;302", "BOX.010"),),
        (_segment("301"), _segment("302")),
    )
    assert [issue.value for issue in audit.issues] == [
        "",
        "301@1",
        "303-0",
        "905",
    ]
    assert audit.requires_review
    assert audit.routes[0].cable_base == "302"


def test_unknown_upstream_blocks_candidate_without_guessing():
    segment = SimpleNamespace(
        base="301",
        source_reference="BOX.999",
        source_point_key=None,
        target_point_key="301/301",
    )
    audit = analyze_cable_transit((_transit_box("A", "301", "BOX.010"),), (segment,))
    assert "TRANSIT_SOURCE_UNRESOLVED" in _codes(audit, "301")
    assert audit.routes[0].status == "REVIEW"


def test_actual_scan_proposal_exposes_readonly_review_without_sqlite_changes(database):
    pid = _project(database)
    _insert_root(database, pid)
    before = database.path.read_bytes()
    physical_box = _change_observation(_box(), "CABLE_TRANSIT", "401")
    proposal = DwgSyncService(database.engine).preview(
        project_id=pid, batch=_batch(physical_box, _track(), _mounted_light())
    )
    assert len(proposal.transit_audit.routes) == 1
    route = proposal.transit_audit.routes[0]
    assert route.cable_base == "401"
    assert route.status == "REVIEW"
    assert "TRANSIT_PATH_REQUIRES_REVIEW" in route.issue_codes
    assert database.path.read_bytes() == before
