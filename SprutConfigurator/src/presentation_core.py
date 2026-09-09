from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

SUPPORTED_FORMAT_VERSION = 2


@dataclass
class PresentationAction:
    status: str          # SAME / CHANGE / ERROR
    serial: str
    kind: str            # service_visible / characteristic_status_visible / bridge_alice
    current: Any
    expected: Any
    detail: str
    accessory_id: int | None = None
    service_id: int | None = None
    characteristic_id: int | None = None
    service_type: str | None = None
    characteristic_type: str | None = None

    @property
    def is_change(self) -> bool:
        return self.status == "CHANGE"

    @property
    def is_error(self) -> bool:
        return self.status == "ERROR"


@dataclass
class PresentationDiff:
    actions: list[PresentationAction]
    errors: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors and not any(a.is_error for a in self.actions)

    @property
    def changes(self) -> list[PresentationAction]:
        return [a for a in self.actions if a.is_change]


def _string(value: Any) -> str:
    return "" if value is None else str(value)


def _service_is_system(service: dict[str, Any]) -> bool:
    return bool(service.get("system")) or service.get("type") == "AccessoryInformation"


def validate_presentation_plan(plan: Any) -> list[str]:
    """Validate only the v2 presentation extension.

    Base v1 fields (serial/name/room/service type/name) remain owned by the
    Configurator's existing validation. This function validates the new
    presentation fields and is intentionally strict.
    """
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["YAML должен содержать объект верхнего уровня."]

    if plan.get("format_version") != SUPPORTED_FORMAT_VERSION:
        errors.append(
            f"Presentation contract ожидает format_version={SUPPORTED_FORMAT_VERSION}, "
            f"получено {plan.get('format_version')!r}."
        )

    accessories = plan.get("accessories")
    if not isinstance(accessories, list):
        errors.append("Поле accessories должно быть списком.")
        return errors

    for idx, item in enumerate(accessories, start=1):
        prefix = f"accessories[{idx}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: должен быть объектом.")
            continue

        bridge = item.get("bridge")
        if bridge is not None:
            if not isinstance(bridge, dict):
                errors.append(f"{prefix}.bridge: должен быть объектом.")
            else:
                unknown = sorted(set(bridge) - {"alice"})
                if unknown:
                    errors.append(
                        f"{prefix}.bridge: неизвестные поля: {', '.join(unknown)}."
                    )
                if "alice" in bridge and not isinstance(bridge["alice"], bool):
                    errors.append(f"{prefix}.bridge.alice: ожидается true/false.")

        services = item.get("services", [])
        if not isinstance(services, list):
            continue

        for sidx, service in enumerate(services, start=1):
            sprefix = f"{prefix}.services[{sidx}]"
            if not isinstance(service, dict):
                continue

            if "visible" in service and not isinstance(service["visible"], bool):
                errors.append(f"{sprefix}.visible: ожидается true/false.")

            status = service.get("status")
            if status is not None:
                if not isinstance(status, dict):
                    errors.append(
                        f"{sprefix}.status: ожидается объект "
                        "{CharacteristicType: true|false}."
                    )
                else:
                    for ctype, desired in status.items():
                        if not isinstance(ctype, str) or not ctype.strip():
                            errors.append(
                                f"{sprefix}.status: имя Characteristic должно быть непустой строкой."
                            )
                        if not isinstance(desired, bool):
                            errors.append(
                                f"{sprefix}.status[{ctype!r}]: ожидается true/false."
                            )

    return errors


def characteristic_type(characteristic: dict[str, Any]) -> str:
    """Return the best stable characteristic type from DISCOVER.

    Current Sprut DISCOVER has been observed with type information in control.type.
    Some dumps may also expose type directly on the Characteristic. We support
    both read shapes without inventing a write contract.
    """
    direct = characteristic.get("type")
    if isinstance(direct, str) and direct:
        return direct

    control = characteristic.get("control")
    if isinstance(control, dict):
        value = control.get("type")
        if isinstance(value, str) and value:
            return value

    return ""


def _unique_accessory(
    serial: str,
    accessories_by_serial: dict[str, list[dict[str, Any]]],
    actions: list[PresentationAction],
    errors: list[str],
) -> dict[str, Any] | None:
    matches = accessories_by_serial.get(serial, [])
    if len(matches) == 1:
        return matches[0]

    if not matches:
        msg = f"{serial}: Accessory с таким SERIAL не найден."
    else:
        msg = f"{serial}: найдено {len(matches)} Accessory с одинаковым SERIAL."
    errors.append(msg)
    actions.append(PresentationAction(
        status="ERROR",
        serial=serial,
        kind="validation",
        current=len(matches),
        expected=1,
        detail=msg,
    ))
    return None


