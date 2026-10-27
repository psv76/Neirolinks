"""NL Project 3.2: 900 bus parent rows must reflect DWG LOAD_NAME and real panel.

No updates to real DWG/SQLite. Synthetic fixtures test heterogeneous purposes,
cross-bus safety and reader support for actual MOD installation.
"""
from sqlalchemy import select,update
from nl_project_2.automation import AutomationService
from nl_project_2.buses import BusService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
 board,bus_endpoint,bus_segment,field_device,project_instance
)
from .test_service import _rs485_resources

def _source_root_on_board(db,project_id,name="ВРУ-20"):
    root=_rs485_resources(db,1)[0]
    bid=new_id()
    with db.engine.begin() as c:
        c.execute(board.insert().values(id=bid,project_id=project_id,designation=name,board_kind="BOARD_IN"))
        instance_id=c.execute(
            select(project_instance.c.id).join(
                __import__("nl_project_2.persistence.schema",fromlist=["instance_resource"]).instance_resource,
                __import__("nl_project_2.persistence.schema",fromlist=["instance_resource"]).instance_resource.c.project_instance_id==project_instance.c.id,
            ).where(
                __import__("nl_project_2.persistence.schema",fromlist=["instance_resource"]).instance_resource.c.id==root,
            )
        ).scalar_one()
        c.execute(update(project_instance).where(project_instance.c.id==instance_id).values(board_id=bid))
    return root

def test_900_journal_preserves_distinct_load_names_and_shows_real_source_board(database):
    pid=database.test_project_id
    root=_source_root_on_board(database,pid)
    svc=BusService(database.engine)
    receipt=svc.create_rs485_bus(project_id=pid,designation="903",root_resource_id=root,points=())
    values=[
        ("903.001","Датчик комбинированный MSW","SENSOR_MSW","Прихожая","903"),
        ("903.002","Преобразователь WB-M1W2","WB_M1W2","Постирочная","903"),
        ("903.003","Датчик комбинированный MSW","SENSOR_MSW","Санузел","903"),
        ("903.004","Другая шина (НЕ ПОКАЗЫВАТЬ)","WB_M1W2","Гостиная","904"),
    ]
    previous=None
    with database.engine.begin() as c:
        for order,(address,purpose,kind,room_name,bus_tag) in enumerate(values,start=1):
            dev=new_id()
            endpoint=new_id()
            c.execute(field_device.insert().values(
                id=dev,project_id=pid,block_kind=kind,
                normalized_fields_json={"BUS_ID":bus_tag,"LOAD_NAME":purpose,
                                        "ROOM":room_name,"BUILDING":"Дом_2"},
                lifecycle="ACTIVE",
            ))
            c.execute(bus_endpoint.insert().values(
                id=endpoint,project_id=pid,bus_id=receipt.bus_id,
                endpoint_kind="FIELD_DEVICE",field_device_id=dev,
                endpoint_role="DEVICE",address=address,endpoint_order=order,
            ))
            c.execute(bus_segment.insert().values(
                id=new_id(),project_id=pid,bus_id=receipt.bus_id,
                source_endpoint_id=previous,target_endpoint_id=endpoint,
                connection_kind="CABLE",origin_kind="PROJECT",migration_state="CONFIRMED",
            ))
            previous=endpoint
    card=next(item for item in svc.journal_cards(pid) if item["designation"]=="903")
    assert card["source_board"]=="ВРУ-20"
    assert card["board"].startswith("ВРУ-20 · ")
    assert "WB-0" in card["board"]
    assert card["load_name"]=="Датчик комбинированный MSW · Преобразователь WB-M1W2"
    assert card["load_name_count"]==2
    assert "903.001: Датчик комбинированный MSW" in card["load_name_tooltip"]
    assert "903.002: Преобразователь WB-M1W2" in card["load_name_tooltip"]
    assert "НЕ ПОКАЗЫВАТЬ" not in card["load_name_tooltip"]
    assert "Гостиная" in card["room_names"]  # The physical point still exists.
    topology=svc.journal_topology(pid,receipt.bus_id)
    assert topology["edges"][0]["target"]["description"]=="Датчик комбинированный MSW"

def test_900_no_dwg_load_name_has_explicit_missing_purpose_not_hardware_guess(database):
    pid=database.test_project_id
    root=_source_root_on_board(database,pid)
    svc=BusService(database.engine)
    receipt=svc.create_rs485_bus(project_id=pid,designation="901",root_resource_id=root,points=())
    card=next(item for item in svc.journal_cards(pid) if item["id"]==receipt.bus_id)
    assert card["load_name"]=="Назначение не задано"
    assert "LOAD_NAME" in card["load_name_tooltip"]

def test_bus_purpose_summary_never_drops_multiple_distinct_designations():
    names=["Электрокарниз окно малое","Электрокарниз окно большое","Электрокарниз дверь","Электрокарниз витраж"]
    result=BusService._journal_purpose_summary(names)
    assert "Электрокарниз окно малое" in result
    assert "Электрокарниз окно большое" in result
    assert "ещё 2" in result


def test_installed_wbe2_inherits_board_for_900_root(database):
    from nl_project_2.persistence.schema import instance_resource
    from nl_project_2.constructor import ConstructorService
    pid=database.test_project_id
    bid=new_id()
    with database.engine.begin() as c:
        c.execute(board.insert().values(
            id=bid,project_id=pid,designation="ВРУ-20",board_kind="BOARD_IN"))
    constructor=ConstructorService(database.engine)
    host=constructor.create_instance(
        project_id=pid,designation="WB-20",board_id=bid,
        passport_key="controller.wiren_board_8_5",
        product_key="product.wirenboard.wb8_4g_64g_ind",
        supply_scope="NEIROLINKS",
    ).instance_id
    module=constructor.create_instance(
        project_id=pid,designation="M01",
        passport_key="module.wirenboard.wbe2_i_rs485_iso",
        product_key="product.wirenboard.wbe2_i_rs485_iso",
        supply_scope="NEIROLINKS",
    ).instance_id
    resources=constructor.list_resources(pid)
    slot=next(r["id"] for r in resources if r["project_instance_id"]==host
              and r["resource_kind"]=="INTERNAL_EXPANSION_SLOT"
              and r["ordinal"]==0)
    attachment=next(r["id"] for r in resources if r["project_instance_id"]==module
                    and r["resource_kind"]=="INTERNAL_EXPANSION_MODULE_ATTACHMENT")
    root=next(r["id"] for r in resources if r["project_instance_id"]==module
              and r["resource_kind"]=="RS485_INTERFACE")
    constructor.create_relation(
        project_id=pid,relation_kind="MODULE_INSTALLATION",
        source_resource_id=slot,target_resource_id=attachment,
    )
    svc=BusService(database.engine)
    result=svc.create_rs485_bus(
        project_id=pid,designation="903",root_resource_id=root,points=())
    card=next(v for v in svc.journal_cards(pid) if v["id"]==result.bus_id)
    assert card["source_board"]=="ВРУ-20"
    assert card["board"].startswith("ВРУ-20 · M01 / RS485")
    assert card["load_name"]=="Назначение не задано"
