"""Generate and validate license/native inventory for the actual frozen distribution."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import re
import shutil
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "packaging" / "dependency_license_inventory.json"
SOURCE_CONFIG_PATH = ROOT / "packaging" / "compliance_sources.json"
SOURCE_CACHE = ROOT / ".cache" / "compliance-sources"

REQUIRED_ASSETS = (
    "_internal/nl_project_2/persistence/migrations/env.py",
    "_internal/nl_project_2/persistence/migrations/script.py.mako",
    "_internal/nl_project_2/persistence/migrations/versions/000000000006_conduit_dwg_contract.py",
    "_internal/resources/catalogs/catalog_manifest.json",
    "_internal/resources/catalogs/equipment_passports.json",
    "_internal/resources/catalogs/products.json",
    "_internal/resources/autocad/block_contract.json",
    "_internal/resources/autocad/block_contract.schema.json",
    "_internal/PySide6/plugins/platforms/qoffscreen.dll",
    "_internal/PySide6/plugins/platforms/qwindows.dll",
)
FORBIDDEN_PAYLOAD_MARKERS = ("webengine", "chromium", "icudtl", "opengl32sw", "/qml/")
ALLOWED_QT_DLLS = {"qt6core.dll", "qt6gui.dll", "qt6network.dll", "qt6widgets.dll"}
RUNTIME_LICENSE_PACKAGES = (
    "alembic",
    "greenlet",
    "mako",
    "markupsafe",
    "packaging",
    "pygments",
    "pyinstaller",
    "pyinstaller-hooks-contrib",
    "pywin32",
    "setuptools",
    "sqlalchemy",
    "typing-extensions",
)
MODULE_COMPONENTS = {
    "alembic": "Alembic 1.18.5",
    "greenlet": "greenlet 3.5.4",
    "mako": "Mako 1.4.1",
    "markupsafe": "MarkupSafe 3.0.3",
    "packaging": "packaging 26.3",
    "pygments": "Pygments 2.20.0",
    "setuptools": "setuptools 83.0.0",
    "sqlalchemy": "SQLAlchemy 2.0.51",
    "typing_extensions": "typing_extensions 4.16.0",
    "PySide6": "PySide6 Essentials 6.11.1",
    "shiboken6": "Shiboken6 6.11.1",
    "win32com": "pywin32 312",
    "pythoncom": "pywin32 312",
    "pywintypes": "pywin32 312",
}
CUSTOM_LICENSE_REVIEWS = {
    "LicenseRef-ICC-License": {
        "classification": "ALLOWED",
        "evidence_file": "LicenseRef-ICC-License.txt",
        "basis": "Permits unrestricted copying, distribution, embedding, use and sale; "
        "an allowed permissive analogue under the closed gate policy.",
    },
    "LicenseRef-BSD-3-Clause-with-PCRE2-Binary-Like-Packages-Exception": {
        "classification": "ALLOWED",
        "evidence_file": "LicenseRef-BSD-3-Clause-with-PCRE2-Binary-Like-Packages-Exception.txt",
        "basis": "BSD-3-Clause terms with an additional downstream binary-package exception; "
        "an allowed permissive analogue under the closed gate policy.",
    },
    "LicenseRef-SHA1-Public-Domain": {
        "classification": "ALLOWED",
        "evidence_file": "LicenseRef-SHA1-Public-Domain.txt",
        "basis": "Explicit public-domain dedication; allowed under the closed gate policy.",
    },
    "LicenseRef-Lcs-Telegraphics": {
        "classification": "ALLOWED",
        "evidence_file": "LicenseRef-Lcs-Telegraphics.txt",
        "basis": "Permits free use, copying and distribution without compensation or restrictions; "
        "an allowed permissive analogue under the closed gate policy.",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def safe_directory_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def locked_packages(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", line)
        if match:
            result[canonical_name(match.group(1))] = match.group(2)
    return result


def validate_policy(policy: dict) -> None:
    locked = locked_packages(ROOT / "requirements.lock")
    declared = {canonical_name(row["name"]): row["version"] for row in policy["packages"]}
    if declared != locked:
        missing = sorted(set(locked) - set(declared))
        extra = sorted(set(declared) - set(locked))
        mismatched = sorted(
            name for name in locked.keys() & declared.keys() if locked[name] != declared[name]
        )
        raise RuntimeError(
            f"Dependency policy does not match requirements.lock: "
            f"missing={missing}, extra={extra}, mismatched={mismatched}"
        )
    invalid = [
        row["name"]
        for row in policy["packages"]
        if row["classification"] not in {"ALLOWED", "CONDITIONAL"}
    ]
    if invalid:
        raise RuntimeError(f"Blocked or unknown dependency classifications: {invalid}")


def analysis_modules(analysis_toc: Path) -> set[str]:
    values = ast.literal_eval(analysis_toc.read_text(encoding="utf-8"))
    modules = {row[0] for row in values[13] + values[14] + values[19]}
    return modules


def actual_python_components(modules: set[str]) -> list[str]:
    components = set()
    for module in modules:
        for prefix, component in MODULE_COMPONENTS.items():
            if module == prefix or module.startswith(prefix + "."):
                components.add(component)
    components.add("CPython 3.13.14 standard library")
    components.add("PyInstaller 6.21.0 bootloader/runtime hooks")
    components.add("pyinstaller-hooks-contrib 2026.6 runtime hooks")
    return sorted(components)


def native_component(relative: str) -> tuple[str, str, str]:
    normalized = relative.replace("\\", "/")
    lowered = normalized.lower()
    filename = Path(lowered).name
    if lowered == "nlproject3.exe":
        return (
            "NL Project wrapper / PyInstaller bootloader 6.21.0",
            "Proprietary application; GPL-2.0-or-later WITH Bootloader-exception",
            "ALLOWED",
        )
    if lowered.startswith("_internal/pyside6/plugins/") or (
        lowered.startswith("_internal/pyside6/qt6") and filename.endswith(".dll")
    ):
        return ("Qt Base 6.11.1", "LGPL-3.0-only", "CONDITIONAL")
    if lowered.startswith("_internal/pyside6/"):
        return ("PySide6 Essentials 6.11.1", "LGPL-3.0-only", "CONDITIONAL")
    if lowered.startswith("_internal/shiboken6/"):
        return ("Shiboken6 6.11.1", "LGPL-3.0-only", "CONDITIONAL")
    if any(marker in lowered for marker in ("/pywin32_system32/", "/win32/", "/pythonwin/")):
        return ("pywin32 312", "PSF-2.0 and component permissive licenses", "ALLOWED")
    if lowered.startswith("_internal/greenlet/"):
        return ("greenlet 3.5.4", "MIT AND PSF-2.0", "ALLOWED")
    if lowered.startswith("_internal/markupsafe/"):
        return ("MarkupSafe 3.0.3", "BSD-3-Clause", "ALLOWED")
    if lowered.startswith("_internal/sqlalchemy/"):
        return ("SQLAlchemy 2.0.51", "MIT", "ALLOWED")
    if filename == "sqlite3.dll":
        return ("SQLite 3.50.4", "Public Domain", "ALLOWED")
    if filename in {"libcrypto-3.dll", "libssl-3.dll"}:
        return ("OpenSSL 3.0.21", "Apache-2.0", "ALLOWED")
    if filename == "libffi-8.dll":
        return ("libffi", "MIT", "ALLOWED")
    if lowered.startswith("_internal/") and (
        filename.startswith(("api-ms-win-", "python", "vcruntime", "ucrtbase"))
        or filename.endswith(".pyd")
    ):
        return (
            "CPython 3.13.14 Windows binary",
            "PSF-2.0 family and bundled third-party/additional Windows terms",
            "ALLOWED",
        )
    return ("UNKNOWN", "UNKNOWN", "UNKNOWN")


def scan_native(dist: Path) -> list[dict]:
    rows = []
    for path in sorted(dist.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".dll", ".exe", ".pyd"}:
            continue
        relative = path.relative_to(dist).as_posix()
        component, license_name, classification = native_component(relative)
        rows.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "component": component,
                "license": license_name,
                "classification": classification,
            }
        )
    unknown = [row["path"] for row in rows if row["classification"] == "UNKNOWN"]
    if unknown:
        raise RuntimeError(f"Unknown native payload: {unknown}")
    return rows


def validate_payload_shape(dist: Path) -> None:
    file_names = {path.relative_to(dist).as_posix() for path in dist.rglob("*") if path.is_file()}
    missing = sorted(set(REQUIRED_ASSETS) - file_names)
    if missing:
        raise RuntimeError(f"Missing packaged runtime assets: {missing}")
    forbidden = sorted(
        path
        for path in file_names
        if any(marker in f"/{path.lower()}" for marker in FORBIDDEN_PAYLOAD_MARKERS)
    )
    if forbidden:
        raise RuntimeError(f"Forbidden unused heavy payload: {forbidden[:20]}")
    qt_dlls = {
        Path(path).name.lower()
        for path in file_names
        if path.lower().startswith("_internal/pyside6/qt6") and path.lower().endswith(".dll")
    }
    if not qt_dlls or not qt_dlls <= ALLOWED_QT_DLLS:
        raise RuntimeError(f"Unexpected Qt DLL set: {sorted(qt_dlls)}")
    redistributed_msvc = [
        path
        for path in file_names
        if path.lower().startswith(("_internal/pyside6/", "_internal/shiboken6/"))
        and Path(path).name.lower().startswith(("msvcp", "vcruntime"))
    ]
    if redistributed_msvc:
        raise RuntimeError(f"Unexpected Qt-bundled Microsoft runtime: {redistributed_msvc}")


def copy_distribution_licenses(target: Path) -> list[str]:
    copied = []
    for package_name in RUNTIME_LICENSE_PACKAGES:
        distribution = importlib.metadata.distribution(package_name)
        package_target = target / f"{canonical_name(package_name)}-{distribution.version}"
        for entry in distribution.files or ():
            name = Path(str(entry)).name.lower()
            if not any(marker in name for marker in ("license", "copying", "notice", "authors")):
                continue
            source = Path(distribution.locate_file(entry))
            if not source.is_file():
                continue
            relative = Path(str(entry))
            destination = package_target / relative.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and sha256(destination) == sha256(source):
                continue
            shutil.copy2(source, destination)
            copied.append(destination.relative_to(target.parent).as_posix())
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    destination = target / "cpython-3.13.14" / "LICENSE.txt"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(python_license, destination)
    copied.append(destination.relative_to(target.parent).as_posix())
    return sorted(set(copied))


def attribution_entries(value: object):
    if isinstance(value, list):
        for item in value:
            yield from attribution_entries(item)
    elif isinstance(value, dict):
        if "License" in value or "LicenseId" in value:
            yield value
        else:
            for item in value.values():
                yield from attribution_entries(item)


def review_attributions(attributions: list[dict], license_files: list[str]) -> dict:
    license_ids = set()
    custom_reviews = []
    missing_id_reviews = []
    unresolved = []
    available_license_files = set(license_files)
    for source in attributions:
        for item in attribution_entries(source["content"]):
            license_id = item.get("LicenseId")
            license_name = item.get("License")
            if license_id:
                license_ids.add(license_id)
            if license_id and license_id.startswith("LicenseRef-"):
                review = CUSTOM_LICENSE_REVIEWS.get(license_id)
                if review is None or review["evidence_file"] not in available_license_files:
                    unresolved.append({"name": item.get("Name"), "license_id": license_id})
                    continue
                custom_reviews.append(
                    {
                        "name": item.get("Name"),
                        "license_id": license_id,
                        **review,
                    }
                )
            elif not license_id:
                if (
                    item.get("Name") == "Python"
                    and license_name == "PSF LICENSE AGREEMENT FOR PYTHON 3.7.0"
                ):
                    missing_id_reviews.append(
                        {
                            "name": "Python 3.7.0 adapted source fragments",
                            "declared_license": license_name,
                            "classification": "ALLOWED",
                            "basis": "Known PSF license; the attributed source file is present "
                            "inside the complete PySide source archive.",
                        }
                    )
                else:
                    unresolved.append({"name": item.get("Name"), "license": license_name})
    if unresolved:
        raise RuntimeError(f"Unresolved Qt attribution licenses: {unresolved}")
    unique_custom = {row["license_id"]: row for row in custom_reviews}
    return {
        "declared_license_ids": sorted(license_ids),
        "custom_license_reviews": [unique_custom[key] for key in sorted(unique_custom)],
        "missing_spdx_id_reviews": missing_id_reviews,
        "unresolved": [],
    }


def extract_compliance_evidence(archive: Path, target: Path) -> dict:
    license_files = []
    attributions = []
    with tarfile.open(archive, "r:xz") as source:
        for member in source:
            normalized = member.name.replace("\\", "/")
            if not member.isfile():
                continue
            if "/LICENSES/" in f"/{normalized}" and normalized.lower().endswith(".txt"):
                stream = source.extractfile(member)
                if stream is None:
                    continue
                destination = target / "LICENSES" / Path(normalized).name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(stream.read())
                license_files.append(destination.name)
            if normalized.endswith("qt_attribution.json"):
                stream = source.extractfile(member)
                if stream is None:
                    continue
                try:
                    content = json.loads(stream.read().decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                attributions.append({"path": normalized, "content": content})
    attribution_path = target / "THIRD_PARTY_ATTRIBUTIONS.json"
    attribution_path.write_text(
        json.dumps({"archive": archive.name, "files": attributions}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return {
        "license_files": sorted(set(license_files)),
        "attribution_files": len(attributions),
        "attribution_inventory": attribution_path.name,
        "attribution_license_review": review_attributions(attributions, license_files),
    }


def generate_notice(source_rows: list[dict]) -> str:
    source_lines = "\n".join(
        f"- `{row['filename']}` — {row['component']} {row['version']}; "
        f"SHA-256 `{row['sha256']}`; included under `THIRD_PARTY_SOURCE/`."
        for row in source_rows
    )
    return f"""# NL Project 3.0 — third-party notices

