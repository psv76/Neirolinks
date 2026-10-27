"""Issue #293: three independent WB8.5 hosts, 12 MOD slots, eight RS485 roots 903–910.

Synthetic fixture only. This does not claim Bogdanovich's DWG/BUS endpoints
are linked: their real passport assignments must first be verified on a copy.
"""
from nl_project_2.buses import BusService
from nl_project_2.constructor import ConstructorService
from nl_project_2.persistence.database import DatabaseManager


def test_3_wb85_8_wbe2_rs485_roots_903_through_910_reopen(database):
    pid = database.test_project_id
    service = ConstructorService(database.engine)
    bus_service = BusService(database.engine)
    hosts = {}
    for name in ("WB-20", "WB-23", "WB-26"):
        host = service.create_instance(
            project_id=pid, designation=name,
            passport_key="controller.wiren_board_8_5",
            product_key="product.wirenboard.wb8_4g_64g_ind",
            supply_scope="NEIROLINKS",
        )
        slots = sorted(
            (
                r for r in service.list_resources(pid)
                if r["project_instance_id"] == host.instance_id
                and r["resource_kind"] == "INTERNAL_EXPANSION_SLOT"
            ),
            key=lambda r: r["ordinal"],
        )
        assert len(slots) == 4
        hosts[name] = slots
    all_slots = {row["id"] for rows in hosts.values() for row in rows}
    assert len(all_slots) == 12

    # One available slot on WB-23 is deliberately reserved for the user's MOD3 example.
    planned = [
        ("WB-20", 0), ("WB-20", 1), ("WB-20", 2),
        ("WB-23", 2), ("WB-23", 0), ("WB-23", 1),
        ("WB-26", 0), ("WB-26", 1),
    ]
    receipt_ids = []
    roots = set()
    slots_used = set()
    for index, (host_name, slot_ord) in enumerate(planned):
        module = service.create_instance(
            project_id=pid, designation=f"WBE2-{index + 1:02}",
            passport_key="module.wirenboard.wbe2_i_rs485_iso",
            product_key="product.wirenboard.wbe2_i_rs485_iso",
            supply_scope="NEIROLINKS",
        )
        ports = [
            r for r in service.list_resources(pid)
            if r["project_instance_id"] == module.instance_id
        ]
        attachment = next(
            r["id"] for r in ports
            if r["resource_kind"] == "INTERNAL_EXPANSION_MODULE_ATTACHMENT"
        )
        rs485 = next(r["id"] for r in ports if r["resource_kind"] == "RS485_INTERFACE")
        slot_id = hosts[host_name][slot_ord]["id"]
        service.create_relation(
            project_id=pid, relation_kind="MODULE_INSTALLATION",
            source_resource_id=slot_id, target_resource_id=attachment,
        )
        bus_name = str(903 + index)
        bus = bus_service.create_rs485_bus(
            project_id=pid, designation=bus_name,
            root_resource_id=rs485, points=(),
        )
        receipt_ids.append((bus_name, bus.bus_id, rs485))
        roots.add(rs485)
        slots_used.add(slot_id)
    assert len(roots) == len(slots_used) == len(receipt_ids) == 8

    path = database.path
    database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        buses = BusService(reopened.engine)
        for name, bus_id, root_id in receipt_ids:
            result = buses.get_bus(pid, bus_id)
            assert result["designation"] == name
            assert result["root_resource_id"] == root_id
        assert len([
            r for r in ConstructorService(reopened.engine).list_relations(pid)
            if r["relation_kind"] == "MODULE_INSTALLATION"
        ]) == 8
    finally:
        reopened.close()
