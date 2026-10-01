"""Application port used by TASK_011 adapters to provide immutable CAD observations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import CadObservationBatch


@dataclass(frozen=True, slots=True)
class CadReadRequest:
    expected_document_identity: str
    deadline_seconds: float
    definition_names: tuple[str, ...] = ()


class CadObservationPort(Protocol):
    def read_observations(self, request: CadReadRequest) -> CadObservationBatch:
        """Return transport-neutral observations; implementation may live out-of-process."""
        ...
