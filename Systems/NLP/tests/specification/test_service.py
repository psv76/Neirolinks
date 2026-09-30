from __future__ import annotations

import hashlib
from decimal import Decimal

from sqlalchemy import select

from nl_project_2.automation import AutomationService
from nl_project_2.cables import CableService
from nl_project_2.catalog.equipment import EquipmentService
from nl_project_2.constructor import ConstructorService
from nl_project_2.panels import PanelService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    cable_length_fact,
    cable_line,
    product_definition,
    project,
)
from nl_project_2.specification import SpecificationService


def _instance(database, designation, product_key, scope="NEIROLINKS"):
    return (
        EquipmentService(database.engine)
        .create_instance(
            project_id=database.test_project_id,
            designation=designation,
            passport_key="protection.circuit_breaker.1p",
            product_key=product_key,
            supply_scope=scope,
        )
        .instance_id
    )


def test_equipment_scopes_price_grouping_replacement_deletion_and_navigation(database):
    project_id = database.test_project_id
    first = _instance(database, "QF.1", "product.schneider.a9f84116")
    second = _instance(database, "QF.2", "product.schneider.a9f84116")
    customer = _instance(database, "QF.C", "product.schneider.a9f84106", scope="CUSTOMER")
    service = SpecificationService(database.engine)
    with database.engine.connect() as connection:
        product_id = connection.scalar(
            select(product_definition.c.id).where(
                product_definition.c.product_key == "product.schneider.a9f84116"
            )
        )
    service.set_product_price(
        project_id=project_id,
        product_definition_id=product_id,
        price="100",
        currency="RUB",
        source_reference="approved quote",
    )
    result = service.build(project_id)
    grouped = next(
        row
        for row in result["rows"]
        if set(row.source_refs) == {("PROJECT_INSTANCE", first), ("PROJECT_INSTANCE", second)}
    )
    assert grouped.quantity == Decimal("2")
    assert grouped.cost == Decimal("200")
    assert len(service.source_navigation(project_id, grouped)) == 2
    customer_row = next(
        row for row in result["rows"] if row.source_refs == (("PROJECT_INSTANCE", customer),)
    )
    assert customer_row.specification_included is True
    assert customer_row.budget_included is False
    assert customer_row.cost is None
    assert "Поставка заказчика" in customer_row.note

    EquipmentService(database.engine).replace_product(
        project_id=project_id,
        instance_id=second,
        new_product_key="product.schneider.a9f84106",
        actor="test",
    )
    assert not any(row.quantity == 2 for row in service.build(project_id)["rows"])
    ConstructorService(database.engine).delete_instance(
        project_id=project_id, instance_id=first, confirmed=True
    )
    assert all(
        ("PROJECT_INSTANCE", first) not in row.source_refs
        for row in service.build(project_id)["rows"]
    )


