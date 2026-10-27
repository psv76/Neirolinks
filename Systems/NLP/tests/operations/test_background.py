from __future__ import annotations

import threading
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


def test_worker_progress_qt_signal_runs_on_gui_thread(qtbot):
    manager = BackgroundOperationManager(max_workers=1)
    controller = BackgroundOperationController(manager)
    gui_thread = threading.get_ident()
    worker_thread_ids = []
    delivered = []
    controller.progress.connect(lambda value: delivered.append((value, threading.get_ident())))

    def worker(_snapshot, token, progress):
        worker_thread_ids.append(threading.get_ident())
        for index in range(80):
            token.checkpoint()
            progress(index)
            time.sleep(0.0005)
        return "finished"

    with qtbot.waitSignal(controller.completed, timeout=4500) as captured:
        controller.start(OperationSnapshot.create("p", 1, ()), worker)
    assert captured.args[0].value == "finished"
    assert worker_thread_ids and worker_thread_ids[0] != gui_thread
    assert [item[0] for item in delivered] == list(range(80))
    assert {item[1] for item in delivered} == {gui_thread}
    manager.close()


def test_progress_callback_survives_deleted_qt_receiver(qtbot):
    manager = BackgroundOperationManager(max_workers=1)
    controller = BackgroundOperationController(manager)

    def worker(_snapshot, _token, progress):
        for index in range(70):
            progress(index)
            time.sleep(0.004)
        return "safe_after_gui_closed"

    controller.start(OperationSnapshot.create("p", 1, ()), worker)
    worker_handle = controller.handle
    controller.deleteLater()
    qtbot.wait(60)
    assert worker_handle.future.result(timeout=4).value == "safe_after_gui_closed"
    manager.close()
