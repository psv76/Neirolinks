#!/usr/bin/env python3
"""Apply Stage C service compatibility to an isolated CI merge worktree ONLY.

This is an experimental integration recipe, not an installed runtime change.
Fail closed if the upstream service shape changes.
"""
from pathlib import Path

P = Path("Systems/NLP/src/nl_project_2/cables/service.py")


def once(source: str, before: str, after: str) -> str:
    count = source.count(before)
    if count != 1:
        raise RuntimeError(f"Expected exactly one match, got {count}: {before[:100]!r}")
    return source.replace(before, after, 1)


def main() -> None:
    s = P.read_text(encoding="utf-8")
    s = once(s, "from decimal import ROUND_CEILING, Decimal, InvalidOperation",
             "from decimal import Decimal, InvalidOperation")
    s = once(s, "from .recalculation import (",
             "from .length_policy import round_up_quantity\nfrom .recalculation import (")
    s = once(s, "    board_reserve_for_line,\n    cable_line_length_breakdown,",
             "    board_reserve_for_line,\n    cable_length_policy,\n    cable_line_length_breakdown,")
    s = once(s, '''            "timber_reserve_m": (
                "0" if length_breakdown is None else str(length_breakdown.timber_reserve_m)
            ),
''', "")
    s = once(s, '''            "timber_segments": (
                0 if length_breakdown is None else length_breakdown.timber_segments
            ),
''', "")
    s = once(s, '''            rounded = unrounded.to_integral_value(rounding=ROUND_CEILING)''',
             '''            with UnitOfWork(self._engine) as uow:
                rounding_step = cable_length_policy(uow, project_id).rounding_step_m
            rounded = round_up_quantity(unrounded, rounding_step)''')
    if s.count('"rounded_up_to_1m"') != 2:
        raise RuntimeError("Unexpected legacy rounding labels")
    s = s.replace('"rounded_up_to_1m"', '"rounded_up_to_project_step"')
    s = once(s, '''            {
                "kind": "timber_reserve",
                "m": str(breakdown.timber_reserve_m),
                "segments": str(breakdown.timber_segments),
            },
''', "")
    P.write_text(s, encoding="utf-8")
    print("Prepared disposable integrated Stage C service; production source unchanged")


if __name__ == "__main__":
    main()
