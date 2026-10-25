"""Read-only, project-scoped verification of physical bus kinds and DALI roots.

A DWG contains designations, not evidence that Project owns a root resource.
This module never creates a bus, address, endpoint, segment or migration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import Connection, and_, select

from nl_project_2.persistence.schema import bus, instance_resource, project_instance

_BUS_ID = re.compile(r"9[0-9]{2}")


@dataclass(frozen=True, slots=True)
class ProjectBusContext:
    kinds: dict[str, str]
    verified_dali_roots: frozenset[str]


def load_project_bus_context(connection: Connection, project_id: str) -> ProjectBusContext:
    """Take explicit facts from ACTIVE buses with a valid, active root owner.

    Project bus kinds are read even when their stored root is unavailable,
    to prevent mistakenly treating an RS485 or KNX bus as DALI.
    Only a DALI root with an active resource of an ACTIVE instance is
    considered verified. Unknown/non-9YY designations do not become
    invented CAD identities.
    """
    rows = connection.execute(
        select(
            bus.c.designation,
            bus.c.bus_kind,
            instance_resource.c.id.label("root_id"),
            instance_resource.c.active.label("root_active"),
            project_instance.c.lifecycle.label("root_owner_lifecycle"),
        )
        .select_from(
            bus.outerjoin(
                instance_resource,
                and_(
                    bus.c.root_resource_id == instance_resource.c.id,
                    bus.c.project_id == instance_resource.c.project_id,
                ),
            ).outerjoin(
                project_instance,
                and_(
                    instance_resource.c.project_instance_id == project_instance.c.id,
                    bus.c.project_id == project_instance.c.project_id,
                ),
            )
        )
        .where(bus.c.project_id == project_id, bus.c.lifecycle == "ACTIVE")
        .order_by(bus.c.designation)
    ).mappings()

    kinds: dict[str, str] = {}
    roots: set[str] = set()
    for row in rows:
        designation = str(row["designation"] or "").strip()
        if not _BUS_ID.fullmatch(designation):
            continue
        kind = str(row["bus_kind"] or "").upper()
        if designation in kinds:
            raise ValueError(f"Ambiguous active Project bus identity {designation}")
        kinds[designation] = kind
        if (
            kind == "DALI"
            and row["root_id"] is not None
            and row["root_active"] is True
            and row["root_owner_lifecycle"] == "ACTIVE"
        ):
            roots.add(f"{designation}.000")
    return ProjectBusContext(kinds, frozenset(roots))