def test_speaker_and_conduit_grouping_hdmi_piece_and_quantity_override(database):
    project_id = database.test_project_id
    cables = CableService(database.engine)
    board_id = cables.create_board_av(project_id=project_id, designation="BOARD_AV")
    speaker_one = cables.create_av_line(
        project_id=project_id,
        board_id=board_id,
        cable_id="SPK-1",
        load_type="SPEAKER_CABLE",
        cable_type="2x2.5",
    )
    speaker_two = cables.create_av_line(
        project_id=project_id,
        board_id=board_id,
        cable_id="SPK-2",
        load_type="SPEAKER_CABLE",
        cable_type="2x2.5",
    )
    hdmi = cables.create_av_line(
        project_id=project_id,
        board_id=board_id,
        cable_id="HDMI-1",
        load_type="HDMI",
        cable_type="HDMI 2.1",
    )
    draft = cables.start_catalog_draft("SPEC-CABLES")
    speaker_product = cables.add_catalog_product(
        draft_release_id=draft,
        product_key="SPK-CABLE",
        category="SPEAKER_CABLE",
        manufacturer="Test",
        model="Speaker 2x2.5",
        cable_type="2x2.5",
    )
    hdmi_product = cables.add_catalog_product(
        draft_release_id=draft,
        product_key="HDMI-5",
        category="HDMI",
        manufacturer="Test",
        model="HDMI",
        cable_type="HDMI 2.1",
        factory_length_m=5,
    )
    cables.publish_catalog(draft)
    for line_id in (speaker_one, speaker_two):
        cables.select_speaker_product(
            project_id=project_id, cable_line_id=line_id, product_id=speaker_product
        )
    with database.engine.begin() as connection:
        for line_id, length in ((speaker_one, "10"), (speaker_two, "15"), (hdmi, "4")):
            connection.execute(
                cable_length_fact.insert().values(
                    id=new_id(),
                    project_id=project_id,
                    cable_line_id=line_id,
                    calculated_length_m_decimal=length,
                    additional_length_m_decimal="0",
                    rounding_policy="NONE",
                    knowledge_status="KNOWN",
                )
            )
    cables.select_hdmi_manually(project_id=project_id, cable_line_id=hdmi, product_id=hdmi_product)
    first_conduit = cables.create_empty_conduit(
        project_id=project_id,
        designation="001.PND25",
        conduit_type="ПНД25",
        diameter_mm=25,
        length_m=12,
    )
    cables.create_empty_conduit(
        project_id=project_id,
        designation="002.PND25",
        conduit_type="ПНД25",
        diameter_mm=25,
        length_m=8,
    )
    service = SpecificationService(database.engine)
    result = service.build(project_id)
    speaker_row = next(
        row for row in result["rows"] if row.item_key.startswith("CABLE_PRODUCT:SPK-CABLE")
    )
    assert speaker_row.quantity == Decimal("25")
    hdmi_row = next(
        row for row in result["rows"] if row.item_key.startswith("CABLE_PRODUCT:HDMI-5")
    )
    assert hdmi_row.quantity == Decimal("1")
    assert "5 m" in hdmi_row.name
    conduit_row = next(row for row in result["rows"] if row.item_key == "CONDUIT:ПНД25:25")
    assert conduit_row.quantity == Decimal("20")

    service.set_override(
        project_id=project_id,
        source_kind="CONDUIT",
        source_id=first_conduit,
        reason="verified site quantity",
        quantity_correction="20",
    )
    conduit_row = next(
        row for row in service.build(project_id)["rows"] if row.item_key == "CONDUIT:ПНД25:25"
    )
    assert conduit_row.quantity == Decimal("28")


def test_selected_dkc_11525_conduit_enters_specification_by_article(database):
    project_id = database.test_project_id
    cables = CableService(database.engine)
    conduit_id = cables.create_empty_conduit(
        project_id=project_id,
        designation="001.PP25",
        conduit_type="ПП25",
        color="синий",
        diameter_mm=25,
        length_m=50,
    )
    product = cables.conduit_product_candidates(
        project_id=project_id, conduit_id=conduit_id
    )[0]
    cables.select_conduit_product(
        project_id=project_id,
        conduit_id=conduit_id,
        product_definition_id=product["id"],
    )
    row = next(
        row
        for row in SpecificationService(database.engine).build(project_id)["rows"]
        if row.item_key == "PRODUCT:product.dkc.11525"
    )
    assert row.article == "11525"
    assert row.quantity == Decimal("50")


