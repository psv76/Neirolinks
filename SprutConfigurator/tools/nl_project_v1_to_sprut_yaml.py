from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nl_project_v1_adapter import extract_object_source_model
from sprut_plan_generator import generate_sprut_plan


def _safe_snapshot(model: dict) -> dict:
    """Strip workstation-local absolute paths before saving a repo fixture."""
    clone = json.loads(json.dumps(model, ensure_ascii=False))
    source = clone.get("source")
    if isinstance(source, dict):
        source.pop("project_folder", None)
        source.pop("layout_dwg_path", None)
        source["scope_note"] = (
            "Extracted from NL Project 1.0 read-only copy; "
            "local workstation paths omitted."
        )
    return clone


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate Sprut Plan YAML from a read-only NL Project 1.0 database "
            "copy through the normalized Project-source boundary."
        )
    )
    parser.add_argument("database", help="Path to a COPY of nl_project.sqlite")
    parser.add_argument("--object", required=True, dest="object_name")
    parser.add_argument("--policy", required=True, help="Sprut export policy YAML")
    parser.add_argument("--output", required=True, help="Generated Sprut Plan YAML")
    parser.add_argument(
        "--source-snapshot",
        help="Optional sanitized JSON snapshot of normalized Project source data",
    )
    args = parser.parse_args()

    source_model = extract_object_source_model(args.database, args.object_name)
    policy = yaml.safe_load(Path(args.policy).read_text(encoding="utf-8-sig"))
    result = generate_sprut_plan(source_model, policy)

    if not result.ok:
        for error in result.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2

    output = Path(args.output)
    output.write_text(
        yaml.safe_dump(result.plan, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    if args.source_snapshot:
        Path(args.source_snapshot).write_text(
            json.dumps(_safe_snapshot(source_model), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )

    print(
        f"PASS: generated {len(result.plan['accessories'])} accessories -> {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
