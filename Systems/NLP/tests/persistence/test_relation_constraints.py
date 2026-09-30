from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    catalog_release,
    functional_relation,
    instance_resource,
    passport_definition,
    passport_resource_definition,
    project,
    project_instance,
)
from nl_project_2.persistence.uow import UnitOfWork


def test_functional_relation_rejects_direct_self_loop(database) -> None:
    catalog_id = new_id()
    passport_id = new_id()
    resource_definition_id = new_id()
    project_id = new_id()
    instance_id = new_id()
    resource_id = new_id()
    with UnitOfWork(database.engine) as work:
        work.execute(
            catalog_release.insert().values(
                id=catalog_id,
                release_code="TEST-CATALOG",
                schema_version=1,
                content_sha256="0" * 64,
                installed_at_utc=datetime.now(UTC),
                status="ACTIVE",
            )
        )
        work.execute(
            passport_definition.insert().values(
                id=passport_id,
                catalog_release_id=catalog_id,
                passport_key="TEST-PASSPORT",
                version=1,
                name="Temporary passport",
                equipment_class="TEST",
                functional_role="TEST",
                schema_version=1,
                source_reference="test-only",
                content_sha256="1" * 64,
            )
        )
        work.execute(
            passport_resource_definition.insert().values(
                id=resource_definition_id,
                passport_definition_id=passport_id,
                resource_key="PORT",
                ordinal=1,
                resource_kind="PORT",
                direction="BIDIRECTIONAL",
                medium="TEST",
            )
        )
        work.execute(
            project.insert().values(
                id=project_id,
                project_code="RELATION-TEST",
                name="Temporary relation test",
                card_fields_json={},
                active_catalog_release_id=catalog_id,
            )
        )
        work.execute(
            project_instance.insert().values(
                id=instance_id,
                project_id=project_id,
                designation="X.01",
                passport_definition_id=passport_id,
                parameters_json={},
            )
        )
        work.execute(
            instance_resource.insert().values(
                id=resource_id,
                project_id=project_id,
                project_instance_id=instance_id,
                resource_key="PORT",
                ordinal=1,
                passport_resource_definition_id=resource_definition_id,
                resource_kind="PORT",
                direction="BIDIRECTIONAL",
                medium="TEST",
                snapshot_json={},
            )
        )
        work.commit()

    with pytest.raises(IntegrityError):
        with UnitOfWork(database.engine) as work:
            work.execute(
                functional_relation.insert().values(
                    id=new_id(),
                    project_id=project_id,
                    relation_kind="TEST_RELATION",
                    source_resource_id=resource_id,
                    target_resource_id=resource_id,
                    parameters_json={},
                    command_id=new_id(),
                )
            )
            work.commit()
