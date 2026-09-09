#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sprut Configurator v0.2.0

Windows utility for:
DISCOVER -> YAML validation -> DRY RUN -> APPLY -> VERIFY

Security:
- cid / token / serial are accepted only from a locally pasted WebUI WebSocket frame;
- the token is kept only in RAM;
- session data is never written to logs or files.
"""

from __future__ import annotations

import csv
import hashlib
import json
import queue
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import yaml
except ImportError as exc:
    raise SystemExit(
        "Не найден PyYAML. Запустите setup.bat или выполните: python -m pip install -r requirements.txt"
    ) from exc

try:
    from websockets.sync.client import connect as ws_connect
except ImportError as exc:
    raise SystemExit(
        "Не найден пакет websockets с sync API. Запустите setup.bat или выполните: "
        "python -m pip install -r requirements.txt"
    ) from exc


APP_NAME = "Sprut Configurator"
APP_VERSION = "0.2.2"
WS_URL = "wss://web.spruthub.ru/spruthub"
WS_SUBPROTOCOL = "json-rpc"
SUPPORTED_FORMAT_VERSION = 1

# Field-confirmed on current Sprut.hub:
# - names are truncated to 32 characters on update;
# - a dot directly after a leading numeric label is removed on round-trip.
SPRUT_NAME_MAX_LEN = 32
SPRUT_LEADING_NUMERIC_DOT_RE = re.compile(r"^\d+\.\s")

RPC_TIMEOUT_S = 15
OPEN_TIMEOUT_S = 15
CLOSE_TIMEOUT_S = 3


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SessionAuth:
    cid: str
    token: str
    serial: str


@dataclass
class PlanAction:
    status: str               # CHANGE / SAME / ERROR
    serial: str
    kind: str                 # accessory_name / room / service_name / validation
    current: str
    expected: str
    detail: str
    accessory_id: int | None = None
    service_id: int | None = None
    room_id: int | None = None
    service_type: str | None = None

    @property
    def is_change(self) -> bool:
        return self.status == "CHANGE"

    @property
    def is_error(self) -> bool:
        return self.status == "ERROR"


@dataclass
class DryRunResult:
    actions: list[PlanAction]
    errors: list[str]
    target_accessories: int

    @property
    def changes(self) -> list[PlanAction]:
        return [a for a in self.actions if a.is_change]

    @property
    def ok(self) -> bool:
        return not self.errors and not any(a.is_error for a in self.actions)


@dataclass
class VerifyRow:
    serial: str
    status: str  # PASSED / FAILED
    detail: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_local() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sha256_json(data: Any) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _string(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def parse_session_frame(text: str) -> SessionAuth:
    """
    Parse cid/token/serial from a copied outgoing WebUI WS frame.
    Prefer valid JSON, then use a conservative regex fallback for DevTools-like text.
    """
    text = text.strip()
    if not text:
        raise ValueError("Пустое сообщение.")

    obj = None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        pass

    if isinstance(obj, dict):
        cid = obj.get("cid")
        token = obj.get("token")
        serial = obj.get("serial")
        if all(isinstance(v, str) and v for v in (cid, token, serial)):
            return SessionAuth(cid=cid, token=token, serial=serial)

    def pick(name: str) -> str | None:
        patterns = [
            rf'["\']{re.escape(name)}["\']\s*:\s*["\']([^"\']+)["\']',
            rf'\b{re.escape(name)}\b\s*:\s*["\']([^"\']+)["\']',
        ]
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                return m.group(1)
        return None

    cid = pick("cid")
    token = pick("token")
    serial = pick("serial")
    if cid and token and serial:
        return SessionAuth(cid=cid, token=token, serial=serial)

    raise ValueError(
        "Не удалось извлечь cid/token/serial. Скопируйте целиком одно исходящее "
        "JSON-сообщение WebSocket Sprut WebUI."
    )


def validate_sprut_roundtrip_name(value: str, context: str) -> list[str]:
    errors: list[str] = []
    if len(value) > SPRUT_NAME_MAX_LEN:
        errors.append(
            f"{context}: имя длиной {len(value)} символов не round-trip совместимо со Sprut "
            f"(подтверждённый предел {SPRUT_NAME_MAX_LEN})."
        )
    if SPRUT_LEADING_NUMERIC_DOT_RE.match(value):
        errors.append(
            f"{context}: Sprut удаляет точку после ведущего цифрового номера: {value!r}. "
            "Используйте, например, '5 Свет ...'."
        )
    return errors


def validate_plan_structure(plan: Any) -> list[str]:
    errors: list[str] = []

    if not isinstance(plan, dict):
        return ["YAML должен содержать объект верхнего уровня."]

    if plan.get("format_version") != SUPPORTED_FORMAT_VERSION:
        errors.append(
            f"Неподдерживаемый format_version={plan.get('format_version')!r}; "
            f"ожидается {SUPPORTED_FORMAT_VERSION}."
        )

    accessories = plan.get("accessories")
    if not isinstance(accessories, list):
        errors.append("Поле accessories должно быть списком.")
        return errors

    seen_serials: set[str] = set()

    for idx, item in enumerate(accessories, start=1):
        prefix = f"accessories[{idx}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: должен быть объектом.")
            continue

        serial = item.get("serial")
        name = item.get("name")
        room = item.get("room")

        if not isinstance(serial, str) or not serial.strip():
            errors.append(f"{prefix}: отсутствует serial.")
        elif serial in seen_serials:
            errors.append(f"{prefix}: повтор serial {serial!r}.")
        else:
            seen_serials.add(serial)

        if not isinstance(name, str) or not name.strip():
            errors.append(f"{prefix}: отсутствует name.")
        else:
            errors.extend(validate_sprut_roundtrip_name(name, f"{prefix}.name"))

        if not isinstance(room, str) or not room.strip():
            errors.append(f"{prefix}: отсутствует room.")

        services = item.get("services", [])
        if not isinstance(services, list):
            errors.append(f"{prefix}: services должен быть списком.")
            continue

        seen_types: set[str] = set()
        for sidx, service in enumerate(services, start=1):
            sprefix = f"{prefix}.services[{sidx}]"
            if not isinstance(service, dict):
                errors.append(f"{sprefix}: должен быть объектом.")
                continue

            service_type = service.get("type")
            service_name = service.get("name")
            if not isinstance(service_type, str) or not service_type.strip():
                errors.append(f"{sprefix}: отсутствует type.")
                continue
            if service_type in seen_types:
                errors.append(
                    f"{sprefix}: тип {service_type!r} повторяется. "
                    "Без дополнительного устойчивого признака выбор сервиса неоднозначен."
                )
            seen_types.add(service_type)

            if not isinstance(service_name, str) or not service_name.strip():
                errors.append(f"{sprefix}: отсутствует name.")
            else:
                errors.extend(validate_sprut_roundtrip_name(service_name, f"{sprefix}.name"))

    return errors


def load_yaml_plan(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8-sig") as fh:
        data = yaml.safe_load(fh)
    errors = validate_plan_structure(data)
    if errors:
        raise ValueError("\n".join(errors))
    return data


def load_discover_json(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8-sig") as fh:
        data = json.load(fh)

    if not isinstance(data, dict):
        raise ValueError("DISCOVER JSON должен быть объектом.")
    if not isinstance(data.get("rooms"), list):
        raise ValueError("В DISCOVER JSON отсутствует список rooms.")
    if not isinstance(data.get("accessories"), list):
        raise ValueError("В DISCOVER JSON отсутствует список accessories.")
    return data


def _service_is_system(service: dict[str, Any]) -> bool:
    return bool(service.get("system")) or service.get("type") == "AccessoryInformation"


def make_dry_run(plan: dict[str, Any], discover: dict[str, Any]) -> DryRunResult:
    structural_errors = validate_plan_structure(plan)
    actions: list[PlanAction] = []
    errors: list[str] = list(structural_errors)

    rooms = discover.get("rooms", [])
    accessories = discover.get("accessories", [])

    rooms_by_name: dict[str, list[dict[str, Any]]] = {}
    for room in rooms:
        name = _string(room.get("name"))
        rooms_by_name.setdefault(name, []).append(room)

    accessories_by_serial: dict[str, list[dict[str, Any]]] = {}
    for accessory in accessories:
        serial = _string(accessory.get("serial"))
        accessories_by_serial.setdefault(serial, []).append(accessory)

    for target in plan.get("accessories", []):
        serial = target["serial"]
        expected_name = target["name"]
        expected_room = target["room"]

        matches = accessories_by_serial.get(serial, [])
        if len(matches) == 0:
            msg = f"{serial}: Accessory с таким SERIAL не найден."
            errors.append(msg)
            actions.append(PlanAction(
                status="ERROR", serial=serial, kind="validation",
                current="", expected="", detail=msg
            ))
            continue

        if len(matches) > 1:
            msg = f"{serial}: найдено {len(matches)} Accessory с одинаковым SERIAL."
            errors.append(msg)
            actions.append(PlanAction(
                status="ERROR", serial=serial, kind="validation",
                current=str(len(matches)), expected="1", detail=msg
            ))
            continue

        accessory = matches[0]
        a_id = accessory.get("id")

        current_name = _string(accessory.get("name"))
        actions.append(PlanAction(
            status="SAME" if current_name == expected_name else "CHANGE",
            serial=serial,
            kind="accessory_name",
            current=current_name,
            expected=expected_name,
            detail="Имя Accessory",
            accessory_id=a_id,
        ))

        room_matches = rooms_by_name.get(expected_room, [])
        current_room_id = accessory.get("roomId")
        current_room_name = next(
            (_string(r.get("name")) for r in rooms if r.get("id") == current_room_id),
            f"roomId={current_room_id}"
        )

        if len(room_matches) == 0:
            msg = f"{serial}: комната {expected_room!r} отсутствует в Sprut."
            errors.append(msg)
            actions.append(PlanAction(
                status="ERROR", serial=serial, kind="room",
                current=current_room_name, expected=expected_room, detail=msg,
                accessory_id=a_id,
            ))
        elif len(room_matches) > 1:
            msg = f"{serial}: имя комнаты {expected_room!r} неоднозначно ({len(room_matches)} совпадения)."
            errors.append(msg)
            actions.append(PlanAction(
                status="ERROR", serial=serial, kind="room",
                current=current_room_name, expected=expected_room, detail=msg,
                accessory_id=a_id,
            ))
        else:
            target_room_id = room_matches[0].get("id")
            actions.append(PlanAction(
                status="SAME" if current_room_id == target_room_id else "CHANGE",
                serial=serial,
                kind="room",
                current=current_room_name,
                expected=expected_room,
                detail="Комната Accessory",
                accessory_id=a_id,
                room_id=target_room_id,
            ))

        services = accessory.get("services", [])
        for service_target in target.get("services", []):
            service_type = service_target["type"]
            expected_service_name = service_target["name"]

            service_matches = [
                s for s in services
                if not _service_is_system(s) and s.get("type") == service_type
            ]

            if len(service_matches) == 0:
                msg = f"{serial}: Service type={service_type!r} не найден."
                errors.append(msg)
                actions.append(PlanAction(
                    status="ERROR", serial=serial, kind="service_name",
                    current="", expected=expected_service_name, detail=msg,
                    accessory_id=a_id, service_type=service_type,
                ))
                continue

            if len(service_matches) > 1:
                msg = (
                    f"{serial}: найдено {len(service_matches)} Service type={service_type!r}; "
                    "выбор по type неоднозначен."
                )
                errors.append(msg)
                actions.append(PlanAction(
                    status="ERROR", serial=serial, kind="service_name",
                    current=str(len(service_matches)), expected="1", detail=msg,
                    accessory_id=a_id, service_type=service_type,
                ))
                continue

            service = service_matches[0]
            current_service_name = _string(service.get("name"))
            actions.append(PlanAction(
                status="SAME" if current_service_name == expected_service_name else "CHANGE",
                serial=serial,
                kind="service_name",
                current=current_service_name,
                expected=expected_service_name,
                detail=f"Имя Service [{service_type}]",
                accessory_id=a_id,
                service_id=service.get("sId"),
                service_type=service_type,
            ))

    return DryRunResult(
        actions=actions,
        errors=errors,
        target_accessories=len(plan.get("accessories", [])),
    )


def verify_plan(plan: dict[str, Any], discover: dict[str, Any]) -> list[VerifyRow]:
    dry = make_dry_run(plan, discover)
    rows: list[VerifyRow] = []

    by_serial: dict[str, list[PlanAction]] = {}
    for action in dry.actions:
        by_serial.setdefault(action.serial, []).append(action)

    for target in plan.get("accessories", []):
        serial = target["serial"]
        serial_actions = by_serial.get(serial, [])

        if not serial_actions:
            rows.append(VerifyRow(serial, "FAILED", "Нет результатов проверки."))
            continue

        bad = [a for a in serial_actions if a.status in ("ERROR", "CHANGE")]
        if bad:
            details = []
            for action in bad:
                if action.status == "ERROR":
                    details.append(action.detail)
                else:
                    details.append(
                        f"{action.detail}: фактически={action.current!r}, ожидается={action.expected!r}"
                    )
            rows.append(VerifyRow(serial, "FAILED", "; ".join(details)))
        else:
            rows.append(VerifyRow(serial, "PASSED", "Имя, комната и Service соответствуют плану."))

    return rows


# ---------------------------------------------------------------------------
# Sprut WebSocket client
# ---------------------------------------------------------------------------

class SprutClient:
    def __init__(self, auth: SessionAuth, log: Callable[[str], None] | None = None):
        self.auth = auth
        self.log = log or (lambda _msg: None)
        self._request_counter = int(time.time() * 1000) % 2_000_000_000
        self._ws = None

    def __enter__(self):
        self._ws = ws_connect(
            WS_URL,
            subprotocols=[WS_SUBPROTOCOL],
            open_timeout=OPEN_TIMEOUT_S,
            close_timeout=CLOSE_TIMEOUT_S,
        )
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
        self._ws = None

    def _next_id(self) -> int:
        self._request_counter += 1
        return self._request_counter

    def rpc(self, params: dict[str, Any]) -> dict[str, Any]:
        if self._ws is None:
            raise RuntimeError("WebSocket не подключён.")

        request_id = self._next_id()
        payload = {
            "params": params,
            "id": request_id,
            "cid": self.auth.cid,
            "token": self.auth.token,
            "serial": self.auth.serial,
        }

        self._ws.send(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

        deadline = time.monotonic() + RPC_TIMEOUT_S
        while time.monotonic() < deadline:
            timeout = max(0.1, deadline - time.monotonic())
            try:
                raw = self._ws.recv(timeout=timeout)
            except TimeoutError:
                break

            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")

            try:
                message = json.loads(raw)
            except Exception:
                continue

            if message.get("id") != request_id:
                # Sprut also sends EVENT_UPDATE. Ignore them here.
                continue

            if "error" in message:
                raise RuntimeError(f"RPC error: {message['error']}")

            result = message.get("result")
            if not isinstance(result, dict):
                raise RuntimeError(f"RPC response без result: {message!r}")
            return result

        raise TimeoutError(f"Sprut RPC timeout, request id={request_id}.")

    @staticmethod
    def _find_collection(root: Any, entity: str) -> list[dict[str, Any]]:
        """
        Tolerant parser for room.list / accessory.list responses.
        """
        candidates: list[list[dict[str, Any]]] = []

        def walk(node: Any):
            if isinstance(node, list):
                if all(isinstance(x, dict) for x in node):
                    candidates.append(node)
                for x in node:
                    walk(x)
            elif isinstance(node, dict):
                for value in node.values():
                    walk(value)

        walk(root)

        if entity == "accessory":
            ranked = [
                c for c in candidates
                if c and any(("serial" in x or "services" in x) for x in c)
            ]
        else:
            ranked = [
                c for c in candidates
                if c
                and any("id" in x and "name" in x for x in c)
                and not any("services" in x or "serial" in x for x in c)
            ]

        if not ranked:
            # Empty collection fallback for a conventional shape.
            direct = root.get(entity, {}) if isinstance(root, dict) else {}
            if isinstance(direct, dict):
                value = direct.get("list")
                if isinstance(value, list):
                    return value
                if isinstance(value, dict):
                    for key in (entity + "s", "items", "data"):
                        if isinstance(value.get(key), list):
                            return value[key]
            raise RuntimeError(f"Не удалось распознать ответ {entity}.list.")

        ranked.sort(key=len, reverse=True)
        return ranked[0]

    def list_rooms(self) -> list[dict[str, Any]]:
        result = self.rpc({"room": {"list": {}}})
        return self._find_collection(result, "room")

    def list_accessories(self) -> list[dict[str, Any]]:
        result = self.rpc({
            "accessory": {
                "list": {
                    "expand": "services,characteristics"
                }
            }
        })
        return self._find_collection(result, "accessory")

    def discover(self) -> dict[str, Any]:
        rooms = self.list_rooms()
        accessories = self.list_accessories()

        services_count = sum(len(a.get("services", [])) for a in accessories)

        missing_serial = [
            a for a in accessories
            if not isinstance(a.get("serial"), str) or not a.get("serial")
        ]

        serial_counts: dict[str, int] = {}
        for accessory in accessories:
            serial = _string(accessory.get("serial"))
            if serial:
                serial_counts[serial] = serial_counts.get(serial, 0) + 1

        duplicate_serials = sorted(
            serial for serial, count in serial_counts.items() if count > 1
        )

        return {
            "meta": {
                "app": f"{APP_NAME} v{APP_VERSION}",
                "discovered_at_local": _now_local(),
                "ws_url": WS_URL,
                "rooms_count": len(rooms),
                "accessories_count": len(accessories),
                "services_count": services_count,
                "accessories_without_serial": len(missing_serial),
                "duplicate_serials": duplicate_serials,
            },
            "rooms": rooms,
            "accessories": accessories,
        }

    def update_accessory_name(self, accessory_id: int, name: str) -> None:
        self.rpc({"accessory": {"update": {"id": accessory_id, "name": name}}})

    def update_accessory_room(self, accessory_id: int, room_id: int) -> None:
        self.rpc({"accessory": {"update": {"id": accessory_id, "roomId": room_id}}})

    def update_service_name(self, accessory_id: int, service_id: int, name: str) -> None:
        self.rpc({"service": {"update": {"aId": accessory_id, "sId": service_id, "name": name}}})


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class ApplyConfirmDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, changes: int, accessories: int):
        super().__init__(parent)
        self.result = False
        self.title("Подтверждение APPLY")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        ttk.Label(
            self,
            text=(
                f"Будет выполнено {changes} изменений для {accessories} Accessory.\n\n"
                "Перед записью Configurator уже выполнил свежий DISCOVER и повторный DRY RUN.\n"
                "Для подтверждения введите APPLY:"
            ),
            justify="left",
        ).pack(padx=18, pady=(18, 8), anchor="w")

        self.var = tk.StringVar()
        entry = ttk.Entry(self, textvariable=self.var, width=30)
        entry.pack(padx=18, pady=6, fill="x")
        entry.focus_set()

        buttons = ttk.Frame(self)
        buttons.pack(padx=18, pady=(8, 18), fill="x")
        ttk.Button(buttons, text="Отмена", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Продолжить", command=self._accept).pack(side="right", padx=(0, 8))

        self.bind("<Return>", lambda _e: self._accept())
        self.bind("<Escape>", lambda _e: self.destroy())

    def _accept(self):
        if self.var.get().strip() == "APPLY":
            self.result = True
            self.destroy()
        else:
            messagebox.showerror("APPLY", "Введите ровно APPLY.", parent=self)

    def show(self) -> bool:
        self.wait_window()
        return self.result


class SprutConfiguratorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("1250x780")
        self.root.minsize(1050, 650)

        self.auth: SessionAuth | None = None
        self.discover_data: dict[str, Any] | None = None
        self.discover_source = ""
        self.plan: dict[str, Any] | None = None
        self.plan_path: str | None = None
        self.last_dry_run: DryRunResult | None = None
        self.last_dry_plan_hash: str | None = None

        self._build_ui()
        self._set_status("Готов.")

    # ---------- UI construction ----------

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")

        session_box = ttk.LabelFrame(top, text="1. Сессия Sprut WebUI", padding=8)
        session_box.pack(fill="x")

        ttk.Label(
            session_box,
            text="Вставьте локально одно исходящее WS JSON-сообщение Sprut WebUI. Токен после разбора очищается из поля и не сохраняется.",
        ).pack(anchor="w")

        line = ttk.Frame(session_box)
        line.pack(fill="x", pady=(5, 0))

        self.session_text = tk.Text(line, height=2, wrap="none")
        self.session_text.pack(side="left", fill="x", expand=True)

        # Explicit Windows clipboard handling. On some Tk/Windows combinations
        # the standard Ctrl+V binding in Text may not fire reliably.
        self.session_text.bind("<Control-v>", self._paste_session_clipboard)
        self.session_text.bind("<Control-V>", self._paste_session_clipboard)
        self.session_text.bind("<Shift-Insert>", self._paste_session_clipboard)

        ttk.Button(line, text="Вставить из буфера", command=self.paste_session_clipboard).pack(side="left", padx=(8, 0))
        ttk.Button(line, text="Принять сессию", command=self.accept_session).pack(side="left", padx=(8, 0))

        self.session_status = ttk.Label(session_box, text="Сессия не загружена")
        self.session_status.pack(anchor="w", pady=(4, 0))

        actions = ttk.Frame(top)
        actions.pack(fill="x", pady=(8, 0))

        ttk.Button(actions, text="DISCOVER", command=self.do_discover).pack(side="left")
        ttk.Button(actions, text="Открыть DISCOVER JSON", command=self.open_discover).pack(side="left", padx=4)
        ttk.Button(actions, text="Сохранить DISCOVER", command=self.save_discover).pack(side="left", padx=4)
        ttk.Button(actions, text="Экспорт CSV", command=self.export_csv).pack(side="left", padx=(4, 16))

        ttk.Separator(actions, orient="vertical").pack(side="left", fill="y", padx=4)

        ttk.Button(actions, text="Загрузить YAML", command=self.open_plan).pack(side="left", padx=4)
        ttk.Button(actions, text="DRY RUN", command=self.do_dry_run).pack(side="left", padx=4)

        self.apply_btn = ttk.Button(actions, text="APPLY", command=self.do_apply, state="disabled")
        self.apply_btn.pack(side="left", padx=4)

        ttk.Button(actions, text="VERIFY", command=self.do_verify).pack(side="left", padx=4)

        self.meta_label = ttk.Label(top, text="DISCOVER: —    YAML: —")
        self.meta_label.pack(anchor="w", pady=(6, 0))

        self.summary_label = ttk.Label(top, text="")
        self.summary_label.pack(anchor="w", pady=(2, 0))

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Plan tab
        plan_tab = ttk.Frame(notebook)
        notebook.add(plan_tab, text="План / DRY RUN / VERIFY")

        columns = ("status", "serial", "kind", "current", "expected", "detail")
        self.action_tree = ttk.Treeview(plan_tab, columns=columns, show="headings")
        headings = {
            "status": "Статус",
            "serial": "SERIAL",
            "kind": "Операция",
            "current": "Сейчас",
            "expected": "Должно быть",
            "detail": "Детали",
        }
        widths = {
            "status": 90, "serial": 260, "kind": 135,
            "current": 200, "expected": 220, "detail": 280,
        }
        for col in columns:
            self.action_tree.heading(col, text=headings[col])
            self.action_tree.column(col, width=widths[col], anchor="w")

        yscroll = ttk.Scrollbar(plan_tab, orient="vertical", command=self.action_tree.yview)
        self.action_tree.configure(yscrollcommand=yscroll.set)
        self.action_tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        self.action_tree.tag_configure("ERROR")
        self.action_tree.tag_configure("CHANGE")
        self.action_tree.tag_configure("SAME")
        self.action_tree.tag_configure("PASSED")
        self.action_tree.tag_configure("FAILED")

        # Discover tab
        discover_tab = ttk.Frame(notebook)
        notebook.add(discover_tab, text="DISCOVER")

        filter_line = ttk.Frame(discover_tab, padding=(0, 4))
        filter_line.pack(fill="x")
        ttk.Label(filter_line, text="Фильтр:").pack(side="left")
        self.filter_var = tk.StringVar()
        filter_entry = ttk.Entry(filter_line, textvariable=self.filter_var)
        filter_entry.pack(side="left", fill="x", expand=True, padx=6)
        self.filter_var.trace_add("write", lambda *_: self.refresh_discover_tree())

        dcols = ("serial", "name", "room", "model", "services")
        self.discover_tree = ttk.Treeview(discover_tab, columns=dcols, show="headings")
        for col, title, width in [
            ("serial", "SERIAL", 300),
            ("name", "Accessory", 240),
            ("room", "Комната", 180),
            ("model", "Model", 180),
            ("services", "Service types", 350),
        ]:
            self.discover_tree.heading(col, text=title)
            self.discover_tree.column(col, width=width, anchor="w")
        dscroll = ttk.Scrollbar(discover_tab, orient="vertical", command=self.discover_tree.yview)
        self.discover_tree.configure(yscrollcommand=dscroll.set)
        self.discover_tree.pack(side="left", fill="both", expand=True)
        dscroll.pack(side="right", fill="y")

        # Log
        log_box = ttk.LabelFrame(self.root, text="Журнал", padding=4)
        log_box.pack(fill="x", padx=8, pady=(0, 8))
        self.log_text = tk.Text(log_box, height=8, state="disabled", wrap="word")
        self.log_text.pack(fill="x")

        self.status_var = tk.StringVar()
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w")
        status_bar.pack(fill="x", side="bottom")

    # ---------- logging / status ----------

    def log(self, msg: str):
        line = f"{datetime.now().strftime('%H:%M:%S')}  {msg}\n"

        def append():
            self.log_text.configure(state="normal")
            self.log_text.insert("end", line)
            self.log_text.see("end")
            self.log_text.configure(state="disabled")

        if threading.current_thread() is threading.main_thread():
            append()
        else:
            self.root.after(0, append)

    def _set_status(self, text: str):
        self.status_var.set(text)

    def _set_busy(self, busy: bool, text: str = ""):
        self.root.config(cursor="wait" if busy else "")
        if text:
            self._set_status(text)

    def _run_worker(self, label: str, fn: Callable[[], Any], done: Callable[[Any], None]):
        self._set_busy(True, label)

        def worker():
            try:
                result = fn()
                self.root.after(0, lambda: finish_ok(result))
            except Exception as exc:
                self.root.after(0, lambda exc=exc: finish_error(exc))

        def finish_ok(result):
            self._set_busy(False, "Готов.")
            done(result)

        def finish_error(exc: Exception):
            self._set_busy(False, "Ошибка.")
            self.log(f"ОШИБКА: {exc}")
            messagebox.showerror(APP_NAME, str(exc), parent=self.root)

        threading.Thread(target=worker, daemon=True).start()

    # ---------- session ----------

    def _clipboard_text(self) -> str:
        # First try Tk clipboard API.
        try:
            value = self.root.clipboard_get()
            if isinstance(value, str):
                return value
        except tk.TclError:
            pass

        # Fallback to selection_get(CLIPBOARD), useful on some Tk builds.
        try:
            value = self.root.selection_get(selection="CLIPBOARD")
            if isinstance(value, str):
                return value
        except tk.TclError:
            pass

        raise ValueError("Не удалось прочитать текст из буфера обмена.")

    def paste_session_clipboard(self):
        try:
            raw = self._clipboard_text()
        except Exception as exc:
            messagebox.showerror("Буфер обмена", str(exc), parent=self.root)
            return

        self.session_text.delete("1.0", "end")
        self.session_text.insert("1.0", raw)
        self.session_text.mark_set("insert", "end-1c")
        self.session_text.see("insert")
        self.session_text.focus_set()
        self.log(f"Текст из буфера вставлен в поле сессии: {len(raw)} символов.")

    def _paste_session_clipboard(self, _event=None):
        self.paste_session_clipboard()
        return "break"

    def accept_session(self):
        raw = self.session_text.get("1.0", "end-1c").strip()
        try:
            self.auth = parse_session_frame(raw)
        except Exception as exc:
            messagebox.showerror("Сессия", str(exc), parent=self.root)
            return

        # Never keep the raw frame in the widget after parsing.
        self.session_text.delete("1.0", "end")
        self.session_status.configure(text="Сессия загружена в память. token/cid/serial не логируются и не сохраняются.")
        self.log("Сессия Sprut WebUI принята локально; секретные поля скрыты.")
        self._update_apply_state()

    # ---------- discover ----------

    def do_discover(self):
        if not self.auth:
            messagebox.showwarning(
                "DISCOVER",
                "Сначала вставьте и примите исходящее WS-сообщение Sprut WebUI.",
                parent=self.root,
            )
            return

        auth = self.auth

        def work():
            with SprutClient(auth, self.log) as client:
                return client.discover()

        self._run_worker("DISCOVER: чтение Sprut...", work, self._after_discover)

    def _after_discover(self, data: dict[str, Any]):
        self.discover_data = data
        self.discover_source = "LIVE"
        self.last_dry_run = None
        self.last_dry_plan_hash = None
        self._update_apply_state()
        self.refresh_discover_tree()
        self._update_meta()
        meta = data["meta"]
        self.log(
            "DISCOVER завершён: "
            f"rooms={meta['rooms_count']}, accessories={meta['accessories_count']}, "
            f"services={meta['services_count']}, missing_serial={meta['accessories_without_serial']}, "
            f"duplicate_serials={len(meta['duplicate_serials'])}."
        )

    def open_discover(self):
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Открыть DISCOVER JSON",
            filetypes=[("JSON", "*.json"), ("Все файлы", "*.*")],
        )
        if not path:
            return

        try:
            data = load_discover_json(path)
        except Exception as exc:
            messagebox.showerror("DISCOVER", str(exc), parent=self.root)
            return

        self.discover_data = data
        self.discover_source = f"FILE: {Path(path).name}"
        self.last_dry_run = None
        self.last_dry_plan_hash = None
        self._update_apply_state()
        self.refresh_discover_tree()
        self._update_meta()
        self.log(f"Открыт DISCOVER JSON: {path}")

    def save_discover(self):
        if not self.discover_data:
            messagebox.showwarning("DISCOVER", "Сначала выполните или откройте DISCOVER.", parent=self.root)
            return

        default_name = "sprut_discover_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Сохранить DISCOVER",
            defaultextension=".json",
            initialfile=default_name,
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return

        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.discover_data, fh, ensure_ascii=False, indent=2)

        self.log(f"DISCOVER сохранён: {path}")

    def export_csv(self):
        if not self.discover_data:
            messagebox.showwarning("CSV", "Сначала выполните или откройте DISCOVER.", parent=self.root)
            return

        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Экспорт DISCOVER CSV",
            defaultextension=".csv",
            initialfile="sprut_discover.csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return

        rooms = {r.get("id"): _string(r.get("name")) for r in self.discover_data["rooms"]}

        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh, delimiter=";")
            writer.writerow([
                "SERIAL", "ACCESSORY_ID", "ACCESSORY_NAME", "ROOM",
                "MODEL", "SERVICE_ID", "SERVICE_TYPE", "SERVICE_NAME", "SYSTEM",
            ])

            for accessory in self.discover_data["accessories"]:
                services = accessory.get("services") or [None]
                for service in services:
                    writer.writerow([
                        accessory.get("serial", ""),
                        accessory.get("id", ""),
                        accessory.get("name", ""),
                        rooms.get(accessory.get("roomId"), ""),
                        accessory.get("model", ""),
                        "" if service is None else service.get("sId", ""),
                        "" if service is None else service.get("type", ""),
                        "" if service is None else service.get("name", ""),
                        "" if service is None else bool(service.get("system")),
                    ])

        self.log(f"CSV экспортирован: {path}")

    def refresh_discover_tree(self):
        tree = self.discover_tree
        for item in tree.get_children():
            tree.delete(item)

        if not self.discover_data:
            return

        needle = self.filter_var.get().strip().lower()
        rooms = {r.get("id"): _string(r.get("name")) for r in self.discover_data["rooms"]}

        for accessory in self.discover_data["accessories"]:
            service_types = ", ".join(
                _string(s.get("type"))
                for s in accessory.get("services", [])
                if not _service_is_system(s)
            )

            values = (
                _string(accessory.get("serial")),
                _string(accessory.get("name")),
                rooms.get(accessory.get("roomId"), ""),
                _string(accessory.get("model")),
                service_types,
            )

            if needle and needle not in " ".join(values).lower():
                continue

            tree.insert("", "end", values=values)

    # ---------- plan ----------

    def open_plan(self):
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Открыть sprut_plan.yaml",
            filetypes=[("YAML", "*.yaml *.yml"), ("Все файлы", "*.*")],
        )
        if not path:
            return

        try:
            plan = load_yaml_plan(path)
        except Exception as exc:
            messagebox.showerror("YAML", str(exc), parent=self.root)
            return

        self.plan = plan
        self.plan_path = path
        self.last_dry_run = None
        self.last_dry_plan_hash = None
        self._update_apply_state()
        self._update_meta()
        self._clear_action_tree()
        self.summary_label.configure(
            text=f"YAML валиден: {len(plan.get('accessories', []))} Accessory."
        )
        self.log(f"YAML загружен и структурно валиден: {path}")

    def do_dry_run(self):
        if not self.plan:
            messagebox.showwarning("DRY RUN", "Сначала загрузите YAML.", parent=self.root)
            return
        if not self.discover_data:
            messagebox.showwarning("DRY RUN", "Сначала выполните или откройте DISCOVER.", parent=self.root)
            return

        result = make_dry_run(self.plan, self.discover_data)
        self.last_dry_run = result
        self.last_dry_plan_hash = _sha256_json(self.plan)
        self._render_dry_run(result)
        self._update_apply_state()

        if result.ok:
            self.log(
                f"DRY RUN PASSED: targets={result.target_accessories}, "
                f"changes={len(result.changes)}, errors=0."
            )
            for action in result.changes:
                self.log(
                    f"DRY CHANGE: {action.serial} — {action.detail}: "
                    f"{action.current!r} -> {action.expected!r}"
                )
        else:
            self.log(
                f"DRY RUN FAILED: targets={result.target_accessories}, "
                f"changes={len(result.changes)}, errors={len(result.errors)}."
            )

    def _render_dry_run(self, result: DryRunResult):
        self._clear_action_tree()
        for action in result.actions:
            self.action_tree.insert(
                "", "end",
                values=(
                    action.status,
                    action.serial,
                    action.kind,
                    action.current,
                    action.expected,
                    action.detail,
                ),
                tags=(action.status,),
            )

        verdict = "PASSED" if result.ok else "FAILED"
        self.summary_label.configure(
            text=(
                f"DRY RUN {verdict}: {result.target_accessories} Accessory; "
                f"{len(result.changes)} изменений; {len(result.errors)} ошибок."
            )
        )

    def _clear_action_tree(self):
        for item in self.action_tree.get_children():
            self.action_tree.delete(item)

    # ---------- apply ----------

    def _update_apply_state(self):
        enabled = (
            self.auth is not None
            and self.plan is not None
            and self.last_dry_run is not None
            and self.last_dry_run.ok
            and self.last_dry_plan_hash == _sha256_json(self.plan)
        )
        self.apply_btn.configure(state="normal" if enabled else "disabled")

    def do_apply(self):
        if not self.auth or not self.plan or not self.last_dry_run or not self.last_dry_run.ok:
            return

        if self.last_dry_plan_hash != _sha256_json(self.plan):
            messagebox.showerror("APPLY", "YAML изменился после DRY RUN. Выполните DRY RUN заново.", parent=self.root)
            return

        auth = self.auth
        plan = self.plan

        # Preflight is read-only and happens before the confirmation dialog.
        def preflight_work():
            with SprutClient(auth, self.log) as client:
                fresh = client.discover()
            dry = make_dry_run(plan, fresh)
            return fresh, dry

        def after_preflight(payload):
            fresh, dry = payload
            self.discover_data = fresh
            self.discover_source = "LIVE preflight"
            self.last_dry_run = dry
            self.last_dry_plan_hash = _sha256_json(plan)
            self._render_dry_run(dry)
            self.refresh_discover_tree()
            self._update_meta()

            if not dry.ok:
                self._update_apply_state()
                messagebox.showerror(
                    "APPLY",
                    f"Свежий preflight DRY RUN не прошёл: {len(dry.errors)} ошибок. Запись отменена.",
                    parent=self.root,
                )
                return

            if not dry.changes:
                messagebox.showinfo("APPLY", "Изменений нет: Sprut уже соответствует YAML.", parent=self.root)
                return

            changed_accessories = len({a.serial for a in dry.changes})
            dialog = ApplyConfirmDialog(self.root, len(dry.changes), changed_accessories)
            if not dialog.show():
                self.log("APPLY отменён пользователем.")
                return

            self._apply_after_confirm(auth, plan, dry)

        self._run_worker("APPLY preflight: свежий DISCOVER...", preflight_work, after_preflight)

    def _apply_after_confirm(self, auth: SessionAuth, plan: dict[str, Any], dry: DryRunResult):
        changes = list(dry.changes)

        def work():
            completed = 0
            with SprutClient(auth, self.log) as client:
                for action in changes:
                    if action.kind == "accessory_name":
                        client.update_accessory_name(action.accessory_id, action.expected)
                    elif action.kind == "room":
                        client.update_accessory_room(action.accessory_id, action.room_id)
                    elif action.kind == "service_name":
                        client.update_service_name(action.accessory_id, action.service_id, action.expected)
                    else:
                        raise RuntimeError(f"Неизвестный action kind={action.kind!r}")

                    completed += 1
                    self.log(
                        f"APPLY {completed}/{len(changes)}: {action.serial} — "
                        f"{action.detail}: {action.current!r} -> {action.expected!r}"
                    )

                # Automatic fresh state for VERIFY.
                fresh = client.discover()
            return fresh, completed

        def done(payload):
            fresh, completed = payload
            self.discover_data = fresh
            self.discover_source = "LIVE after APPLY"
            self.last_dry_run = None
            self.last_dry_plan_hash = None
            self._update_apply_state()
            self.refresh_discover_tree()
            self._update_meta()
            self.log(f"APPLY завершён: выполнено {completed} RPC-изменений. Запускаю VERIFY.")
            self._render_verify(verify_plan(plan, fresh))

        self._run_worker("APPLY: запись в Sprut...", work, done)

    # ---------- verify ----------

    def do_verify(self):
        if not self.plan:
            messagebox.showwarning("VERIFY", "Сначала загрузите YAML.", parent=self.root)
            return

        if self.auth:
            auth = self.auth
            plan = self.plan

            def work():
                with SprutClient(auth, self.log) as client:
                    return client.discover()

            def done(fresh):
                self.discover_data = fresh
                self.discover_source = "LIVE VERIFY"
                self.last_dry_run = None
                self.last_dry_plan_hash = None
                self._update_apply_state()
                self.refresh_discover_tree()
                self._update_meta()
                self._render_verify(verify_plan(plan, fresh))

            self._run_worker("VERIFY: свежий DISCOVER...", work, done)
            return

        if not self.discover_data:
            messagebox.showwarning(
                "VERIFY",
                "Нет сессии для свежего DISCOVER и нет открытого DISCOVER JSON.",
                parent=self.root,
            )
            return

        self._render_verify(verify_plan(self.plan, self.discover_data))

    def _render_verify(self, rows: list[VerifyRow]):
        self._clear_action_tree()

        passed = 0
        failed = 0
        for row in rows:
            if row.status == "PASSED":
                passed += 1
            else:
                failed += 1

            self.action_tree.insert(
                "", "end",
                values=(row.status, row.serial, "VERIFY", "", "", row.detail),
                tags=(row.status,),
            )

        verdict = "PASSED" if failed == 0 else "FAILED"
        self.summary_label.configure(
            text=f"VERIFY {verdict}: PASSED={passed}, FAILED={failed}."
        )
        self.log(f"VERIFY {verdict}: PASSED={passed}, FAILED={failed}.")
        if failed:
            for row in rows:
                if row.status == "FAILED":
                    self.log(f"VERIFY FAILED ITEM: {row.serial} — {row.detail}")

    # ---------- meta ----------

    def _update_meta(self):
        discover_text = "—"
        if self.discover_data:
            meta = self.discover_data.get("meta", {})
            discover_text = (
                f"{self.discover_source}; rooms={len(self.discover_data.get('rooms', []))}; "
                f"accessories={len(self.discover_data.get('accessories', []))}; "
                f"services={meta.get('services_count', '?')}"
            )

        plan_text = "—"
        if self.plan:
            plan_text = f"{Path(self.plan_path).name if self.plan_path else 'YAML'}; targets={len(self.plan.get('accessories', []))}"

        self.meta_label.configure(text=f"DISCOVER: {discover_text}    YAML: {plan_text}")


def main():
    root = tk.Tk()
    app = SprutConfiguratorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
