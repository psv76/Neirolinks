import pytest
from sqlalchemy import func, select, update

from nl_project_2.buses import BusService
from nl_project_2.cad_contract import (
    BlockDefinitionMetadata,
    CadObservation,
    CadObservationBatch,
    load_contract,
)
from nl_project_2.cad_sync import ChangeClass, DwgSyncService, WriteResult
from nl_project_2.persistence.schema import (
    bus,
    bus_endpoint,
    bus_segment,
    cable_line,
    field_device,
    project_instance,
)

from .test_branched_service import _sources
from .test_service import _rs485_resources


def outlet(number, source="", **overrides):
    attrs = {
        tag: "" for tag in load_contract().block("CABLE_OUTLET_BUS").required_definition_attributes
    }
    attrs.update(
        DEVICE_NAME="Электрокарниз",
        BUILDING="B1",
        ROOM="R1",
        MOUNT_HEIGHT="4500",
        BUS_POINT_ID=f"920.{number:03d}",
        BUS_SOURCE=source,
        BUS_CABLE_TYPE="FTP 5e",
        BUS_MOUNT_WAY="По полу",
        BUS_GOFRA_TYPE="ППЛ20",
        BUS_GOFRA_COLOR="Синий",
        LOAD_NAME="Электрокарниз окно",
    )
    attrs.update(overrides)
    return CadObservation.from_mapping(
        effective_name="CABLE_OUTLET_BUS",
        layer="BUS",
        raw_attributes=attrs,
        x=number * 1000,
        y=0,
        handle=f"A{number}",
        definition=BlockDefinitionMetadata(tuple(attrs), False),
    )


def rewritten(row, **changes):
    attrs = {item.tag: item.value for item in row.raw_attributes}
    attrs.update(changes)
    return CadObservation.from_mapping(
        effective_name=row.effective_name,
        layer=row.layer,
        raw_attributes=attrs,
        x=row.x,
        y=row.y,
        handle=row.handle,
        definition=row.definition,
    )


def batch(*rows):
    return CadObservationBatch("C:/fixture/issue225.dwg", rows)


def setup_bus(database, kind):
    service = BusService(database.engine)
    if kind == "RS485":
        root = _rs485_resources(database, count=1)[0]
        return service.create_rs485_bus(
            project_id=database.test_project_id, designation="920", root_resource_id=root, points=()
        )
    _, dali, knx, _ = _sources(database)
    return service.create_branched_bus(
        project_id=database.test_project_id,
        bus_kind=kind,
        designation="920",
        root_resource_id=dali if kind == "DALI" else knx,
        points=(),
        branches=(),
    )


class Bridge:
    def write_attributes(self, *, document_identity, changes, deadline_seconds):
        self.changes = changes
        return WriteResult(
            document_identity=document_identity,
            readback=tuple(
                {"handle": x["handle"], "tag": x["tag"], "value": x["new_value"]} for x in changes
            ),
            no_save_confirmed=True,
            document_saved=False,
        )


