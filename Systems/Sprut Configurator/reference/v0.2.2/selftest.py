#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from pathlib import Path

from sprut_configurator import load_yaml_plan, load_discover_json, make_dry_run, verify_plan

ROOT = Path(__file__).resolve().parent
plan_path = ROOT / "05_31_Ivolga_sprut_plan_v3.yaml"
discover_path = ROOT / "Ivolga_home_sprut_2.json"

if not plan_path.exists() or not discover_path.exists():
    raise SystemExit("Self-test fixtures are missing.")

plan = load_yaml_plan(plan_path)
discover = load_discover_json(discover_path)
dry = make_dry_run(plan, discover)

print("targets:", dry.target_accessories)
print("changes:", len(dry.changes))
print("errors:", len(dry.errors))

if dry.target_accessories != 51:
    raise SystemExit("FAIL: expected 51 target accessories")

if dry.errors:
    print("\n".join(dry.errors))
    raise SystemExit("FAIL: DRY RUN contains errors")

verify = verify_plan(plan, discover)
failed = [row for row in verify if row.status == "FAILED"]

# Current discover is intentionally pre-APPLY, so VERIFY must have failures.
if not failed:
    raise SystemExit("FAIL: pre-APPLY fixture unexpectedly already matches plan")

print("PASS: YAML parsed; 51 targets resolved; no DRY RUN errors; pre-APPLY differences detected.")
