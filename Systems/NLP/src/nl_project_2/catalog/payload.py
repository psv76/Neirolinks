"""Load the approved catalog payload explicitly; runtime queries never read JSON."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nl_project_2.runtime_resources import bundled_path


@dataclass(frozen=True)
class CatalogPayload:
    manifest: dict[str, Any]
    passports: dict[str, Any]
    products: dict[str, Any]
    raw_files: dict[str, bytes]

    @property
    def content_sha256(self) -> str:
        joined = (
            self.raw_files["equipment_passports.json"] + b"\0" + self.raw_files["products.json"]
        )
        return hashlib.sha256(joined).hexdigest()


def default_catalog_directory() -> Path:
    return bundled_path("resources", "catalogs")


def load_payload(directory: str | Path) -> CatalogPayload:
    root = Path(directory).resolve()
    raw = {
        name: (root / name).read_bytes() for name in ("equipment_passports.json", "products.json")
    }
    return CatalogPayload(
        manifest=json.loads((root / "catalog_manifest.json").read_text(encoding="utf-8")),
        passports=json.loads(raw["equipment_passports.json"].decode("utf-8-sig")),
        products=json.loads(raw["products.json"].decode("utf-8-sig")),
        raw_files=raw,
    )


def load_packaged_payload() -> CatalogPayload:
    return load_payload(default_catalog_directory())
