"""Resolve application and bundled-resource paths in source and frozen modes."""

from __future__ import annotations

import sys
from pathlib import Path

CAD_BRIDGE_MODE = "--nlp2-cad-bridge"


def is_frozen() -> bool:
    """Return whether the current interpreter is a frozen application."""
    return bool(getattr(sys, "frozen", False))


def application_root() -> Path:
    """Return the user-visible installation root or the source repository root."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def bundled_root() -> Path:
    """Return the root where PyInstaller places bundled data files."""
    if is_frozen():
        return Path(sys._MEIPASS).resolve()
    return application_root()


def bundled_path(*parts: str) -> Path:
    """Resolve an immutable application resource without touching user data."""
    return bundled_root().joinpath(*parts)


def package_data_path(*parts: str) -> Path:
    """Resolve data stored next to Python package code in source or frozen mode."""
    prefix = () if is_frozen() else ("src",)
    return bundled_path(*prefix, "nl_project_2", *parts)


def sta_bridge_command(pipe: str, bridge_script: Path | None = None) -> list[str]:
    """Build the command for a separate source or frozen STA bridge process."""
    if bridge_script is not None:
        return [sys.executable, str(bridge_script), "--pipe", pipe]
    if is_frozen():
        return [sys.executable, CAD_BRIDGE_MODE, "--pipe", pipe]
    script = application_root() / "tools" / "autocad_sta_bridge.py"
    return [sys.executable, str(script), "--pipe", pipe]
