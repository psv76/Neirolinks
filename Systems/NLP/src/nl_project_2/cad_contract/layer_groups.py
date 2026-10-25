"""Staged working-layer group helpers; not connected to runtime validation."""

from collections.abc import Collection

from .layer_names import parse_working_layer_name

_GROUP_BY_PREFIX = {
    100: "POWER",
    200: "SWITCHES",
    300: "LIGHTING_230V",
    400: "LIGHTING_LED",
    500: "SENSORS",
    600: "HVAC",
    700: "AV",
    800: "NETWORK",
    900: "BUS",
}


def function_group_for_working_layer(layer: object) -> str | None:
    """Resolve a C1-valid layer name without interpreting suffixes or cable IDs."""
    prefix = parse_working_layer_name(layer)
    if prefix is None:
        return None
    return _GROUP_BY_PREFIX[prefix]


def hvac_allowed_device_types(
    ventilation: Collection[str], heating: Collection[str]
) -> frozenset[str]:
    """Combine both device families without modifying their source collections."""
    return frozenset(ventilation) | frozenset(heating)
