"""Shared atomic line-import selection contract for engine and preview UI."""

from __future__ import annotations

from dataclasses import dataclass

from .models import ChangeClass


@dataclass(frozen=True, slots=True)
class AtomicLineImportGroup:
    line_number: str
    required_paths: frozenset[str]
    blocked_paths: frozenset[str]

    @property
    def blocked(self) -> bool:
        return bool(self.blocked_paths)


def atomic_line_import_groups(
    proposal,
    allowed_statuses: set[ChangeClass] | frozenset[ChangeClass] | None = None,
) -> tuple[AtomicLineImportGroup, ...]:
    """Derive the exact all-insertion set used by the existing partial-line guard."""

    handles_by_line: dict[str, set[str]] = {}
    for observation in proposal.batch.observations:
        if not observation.handle:
            continue
        attributes = {item.tag: item.value for item in observation.raw_attributes}
        cable_id = str(attributes.get("CABLE_ID", "")).strip()
        if cable_id:
            handles_by_line.setdefault(cable_id.split(".", 1)[0], set()).add(observation.handle)
    changes_by_path = {change.field_path: change for change in proposal.changes}
    groups = []
    for line_number, handles in sorted(handles_by_line.items()):
        required = frozenset(f"{handle}:$" for handle in handles)
        changes = [changes_by_path.get(path) for path in required]
        if not any(
            change is not None and change.change_class is ChangeClass.NEW_DWG_INSERTION
            for change in changes
        ):
            continue
        blocked = frozenset(
            path
            for path in required
            if changes_by_path.get(path) is None
            or (
                allowed_statuses is not None
                and changes_by_path[path].change_class not in allowed_statuses
            )
        )
        groups.append(AtomicLineImportGroup(line_number, required, blocked))
    return tuple(groups)
