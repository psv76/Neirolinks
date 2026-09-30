"""Typed value objects for persisted field/topology identity."""

from __future__ import annotations

from dataclasses import dataclass


class FieldModelRuleError(ValueError):
    """A requested field/topology fact violates the approved closed contract."""


LED_LAYOUT = {
    "MONO": (1, 2),
    "CCT": (2, 3),
    "RGB": (3, 4),
    "RGBW": (4, 5),
}

MOUNT_WAYS = frozenset({"По полу", "По потолку", "В стене", "В кабель-канале"})

CANONICAL_FIELD_PORTS = {
    "WB_MRM2_MINI": {
        "COM1": ("RELAY_COMMON", "BIDIRECTIONAL"),
        "COM2": ("RELAY_COMMON", "BIDIRECTIONAL"),
        "K1": ("RELAY_OUTPUT", "OUT"),
        "K2": ("RELAY_OUTPUT", "OUT"),
        "IN_1": ("DIGITAL_INPUT", "IN"),
        "IN_2": ("DIGITAL_INPUT", "IN"),
    },
    "WB_M1W2": {
        "W1": ("ONEWIRE_CHANNEL", "BIDIRECTIONAL"),
        "W2": ("ONEWIRE_CHANNEL", "BIDIRECTIONAL"),
    },
}


@dataclass(frozen=True, slots=True)
class RouteFacts:
    mount_way: str | None = None
    gofra_type: str | None = None
    gofra_color: str | None = None

    def normalized(self) -> RouteFacts:
        mount_way = None if self.mount_way in (None, "") else str(self.mount_way).strip()
        if mount_way is not None and mount_way not in MOUNT_WAYS:
            raise FieldModelRuleError(f"Unsupported segment MOUNT_WAY: {self.mount_way}")
        return RouteFacts(
            mount_way,
            None if self.gofra_type in (None, "") else str(self.gofra_type).strip(),
            None if self.gofra_color in (None, "") else str(self.gofra_color).strip(),
        )


def normalize_led_type(value: str) -> tuple[str, int, int]:
    normalized = str(value).strip().upper()
    layout = LED_LAYOUT.get(normalized)
    if layout is None:
        raise FieldModelRuleError(f"Unsupported canonical LED_TYPE: {value}")
    channels, conductors = layout
    return normalized, channels, conductors


def canonical_port(block_kind: str, port_tag: str) -> tuple[str, str]:
    block = str(block_kind).strip().upper()
    tag = str(port_tag).strip().upper()
    spec = CANONICAL_FIELD_PORTS.get(block, {}).get(tag)
    if spec is None:
        raise FieldModelRuleError(f"Port {tag} is not approved for field device {block}")
    return spec
