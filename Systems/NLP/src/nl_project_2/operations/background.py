"""Cancellable background calculations over immutable input snapshots."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any


class OperationCancelled(RuntimeError):
    pass


class StaleOperationResult(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OperationSnapshot:
    project_id: str
    input_revision: int
    payload: Any
    correlation_id: str

    @classmethod
    def create(cls, project_id: str, input_revision: int, payload: Any):
        return cls(project_id, input_revision, payload, str(uuid.uuid4()))


@dataclass(frozen=True, slots=True)
class OperationResult:
    snapshot: OperationSnapshot
    value: Any


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def checkpoint(self) -> None:
        if self.cancelled:
            raise OperationCancelled("Background operation cancelled")


@dataclass(slots=True)
class OperationHandle:
    future: Future
    token: CancellationToken

    def cancel(self) -> None:
        self.token.cancel()


class BackgroundOperationManager:
    def __init__(self, *, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="nlp2-worker"
        )

    def submit(
        self,
        snapshot: OperationSnapshot,
        worker: Callable[[OperationSnapshot, CancellationToken, Callable[[int], None]], Any],
        *,
        progress: Callable[[int], None] | None = None,
    ) -> OperationHandle:
        token = CancellationToken()
        report = progress or (lambda _value: None)

        def execute() -> OperationResult:
            token.checkpoint()
            value = worker(snapshot, token, report)
            token.checkpoint()
            return OperationResult(snapshot, value)

        return OperationHandle(self._executor.submit(execute), token)

    @staticmethod
    def apply_if_current(
        result: OperationResult,
        *,
        current_revision: int,
        commit: Callable[[Any], Any],
    ) -> Any:
        if result.snapshot.input_revision != current_revision:
            raise StaleOperationResult(
                f"Result revision {result.snapshot.input_revision} is stale; "
                f"current revision is {current_revision}"
            )
        return commit(result.value)

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)
