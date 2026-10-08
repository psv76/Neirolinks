from types import SimpleNamespace

from nl_project_2.cad_sync import ChangeClass, build_dwg_update_plan
from nl_project_2.cad_sync.models import SyncChange


def _attr(tag, value):
    return SimpleNamespace(tag=tag, value=value)


def _observation(handle, cable_id="", bus_point_id=""):
    attributes = []
    if cable_id:
        attributes.append(_attr("CABLE_ID", cable_id))
    if bus_point_id:
        attributes.append(_attr("BUS_POINT_ID", bus_point_id))
    return SimpleNamespace(
        handle=handle,
        raw_attributes=tuple(attributes),
    )


def _change(
    path,
    handle,
    field,
    change_class,
    *,
    detail_status=None,
    structural=False,
    display_context=None,
):
    return SyncChange(
        field_path=path,
        handle=handle,
        field=field,
        baseline_value=None,
        project_value=None,
        dwg_value=None,
        change_class=change_class,
        reason="Workflow fixture",
        detail_status=detail_status,
        structural=structural,
        display_context=display_context or {},
    )


def _proposal(changes, observations=()):
    return SimpleNamespace(
        changes=tuple(changes),
        batch=SimpleNamespace(observations=tuple(observations)),
    )


def test_one_sided_changes_are_automatic_and_conflicts_are_not():
    proposal = _proposal(
        (
            _change("A:LOAD_NAME", "A", "LOAD_NAME", ChangeClass.DWG_CHANGED),
            _change("B:LOAD_NAME", "B", "LOAD_NAME", ChangeClass.PROJECT_CHANGED),
            _change("C:LOAD_NAME", "C", "LOAD_NAME", ChangeClass.BOTH_CHANGED_CONFLICT),
            _change("D:$", "D", "$", ChangeClass.INVALID_DWG_DATA),
            _change("E:X", "E", "X", ChangeClass.PROJECT_CHANGED),
        )
    )

    plan = build_dwg_update_plan(proposal)

    assert plan.import_paths == frozenset({"A:LOAD_NAME"})
    assert plan.write_paths == frozenset({"B:LOAD_NAME"})
    assert [item.field_path for item in plan.conflicts] == ["C:LOAD_NAME"]
    assert {item.field_path for item in plan.problems} == {"D:$", "E:X"}


def test_new_line_is_never_partially_auto_imported_when_atomic_group_is_blocked():
    proposal = _proposal(
        (
            _change("A:$", "A", "$", ChangeClass.NEW_DWG_INSERTION),
            _change("B:$", "B", "$", ChangeClass.BOTH_CHANGED_CONFLICT),
        ),
        (
            _observation("A", "106.01"),
            _observation("B", "106.02"),
        ),
    )

    plan = build_dwg_update_plan(proposal)

    assert not plan.import_paths
    assert plan.blocked_lines == ("106",)
    assert [item.field_path for item in plan.conflicts] == ["B:$"]


def test_room_canonicalization_and_unresolved_room_stay_explicit():
    canonicalization = _change(
        "A:ROOM",
        "A",
        "ROOM",
        ChangeClass.DWG_CHANGED,
        detail_status="ROOM_CANONICALIZATION",
    )
    unresolved = _change(
        "B:ROOM",
        "B",
        "ROOM",
        ChangeClass.EQUAL,
        display_context={"room_name": "Не разрешено: Дет. ванная 2"},
    )

    plan = build_dwg_update_plan(_proposal((canonicalization, unresolved)))

    assert not plan.import_paths
    assert {item.field_path for item in plan.problems} == {"A:ROOM", "B:ROOM"}


def test_missing_project_bus_root_is_explicit_and_bus_points_are_not_auto_applied():
    proposal = _proposal(
        (
            _change("A:$", "A", "$", ChangeClass.NEW_DWG_INSERTION),
            _change("B:$", "B", "$", ChangeClass.NEW_DWG_INSERTION),
            _change("C:LOAD_NAME", "C", "LOAD_NAME", ChangeClass.DWG_CHANGED),
        ),
        (
            _observation("A", bus_point_id="903.001"),
            _observation("B", bus_point_id="903.002"),
            _observation("C"),
        ),
    )

    plan = build_dwg_update_plan(
        proposal,
        existing_bus_designations=frozenset({"902"}),
    )

    assert plan.missing_bus_roots == ("903",)
    assert plan.import_paths == frozenset({"C:LOAD_NAME"})


def test_existing_project_bus_root_keeps_bus_points_in_automatic_plan():
    proposal = _proposal(
        (_change("A:$", "A", "$", ChangeClass.NEW_DWG_INSERTION),),
        (_observation("A", bus_point_id="903.001"),),
    )

    plan = build_dwg_update_plan(
        proposal,
        existing_bus_designations=frozenset({"903"}),
    )

    assert plan.missing_bus_roots == ()
    assert plan.import_paths == frozenset({"A:$"})


def test_valid_standalone_new_insertion_is_auto_imported_even_when_structural():
    proposal = _proposal(
        (
            _change(
                "ROOT:$",
                "ROOT",
                "$",
                ChangeClass.NEW_DWG_INSERTION,
                structural=True,
            ),
        ),
        (_observation("ROOT"),),
    )

    plan = build_dwg_update_plan(proposal)

    assert plan.import_paths == frozenset({"ROOT:$"})
    assert not plan.problems
