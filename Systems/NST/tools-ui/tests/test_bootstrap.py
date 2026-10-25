"""One-command NST Tools bootstrap: approved-only and tamper rejection."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest import mock
import zipfile

TOOLS = Path(__file__).resolve().parents[1] / "tools"
spec = importlib.util.spec_from_file_location("nst_one_command_bootstrap", TOOLS/"bootstrap_latest.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def kit_fixture():
    nst=b"NST_DEBIAN_TEST"
    tools=b"TOOLS_DEBIAN_TEST"
    checksums=(mod.sha256(nst)+"  nst_2.5_all.deb\n"+
               mod.sha256(tools)+"  neirolinks-tools_1.0_all.deb\n").encode()
    content={"nst_2.5_all.deb":nst,"neirolinks-tools_1.0_all.deb":tools,
             "SHA256SUMS":checksums,"install.sh":b"#!/bin/sh\nexit 0\n",
             "README.md":b"test"}
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z:
        for key, value in content.items():
            z.writestr(key,value)
    blob=buf.getvalue()
    tag="neirolinks-tools-approved-package-1.0"
    url="https://github.com/psv76/Neirolinks/releases/download/"+tag+"/"
    catalog={"approved":True,"component":"neirolinks-tools","version":"1.0",
             "commit":"a"*40,
             "assets":{"neirolinks-nst-onboarding-kit_1.0.zip":mod.sha256(blob),
                       "nested:nst_2.5_all.deb":mod.sha256(nst)}}
    cat=json.dumps(catalog).encode()
    release={"tag_name":tag,"draft":False,"prerelease":False,
             "assets":[{"name":"neirolinks-nst-onboarding-kit_1.0.zip",
                        "digest":"sha256:"+mod.sha256(blob),
                        "browser_download_url":url+"neirolinks-nst-onboarding-kit_1.0.zip"},
                       {"name":"neirolinks-tools-catalog.json",
                        "digest":"sha256:"+mod.sha256(cat),
                        "browser_download_url":url+"neirolinks-tools-catalog.json"}]}
    def fetch(url, _max):
        if url.endswith("catalog.json"):return cat
        if url.endswith(".zip"):return blob
        raise AssertionError(url)
    return release, fetch, blob, catalog, content


class BootstrapTests(unittest.TestCase):
    def test_approved_highest_version_and_no_drafts(self):
        tag="neirolinks-tools-approved-package-"
        def release(v,draft=False,prerelease=False):
            return {"tag_name":tag+v,"draft":draft,"prerelease":prerelease}
        picked=mod.selected_release([[release("1.0"),release("1.5")],
                                      [release("2.0",draft=True),release("1.10"),
                                       release("3.0",prerelease=True)]])
        self.assertEqual(picked["tag_name"],tag+"1.10")

    def test_catalog_and_zip_validated(self):
        release, fetch, blob, catalog, original=kit_fixture()
        v, (url,digest), pinned, accepted=mod.read_approved_release(release, fetch)
        self.assertEqual(v,"1.0")
        self.assertEqual(digest,mod.sha256(blob))
        self.assertEqual(pinned,{"nst_2.5_all.deb":mod.sha256(original["nst_2.5_all.deb"])})
        self.assertEqual(mod.safe_kit(blob,v,pinned),original)

    def test_catalog_modification_rejected(self):
        release, fetch, blob, catalog, _=kit_fixture()
        with self.assertRaisesRegex(mod.InstallError,"catalog SHA256"):
            mod.read_approved_release(release,lambda url,limit: b"tampered" if url.endswith(".json") else fetch(url,limit))

    def test_unapproved_and_fake_asset_host_rejected(self):
        release, fetch, *_=kit_fixture()
        release["prerelease"]=True
        with self.assertRaises(mod.InstallError):mod.read_approved_release(release,fetch)
        release["prerelease"]=False
        release["assets"][0]["browser_download_url"]="https://example.org/malware.zip"
        with self.assertRaises(mod.InstallError):mod.read_approved_release(release,fetch)

    def test_corrupted_kit_detected(self):
        release, fetch, blob, catalog, content=kit_fixture()
        bad=dict(content)
        bad["nst_2.5_all.deb"]=b"tampered"
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,"w") as z:
            for name,value in bad.items():z.writestr(name,value)
        with self.assertRaisesRegex(mod.InstallError,"NST package"):
            mod.safe_kit(buf.getvalue(),"1.0",{"nst_2.5_all.deb":mod.sha256(content["nst_2.5_all.deb"])})

    def test_zip_traversal_and_unexpected_files_rejected(self):
        _, _, _, _, content=kit_fixture()
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,"w") as z:
            for name,value in content.items():z.writestr(name,value)
            z.writestr("../outside",b"bad")
        with self.assertRaises(mod.InstallError):
            mod.safe_kit(buf.getvalue(),"1.0",{"nst_2.5_all.deb":mod.sha256(content["nst_2.5_all.deb"])})

    def test_check_never_installs(self):
        release,fetch,blob,catalog,content=kit_fixture()
        def http(url,size):
            if "/releases?" in url:return json.dumps([release]).encode()
            return fetch(url,size)
        with mock.patch.object(mod,"install") as install, mock.patch.object(mod,"preflight") as preflight:
            mod.run(SimpleNamespace(check=True),fetch=http)
        install.assert_not_called()
        preflight.assert_not_called()

    def test_failure_never_runs_installer(self):
        release,fetch,blob,catalog,_=kit_fixture()
        def http(url,size):
            if "/releases?" in url:return json.dumps([release]).encode()
            if url.endswith(".zip"):return b"not approved"
            return fetch(url,size)
        with mock.patch.object(mod,"install") as install, mock.patch.object(mod,"preflight",return_value=None):
            with self.assertRaises(mod.InstallError):
                mod.run(SimpleNamespace(check=False),fetch=http)
        install.assert_not_called()


if __name__=="__main__":
    unittest.main()
