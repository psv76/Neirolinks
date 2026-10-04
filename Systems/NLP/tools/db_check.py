"""Read-only database structure and referential-integrity check."""

from __future__ import annotations

import argparse
import json

from nl_project_2.persistence.diagnostics import inspect_database


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", help="Path to an existing NL Project 3.0 SQLite file")
    arguments = parser.parse_args()
    result = inspect_database(arguments.database)
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
