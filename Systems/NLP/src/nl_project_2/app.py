"""Application-shell orchestration; no project or persistence access belongs here."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from nl_project_2 import BUILD_STAGE, PRODUCT_LINE, PRODUCT_NAME
from nl_project_2.config import PathConfig
from nl_project_2.main_window import MainWindow
from nl_project_2.objects.runtime import ApplicationRuntime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nl-project-2")
    parser.add_argument(
        "--auto-close-ms",
        type=int,
        default=0,
        metavar="MILLISECONDS",
        help="close the shell after a positive delay; intended for deployment smoke checks",
    )
    parser.add_argument("--version", action="store_true", help="print the product-line identifier")
    parser.add_argument("--database", type=Path, help="explicit NL Project 2.0 database path")
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
    runtime = ApplicationRuntime.open(PathConfig.from_environment(), database_path=args.database)
    window = MainWindow(runtime)
    window.show()
    if args.auto_close_ms:
        QTimer.singleShot(args.auto_close_ms, window.close)
    return app.exec()
