from nl_project_2.distribution import (
    ICL_STATUSES,
    assess_distribution_node,
    assess_icl,
    assess_psu_load,
)


def _icl():
    return {
        "input_voltage_range_v_ac": [180, 264],
        "frequency_range_hz": [47, 63],
        "continuous_current_a": 16,
        "rated_load_va": 3680,
        "maximum_capacitive_load_uf": 2500,
        "operating_temperature_range_c": [-30, 70],
    }


def _psu(**changes):
    result = {
        "current_kind": "AC",
        "input_voltage_range_v_ac": [85, 264],
        "input_frequency_range_hz": [47, 63],
        "input_current_a_typical_at_230_v_ac": 1,
        "input_apparent_power_va": 100,
        "input_capacitance_uf": 200,
        "startup_time_ms_at_230_v_ac": 500,
    }
    result.update(changes)
    return result


def _assess(psus, **changes):
    values = {
        "icl": _icl(),
        "power_supplies": tuple(psus),
        "has_distribution_node": len(psus) <= 1,
        "ambient_temperature_c": 25,
        "switching_cycles_per_minute": 1,
        "switching_interval_ms": 2000,
    }
    values.update(changes)
    return assess_icl(**values)


def test_all_five_icl_statuses_and_limit_priority_over_missing():
    assert _assess([_psu()]).status == "VERIFIED"
    exceeded = _assess([_psu(input_current_a_typical_at_230_v_ac=17)])
    assert exceeded.status == "LIMIT_EXCEEDED"
    incomplete = _assess([_psu(input_apparent_power_va=None, input_capacitance_uf=None)])
    assert incomplete.status == "DATA_INCOMPLETE"
    assert any("input_apparent_power_va" in item for item in incomplete.missing_fields)
    assert _assess([_psu(current_kind="DC")]).status == "INCOMPATIBLE"
    assert (
        assess_icl(icl=None, power_supplies=(), has_distribution_node=False).status
        == "NOT_APPLICABLE"
    )
    priority = _assess([_psu(input_current_a_typical_at_230_v_ac=20, input_capacitance_uf=None)])
    assert priority.status == "LIMIT_EXCEEDED"
    assert {
        "VERIFIED",
        "LIMIT_EXCEEDED",
        "DATA_INCOMPLETE",
        "INCOMPATIBLE",
        "NOT_APPLICABLE",
    } == ICL_STATUSES


def test_multiple_psus_require_distribution_node():
    assert _assess([_psu(), _psu()], has_distribution_node=False).status == "INCOMPATIBLE"
    assert _assess([_psu(), _psu()], has_distribution_node=True).status == "VERIFIED"


def test_psu_load_and_distribution_limits():
    verified = assess_psu_load(
        output_voltage_v=24,
        rated_power_w=60,
        rated_current_a=3,
        consumers=(
            {"voltage_range_v": [20, 28], "power_w": 20, "current_a": 1},
            {"voltage_v": 24, "power_w": 30, "current_a": 1.5},
        ),
    )
    assert verified.status == "VERIFIED"
    assert (
        assess_psu_load(
            output_voltage_v=48,
            rated_power_w=60,
            rated_current_a=3,
            consumers=({"voltage_v": 24, "power_w": 20, "current_a": 1},),
        ).status
        == "INCOMPATIBLE"
    )
    assert (
        assess_psu_load(
            output_voltage_v=24,
            rated_power_w=40,
            rated_current_a=3,
            consumers=({"voltage_v": 24, "power_w": 50, "current_a": 2},),
        ).status
        == "LIMIT_EXCEEDED"
    )

    assert (
        assess_distribution_node(
            available_points=7,
            used_points=7,
            rated_current_a=100,
            total_current_a=80,
            allowed_section_range_mm2=[2.5, 16],
            conductor_sections_mm2=(2.5, 10),
            required_bus_configuration="3L+PEN",
            actual_bus_configuration="3L+PEN",
            source_count=1,
        ).status
        == "VERIFIED"
    )
    assert (
        assess_distribution_node(
            available_points=7,
            used_points=8,
            rated_current_a=100,
            total_current_a=80,
            allowed_section_range_mm2=[2.5, 16],
            conductor_sections_mm2=(1.5,),
            required_bus_configuration="3L+PEN",
            actual_bus_configuration="1L+N",
            source_count=2,
        ).status
        == "INCOMPATIBLE"
    )
