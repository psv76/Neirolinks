from __future__ import annotations

import json
import sys
import types
from pathlib import Path

from tools import package_compliance, package_entry


def test_dependency_policy_exactly_matches_locked_environment() -> None:
    root = Path(__file__).resolve().parents[2]
    policy = json.loads(
        (root / "packaging" / "dependency_license_inventory.json").read_text(encoding="utf-8")
    )

    package_compliance.validate_policy(policy)

    assert len(policy["packages"]) == 31
    assert {row["classification"] for row in policy["packages"]} == {
        "ALLOWED",
        "CONDITIONAL",
    }


def test_native_inventory_mapping_has_no_implicit_license_fallback() -> None:
    assert package_compliance.native_component("_internal/PySide6/Qt6Core.dll") == (
        "Qt Base 6.11.1",
        "LGPL-3.0-only",
        "CONDITIONAL",
    )
    assert package_compliance.native_component("_internal/sqlite3.dll") == (
        "SQLite 3.50.4",
        "Public Domain",
        "ALLOWED",
    )
    assert package_compliance.native_component("_internal/unreviewed.dll") == (
        "UNKNOWN",
        "UNKNOWN",
        "UNKNOWN",
    )


def test_spec_bundles_required_assets_and_excludes_unused_heavy_qt() -> None:
    root = Path(__file__).resolve().parents[2]
    spec = (root / "packaging" / "nl_project_3.spec").read_text(encoding="utf-8")

    assert 'root / "resources" / "catalogs"' in spec
    assert 'root / "resources" / "autocad"' in spec
    assert 'root / "src" / "nl_project_2" / "persistence" / "migrations"' in spec
    assert '"PySide6.QtWebEngineCore"' in spec
    assert '"PySide6.QtWebEngineWidgets"' in spec
    assert '"pyside6/plugins/platforms/qoffscreen.dll"' in spec
    assert '"pyside6/plugins/platforms/qwindows.dll"' in spec
    assert "datas=[]" not in spec.replace(" ", "")


def test_package_entry_dispatches_sta_bridge_without_importing_gui(monkeypatch) -> None:
    observed = {}
    fake_bridge = types.ModuleType("autocad_sta_bridge")

    def bridge_main(arguments):
        observed["arguments"] = arguments
        return 17

    fake_bridge.main = bridge_main
    monkeypatch.setitem(sys.modules, "autocad_sta_bridge", fake_bridge)

    assert package_entry.package_main(["--nlp3-cad-bridge", "--pipe", "test-pipe"]) == 17
    assert observed == {"arguments": ["--pipe", "test-pipe"]}
