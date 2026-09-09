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


def yandex_bridge_list_params(
    bridge_index: str = FIELD_CONFIRMED_YANDEX_BRIDGE_INDEX,
) -> dict[str, Any]:
    """Build the field-confirmed bridge membership read request."""
    return {
        "bridgeService": {
            "list": {
                "bridgeIndex": bridge_index,
            }
        }
    }


def parse_yandex_bridge_services(result: Any) -> list[dict[str, Any]]:
    """Parse the field-confirmed bridgeService.list result shape.

    Expected result:
    {"bridgeService":{"list":{"services":[...]}}}
    """
    try:
        services = result["bridgeService"]["list"]["services"]
    except (TypeError, KeyError) as exc:
        raise ValueError(
            "Не удалось распознать ответ bridgeService.list: "
            "ожидается result.bridgeService.list.services."
        ) from exc

    if not isinstance(services, list) or not all(
        isinstance(item, dict) for item in services
    ):
        raise ValueError(
            "bridgeService.list.services должен быть списком объектов."
        )

    return services


def yandex_bridge_membership(
    bridge_services: list[dict[str, Any]],
    a_id: int,
    s_id: int,
    bridge_index: str = FIELD_CONFIRMED_YANDEX_BRIDGE_INDEX,
) -> bool:
    """Return whether exact aId+sId Service is present in the bridge."""
    return any(
        item.get("bridgeIndex") == bridge_index
        and item.get("aId") == a_id
        and item.get("sId") == s_id
        for item in bridge_services
    )


def yandex_bridge_enable_params(
    a_id: int,
    s_id: int,
    bridge_index: str = FIELD_CONFIRMED_YANDEX_BRIDGE_INDEX,
) -> dict[str, Any]:
    """Build the field-confirmed Alice/Yandex bridge enable params."""
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
    """Build the field-confirmed Alice/Yandex bridge disable params."""
    return {
        "bridgeService": {
            "delete": {
                "bridgeIndex": bridge_index,
                "aId": a_id,
                "sId": s_id,
            }
        }
    }
