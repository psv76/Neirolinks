from pathlib import Path
import json
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from sprut_plan_generator import generate_sprut_plan

OBJECT_FIXTURE = (
    ROOT.parent
    / "objects"
    / "05_31_Ivolga_13"
    / "Doc"
    / "SprutConfigurator"
    / "issue22"
    / "nl_project1_besedka_source_fixture.json"
)
OBJECT_POLICY = (
    ROOT.parent
    / "objects"
    / "05_31_Ivolga_13"
    / "Doc"
    / "SprutConfigurator"
    / "issue22"
    / "besedka_sprut_export_policy.yaml"
)


def test_besedka_fixture_generates_18_project_derived_lights():
    source = json.loads(OBJECT_FIXTURE.read_text(encoding="utf-8"))
    policy = yaml.safe_load(OBJECT_POLICY.read_text(encoding="utf-8"))

    result = generate_sprut_plan(source, policy)
    assert result.ok, result.errors

    accessories = result.plan["accessories"]
    assert len(accessories) == 18
    assert accessories[0] == {
        "serial": "A41/K1",
        "name": "301 Свет фасад беседки",
        "room": "Фасад",
        "services": [
            {
                "type": "Lightbulb",
                "name": "301 Свет фасад беседки",
                "visible": True,
            }
        ],
    }
    assert accessories[-1]["serial"] == "A48/Channel 3"
    assert accessories[-1]["name"] == "356 LED над грилем"


def test_direct_output_guard_rejects_non_output_identity():
    source = {
        "source": {"object_name": "X"},
        "lines": [
            {
                "id": "1",
                "room": "R",
                "purpose": "P",
                "connection_point": "WB.02/MOD1",
            }
        ],
    }
    policy = {
        "policy_version": 1,
        "targets": [
            {
                "source_line": "1",
                "serial_from": "connection_point",
                "require_direct_output": True,
                "services": [{"type": "Lightbulb"}],
            }
        ],
    }

    result = generate_sprut_plan(source, policy)
    assert not result.ok
    assert "not a direct WB output identity" in result.errors[0]


def test_duplicate_serial_is_error():
    source = {
        "source": {"object_name": "X"},
        "lines": [
            {
                "id": "1",
                "room": "R",
                "purpose": "One",
                "connection_point": "A1/K1",
            },
            {
                "id": "2",
                "room": "R",
                "purpose": "Two",
                "connection_point": "A1/K1",
            },
        ],
    }
    target = {
        "serial_from": "connection_point",
        "require_direct_output": True,
        "services": [{"type": "Lightbulb"}],
    }
    policy = {
        "policy_version": 1,
        "targets": [
            {"source_line": "1", **target},
            {"source_line": "2", **target},
        ],
    }

    result = generate_sprut_plan(source, policy)
    assert not result.ok
    assert any("duplicate generated serial" in error for error in result.errors)


def test_name_limit_fails_closed():
    source = {
        "source": {"object_name": "X"},
        "lines": [
            {
                "id": "1",
                "room": "R",
                "purpose": "X" * 40,
                "connection_point": "A1/K1",
            }
        ],
    }
    policy = {
        "policy_version": 1,
        "targets": [
            {
                "source_line": "1",
                "serial_from": "connection_point",
                "require_direct_output": True,
                "services": [{"type": "Lightbulb"}],
            }
        ],
    }

    result = generate_sprut_plan(source, policy)
    assert not result.ok
    assert any("32-char limit" in error for error in result.errors)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
