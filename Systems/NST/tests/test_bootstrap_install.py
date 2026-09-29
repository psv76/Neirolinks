import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("nli_bootstrap", ROOT / "install.py")
bootstrap_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap_mod)


class FakeTransport:
    def __init__(self, releases, assets):
        self.releases = releases
        self.assets = assets
        self.calls = []

    def __call__(self, url, limit=bootstrap_mod.MAX_METADATA, binary=False):
        self.calls.append((url, limit, binary))
        if "/releases?per_page=100&page=1" in url:
            return json.dumps(self.releases).encode()
        if "/releases?per_page=100&page=2" in url:
            return b"[]"
        ident = int(url.rsplit("/", 1)[1])
        return self.assets[ident]


def release(version, catalog_id, deb_id, catalog, deb, draft=False, prerelease=False):
    c = json.dumps(catalog, separators=(",", ":")).encode()
    return {
        "draft": draft,
        "prerelease": prerelease,
        "published_at": "2026-09-25T00:00:00Z",
        "tag_name": "nli-approved-" + version,
        "assets": [
            {"id": catalog_id, "name": "nli-catalog.json",
             "digest": "sha256:" + hashlib.sha256(c).hexdigest()},
            {"id": deb_id, "name": "neiro-nli_" + version + "_all.deb",
             "digest": "sha256:" + hashlib.sha256(deb).hexdigest()},
        ],
    }, c


class BootstrapTests(unittest.TestCase):
    def fixture(self, version="0.1.9"):
        deb = b"approved deb bytes " + version.encode()
        catalog = {
            "schema": 1,
            "repository": bootstrap_mod.REPO,
            "approved": True,
            "components": [],
            "nli": {"version": version, "approved": True,
                    "sha256": hashlib.sha256(deb).hexdigest()},
        }
        rel, cat = release(version, 10, 11, catalog, deb)
        return deb, catalog, rel, cat

    def test_check_selects_latest_published_non_draft(self):
        old_deb, old_catalog, old_rel, old_cat = self.fixture("0.1.8")
        deb, catalog, rel, cat = self.fixture("0.1.9")
        draft_deb = b"draft"
        draft_catalog = {
            "schema": 1, "repository": bootstrap_mod.REPO, "approved": True,
            "components": [],
            "nli": {"version": "9.9.9", "approved": True,
                    "sha256": hashlib.sha256(draft_deb).hexdigest()},
        }
        draft_rel, draft_cat = release("9.9.9", 20, 21, draft_catalog, draft_deb, draft=True)
        transport = FakeTransport(
            [old_rel, draft_rel, rel],
            {10: old_cat, 11: old_deb, 20: draft_cat, 21: draft_deb,
             # the second stable release reuses IDs in the helper; rewrite here
             30: cat, 31: deb},
        )
        rel["assets"][0]["id"] = 30
        rel["assets"][1]["id"] = 31
        result = bootstrap_mod.Bootstrap(transport=transport).check()
        self.assertEqual(result["version"], "0.1.9")
        self.assertEqual(result["sha256"], hashlib.sha256(deb).hexdigest())

    def test_catalog_asset_checksum_mismatch_fails(self):
        deb, catalog, rel, cat = self.fixture()
        transport = FakeTransport([rel], {10: cat + b"x", 11: deb})
        with self.assertRaisesRegex(bootstrap_mod.InstallError, "checksum"):
            bootstrap_mod.Bootstrap(transport=transport).check()

    def test_install_verifies_deb_identity_installs_and_checks_cli(self):
        deb, catalog, rel, cat = self.fixture()
        transport = FakeTransport([rel], {10: cat, 11: deb})
        calls = []

        def runner(argv, capture=False):
            calls.append(list(argv))
            if argv[:2] == ["/usr/bin/dpkg-deb", "-f"]:
                self.assertEqual(Path(argv[2]).read_bytes(), deb)
                return {"Package": "neiro-nli", "Version": "0.1.9", "Architecture": "all"}[argv[3]]
            if argv[:2] == ["/usr/bin/dpkg", "--install"]:
                self.assertEqual(Path(argv[2]).read_bytes(), deb)
                return ""
            if argv[:2] == ["/usr/bin/nli", "--json"]:
                return '{"version":"0.1.9"}'
            raise AssertionError(argv)

        result = bootstrap_mod.Bootstrap(
            transport=transport, runner=runner, euid=lambda: 0
        ).install()
        self.assertEqual(result["version"], "0.1.9")
        self.assertTrue(any(c[:2] == ["/usr/bin/dpkg", "--install"] for c in calls))

    def test_non_root_fails_before_network(self):
        def no_network(*args, **kwargs):
            raise AssertionError("network must not be used")
        with self.assertRaisesRegex(bootstrap_mod.InstallError, "root"):
            bootstrap_mod.Bootstrap(transport=no_network, euid=lambda: 1000).install()


if __name__ == "__main__":
    unittest.main()
