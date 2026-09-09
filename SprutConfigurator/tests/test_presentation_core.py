from pathlib import Path
import sys

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from presentation_core import (
    characteristic_type,
    make_presentation_diff,
    validate_presentation_plan,
    verify_presentation,
)


def base_plan():
    return {
        "format_version": 2,
        "accessories": [
            {
                "serial": "NL_simple_thermostat_010",
                "name": "Воздух",
                "room": "Гостиная",
                "bridge": {"alice": True},
                "services": [
                    {
                        "type": "Thermostat",
                        "name": "Воздух",
                        "visible": True,
                        "status": {
                            "CurrentHeatingCoolingState": True,
                            "CurrentTemperature": True,
                        },
                    }
                ],
            },
            {
                "serial": "NL_simple_thermostat_611",
                "name": "Пол",
                "room": "Гостиная",
                "bridge": {"alice": False},
                "services": [
                    {
                        "type": "Thermostat",
                        "name": "Пол",
                        "visible": True,
                        "status": {
                            "CurrentHeatingCoolingState": False,
                            "CurrentTemperature": False,
                        },
                    }
                ],
            },
        ],
    }


def discover():
    def thermostat(aid, serial, visible, mode_status, temp_status, alice):
        return {
            "id": aid,
            "serial": serial,
            "_testAlice": alice,
            "services": [
                {"type": "AccessoryInformation", "system": True, "sId": 1},
                {
                    "type": "Thermostat",
                    "name": serial,
                    "sId": 13,
                    "visible": visible,
                    "characteristics": [
                        {
                            "cId": 20,
                            "statusVisible": mode_status,
                            "control": {"type": "CurrentHeatingCoolingState"},
                        },
                        {
                            "cId": 21,
                            "statusVisible": temp_status,
                            "control": {"type": "CurrentTemperature"},
                        },
                    ],
                },
            ],
        }

    return {
        "accessories": [
            thermostat(10, "NL_simple_thermostat_010", False, False, True, False),
            thermostat(11, "NL_simple_thermostat_611", True, True, False, False),
        ]
    }


def alice_getter(accessory):
    return accessory.get("_testAlice")


def test_validation():
    plan = base_plan()
    assert validate_presentation_plan(plan) == []

    bad = base_plan()
    bad["accessories"][0]["services"][0]["visible"] = "yes"
    bad["accessories"][1]["bridge"]["alice"] = 1
    errors = validate_presentation_plan(bad)
    assert any(".visible" in e for e in errors)
    assert any("bridge.alice" in e for e in errors)


def test_characteristic_type():
    assert characteristic_type({"type": "A"}) == "A"
    assert characteristic_type({"control": {"type": "B"}}) == "B"
    assert characteristic_type({}) == ""


def test_diff_with_confirmed_alice_adapter():
    diff = make_presentation_diff(
        base_plan(),
        discover(),
        alice_state_getter=alice_getter,
    )
    assert diff.ok
    changed = {(a.serial, a.kind, a.characteristic_type): a for a in diff.changes}

    assert ("NL_simple_thermostat_010", "bridge_alice", None) in changed
    assert ("NL_simple_thermostat_010", "service_visible", None) in changed
    assert (
        "NL_simple_thermostat_010",
        "characteristic_status_visible",
        "CurrentHeatingCoolingState",
    ) in changed

    assert (
        "NL_simple_thermostat_611",
        "characteristic_status_visible",
        "CurrentHeatingCoolingState",
    ) in changed

    assert (
        "NL_simple_thermostat_010",
        "characteristic_status_visible",
        "CurrentTemperature",
    ) not in changed
    assert (
        "NL_simple_thermostat_611",
        "characteristic_status_visible",
        "CurrentTemperature",
    ) not in changed


def test_alice_without_adapter_is_fail_closed():
    diff = make_presentation_diff(base_plan(), discover())
    assert not diff.ok
    assert any(a.kind == "bridge_alice" and a.status == "ERROR" for a in diff.actions)


def test_missing_status_visible_is_error():
    data = discover()
    del data["accessories"][0]["services"][1]["characteristics"][0]["statusVisible"]
    diff = make_presentation_diff(
        base_plan(), data, alice_state_getter=alice_getter
    )
    assert not diff.ok
    assert any(
        a.kind == "characteristic_status_visible"
        and a.status == "ERROR"
        and a.current == "MISSING"
        for a in diff.actions
    )


def test_verify():
    plan = base_plan()
    data = discover()

    air = data["accessories"][0]
    floor = data["accessories"][1]
    air["_testAlice"] = True
    air["services"][1]["visible"] = True
    air["services"][1]["characteristics"][0]["statusVisible"] = True
    floor["_testAlice"] = False
    floor["services"][1]["visible"] = True
    floor["services"][1]["characteristics"][0]["statusVisible"] = False

    rows = verify_presentation(plan, data, alice_state_getter=alice_getter)
    assert rows == [
        ("NL_simple_thermostat_010", "PASSED", "Presentation policy соответствует плану."),
        ("NL_simple_thermostat_611", "PASSED", "Presentation policy соответствует плану."),
    ]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
