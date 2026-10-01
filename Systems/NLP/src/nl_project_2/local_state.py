"""Versioned local UI state, kept outside Project SQLite."""

from __future__ import annotations

import json
import os
from pathlib import Path


class UiStateStore:
    VERSION = 1

    def __init__(self, local_state_root: Path) -> None:
        self.path = local_state_root / "ui-state-v1.json"

    def load(self) -> dict:
        if not self.path.exists():
            return {"version": self.VERSION}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": self.VERSION}
        if value.get("version") != self.VERSION:
            return {"version": self.VERSION}
        return value

    def update(self, **values) -> None:
        state = self.load()
        state.update(values)
        state["version"] = self.VERSION
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
