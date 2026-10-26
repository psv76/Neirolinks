"""Read-only scan evidence; candidates never imply a committed transaction."""

from collections.abc import Iterable

from .models import ChangeClass, ScanProposal


def insertion_candidates(proposal: ScanProposal) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "path": change.field_path,
            "handle": change.handle,
            "cable_id": str((change.dwg_value or {}).get("CABLE_ID") or ""),
        }
        for change in proposal.changes
        if change.change_class is ChangeClass.NEW_DWG_INSERTION
    )


def preview_evidence(proposal: ScanProposal) -> str:
    candidates = insertion_candidates(proposal)
    identities = ", ".join(
        f"{item['cable_id'] or 'без CABLE_ID'} (Handle {item['handle']})" for item in candidates
    )
    lines = [
        f"Кандидаты NEW_DWG_INSERTION в исходном preview: {len(candidates)}. {identities}",
        "Это кандидаты, а не подтверждение Apply. Ошибки указаны отдельно; "
        "ошибка общей транзакции отменяет весь выбранный импорт.",
    ]
    for issue in proposal.issues:
        if issue.blocks_acceptance:
            handles = tuple(dict.fromkeys(h for h in (issue.handle, *issue.related_handles) if h))
            scope = ", ".join(handles) if handles else "весь импорт"
            lines.append(f"{issue.code} [{scope}] {issue.field or ''}: {issue.message}")
    return "\n".join(lines)


def apply_failure_evidence(
    proposal: ScanProposal, selected_paths: Iterable[str], error: Exception
) -> dict:
    selected = frozenset(selected_paths)
    return {
        "project_id": proposal.project_id,
        "document_identity": proposal.batch.document_identity,
        "binding_id": proposal.binding_id,
        "project_revision": proposal.project_revision,
        "selected_count": len(selected),
        "selected_paths": sorted(selected),
        "insertion_candidates": insertion_candidates(proposal),
        "selected_insertion_count": sum(
            item["path"] in selected for item in insertion_candidates(proposal)
        ),
        "status": "NOT_APPLIED",
        "reason": f"{type(error).__name__}: {error}",
    }


def apply_failure_message(error: Exception) -> str:
    return (
        "DWG → Project: выбранный импорт не применён. Проверка могла остановить Apply "
        "до записи; при ошибке транзакции все её изменения отменены. "
        "Исправьте указанную причину и повторите сканирование.\n"
        f"{type(error).__name__}: {error}"
    )
