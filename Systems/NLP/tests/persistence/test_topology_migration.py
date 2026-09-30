from __future__ import annotations

import sqlite3

from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.migration import (
    CONDUIT_DWG_CONTRACT_REVISION,
    HEAD_REVISION,
    current_revision_read_only,
    downgrade_database,
    initialize_database,
    upgrade_database,
)


def _previous_head_fixture(
    path, *, point_count: int, include_conduit: bool = True
) -> dict[str, str]:
    initialize_database(path, target=CONDUIT_DWG_CONTRACT_REVISION)
    ids = {
        "project": new_id(),
        "line": new_id(),
        "device1": new_id(),
        "device2": new_id(),
        "point1": new_id(),
        "point2": new_id(),
        "conduit": new_id(),
        "conduit_assignment": new_id(),
    }
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys=OFF;
            DROP TABLE cable_point;
            DROP TABLE cable_line_assignment;
            DROP TABLE led_line_profile;
            CREATE TABLE cable_point (
                id VARCHAR(36) PRIMARY KEY,
                project_id VARCHAR(36) NOT NULL,
                cable_line_id VARCHAR(36) NOT NULL,
                field_device_id VARCHAR(36),
                point_kind VARCHAR(64) NOT NULL,
                ordinal INTEGER NOT NULL,
                location_json JSON,
                dwg_observation_id VARCHAR(36),
                created_at_utc DATETIME,
                updated_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                row_version INTEGER NOT NULL DEFAULT 1,
                CONSTRAINT uq_cable_point_id UNIQUE(id, project_id),
                CONSTRAINT uq_cable_point_cable_line_id UNIQUE(cable_line_id, ordinal),
                CONSTRAINT uq_cable_point_field_device_id UNIQUE(field_device_id)
            );
            CREATE TABLE cable_line_assignment (
                id VARCHAR(36) PRIMARY KEY,
                project_id VARCHAR(36) NOT NULL,
                cable_line_id VARCHAR(36) NOT NULL,
                output_resource_id VARCHAR(36) NOT NULL,
                assignment_role VARCHAR(64) NOT NULL,
                reservation_id VARCHAR(36),
                created_at_utc DATETIME,
                updated_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                row_version INTEGER NOT NULL DEFAULT 1,
                UNIQUE(cable_line_id, assignment_role),
                UNIQUE(output_resource_id, assignment_role)
            );
            CREATE TABLE led_line_profile (
                id VARCHAR(36) PRIMARY KEY,
                project_id VARCHAR(36) NOT NULL,
                cable_line_id VARCHAR(36) NOT NULL UNIQUE,
                led_kind VARCHAR(16) NOT NULL,
                voltage_decimal TEXT NOT NULL,
                channels INTEGER NOT NULL,
                power_per_m_decimal TEXT,
                tape_product_definition_id VARCHAR(36),
                supply_scope VARCHAR(20),
                created_at_utc DATETIME,
                updated_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                row_version INTEGER NOT NULL DEFAULT 1,
                UNIQUE(id, project_id),
                CONSTRAINT ck_led_line_profile_led_kind
                    CHECK (led_kind IN ('MONO','CCT','RGBW')),
                CONSTRAINT ck_led_line_profile_channels_positive CHECK (channels >= 1)
            );
            CREATE TABLE conduit_cable_assignment (
                id VARCHAR(36) PRIMARY KEY,
                project_id VARCHAR(36) NOT NULL,
                conduit_id VARCHAR(36) NOT NULL,
                cable_line_id VARCHAR(36) NOT NULL,
                created_at_utc DATETIME,
                updated_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                row_version INTEGER NOT NULL DEFAULT 1,
                UNIQUE(conduit_id, cable_line_id)
            );
            """
        )
        connection.execute(
            "INSERT INTO project (id,project_code,name,card_fields_json,lifecycle) "
            "VALUES (?,?,?,'{}','ACTIVE')",
            (ids["project"], "P0-MIGRATION", "P0 migration"),
        )
        for key in ("device1", "device2"):
            connection.execute(
                "INSERT INTO field_device "
                "(id,project_id,block_kind,normalized_fields_json,lifecycle) "
                "VALUES (?,?,?,'{}','ACTIVE')",
                (ids[key], ids["project"], "GENERIC"),
            )
        line_facts = (
            '{"MOUNT_WAY":"По полу","GOFRA_TYPE":"ПВХ16",'
            '"GOFRA_COLOR":"серый","GOFRA_ID":"ГФ001.ПВХ16",'
            '"CABLE_TYPE":"ВВГнг"}'
            if include_conduit
            else '{"MOUNT_WAY":"В кабель-канале","CABLE_TYPE":"ВВГнг"}'
        )
        connection.execute(
            "INSERT INTO cable_line "
            "(id,project_id,designation,system_kind,cable_facts_json,lifecycle) "
            "VALUES (?,?,?,'POWER',?,'ACTIVE')",
            (
                ids["line"],
                ids["project"],
                "L.MIG",
                line_facts,
            ),
        )
        for ordinal, pair in enumerate(
            (("point1", "device1"), ("point2", "device2"))[:point_count]
        ):
            connection.execute(
                "INSERT INTO cable_point "
                "(id,project_id,cable_line_id,field_device_id,point_kind,ordinal) "
                "VALUES (?,?,?,?,?,?)",
                (
                    ids[pair[0]],
                    ids["project"],
                    ids["line"],
                    ids[pair[1]],
                    "DWG_INSERTION",
                    ordinal,
                ),
            )
        if include_conduit:
            connection.execute(
                "INSERT INTO conduit "
                "(id,project_id,designation,conduit_number,conduit_type,color,lifecycle) "
                "VALUES (?,?,?,1,?,?,'ACTIVE')",
                (ids["conduit"], ids["project"], "ГФ001.ПВХ16", "ПВХ16", "серый"),
            )
            connection.execute(
                "INSERT INTO conduit_cable_assignment "
                "(id,project_id,conduit_id,cable_line_id) VALUES (?,?,?,?)",
                (
                    ids["conduit_assignment"],
                    ids["project"],
                    ids["conduit"],
                    ids["line"],
                ),
            )
    return ids


def test_previous_head_simple_line_without_conduit_is_deterministic(tmp_path) -> None:
    path = tmp_path / "simple-line.sqlite"
    _previous_head_fixture(path, point_count=1, include_conduit=False)
    upgrade_database(path, tmp_path / "backup")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM cable_segment").fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM conduit_segment_assignment"
        ).fetchone()[0] == 0
        review_count = connection.execute(
            "SELECT count(*) FROM topology_migration_review"
        ).fetchone()[0]
        assert review_count == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_previous_head_shared_identity_becomes_one_point_with_memberships(tmp_path) -> None:
    path = tmp_path / "shared-point.sqlite"
    ids = _previous_head_fixture(path, point_count=2, include_conduit=False)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE cable_line SET designation='101' WHERE id=?",
            (ids["line"],),
        )
        connection.execute(
            "UPDATE field_device SET normalized_fields_json=? WHERE id IN (?,?)",
            ('{"CABLE_ID":"101"}', ids["device1"], ids["device2"]),
        )

    upgrade_database(path, tmp_path / "backup")

    with sqlite3.connect(path) as connection:
        point = connection.execute(
            "SELECT id,point_kind FROM cable_point WHERE logical_identity='101'"
        ).fetchone()
        assert point == (ids["point1"], "INSTALLATION_GROUP")
        memberships = connection.execute(
            "SELECT cable_point_id,field_device_id FROM cable_point_field_device "
            "ORDER BY field_device_id"
        ).fetchall()
        assert memberships == sorted(
            [(ids["point1"], ids["device1"]), (ids["point1"], ids["device2"])],
            key=lambda item: item[1],
        )
        assert connection.execute("SELECT count(*) FROM cable_segment").fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM topology_migration_review"
        ).fetchone()[0] == 0
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_previous_head_upgrade_reopen_integrity_and_safe_downgrade(tmp_path) -> None:
    path = tmp_path / "previous-head.sqlite"
    ids = _previous_head_fixture(path, point_count=1)
    receipt = upgrade_database(path, tmp_path / "upgrade-backup")
    assert receipt.source_revision == CONDUIT_DWG_CONTRACT_REVISION
    assert current_revision_read_only(path) == HEAD_REVISION
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT count(*) FROM cable_segment").fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM cable_point_field_device"
        ).fetchone()[0] == 1
        assignment = connection.execute(
            "SELECT cable_segment_id FROM conduit_segment_assignment"
        ).fetchone()
        assert assignment is not None
        line_facts = connection.execute(
            "SELECT cable_facts_json FROM cable_line WHERE id=?", (ids["line"],)
        ).fetchone()[0]
        assert "MOUNT_WAY" not in line_facts and "CABLE_TYPE" in line_facts

    downgrade_database(
        path,
        tmp_path / "downgrade-backup",
        target=CONDUIT_DWG_CONTRACT_REVISION,
    )
    assert current_revision_read_only(path) == CONDUIT_DWG_CONTRACT_REVISION
    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(cable_point)")}
        owner = connection.execute(
            "SELECT field_device_id FROM cable_point WHERE id=?", (ids["point1"],)
        ).fetchone()[0]
        assert "logical_identity" not in columns
        assert owner == ids["device1"]
        assert connection.execute(
            "SELECT count(*) FROM conduit_cable_assignment"
        ).fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_ambiguous_legacy_point_order_is_explicit_review(tmp_path) -> None:
    path = tmp_path / "ambiguous.sqlite"
    ids = _previous_head_fixture(path, point_count=2)
    upgrade_database(path, tmp_path / "backup")
    with sqlite3.connect(path) as connection:
        review = connection.execute(
            "SELECT review_kind,review_state,reason FROM topology_migration_review "
            "WHERE cable_line_id=?",
            (ids["line"],),
        ).fetchone()
        assert review is not None
        assert review[0] == "LEGACY_LINE_TOPOLOGY"
        assert review[1] == "MIGRATION_REVIEW_REQUIRED"
        assert "scan order" in review[2]
        assert connection.execute("SELECT count(*) FROM cable_segment").fetchone()[0] == 0
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
