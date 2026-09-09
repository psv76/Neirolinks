#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Sprut Configurator v0.3.0-dev — Issue #22.

Development overlay on the frozen v0.2.2 reference.

Field-confirmed write RPC:
- Service.visible
- Characteristic.statusVisible
- Yandex bridge disable (delete)

Alice read-path and enable RPC are still not fully confirmed, therefore any
plan containing bridge.alice remains fail-closed before APPLY.
"""

from __future__ import annotations

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
    service_visible_params,
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

base.APP_VERSION = "0.3.0-dev"

_original_validate_plan_structure = base.validate_plan_structure
_original_make_dry_run = base.make_dry_run
_original_update_apply_state = base.SprutConfiguratorApp._update_apply_state

PRESENTATION_KINDS = {
    "service_visible",
    "characteristic_status_visible",
    "bridge_alice",
}

# Exact write frames captured from the real Sprut WebUI on Issue #22:
#
# {"params":{"service":{"update":{"aId":118,"sId":13,"visible":false}}},...}
# {"params":{"characteristic":{"update":{"aId":118,"sId":13,"cId":15,
#                                       "statusVisible":false}}},...}
# {"params":{"bridgeService":{"delete":{"bridgeIndex":"Yandex_1",
#                                      "aId":118,"sId":13}}},...}
#
# The bridge delete frame is documented, but bridge.alice remains blocked until
# the current membership read-path and enable/create frame are also confirmed.


def _as_v1(plan: dict[str, Any]) -> dict[str, Any]:
    clone = dict(plan)
    clone["format_version"] = 1
    return clone


def validate_plan_structure_v2(plan: Any) -> list[str]:
    if not isinstance(plan, dict):
        return _original_validate_plan_structure(plan)

    errors = _original_validate_plan_structure(_as_v1(plan))
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
    # v0.2.2 PlanAction predates Characteristic writes; attach runtime metadata
    # without modifying the frozen reference source.
    converted.characteristic_id = action.characteristic_id
    converted.characteristic_type = action.characteristic_type
    return converted


def make_dry_run_v2(plan: dict[str, Any], discover: dict[str, Any]):
    structural_errors = validate_plan_structure_v2(plan)

    # Reuse the proven v0.2.2 identity/name/room/service-name engine.
    base_dry = _original_make_dry_run(_as_v1(plan), discover)

    # Alice intentionally has no getter yet: a requested bridge policy yields
    # ERROR and therefore blocks APPLY. Service.visible/statusVisible can pass.
    presentation = make_presentation_diff(plan, discover)

    base_structure = set(_original_validate_plan_structure(_as_v1(plan)))
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

    dry = self.last_dry_run
    if not dry or not dry.ok:
        return

    # A bridge policy currently makes DRY RUN fail-closed already. This second
    # guard prevents accidental enablement if that behavior changes later.
    if any(a.kind == "bridge_alice" for a in dry.actions):
        self.apply_btn.configure(state="disabled")


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
        # Field-confirmed WebUI RPC shape.
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
        # Field-confirmed WebUI RPC shape.
        client.rpc(characteristic_status_visible_params(
            action.accessory_id,
            action.service_id,
            c_id,
            bool(action.expected),
        ))
        return

    if action.kind == "bridge_alice":
        # The disable RPC below is known, but a full desired-state action is not
        # safe until read + enable are known. Never silently perform one-way
        # bridge changes inside a generic APPLY.
        raise RuntimeError(
            "Alice bridge APPLY заблокирован: подтверждено только удаление "
            f"через bridgeService.delete/{FIELD_CONFIRMED_YANDEX_BRIDGE_INDEX}; "
            "нужны read-path и enable/create RPC."
        )

    raise RuntimeError(f"Неизвестный action kind={action.kind!r}")


def apply_after_confirm_v2(self, auth, plan, dry):
    if any(a.kind == "bridge_alice" for a in dry.actions):
        raise RuntimeError(
            "APPLY заблокирован: plan содержит bridge.alice, а полный "
            "read/write контракт Alice ещё не подтверждён."
        )

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


# Patch integration points only. Frozen v0.2.2 remains untouched.
base.load_yaml_plan = load_yaml_plan_v2
base.make_dry_run = make_dry_run_v2
base.verify_plan = verify_plan_v2
base.SprutConfiguratorApp._update_apply_state = update_apply_state_v2
base.SprutConfiguratorApp._apply_after_confirm = apply_after_confirm_v2


def main():
    base.main()


if __name__ == "__main__":
    main()
