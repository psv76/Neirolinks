"""Signed catalog integrity must remain strict across Git newline normalization."""

import hashlib

import pytest

from nl_project_2.catalog.payload import load_packaged_payload, load_payload
from nl_project_2.catalog.validation import CatalogValidationError, validate_payload


def test_signed_crlf_catalog_accepts_lf_checkout_without_changing_release():
    payload = load_packaged_payload()
    validate_payload(payload)
    assert payload.content_sha256 == payload.manifest["content_sha256"]
    for filename, expected in payload.manifest["files"].items():
        assert hashlib.sha256(payload.raw_files[filename]).hexdigest() == expected


def test_newline_normalization_cannot_hide_catalog_tampering(tmp_path):
    approved = load_packaged_payload()
    (tmp_path / "catalog_manifest.json").write_text(
        __import__("json").dumps(approved.manifest), encoding="utf-8"
    )
    for filename, source in approved.raw_files.items():
        data = source.replace(b"\r\n", b"\n")
        if filename == "products.json":
            data = data.replace(b'"schema_version"', b'"schema_versi0n"', 1)
        (tmp_path / filename).write_bytes(data)
    payload = load_payload(tmp_path)
    with pytest.raises(CatalogValidationError, match="HASH_MISMATCH"):
        validate_payload(payload)
