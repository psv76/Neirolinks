import argparse
import json
import os
import sys
from . import __version__
from .core import Engine
from .firmware import Firmware
from .layout import load_config
from .util import Error


BANNER = r""" _   _ _     ___
| \\ | | |   |_ _|
|  \\| | |    | |
| |\\  | |___ | |
|_| \\_|_____|___|"""

ANSI = {
    "reset": "\\033[0m",
    "bold": "\\033[1m",
    "dim": "\\033[2m",
    "red": "\\033[31m",
    "green": "\\033[32m",
    "yellow": "\\033[33m",
    "cyan": "\\033[36m",
}


def paint(text, style, enabled):
    return ANSI[style] + text + ANSI["reset"] if enabled else text


def human_object(value):
    return str(value or "—").replace("_", " ")


def human_role(value):
    return {"boiler": "Котельная", "gazebo": "Беседка"}.get(value, str(value or "—"))


def component_name(value):
    return {
        "hhm": "HHM",
        "pressure_makeup": "Подпитка отопления",
    }.get(value, str(value or "—"))


def operation_name(value):
    return {
        "status": "Состояние",
        "check": "Проверка",
        "verify": "Проверка состояния",
        "update": "Обновление",
        "rollback": "Восстановление",
        "firmware": "Прошивка",
    }.get(value, str(value or "—"))


def state_name(value):
    return {
        "update_ok": "Обновлено успешно",
        "rollback_ok": "Восстановлено успешно",
        "baseline_restored": "Базовая версия восстановлена",
        "ok": "Успешно",
        "failed": "Ошибка",
        "partial_failure": "Частичная ошибка",
        "recovery_required": "Требуется восстановление",
        "rolled_back": "Выполнен автоматический откат",
        "unavailable": "Недоступно",
    }.get(value, str(value or "Неизвестно"))


def reason_name(value):
    text = str(value or "Причина не указана")
    if text.startswith("HHM runtime not loaded:"):
        return "HHM не прошёл проверку после перезапуска"
    if "journal reports errors" in text:
        return "Обнаружены ошибки в журнале wb-rules"
    return text


def status_mark(ok, color):
    return paint("✓", "green", color) if ok else paint("✗", "red", color)


def heading(text, color):
    return paint(text, "cyan", color)


def dim(text, color):
    return paint(text, "dim", color)


def show_version(json_mode=False, color=False):
    if json_mode:
        print(json.dumps({"version": __version__}, ensure_ascii=False))
        return
    print(paint(BANNER, "green", color))
    print()
    print("NEIROLINKS Installer " + paint(__version__, "green", color))


def render_status(result, color):
    print("NLI " + paint(__version__, "green", color) + " · NEIROLINKS Installer")
    print()
    print(f"Объект:       {human_object(result.get('object'))}")
    print(f"Контроллер:   {result.get('hostname') or '—'}")
    print(f"Роль:         {human_role(result.get('role'))}")

    print()
    print(heading("КОМПОНЕНТЫ", color))
    components = result.get("components", {})
    if not components:
        print("  " + dim("Нет зарегистрированных компонентов", color))
    for name, state in components.items():
        label = component_name(name)
        if state:
            version = state.get("manifest", {}).get("version", "—")
            last = state_name(state.get("last_result"))
            print()
            print(f"  {status_mark(True, color)} {paint(label, 'cyan', color)}")
            print(f"    Версия:       {paint(str(version), 'green', color)}")
            print(f"    Состояние:    {paint(last, 'green', color)}")
        else:
            print()
            print(f"  {paint('•', 'yellow', color)} {paint(label, 'cyan', color)}")
            print("    " + paint("Установленная версия ещё не зарегистрирована; требуется проверка baseline", "yellow", color))

    history = result.get("last_operations", {})
    if history:
        print()
        print(heading("ПОСЛЕДНИЕ ОПЕРАЦИИ", color))
        width = max(len(component_name(name)) for name in history)
        for name, record in history.items():
            label = component_name(name)
            op = operation_name(record.get("command"))
            ok = record.get("final_status") == "ok"
            final = state_name(record.get("final_status"))
            final = paint(final, "green" if ok else "red", color)
            print(f"  {status_mark(ok, color)} {label:<{width}}   {op:<18} {final}")

    print()
    print(heading("СОСТОЯНИЕ", color))
    pending = result.get("pending")
    if pending:
        print()
        print("  " + paint("✗ ТРЕБУЕТСЯ ВОССТАНОВЛЕНИЕ", "red", color))
        print()
        component = pending.get("component")
        print(f"  Компонент:       {component_name(component)}")
        print(f"  Операция:        {operation_name(pending.get('command'))}")
        print(f"  Причина:         {reason_name(pending.get('error') or pending.get('rollback_error'))}")
        backup = pending.get("backup") or {}
        if backup.get("id"):
            print(f"  Резервная копия: {backup['id']}")
        if component:
            print()
            print("  Следующее действие:")
            print("    " + paint("nli rollback " + component, "yellow", color))
    else:
        print()
        print("  " + paint("✓ Система готова", "green", color))
        print("  " + dim("Незавершённых операций нет.", color))