@pytest.mark.parametrize("kind", ["RS485", "DALI", "KNX"])
def test_import_edges_noop_writeback_conflict_and_missing(database, kind):
    setup_bus(database, kind)
    project_id = database.test_project_id
    sync = DwgSyncService(database.engine)
    rows = tuple(
        outlet(i, "" if kind == "RS485" else ("920.000" if i == 1 else "920.001"))
        for i in (3, 1, 2)
    )
    with database.engine.connect() as c:
        equipment_count = c.scalar(select(func.count()).select_from(project_instance))
    proposal = sync.preview(project_id=project_id, batch=batch(*rows))
    assert proposal.can_apply, proposal.issues
    sync.apply_dwg_to_project(
        proposal,
        selected_paths={
            x.field_path
            for x in proposal.changes
            if x.change_class == ChangeClass.NEW_DWG_INSERTION
        },
        confirmed=True,
    )
    with database.engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(cable_line)) == 0
        assert c.scalar(select(func.count()).select_from(project_instance)) == equipment_count
        assert c.scalar(select(func.count()).select_from(field_device)) == 3
        points = {x["id"]: x["address"] for x in c.execute(select(bus_endpoint)).mappings()}
        segments = list(c.execute(select(bus_segment)).mappings())
        assert len(segments) == 3
        edges = {
            (points.get(x["source_endpoint_id"], "920.000"), points[x["target_endpoint_id"]])
            for x in segments
        }
        expected = {
            ("920.000", "920.001"),
            ("920.001", "920.002"),
            ("920.002" if kind == "RS485" else "920.001", "920.003"),
        }
        assert edges == expected
        assert all(x["gofra_type"] == "ППЛ20" for x in segments)
    again = sync.preview(project_id=project_id, batch=batch(*rows))
    generated = [x for x in again.changes if x.change_class == ChangeClass.PROJECT_CHANGED]
    assert len(generated) == 3 and {x.field for x in generated} == {"BUS_GOFRA_ID"}
    sync.write_project_to_dwg(
        again, selected_paths={x.field_path for x in generated}, confirmed=True, bridge=Bridge()
    )
    ids = {x.handle: x.project_value for x in generated}
    rows = tuple(rewritten(row, BUS_GOFRA_ID=ids[row.handle]) for row in rows)
    again = sync.preview(project_id=project_id, batch=batch(*rows))
    assert all(x.change_class == ChangeClass.EQUAL for x in again.changes), [
        (x.field, x.change_class) for x in again.changes if x.change_class != ChangeClass.EQUAL
    ]
    with database.engine.begin() as c:
        row = (
            c.execute(select(field_device).where(field_device.c.entity_handle == "A2"))
            .mappings()
            .one()
        )
        fields = dict(row["normalized_fields_json"])
        fields["COMMENT_1"] = "Project comment"
        c.execute(
            update(field_device)
            .where(field_device.c.id == row["id"])
            .values(normalized_fields_json=fields)
        )
    proposal = sync.preview(project_id=project_id, batch=batch(*rows))
    change = next(x for x in proposal.changes if x.handle == "A2" and x.field == "COMMENT_1")
    assert change.change_class == ChangeClass.PROJECT_CHANGED
    bridge = Bridge()
    result = sync.write_project_to_dwg(
        proposal, selected_paths={change.field_path}, confirmed=True, bridge=bridge
    )
    assert result.no_save_confirmed and not result.document_saved
    assert len(bridge.changes) == 1
    written = tuple(
        rewritten(row, COMMENT_1="Project comment" if row.handle == "A2" else "") for row in rows
    )
    assert all(
        x.change_class == ChangeClass.EQUAL
        for x in sync.preview(project_id=project_id, batch=batch(*written)).changes
    )
    missing = sync.preview(project_id=project_id, batch=batch(*written[:-1]))
    assert any(
        x.change_class == ChangeClass.MISSING_DWG_INSERTION and x.handle == "A2"
        for x in missing.changes
    )
    # Reopening the same physical insertion retains identity, with no duplicate segment.
    reopened = DwgSyncService(database.engine).preview(project_id=project_id, batch=batch(*written))
    assert all(x.change_class == ChangeClass.EQUAL for x in reopened.changes)


@pytest.mark.parametrize("kind", ["RS485", "DALI", "KNX"])
def test_segment_owner_conflict_selective_apply_and_writeback(database, kind):
    setup_bus(database, kind)
    pid = database.test_project_id
    sync = DwgSyncService(database.engine)
    rows = tuple(
        outlet(i, "" if kind == "RS485" else "920.000", BUS_GOFRA_ID=f"00{i}.PP20") for i in (1, 2)
    )
    proposal = sync.preview(project_id=pid, batch=batch(*rows))
    sync.apply_dwg_to_project(
        proposal, selected_paths={x.field_path for x in proposal.changes}, confirmed=True
    )
    with database.engine.begin() as c:
        endpoint = c.scalar(select(bus_endpoint.c.id).where(bus_endpoint.c.address == "920.001"))
        c.execute(
            update(bus_segment)
            .where(bus_segment.c.target_endpoint_id == endpoint)
            .values(mount_way="По потолку")
        )
    changed = (rewritten(rows[0], BUS_MOUNT_WAY="В стене"), rewritten(rows[1], COMMENT_1="DWG"))
    proposal = sync.preview(project_id=pid, batch=batch(*changed))
    conflict = next(x for x in proposal.changes if x.handle == "A1" and x.field == "BUS_MOUNT_WAY")
    assert conflict.change_class == ChangeClass.BOTH_CHANGED_CONFLICT
    other = next(x for x in proposal.changes if x.handle == "A2" and x.field == "COMMENT_1")
    sync.apply_dwg_to_project(proposal, selected_paths={other.field_path}, confirmed=True)
    with database.engine.connect() as c:
        assert (
            c.scalar(
                select(bus_segment.c.mount_way).where(bus_segment.c.target_endpoint_id == endpoint)
            )
            == "По потолку"
        )
    # With unchanged DWG, canonical Project route is offered for exact write/read-back.
    proposal = sync.preview(project_id=pid, batch=batch(rows[0], changed[1]))
    route = next(x for x in proposal.changes if x.handle == "A1" and x.field == "BUS_MOUNT_WAY")
    assert route.change_class == ChangeClass.PROJECT_CHANGED
    bridge = Bridge()
    sync.write_project_to_dwg(
        proposal, selected_paths={route.field_path}, confirmed=True, bridge=bridge
    )
    assert [(x["handle"], x["tag"]) for x in bridge.changes] == [("A1", "BUS_MOUNT_WAY")]
    final = (rewritten(rows[0], BUS_MOUNT_WAY="По потолку"), changed[1])
    assert all(
        x.change_class == ChangeClass.EQUAL
        for x in sync.preview(project_id=pid, batch=batch(*final)).changes
    )