def _unique_service(
    serial: str,
    accessory: dict[str, Any],
    service_type: str,
    actions: list[PresentationAction],
    errors: list[str],
) -> dict[str, Any] | None:
    matches = [
        s for s in accessory.get("services", [])
        if isinstance(s, dict)
        and not _service_is_system(s)
        and s.get("type") == service_type
    ]
    if len(matches) == 1:
        return matches[0]

    if not matches:
        msg = f"{serial}: Service type={service_type!r} не найден."
    else:
        msg = (
            f"{serial}: найдено {len(matches)} Service type={service_type!r}; "
            "выбор по type неоднозначен."
        )
    errors.append(msg)
    actions.append(PresentationAction(
        status="ERROR",
        serial=serial,
        kind="validation",
        current=len(matches),
        expected=1,
        detail=msg,
        accessory_id=accessory.get("id"),
        service_type=service_type,
    ))
    return None


def _unique_characteristic(
    serial: str,
    accessory: dict[str, Any],
    service: dict[str, Any],
    service_type: str,
    ctype: str,
    actions: list[PresentationAction],
    errors: list[str],
) -> dict[str, Any] | None:
    matches = [
        c for c in service.get("characteristics", [])
        if isinstance(c, dict) and characteristic_type(c) == ctype
    ]
    if len(matches) == 1:
        return matches[0]

    if not matches:
        msg = (
            f"{serial}: Characteristic type={ctype!r} "
            f"в Service {service_type!r} не найден."
        )
    else:
        msg = (
            f"{serial}: найдено {len(matches)} Characteristic type={ctype!r} "
            f"в Service {service_type!r}; выбор неоднозначен."
        )
    errors.append(msg)
    actions.append(PresentationAction(
        status="ERROR",
        serial=serial,
        kind="validation",
        current=len(matches),
        expected=1,
        detail=msg,
        accessory_id=accessory.get("id"),
        service_id=service.get("sId"),
        service_type=service_type,
        characteristic_type=ctype,
    ))
    return None


AliceStateGetter = Callable[[dict[str, Any]], bool | None]


