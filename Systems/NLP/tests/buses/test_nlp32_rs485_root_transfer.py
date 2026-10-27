"""RS-485 bus-root reassignment must preserve the bus graph and guard occupied ports."""
import pytest
from sqlalchemy import select
from nl_project_2.buses import BusError, BusService
from nl_project_2.constructor import ConstructorService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import board, bus_endpoint, bus_segment
from .test_service import _rs485_resources


def test_rs485_903_transfer_retains_bus_and_segments(database):
    pid=database.test_project_id
    svc=ConstructorService(database.engine)
    same=new_id()
    with database.engine.begin() as c:
        c.execute(board.insert().values(id=same,project_id=pid,designation="QB.01",board_kind="POWER"))
    def make(name,passport,product):
        receipt=svc.create_instance(project_id=pid,designation=name,passport_key=passport,
                                    product_key=product,supply_scope="NEIROLINKS",board_id=same)
        return receipt.instance_id
    old=make("WB-21","gateway.wirenboard.wb_mge_v3","product.wirenboard.wb_mge_v3")
    new=make("WB-22","gateway.wirenboard.wb_mge_v3","product.wirenboard.wb_mge_v3")
    rs=svc.list_resources(pid)
    ids={}
    for owner in (old,new):
        ids[owner]=next(r["id"] for r in rs if r["project_instance_id"]==owner and
                        r["resource_kind"]=="RS485_INTERFACE")
    endpoint=_rs485_resources(database,1)[0]
    bus=BusService(database.engine)
    receipt=bus.create_rs485_bus(project_id=pid,designation="903",root_resource_id=ids[old],
        points=({"resource_id":endpoint,"cable_id":"903.001","x_mm":0,"y_mm":0},))
    with database.engine.connect() as c:
        endpoint_rows=list(c.execute(select(bus_endpoint).where(bus_endpoint.c.bus_id==receipt.bus_id)).mappings())
        segment_rows=list(c.execute(select(bus_segment).where(bus_segment.c.bus_id==receipt.bus_id)).mappings())
    bus.transfer_rs485_source(project_id=pid,bus_id=receipt.bus_id,new_root_resource_id=ids[new])
    result=bus.get_bus(pid,receipt.bus_id)
    assert result["id"]==receipt.bus_id and result["designation"]=="903"
    assert result["root_resource_id"]==ids[new]
    bus.transfer_rs485_source(project_id=pid,bus_id=receipt.bus_id,new_root_resource_id=ids[new])
    with database.engine.connect() as c:
        assert endpoint_rows==list(c.execute(select(bus_endpoint).where(bus_endpoint.c.bus_id==receipt.bus_id)).mappings())
        assert segment_rows==list(c.execute(select(bus_segment).where(bus_segment.c.bus_id==receipt.bus_id)).mappings())
    assert next(x for x in bus.list_rs485_resource_candidates(pid) if x["id"]==ids[old])["source_available"]


def test_occupied_source_is_rejected(database):
    pid=database.test_project_id
    a,b,*_= _rs485_resources(database,3)
    bus=BusService(database.engine)
    first=bus.create_rs485_bus(project_id=pid,designation="903",root_resource_id=a,points=())
    second=bus.create_rs485_bus(project_id=pid,designation="904",root_resource_id=b,points=())
    with pytest.raises(BusError,match="already belongs"):
        bus.transfer_rs485_source(project_id=pid,bus_id=first.bus_id,new_root_resource_id=b)
    assert bus.get_bus(pid,first.bus_id)["root_resource_id"]==a
    assert bus.get_bus(pid,second.bus_id)["root_resource_id"]==b