@pytest.mark.parametrize("kind", ["DALI", "KNX"])
def test_bus_source_project_owner_and_invalid_write_cycle(database, kind):
    from nl_project_2.cad_sync import DwgSyncError

    setup_bus(database, kind)
    pid = database.test_project_id
    sync = DwgSyncService(database.engine)
    rows = (
        outlet(1, "920.000", BUS_GOFRA_ID="001.PP20"),
        outlet(2, "920.001", BUS_GOFRA_ID="002.PP20"),
    )
    proposal = sync.preview(project_id=pid, batch=batch(*rows))
    sync.apply_dwg_to_project(
        proposal, selected_paths={x.field_path for x in proposal.changes}, confirmed=True
    )
    with database.engine.begin() as c:
        endpoints = {
            x.address: x.id for x in c.execute(select(bus_endpoint.c.address, bus_endpoint.c.id))
        }
        c.execute(
            update(bus_segment)
            .where(bus_segment.c.target_endpoint_id == endpoints["920.002"])
            .values(source_endpoint_id=None)
        )
    proposal = sync.preview(project_id=pid, batch=batch(*rows))
    change = next(x for x in proposal.changes if x.handle == "A2" and x.field == "BUS_SOURCE")
    assert change.change_class == ChangeClass.PROJECT_CHANGED and change.project_value == "920.000"
    sync.write_project_to_dwg(
        proposal, selected_paths={change.field_path}, confirmed=True, bridge=Bridge()
    )
    rows = (rows[0], rewritten(rows[1], BUS_SOURCE="920.000"))
    assert all(
        x.change_class == ChangeClass.EQUAL
        for x in sync.preview(project_id=pid, batch=batch(*rows)).changes
    )
    # A Project-side ring cannot be pushed into a valid drawing.
    with database.engine.begin() as c:
        c.execute(
            update(bus_segment)
            .where(bus_segment.c.target_endpoint_id == endpoints["920.001"])
            .values(source_endpoint_id=endpoints["920.002"])
        )
        c.execute(
            update(bus_segment)
            .where(bus_segment.c.target_endpoint_id == endpoints["920.002"])
            .values(source_endpoint_id=endpoints["920.001"])
        )
    proposal = sync.preview(project_id=pid, batch=batch(*rows))
    with pytest.raises(DwgSyncError, match="BUS_SOURCE_CYCLE"):
        sync.write_project_to_dwg(
            proposal,
            selected_paths={x.field_path for x in proposal.changes if x.field == "BUS_SOURCE"},
            confirmed=True,
            bridge=Bridge(),
        )


