#!/usr/bin/env python3
"""Standalone bootstrap installer for the latest published approved NLI package.

This file intentionally uses only Python stdlib and dpkg. It does not create or
modify object configuration and never restarts Wiren Board services itself.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.request
from urllib.parse import urlparse

REPO = "psv76/Neirolinks"
API = "https://api.github.com/repos/" + REPO
MAX_METADATA = 2 * 1024 * 1024
MAX_PACKAGE = 32 * 1024 * 1024


class InstallError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise InstallError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def version(value):
    require(isinstance(value, str) and re.fullmatch(
        r"\d+\.\d+(?:\.\d+)?(?:[-+][A-Za-z0-9_.-]+)?", value), "Invalid release version")
    numbers = re.match(r"\d+\.\d+(?:\.\d+)?", value)[0].split(".")
    return tuple(map(int, numbers)) + (0,) * (3 - len(numbers))


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        require(parsed.scheme == "https" and parsed.hostname == "release-assets.githubusercontent.com",
                "Untrusted GitHub release redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, limit=MAX_METADATA, binary=False):
    require(url.startswith(API + "/"), "Release source must be " + REPO)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "neiro-nli-bootstrap/1",
            "Accept": "application/octet-stream" if binary else "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.build_opener(Redirect).open(request, timeout=30) as response:
            data = response.read(limit + 1)
            require(len(data) <= limit, "Oversize release data")
            size = response.headers.get("Content-Length")
            require(size is None or int(size) == len(data), "Truncated release data")
            return data
    except InstallError:
        raise
    except (OSError, ValueError) as exc:
        raise InstallError("Не удалось получить approved release: " + str(exc)) from exc


def run(argv, capture=False):
    if capture:
        return subprocess.check_output(argv, text=True).strip()
    subprocess.run(argv, check=True)
    return ""


class Bootstrap:
    def __init__(self, transport=fetch, runner=run, euid=os.geteuid):
        self.fetch = transport
        self.run = runner
        self.euid = euid

    def asset(self, item, limit):
        ident = item.get("id")
        expected = item.get("digest", "")
        require(isinstance(ident, int) and ident > 0, "Invalid release asset ID")
        require(isinstance(expected, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", expected),
                "GitHub release asset must expose SHA256 digest")
        data = self.fetch(API + "/releases/assets/" + str(ident), limit, True)
        require(digest(data) == expected[7:], "Release asset checksum mismatch")
        return data

    def catalogs(self):
        out = []
        for page in range(1, 11):
            raw = self.fetch(API + "/releases?per_page=100&page=" + str(page))
            try:
                releases = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise InstallError("Invalid GitHub releases response") from exc
            require(isinstance(releases, list), "Invalid GitHub releases response")
            for release in releases:
                require(isinstance(release, dict), "Invalid GitHub release")
                if (release.get("draft") is not False or release.get("prerelease") is not False
                        or not release.get("published_at")
                        or not release.get("tag_name", "").startswith("nli-approved-")):
                    continue
                assets = release.get("assets")
                require(isinstance(assets, list) and all(isinstance(a, dict) for a in assets),
                        "Invalid release assets")
                catalogs = [a for a in assets if a.get("name") == "nli-catalog.json"]
                require(len(catalogs) == 1, "Approved release requires one nli-catalog.json")
                data = self.asset(catalogs[0], MAX_METADATA)
                try:
                    catalog = json.loads(data)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise InstallError("Invalid approved catalog") from exc
                require(isinstance(catalog, dict)
                        and catalog.get("schema") == 1
                        and catalog.get("repository") == REPO
                        and catalog.get("approved") is True,
                        "Invalid approved catalog")
                out.append((catalog, release))
                require(len(out) <= 32, "Approved catalog count bound exceeded")
            if len(releases) < 100:
                return out
        raise InstallError("Release catalog pagination bound exceeded")

    def package(self):
        candidates = []
        for catalog, release in self.catalogs():
            package = catalog.get("nli")
            if package is None:
                continue
            require(isinstance(package, dict) and package.get("approved") is True,
                    "Unapproved NLI package")
            rank = version(package.get("version"))
            sha = package.get("sha256")
            require(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha),
                    "Invalid package SHA256")
            assets = [a for a in release["assets"]
                      if a.get("name") == "neiro-nli_" + package["version"] + "_all.deb"]
            require(len(assets) == 1 and assets[0].get("digest") == "sha256:" + sha,
                    "Missing/mismatched NLI release package")
            candidates.append((rank, package, assets[0]))
        require(candidates, "Нет опубликованного approved NLI release")
        candidates.sort(key=lambda item: item[0], reverse=True)
        rank, package, asset = candidates[0]
        require(all(p == package for r, p, a in candidates if r == rank),
                "Conflicting approved NLI packages")
        return dict(package, asset=asset)

    def check(self):
        package = self.package()
        return {"version": package["version"], "sha256": package["sha256"]}

    def install(self):
        require(self.euid() == 0, "Запустите установщик от root")
        package = self.package()
        data = self.asset(package["asset"], MAX_PACKAGE)
        require(digest(data) == package["sha256"], "Package checksum mismatch")
        fd, path = tempfile.mkstemp(prefix="neiro-nli-", suffix=".deb", dir="/tmp")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            metadata = [
                self.run(["/usr/bin/dpkg-deb", "-f", path, field], True)
                for field in ("Package", "Version", "Architecture")
            ]
            require(metadata == ["neiro-nli", package["version"], "all"],
                    "Downloaded .deb identity mismatch")
            self.run(["/usr/bin/dpkg", "--install", path])
            reported = self.run(["/usr/bin/nli", "--json", "--version"], True)
            try:
                actual = json.loads(reported).get("version")
            except (AttributeError, json.JSONDecodeError) as exc:
                raise InstallError("Installed NLI version check failed") from exc
            require(actual == package["version"],
                    "Installed NLI version mismatch: " + str(actual))
            return {"version": actual, "sha256": package["sha256"]}
        finally:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass


def main(argv=None, bootstrap=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="only show the latest approved NLI package; do not install")
    args = parser.parse_args(argv)
    bootstrap = bootstrap or Bootstrap()
    try:
        result = bootstrap.check() if args.check else bootstrap.install()
    except (InstallError, subprocess.CalledProcessError) as exc:
        print("Ошибка:", exc)
        return 1
    if args.check:
        print("Последний approved NLI:", result["version"])
        print("SHA256:", result["sha256"])
    else:
        print("NLI установлен:", result["version"])
        print("SHA256:", result["sha256"])
        print("Далее: nli status")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
