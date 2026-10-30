"""Application-shell orchestration; no project or persistence access belongs here."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from nl_project_2 import BUILD_STAGE, PRODUCT_LINE, PRODUCT_NAME
from nl_project_2.config import DEFAULT_DATABASE_NAME, PathConfig
from nl_project_2.main_window import MainWindow
from nl_project_2.objects.instance_lock import DatabaseInstanceLock
from nl_project_2.objects.runtime import ApplicationRuntime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nl-project-3")
    parser.add_argument(
        "--auto-close-ms",
        type=int,
        default=0,
        metavar="MILLISECONDS",
        help="close the shell after a positive delay; intended for deployment smoke checks",
    )
    parser.add_argument("--version", action="store_true", help="print the product-line identifier")
    parser.add_argument("--database", type=Path, help="explicit NL Project 3.0 database path")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.version:
        print(f"{PRODUCT_NAME} {PRODUCT_LINE} ({BUILD_STAGE})")
        return 0
    if args.auto_close_ms < 0:
        raise ValueError("--auto-close-ms must be zero or positive")

    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName(PRODUCT_NAME)
    app.setApplicationVersion(PRODUCT_LINE)
    paths = PathConfig.from_environment()
    database_path = (args.database or paths.user_projects_root / DEFAULT_DATABASE_NAME).resolve()
    # A live process owns this OS lock for its full GUI lifetime. A crashed
    # process automatically releases it, but an unclosed work period remains
    # available for conservative recovery at the last persisted heartbeat.
    with DatabaseInstanceLock(database_path) as lock:
        runtime = ApplicationRuntime.open(paths, database_path=database_path)
        try:
            runtime.work_time.recover_abandoned_session(lock)
            window = MainWindow(runtime)
            heartbeat = QTimer(window)
            heartbeat.setInterval(30_000)
            heartbeat.timeout.connect(runtime.work_time.heartbeat)
            heartbeat.start()
            window.showMaximized()
            if args.auto_close_ms:
                QTimer.singleShot(args.auto_close_ms, window.close)
            return app.exec()
        finally:
            # Also close an active period when Qt exits without a closeEvent.
            runtime.close()
