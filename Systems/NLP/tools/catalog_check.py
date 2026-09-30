"""Validate approved catalog payload and optionally compare an installed SQLite catalog."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nl_project_2.catalog.payload import load_payload  # noqa: E402
from nl_project_2.catalog.queries import CatalogQueries  # noqa: E402
from nl_project_2.catalog.validation import CatalogValidationError, validate_payload  # noqa: E402
from nl_project_2.persistence.database import DatabaseManager  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-dir", type=Path, default=ROOT / "resources" / "catalogs")
    parser.add_argument("--database", type=Path)
    parser.add_argument(
        "--normative-dir",
        type=Path,
        default=ROOT / "docs" / "product" / "catalogs",
    )
    args = parser.parse_args()
    try:
        payload = load_payload(args.catalog_dir)
        validate_payload(payload)
        result = {
            "status": "PASSED",
            "content_sha256": payload.content_sha256,
            "passports": len(payload.passports["passports"]),
            "products": len(payload.products["products"]),
        }
        if args.normative_dir.is_dir():
            normative_passports = json.loads(
                (args.normative_dir / "equipment_passports.json").read_text(encoding="utf-8-sig")
            )
            normative_products = json.loads(
                (args.normative_dir / "products.json").read_text(encoding="utf-8-sig")
            )
            passport_equal = payload.passports == normative_passports
            product_equal = payload.products == normative_products
            result["normative_identity_and_facts_equal"] = passport_equal and product_equal
            if not result["normative_identity_and_facts_equal"]:
                raise ValueError("Packaged catalog differs from the normative 17/30 payload")
        if args.database:
            with DatabaseManager().open_existing(args.database) as database:
                queries = CatalogQueries(database.engine)
                result["database_passports"] = len(queries.passports())
                result["database_products"] = len(queries.products())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (CatalogValidationError, OSError, ValueError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