@pytest.mark.parametrize("kind", ["DALI", "KNX"])
def test_explicit_bus_kind_creation_ui(database, qtbot, monkeypatch, kind):
    from PySide6.QtWidgets import QDialog, QInputDialog

    from nl_project_2.presentation.bus_workspace import BusWorkspaceDialog, _Rs485ResourceDialog

    _, dali, knx, _ = _sources(database)
    service = BusService(database.engine)
    expected = dali if kind == "DALI" else knx
    assert expected in {
        x["id"] for x in service.list_bus_source_candidates(database.test_project_id, kind)
    }
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **kw: (kind, True))
    monkeypatch.setattr(_Rs485ResourceDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(_Rs485ResourceDialog, "values", lambda self: ("920", expected))
    dialog = BusWorkspaceDialog(service, database.test_project_id)
    qtbot.addWidget(dialog)
    assert dialog.create_bus("920")
    stored = service.list_buses(database.test_project_id)
    assert len(stored) == 1 and stored[0]["bus_kind"] == kind
    assert stored[0]["root_resource_id"] == expected


@pytest.mark.parametrize("kind", ["RS485", "DALI", "KNX"])
def test_bus_only_load_name_remains_editable_without_line(database, kind):
    setup_bus(database, kind)
    sync = DwgSyncService(database.engine)
    pid = database.test_project_id
    row = outlet(1, "" if kind == "RS485" else "920.000", BUS_GOFRA_ID="001.PP20")
    proposal = sync.preview(project_id=pid, batch=batch(row))
    sync.apply_dwg_to_project(
        proposal, selected_paths={x.field_path for x in proposal.changes}, confirmed=True
    )
    changed = rewritten(row, LOAD_NAME="Окно 2")
    proposal = sync.preview(project_id=pid, batch=batch(changed))
    change = next(x for x in proposal.changes if x.field == "LOAD_NAME")
    assert change.change_class == ChangeClass.DWG_CHANGED
    sync.apply_dwg_to_project(proposal, selected_paths={change.field_path}, confirmed=True)
    assert all(
        x.change_class == ChangeClass.EQUAL
        for x in sync.preview(project_id=pid, batch=batch(changed)).changes
    )
    with database.engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(cable_line)) == 0


def test_lengths_and_specification_have_one_physical_segment(database):
    from decimal import Decimal

    from nl_project_2.specification.service import SpecificationService

    from .test_recalculation import _insert_room_and_board_geometry

    pid, _room, root = _insert_room_and_board_geometry(database)
    BusService(database.engine).create_rs485_bus(
        project_id=pid, designation="920", root_resource_id=root, points=()
    )
    sync = DwgSyncService(database.engine)
    rows = tuple(
        outlet(i, BUILDING="Building", ROOM="Room", MOUNT_HEIGHT="300", BUS_GOFRA_ID=f"00{i}.PP20")
        for i in (1, 2, 3)
    )
    proposal = sync.preview(project_id=pid, batch=batch(*rows))
    sync.apply_dwg_to_project(
        proposal,
        selected_paths={
            x.field_path
            for x in proposal.changes
            if x.change_class == ChangeClass.NEW_DWG_INSERTION
        },
        confirmed=True,
    )
    with database.engine.connect() as c:
        lengths = [Decimal(x) for x in c.execute(select(bus_segment.c.length_m_decimal)).scalars()]
    assert sorted(lengths) == [Decimal("1.6"), Decimal("1.6"), Decimal("3.1")]
    report = SpecificationService(database.engine).build(pid)
    assert all("Электрокарниз" not in row.name for row in report["rows"])
    refs = [ref for row in report["rows"] for ref in row.source_refs]
    assert len(refs) == len(set(refs))


def _bus_edges(connection):
    endpoint_addresses = {
        row.id: row.address
        for row in connection.execute(select(bus_endpoint.c.id, bus_endpoint.c.address))
    }
    return {
        (
            endpoint_addresses.get(row.source_endpoint_id, "920.000"),
            endpoint_addresses[row.target_endpoint_id],
        )
        for row in connection.execute(
            select(bus_segment.c.source_endpoint_id, bus_segment.c.target_endpoint_id)
        )
    }


def test_rs485_missing_middle_point_does_not_rewire_on_selective_apply(database):
    setup_bus(database, "RS485")
    sync = DwgSyncService(database.engine)
    project_id = database.test_project_id
    rows = tuple(outlet(i, BUS_GOFRA_ID=f"00{i}.PP20") for i in (1, 2, 3))
    initial = sync.preview(project_id=project_id, batch=batch(*rows))
    sync.apply_dwg_to_project(
        initial,
        selected_paths={
            item.field_path
            for item in initial.changes
            if item.change_class is ChangeClass.NEW_DWG_INSERTION
        },
        confirmed=True,
    )
    expected = {
        ("920.000", "920.001"),
        ("920.001", "920.002"),
        ("920.002", "920.003"),
    }
    with database.engine.connect() as connection:
        assert _bus_edges(connection) == expected

    # The DWG scan is missing an accepted middle insertion, but the user
    # only accepts a note on the still-visible 003. No deletion was approved.
    observed = (rows[0], rewritten(rows[2], COMMENT_1="DWG note"))
    proposal = sync.preview(project_id=project_id, batch=batch(*observed))
    assert any(
        item.handle == "A2" and item.change_class is ChangeClass.MISSING_DWG_INSERTION
        for item in proposal.changes
    )
    comment = next(
        item for item in proposal.changes if item.handle == "A3" and item.field == "COMMENT_1"
    )
    sync.apply_dwg_to_project(
        proposal,
        selected_paths={comment.field_path},
        confirmed=True,
    )
    with database.engine.connect() as connection:
        assert _bus_edges(connection) == expected
        assert connection.scalar(select(func.count()).select_from(bus_segment)) == 3