def render_journal(result, color):
    events = []
    for attempt in result.get("verification_attempts", []):
        events.extend(attempt.get("journal", []))
    if not events:
        return
    print()
    print(heading("ДИАГНОСТИКА ОБЩЕЙ СРЕДЫ", color))
    for event in events:
        fatal = bool(event.get("fatal"))
        marker = paint("✗", "red", color) if fatal else paint("⚠", "yellow", color)
        category = event.get("category", "journal")
        message = event.get("message", "")
        print(f"  {marker} {category}: {message}")


def render_check(result, color):
    label = component_name(result.get("component"))
    print(heading("Проверка " + label, color))
    print()
    if result.get("from_version"):
        print(f"Установлено:    {result['from_version']}")
    if result.get("to_version"):
        print(f"Для установки:  {result['to_version']}")
    print()
    if result.get("preflight") == "ok":
        print("  " + status_mark(True, color) + " Предварительная проверка пройдена")
    if result.get("final_status") == "ok":
        print("  " + status_mark(True, color) + " Пакет обновления проверен")
        print()
        print(paint("РЕЗУЛЬТАТ: обновление разрешено", "green", color))
    else:
        print("  " + status_mark(False, color) + " " + reason_name(result.get("error")))
        print()
        print(paint("РЕЗУЛЬТАТ: обновление заблокировано", "red", color))


def render_verify(result, color):
    label = component_name(result.get("component"))
    print(heading("Проверка состояния " + label, color))
    print()
    if result.get("from_version"):
        print(f"Версия: {result['from_version']}")
    print()
    ok = result.get("final_status") == "ok"
    if ok:
        print("  " + status_mark(True, color) + " Файлы, службы и runtime прошли проверку")
        print()
        print(paint("РЕЗУЛЬТАТ: исправен", "green", color))
    else:
        print("  " + status_mark(False, color) + " " + reason_name(result.get("error")))
        print()
        print(paint("РЕЗУЛЬТАТ: требуется проверка", "red", color))
    render_journal(result, color)


