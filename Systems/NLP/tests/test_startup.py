from __future__ import annotations

import json
from pathlib import Path

from nl_project_2.__main__ import main


def test_fatal_startup_is_logged_without_traceback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NLP2_LOCAL_STATE_ROOT", str(tmp_path / "state"))

    def fail(_argv) -> int:
        raise RuntimeError("sensitive detail must not be stored")

    assert main([], runner=fail) == 1
    log_path = tmp_path / "state" / "logs" / "fatal-startup.jsonl"
    event = json.loads(log_path.read_text(encoding="utf-8"))
    assert event["component"] == "app_shell"
    assert event["error_category"] == "RuntimeError"
    assert "sensitive detail" not in log_path.read_text(encoding="utf-8")