def test_rs485_inserting_point_between_accepted_points_repairs_successor(database):
    setup_bus(database, "RS485")
    sync = DwgSyncService(database.engine)
    project_id = database.test_project_id
    first = outlet(1, BUS_GOFRA_ID="001.PP20")
    middle = outlet(2, BUS_GOFRA_ID="002.PP20")
    last = outlet(3, BUS_GOFRA_ID="003.PP20")
    initial = sync.preview(project_id=project_id, batch=batch(first, last))
    sync.apply_dwg_to_project(
        initial,
        selected_paths={
            item.field_path
            for item in initial.changes
            if item.change_class is ChangeClass.NEW_DWG_INSERTION
        },
        confirmed=True,
    )
    with database.engine.connect() as connection:
        assert _bus_edges(connection) == {
            ("920.000", "920.001"),
            ("920.001", "920.003"),
        }

    proposal = sync.preview(project_id=project_id, batch=batch(first, middle, last))
    insertion = next(
        item
        for item in proposal.changes
        if item.handle == "A2" and item.change_class is ChangeClass.NEW_DWG_INSERTION
    )
    sync.apply_dwg_to_project(proposal, selected_paths={insertion.field_path}, confirmed=True)
    with database.engine.connect() as connection:
        assert _bus_edges(connection) == {
            ("920.000", "920.001"),
            ("920.001", "920.002"),
            ("920.002", "920.003"),
        }
    after = sync.preview(project_id=project_id, batch=batch(first, middle, last))
    assert all(item.change_class is ChangeClass.EQUAL for item in after.changes)


@pytest.mark.parametrize("kind", ["RS485", "DALI", "KNX"])
@pytest.mark.parametrize("change_kind", ["free_number", "swap"])
def test_existing_bus_point_renumber_is_explicitly_blocked(database, kind, change_kind):
    from nl_project_2.cad_sync import DwgSyncError

    setup_bus(database, kind)
    sync = DwgSyncService(database.engine)
    project_id = database.test_project_id
    rows = tuple(
        outlet(i, "" if kind == "RS485" else "920.000", BUS_GOFRA_ID=f"00{i}.PP20") for i in (1, 2)
    )
    initial = sync.preview(project_id=project_id, batch=batch(*rows))
    sync.apply_dwg_to_project(
        initial,
        selected_paths={
            item.field_path
            for item in initial.changes
            if item.change_class is ChangeClass.NEW_DWG_INSERTION
        },
        confirmed=True,
    )
    if change_kind == "swap":
        changed = (
            rewritten(rows[0], BUS_POINT_ID="920.002"),
            rewritten(rows[1], BUS_POINT_ID="920.001"),
        )
    else:
        changed = (rewritten(rows[0], BUS_POINT_ID="920.004"), rows[1])
    proposal = sync.preview(project_id=project_id, batch=batch(*changed))
    renumbers = [
        item
        for item in proposal.changes
        if item.field == "BUS_POINT_ID" and item.change_class is ChangeClass.IDENTITY_COLLISION
    ]
    assert len(renumbers) == (2 if change_kind == "swap" else 1)
    assert all(item.detail_status == "STRUCTURAL_IDENTITY_REVIEW" for item in renumbers)
    with pytest.raises(DwgSyncError, match="BUS_POINT_ID_RENUMBER_REQUIRES_ATTENTION"):
        sync.apply_dwg_to_project(
            proposal,
            selected_paths={item.field_path for item in renumbers},
            confirmed=True,
            allow_structural=True,
        )
    with database.engine.connect() as connection:
        endpoint_owners = {
            row.address: row.field_device_id
            for row in connection.execute(
                select(bus_endpoint.c.address, bus_endpoint.c.field_device_id)
            )
        }
        assert set(endpoint_owners) == {"920.001", "920.002"}
        assert len(set(endpoint_owners.values())) == 2
        assert _bus_edges(connection) == {
            ("920.000", "920.001"),
            ("920.001" if kind == "RS485" else "920.000", "920.002"),
        }