NL Project application code remains proprietary. Third-party components remain under their
own licenses; this notice does not relicense NL Project source code.

## Qt for Python / Qt LGPL route

This onedir package uses unmodified PySide6/Shiboken6/Qt 6.11.1 shared DLLs and Python
extension modules loaded dynamically from `_internal`. No Qt library is statically linked into
NL Project. The package intentionally excludes the unused Qt WebEngine, Chromium, QML, PDF,
software OpenGL, SVG and Virtual Keyboard payloads.

Recipients may replace or modify the LGPL-covered Qt/PySide6/Shiboken6 libraries, reverse
engineer the application when necessary to debug those modifications, and run the application
with ABI-compatible replacement libraries. Replace the relevant DLL/PYD files under
`_internal/PySide6` and `_internal/shiboken6` while preserving the onedir layout. Distribution
terms for NL Project must not restrict those LGPL rights.

Full license texts are in `THIRD_PARTY_LICENSES`. Complete corresponding source archives for
the exact LGPL components are shipped with this copy:

{source_lines}

## Microsoft runtime boundary

The CPython 3.13.14 Windows binary and its Microsoft Distributable Code are covered by the
additional Windows conditions in `THIRD_PARTY_LICENSES/cpython-3.13.14/LICENSE.txt`. Microsoft
runtime DLLs shipped inside the PySide6 wheels are not redistributed. Qt requires the separately
installed Microsoft Visual C++ v14 x64 Redistributable 14.44 or later as a system prerequisite;
that external prerequisite is installed and licensed separately from NL Project.

