from collections.abc import Collection

import pytest

from nl_project_2.cad_contract.layer_groups import (
    function_group_for_working_layer,
    hvac_allowed_device_types,
)


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [
        (100, "POWER"),
        (200, "SWITCHES"),
        (300, "LIGHTING_230V"),
        (400, "LIGHTING_LED"),
        (500, "SENSORS"),
        (600, "HVAC"),
        (700, "AV"),
        (800, "NETWORK"),
        (900, "BUS"),
    ],
)
@pytest.mark.parametrize("suffix", ["arbitrary", "Произвольный слой", "Mixed__Case_2", "_"])
def test_all_groups_with_free_suffixes(prefix: int, expected: str, suffix: str) -> None:
    assert function_group_for_working_layer(f"{prefix}_{suffix}") == expected


@pytest.mark.parametrize(
    "layer",
    [
        "",
        "300",
        "300_",
        "300_  ",
        "300_ Свет",
        "300_Свет ",
        " 300_Свет",
        "300_\tСвет",
        "300_Свет\n",
        "300_Свет\u00a0",
        "350_Свет",
        "000_Свет",
        "1000_Свет",
        "0300_Свет",
        "٣00_Свет",
        "DALI_GROUPS",
        "ARCH_WALLS",
        "HEATING",
        "VENTILATION",
        "AV",
        "POWER",
        "LIGHTING_230V",
        "HVAC",
        "700",
        "701",
        "HDMI",
        None,
        700,
        700.0,
        True,
        b"700_HDMI",
        [],
        {},
        object(),
    ],
)
def test_rejected_layers_and_non_strings(layer: object) -> None:
    assert function_group_for_working_layer(layer) is None


@pytest.mark.parametrize("suffix", ["Отопление", "Вентиляция", "HEATING", "VENTILATION"])
def test_hvac_never_returns_a_legacy_family(suffix: str) -> None:
    group = function_group_for_working_layer(f"600_{suffix}")
    assert group == "HVAC"
    assert group not in {"HEATING", "VENTILATION"}


@pytest.mark.parametrize("suffix", ["HDMI", "Акустика", "301", "7YY", "Living room TV"])
def test_av_classifies_only_the_layer_without_cable_id_rules(suffix: str) -> None:
    # No cable ID is supplied or needed; even numeric-looking suffixes are free text.
    assert function_group_for_working_layer(f"700_{suffix}") == "AV"


def test_hvac_union_preserves_both_actual_contract_families(block_contract) -> None:
    # C7A replaces the two machine groups with HVAC. Keep both approved former
    # families explicit so dropping either family still fails this inventory.
    ventilation = frozenset({"AIR_VALVE", "MOTOR", "CABLE_OUTLET", "EL_BOX"})
    heating = frozenset({"HEATING_DEVICE", "CABLE_OUTLET", "EL_BOX"})
    assert "VENTILATION" not in block_contract.functional_groups
    assert "HEATING" not in block_contract.functional_groups

    result = hvac_allowed_device_types(ventilation, heating)

    assert isinstance(result, frozenset)
    assert ventilation <= result
    assert heating <= result
    assert result == ventilation | heating
    assert block_contract.functional_groups["HVAC"].device_types == result


@pytest.mark.parametrize(
    ("ventilation", "heating", "expected"),
    [
        ([], [], frozenset()),
        (["FAN"], [], frozenset({"FAN"})),
        ([], ["HEATER"], frozenset({"HEATER"})),
        (["FAN", "SHARED", "FAN"], ["HEATER", "SHARED"], frozenset({"FAN", "HEATER", "SHARED"})),
        (("FAN",), {"HEATER"}, frozenset({"FAN", "HEATER"})),
    ],
)
def test_hvac_union_collections(
    ventilation: Collection[str], heating: Collection[str], expected: frozenset[str]
) -> None:
    before_ventilation = tuple(ventilation)
    before_heating = tuple(heating)

    result = hvac_allowed_device_types(ventilation, heating)

    assert isinstance(result, frozenset)
    assert result == expected
    assert tuple(ventilation) == before_ventilation
    assert tuple(heating) == before_heating
