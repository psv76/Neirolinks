from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import QLabel

from nl_project_2 import BUILD_STAGE, PRODUCT_LINE, PRODUCT_NAME
from nl_project_2.main_window import MainWindow


def test_main_window_identifies_product_line(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.windowTitle() == f"{PRODUCT_NAME} {PRODUCT_LINE}"
    assert BUILD_STAGE in window.findChild(QLabel, "productLineLabel").text()


def test_module_version_command() -> None:
    root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(root / "src")
    completed = subprocess.run(
        [sys.executable, "-m", "nl_project_2", "--version"],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == "NL Project 2.0 (objects)"


def test_shell_process_starts_and_closes(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(root / "src")
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment["NLP2_PROJECTS_ROOT"] = str(tmp_path / "projects")
    completed = subprocess.run(
        [sys.executable, "-m", "nl_project_2", "--auto-close-ms", "25"],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
