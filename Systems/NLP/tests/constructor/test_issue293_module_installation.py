from nl_project_2.constructor.domain import ResourceFacts, default_relation_definitions, validate_relation


def resource(ident, kind, direction):
    return ResourceFacts(
        id=ident, instance_id=ident, key=ident, kind=kind, direction=direction,
        medium="INTERNAL", exclusive=True
    )


def test_module_installation_accepts_typed_slot_and_attachment():
    definition = default_relation_definitions()["MODULE_INSTALLATION"]
    preview = validate_relation(
        definition,
        resource("MOD1", "INTERNAL_EXPANSION_SLOT", "BIDIRECTIONAL"),
        resource("HOST_SLOT", "INTERNAL_EXPANSION_MODULE_ATTACHMENT", "IN"),
    )
    assert preview.allowed


def test_module_installation_rejects_port_as_slot():
    definition = default_relation_definitions()["MODULE_INSTALLATION"]
    preview = validate_relation(
        definition,
        resource("RS485", "RS485_INTERFACE", "BIDIRECTIONAL"),
        resource("HOST_SLOT", "INTERNAL_EXPANSION_MODULE_ATTACHMENT", "IN"),
    )
    assert not preview.allowed


def test_module_installation_rejects_occupied_slot():
    definition = default_relation_definitions()["MODULE_INSTALLATION"]
    preview = validate_relation(
        definition,
        resource("MOD1", "INTERNAL_EXPANSION_SLOT", "BIDIRECTIONAL"),
        resource("HOST_SLOT", "INTERNAL_EXPANSION_MODULE_ATTACHMENT", "IN"),
        source_relation_count=1,
    )
    assert not preview.allowed
