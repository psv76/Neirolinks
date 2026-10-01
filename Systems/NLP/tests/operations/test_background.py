from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QTimer

from nl_project_2.operations import (
    BackgroundOperationManager,
    OperationCancelled,
    OperationSnapshot,
    StaleOperationResult,
)
from nl_project_2.presentation.background_operation import BackgroundOperationController


def test_cancel_and_stale_result_never_apply_partial_state():
    manager = BackgroundOperationManager(max_workers=1)
    committed = []

    def worker(_snapshot, token, progress):
        for index in range(100):
            token.checkpoint()
            progress(index)
            time.sleep(0.001)
        return "result"

    handle = manager.submit(OperationSnapshot.create("p", 4, (1, 2, 3)), worker)
    handle.cancel()
    with pytest.raises(OperationCancelled):
        handle.future.result(timeout=2)
    assert committed == []

    completed = manager.submit(
        OperationSnapshot.create("p", 4, ()),
        lambda _snapshot, _token, _progress: "ready",
    ).future.result(timeout=2)
    with pytest.raises(StaleOperationResult):
        manager.apply_if_current(completed, current_revision=5, commit=committed.append)
    assert committed == []
    assert (
        manager.apply_if_current(completed, current_revision=4, commit=lambda value: value.upper())
        == "READY"
    )
    manager.close()


def test_qt_event_loop_remains_responsive_during_worker(qtbot):
    manager = BackgroundOperationManager(max_workers=1)
    controller = BackgroundOperationController(manager)
    heartbeats = []
    timer = QTimer()
    timer.setInterval(5)
    timer.timeout.connect(lambda: heartbeats.append(time.perf_counter()))
    timer.start()

    def worker(_snapshot, token, progress):
        for index in range(30):
            token.checkpoint()
            progress(index)
            time.sleep(0.005)
        return "done"

    with qtbot.waitSignal(controller.completed, timeout=3000) as blocker:
        controller.start(OperationSnapshot.create("p", 1, ()), worker)
    timer.stop()
    assert blocker.args[0].value == "done"
    assert len(heartbeats) >= 5
    manager.close()
