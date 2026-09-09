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


def yandex_bridge_disable_params(
    a_id: int,
    s_id: int,
    bridge_index: str = FIELD_CONFIRMED_YANDEX_BRIDGE_INDEX,
) -> dict[str, Any]:
    """Build the captured Alice/Yandex bridge disable params.

    This is intentionally not used by generic APPLY yet because desired-state
    support also requires a confirmed current-state read path and enable/create
    operation for VERIFY and bidirectional reconciliation.
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