def test_internal_material_workshop_control_and_reopen(database):
    project_id = database.test_project_id
    panels = PanelService(database.engine)
    board_id = panels.create_board(project_id=project_id, designation="BOARD.1")
    material_id = panels.record_material_fact(
        project_id=project_id,
        board_id=board_id,
        material_kind="COMB_BUSBAR",
        quantity="10",
        unit="pcs",
        reason="Feeds QF group",
    )
    service = SpecificationService(database.engine)
    service.set_material_price(
        project_id=project_id,
        material_fact_id=material_id,
        price="15",
        currency="RUB",
        source_reference="calculated price",
    )
    claim_id = service.record_workshop_claim(
        project_id=project_id,
        calculated_material_fact_id=material_id,
        quantity="12",
        unit_price="16",
        currency="RUB",
        source_reference="workshop invoice",
    )
    reopened = SpecificationService(database.engine).build(project_id)
    internal = next(row for row in reopened["rows"] if row.internal)
    assert internal.specification_included is False
    assert internal.budget_included is False
    assert internal.cost == Decimal("150")
    control = reopened["workshop"][0]
    assert control["workshop_material_fact_id"] == claim_id
    assert control["claimed_cost"] == Decimal("192")
    assert control["quantity_deviation"] == Decimal("2")
    assert control["cost_deviation"] == Decimal("42")


def test_unpriced_neirolinks_is_unknown_not_zero(database):
    project_id = database.test_project_id
    instance_id = _instance(database, "QF.UNKNOWN", "product.schneider.a9f84116")
    result = SpecificationService(database.engine).build(project_id)
    row = next(
        row for row in result["rows"] if row.source_refs == (("PROJECT_INSTANCE", instance_id),)
    )
    assert row.cost is None
    assert result["unknown_budget_rows"] == 1
    assert result["neirolinks_total"] == Decimal("0")


def test_all_supply_scopes_and_read_path_does_not_write(database):
    project_id = database.test_project_id
    _instance(database, "QF.N", "product.schneider.a9f84116", "NEIROLINKS")
    _instance(database, "QF.C", "product.schneider.a9f84106", "CUSTOMER")
    _instance(database, "QF.W", "product.schneider.a9f84116", "ASSEMBLY_WORKSHOP")
    _instance(database, "QF.B", "product.schneider.a9f84106", "BY_CONTRACT")
    before_hash = hashlib.sha256(database.path.read_bytes()).hexdigest()
    with database.engine.connect() as connection:
        before_revision = connection.scalar(
            select(project.c.project_revision).where(project.c.id == project_id)
        )
    rows = SpecificationService(database.engine).build(project_id)["rows"]
    with database.engine.connect() as connection:
        after_revision = connection.scalar(
            select(project.c.project_revision).where(project.c.id == project_id)
        )
    after_hash = hashlib.sha256(database.path.read_bytes()).hexdigest()
    assert {row.supply_scope for row in rows} == {
        "NEIROLINKS",
        "CUSTOMER",
        "ASSEMBLY_WORKSHOP",
        "BY_CONTRACT",
    }
    assert before_revision == after_revision
    assert before_hash == after_hash


def test_led_profiles_are_grouped_as_factory_reels(database):
    project_id = database.test_project_id
    with database.engine.begin() as connection:
        line_one, line_two = new_id(), new_id()
        for line_id, designation in ((line_one, "LED.1"), (line_two, "LED.2")):
            connection.execute(
                cable_line.insert().values(
                    id=line_id,
                    project_id=project_id,
                    designation=designation,
                    system_kind="LED",
                    cable_facts_json={},
                    lifecycle="ACTIVE",
                )
            )
    automation = AutomationService(database.engine)
    for line_id in (line_one, line_two):
        automation.create_led_profile(
            project_id=project_id,
            cable_line_id=line_id,
            led_kind="MONO",
            tape_product_key="product.arlight.048822",
            supply_scope="NEIROLINKS",
            segments=({"design_length_mm": "2000"},),
        )
    rows = SpecificationService(database.engine, automation).build(project_id)["rows"]
    led = next(row for row in rows if row.item_key.startswith("PRODUCT:product.arlight.048822"))
    assert led.quantity == Decimal("1")
    assert led.unit == "reel"
    assert len(led.source_refs) == 2
    assert "reels=1" in led.trace[0]
