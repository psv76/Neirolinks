"""Minimal PySide6 shell for the 3.0 product line."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget

from nl_project_2 import BUILD_STAGE, PRODUCT_LINE, PRODUCT_NAME


class MainWindow(QMainWindow):
    def __init__(self, runtime=None) -> None:
        super().__init__()
        self._runtime = runtime
        self.setObjectName("nlProject3MainWindow")
        self.setWindowTitle(f"{PRODUCT_NAME} {PRODUCT_LINE}")
        self.resize(720, 420)

        if runtime is None:
            label = QLabel(f"{PRODUCT_NAME} {PRODUCT_LINE}\n{BUILD_STAGE}")
            label.setObjectName("productLineLabel")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            central = QWidget()
            layout = QVBoxLayout(central)
            layout.addWidget(label)
            self.setCentralWidget(central)
        else:
            from nl_project_2.presentation.object_workspace import ObjectWorkspace

            self.setCentralWidget(ObjectWorkspace(runtime, self))

    def closeEvent(self, event) -> None:
        if self._runtime is not None:
            self._runtime.close()
        super().closeEvent(event)
