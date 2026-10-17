#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Sprut Configurator v0.3.1-dev — Issue #22.

Development overlay on the frozen v0.2.2 reference.

Field-confirmed on real Sprut WebUI:
- Service.visible update
- Characteristic.statusVisible update
- Yandex bridge membership list
- Yandex bridge enable/create
- Yandex bridge disable/delete

v0.3.1-dev additionally supports an optional Service `match_name` selector for
the case when one Accessory contains several Services with the same type.
Matching remains fail-closed and never stores runtime sId in YAML.

All presentation policies participate in:
DISCOVER -> diff -> DRY RUN -> APPLY -> fresh DISCOVER -> VERIFY.
"""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import sys
from pathlib import Path
from typing import Any

from src.presentation_core import (
    make_presentation_diff,
    validate_presentation_plan,
)
from src.rpc_contract import (
    FIELD_CONFIRMED_YANDEX_BRIDGE_INDEX,
    characteristic_status_visible_params,
    parse_yandex_bridge_services,
    service_visible_params,
    yandex_bridge_disable_params,
    yandex_bridge_enable_params,
    yandex_bridge_list_params,
    yandex_bridge_membership,
)

ROOT = Path(__file__).resolve().parent
BASE_PATH = ROOT / "reference" / "v0.2.2" / "sprut_configurator.py"

_spec = importlib.util.spec_from_file_location(
    "sprut_configurator_v022_base", BASE_PATH
)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Не удалось загрузить reference Configurator: {BASE_PATH}")

base = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = base
_spec.loader.exec_module(base)

base.APP_VERSION = "0.3.1-dev"

_original_validate_plan_structure = base.validate_plan_structure
_original_make_dry_run = base.make_dry_run
_original_update_apply_state = base.SprutConfiguratorApp._update_apply_state
_original_client_discover = base.SprutClient.discover


def _as_v1(plan: dict[str, Any]) -> dict[str, Any]:
    clone = deepcopy(plan)
    clone["format_version"] = 1
    return clone


def _selector_type(service_type: str, match_name: str) -> str:
    """Synthetic type used only inside the frozen v0.2.2 matching engine."""
    return f"{service_type}@@match_name={match_name}"


def _selector_plan_for_base(plan: dict[str, Any]) -> dict[str, Any]:
    """Create a v1-compatible view where selected duplicate Services are unique.

    `match_name` never reaches Sprut. It is translated to a synthetic Service
    type only for the frozen v0.2.2 structural/diff engine.
    """
    clone = _as_v1(plan)
    for accessory in clone.get("accessories", []):
        if not isinstance(accessory, dict):
            continue
        services = accessory.get("services", [])
        if not isinstance(services, list):
            continue
        for service in services:
            if not isinstance(service, dict):
                continue
            service_type = service.get("type")
            match_name = service.get("match_name")
            if (
                isinstance(service_type, str)
                and service_type
                and isinstance(match_name, str)
                and match_name
            ):
                service["type"] = _selector_type(service_type, match_name)
    return clone


def _selector_discover_for_base(
    plan: dict[str, Any],
    discover: dict[str, Any],
) -> dict[str, Any]:
    """Mirror `match_name` selectors into a DISCOVER copy for legacy matching."""
    clone = deepcopy(discover)
    accessories = clone.get("accessories", [])
    if not isinstance(accessories, list):
        return clone

    by_serial: dict[str, list[dict[str, Any]]] = {}
    for accessory in accessories:
        if isinstance(accessory, dict):
            by_serial.setdefault(str(accessory.get("serial", "")), []).append(accessory)

    for target in plan.get("accessories", []):
        if not isinstance(target, dict):
            continue
        serial = target.get("serial")
        if not isinstance(serial, str) or not serial:
            continue

        for service_target in target.get("services", []):
            if not isinstance(service_target, dict):
                continue
            service_type = service_target.get("type")
            match_name = service_target.get("match_name")
            if not (
                isinstance(service_type, str)
                and service_type
                and isinstance(match_name, str)
                and match_name
            ):
                continue

            synthetic = _selector_type(service_type, match_name)
            for accessory in by_serial.get(serial, []):
                services = accessory.get("services", [])
                if not isinstance(services, list):
                    continue
                for service in services:
                    if not isinstance(service, dict):
                        continue
                    if (
                        not bool(service.get("system"))
                        and service.get("type") != "AccessoryInformation"
                        and service.get("type") == service_type
                        and str(service.get("name", "")) == match_name
                    ):
                        service["type"] = synthetic

    return clone


def validate_plan_structure_v2(plan: Any) -> list[str]:
    if not isinstance(plan, dict):
        return _original_validate_plan_structure(plan)

    base_view = _selector_plan_for_base(plan)
    errors = _original_validate_plan_structure(base_view)
    errors.extend(validate_presentation_plan(plan))
    return errors


def load_yaml_plan_v2(path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        data = base.yaml.safe_load(fh)
    errors = validate_plan_structure_v2(data)
    if errors:
        raise ValueError("\n".join(errors))
    return data


def _presentation_action_to_base(action):
    converted = base.PlanAction(
        status=action.status,
        serial=action.serial,
        kind=action.kind,
        current=action.current,
        expected=action.expected,
        detail=action.detail,
        accessory_id=action.accessory_id,
        service_id=action.service_id,
        room_id=None,
        service_type=action.service_type,
    )
    converted.characteristic_id = action.characteristic_id
    converted.characteristic_type = action.characteristic_type
    return converted


def list_yandex_bridge_services(self):
    """Read current Service membership of Yandex_1 via field-confirmed RPC."""
    result = self.rpc(yandex_bridge_list_params())
    return parse_yandex_bridge_services(result)


def discover_v2(self):
    """Extend proven v0.2.2 DISCOVER with current Yandex bridge membership."""
    data = _original_client_discover(self)
    services = list_yandex_bridge_services(self)

    bridges = data.setdefault("bridges", {})
    bridges[FIELD_CONFIRMED_YANDEX_BRIDGE_INDEX] = services

    meta = data.setdefault("meta", {})
    meta["yandex_bridge_index"] = FIELD_CONFIRMED_YANDEX_BRIDGE_INDEX
    meta["yandex_bridge_services_count"] = len(services)
    return data


def _alice_state_getter_from_discover(discover: dict[str, Any]):
    bridges = discover.get("bridges")
    if not isinstance(bridges, dict):
        return None

    services = bridges.get(FIELD_CONFIRMED_YANDEX_BRIDGE_INDEX)
    if not isinstance(services, list):
        return None

    def getter(accessory: dict[str, Any], service: dict[str, Any]) -> bool | None:
        a_id = accessory.get("id")
        s_id = service.get("sId")
        if not isinstance(a_id, int) or not isinstance(s_id, int):
            return None
        return yandex_bridge_membership(
            services,
            a_id,
            s_id,
            FIELD_CONFIRMED_YANDEX_BRIDGE_INDEX,
        )

    return getter


def make_dry_run_v2(plan: dict[str, Any], discover: dict[str, Any]):
    structural_errors = validate_plan_structure_v2(plan)

    base_plan = _selector_plan_for_base(plan)
    base_discover = _selector_discover_for_base(plan, discover)
    base_dry = _original_make_dry_run(base_plan, base_discover)

    presentation = make_presentation_diff(
        plan,
        discover,
        alice_state_getter=_alice_state_getter_from_discover(discover),
    )

    base_structure = set(_original_validate_plan_structure(base_plan))
    runtime_base_errors = [
        e for e in base_dry.errors if e not in base_structure
    ]

    actions = list(base_dry.actions)
    actions.extend(
        _presentation_action_to_base(a) for a in presentation.actions
    )

    errors = list(structural_errors)
    for error in runtime_base_errors + presentation.errors:
        if error not in errors:
            errors.append(error)

    return base.DryRunResult(
        actions=actions,
        errors=errors,
        target_accessories=base_dry.target_accessories,
    )


def verify_plan_v2(plan: dict[str, Any], discover: dict[str, Any]):
    """VERIFY all legacy and v2 desired-state fields through one fresh diff."""
    dry = make_dry_run_v2(plan, discover)
    by_serial: dict[str, list[Any]] = {}
    for action in dry.actions:
        by_serial.setdefault(action.serial, []).append(action)

    rows = []
    for target in plan.get("accessories", []):
        serial = target["serial"]
        actions = by_serial.get(serial, [])
        if not actions:
            rows.append(base.VerifyRow(
                serial, "FAILED", "Нет результатов проверки."
            ))
            continue

        bad = [a for a in actions if a.status in ("ERROR", "CHANGE")]
        if bad:
            details = []
            for action in bad:
                if action.status == "ERROR":
                    details.append(action.detail)
                else:
                    details.append(
                        f"{action.detail}: фактически={action.current!r}, "
                        f"ожидается={action.expected!r}"
                    )
            rows.append(base.VerifyRow(
                serial, "FAILED", "; ".join(details)
            ))
        else:
            rows.append(base.VerifyRow(
                serial, "PASSED",
                "Имя, комната, Service и presentation policy соответствуют плану."
            ))
    return rows


def update_apply_state_v2(self):
    _original_update_apply_state(self)


def _write_action(client, action):
    if action.kind == "accessory_name":
        client.update_accessory_name(action.accessory_id, action.expected)
        return

    if action.kind == "room":
        client.update_accessory_room(action.accessory_id, action.room_id)
        return

    if action.kind == "service_name":
        client.update_service_name(
            action.accessory_id, action.service_id, action.expected
        )
        return

    if action.kind == "service_visible":
        client.rpc(service_visible_params(
            action.accessory_id,
            action.service_id,
            bool(action.expected),
        ))
        return

    if action.kind == "characteristic_status_visible":
        c_id = getattr(action, "characteristic_id", None)
        if c_id is None:
            raise RuntimeError(
                f"{action.serial}: отсутствует cId для statusVisible APPLY."
            )
        client.rpc(characteristic_status_visible_params(
            action.accessory_id,
            action.service_id,
            c_id,
            bool(action.expected),
        ))
        return

    if action.kind == "bridge_alice":
        if bool(action.expected):
            client.rpc(yandex_bridge_enable_params(
                action.accessory_id,
                action.service_id,
            ))
        else:
            client.rpc(yandex_bridge_disable_params(
                action.accessory_id,
                action.service_id,
            ))
        return

    raise RuntimeError(f"Неизвестный action kind={action.kind!r}")


def apply_after_confirm_v2(self, auth, plan, dry):
    changes = list(dry.changes)

    def work():
        completed = 0
        with base.SprutClient(auth, self.log) as client:
            for action in changes:
                _write_action(client, action)
                completed += 1
                self.log(
                    f"APPLY {completed}/{len(changes)}: {action.serial} — "
                    f"{action.detail}: {action.current!r} -> {action.expected!r}"
                )
            fresh = client.discover()
        return fresh, completed

    def done(payload):
        fresh, completed = payload
        self.discover_data = fresh
        self.discover_source = "LIVE after APPLY"
        self.last_dry_run = None
        self.last_dry_plan_hash = None
        self._update_apply_state()
        self.refresh_discover_tree()
        self._update_meta()
        self.log(
            f"APPLY завершён: выполнено {completed} RPC-изменений. "
            "Запускаю VERIFY."
        )
        self._render_verify(verify_plan_v2(plan, fresh))

    self._run_worker("APPLY: запись в Sprut...", work, done)


base.load_yaml_plan = load_yaml_plan_v2
base.make_dry_run = make_dry_run_v2
base.verify_plan = verify_plan_v2
base.SprutClient.discover = discover_v2
base.SprutConfiguratorApp._update_apply_state = update_apply_state_v2
base.SprutConfiguratorApp._apply_after_confirm = apply_after_confirm_v2


def main():
    base.main()


if __name__ == "__main__":
    main()
