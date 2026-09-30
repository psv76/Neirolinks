"""Download and verify exact LGPL corresponding-source archives for packaging."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "packaging" / "compliance_sources.json"
DEFAULT_CACHE = ROOT / ".cache" / "compliance-sources"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare(config_path: Path, cache_directory: Path) -> list[dict]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    cache_directory.mkdir(parents=True, exist_ok=True)
    receipts = []
    for source in config["sources"]:
        target = cache_directory / source["filename"]
        if not target.is_file() or target.stat().st_size != source["bytes"]:
            partial = target.with_suffix(target.suffix + ".partial")
            partial.unlink(missing_ok=True)
            with urllib.request.urlopen(source["download_url"], timeout=120) as response:
                with partial.open("wb") as output:
                    while block := response.read(1024 * 1024):
                        output.write(block)
            os.replace(partial, target)
        actual_hash = sha256(target)
        if target.stat().st_size != source["bytes"] or actual_hash != source["sha256"]:
            raise RuntimeError(f"Compliance source verification failed: {target}")
        receipts.append(
            {
                "component": source["component"],
                "version": source["version"],
                "path": str(target),
                "bytes": target.stat().st_size,
                "sha256": actual_hash,
                "official_url": source["official_url"],
                "download_url": source["download_url"],
            }
        )
    return receipts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--cache-directory", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    receipts = prepare(args.config.resolve(), args.cache_directory.resolve())
    print(json.dumps({"status": "PASSED", "sources": receipts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