## Other components

`RUNTIME_COMPONENTS.json` is generated from the actual clean distribution and records every
distributed EXE/DLL/PYD with its hash, origin component, license family and gate classification.
Permissive package licenses, PyInstaller's bootloader exception, Qt/PySide license texts and Qt
third-party attribution records are under `THIRD_PARTY_LICENSES`.

Official evidence references:

- https://doc.qt.io/qtforpython-6/
- https://www.qt.io/development/open-source-lgpl-obligations
- https://www.qt.io/faq/qt-open-source-licensing
- https://www.sqlite.org/copyright.html
- https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist
"""


def generate(dist: Path, analysis_toc: Path) -> dict:
    validate_payload_shape(dist)
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    validate_policy(policy)
    source_config = json.loads(SOURCE_CONFIG_PATH.read_text(encoding="utf-8"))
    licenses = dist / "THIRD_PARTY_LICENSES"
    sources = dist / "THIRD_PARTY_SOURCE"
    for target in (licenses, sources):
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
    copied_licenses = copy_distribution_licenses(licenses)
    source_rows = []
    source_evidence = []
    for row in source_config["sources"]:
        cached = SOURCE_CACHE / row["filename"]
        if (
            not cached.is_file()
            or cached.stat().st_size != row["bytes"]
            or sha256(cached) != row["sha256"]
        ):
            raise RuntimeError(f"Missing or invalid prepared compliance source: {cached}")
        destination = sources / row["filename"]
        shutil.copy2(cached, destination)
        source_rows.append(row)
        evidence_target = licenses / safe_directory_name(row["component"])
        evidence_target.mkdir(parents=True, exist_ok=True)
        source_evidence.append(
            {
                "component": row["component"],
                "archive": destination.relative_to(dist).as_posix(),
                "bytes": destination.stat().st_size,
                "sha256": sha256(destination),
                "evidence": extract_compliance_evidence(destination, evidence_target),
            }
        )
    modules = analysis_modules(analysis_toc)
    native_rows = scan_native(dist)
    inventory = {
        "schema_version": 1,
        "status": "PASSED",
        "policy_source": policy["policy_source"],
        "actual_python_components": actual_python_components(modules),
        "native_files": native_rows,
        "lgpl_source_evidence": source_evidence,
        "copied_license_files": copied_licenses,
        "external_prerequisites": [
            {
                "component": "Microsoft Visual C++ v14 x64 Redistributable",
                "minimum_version": "14.44",
                "distribution": "not included; separately installed system prerequisite",
                "classification": "CONDITIONAL",
            }
        ],
        "locked_dependency_policy": policy["packages"],
    }
    (dist / "RUNTIME_COMPONENTS.json").write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (dist / "THIRD_PARTY_NOTICES.md").write_text(generate_notice(source_rows), encoding="utf-8")
    return inventory


def validate_generated(dist: Path) -> dict:
    validate_payload_shape(dist)
    inventory_path = dist / "RUNTIME_COMPONENTS.json"
    notice_path = dist / "THIRD_PARTY_NOTICES.md"
    if not inventory_path.is_file() or not notice_path.is_file():
        raise RuntimeError("Generated compliance inventory/notices are missing")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    actual_native = scan_native(dist)
    if inventory["native_files"] != actual_native:
        raise RuntimeError("Generated native inventory does not match actual distribution")
    for row in inventory["lgpl_source_evidence"]:
        archive = dist / row["archive"]
        if (
            not archive.is_file()
            or archive.stat().st_size != row["bytes"]
            or sha256(archive) != row["sha256"]
        ):
            raise RuntimeError(f"LGPL source evidence mismatch: {archive}")
    if not (dist / "THIRD_PARTY_LICENSES" / "qt-base" / "LICENSES" / "LGPL-3.0-only.txt").is_file():
        raise RuntimeError("Qt LGPL-3.0 license text is missing")
    return inventory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--analysis-toc", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    dist = args.dist.resolve()
    if not dist.is_dir():
        raise RuntimeError(f"Distribution does not exist: {dist}")
    if args.validate_only:
        inventory = validate_generated(dist)
    else:
        if args.analysis_toc is None:
            raise RuntimeError("--analysis-toc is required while generating compliance evidence")
        inventory = generate(dist, args.analysis_toc.resolve())
        inventory = validate_generated(dist)
    print(
        json.dumps(
            {
                "status": "PASSED",
                "native_files": len(inventory["native_files"]),
                "python_components": len(inventory["actual_python_components"]),
                "unknown_or_blocked": 0,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
