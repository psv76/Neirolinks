"""Q216: full non-publishable Specification cutover preview.

Preview the complete bill of materials with one source per physical Conduit.
Production build(), exports and procurements are unchanged. The caller must
supply a consistent read snapshot and prevent project-revision races.
"""

from __future__ import annotations

from dataclasses import dataclass

from .conduit_source_preview import ConduitSpecificationDecision
from .domain import SpecificationIssue, SpecificationSource

_LEGACY_TUBE_KINDS = frozenset({"CONDUIT", "BUS_SEGMENT_CONDUIT"})


@dataclass(frozen=True, slots=True)
class IntegratedConduitCutover:
    sources: tuple[SpecificationSource, ...]
    issues: tuple[SpecificationIssue, ...]
    legacy_tube_source_count: int
    replacement_conduit_source_count: int
    orphan_bus_source_ids: tuple[str, ...]
    preview_only: bool = True
    can_publish: bool = False


def compose_integrated_conduit_cutover(
    *,
    baseline_sources: tuple[SpecificationSource, ...],
    replacement_conduits: tuple[SpecificationSource, ...],
    decisions: tuple[ConduitSpecificationDecision, ...],
    assigned_bus_segment_ids: frozenset[str],
) -> IntegratedConduitCutover:
    """Replace all legacy physical tube sources, *only in memory*, exactly once.

    Non-Conduit source identity, quantities and ordering are preserved.
    Missing BUS->Conduit assignment is an explicit blocker, never a silent
    disappearance from the production specification.
    """
    legacy = tuple(
        source for source in baseline_sources
        if source.source_kind in _LEGACY_TUBE_KINDS
    )
    others = tuple(
        source for source in baseline_sources
        if source.source_kind not in _LEGACY_TUBE_KINDS
    )
    if any(source.source_kind != "CONDUIT" for source in replacement_conduits):
        raise ValueError("Only physical Conduit sources may replace legacy tube sources")
    new_ids = [source.source_id for source in replacement_conduits]
    decisions_by_id = {decision.conduit_id: decision for decision in decisions}
    if len(new_ids) != len(set(new_ids)):
        raise ValueError("Duplicate physical Conduit sources in cutover")
    if len(decisions_by_id) != len(decisions) or set(new_ids) != set(decisions_by_id):
        raise ValueError("Cutover must cover every physical Conduit exactly once")
    for source in replacement_conduits:
        decision = decisions_by_id[source.source_id]
        if source.quantity != decision.quantity_m:
            # Individual source overrides may be valid: this method is fed
            # already corrected sources, so only block unsafe unknown -> number.
            if decision.quantity_m is None and source.quantity is not None:
                raise ValueError("Blocked Conduit quantity may not be overridden into a number")
        if decision.status.startswith("BLOCKED_") and source.quantity is not None:
            raise ValueError("Blocked physical Conduit cannot enter a purchasing quantity")

    old_bus = tuple(
        source for source in legacy if source.source_kind == "BUS_SEGMENT_CONDUIT"
    )
    old_bus_ids = [source.source_id for source in old_bus]
    if len(set(old_bus_ids)) != len(old_bus_ids):
        raise ValueError("Duplicate legacy BUS segment tube sources")
    unmatched = tuple(sorted(set(old_bus_ids) - assigned_bus_segment_ids))
    issues: list[SpecificationIssue] = []
    for source_id in unmatched:
        issues.append(
            SpecificationIssue(
                code="BUS_SEGMENT_WITHOUT_ACTIVE_CONDUIT",
                source_kind="BUS_SEGMENT_CONDUIT",
                source_id=source_id,
                message="Сегмент BUS с потребностью в трубе не привязан к активной Conduit",
                status="PROJECT_ERROR",
                blocking=True,
                required_action="Восстановить физическую привязку BUS до выпуска спецификации",
            )
        )
    for decision in decisions:
        if not decision.status.startswith("BLOCKED_"):
            continue
        issues.append(
            SpecificationIssue(
                code="PHYSICAL_CONDUIT_QUANTITY_BLOCKED",
                source_kind="CONDUIT",
                source_id=decision.conduit_id,
                message=(
                    f"Труба {decision.designation}: не подтверждена физическая длина "
                    f"или совместимость ({decision.status})"
                ),
                status="DATA_REQUIRED",
                blocking=True,
                required_action="Проверить Q03/Q06 и подтвердить итоговую длину физической трубы",
            )
        )

    result = others + replacement_conduits
    keys = [(source.source_kind, source.source_id) for source in result]
    if len(keys) != len(set(keys)):
        raise ValueError("Repeated Specification source identity after tube cutover")
    return IntegratedConduitCutover(
        sources=result,
        issues=tuple(issues),
        legacy_tube_source_count=len(legacy),
        replacement_conduit_source_count=len(replacement_conduits),
        orphan_bus_source_ids=unmatched,
    )
