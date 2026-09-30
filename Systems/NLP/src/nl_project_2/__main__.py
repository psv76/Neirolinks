"""Module entry point with a controlled fatal-startup boundary."""

from collections.abc import Callable, Sequence

from nl_project_2.app import run
from nl_project_2.config import PathConfig
from nl_project_2.structured_log import record_fatal_startup


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: Callable[[Sequence[str] | None], int] = run,
) -> int:
    try:
        return runner(argv)
    except Exception as error:
        record_fatal_startup(error, PathConfig.from_environment())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
