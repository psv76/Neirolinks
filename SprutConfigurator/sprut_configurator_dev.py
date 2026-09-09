#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Sprut Configurator v0.3.0-dev.

Development launcher for Issue #22.

The frozen v0.2.2 implementation remains the proven base. This launcher overlays
format_version 2 presentation validation/diff/DRY RUN/VERIFY.

Presentation APPLY is intentionally fail-closed until exact outgoing Sprut WebUI
write frames are captured and field-confirmed.
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

ROOT = Path(__file__).resolve().parent
BASE_PATH = ROOT / "reference" / "v0.2.2" / "sprut_configurator.py"

_spec = importlib.util.spec_from_file_location("sprut_configurator_v022_base", BASE_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Не удалось загрузить reference Configurator: {BASE_PATH}")

base = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = base
_spec.loader.exec_module(base)

base.APP_VERSION = "0.3.0-dev"

_original_validate_plan_structure = base.validate_plan_structure
_original_make_dry_run = base.make_dry_run
_original_update_apply_state = base.SprutConfiguratorApp._update_apply_state
_original_apply_after_confirm = base.SprutConfiguratorApp._apply_after_confirm

PRESENTATION_KINDS = {
    "service_visible",
    "characteristic_status_visible",
    "bridge_alice",
}


def _as_v1(plan: dict[str, Any]) -> dict[str, Any]:
    """Reuse proven v0.2.2 validation/diff without mutating the v2 plan."""
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
    return base.PlanAction(
        status=action.status,
        serial=action.serial,
        kind=action.kind,
        current=str(action.current),
        expected=str(action.expected),
        detail=action.detail,
        accessory_id=action.accessory_id,
        service_id=action.service_id,
        room_id=None,
        service_type=action.service_type,
    )


def make_dry_run_v2(plan: dict[str, Any], discover: dict[str, Any]):
    structural_errors = validate_plan_structure_v2(plan)

    # The original function still sees the original v1 validator in its module
    # globals, so this call remains a clean regression reuse of v0.2.2.
    base_dry = _original_make_dry_run(_as_v1(plan), discover)
    presentation = make_presentation_diff(plan, discover)

    base_structure = set(_original_validate_plan_structure(_as_v1(plan)))
    runtime_base_errors = [e for e in base_dry.errors if e not in base_structure]

    actions = list(base_dry.actions)
    actions.extend(_presentation_action_to_base(a) for a in presentation.actions)

    errors = list(structural_errors)
    for error in runtime_base_errors + presentation.errors:
        if error not in errors:
            errors.append(error)

    return base.DryRunResult(
        actions=actions,
        errors=errors,
        target_accessories=base_dry.target_accessories,
    )


def update_apply_state_v2(self):
    _original_update_apply_state(self)

    dry = self.last_dry_run
    if dry and any(action.kind in PRESENTATION_KINDS for action in dry.actions):
        self.apply_btn.configure(state="disabled")


def apply_after_confirm_fail_closed(self, auth, plan, dry):
    """Second safety barrier: never partially APPLY an unconfirmed v2 write."""
    if any(action.kind in PRESENTATION_KINDS for action in dry.actions):
        detail = ", ".join(
            sorted({action.kind for action in dry.actions if action.kind in PRESENTATION_KINDS})
        )
        raise RuntimeError(
            "APPLY v0.3.0-dev заблокирован для presentation policy "
            f"({detail}). Реальные write RPC Sprut WebUI ещё не подтверждены. "
            "Это намеренная fail-closed защита от частичной записи."
        )

    return _original_apply_after_confirm(self, auth, plan, dry)


# Patch only the integration points needed by the existing GUI.
# Keep base.validate_plan_structure untouched so the frozen v0.2.2 engine can
# still validate its v1 clone without recursion or format-version leakage.
base.load_yaml_plan = load_yaml_plan_v2
base.make_dry_run = make_dry_run_v2
base.SprutConfiguratorApp._update_apply_state = update_apply_state_v2
base.SprutConfiguratorApp._apply_after_confirm = apply_after_confirm_fail_closed


def main():
    base.main()


if __name__ == "__main__":
    main()
