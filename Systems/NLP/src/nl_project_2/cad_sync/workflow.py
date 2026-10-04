"""User-facing DWG synchronization planning.

The three-way engine remains authoritative.  This module only decides which
already-classified changes are safe to apply without another per-field
confirmation and which changes still need a user decision.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import ChangeClass, SyncChange
from .selection import atomic_line_import_groups
from .service import PROJECT_TO_DWG_ALLOW_LIST


_AUTO_IMPORT = frozenset({ChangeClass.NEW_DWG_INSERTION, ChangeClass.DWG_CHANGED})


@dataclass(frozen=True, slots=True)
class DwgUpdatePlan:
    import_paths: frozenset[str]
    write_paths: frozenset[str]
    conflicts: tuple[SyncChange, ...]
    problems: tuple[SyncChange, ...]
    blocked_lines: tuple[str, ...]
    missing_bus_roots: tuple[str, ...]


def build_dwg_update_plan(
    proposal,
    *,
    existing_bus_designations: frozenset[str] = frozenset(),
) -> DwgUpdatePlan:
    """Build the normal one-click update plan from an immutable scan proposal.

    Safe one-sided changes are automatic.  True two-sided conflicts, structural
    ambiguity, missing insertions and unresolved/canonical-room work stay
    explicit.
    """

    by_path = {change.field_path: change for change in proposal.changes}

    bus_points = tuple(getattr(getattr(proposal, "snapshot", None), "bus_points", ()) or ())
    missing_bus_roots = tuple(
        sorted(
            {
                str(point.bus_id)
                for point in bus_points
                if str(point.bus_id) not in existing_bus_designations
            }
        )
    )
    missing_bus_handles = {
        str(point.handle)
        for point in bus_points
        if str(point.bus_id) in missing_bus_roots
    }

    groups = atomic_line_import_groups(proposal, set(_AUTO_IMPORT))
    grouped_paths = {path for group in groups for path in group.required_paths}
    import_paths: set[str] = set()
    blocked_lines: list[str] = []

    for group in groups:
        explicit_only = any(
            by_path[path].detail_status == "ROOM_CANONICALIZATION"
            for path in group.required_paths
            if path in by_path
        )
        if group.blocked or explicit_only:
            blocked_lines.append(group.line_number)
            continue
        safe_paths = {
            path
            for path in group.required_paths
            if by_path.get(path) is None or by_path[path].handle not in missing_bus_handles
        }
        if safe_paths != set(group.required_paths):
            blocked_lines.append(group.line_number)
            continue
        import_paths.update(group.required_paths)

    conflicts: list[SyncChange] = []
    problems: list[SyncChange] = []
    write_paths: set[str] = set()

    for change in proposal.changes:
        if change.change_class is ChangeClass.BOTH_CHANGED_CONFLICT:
            conflicts.append(change)
            continue

        unresolved_room = (
            change.field == "ROOM"
            and str(change.display_context.get("room_name") or "").startswith("Не разрешено")
        )
        explicit_room_link = change.detail_status == "ROOM_CANONICALIZATION"

        if change.change_class in _AUTO_IMPORT:
            if change.handle in missing_bus_handles:
                continue
            if (
                change.field_path not in grouped_paths
                and not change.structural
                and not explicit_room_link
            ):
                import_paths.add(change.field_path)
            elif explicit_room_link:
                problems.append(change)
            continue

        if change.change_class is ChangeClass.PROJECT_CHANGED:
            if change.field in PROJECT_TO_DWG_ALLOW_LIST and not change.structural:
                write_paths.add(change.field_path)
            else:
                problems.append(change)
            continue

        if change.change_class in {
            ChangeClass.INVALID_DWG_DATA,
            ChangeClass.IDENTITY_COLLISION,
            ChangeClass.MISSING_DWG_INSERTION,
        }:
            problems.append(change)
            continue

        if unresolved_room or explicit_room_link:
            problems.append(change)

    # Preserve source order and avoid duplicate issue rows.
    seen: set[str] = set()
    ordered_problems = []
    for change in problems:
        if change.field_path in seen:
            continue
        seen.add(change.field_path)
        ordered_problems.append(change)

    return DwgUpdatePlan(
        import_paths=frozenset(import_paths),
        write_paths=frozenset(write_paths),
        conflicts=tuple(conflicts),
        problems=tuple(ordered_problems),
        blocked_lines=tuple(sorted(set(blocked_lines))),
        missing_bus_roots=missing_bus_roots,
    )
