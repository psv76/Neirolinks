"""Synthetic reproduction only; run with basetemp under issue-286-ethernet."""

import pytest
from sqlalchemy import event, select, update
from test_issue237_bus_outlet_owner_gate import _outlet
from test_issue237_project_bus_context import _insert_root
from test_sync_service import _applicable, _batch, _project, _socket

from nl_project_2.cad_contract import BlockDefinitionMetadata, CadObservation, load_contract
from nl_project_2.cad_sync import ChangeClass, DwgSyncError, DwgSyncService
from nl_project_2.cad_sync.diagnostics import (
    apply_failure_evidence,
    apply_failure_message,
    preview_evidence,
)
from nl_project_2.cad_sync.workflow import build_dwg_update_plan
from nl_project_2.persistence.schema import bus_endpoint, cable_line, field_device


def _ethernet(number):
    name = "CONTROL_PANEL_4" if number < 830 else "SOCKET_ETHERNET"
    rule = load_contract().block(name)
    attrs = {tag: "" for tag in rule.required_definition_attributes}
    attrs.update(
        DEVICE_NAME=f"Ethernet {number}",
        CABLE_ID=str(number),
        CABLE_TYPE="FTP 5e",
        BOARD="B.01",
        BUILDING="Building",
        ROOM="Room",
        MOUNT_HEIGHT="300",
        MOUNT_WAY="По потолку",
    )
    if rule.allowed_load_types:
        attrs["LOAD_TYPE"] = sorted(rule.allowed_load_types)[0]
    return CadObservation.from_mapping(
        effective_name=name,
        layer="800_Ethernet",
        handle=f"E{number}",
        x=number,
        y=0,
        raw_attributes=attrs,
        definition=BlockDefinitionMetadata(tuple(attrs)),
    )


def _state(database):
    # All rows, including journals, baselines and correlated topology.
    with database.engine.connect() as conn:
        return {
            table.name: conn.execute(select(table)).all()
            for table in cable_line.metadata.sorted_tables
        }


@pytest.mark.parametrize("failure", ["none", "duplicate_color", "accepted_owner_mismatch"])
def test_ethernet_18_candidates_and_transaction_boundary(database, failure, qtbot):
    pid = _project(database)
    _insert_root(database, pid, designation="906", kind="DALI")
    service = DwgSyncService(database.engine)
    existing = tuple(_ethernet(n) for n in (*range(801, 814), *range(830, 857)))
    bus_row = _outlet(handle="BUS906", point_id="906.001", source="906.000")
    initial = service.preview(project_id=pid, batch=_batch(*existing, bus_row))
    assert initial.can_apply, initial.issues
    service.apply_dwg_to_project(initial, selected_paths=_applicable(initial), confirmed=True)
    extra = ()
    if failure != "none":
        extra = (
            _socket(handle="COLOR1", cable_id="101", gofra_color="Черный"),
            _socket(handle="COLOR2", cable_id="102", gofra_color="Синий"),
        )
    if failure == "duplicate_color":
        extra += (_outlet(handle="DUP906", point_id="906.001", source="906.000"),)
    if failure == "accepted_owner_mismatch":
        # Explicitly inconsistent accepted fixture; no claim this is the live DB state.
        with database.engine.begin() as conn:
            conn.execute(
                update(bus_endpoint)
                .where(bus_endpoint.c.project_id == pid)
                .values(address="906.002")
            )
    before = _state(database)
    batch = _batch(*existing, *(_ethernet(n) for n in range(857, 875)), bus_row, *extra)
    proposal = service.preview(project_id=pid, batch=batch)
    candidates = [c for c in proposal.changes if c.change_class is ChangeClass.NEW_DWG_INSERTION]
    assert len(candidates) == 18
    assert {c.dwg_value["CABLE_ID"] for c in candidates} == {str(n) for n in range(857, 875)}
    assert _state(database) == before
    evidence = preview_evidence(proposal)
    assert "NEW_DWG_INSERTION в исходном preview: 18" in evidence
    assert all(f"{n} (Handle E{n})" in evidence for n in range(857, 875))
    from nl_project_2.presentation.object_workspace import DwgSyncResolutionDialog

    dialog = DwgSyncResolutionDialog(proposal, build_dwg_update_plan(proposal))
    qtbot.addWidget(dialog)
    assert dialog.candidate_evidence.toPlainText() == evidence
    assert _state(database) == before
    if failure == "duplicate_color":
        codes = {issue.code for issue in proposal.issues}
        assert {"DUPLICATE_BUS_POINT_ID", "CONDUIT_COLOR_INCONSISTENT"} <= codes
        assert all(
            issue.handle or issue.related_handles
            for issue in proposal.issues
            if issue.code in {"DUPLICATE_BUS_POINT_ID", "CONDUIT_COLOR_INCONSISTENT"}
        )
    if failure == "accepted_owner_mismatch":
        statements = []

        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(database.engine, "before_cursor_execute", capture)
        try:
            with pytest.raises(
                DwgSyncError, match="BUS_POINT_ID_RENUMBER_REQUIRES_ATTENTION:906:906.001"
            ) as caught:
                service.apply_dwg_to_project(
                    proposal, selected_paths=_applicable(proposal), confirmed=True
                )
        finally:
            event.remove(database.engine, "before_cursor_execute", capture)
        assert any(s.startswith("INSERT INTO cable_line") for s in statements)
        diagnostic = apply_failure_evidence(proposal, _applicable(proposal), caught.value)
        assert diagnostic["selected_insertion_count"] == 18
        assert diagnostic["status"] == "NOT_APPLIED"
        assert diagnostic["project_id"] == pid
        assert "906:906.001" in diagnostic["reason"]
        assert "906:906.001" in apply_failure_message(caught.value)
        assert "CONDUIT_COLOR_INCONSISTENT" in evidence
        assert _state(database) == before
        return
    service.apply_dwg_to_project(proposal, selected_paths=_applicable(proposal), confirmed=True)
    after = _state(database)
    assert all(row in after["cable_line"] for row in before["cable_line"])
    assert all(row in after["field_device"] for row in before["field_device"])
    assert after["bus_endpoint"] == before["bus_endpoint"]
    assert after["bus_segment"] == before["bus_segment"]
    assert after["conduit"] == before["conduit"]
    with database.engine.connect() as conn:
        lines = conn.execute(select(cable_line)).mappings().all()
        assert len(lines) == 58
        assert {row["project_id"] for row in lines} == {pid}
        devices = conn.execute(select(field_device)).mappings().all()
        assert len({row["dwg_document_binding_id"] for row in devices}) == 1
    replay = service.preview(project_id=pid, batch=batch)
    assert not _applicable(replay)
    assert _state(database) == after