def render_mutation(result, color):
    command = result.get("command")
    label = component_name(result.get("component"))
    title = ("Обновление " if command == "update" else "Восстановление ") + label
    print(heading(title, color))
    print()
    if result.get("from_version"):
        print(f"Исходная версия: {result['from_version']}")
    if result.get("to_version"):
        print(f"Целевая версия:  {result['to_version']}")
    print()

    steps = [
        ("preflight", "Предварительная проверка"),
        ("backup", "Резервная копия"),
        ("install", "Установка"),
        ("verify", "Проверка после запуска"),
        ("rollback", "Автоматический откат"),
    ]
    for key, label_text in steps:
        value = result.get(key)
        if value in (None, "not_run"):
            continue
        ok = value == "ok" or (key == "backup" and isinstance(value, dict))
        if value == "running":
            marker = paint("…", "yellow", color)
            detail = paint("выполняется", "yellow", color)
        elif ok:
            marker = status_mark(True, color)
            detail = paint("успешно", "green", color)
        else:
            marker = status_mark(False, color)
            detail = paint(state_name(value), "red", color)
        if key == "backup" and isinstance(value, dict) and value.get("id"):
            detail += " · " + value["id"]
        print(f"  {marker} {label_text}: {detail}")

    render_journal(result, color)
    print()
    final = result.get("final_status")
    if final == "ok":
        print(paint("РЕЗУЛЬТАТ: успешно", "green", color))
    elif final == "rolled_back":
        print(paint("РЕЗУЛЬТАТ: обновление отменено, предыдущая версия восстановлена", "yellow", color))
    elif final == "recovery_required" or result.get("pending"):
        print(paint("РЕЗУЛЬТАТ: требуется восстановление", "red", color))
    else:
        print(paint("РЕЗУЛЬТАТ: ошибка", "red", color))
        if result.get("error"):
            print("Причина: " + reason_name(result["error"]))


def render_generic(result, color):
    print("NLI " + paint(__version__, "green", color))
    for key, label in (
        ("object", "Объект"), ("role", "Роль"), ("hostname", "Контроллер"),
        ("component", "Компонент"), ("from_version", "Исходная версия"),
        ("to_version", "Целевая версия"), ("error", "Ошибка"), ("reason", "Причина"),
    ):
        if result.get(key) is not None:
            value = result[key]
            if key == "object":
                value = human_object(value)
            elif key == "role":
                value = human_role(value)
            elif key == "component":
                value = component_name(value)
            print(f"{label}: {value}")
    print()
    ok = result.get("final_status") == "ok"
    print(paint("РЕЗУЛЬТАТ: " + ("успешно" if ok else state_name(result.get("final_status"))),
                "green" if ok else "red", color))


def render_human(result, color):
    command = result.get("command")
    if command == "status":
        render_status(result, color)
    elif command == "check":
        render_check(result, color)
    elif command == "verify":
        render_verify(result, color)
    elif command in ("update", "rollback"):
        render_mutation(result, color)
    else:
        render_generic(result, color)


def main(argv=None, engine=None):
    parser = argparse.ArgumentParser(prog="nli", description="NEIROLINKS Installer / Updater")
    parser.add_argument("--version", action="store_true", help="Показать версию и выйти")
    parser.add_argument("--config", help="Persistent config under /mnt/data/etc/neiro/nli/")
    parser.add_argument("--json", action="store_true", help="Emit complete audit record, including read-only operations")
    parser.add_argument("--no-color", action="store_true", help="Отключить ANSI-цвета")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status")
    for command in ("check", "update", "verify", "rollback"):
        sub.add_parser(command).add_argument("component")
    sub.add_parser("firmware").add_argument("action", choices=("check", "update", "recover"))
    args = parser.parse_args(argv)

    color = (not args.no_color and not args.json and not os.environ.get("NO_COLOR")
             and bool(getattr(sys.stdout, "isatty", lambda: False)()))

    if args.version:
        show_version(args.json, color)
        return 0
    if args.command is None:
        parser.error("the following arguments are required: command")

    try:
        e = engine or Engine(load_config(args.config))
        if args.command == "firmware":
            result = Firmware(e).execute(args.action)
        elif args.command in ("update", "rollback"):
            result = e.mutate(args.command, args.component)
        else:
            result = e.read_operation(args.command, getattr(args, "component", None))
    except (Error, OSError, ValueError, KeyError, TypeError) as exc:
        result = {"final_status": "failed", "error": str(exc), "command": args.command,
                  "component": getattr(args, "component", None)}

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        render_human(result, color)
    return 0 if result["final_status"] == "ok" else (3 if result["final_status"] == "unavailable" else 1)


if __name__ == "__main__":
    sys.exit(main())
