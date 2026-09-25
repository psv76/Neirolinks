import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nli.cli import BANNER, main


class TTYBuffer(io.StringIO):
    def isatty(self):
        return True


class StubEngine:
    def __init__(self, records):
        self.records = records

    def read_operation(self, command, component=None):
        return self.records[command]

    def mutate(self, command, component):
        return self.records[command]


def status_record(pending=None):
    return {
        "object": "05_31_Ivolga_13",
        "role": "boiler",
        "hostname": "wirenboard-ABF62SL",
        "command": "status",
        "component": None,
        "final_status": "recovery_required" if pending else "ok",
        "components": {
            "hhm": {
                "manifest": {"version": "3.0.0-FSE+d75710dad939"},
                "last_result": "update_ok",
            },
            "pressure_makeup": {
                "manifest": {"version": "1.0"},
                "last_result": "update_ok",
            },
        },
        "last_operations": {
            "hhm": {"command": "update", "final_status": "ok"},
            "pressure_makeup": {"command": "update", "final_status": "ok"},
        },
        "pending": pending,
    }


class CliUiTests(unittest.TestCase):
    def capture(self, args, engine=None, tty=False):
        output = TTYBuffer() if tty else io.StringIO()
        with patch.dict(os.environ, {"NO_COLOR": ""}), contextlib.redirect_stdout(output):
            code = main(args, engine=engine)
        return code, output.getvalue()

    def test_version_has_banner_and_human_title(self):
        code, output = self.capture(["--version"])
        self.assertEqual(code, 0)
        self.assertIn(BANNER, output)
        self.assertIn("NEIROLINKS Installer 0.1.8", output)

    def test_version_json_is_machine_clean(self):
        code, output = self.capture(["--json", "--version"], tty=True)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output), {"version": "0.1.8"})
        self.assertNotIn("\x1b[", output)
        self.assertNotIn(BANNER, output)

    def test_status_is_russian_without_banner(self):
        engine = StubEngine({"status": status_record()})
        code, output = self.capture(["status"], engine=engine)
        self.assertEqual(code, 0)
        self.assertIn("Объект:       05 31 Иволга 13", output)
        self.assertIn("Роль:         Котельная", output)
        self.assertIn("КОМПОНЕНТЫ", output)
        self.assertIn("Подпитка отопления", output)
        self.assertIn("Система готова", output)
        self.assertNotIn(BANNER, output)

    def test_tty_uses_color_and_no_color_disables_it(self):
        engine = StubEngine({"status": status_record()})
        _, colored = self.capture(["status"], engine=engine, tty=True)
        self.assertIn("\x1b[", colored)
        _, plain = self.capture(["--no-color", "status"], engine=engine, tty=True)
        self.assertNotIn("\x1b[", plain)

    def test_json_status_is_unchanged_clean_data(self):
        record = status_record()
        engine = StubEngine({"status": record})
        code, output = self.capture(["--json", "status"], engine=engine, tty=True)
        self.assertEqual(code, 0)
        parsed = json.loads(output)
        self.assertEqual(parsed, record)
        self.assertNotIn("\x1b[", output)
        self.assertNotIn("СОСТОЯНИЕ", output)

    def test_recovery_status_is_prominent_and_actionable(self):
        pending = {
            "component": "hhm",
            "command": "update",
            "error": "HHM runtime not loaded: HHM3_FSE/runtime_status",
            "backup": {"id": "abc123"},
        }
        engine = StubEngine({"status": status_record(pending)})
        code, output = self.capture(["status"], engine=engine)
        self.assertEqual(code, 1)
        self.assertIn("ТРЕБУЕТСЯ ВОССТАНОВЛЕНИЕ", output)
        self.assertIn("HHM не прошёл проверку после перезапуска", output)
        self.assertIn("nli rollback hhm", output)

    def test_check_is_human_russian(self):
        record = {
            "object": "05_31_Ivolga_13",
            "role": "boiler",
            "hostname": "wirenboard-ABF62SL",
            "command": "check",
            "component": "hhm",
            "from_version": "3.0.0-FSE+old",
            "to_version": "3.0.0-FSE+new",
            "preflight": "ok",
            "backup": None,
            "install": "not_run",
            "verify": "not_run",
            "rollback": "not_run",
            "final_status": "ok",
        }
        engine = StubEngine({"check": record})
        code, output = self.capture(["check", "hhm"], engine=engine)
        self.assertEqual(code, 0)
        self.assertIn("Проверка HHM", output)
        self.assertIn("Установлено:", output)
        self.assertIn("Доступно:", output)
        self.assertIn("РЕЗУЛЬТАТ: обновление разрешено", output)


if __name__ == "__main__":
    unittest.main()
