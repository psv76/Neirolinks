"""NST platform metadata stored alongside preserved NLI durable state."""
from .layout import STATE_DIR
from .util import read_json, require, write_json

PLATFORM_STATE = STATE_DIR + "/platform.json"


def default_platform_state():
    return {
        "schema": 1,
        "controller": None,
        "registry": None,
        "deployment": None,
        "desired_state": None,
    }


def validate_platform_state(value):
    require(type(value) is dict, "Invalid NST platform state")
    require(set(value) == {"schema", "controller", "registry", "deployment", "desired_state"},
            "Invalid NST platform state fields")
    require(value["schema"] == 1, "Unsupported NST platform state schema")
    for key in ("controller", "registry", "deployment", "desired_state"):
        require(value[key] is None or type(value[key]) is dict, "Invalid NST platform " + key)
    return value


def load_platform_state(engine):
    path = engine.target(PLATFORM_STATE)
    if not path.exists():
        return default_platform_state()
    return validate_platform_state(read_json(path))


def save_platform_state(engine, value):
    write_json(engine.target(PLATFORM_STATE), validate_platform_state(value))
