"""Versioned local application profile kept outside Project SQLite."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LastUsedPreference:
    action_type: str
    stable_identity: str | None
    resolved: bool
    updated_at_utc: str | None = None


class LocalApplicationProfile:
    """Atomic JSON profile for cross-project, non-engineering preferences."""

    VERSION = 1

    def __init__(self, local_state_root: Path) -> None:
        self.path = Path(local_state_root) / "application-profile-v1.json"

    @classmethod
    def _empty(cls) -> dict:
        return {"version": cls.VERSION, "last_used": {}}

    def load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return self._empty()
        if value.get("version") != self.VERSION or not isinstance(value.get("last_used"), dict):
            return self._empty()
        return value

    def preference(self, action_type: str) -> LastUsedPreference:
        action = str(action_type).strip().upper()
        entry = self.load()["last_used"].get(action)
        if not isinstance(entry, dict) or not isinstance(entry.get("stable_identity"), str):
            return LastUsedPreference(action, None, False)
        return LastUsedPreference(
            action,
            entry["stable_identity"],
            True,
            entry.get("updated_at_utc"),
        )

    def resolve(self, action_type: str, available_identities: Iterable[str]) -> LastUsedPreference:
        """Resolve a preference and clear only a truly absent/stale catalog identity."""

        preference = self.preference(action_type)
        if preference.stable_identity is None:
            return preference
        available = frozenset(str(item) for item in available_identities)
        if preference.stable_identity in available:
            return preference
        state = self.load()
        state["last_used"].pop(preference.action_type, None)
        self._save(state)
        return LastUsedPreference(preference.action_type, None, False)

    def update(self, action_type: str, stable_identity: str) -> LastUsedPreference:
        action = str(action_type).strip().upper()
        identity = str(stable_identity).strip()
        if not action or not identity:
            raise ValueError("Last-used action and stable identity are required")
        now = datetime.now(UTC).isoformat()
        state = self.load()
        state["last_used"][action] = {
            "stable_identity": identity,
            "updated_at_utc": now,
        }
        self._save(state)
        return LastUsedPreference(action, identity, True, now)

    def _save(self, state: dict) -> None:
        state = dict(state)
        state["version"] = self.VERSION
        state.setdefault("last_used", {})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
