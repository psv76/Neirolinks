"""Read-only command-line self-check for the TASK_010 machine contract."""

from __future__ import annotations

import argparse
from pathlib import Path

from nl_project_2.cad_contract import load_contract


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=None)
    args = parser.parse_args()
    contract = load_contract(args.contract)
    directory = (
        args.contract.parent
        if args.contract is not None
        else Path(__file__).parents[1] / "resources" / "autocad"
    )
    forbidden = sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.casefold() in {".dwg", ".dxf", ".dwt", ".dws"}
    )
    if forbidden:
        for path in forbidden:
            print(f"FORBIDDEN_GRAPHICAL_RESOURCE:{path}")
        return 1
    print(
        f"OK contract={contract.contract_version} names={len(contract.blocks)} "
        f"groups={len(contract.functional_groups)} geometry_files=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
