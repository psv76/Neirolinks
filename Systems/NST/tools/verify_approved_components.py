#!/usr/bin/env python3
"""Verify committed approved-component snapshot against published stable GitHub Releases."""
import argparse
from pathlib import Path
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nli.releases import API, Releases, fetch
from nli.util import decode, require


def verify_snapshot(path):
    snapshot = decode(Path(path).read_bytes())
    require(snapshot.get("schema") == 1 and type(snapshot.get("components")) is list,
            "Invalid approved component snapshot")
    releases = Releases()
    checked = {}
    for entry in snapshot["components"]:
        approval = entry["approval"]
        tag = approval["tag"]
        if tag not in checked:
            release = decode(fetch(API + "/releases/tags/" + quote(tag, safe="")))
            require(release.get("draft") is False and release.get("prerelease") is False
                    and release.get("published_at"), "Approval tag is not a published stable release: " + tag)
            require(release["published_at"] == approval["published_at"], "Approval publication timestamp mismatch: " + tag)
            assets = [a for a in release.get("assets", []) if a.get("name") == "nli-catalog.json"]
            require(len(assets) == 1, "Approved release requires one nli-catalog.json: " + tag)
            require(assets[0].get("digest") == "sha256:" + approval["catalog_sha256"],
                    "Approved catalog digest mismatch: " + tag)
            catalog = decode(releases.asset(assets[0], 2 * 1024 * 1024))
            ref = decode(fetch(API + "/git/ref/tags/" + quote(tag, safe="")))
            require(ref.get("object", {}).get("type") == "commit"
                    and ref["object"]["sha"] == approval["release_commit"],
                    "Approved tag commit mismatch: " + tag)
            checked[tag] = catalog
        catalog = checked[tag]
        require(catalog.get("approved") is True and catalog.get("repository") == snapshot["repository"],
                "Invalid approved catalog: " + tag)
        matches = [
            item for item in catalog.get("components", [])
            if (item.get("component"), item.get("object"), item.get("role"), item.get("version")) ==
               (entry["component"], entry["object"], entry["role"], entry["version"])
        ]
        require(len(matches) == 1, "Approved catalog does not contain exact component: " + entry["component"])
        require(matches[0].get("approved") is True, "Catalog component is not approved")
        require(matches[0].get("manifest") == entry["manifest"], "Catalog manifest reference mismatch")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", nargs="?", default=str(ROOT / "deployment/approved-components.json"))
    args = parser.parse_args(argv)
    verify_snapshot(args.snapshot)
    print("approved component snapshot: OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
