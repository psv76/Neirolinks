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
from rpc_contract import (
    characteristic_status_visible_params,
    parse_yandex_bridge_services,
    service_visible_params,
    yandex_bridge_disable_params,
    yandex_bridge_enable_params,
    yandex_bridge_list_params,
    yandex_bridge_membership,
)


def base_plan():
    return {
        "format_version": 2,
        "accessories": [
            {
                "serial": "NL_simple_thermostat_010",
                "name": "Воздух",
                "room": "Гостиная",
                "services": [
                    {
                        "type": "Thermostat",
                        "name": "Воздух",
                        "visible": True,
                        "status": {
                            "CurrentHeatingCoolingState": True,
                            "CurrentTemperature": True,
                        },
                        "bridge": {"alice": True},
                    }
                ],
            },
            {
                "serial": "NL_simple_thermostat_611",
                "name": "Пол",
                "room": "Гостиная",
                "services": [
                    {
                        "type": "Thermostat",
                        "name": "Пол",
                        "visible": True,
                        "status": {
                            "CurrentHeatingCoolingState": False,
                            "CurrentTemperature": False,
                        },
                        "bridge": {"alice": False},
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
            "services": [
                {"type": "AccessoryInformation", "system": True, "sId": 1},
                {
                    "type": "Thermostat",
                    "name": serial,
                    "sId": 13,
                    "visible": visible,
                    "_testAlice": alice,
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


def alice_getter(accessory, service):
    return service.get("_testAlice")


def test_validation():
    plan = base_plan()
    assert validate_presentation_plan(plan) == []

    bad = base_plan()
    bad["accessories"][0]["services"][0]["visible"] = "yes"
    bad["accessories"][1]["services"][0]["bridge"]["alice"] = 1
    errors = validate_presentation_plan(bad)
    assert any(".visible" in e for e in errors)
    assert any("bridge.alice" in e for e in errors)

    ambiguous = base_plan()
    ambiguous["accessories"][0]["bridge"] = {"alice": True}
    errors = validate_presentation_plan(ambiguous)
    assert any("bridge policy должен задаваться внутри services[]" in e for e in errors)


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

    alice = changed[("NL_simple_thermostat_010", "bridge_alice", None)]
    assert alice.service_id == 13

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


def test_alice_without_adapter_is_fail_closed():
    diff = make_presentation_diff(base_plan(), discover())
    assert not diff.ok
    bridge_errors = [
        a for a in diff.actions
        if a.kind == "bridge_alice" and a.status == "ERROR"
    ]
    assert len(bridge_errors) == 2
    assert all(a.service_id == 13 for a in bridge_errors)


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

    air = data["accessories"][0]["services"][1]
    floor = data["accessories"][1]["services"][1]

    air["_testAlice"] = True
    air["visible"] = True
    air["characteristics"][0]["statusVisible"] = True

    floor["_testAlice"] = False
    floor["visible"] = True
    floor["characteristics"][0]["statusVisible"] = False

    rows = verify_presentation(plan, data, alice_state_getter=alice_getter)
    assert rows == [
        ("NL_simple_thermostat_010", "PASSED", "Presentation policy соответствует плану."),
        ("NL_simple_thermostat_611", "PASSED", "Presentation policy соответствует плану."),
    ]


def test_field_confirmed_rpc_params():
    assert service_visible_params(118, 13, False) == {
        "service": {
            "update": {
                "aId": 118,
                "sId": 13,
                "visible": False,
            }
        }
    }

    assert characteristic_status_visible_params(118, 13, 15, False) == {
        "characteristic": {
            "update": {
                "aId": 118,
                "sId": 13,
                "cId": 15,
                "statusVisible": False,
            }
        }
    }

    assert yandex_bridge_list_params() == {
        "bridgeService": {
            "list": {
                "bridgeIndex": "Yandex_1",
            }
        }
    }

    assert yandex_bridge_enable_params(118, 13) == {
        "bridgeService": {
            "create": {
                "bridgeIndex": "Yandex_1",
                "aId": 118,
                "sId": 13,
                "write": True,
            }
        }
    }

    assert yandex_bridge_disable_params(118, 13) == {
        "bridgeService": {
            "delete": {
                "bridgeIndex": "Yandex_1",
                "aId": 118,
                "sId": 13,
            }
        }
    }


def test_bridge_list_response_parser_and_membership():
    result = {
        "bridgeService": {
            "list": {
                "services": [
                    {
                        "aId": 118,
                        "sId": 13,
                        "write": True,
                        "key": "Bridge:Yandex_1",
                        "bridgeIndex": "Yandex_1",
                    },
                    {
                        "aId": 9,
                        "sId": 18,
                        "write": True,
                        "key": "Bridge:Yandex_1",
                        "bridgeIndex": "Yandex_1",
                    },
                ]
            }
        }
    }

    services = parse_yandex_bridge_services(result)
    assert len(services) == 2
    assert yandex_bridge_membership(services, 118, 13) is True
    assert yandex_bridge_membership(services, 118, 18) is False
    assert yandex_bridge_membership(services, 9, 18) is True


def test_bridge_list_response_parser_rejects_unknown_shape():
    try:
        parse_yandex_bridge_services({"bridgeService": {"list": {}}})
    except ValueError as exc:
        assert "result.bridgeService.list.services" in str(exc)
    else:
        raise AssertionError("Malformed bridgeService.list response must fail")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
