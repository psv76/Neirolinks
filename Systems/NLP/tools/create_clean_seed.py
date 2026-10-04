"""Create a clean NL Project 3.0 working database from explicitly allowed legacy seed."""

from __future__ import annotations

import argparse
from pathlib import Path

from nl_project_2.operations.clean_seed import create_clean_seed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-db", type=Path, required=True)
    parser.add_argument("--target-db", type=Path, required=True)
    parser.add_argument("--legacy-snapshot-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--copy-project-setting", action="append", default=[])
    args = parser.parse_args()

    receipt = create_clean_seed(
        legacy_database=args.legacy_db,
        target_database=args.target_db,
        legacy_snapshot_root=args.legacy_snapshot_root,
        copied_setting_keys=tuple(args.copy_project_setting),
    )
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(receipt.to_json(), encoding="utf-8")
    print(receipt.to_json(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