@pytest.mark.parametrize("kind", ["RS485", "DALI", "KNX"])
def test_bus_cable_type_changes_only_when_all_accepted_points_agree(database, kind):
    setup_bus(database, kind)
    sync = DwgSyncService(database.engine)
    project_id = database.test_project_id
    rows = tuple(
        outlet(
            i,
            "" if kind == "RS485" else "920.000",
            BUS_GOFRA_ID=f"00{i}.PP20",
        )
        for i in (1, 2, 3)
    )
    initial = sync.preview(project_id=project_id, batch=batch(*rows))
    sync.apply_dwg_to_project(
        initial,
        selected_paths={
            item.field_path
            for item in initial.changes
            if item.change_class is ChangeClass.NEW_DWG_INSERTION
        },
        confirmed=True,
    )

    # All accepted DWG points change the Bus-owned type in one operation.
    revised = tuple(rewritten(row, BUS_CABLE_TYPE="FTP 6e") for row in rows)
    proposal = sync.preview(project_id=project_id, batch=batch(*revised))
    changes = [
        item
        for item in proposal.changes
        if item.field == "BUS_CABLE_TYPE" and item.change_class is ChangeClass.DWG_CHANGED
    ]
    assert len(changes) == 3
    sync.apply_dwg_to_project(
        proposal,
        selected_paths={item.field_path for item in changes},
        confirmed=True,
    )
    with database.engine.connect() as connection:
        assert (
            connection.scalar(select(bus.c.cable_type).where(bus.c.designation == "920"))
            == "FTP 6e"
        )
    assert all(
        item.change_class is ChangeClass.EQUAL
        for item in sync.preview(project_id=project_id, batch=batch(*revised)).changes
    )

    # An incomplete DWG snapshot must not silently rewrite the whole Bus.
    incomplete = (rewritten(revised[0], BUS_CABLE_TYPE="FTP 7e"),)
    proposal = sync.preview(project_id=project_id, batch=batch(*incomplete))
    change = next(
        item
        for item in proposal.changes
        if item.field == "BUS_CABLE_TYPE" and item.change_class is ChangeClass.DWG_CHANGED
    )
    from nl_project_2.cad_sync import DwgSyncError

    with pytest.raises(DwgSyncError, match="BUS_CABLE_TYPE_PARTIAL_CHANGE"):
        sync.apply_dwg_to_project(proposal, selected_paths={change.field_path}, confirmed=True)
    with database.engine.connect() as connection:
        assert (
            connection.scalar(select(bus.c.cable_type).where(bus.c.designation == "920"))
            == "FTP 6e"
        )


def test_existing_bus_point_cannot_move_to_another_bus(database):
    from nl_project_2.cad_sync import DwgSyncError

    roots = _rs485_resources(database, count=2)
    service = BusService(database.engine)
    project_id = database.test_project_id
    for designation, root in zip(("920", "921"), roots, strict=True):
        service.create_rs485_bus(
            project_id=project_id,
            designation=designation,
            root_resource_id=root,
            points=(),
        )
    sync = DwgSyncService(database.engine)
    original = outlet(1, BUS_GOFRA_ID="001.PP20")
    initial = sync.preview(project_id=project_id, batch=batch(original))
    sync.apply_dwg_to_project(
        initial,
        selected_paths={
            item.field_path
            for item in initial.changes
            if item.change_class is ChangeClass.NEW_DWG_INSERTION
        },
        confirmed=True,
    )
    moved = rewritten(original, BUS_POINT_ID="921.001")
    proposal = sync.preview(project_id=project_id, batch=batch(moved))
    renumber = next(
        item
        for item in proposal.changes
        if item.field == "BUS_POINT_ID" and item.change_class is ChangeClass.IDENTITY_COLLISION
    )
    with pytest.raises(DwgSyncError, match="BUS_POINT_ID_RENUMBER_REQUIRES_ATTENTION"):
        sync.apply_dwg_to_project(
            proposal,
            selected_paths={renumber.field_path},
            confirmed=True,
            allow_structural=True,
        )
    with database.engine.connect() as connection:
        addresses = list(connection.execute(select(bus_endpoint.c.address)).scalars())
        assert addresses == ["920.001"]
