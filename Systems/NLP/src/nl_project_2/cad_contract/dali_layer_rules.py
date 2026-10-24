"""Staged DALI_GROUP placement eligibility, not a runtime validation rule."""

from .layer_groups import function_group_for_working_layer


def is_valid_dali_group_layer(layer: object) -> bool:
    """Allow any valid lighting working layer; do not validate logical IDs."""
    return function_group_for_working_layer(layer) in {"LIGHTING_230V", "LIGHTING_LED"}
