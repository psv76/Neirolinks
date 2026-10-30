"""Module entry point with a controlled fatal-startup boundary."""

from collections.abc import Callable, Sequence

from nl_project_2.app import run
from nl_project_2.config import PathConfig
from nl_project_2.structured_log import record_fatal_startup, show_fatal_startup


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: Callable[[Sequence[str] | None], int] = run,
) -> int:
    try:
        return runner(argv)
    except Exception as error:
        paths = PathConfig.from_environment()
        try:
            log_path = record_fatal_startup(error, paths)
        except Exception:
            # Logging failures must never hide the initial failure from a
            # user who launched the windowless pythonw.exe entry point.
            log_path = paths.log_root / "fatal-startup.jsonl"
        show_fatal_startup(error, log_path)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
