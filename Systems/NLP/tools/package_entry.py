"""Frozen entry point, including the separate-process STA bridge mode."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from nl_project_2.runtime_resources import CAD_BRIDGE_MODE


def package_main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == [CAD_BRIDGE_MODE]:
        from autocad_sta_bridge import main as bridge_main

        return bridge_main(arguments[1:])

    from nl_project_2.__main__ import main as application_main

    return application_main(arguments)


if __name__ == "__main__":
    raise SystemExit(package_main())
