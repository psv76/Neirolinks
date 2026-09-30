from __future__ import annotations

import sys
from pathlib import Path

from nl_project_2 import runtime_resources


def test_source_resources_resolve_from_repository() -> None:
    root = Path(__file__).resolve().parents[1]

    assert runtime_resources.application_root() == root
    assert (
        runtime_resources.bundled_path("resources", "catalogs") == root / "resources" / "catalogs"
    )
    assert runtime_resources.package_data_path("persistence", "migrations") == (
        root / "src" / "nl_project_2" / "persistence" / "migrations"
    )
    assert runtime_resources.sta_bridge_command("pipe") == [
        sys.executable,
        str(root / "tools" / "autocad_sta_bridge.py"),
        "--pipe",
        "pipe",
    ]


def test_frozen_resources_and_bridge_use_distribution_contract(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "NLProject2" / "NLProject2.exe"
    bundled = tmp_path / "NLProject2" / "_internal"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundled), raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    assert runtime_resources.application_root() == executable.parent
    assert (
        runtime_resources.bundled_path("resources", "autocad") == bundled / "resources" / "autocad"
    )
    assert runtime_resources.package_data_path("persistence", "migrations") == (
        bundled / "nl_project_2" / "persistence" / "migrations"
    )
    assert runtime_resources.sta_bridge_command("pipe") == [
        str(executable),
        runtime_resources.CAD_BRIDGE_MODE,
        "--pipe",
        "pipe",
    ]
