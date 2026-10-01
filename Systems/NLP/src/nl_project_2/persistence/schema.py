"""Complete SQLAlchemy Core metadata for the approved MVP data model."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = MetaData(naming_convention=NAMING_CONVENTION)

LIFECYCLE = ("ACTIVE", "RETIRED")
KNOWLEDGE = ("KNOWN", "UNKNOWN", "INCOMPLETE")
DIRECTION = ("IN", "OUT", "BIDIRECTIONAL", "PASSIVE", "INTERNAL")
SUPPLY_SCOPE = ("NEIROLINKS", "CUSTOMER", "ASSEMBLY_WORKSHOP", "BY_CONTRACT")
LED_KINDS = ("MONO", "CCT", "RGB", "RGBW")
TOPOLOGY_POINT_KINDS = (
    "INTERNAL_SOURCE",
    "DEVICE_POINT",
    "INSTALLATION_GROUP",
    "EL_BOX",
    "BUS_POINT",
)
TOPOLOGY_ENDPOINT_KINDS = ("TOPOLOGY_POINT", "INSTANCE_RESOURCE", "FIELD_PORT")
TOPOLOGY_MIGRATION_STATES = ("CONFIRMED", "MIGRATION_REVIEW_REQUIRED")
TOPOLOGY_ORIGINS = ("MIGRATION", "PROJECT")
MOUNT_WAYS = ("По полу", "По потолку", "В стене", "В брусе", "В кабель-канале")
FIELD_PORT_KINDS = (
    "RELAY_COMMON",
    "RELAY_OUTPUT",
    "DIGITAL_INPUT",
    "ONEWIRE_CHANNEL",
    "BUS_INTERFACE",
)
CONTROL_INPUT_KINDS = ("INSTANCE_RESOURCE", "FIELD_PORT")
BUS_ENDPOINT_KINDS = ("INSTANCE_RESOURCE", "FIELD_DEVICE")
CONTROL_TARGET_KINDS = ("UNRESOLVED", "CABLE_LINE", "DALI_GROUP")
USER_RESERVE_TARGETS = ("PROJECT_INSTANCE", "INSTANCE_RESOURCE")
LED_SYNC_STATES = (
    "UNCONFIRMED",
    "IN_SYNC",
    "DWG_CHANGED",
    "PROJECT_CHANGED",
    "BOTH_CHANGED_CONFLICT",
)


def technical_id() -> Column[str]:
    return Column(
        "id",
        String(36),
        primary_key=True,
        nullable=False,
    )


def project_id(*, ondelete: str = "CASCADE") -> Column[str]:
    return Column(
        "project_id",
        String(36),
        ForeignKey("project.id", ondelete=ondelete),
        nullable=False,
    )


def timestamps_and_version() -> tuple[Column[DateTime], Column[DateTime], Column[int]]:
    return (
        Column(
            "created_at_utc",
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
        ),
        Column(
            "updated_at_utc",
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        Column("row_version", Integer, server_default=text("1"), nullable=False),
    )


def lifecycle_column() -> Column[str]:
    return Column("lifecycle", String(16), server_default=text("'ACTIVE'"), nullable=False)


def enum_check(column: str, values: Iterable[str], name: str) -> CheckConstraint:
    quoted = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f"{column} IN ({quoted})", name=name)


def uuid_check(column: str = "id") -> CheckConstraint:
    return CheckConstraint(
        f"length({column}) = 36 AND lower({column}) = {column}",
        name=f"{column}_canonical_uuid",
    )


catalog_release = Table(
    "catalog_release",
    metadata,
    technical_id(),
    Column("release_code", String(100), nullable=False, unique=True),
    Column("schema_version", Integer, nullable=False),
    Column("content_sha256", String(64), nullable=False),
    Column("installed_at_utc", DateTime(timezone=True), nullable=False),
    Column("status", String(16), nullable=False),
    uuid_check(),
    enum_check("status", ("DRAFT", "ACTIVE", "RETIRED"), "status"),
    CheckConstraint("schema_version >= 1", name="schema_version_positive"),
    CheckConstraint("length(content_sha256) = 64", name="content_sha256_length"),
)
Index(
    "uq_catalog_release_one_active",
    catalog_release.c.status,
    unique=True,
    sqlite_where=catalog_release.c.status == "ACTIVE",
)

passport_definition = Table(
    "passport_definition",
    metadata,
    technical_id(),
    Column(
        "catalog_release_id",
        String(36),
        ForeignKey("catalog_release.id"),
        nullable=False,
    ),
    Column("passport_key", String(200), nullable=False),
    Column("version", Integer, nullable=False),
    Column("name", Text, nullable=False),
    Column("equipment_class", String(100), nullable=False),
    Column("functional_role", Text, nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("source_reference", Text, nullable=False),
    Column("content_sha256", String(64), nullable=False),
    lifecycle_column(),
    UniqueConstraint("passport_key", "version"),
    UniqueConstraint("id", "version"),
    uuid_check(),
    enum_check("lifecycle", LIFECYCLE, "lifecycle"),
    CheckConstraint("version >= 1 AND schema_version >= 1", name="versions_positive"),
)

passport_property_definition = Table(
    "passport_property_definition",
    metadata,
    technical_id(),
    Column(
        "passport_definition_id",
        String(36),
        ForeignKey("passport_definition.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("property_key", String(120), nullable=False),
    Column("value_type", String(32), nullable=False),
    Column("value_text", Text),
    Column("minimum_decimal", Text),
    Column("maximum_decimal", Text),
    Column("enum_values_json", JSON),
    Column("unit", String(32)),
    Column("knowledge_status", String(16), nullable=False),
    Column("source_reference", Text),
    UniqueConstraint("passport_definition_id", "property_key"),
    uuid_check(),
    enum_check("knowledge_status", KNOWLEDGE, "knowledge_status"),
    CheckConstraint(
        "minimum_decimal IS NULL OR maximum_decimal IS NULL "
        "OR CAST(minimum_decimal AS NUMERIC) <= CAST(maximum_decimal AS NUMERIC)",
        name="range_order",
    ),
)

passport_resource_definition = Table(
    "passport_resource_definition",
    metadata,
    technical_id(),
    Column(
        "passport_definition_id",
        String(36),
        ForeignKey("passport_definition.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("resource_key", String(120), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("resource_kind", String(100), nullable=False),
    Column("direction", String(20), nullable=False),
    Column("medium", String(64), nullable=False),
    Column("electrical_json", JSON),
    Column("signal_json", JSON),
    Column("exclusive", Boolean, nullable=False, server_default=text("0")),
    Column("capacity_decimal", Text),
    Column("group_key", String(120)),
    Column("display_json", JSON),
    UniqueConstraint("passport_definition_id", "resource_key", "ordinal"),
    uuid_check(),
    enum_check("direction", DIRECTION, "direction"),
    CheckConstraint("ordinal >= 0", name="ordinal_non_negative"),
)

passport_rule_definition = Table(
    "passport_rule_definition",
    metadata,
    technical_id(),
    Column(
        "passport_definition_id",
        String(36),
        ForeignKey("passport_definition.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("rule_key", String(120), nullable=False),
    Column("rule_kind", String(100), nullable=False),
    Column("rule_version", Integer, nullable=False),
    Column("parameters_json", JSON, nullable=False),
    Column("resource_keys_json", JSON, nullable=False),
    UniqueConstraint("passport_definition_id", "rule_key"),
    uuid_check(),
    CheckConstraint("rule_version >= 1", name="rule_version_positive"),
)

product_definition = Table(
    "product_definition",
    metadata,
    technical_id(),
    Column(
        "catalog_release_id",
        String(36),
        ForeignKey("catalog_release.id"),
        nullable=False,
    ),
    Column(
        "passport_definition_id",
        String(36),
        ForeignKey("passport_definition.id"),
        nullable=False,
    ),
    Column("product_key", String(200), nullable=False),
    Column("version", Integer, nullable=False),
    Column("manufacturer", Text, nullable=False),
    Column("normalized_manufacturer", Text, nullable=False),
    Column("series", Text),
    Column("model", Text),
    Column("article", Text),
    Column("normalized_article", Text),
    Column("name", Text, nullable=False),
    Column("width_mm_decimal", Text),
    Column("height_mm_decimal", Text),
    Column("depth_mm_decimal", Text),
    Column("din_width_decimal", Text),
    Column("package_facts_json", JSON),
    Column("project_parameters_json", JSON, nullable=False),
    Column("supply_defaults_json", JSON),
    Column("evidence_json", JSON, nullable=False),
    lifecycle_column(),
    UniqueConstraint("product_key", "version"),
    UniqueConstraint("id", "passport_definition_id"),
    uuid_check(),
    enum_check("lifecycle", LIFECYCLE, "lifecycle"),
    CheckConstraint("version >= 1", name="version_positive"),
)
Index(
    "uq_product_manufacturer_article_known",
    product_definition.c.normalized_manufacturer,
    product_definition.c.normalized_article,
    unique=True,
    sqlite_where=product_definition.c.normalized_article.is_not(None),
)

project = Table(
    "project",
    metadata,
    technical_id(),
    Column("project_code", String(100), nullable=False),
    Column("name", Text, nullable=False),
    Column("card_fields_json", JSON, nullable=False),
    Column("active_catalog_release_id", String(36), ForeignKey("catalog_release.id")),
    lifecycle_column(),
    Column("project_revision", Integer, server_default=text("0"), nullable=False),
    *timestamps_and_version(),
    UniqueConstraint("id", "project_revision"),
    uuid_check(),
    enum_check("lifecycle", LIFECYCLE, "lifecycle"),
    CheckConstraint("project_revision >= 0", name="project_revision_non_negative"),
)
Index(
    "uq_project_code_active",
    project.c.project_code,
    unique=True,
    sqlite_where=project.c.lifecycle == "ACTIVE",
)

building = Table(
    "building",
    metadata,
    technical_id(),
    project_id(),
    Column("code", String(100), nullable=False),
    Column("normalized_code", String(100), nullable=False),
    Column("name", Text, nullable=False),
    Column("display_order", Integer, nullable=False),
    Column("properties_json", JSON),
    *timestamps_and_version(),
    UniqueConstraint("project_id", "normalized_code"),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
    CheckConstraint("display_order >= 0", name="display_order_non_negative"),
)

room = Table(
    "room",
    metadata,
    technical_id(),
    project_id(),
    Column("building_id", String(36), nullable=False),
    Column("name", Text, nullable=False),
    Column("normalized_name", Text, nullable=False),
    Column("base_mark", Text),
    Column("height_m_decimal", Text),
    Column("display_json", JSON),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["building_id", "project_id"],
        ["building.id", "building.project_id"],
        ondelete="CASCADE",
    ),
    UniqueConstraint("building_id", "normalized_name"),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
)

project_setting = Table(
    "project_setting",
    metadata,
    technical_id(),
    project_id(),
    Column("setting_key", String(120), nullable=False),
    Column("value_type", String(32), nullable=False),
    Column("value_json", JSON, nullable=False),
    *timestamps_and_version(),
    UniqueConstraint("project_id", "setting_key"),
    uuid_check(),
)

work_session = Table(
    "work_session",
    metadata,
    technical_id(),
    project_id(),
    Column("application_instance_id", String(36), nullable=False),
    Column("started_at_utc", DateTime(timezone=True), nullable=False),
    Column("stopped_at_utc", DateTime(timezone=True)),
    Column("intervals_json", JSON, nullable=False),
    Column("close_reason", String(64)),
    Column("recovery_reason", Text),
    *timestamps_and_version(),
    uuid_check(),
    CheckConstraint(
        "stopped_at_utc IS NULL OR stopped_at_utc >= started_at_utc",
        name="stop_after_start",
    ),
)
Index(
    "uq_work_session_active_instance",
    work_session.c.application_instance_id,
    unique=True,
    sqlite_where=work_session.c.stopped_at_utc.is_(None),
)

board = Table(
    "board",
    metadata,
    technical_id(),
    project_id(),
    Column("designation", String(120), nullable=False),
    Column("board_kind", String(64), nullable=False),
    Column("room_id", String(36)),
    Column("title", Text),
    lifecycle_column(),
    *timestamps_and_version(),
    ForeignKeyConstraint(["room_id", "project_id"], ["room.id", "room.project_id"]),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
    enum_check("lifecycle", LIFECYCLE, "lifecycle"),
)
Index(
    "uq_board_designation_active",
    board.c.project_id,
    board.c.designation,
    unique=True,
    sqlite_where=board.c.lifecycle == "ACTIVE",
)

project_instance = Table(
    "project_instance",
    metadata,
    technical_id(),
    project_id(),
    Column("designation", String(120), nullable=False),
    Column("board_id", String(36)),
    Column("room_id", String(36)),
    Column("passport_definition_id", String(36), nullable=False),
    Column("product_definition_id", String(36)),
    Column("supply_scope", String(20)),
    lifecycle_column(),
    Column("notes", Text),
    Column("parameters_json", JSON, nullable=False),
    *timestamps_and_version(),
    ForeignKeyConstraint(["board_id", "project_id"], ["board.id", "board.project_id"]),
    ForeignKeyConstraint(["room_id", "project_id"], ["room.id", "room.project_id"]),
    ForeignKeyConstraint(
        ["product_definition_id", "passport_definition_id"],
        ["product_definition.id", "product_definition.passport_definition_id"],
    ),
    ForeignKeyConstraint(["passport_definition_id"], ["passport_definition.id"]),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
    enum_check("lifecycle", LIFECYCLE, "lifecycle"),
    enum_check("supply_scope", SUPPLY_SCOPE, "supply_scope"),
)
Index(
    "uq_project_instance_designation_active",
    project_instance.c.project_id,
    project_instance.c.designation,
    unique=True,
    sqlite_where=project_instance.c.lifecycle == "ACTIVE",
)

instance_resource = Table(
    "instance_resource",
    metadata,
    technical_id(),
    project_id(),
    Column("project_instance_id", String(36), nullable=False),
    Column("resource_key", String(120), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("passport_resource_definition_id", String(36), nullable=False),
    Column("resource_kind", String(100), nullable=False),
    Column("direction", String(20), nullable=False),
    Column("medium", String(64), nullable=False),
    Column("snapshot_json", JSON, nullable=False),
    Column("active", Boolean, nullable=False, server_default=text("1")),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["project_instance_id", "project_id"],
        ["project_instance.id", "project_instance.project_id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["passport_resource_definition_id"],
        ["passport_resource_definition.id"],
    ),
    UniqueConstraint("project_instance_id", "resource_key", "ordinal"),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
    enum_check("direction", DIRECTION, "direction"),
    CheckConstraint("ordinal >= 0", name="ordinal_non_negative"),
)

product_selection_history = Table(
    "product_selection_history",
    metadata,
    technical_id(),
    project_id(),
    Column("project_instance_id", String(36), nullable=False),
    Column("old_product_definition_id", String(36), ForeignKey("product_definition.id")),
    Column("new_product_definition_id", String(36), ForeignKey("product_definition.id")),
    Column("command_id", String(36), nullable=False),
    Column("actor", Text, nullable=False),
    Column("changed_at_utc", DateTime(timezone=True), nullable=False),
    Column("compatibility_result_json", JSON, nullable=False),
    ForeignKeyConstraint(
        ["project_instance_id", "project_id"],
        ["project_instance.id", "project_instance.project_id"],
    ),
    uuid_check(),
)

FOUNDATION_TABLE_NAMES = frozenset(
    {
        "catalog_release",
        "passport_definition",
        "passport_property_definition",
        "passport_resource_definition",
        "passport_rule_definition",
        "product_definition",
        "project",
        "building",
        "room",
        "project_setting",
        "work_session",
        "board",
        "project_instance",
        "instance_resource",
        "product_selection_history",
    }
)

functional_relation = Table(
    "functional_relation",
    metadata,
    technical_id(),
    project_id(),
    Column("relation_kind", String(100), nullable=False),
    Column("source_resource_id", String(36), nullable=False),
    Column("target_resource_id", String(36), nullable=False),
    Column("parameters_json", JSON, nullable=False),
    Column("command_id", String(36), nullable=False),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["source_resource_id", "project_id"],
        ["instance_resource.id", "instance_resource.project_id"],
    ),
    ForeignKeyConstraint(
        ["target_resource_id", "project_id"],
        ["instance_resource.id", "instance_resource.project_id"],
    ),
    UniqueConstraint(
        "project_id",
        "relation_kind",
        "source_resource_id",
        "target_resource_id",
    ),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
    CheckConstraint("source_resource_id <> target_resource_id", name="no_self_loop"),
)

resource_reservation = Table(
    "resource_reservation",
    metadata,
    technical_id(),
    project_id(),
    Column("resource_id", String(36), nullable=False),
    Column("reservation_kind", String(100), nullable=False),
    Column("slot_key", String(120)),
    Column("address", String(120)),
    Column("quantity_decimal", Text),
    Column("owner_relation_id", String(36)),
    Column("owner_assignment_kind", String(100)),
    Column("owner_assignment_id", String(36)),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["resource_id", "project_id"],
        ["instance_resource.id", "instance_resource.project_id"],
    ),
    ForeignKeyConstraint(
        ["owner_relation_id", "project_id"],
        ["functional_relation.id", "functional_relation.project_id"],
    ),
    UniqueConstraint("resource_id", "reservation_kind", "slot_key"),
    uuid_check(),
    CheckConstraint(
        "(owner_relation_id IS NOT NULL) <> (owner_assignment_id IS NOT NULL)",
        name="exactly_one_owner",
    ),
)
Index(
    "uq_resource_reservation_address",
    resource_reservation.c.resource_id,
    resource_reservation.c.address,
    unique=True,
    sqlite_where=resource_reservation.c.address.is_not(None),
)

user_reserve = Table(
    "user_reserve",
    metadata,
    technical_id(),
    project_id(),
    Column("target_kind", String(32), nullable=False),
    Column("project_instance_id", String(36)),
    Column("instance_resource_id", String(36)),
    Column("actor", Text, nullable=False),
    Column("note", Text),
    lifecycle_column(),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["project_instance_id", "project_id"],
        ["project_instance.id", "project_instance.project_id"],
    ),
    ForeignKeyConstraint(
        ["instance_resource_id", "project_id"],
        ["instance_resource.id", "instance_resource.project_id"],
    ),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
    enum_check("target_kind", USER_RESERVE_TARGETS, "target_kind"),
    enum_check("lifecycle", LIFECYCLE, "lifecycle"),
    CheckConstraint(
        "(target_kind = 'PROJECT_INSTANCE' AND project_instance_id IS NOT NULL "
        "AND instance_resource_id IS NULL) OR "
        "(target_kind = 'INSTANCE_RESOURCE' AND instance_resource_id IS NOT NULL "
        "AND project_instance_id IS NULL)",
        name="typed_target",
    ),
)
Index(
    "uq_user_reserve_active_instance",
    user_reserve.c.project_instance_id,
    unique=True,
    sqlite_where=(
        (user_reserve.c.target_kind == "PROJECT_INSTANCE") & (user_reserve.c.lifecycle == "ACTIVE")
    ),
)
Index(
    "uq_user_reserve_active_resource",
    user_reserve.c.instance_resource_id,
    unique=True,
    sqlite_where=(
        (user_reserve.c.target_kind == "INSTANCE_RESOURCE") & (user_reserve.c.lifecycle == "ACTIVE")
    ),
)

validation_trace = Table(
    "validation_trace",
    metadata,
    technical_id(),
    project_id(),
    Column("rule_kind", String(100), nullable=False),
    Column("rule_version", Integer, nullable=False),
    Column("input_entity_ids_json", JSON, nullable=False),
    Column("normalized_operands_json", JSON, nullable=False),
    Column("outcome", String(32), nullable=False),
    Column("command_correlation_id", String(36), nullable=False),
    Column("created_at_utc", DateTime(timezone=True), nullable=False),
    uuid_check(),
    CheckConstraint("rule_version >= 1", name="rule_version_positive"),
)

dwg_document_binding = Table(
    "dwg_document_binding",
    metadata,
    technical_id(),
    project_id(),
    Column("application_uuid", String(36), nullable=False),
    Column("normalized_last_path", Text),
    Column("document_signature", Text),
    Column("fingerprint", String(128)),
    Column("confirmed_at_utc", DateTime(timezone=True)),
    Column("status", String(32), nullable=False),
    *timestamps_and_version(),
    UniqueConstraint("project_id", "application_uuid"),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
)

dwg_scan = Table(
    "dwg_scan",
    metadata,
    technical_id(),
    project_id(),
    Column("dwg_document_binding_id", String(36), nullable=False),
    Column("adapter_version", String(64), nullable=False),
    Column("protocol_version", String(64), nullable=False),
    Column("contract_version", String(64), nullable=False),
    Column("started_at_utc", DateTime(timezone=True), nullable=False),
    Column("completed_at_utc", DateTime(timezone=True)),
    Column("document_facts_json", JSON, nullable=False),
    Column("content_sha256", String(64)),
    Column("status", String(32), nullable=False),
    ForeignKeyConstraint(
        ["dwg_document_binding_id", "project_id"],
        ["dwg_document_binding.id", "dwg_document_binding.project_id"],
    ),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
)

dwg_observation = Table(
    "dwg_observation",
    metadata,
    technical_id(),
    project_id(),
    Column("dwg_scan_id", String(36), nullable=False),
    Column("entity_handle", String(64), nullable=False),
    Column("effective_block_name", Text, nullable=False),
    Column("layer_name", Text, nullable=False),
    Column("space_name", Text, nullable=False),
    Column("geometry_json", JSON, nullable=False),
    Column("raw_attributes_json", JSON, nullable=False),
    Column("diagnostics_json", JSON, nullable=False),
    ForeignKeyConstraint(
        ["dwg_scan_id", "project_id"],
        ["dwg_scan.id", "dwg_scan.project_id"],
        ondelete="CASCADE",
    ),
    UniqueConstraint("dwg_scan_id", "entity_handle"),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
)

field_device = Table(
    "field_device",
    metadata,
    technical_id(),
    project_id(),
    Column("block_kind", String(100), nullable=False),
    Column("room_id", String(36)),
    Column("normalized_fields_json", JSON, nullable=False),
    Column("dwg_document_binding_id", String(36)),
    Column("entity_handle", String(64)),
    lifecycle_column(),
    *timestamps_and_version(),
    ForeignKeyConstraint(["room_id", "project_id"], ["room.id", "room.project_id"]),
    ForeignKeyConstraint(
        ["dwg_document_binding_id", "project_id"],
        ["dwg_document_binding.id", "dwg_document_binding.project_id"],
    ),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
    enum_check("lifecycle", LIFECYCLE, "lifecycle"),
)
Index(
    "uq_field_device_binding_handle_active",
    field_device.c.dwg_document_binding_id,
    field_device.c.entity_handle,
    unique=True,
    sqlite_where=(
        field_device.c.dwg_document_binding_id.is_not(None)
        & field_device.c.entity_handle.is_not(None)
        & (field_device.c.lifecycle == "ACTIVE")
    ),
)

field_device_product_selection = Table(
    "field_device_product_selection",
    metadata,
    technical_id(),
    project_id(),
    Column("field_device_id", String(36), nullable=False, unique=True),
    Column("product_definition_id", String(36), nullable=False),
    Column("configuration_schema_version", Integer, nullable=False),
    Column("configuration_json", JSON, nullable=False),
    Column("supply_scope", String(20), nullable=False),
    Column("knowledge_status", String(16), nullable=False),
    lifecycle_column(),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["field_device_id", "project_id"],
        ["field_device.id", "field_device.project_id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["product_definition_id"],
        ["product_definition.id"],
    ),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
    enum_check("supply_scope", SUPPLY_SCOPE, "supply_scope"),
    enum_check("knowledge_status", KNOWLEDGE, "knowledge_status"),
    enum_check("lifecycle", LIFECYCLE, "lifecycle"),
    CheckConstraint("configuration_schema_version >= 1", name="schema_version_positive"),
)

field_port = Table(
    "field_port",
    metadata,
    technical_id(),
    project_id(),
    Column("field_device_id", String(36), nullable=False),
    Column("port_tag", String(32), nullable=False),
    Column("port_kind", String(32), nullable=False),
    Column("direction", String(20), nullable=False),
    Column("contract_version", Integer, nullable=False),
    lifecycle_column(),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["field_device_id", "project_id"],
        ["field_device.id", "field_device.project_id"],
        ondelete="CASCADE",
    ),
    UniqueConstraint("field_device_id", "port_tag"),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
    enum_check("port_kind", FIELD_PORT_KINDS, "port_kind"),
    enum_check("direction", DIRECTION, "direction"),
    enum_check("lifecycle", LIFECYCLE, "lifecycle"),
    CheckConstraint("contract_version >= 1", name="contract_version_positive"),
)

cable_line = Table(
    "cable_line",
    metadata,
    technical_id(),
    project_id(),
    Column("designation", String(120), nullable=False),
    Column("system_kind", String(100), nullable=False),
    Column("board_id", String(36)),
    Column("cable_facts_json", JSON, nullable=False),
    lifecycle_column(),
    *timestamps_and_version(),
    ForeignKeyConstraint(["board_id", "project_id"], ["board.id", "board.project_id"]),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
    enum_check("lifecycle", LIFECYCLE, "lifecycle"),
)
Index(
    "uq_cable_line_designation_active",
    cable_line.c.project_id,
    cable_line.c.designation,
    unique=True,
    sqlite_where=cable_line.c.lifecycle == "ACTIVE",
)

cable_point = Table(
    "cable_point",
    metadata,
    technical_id(),
    project_id(),
    Column("cable_line_id", String(36), nullable=False),
    # Retained as a physically empty compatibility column through revision 000000000007.
    # Authoritative membership lives only in cable_point_field_device.
    Column("field_device_id", String(36)),
    Column("point_kind", String(64), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("logical_identity", String(160)),
    Column("origin_kind", String(16), nullable=False, server_default=text("'PROJECT'")),
    Column(
        "migration_state",
        String(40),
        nullable=False,
        server_default=text("'CONFIRMED'"),
    ),
    Column("location_json", JSON),
    Column("dwg_observation_id", String(36)),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["cable_line_id", "project_id"],
        ["cable_line.id", "cable_line.project_id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["field_device_id", "project_id"],
        ["field_device.id", "field_device.project_id"],
    ),
    ForeignKeyConstraint(
        ["dwg_observation_id", "project_id"],
        ["dwg_observation.id", "dwg_observation.project_id"],
    ),
    UniqueConstraint("cable_line_id", "ordinal"),
    UniqueConstraint("id", "project_id"),
    UniqueConstraint("id", "project_id", "cable_line_id"),
    uuid_check(),
    enum_check("point_kind", TOPOLOGY_POINT_KINDS, "point_kind"),
    enum_check("origin_kind", TOPOLOGY_ORIGINS, "origin_kind"),
    enum_check("migration_state", TOPOLOGY_MIGRATION_STATES, "migration_state"),
    CheckConstraint("field_device_id IS NULL", name="legacy_device_owner_empty"),
    CheckConstraint("ordinal >= 0", name="ordinal_non_negative"),
)
Index(
    "uq_cable_point_project_identity",
    cable_point.c.project_id,
    cable_point.c.logical_identity,
    unique=True,
    sqlite_where=cable_point.c.logical_identity.is_not(None),
)

cable_point_field_device = Table(
    "cable_point_field_device",
    metadata,
    technical_id(),
    project_id(),
    Column("cable_point_id", String(36), nullable=False),
    Column("field_device_id", String(36), nullable=False),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["cable_point_id", "project_id"],
        ["cable_point.id", "cable_point.project_id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["field_device_id", "project_id"],
        ["field_device.id", "field_device.project_id"],
        ondelete="CASCADE",
    ),
    UniqueConstraint("cable_point_id", "field_device_id"),
    UniqueConstraint("field_device_id"),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
)

cable_topology_endpoint = Table(
    "cable_topology_endpoint",
    metadata,
    technical_id(),
    project_id(),
    Column("cable_line_id", String(36), nullable=False),
    Column("endpoint_kind", String(32), nullable=False),
    Column("cable_point_id", String(36)),
    Column("instance_resource_id", String(36)),
    Column("field_port_id", String(36)),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["cable_line_id", "project_id"],
        ["cable_line.id", "cable_line.project_id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["cable_point_id", "project_id", "cable_line_id"],
        ["cable_point.id", "cable_point.project_id", "cable_point.cable_line_id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["instance_resource_id", "project_id"],
        ["instance_resource.id", "instance_resource.project_id"],
    ),
    ForeignKeyConstraint(
        ["field_port_id", "project_id"],
        ["field_port.id", "field_port.project_id"],
    ),
    UniqueConstraint("id", "project_id", "cable_line_id"),
    UniqueConstraint("cable_line_id", "cable_point_id"),
    UniqueConstraint("cable_line_id", "instance_resource_id"),
    UniqueConstraint("cable_line_id", "field_port_id"),
    uuid_check(),
    enum_check("endpoint_kind", TOPOLOGY_ENDPOINT_KINDS, "endpoint_kind"),
    CheckConstraint(
        "(endpoint_kind = 'TOPOLOGY_POINT' AND cable_point_id IS NOT NULL "
        "AND instance_resource_id IS NULL AND field_port_id IS NULL) OR "
        "(endpoint_kind = 'INSTANCE_RESOURCE' AND instance_resource_id IS NOT NULL "
        "AND cable_point_id IS NULL AND field_port_id IS NULL) OR "
        "(endpoint_kind = 'FIELD_PORT' AND field_port_id IS NOT NULL "
        "AND cable_point_id IS NULL AND instance_resource_id IS NULL)",
        name="typed_owner",
    ),
)

cable_segment = Table(
    "cable_segment",
    metadata,
    technical_id(),
    project_id(),
    Column("cable_line_id", String(36), nullable=False),
    Column("source_endpoint_id", String(36), nullable=False),
    Column("target_endpoint_id", String(36), nullable=False),
    Column("mount_way", String(32)),
    Column("gofra_type", String(120)),
    Column("gofra_color", Text),
    Column("calculated_length_m_decimal", Text),
    Column("calculation_revision", Integer),
    Column("origin_kind", String(16), nullable=False, server_default=text("'PROJECT'")),
    Column(
        "migration_state",
        String(40),
        nullable=False,
        server_default=text("'CONFIRMED'"),
    ),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["cable_line_id", "project_id"],
        ["cable_line.id", "cable_line.project_id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["source_endpoint_id", "project_id", "cable_line_id"],
        [
            "cable_topology_endpoint.id",
            "cable_topology_endpoint.project_id",
            "cable_topology_endpoint.cable_line_id",
        ],
    ),
    ForeignKeyConstraint(
        ["target_endpoint_id", "project_id", "cable_line_id"],
        [
            "cable_topology_endpoint.id",
            "cable_topology_endpoint.project_id",
            "cable_topology_endpoint.cable_line_id",
        ],
    ),
    UniqueConstraint("cable_line_id", "source_endpoint_id", "target_endpoint_id"),
    UniqueConstraint("cable_line_id", "target_endpoint_id"),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
    enum_check("mount_way", MOUNT_WAYS, "mount_way"),
    enum_check("origin_kind", TOPOLOGY_ORIGINS, "origin_kind"),
    enum_check("migration_state", TOPOLOGY_MIGRATION_STATES, "migration_state"),
    CheckConstraint("source_endpoint_id <> target_endpoint_id", name="no_self_edge"),
    CheckConstraint(
        "calculation_revision IS NULL OR calculation_revision >= 1",
        name="calculation_revision_positive",
    ),
)

topology_migration_review = Table(
    "topology_migration_review",
    metadata,
    technical_id(),
    project_id(),
    Column("cable_line_id", String(36), nullable=False),
    Column("review_kind", String(64), nullable=False),
    Column("legacy_source_id", String(36)),
    Column("reason", Text, nullable=False),
    Column("legacy_payload_json", JSON, nullable=False),
    Column("review_state", String(40), nullable=False),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["cable_line_id", "project_id"],
        ["cable_line.id", "cable_line.project_id"],
        ondelete="CASCADE",
    ),
    UniqueConstraint("project_id", "review_kind", "legacy_source_id"),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
    enum_check("review_state", TOPOLOGY_MIGRATION_STATES, "review_state"),
)

cable_line_assignment = Table(
    "cable_line_assignment",
    metadata,
    technical_id(),
    project_id(),
    Column("cable_line_id", String(36), nullable=False),
    Column("endpoint_id", String(36), nullable=False),
    Column("assignment_role", String(64), nullable=False),
    Column("reservation_id", String(36)),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["cable_line_id", "project_id"],
        ["cable_line.id", "cable_line.project_id"],
    ),
    ForeignKeyConstraint(
        ["endpoint_id", "project_id", "cable_line_id"],
        [
            "cable_topology_endpoint.id",
            "cable_topology_endpoint.project_id",
            "cable_topology_endpoint.cable_line_id",
        ],
    ),
    ForeignKeyConstraint(["reservation_id"], ["resource_reservation.id"]),
    UniqueConstraint("cable_line_id", "assignment_role"),
    UniqueConstraint("endpoint_id", "assignment_role"),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
)

field_control_key = Table(
    "field_control_key",
    metadata,
    technical_id(),
    project_id(),
    Column("field_device_id", String(36), nullable=False),
    Column("key_tag", String(16), nullable=False),
    Column("functional_target_text", String(160)),
    Column("target_kind", String(24), nullable=False),
    Column("target_cable_line_id", String(36)),
    Column("target_dali_group_id", String(36)),
    Column("origin_json", JSON, nullable=False),
    Column("baseline_json", JSON),
    lifecycle_column(),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["field_device_id", "project_id"],
        ["field_device.id", "field_device.project_id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["target_cable_line_id", "project_id"],
        ["cable_line.id", "cable_line.project_id"],
    ),
    ForeignKeyConstraint(
        ["target_dali_group_id", "project_id"],
        ["dali_group.id", "dali_group.project_id"],
    ),
    UniqueConstraint("field_device_id", "key_tag"),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
    enum_check("target_kind", CONTROL_TARGET_KINDS, "target_kind"),
    enum_check("lifecycle", LIFECYCLE, "lifecycle"),
    CheckConstraint("key_tag IN ('KEY_1', 'KEY_2', 'KEY_3', 'KEY_4')", name="key_tag"),
    CheckConstraint(
        "(target_kind = 'UNRESOLVED' AND target_cable_line_id IS NULL "
        "AND target_dali_group_id IS NULL) OR "
        "(target_kind = 'CABLE_LINE' AND target_cable_line_id IS NOT NULL "
        "AND target_dali_group_id IS NULL) OR "
        "(target_kind = 'DALI_GROUP' AND target_dali_group_id IS NOT NULL "
        "AND target_cable_line_id IS NULL)",
        name="typed_target",
    ),
)

control_key_input_assignment = Table(
    "control_key_input_assignment",
    metadata,
    technical_id(),
    project_id(),
    Column("field_control_key_id", String(36), nullable=False, unique=True),
    Column(
        "input_kind",
        String(24),
        nullable=False,
        server_default=text("'INSTANCE_RESOURCE'"),
    ),
    Column("input_resource_id", String(36), unique=True),
    Column("field_port_id", String(36), unique=True),
    Column("reservation_id", String(36), unique=True),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["field_control_key_id", "project_id"],
        ["field_control_key.id", "field_control_key.project_id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["input_resource_id", "project_id"],
        ["instance_resource.id", "instance_resource.project_id"],
    ),
    ForeignKeyConstraint(
        ["field_port_id", "project_id"],
        ["field_port.id", "field_port.project_id"],
    ),
    ForeignKeyConstraint(["reservation_id"], ["resource_reservation.id"]),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
    enum_check("input_kind", CONTROL_INPUT_KINDS, "input_kind"),
    CheckConstraint(
        "(input_kind = 'INSTANCE_RESOURCE' AND input_resource_id IS NOT NULL "
        "AND field_port_id IS NULL AND reservation_id IS NOT NULL) OR "
        "(input_kind = 'FIELD_PORT' AND field_port_id IS NOT NULL "
        "AND input_resource_id IS NULL AND reservation_id IS NULL)",
        name="typed_input_owner",
    ),
)

dwg_baseline = Table(
    "dwg_baseline",
    metadata,
    technical_id(),
    project_id(),
    Column("dwg_document_binding_id", String(36), nullable=False),
    Column("field_path", Text, nullable=False),
    Column("accepted_value_json", JSON),
    Column("dwg_scan_id", String(36), nullable=False),
    Column("project_revision", Integer, nullable=False),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["dwg_document_binding_id", "project_id"],
        ["dwg_document_binding.id", "dwg_document_binding.project_id"],
    ),
    ForeignKeyConstraint(
        ["dwg_scan_id", "project_id"],
        ["dwg_scan.id", "dwg_scan.project_id"],
    ),
    UniqueConstraint("dwg_document_binding_id", "field_path"),
    uuid_check(),
)

dwg_sync_operation = Table(
    "dwg_sync_operation",
    metadata,
    technical_id(),
    project_id(),
    Column("dwg_document_binding_id", String(36), nullable=False),
    Column("direction", String(32), nullable=False),
    Column("selection_json", JSON, nullable=False),
    Column("result_json", JSON, nullable=False),
    Column("correlation_id", String(36), nullable=False, unique=True),
    Column("created_at_utc", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["dwg_document_binding_id", "project_id"],
        ["dwg_document_binding.id", "dwg_document_binding.project_id"],
    ),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
)

dwg_sync_change = Table(
    "dwg_sync_change",
    metadata,
    technical_id(),
    project_id(),
    Column("dwg_sync_operation_id", String(36), nullable=False),
    Column("field_path", Text, nullable=False),
    Column("baseline_value_json", JSON),
    Column("project_value_json", JSON),
    Column("dwg_value_json", JSON),
    Column("change_class", String(64), nullable=False),
    Column("decision", String(64)),
    Column("apply_result_json", JSON),
    Column("readback_result_json", JSON),
    ForeignKeyConstraint(
        ["dwg_sync_operation_id", "project_id"],
        ["dwg_sync_operation.id", "dwg_sync_operation.project_id"],
        ondelete="CASCADE",
    ),
    UniqueConstraint("dwg_sync_operation_id", "field_path"),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
)

dwg_write_receipt = Table(
    "dwg_write_receipt",
    metadata,
    technical_id(),
    project_id(),
    Column("dwg_sync_change_id", String(36), nullable=False, unique=True),
    Column("target_preconditions_json", JSON, nullable=False),
    Column("written_value_json", JSON),
    Column("readback_value_json", JSON),
    Column("no_save_confirmed", Boolean, nullable=False),
    Column("created_at_utc", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["dwg_sync_change_id", "project_id"],
        ["dwg_sync_change.id", "dwg_sync_change.project_id"],
    ),
    uuid_check(),
)

cable_length_fact = Table(
    "cable_length_fact",
    metadata,
    technical_id(),
    project_id(),
    Column("cable_line_id", String(36), nullable=False, unique=True),
    Column("calculated_length_m_decimal", Text),
    Column("calculation_source", String(64)),
    Column("calculation_revision", Integer),
    Column("additional_length_m_decimal", Text),
    Column("manual_full_length_m_decimal", Text),
    Column("rounding_policy", String(64), nullable=False),
    Column("knowledge_status", String(16), nullable=False),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["cable_line_id", "project_id"],
        ["cable_line.id", "cable_line.project_id"],
    ),
    uuid_check(),
    enum_check("knowledge_status", KNOWLEDGE, "knowledge_status"),
)

conduit = Table(
    "conduit",
    metadata,
    technical_id(),
    project_id(),
    Column("designation", String(120), nullable=False),
    Column("conduit_number", Integer),
    Column("conduit_type", String(64), nullable=False),
    Column("color", Text),
    Column("diameter_mm_decimal", Text),
    Column("length_m_decimal", Text),
    Column("product_definition_id", String(36), ForeignKey("product_definition.id")),
    Column("path_json", JSON),
    Column("location_json", JSON),
    Column("supply_scope", String(20)),
    lifecycle_column(),
    *timestamps_and_version(),
    UniqueConstraint("project_id", "designation"),
    UniqueConstraint("project_id", "conduit_number"),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
    enum_check("lifecycle", LIFECYCLE, "lifecycle"),
    enum_check("supply_scope", SUPPLY_SCOPE, "supply_scope"),
)

conduit_segment_assignment = Table(
    "conduit_segment_assignment",
    metadata,
    technical_id(),
    project_id(),
    Column("conduit_id", String(36), nullable=False),
    Column("cable_segment_id", String(36), nullable=False, unique=True),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["conduit_id", "project_id"],
        ["conduit.id", "conduit.project_id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["cable_segment_id", "project_id"],
        ["cable_segment.id", "cable_segment.project_id"],
        ondelete="CASCADE",
    ),
    UniqueConstraint("conduit_id", "cable_segment_id"),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
)

cable_catalog_release = Table(
    "cable_catalog_release",
    metadata,
    technical_id(),
    Column("release_code", String(100), nullable=False, unique=True),
    Column("schema_version", Integer, nullable=False),
    Column("content_sha256", String(64), nullable=False),
    Column("installed_at_utc", DateTime(timezone=True), nullable=False),
    Column("status", String(16), nullable=False),
    uuid_check(),
    enum_check("status", ("DRAFT", "ACTIVE", "RETIRED"), "status"),
)
Index(
    "uq_cable_catalog_release_one_active",
    cable_catalog_release.c.status,
    unique=True,
    sqlite_where=cable_catalog_release.c.status == "ACTIVE",
)

cable_product_definition = Table(
    "cable_product_definition",
    metadata,
    technical_id(),
    Column(
        "cable_catalog_release_id",
        String(36),
        ForeignKey("cable_catalog_release.id"),
        nullable=False,
    ),
    Column("product_key", String(200), nullable=False),
    Column("version", Integer, nullable=False),
    Column("category", String(64), nullable=False),
    Column("manufacturer", Text, nullable=False),
    Column("model", Text),
    Column("article", Text),
    Column("technical_properties_json", JSON, nullable=False),
    Column("factory_length_m_decimal", Text),
    lifecycle_column(),
    UniqueConstraint("product_key", "version"),
    uuid_check(),
    enum_check("lifecycle", LIFECYCLE, "lifecycle"),
    enum_check(
        "category",
        ("SPEAKER_CABLE", "HDMI", "OTHER_APPROVED_CABLE"),
        "category",
    ),
)

av_cable_profile = Table(
    "av_cable_profile",
    metadata,
    technical_id(),
    project_id(),
    Column("cable_line_id", String(36), nullable=False, unique=True),
    Column("board_id", String(36), nullable=False),
    Column("cable_id", String(120), nullable=False),
    Column("profile_json", JSON, nullable=False),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["cable_line_id", "project_id"],
        ["cable_line.id", "cable_line.project_id"],
    ),
    ForeignKeyConstraint(["board_id", "project_id"], ["board.id", "board.project_id"]),
    UniqueConstraint("board_id", "cable_id"),
    uuid_check(),
)

cable_line_product_selection = Table(
    "cable_line_product_selection",
    metadata,
    technical_id(),
    project_id(),
    Column("cable_line_id", String(36), nullable=False, unique=True),
    Column(
        "cable_product_definition_id",
        String(36),
        ForeignKey("cable_product_definition.id"),
        nullable=False,
    ),
    Column("selected_at_utc", DateTime(timezone=True), nullable=False),
    Column("command_id", String(36), nullable=False),
    ForeignKeyConstraint(
        ["cable_line_id", "project_id"],
        ["cable_line.id", "cable_line.project_id"],
    ),
    uuid_check(),
)

load_requirement = Table(
    "load_requirement",
    metadata,
    technical_id(),
    project_id(),
    Column("project_instance_id", String(36)),
    Column("cable_line_id", String(36)),
    Column("power_w_decimal", Text),
    Column("current_a_decimal", Text),
    Column("voltage_json", JSON),
    Column("source_kind", String(32), nullable=False),
    Column("knowledge_status", String(16), nullable=False),
    Column("override_history_json", JSON),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["project_instance_id", "project_id"],
        ["project_instance.id", "project_instance.project_id"],
    ),
    ForeignKeyConstraint(
        ["cable_line_id", "project_id"],
        ["cable_line.id", "cable_line.project_id"],
    ),
    uuid_check(),
    enum_check("source_kind", ("DWG", "PROJECT", "PASSPORT", "CALCULATED"), "source"),
    enum_check("knowledge_status", KNOWLEDGE, "knowledge_status"),
    CheckConstraint(
        "(project_instance_id IS NOT NULL) <> (cable_line_id IS NOT NULL)",
        name="exactly_one_owner",
    ),
)

led_line_profile = Table(
    "led_line_profile",
    metadata,
    technical_id(),
    project_id(),
    Column("cable_line_id", String(36), nullable=False, unique=True),
    Column("led_kind", String(16), nullable=False),
    Column("voltage_decimal", Text),
    Column("channels", Integer, nullable=False),
    Column("power_per_m_decimal", Text),
    Column("tape_product_definition_id", String(36), ForeignKey("product_definition.id")),
    Column("supply_scope", String(20)),
    Column("led_type_origin", String(24), nullable=False, server_default=text("'PROJECT'")),
    Column("sync_baseline_json", JSON),
    Column("sync_state", String(40), nullable=False, server_default=text("'UNCONFIRMED'")),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["cable_line_id", "project_id"],
        ["cable_line.id", "cable_line.project_id"],
    ),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
    enum_check("led_kind", LED_KINDS, "led_kind"),
    enum_check("led_type_origin", ("DWG", "PROJECT", "MIGRATION"), "led_type_origin"),
    enum_check("sync_state", LED_SYNC_STATES, "sync_state"),
    enum_check("supply_scope", SUPPLY_SCOPE, "supply_scope"),
    CheckConstraint(
        "(led_kind = 'MONO' AND channels = 1) OR "
        "(led_kind = 'CCT' AND channels = 2) OR "
        "(led_kind = 'RGB' AND channels = 3) OR "
        "(led_kind = 'RGBW' AND channels = 4)",
        name="channels_match_kind",
    ),
)

led_segment = Table(
    "led_segment",
    metadata,
    technical_id(),
    project_id(),
    Column("led_line_profile_id", String(36), nullable=False),
    Column("requested_length_m_decimal", Text, nullable=False),
    Column("segment_order", Integer, nullable=False),
    Column("zone", Text),
    Column("explicit_split_json", JSON),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["led_line_profile_id", "project_id"],
        ["led_line_profile.id", "led_line_profile.project_id"],
        ondelete="CASCADE",
    ),
    UniqueConstraint("led_line_profile_id", "segment_order"),
    uuid_check(),
    CheckConstraint("segment_order >= 0", name="segment_order_non_negative"),
)

bus = Table(
    "bus",
    metadata,
    technical_id(),
    project_id(),
    Column("bus_kind", String(16), nullable=False),
    Column("designation", String(120), nullable=False),
    Column("root_resource_id", String(36), nullable=False),
    Column("topology_policy", String(64), nullable=False),
    Column("cable_type", Text),
    lifecycle_column(),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["root_resource_id", "project_id"],
        ["instance_resource.id", "instance_resource.project_id"],
    ),
    UniqueConstraint("project_id", "designation"),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
    enum_check("bus_kind", ("RS485", "DALI", "KNX"), "bus_kind"),
    enum_check("lifecycle", LIFECYCLE, "lifecycle"),
)

bus_endpoint = Table(
    "bus_endpoint",
    metadata,
    technical_id(),
    project_id(),
    Column("bus_id", String(36), nullable=False),
    Column(
        "endpoint_kind",
        String(24),
        nullable=False,
        server_default=text("'INSTANCE_RESOURCE'"),
    ),
    Column("resource_id", String(36)),
    Column("field_device_id", String(36)),
    Column("endpoint_role", String(64), nullable=False),
    Column("address", String(120)),
    Column("endpoint_order", Integer),
    Column("bus_branch_id", String(36)),
    *timestamps_and_version(),
    ForeignKeyConstraint(["bus_id", "project_id"], ["bus.id", "bus.project_id"]),
    ForeignKeyConstraint(
        ["resource_id", "project_id"],
        ["instance_resource.id", "instance_resource.project_id"],
    ),
    ForeignKeyConstraint(
        ["field_device_id", "project_id"],
        ["field_device.id", "field_device.project_id"],
    ),
    UniqueConstraint("bus_id", "resource_id"),
    UniqueConstraint("bus_id", "field_device_id"),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
    enum_check("endpoint_kind", BUS_ENDPOINT_KINDS, "endpoint_kind"),
    CheckConstraint(
        "(endpoint_kind = 'INSTANCE_RESOURCE' AND resource_id IS NOT NULL "
        "AND field_device_id IS NULL) OR "
        "(endpoint_kind = 'FIELD_DEVICE' AND field_device_id IS NOT NULL "
        "AND resource_id IS NULL)",
        name="typed_endpoint_owner",
    ),
)
Index(
    "uq_bus_endpoint_address_known",
    bus_endpoint.c.bus_id,
    bus_endpoint.c.address,
    unique=True,
    sqlite_where=bus_endpoint.c.address.is_not(None),
)

bus_branch = Table(
    "bus_branch",
    metadata,
    technical_id(),
    project_id(),
    Column("bus_id", String(36), nullable=False),
    Column("branch_key", String(120), nullable=False),
    Column("branch_order", Integer, nullable=False),
    *timestamps_and_version(),
    ForeignKeyConstraint(["bus_id", "project_id"], ["bus.id", "bus.project_id"]),
    UniqueConstraint("bus_id", "branch_key"),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
)

bus_endpoint.append_constraint(
    ForeignKeyConstraint(
        ["bus_branch_id", "project_id"],
        ["bus_branch.id", "bus_branch.project_id"],
    )
)

bus_segment = Table(
    "bus_segment",
    metadata,
    technical_id(),
    project_id(),
    Column("bus_id", String(36), nullable=False),
    Column("source_endpoint_id", String(36)),
    Column("target_endpoint_id", String(36), nullable=False),
    Column("connection_kind", String(16), nullable=False),
    Column("mount_way", String(64)),
    Column("gofra_type", String(64)),
    Column("gofra_color", String(64)),
    Column("gofra_id", String(64)),
    Column("length_m_decimal", Text),
    Column("origin_kind", String(16), nullable=False, server_default=text("'PROJECT'")),
    Column("migration_state", String(32), nullable=False, server_default=text("'CONFIRMED'")),
    *timestamps_and_version(),
    ForeignKeyConstraint(["bus_id", "project_id"], ["bus.id", "bus.project_id"]),
    ForeignKeyConstraint(
        ["source_endpoint_id", "project_id"], ["bus_endpoint.id", "bus_endpoint.project_id"]
    ),
    ForeignKeyConstraint(
        ["target_endpoint_id", "project_id"], ["bus_endpoint.id", "bus_endpoint.project_id"]
    ),
    UniqueConstraint("bus_id", "target_endpoint_id"),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
    enum_check("connection_kind", ("CABLE", "TRACK"), "connection_kind"),
    enum_check("origin_kind", TOPOLOGY_ORIGINS, "origin_kind"),
    enum_check("migration_state", TOPOLOGY_MIGRATION_STATES, "migration_state"),
    CheckConstraint(
        "source_endpoint_id IS NULL OR source_endpoint_id <> target_endpoint_id",
        name="not_self_loop",
    ),
    CheckConstraint(
        "connection_kind = 'CABLE' OR (mount_way IS NULL AND gofra_type IS NULL "
        "AND gofra_color IS NULL AND gofra_id IS NULL "
        "AND length_m_decimal IS NULL)",
        name="track_has_no_external_route",
    ),
)

bus_segment_conduit_assignment = Table(
    "bus_segment_conduit_assignment",
    metadata,
    technical_id(),
    project_id(),
    Column("bus_segment_id", String(36), nullable=False),
    Column("conduit_id", String(36), nullable=False),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["bus_segment_id", "project_id"],
        ["bus_segment.id", "bus_segment.project_id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(["conduit_id", "project_id"], ["conduit.id", "conduit.project_id"]),
    UniqueConstraint("bus_segment_id"),
    uuid_check(),
)

bus_branch_point = Table(
    "bus_branch_point",
    metadata,
    technical_id(),
    project_id(),
    Column("bus_branch_id", String(36), nullable=False),
    Column("resource_id", String(36), nullable=False),
    Column("point_order", Integer, nullable=False),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["bus_branch_id", "project_id"],
        ["bus_branch.id", "bus_branch.project_id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["resource_id", "project_id"],
        ["instance_resource.id", "instance_resource.project_id"],
    ),
    UniqueConstraint("bus_branch_id", "point_order"),
    uuid_check(),
)

dali_group = Table(
    "dali_group",
    metadata,
    technical_id(),
    project_id(),
    Column("bus_id", String(36), nullable=False),
    Column("group_key", String(120), nullable=False),
    lifecycle_column(),
    *timestamps_and_version(),
    ForeignKeyConstraint(["bus_id", "project_id"], ["bus.id", "bus.project_id"]),
    UniqueConstraint("project_id", "group_key"),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
    enum_check("lifecycle", LIFECYCLE, "lifecycle"),
)

dali_group_member = Table(
    "dali_group_member",
    metadata,
    technical_id(),
    project_id(),
    Column("dali_group_id", String(36), nullable=False),
    Column("resource_id", String(36), nullable=False),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["dali_group_id", "project_id"],
        ["dali_group.id", "dali_group.project_id"],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["resource_id", "project_id"],
        ["instance_resource.id", "instance_resource.project_id"],
    ),
    UniqueConstraint("dali_group_id", "resource_id"),
    uuid_check(),
)

graph_layout_preference = Table(
    "graph_layout_preference",
    metadata,
    technical_id(),
    project_id(),
    Column("view_key", String(120), nullable=False),
    Column("node_id", String(120), nullable=False),
    Column("x_decimal", Text, nullable=False),
    Column("y_decimal", Text, nullable=False),
    Column("collapsed", Boolean, nullable=False, server_default=text("0")),
    *timestamps_and_version(),
    UniqueConstraint("project_id", "view_key", "node_id"),
    uuid_check(),
)

panel_section = Table(
    "panel_section",
    metadata,
    technical_id(),
    project_id(),
    Column("board_id", String(36), nullable=False),
    Column("section_key", String(120), nullable=False),
    Column("section_order", Integer, nullable=False),
    *timestamps_and_version(),
    ForeignKeyConstraint(["board_id", "project_id"], ["board.id", "board.project_id"]),
    UniqueConstraint("board_id", "section_key"),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
)

panel_rail = Table(
    "panel_rail",
    metadata,
    technical_id(),
    project_id(),
    Column("panel_section_id", String(36), nullable=False),
    Column("rail_order", Integer, nullable=False),
    Column("usable_width_mm_decimal", Text),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["panel_section_id", "project_id"],
        ["panel_section.id", "panel_section.project_id"],
        ondelete="CASCADE",
    ),
    UniqueConstraint("panel_section_id", "rail_order"),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
)

panel_placement = Table(
    "panel_placement",
    metadata,
    technical_id(),
    project_id(),
    Column("panel_rail_id", String(36), nullable=False),
    Column("project_instance_id", String(36), nullable=False),
    Column("start_mm_decimal", Text, nullable=False),
    Column("width_mm_decimal", Text),
    Column("orientation", String(32), nullable=False),
    Column("status", String(32), nullable=False),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["panel_rail_id", "project_id"],
        ["panel_rail.id", "panel_rail.project_id"],
    ),
    ForeignKeyConstraint(
        ["project_instance_id", "project_id"],
        ["project_instance.id", "project_instance.project_id"],
    ),
    UniqueConstraint("panel_rail_id", "project_instance_id"),
    uuid_check(),
)

assembly_material_fact = Table(
    "assembly_material_fact",
    metadata,
    technical_id(),
    project_id(),
    Column("board_id", String(36), nullable=False),
    Column("material_kind", String(100), nullable=False),
    Column("quantity_decimal", Text, nullable=False),
    Column("unit", String(32), nullable=False),
    Column("reason", Text, nullable=False),
    Column("source_kind", String(64), nullable=False),
    *timestamps_and_version(),
    ForeignKeyConstraint(["board_id", "project_id"], ["board.id", "board.project_id"]),
    UniqueConstraint("id", "project_id"),
    uuid_check(),
)

commercial_fact = Table(
    "commercial_fact",
    metadata,
    technical_id(),
    project_id(),
    Column("product_definition_id", String(36), ForeignKey("product_definition.id")),
    Column("assembly_material_fact_id", String(36)),
    Column("price_decimal", Text),
    Column("currency", String(3)),
    Column("effective_date", String(10)),
    Column("source_reference", Text),
    Column("knowledge_status", String(16), nullable=False),
    *timestamps_and_version(),
    ForeignKeyConstraint(
        ["assembly_material_fact_id", "project_id"],
        ["assembly_material_fact.id", "assembly_material_fact.project_id"],
    ),
    uuid_check(),
    enum_check("knowledge_status", KNOWLEDGE, "knowledge_status"),
    CheckConstraint(
        "(product_definition_id IS NOT NULL) <> (assembly_material_fact_id IS NOT NULL)",
        name="exactly_one_reference",
    ),
)

specification_override = Table(
    "specification_override",
    metadata,
    technical_id(),
    project_id(),
    Column("source_kind", String(100), nullable=False),
    Column("source_id", String(36), nullable=False),
    Column("supply_scope", String(20)),
    Column("note", Text),
    Column("included", Boolean),
    Column("quantity_correction_decimal", Text),
    Column("reason", Text, nullable=False),
    *timestamps_and_version(),
    UniqueConstraint("project_id", "source_kind", "source_id"),
    uuid_check(),
    enum_check("supply_scope", SUPPLY_SCOPE, "supply_scope"),
)

validation_issue_state = Table(
    "validation_issue_state",
    metadata,
    technical_id(),
    project_id(),
    Column("issue_key", String(200), nullable=False),
    Column("rule_kind", String(100), nullable=False),
    Column("input_revision", Integer, nullable=False),
    Column("state", String(32), nullable=False),
    Column("reason", Text),
    Column("actor", Text, nullable=False),
    Column("decided_at_utc", DateTime(timezone=True), nullable=False),
    *timestamps_and_version(),
    UniqueConstraint("project_id", "issue_key"),
    uuid_check(),
    enum_check("state", ("ACKNOWLEDGED", "WAIVED"), "state"),
)

operation_journal = Table(
    "operation_journal",
    metadata,
    technical_id(),
    project_id(),
    Column("command_id", String(36), nullable=False, unique=True),
    Column("command_type", String(120), nullable=False),
    Column("project_revision_before", Integer, nullable=False),
    Column("project_revision_after", Integer),
    Column("correlation_id", String(36), nullable=False),
    Column("status", String(32), nullable=False),
    Column("started_at_utc", DateTime(timezone=True), nullable=False),
    Column("completed_at_utc", DateTime(timezone=True)),
    Column("summary_json", JSON, nullable=False),
    uuid_check(),
    CheckConstraint(
        "project_revision_after IS NULL OR project_revision_after >= project_revision_before",
        name="revision_order",
    ),
)

bulk_operation_receipt = Table(
    "bulk_operation_receipt",
    metadata,
    technical_id(),
    project_id(),
    Column("command_id", String(36), nullable=False, unique=True),
    Column("action_type", String(32), nullable=False),
    Column("selected_owner_ids_json", JSON, nullable=False),
    Column("preview_fingerprint", String(64), nullable=False),
    Column("project_revision_before", Integer, nullable=False),
    Column("project_revision_after", Integer, nullable=False),
    Column("result_status", String(32), nullable=False),
    Column("correlation_id", String(36), nullable=False),
    Column("summary_json", JSON, nullable=False),
    Column(
        "created_at_utc",
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    ),
    UniqueConstraint("project_id", "preview_fingerprint"),
    uuid_check(),
    enum_check("action_type", ("PROTECTION", "POWER", "OUTPUT", "INPUT"), "action_type"),
    enum_check("result_status", ("SUCCEEDED",), "result_status"),
    CheckConstraint(
        "project_revision_after > project_revision_before",
        name="revision_advanced",
    ),
)

background_job = Table(
    "background_job",
    metadata,
    technical_id(),
    project_id(),
    Column("job_kind", String(120), nullable=False),
    Column("input_revision", Integer, nullable=False),
    Column("status", String(32), nullable=False),
    Column("result_reference", Text),
    Column("correlation_id", String(36), nullable=False),
    *timestamps_and_version(),
    uuid_check(),
    enum_check(
        "status",
        ("PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "STALE"),
        "status",
    ),
)

DALI_GROUP_TABLE_NAMES = frozenset({"dali_group", "dali_group_member"})
BULK_OPERATION_TABLE_NAMES = frozenset({"bulk_operation_receipt"})
TOPOLOGY_TABLE_NAMES = frozenset(
    {
        "user_reserve",
        "field_device_product_selection",
        "field_port",
        "cable_point_field_device",
        "cable_topology_endpoint",
        "cable_segment",
        "topology_migration_review",
        "field_control_key",
        "control_key_input_assignment",
        "conduit_segment_assignment",
    }
)
# Revision 000000000002 imports this set, so it must never absorb later tables.
FEATURE_TABLE_NAMES = (
    frozenset(metadata.tables)
    - FOUNDATION_TABLE_NAMES
    - DALI_GROUP_TABLE_NAMES
    - BULK_OPERATION_TABLE_NAMES
    - TOPOLOGY_TABLE_NAMES
)
HEAD_TABLE_NAMES = frozenset(metadata.tables)


def create_tables(bind, table_names: Iterable[str]) -> None:
    selected = set(table_names)
    for table in metadata.sorted_tables:
        if table.name in selected:
            table.create(bind, checkfirst=False)


def drop_tables(bind, table_names: Iterable[str]) -> None:
    selected = set(table_names)
    for table in reversed(metadata.sorted_tables):
        if table.name in selected:
            table.drop(bind, checkfirst=False)
