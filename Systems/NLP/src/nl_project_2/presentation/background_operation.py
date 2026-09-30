"""Qt adapter that delivers pure background results back on the UI thread."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from nl_project_2.operations import OperationCancelled


class BackgroundOperationController(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str, str)
    cancelled = Signal()

    def __init__(self, manager, parent=None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.handle = None
        self._timer = QTimer(self)
        self._timer.setInterval(25)
        self._timer.timeout.connect(self._poll)

    def start(self, snapshot, worker) -> None:
        if self.handle is not None and not self.handle.future.done():
            raise RuntimeError("A background operation is already running")
        self.handle = self.manager.submit(snapshot, worker, progress=self.progress.emit)
        self._timer.start()

    def cancel(self) -> None:
        if self.handle is not None:
            self.handle.cancel()

    def _poll(self) -> None:
        if self.handle is None or not self.handle.future.done():
            return
        self._timer.stop()
        try:
            result = self.handle.future.result()
        except OperationCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(type(exc).__name__, str(exc))
        else:
            self.completed.emit(result)