def test_selected_new_ethernet_does_not_reassign_accepted_bus_conduits(database):
    # An existing accepted BUS with a conduit is not an implicit side effect
    # of an unrelated Ethernet-only Apply.
    pid = _project(database)
    _insert_root(database, pid, designation="906", kind="DALI")
    service = DwgSyncService(database.engine)
    bus_observation = _outlet(handle="BUS906", point_id="906.001", source="906.000")
    attributes = {item.tag: item.value for item in bus_observation.raw_attributes}
    attributes.update(BUS_GOFRA_TYPE="ППЛ20", BUS_GOFRA_COLOR="Синий")
    bus_observation = CadObservation.from_mapping(
        effective_name="CABLE_OUTLET_BUS",
        layer="BUS",
        handle="BUS906",
        x=100,
        y=200,
        raw_attributes=attributes,
        definition=BlockDefinitionMetadata(tuple(attributes)),
    )
    initial = service.preview(project_id=pid, batch=_batch(_ethernet(830), bus_observation))
    assert initial.can_apply, initial.issues
    service.apply_dwg_to_project(initial, selected_paths=_applicable(initial), confirmed=True)
    before = _state(database)
    assert before["bus_segment_conduit_assignment"], (
        "Fixture must persist at least one BUS conduit assignment before Ethernet update"
    )
    assert before["conduit"]
    updated = service.preview(
        project_id=pid, batch=_batch(_ethernet(830), _ethernet(857), bus_observation)
    )
    inserted = [
        c.field_path
        for c in updated.changes
        if c.change_class is ChangeClass.NEW_DWG_INSERTION and c.handle == "E857"
    ]
    assert inserted == ["E857:$"]
    service.apply_dwg_to_project(updated, selected_paths=inserted, confirmed=True)
    after = _state(database)
    assert after["bus_endpoint"] == before["bus_endpoint"]
    assert after["bus_segment"] == before["bus_segment"]
    assert after["bus_segment_conduit_assignment"] == before["bus_segment_conduit_assignment"]
    assert all(row in after["conduit"] for row in before["conduit"])
    assert len(after["cable_line"]) == len(before["cable_line"]) + 1
