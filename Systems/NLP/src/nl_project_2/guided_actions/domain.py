"""Immutable user-facing contracts for one guided single-line action."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class GuidedAction(StrEnum):
    PROTECTION = "PROTECTION"
    POWER = "POWER"
    OUTPUT = "OUTPUT"
    INPUT = "INPUT"

    @property
    def label(self) -> str:
        return {
            self.PROTECTION: "Назначить защиту",
            self.POWER: "Назначить питание",
            self.OUTPUT: "Назначить выход/канал",
            self.INPUT: "Назначить вход",
        }[self]


class CandidateState(StrEnum):
    SELECTABLE = "SELECTABLE"
    UNAVAILABLE = "UNAVAILABLE"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True)
class GuidedCandidate:
    """Human-first option; canonical identifiers stay behind the service boundary."""

    candidate_id: str
    target_label: str
    instance_label: str | None
    location_label: str | None
    state: CandidateState
    selectable: bool
    reason_codes: tuple[str, ...]
    explanation: str
    warnings: tuple[str, ...] = ()
    technical_identity: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateQuery:
    action: GuidedAction
    action_label: str
    owner_label: str
    project_revision: int
    candidates: tuple[GuidedCandidate, ...]
    status: str
    explanation: str
    suggested_next_actions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GuidedActionPreview:
    action: GuidedAction
    action_label: str
    owner_label: str
    target_label: str
    changes: tuple[str, ...]
    existing_state: tuple[str, ...]
    warnings: tuple[str, ...]
    missing_facts: tuple[str, ...]
    project_revision: int
    fingerprint: str
    confirmation_token: str


@dataclass(frozen=True, slots=True)
class GuidedActionReceipt:
    action: GuidedAction
    action_label: str
    project_revision_before: int
    project_revision_after: int
    canonical_fact_kind: str
    canonical_fact_count: int
    updated_owner_label: str
    updated_state: str
    preference_identity: str | None = None
    preference_updated: bool = False
    preference_diagnostic: str | None = None


class GuidedActionError(RuntimeError):
    pass


class CandidateUnavailable(GuidedActionError):
    pass


class ConfirmationRequired(GuidedActionError):
    pass


class StalePreview(GuidedActionError):
    pass
