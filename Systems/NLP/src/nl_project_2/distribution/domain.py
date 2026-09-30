"""Pure distribution, PSU-load and ICL assessments."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

ICL_STATUSES = frozenset(
    {"VERIFIED", "LIMIT_EXCEEDED", "DATA_INCOMPLETE", "INCOMPATIBLE", "NOT_APPLICABLE"}
)


@dataclass(frozen=True, slots=True)
class Assessment:
    status: str
    trace: tuple[dict[str, Any], ...]
    missing_fields: tuple[str, ...] = ()


def assess_psu_load(
    *,
    output_voltage_v,
    rated_power_w,
    rated_current_a,
    consumers: tuple[dict[str, Any], ...],
) -> Assessment:
    trace = []
    missing = []
    voltage = _decimal(output_voltage_v)
    power_limit = _decimal(rated_power_w)
    current_limit = _decimal(rated_current_a)
    power = Decimal("0")
    current = Decimal("0")
    incompatible = False
    for index, consumer in enumerate(consumers):
        accepted = _range(consumer.get("voltage_range_v"), consumer.get("voltage_v"))
        if voltage is None or accepted is None:
            missing.append(f"consumers[{index}].voltage")
        elif not accepted[0] <= voltage <= accepted[1]:
            incompatible = True
        item_power = _decimal(consumer.get("power_w"))
        item_current = _decimal(consumer.get("current_a"))
        if item_power is None:
            missing.append(f"consumers[{index}].power_w")
        else:
            power += item_power
        if item_current is None:
            missing.append(f"consumers[{index}].current_a")
        else:
            current += item_current
    trace.append(
        {
            "rule": "distribution.psu_voltage",
            "actual": str(voltage) if voltage is not None else None,
            "result": "INCOMPATIBLE" if incompatible else "PASS",
        }
    )
    exceeded = (power_limit is not None and power > power_limit) or (
        current_limit is not None and current > current_limit
    )
    trace.append(
        {
            "rule": "distribution.psu_capacity",
            "actual": {"power_w": str(power), "current_a": str(current)},
            "required": {
                "rated_power_w": _text(power_limit),
                "rated_current_a": _text(current_limit),
            },
            "result": "LIMIT_EXCEEDED" if exceeded else "PASS",
        }
    )
    if incompatible:
        status = "INCOMPATIBLE"
    elif exceeded:
        status = "LIMIT_EXCEEDED"
    elif missing or power_limit is None or current_limit is None:
        status = "DATA_INCOMPLETE"
    else:
        status = "VERIFIED"
    return Assessment(status, tuple(trace), tuple(sorted(set(missing))))


def assess_distribution_node(
    *,
    available_points: int,
    used_points: int,
    rated_current_a,
    total_current_a,
    allowed_section_range_mm2,
    conductor_sections_mm2: tuple[Any, ...],
    required_bus_configuration: str,
    actual_bus_configuration: str,
    source_count: int,
) -> Assessment:
    trace = []
    errors = []
    if used_points > available_points:
        errors.append("POINT_CAPACITY")
    if source_count > 1:
        errors.append("MULTIPLE_SOURCES")
    rated = _decimal(rated_current_a)
    current = _decimal(total_current_a)
    if rated is None or current is None:
        status = "DATA_INCOMPLETE"
    elif current > rated:
        errors.append("CURRENT_LIMIT")
        status = "LIMIT_EXCEEDED"
    else:
        status = "VERIFIED"
    allowed = _range(allowed_section_range_mm2, None)
    for section in conductor_sections_mm2:
        value = _decimal(section)
        if value is None or allowed is None:
            status = "DATA_INCOMPLETE" if not errors else status
        elif not allowed[0] <= value <= allowed[1]:
            errors.append("CONDUCTOR_SECTION")
    if required_bus_configuration != actual_bus_configuration:
        errors.append("BUS_CONFIGURATION")
    if errors:
        status = "LIMIT_EXCEEDED" if errors == ["CURRENT_LIMIT"] else "INCOMPATIBLE"
    trace.append(
        {
            "rule": "distribution.node",
            "actual": {
                "used_points": used_points,
                "current_a": _text(current),
                "source_count": source_count,
                "bus_configuration": actual_bus_configuration,
            },
            "required": {
                "available_points": available_points,
                "rated_current_a": _text(rated),
                "bus_configuration": required_bus_configuration,
                "section_range_mm2": allowed_section_range_mm2,
            },
            "errors": errors,
        }
    )
    return Assessment(status, tuple(trace))


def assess_icl(
    *,
    icl: dict[str, Any] | None,
    power_supplies: tuple[dict[str, Any], ...],
    has_distribution_node: bool,
    project_voltage_v=230,
    project_frequency_hz=50,
    ambient_temperature_c=None,
    switching_cycles_per_minute=None,
    switching_interval_ms=None,
) -> Assessment:
    if icl is None or not power_supplies:
        return Assessment(
            "NOT_APPLICABLE",
            ({"rule": "icl.applicability", "result": "NOT_APPLICABLE"},),
        )
    trace = []
    missing = []
    incompatible = len(power_supplies) > 1 and not has_distribution_node
    project_voltage = _decimal(project_voltage_v)
    project_frequency = _decimal(project_frequency_hz)
    icl_voltage = _range(icl.get("input_voltage_range_v_ac"), None)
    icl_frequency = _range(icl.get("frequency_range_hz"), None)
    for index, psu in enumerate(power_supplies):
        if psu.get("current_kind", "AC") != "AC":
            incompatible = True
        psu_voltage = _range(psu.get("input_voltage_range_v_ac"), None)
        psu_frequency = _range(psu.get("input_frequency_range_hz"), None)
        if not _point_in_both(project_voltage, icl_voltage, psu_voltage):
            incompatible = True
        if not _point_in_both(project_frequency, icl_frequency, psu_frequency):
            incompatible = True
        for field in (
            "input_current_a_typical_at_230_v_ac",
            "input_apparent_power_va",
            "input_capacitance_uf",
            "startup_time_ms_at_230_v_ac",
        ):
            if psu.get(field) is None:
                missing.append(f"power_supplies[{index}].{field}")
    trace.append(
        {
            "rule": "icl.structure_and_ranges",
            "result": "INCOMPATIBLE" if incompatible else "PASS",
            "actual": {
                "power_supply_count": len(power_supplies),
                "has_distribution_node": has_distribution_node,
                "voltage_v": _text(project_voltage),
                "frequency_hz": _text(project_frequency),
            },
        }
    )
    sums = {}
    fields_and_limits = (
        ("input_current_a_typical_at_230_v_ac", "continuous_current_a"),
        ("input_apparent_power_va", "rated_load_va"),
        ("input_capacitance_uf", "maximum_capacitive_load_uf"),
    )
    exceeded = False
    for field, limit_field in fields_and_limits:
        values = [_decimal(psu.get(field)) for psu in power_supplies]
        limit = _decimal(icl.get(limit_field))
        total = None if any(value is None for value in values) else sum(values, Decimal("0"))
        sums[field] = _text(total)
        if limit is None:
            missing.append(f"icl.{limit_field}")
        if total is not None and limit is not None and total > limit:
            exceeded = True
        trace.append(
            {
                "rule": f"icl.{field}",
                "actual": _text(total),
                "required_max": _text(limit),
                "result": (
                    "DATA_INCOMPLETE"
                    if total is None or limit is None
                    else "LIMIT_EXCEEDED"
                    if total > limit
                    else "PASS"
                ),
            }
        )
    temperature = _decimal(ambient_temperature_c)
    temperature_range = _range(icl.get("operating_temperature_range_c"), None)
    if temperature is None:
        missing.append("project.ambient_temperature_c")
    elif temperature_range is None or not (
        temperature_range[0] <= temperature <= temperature_range[1]
    ):
        incompatible = True
    cycles = _decimal(switching_cycles_per_minute)
    interval = _decimal(switching_interval_ms)
    startup_values = [_decimal(psu.get("startup_time_ms_at_230_v_ac")) for psu in power_supplies]
    startup = None if any(value is None for value in startup_values) else max(startup_values)
    if cycles is None:
        missing.append("project.switching_cycles_per_minute")
    if startup is not None:
        if startup < 250:
            allowed_cycles = Decimal("0.2")
        elif startup <= 350:
            allowed_cycles = Decimal("1")
        else:
            allowed_cycles = Decimal("5")
        if cycles is not None and cycles > allowed_cycles:
            exceeded = True
        if startup > 350:
            if interval is None:
                missing.append("project.switching_interval_ms")
            elif interval <= 1500:
                exceeded = True
    trace.append(
        {
            "rule": "icl.switching_and_temperature",
            "actual": {
                "temperature_c": _text(temperature),
                "startup_time_ms": _text(startup),
                "cycles_per_minute": _text(cycles),
                "interval_ms": _text(interval),
            },
            "missing": sorted(set(missing)),
        }
    )
    if incompatible:
        status = "INCOMPATIBLE"
    elif exceeded:
        status = "LIMIT_EXCEEDED"
    elif missing:
        status = "DATA_INCOMPLETE"
    else:
        status = "VERIFIED"
    return Assessment(status, tuple(trace), tuple(sorted(set(missing))))


def _decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _range(value, point):
    if value is not None:
        try:
            low, high = value
        except (TypeError, ValueError):
            return None
        low, high = _decimal(low), _decimal(high)
        return None if low is None or high is None or low > high else (low, high)
    scalar = _decimal(point)
    return None if scalar is None else (scalar, scalar)


def _point_in_both(point, first, second) -> bool:
    return (
        point is not None
        and first is not None
        and second is not None
        and first[0] <= point <= first[1]
        and second[0] <= point <= second[1]
    )


def _text(value) -> str | None:
    return None if value is None else str(value)
