#!/usr/bin/env python3
"""Bootstrap only the highest published *approved* NEIROLINKS Tools kit.

This script never builds software from mutable main and never trusts a ZIP file
until the GitHub Releases API SHA256, published catalog and embedded checksums
have all been checked. No controller changes occur until preflight succeeds.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

API = "https://api.github.com/repos/psv76/Neirolinks"
TAG = re.compile(r"^neirolinks-tools-approved-package-(\d+)\.(\d+)(?:\.(\d+))?$")
SHA = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
MAX_JSON = 2 * 1024 * 1024
MAX_ZIP = 24 * 1024 * 1024
MAX_FILE = 36 * 1024 * 1024


class InstallError(Exception):
    pass


def sha256(blob):
    return hashlib.sha256(blob).hexdigest()


def fetch_https(url, limit):
    url_parts = urlparse(url)
    if url_parts.scheme != "https" or not url_parts.hostname:
        raise InstallError("Only HTTPS sources are permitted")
    request = Request(url, headers={
        "User-Agent": "NEIROLINKS-Tools-approved-bootstrap/1.0",
        "Accept": "application/vnd.github+json" if url_parts.hostname == "api.github.com"
        else "application/octet-stream",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    class HttpsOnlyRedirects(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if urlparse(newurl).scheme != "https":
                raise InstallError("Refusing non-HTTPS redirect")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    try:
        with build_opener(HttpsOnlyRedirects()).open(request, timeout=45) as response:
            if urlparse(response.geturl()).scheme != "https":
                raise InstallError("Insecure redirect")
            content = bytearray()
            while chunk := response.read(131072):
                content.extend(chunk)
                if len(content) > limit:
                    raise InstallError("Download exceeds size limit")
            return bytes(content)
    except (OSError, ValueError) as exc:
        raise InstallError("HTTPS download failed: " + str(exc)) from exc


def read_json(blob, label):
    try:
        data = json.loads(blob.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise InstallError(label + " is not valid JSON") from exc
    if not isinstance(data, dict):
        raise InstallError(label + " must be an object")
    return data


def selected_release(pages):
    candidates = []
    for releases in pages:
        if not isinstance(releases, list):
            raise InstallError("GitHub releases index must be a list")
        for release in releases:
            if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
                continue
            match = TAG.fullmatch(str(release.get("tag_name", "")))
            if match:
                version = tuple(int(k or 0) for k in match.groups())
                candidates.append((version, release))
    if not candidates:
        raise InstallError("No published approved NEIROLINKS Tools release found")
    return max(candidates, key=lambda item: item[0])[1]


def discover(fetch=fetch_https):
    pages = []
    for page in range(1, 4):
        blob = fetch(API + "/releases?per_page=100&page=" + str(page), MAX_JSON)
        try:
            listing = json.loads(blob)
        except (UnicodeError, ValueError) as exc:
            raise InstallError("GitHub releases response invalid") from exc
        if not isinstance(listing, list):
            raise InstallError("GitHub releases response invalid")
        pages.append(listing)
        if len(listing) < 100:
            break
    return selected_release(pages)


def release_assets(release):
    tag = str(release.get("tag_name", ""))
    match = TAG.fullmatch(tag)
    if not match or release.get("draft") or release.get("prerelease"):
        raise InstallError("Not an approved published release")
    version = ".".join(match.group(1, 2)) + (("." + match.group(3)) if match.group(3) else "")
    expected = ("neirolinks-nst-onboarding-kit_" + version + ".zip", "neirolinks-tools-catalog.json")
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise InstallError("Release assets missing")
    entries = {}
    for entry in assets:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if name in expected:
            if name in entries:
                raise InstallError("Duplicate release asset " + name)
            checksum = str(entry.get("digest", ""))
            if not checksum.startswith("sha256:") or not SHA.fullmatch(checksum[7:]):
                raise InstallError("Release asset SHA256 unavailable for " + str(name))
            link = str(entry.get("browser_download_url", ""))
            expected_prefix = ("https://github.com/psv76/Neirolinks/releases/download/" + tag + "/")
            if link != expected_prefix + name:
                raise InstallError("Unexpected GitHub release asset URL")
            entries[name] = (link, checksum[7:])
    if set(entries) != set(expected):
        raise InstallError("Incomplete approved release: ZIP/catalog absent")
    return version, entries


def read_approved_release(release, fetch=fetch_https):
    version, assets = release_assets(release)
    catalog_url, catalog_sha = assets["neirolinks-tools-catalog.json"]
    catalog_blob = fetch(catalog_url, MAX_JSON)
    if sha256(catalog_blob) != catalog_sha:
        raise InstallError("Approved catalog SHA256 mismatch")
    catalog = read_json(catalog_blob, "Release catalog")
    if (catalog.get("approved") is not True or catalog.get("component") != "neirolinks-tools"
            or str(catalog.get("version")) != version
            or not COMMIT.fullmatch(str(catalog.get("commit", "")))):
        raise InstallError("Approved catalog metadata mismatch")
    descriptors = catalog.get("assets")
    if not isinstance(descriptors, dict):
        raise InstallError("Approved catalog asset manifest missing")
    kit_name = "neirolinks-nst-onboarding-kit_" + version + ".zip"
    if descriptors.get(kit_name) != assets[kit_name][1]:
        raise InstallError("GitHub asset and approved catalog disagree")
    nested = {key[7:]: value for key, value in descriptors.items()
              if key.startswith("nested:") and SHA.fullmatch(str(value))}
    if len(nested) != 1 or not re.fullmatch(r"nst_\d+\.\d+_all\.deb", next(iter(nested))):
        raise InstallError("Catalog missing pinned NST package digest")
    return version, assets[kit_name], nested, catalog


def safe_kit(zip_blob, version, nested):
    """Validate archive names and all package checksums before any local write."""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_blob)) as archive:
            names = archive.namelist()
            expected = {next(iter(nested)), "neirolinks-tools_" + version + "_all.deb",
                        "SHA256SUMS", "install.sh", "README.md"}
            if len(names) != len(expected) or set(names) != expected:
                raise InstallError("Kit contains unexpected or missing files")
            files = {}
            for info in archive.infolist():
                if (info.is_dir() or info.file_size > MAX_FILE
                        or (info.external_attr >> 16) & 0o170000 == 0o120000):
                    raise InstallError("Unsafe kit archive member")
                files[info.filename] = archive.read(info)
    except (ValueError, OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise InstallError("Kit ZIP invalid") from exc
    pinned_nst = next(iter(nested))
    if sha256(files[pinned_nst]) != nested[pinned_nst]:
        raise InstallError("NST package differs from approved hash")
    checksum_lines = files["SHA256SUMS"].decode("ascii").splitlines()
    if len(checksum_lines) != 2:
        raise InstallError("Kit SHA256SUMS must list exactly two packages")
    expected = {line.split("  ", 1)[1]: line[:64]
                for line in checksum_lines if re.fullmatch(r"[0-9a-f]{64}  [a-zA-Z0-9._-]+\.deb", line)}
    if set(expected) != {pinned_nst, "neirolinks-tools_" + version + "_all.deb"}:
        raise InstallError("Kit SHA256SUMS malformed")
    if expected[pinned_nst] != nested[pinned_nst]:
        raise InstallError("Nested NST SHA256 differs from catalog")
    for filename, digest in expected.items():
        if sha256(files[filename]) != digest:
            raise InstallError("Kit Debian package SHA256 mismatch: " + filename)
    return files


def preflight():
    if os.name != "posix" or os.geteuid() != 0:
        raise InstallError("Run as root in Wiren Board Linux terminal")
    for path in ("/etc/systemd/system/neirolinks-tools.service",
                 "/etc/wb-homeui/custom-menu/neirolinks.json",
                 "/etc/nginx/includes/default.wb.d/neirolinks-tools.conf"):
        if os.path.lexists(path):
            raise InstallError("Existing NEIROLINKS Tools pilot found. Refusing overwrite: " + path)
    for binary in ("/usr/bin/python3", "/usr/bin/wb-homeui-gates", "/usr/bin/wb-homeui-users"):
        if not Path(binary).is_file():
            raise InstallError("Missing prerequisite: " + binary)
    result = subprocess.run(["/usr/bin/wb-homeui-users", "list"],
                            capture_output=True, text=True, timeout=10, check=False)
    if result.returncode or not any(line.strip().endswith("(admin)") for line in result.stdout.splitlines()):
        raise InstallError("Create a WebUI administrator first: Settings > Users")
    versions = subprocess.run(["/usr/bin/dpkg-query", "-W", "-f=${Version}", "nst"],
                              capture_output=True, text=True, timeout=10, check=False)
    return versions.stdout.strip() if versions.returncode == 0 else None


def install(files, current_version):
    nst_name = next(name for name in files if re.fullmatch(r"nst_\d+\.\d+_all\.deb", name))
    nst_version = nst_name.split("_")[1]
    if current_version:
        result = subprocess.run(["/usr/bin/dpkg", "--compare-versions",
                                 current_version, "gt", nst_version], check=False)
        if result.returncode == 0:
            raise InstallError("Already installed NST is newer than the approved kit")
    with tempfile.TemporaryDirectory(prefix="neirolinks-onboarding-") as directory:
        root = Path(directory)
        for name, blob in files.items():
            file = root / name
            file.write_bytes(blob)
            file.chmod(0o700 if name == "install.sh" else 0o600)
        print("SHA256 verified. Installing NST and NEIROLINKS Tools...", flush=True)
        subprocess.run(["/bin/sh", str(root / "install.sh")], cwd=root, check=True,
                       timeout=900)


def run(args, fetch=fetch_https):
    current = preflight() if not args.check else None
    print("Finding the latest approved NEIROLINKS Tools release...", flush=True)
    release = discover(fetch)
    version, (url, digest), nested, catalog = read_approved_release(release, fetch)
    print("Approved:", release["tag_name"], "source:", catalog["commit"][:12], flush=True)
    bundle = fetch(url, MAX_ZIP)
    if sha256(bundle) != digest:
        raise InstallError("Downloaded kit ZIP SHA256 mismatch")
    files = safe_kit(bundle, version, nested)
    print("Approved kit SHA256:", digest, flush=True)
    if args.check:
        print("Check successful. Packages:", ", ".join(sorted(k for k in files if k.endswith(".deb"))))
        return
    install(files, current)
    print("Installation successful. Refresh WB WebUI: NEIROLINKS > Service.", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install latest approved NEIROLINKS Tools + NST")
    parser.add_argument("--check", action="store_true", help="Download and verify without installation")
    options = parser.parse_args(argv)
    try:
        run(options)
    except (InstallError, subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        print("NEIROLINKS install failed:", str(exc), file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
