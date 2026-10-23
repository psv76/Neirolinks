"""Reproduce H1 against pinned pure source; success means defect reproduced.

No application imports, database, CAD, migration or network access.
Requires the two pinned commits to be available in this Git checkout.
This diagnostic is not a runtime acceptance test or a proposed height policy.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import types
from decimal import Decimal
from pathlib import Path

MAIN = "8f566f7a1eddb2c7eb4242dd275cdd775ca79a89"
STAGE_C = "ff9b0ef52f89d5f9445b55b468414adbaf8a331e"
REPO = Path(__file__).resolve().parents[3]
PREFIX = "Systems/NLP/src/nl_project_2/"


def source(revision: str, path: str) -> str:
    return subprocess.check_output(["git", "show", f"{revision}:{PREFIX}{path}"], cwd=REPO).decode(
        "utf-8"
    )


def pure_domain(revision: str) -> types.ModuleType:
    tree = ast.parse(source(revision, "cables/domain.py"))
    # Load only inspected arithmetic definitions, never the application package.
    names = {
        "CableCalculationError",
        "RouteMethod",
        "CablePointInput",
        "calculate_segment_length",
        "_decimal",
    }
    definitions = [
        node
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names
    ]
    assert {node.name for node in definitions} == names
    imports = ast.parse(
        "from __future__ import annotations\n"
        "from dataclasses import dataclass\n"
        "from decimal import Decimal, InvalidOperation\n"
        "from enum import StrEnum\n"
    ).body
    module = types.ModuleType(f"height_evidence_{revision}")
    sys.modules[module.__name__] = module
    exec(compile(ast.Module(imports + definitions, []), revision, "exec"), module.__dict__)
    return module


def ceiling_required_fields(path: str, route_type: type) -> list[str]:
    """Execute only the source's required-field selection, not its DB adapter."""
    tree = ast.parse(source(STAGE_C, path))
    candidates = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for index, statement in enumerate(node.body):
            if isinstance(statement, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "required" for t in statement.targets
            ):
                selection = [statement]
                for following in node.body[index + 1 :]:
                    if not isinstance(following, ast.If):
                        break
                    selection.append(following)
                candidates.append(selection)
    assert len(candidates) == 1, "Required-field source shape changed; re-audit"
    namespace = {"route": route_type.CEILING, "RouteMethod": route_type}
    exec(compile(ast.Module(candidates[0], []), path, "exec"), namespace)
    return sorted(namespace["required"])


def check() -> None:
    results = {}
    ac033 = {}
    for label, revision in (("main", MAIN), ("stage_c", STAGE_C)):
        module = pure_domain(revision)
        points = [
            module.CablePointInput.from_values(
                x_mm=x,
                y_mm=0,
                mount_height_mm=1000,
                base_mark_mm=-250,
                room_height_m=3,
            )
            for x in (0, 2000)
        ]
        length, _ = module.calculate_segment_length(*points, module.RouteMethod.CEILING)
        results[label] = str(length)
        reference_points = [
            module.CablePointInput.from_values(
                x_mm=x,
                y_mm=y,
                mount_height_mm=300,
                base_mark_mm=base,
                room_height_m=height,
            )
            for x, y, base, height in ((0, 0, -250, "2.8"), (1000, 2000, -150, "3.0"))
        ]
        ac033[label] = {
            route.name: str(module.calculate_segment_length(*reference_points, route)[0])
            for route in (
                module.RouteMethod.FLOOR,
                module.RouteMethod.CEILING,
                module.RouteMethod.CABLE_CHANNEL,
            )
        }
    # Doc 11 and user clarification: heights are measured from finished floor;
    # ceiling 3000 mm, two device ends at 1000 mm, horizontal run 2000 mm.
    assert Decimal(results["main"]) == Decimal("6")
    assert Decimal(results["stage_c"]) == Decimal("5.5")
    for label in ac033:
        assert Decimal(ac033[label]["FLOOR"]) == Decimal("4.1")
        assert Decimal(ac033[label]["CABLE_CHANNEL"]) == Decimal("3")
    assert Decimal(ac033["main"]["CEILING"]) == Decimal("8.4")
    assert Decimal(ac033["stage_c"]["CEILING"]) == Decimal("8.1")
    requirements = {
        path: ceiling_required_fields(path, module.RouteMethod)
        for path in ("cables/recalculation.py", "buses/recalculation.py")
    }
    for fields in requirements.values():
        # Absence of base is correct for C=R*1000; fix the formula, not this set.
        assert "height" in fields and "mount" in fields and "base" not in fields
    print(
        json.dumps(
            {
                "status": "H1_REPRODUCED_NOT_ACCEPTANCE",
                "main_sha": MAIN,
                "stage_c_sha": STAGE_C,
                "doc11_expected_m": "6",
                "actual_m": results,
                "ac033_actual_m": ac033,
                "clarification": "base is not a required input to the correct ceiling formula",
                "stage_c_ceiling_required_fields": requirements,
                "scope": "pure source arithmetic and required-field selection only",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    check()