def make_presentation_diff(
    plan: dict[str, Any],
    discover: dict[str, Any],
    *,
    alice_state_getter: AliceStateGetter | None = None,
) -> PresentationDiff:
    """Build read-only desired/current diff for v2 presentation policy.

    No write RPC is encoded here. The diff is safe to use before the WebUI write
    frames are field-confirmed.

    Alice is deliberately adapter-based because its runtime storage path has not
    yet been confirmed. Without a getter, a requested bridge.alice policy is an
    ERROR, preventing a false-success DRY RUN.
    """
    errors = validate_presentation_plan(plan)
    actions: list[PresentationAction] = []

    accessories = discover.get("accessories", [])
    if not isinstance(accessories, list):
        msg = "DISCOVER: accessories должен быть списком."
        return PresentationDiff(
            actions=[PresentationAction("ERROR", "", "validation", "", "", msg)],
            errors=errors + [msg],
        )

    accessories_by_serial: dict[str, list[dict[str, Any]]] = {}
    for accessory in accessories:
        if isinstance(accessory, dict):
            accessories_by_serial.setdefault(_string(accessory.get("serial")), []).append(accessory)

    for target in plan.get("accessories", []):
        if not isinstance(target, dict):
            continue
        serial = target.get("serial")
        if not isinstance(serial, str) or not serial:
            continue

        accessory = _unique_accessory(serial, accessories_by_serial, actions, errors)
        if accessory is None:
            continue

        bridge = target.get("bridge")
        if isinstance(bridge, dict) and "alice" in bridge:
            expected_alice = bridge["alice"]
            if alice_state_getter is None:
                msg = (
                    f"{serial}: bridge.alice задан, но runtime getter Alice ещё не "
                    "подтверждён реальным Sprut WebUI frame."
                )
                errors.append(msg)
                actions.append(PresentationAction(
                    status="ERROR",
                    serial=serial,
                    kind="bridge_alice",
                    current="UNKNOWN",
                    expected=expected_alice,
                    detail=msg,
                    accessory_id=accessory.get("id"),
                ))
            else:
                current_alice = alice_state_getter(accessory)
                if current_alice is None:
                    msg = f"{serial}: getter Alice не смог определить текущее состояние."
                    errors.append(msg)
                    actions.append(PresentationAction(
                        status="ERROR",
                        serial=serial,
                        kind="bridge_alice",
                        current="UNKNOWN",
                        expected=expected_alice,
                        detail=msg,
                        accessory_id=accessory.get("id"),
                    ))
                else:
                    actions.append(PresentationAction(
                        status="SAME" if current_alice == expected_alice else "CHANGE",
                        serial=serial,
                        kind="bridge_alice",
                        current=current_alice,
                        expected=expected_alice,
                        detail="Alice bridge policy",
                        accessory_id=accessory.get("id"),
                    ))

        for service_target in target.get("services", []):
            if not isinstance(service_target, dict):
                continue
            service_type = service_target.get("type")
            if not isinstance(service_type, str) or not service_type:
                continue

            needs_service = (
                "visible" in service_target
                or isinstance(service_target.get("status"), dict)
            )
            if not needs_service:
                continue

            service = _unique_service(
                serial, accessory, service_type, actions, errors
            )
            if service is None:
                continue

            if "visible" in service_target:
                expected_visible = service_target["visible"]
                if "visible" not in service:
                    msg = (
                        f"{serial}: Service {service_type!r} в DISCOVER не содержит "
                        "поле visible."
                    )
                    errors.append(msg)
                    actions.append(PresentationAction(
                        status="ERROR",
                        serial=serial,
                        kind="service_visible",
                        current="MISSING",
                        expected=expected_visible,
                        detail=msg,
                        accessory_id=accessory.get("id"),
                        service_id=service.get("sId"),
                        service_type=service_type,
                    ))
                else:
                    current_visible = bool(service.get("visible"))
                    actions.append(PresentationAction(
                        status="SAME" if current_visible == expected_visible else "CHANGE",
                        serial=serial,
                        kind="service_visible",
                        current=current_visible,
                        expected=expected_visible,
                        detail=f"Service.visible [{service_type}]",
                        accessory_id=accessory.get("id"),
                        service_id=service.get("sId"),
                        service_type=service_type,
                    ))

            status = service_target.get("status")
            if isinstance(status, dict):
                for ctype, expected_status_visible in status.items():
                    if not isinstance(ctype, str) or not isinstance(expected_status_visible, bool):
                        continue
                    characteristic = _unique_characteristic(
                        serial, accessory, service, service_type, ctype, actions, errors
                    )
                    if characteristic is None:
                        continue

                    if "statusVisible" not in characteristic:
                        msg = (
                            f"{serial}: Characteristic {ctype!r} в DISCOVER не содержит "
                            "поле statusVisible."
                        )
                        errors.append(msg)
                        actions.append(PresentationAction(
                            status="ERROR",
                            serial=serial,
                            kind="characteristic_status_visible",
                            current="MISSING",
                            expected=expected_status_visible,
                            detail=msg,
                            accessory_id=accessory.get("id"),
                            service_id=service.get("sId"),
                            characteristic_id=characteristic.get("cId"),
                            service_type=service_type,
                            characteristic_type=ctype,
                        ))
                    else:
                        current = bool(characteristic.get("statusVisible"))
                        actions.append(PresentationAction(
                            status="SAME" if current == expected_status_visible else "CHANGE",
                            serial=serial,
                            kind="characteristic_status_visible",
                            current=current,
                            expected=expected_status_visible,
                            detail=(
                                f"Characteristic.statusVisible "
                                f"[{service_type}/{ctype}]"
                            ),
                            accessory_id=accessory.get("id"),
                            service_id=service.get("sId"),
                            characteristic_id=characteristic.get("cId"),
                            service_type=service_type,
                            characteristic_type=ctype,
                        ))

    return PresentationDiff(actions=actions, errors=errors)


def verify_presentation(
    plan: dict[str, Any],
    discover: dict[str, Any],
    *,
    alice_state_getter: AliceStateGetter | None = None,
) -> list[tuple[str, str, str]]:
    """Return (serial, PASSED|FAILED, detail) rows.

    A target passes only if every requested presentation property is SAME.
    """
    diff = make_presentation_diff(
        plan, discover, alice_state_getter=alice_state_getter
    )

    by_serial: dict[str, list[PresentationAction]] = {}
    for action in diff.actions:
        if action.serial:
            by_serial.setdefault(action.serial, []).append(action)

    rows: list[tuple[str, str, str]] = []
    for target in plan.get("accessories", []):
        if not isinstance(target, dict):
            continue
        serial = target.get("serial")
        if not isinstance(serial, str) or not serial:
            continue

        requested = False
        bridge = target.get("bridge")
        if isinstance(bridge, dict) and "alice" in bridge:
            requested = True
        for service in target.get("services", []):
            if isinstance(service, dict) and (
                "visible" in service or isinstance(service.get("status"), dict)
            ):
                requested = True
                break

        if not requested:
            continue

        actions = by_serial.get(serial, [])
        bad = [a for a in actions if a.status != "SAME"]
        if not actions:
            rows.append((serial, "FAILED", "Нет результатов presentation-проверки."))
        elif bad:
            detail = "; ".join(
                a.detail if a.status == "ERROR"
                else f"{a.detail}: фактически={a.current!r}, ожидается={a.expected!r}"
                for a in bad
            )
            rows.append((serial, "FAILED", detail))
        else:
            rows.append((serial, "PASSED", "Presentation policy соответствует плану."))

    return rows
