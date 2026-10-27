"""Guarded and audited same-board RS485 source reassignment (NLP 3.2).

No direct SQL UPDATE. Refuse if NLP process open, DB SHA differs,
source is not exactly WB-21 / RS485 or target not exactly M01 / RS485,
or 903 no longer exists. Verified backup before BusService transaction.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from sqlalchemy import select
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from nl_project_2.buses import BusService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.migration import create_verified_backup, HEAD_REVISION,current_revision_read_only
from nl_project_2.persistence.schema import (bus,instance_resource,project_instance,
    passport_definition,project,functional_relation,bus_endpoint,bus_segment,
    bus_branch,bus_physical_link,bus_physical_node, cable_line)
from apply_additive_catalog_successor import require_app_closed,check_integrity

TABLES={"project":project,"instances":project_instance,"resources":instance_resource,
        "relations":functional_relation,"endpoints":bus_endpoint,"segments":bus_segment,
        "branches":bus_branch,"physical_links":bus_physical_link,
        "physical_nodes":bus_physical_node,"cables":cable_line}

def read_fingerprint(engine,project_id):
    with engine.connect() as c:
        result={}
        for key,table in TABLES.items():
            rows=c.execute(select(table).where(table.c.project_id==project_id)).mappings().all()
            result[key]=sorted(json.dumps(dict(r),sort_keys=True,ensure_ascii=False,default=str) for r in rows)
        result["other_buses"]=sorted(
            json.dumps(dict(r),sort_keys=True,ensure_ascii=False,default=str)
            for r in c.execute(select(bus).where(
                bus.c.project_id==project_id,bus.c.designation!="903")).mappings()
        )
        return result

def apply(database:Path,backup_root:Path,expected_sha:str)->dict:
    require_app_closed()
    database=database.resolve()
    if current_revision_read_only(database)!=HEAD_REVISION:
        raise RuntimeError("Working schema head changed")
    sha=hashlib.sha256(database.read_bytes()).hexdigest()
    if sha!=expected_sha.lower().strip():
        raise RuntimeError("Working DB SHA differs; no modification performed")
    check_integrity(database)
    with sqlite3.connect(str(database),timeout=0) as c:
        c.execute("BEGIN EXCLUSIVE")
        c.rollback()
    db=DatabaseManager().open_existing(database)
    try:
        with db.engine.connect() as c:
            row=c.execute(select(bus).where(bus.c.designation=="903",bus.c.bus_kind=="RS485",
                     bus.c.lifecycle=="ACTIVE")).mappings().one()
            pid=row["project_id"]
            source_owner=c.execute(
                select(project_instance.c.designation)
                .join(instance_resource,instance_resource.c.project_instance_id==project_instance.c.id)
                .where(instance_resource.c.id==row["root_resource_id"])).scalar_one()
            targets=c.execute(
                select(instance_resource.c.id,passport_definition.c.passport_key)
                .join(project_instance,project_instance.c.id==instance_resource.c.project_instance_id)
                .join(passport_definition,passport_definition.c.id==project_instance.c.passport_definition_id)
                .where(
                    project_instance.c.project_id==pid,project_instance.c.designation=="M01",
                    project_instance.c.lifecycle=="ACTIVE",
                    instance_resource.c.resource_kind=="RS485_INTERFACE",
                    instance_resource.c.active.is_(True),
                )
            ).all()
            if len(targets)!=1 or targets[0].passport_key!="module.wirenboard.wbe2_i_rs485_iso":
                raise RuntimeError("Expected unique M01 WBE2 RS485 port not found")
            new_root=targets[0].id
            if source_owner!="WB-21":
                raise RuntimeError(f"903 root owner changed: {source_owner}; abort")
            if row["root_resource_id"]==new_root:
                raise RuntimeError("Source is already M01; no update required")
            before=read_fingerprint(db.engine,pid)
            bus_id=row["id"]
            service=BusService(db.engine)
            original=service.get_bus(pid,bus_id)
            if len(original["endpoints"])!=5 or len(original["segments"])!=5:
                raise RuntimeError("903 topology changed from approved 5 points/5 segments")
    finally:db.close()
    directory=backup_root.resolve()/f"nlp32_bus903_to_M01_{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    directory.mkdir(parents=True,exist_ok=False)
    verified=create_verified_backup(database,directory)
    if hashlib.sha256(database.read_bytes()).hexdigest()!=sha:
        raise RuntimeError("Database changed during backup; no transfer")
    db=DatabaseManager().open_existing(database)
    try:
        BusService(db.engine).transfer_rs485_source(
            project_id=pid,bus_id=bus_id,new_root_resource_id=new_root)
        after=read_fingerprint(db.engine,pid)
        updated=BusService(db.engine).get_bus(pid,bus_id)
        if after!=before or updated["designation"]!="903" or updated["root_resource_id"]!=new_root:
            raise RuntimeError("Post-transfer evidence mismatch. Preserve backup for recovery.")
    finally:db.close()
    check_integrity(database)
    receipt={"status":"PASS","bus":"903","bus_id":bus_id,
       "old_owner":"WB-21 / RS485","new_owner":"M01 / RS485",
       "new_root_resource_id":new_root,"backup":str(verified.path),
       "backup_sha256":verified.sha256,"pre_transfer_sha256":sha,
       "project_and_all_graph_tables_unchanged":True,
       "other_bus_rows_unchanged":True,"sqlite_integrity":"ok"}
    (directory/"transfer_receipt.json").write_text(
        json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    return receipt

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--database",required=True,type=Path)
    parser.add_argument("--backup-root",required=True,type=Path)
    parser.add_argument("--expected-database-sha256",required=True)
    args=parser.parse_args()
    print(json.dumps(apply(args.database,args.backup_root,args.expected_database_sha256),
                     ensure_ascii=False,indent=2))
