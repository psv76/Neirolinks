from __future__ import annotations

from typing import Any

# Field-confirmed on real Sprut WebUI during Issue #22.
FIELD_CONFIRMED_YANDEX_BRIDGE_INDEX = "Yandex_1"


def service_visible_params(a_id: int, s_id: int, visible: bool) -> dict[str, Any]:
    """Build field-confirmed Service.visible params."""
    return {
        "service": {
            "update": {
                "aId": a_id,
                "sId": s_id,
                "visible": bool(visible),
            }
        }
    }


def characteristic_status_visible_params(
    a_id: int,
    s_id: int,
    c_id: int,
    status_visible: bool,
) -> dict[str, Any]:
    """Build field-confirmed Characteristic.statusVisible params."""
    return {
        "characteristic": {
            "update": {
                "aId": a_id,
                "sId": s_id,
                "cId": c_id,
                "statusVisible": bool(status_visible),
            }
        }
    }


def yandex_bridge_enable_params(
    a_id: int,
    s_id: int,
    bridge_index: str = FIELD_CONFIRMED_YANDEX_BRIDGE_INDEX,
) -> dict[str, Any]:
    """Build the captured Alice/Yandex bridge enable params.

    The WebUI create frame was captured with write=true. The operation is
    field-confirmed, but generic desired-state APPLY remains blocked until the
    current bridge membership read-path is also confirmed for DRY RUN/VERIFY.
    """
    return {
        "bridgeService": {
            "create": {
                "bridgeIndex": bridge_index,
                "aId": a_id,
                "sId": s_id,
                "write": True,
            }
        }
    }


def yandex_bridge_disable_params(
    a_id: int,
    s_id: int,
    bridge_index: str = FIELD_CONFIRMED_YANDEX_BRIDGE_INDEX,
) -> dict[str, Any]:
    """Build the captured Alice/Yandex bridge disable params.

    Both bridge enable/create and disable/delete operations are now
    field-confirmed. Generic desired-state APPLY remains blocked until the
    current bridge membership read-path is confirmed for DRY RUN/VERIFY.
    """
    return {
        "bridgeService": {
            "delete": {
                "bridgeIndex": bridge_index,
                "aId": a_id,
                "sId": s_id,
            }
        }
    }
