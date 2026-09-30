from __future__ import annotations

from nl_project_2.resource_labels import (
    resource_display_name,
    resource_technical_identity,
    resource_user_label,
)


def test_passport_label_is_primary_and_identity_remains_stable():
    row = {
        "instance_designation": "A01",
        "resource_key": "COM",
        "ordinal": 0,
        "display_json": {"label": "COM1", "quantity": 2},
    }

    assert resource_display_name(row) == "COM1"
    assert resource_user_label(row) == "A01 / COM1"
    assert resource_technical_identity(row) == "A01 / COM[0]"


def test_unlabelled_resources_do_not_receive_invented_one_based_names():
    singleton = {
        "instance_designation": "A01",
        "resource_key": "ELECTRONICS_POWER",
        "ordinal": 0,
        "display_json": {"quantity": 1},
    }
    repeated = {
        "instance_designation": "WB.01",
        "resource_key": "AX",
        "ordinal": 0,
        "display_json": {"quantity": 4},
    }

    assert resource_user_label(singleton) == "A01 / ELECTRONICS_POWER"
    assert resource_technical_identity(singleton) == "A01 / ELECTRONICS_POWER[0]"
    assert resource_user_label(repeated) == "WB.01 / AX[0]"
    assert "AX1" not in resource_user_label(repeated)


def test_snapshot_passport_label_is_used_for_legacy_read_model_rows():
    row = {
        "resource_key": "PWM",
        "ordinal": 3,
        "snapshot_json": {"passport_resource": {"label": "Channel4", "quantity": 4}},
    }

    assert resource_display_name(row) == "Channel4"
    assert resource_technical_identity(row) == "PWM[3]"
