from __future__ import annotations

import pytest

from nl_project_2.cables.domain import (
    ConduitContractError,
    conduit_type_suffix,
    format_conduit_id,
    parse_conduit_id,
    validate_line_conduit_fields,
)


@pytest.mark.parametrize(
    ("conduit_type", "suffix"),
    [
        ("ППЛ20", "PP20"),
        ("ППЛ25", "PP25"),
        ("МПТ16", "MPT16"),
        ("ПНД20", "PND20"),
        ("ПНД25", "PND25"),
        ("ПВХ20", "PVH20"),
        ("Металлорукав25", "MR25"),
    ],
)
def test_russian_conduit_type_generates_and_validates_technical_id(conduit_type, suffix):
    assert conduit_type_suffix(conduit_type) == suffix
    designation = format_conduit_id(3, conduit_type)
    assert designation == f"003.{suffix}"
    assert parse_conduit_id(designation, conduit_type) == 3
    assert validate_line_conduit_fields(
        mount_way="По полу",
        conduit_type=conduit_type,
        conduit_color="",
        conduit_id=designation,
    )
    with pytest.raises(ConduitContractError, match="suffix"):
        parse_conduit_id("003.WRONG16", conduit_type)


@pytest.mark.parametrize("value", ["ПП20", "ПП25", "МПТ16.5", "ППЛ", "PPL25"])
def test_noncanonical_or_malformed_conduit_type_is_rejected(value):
    with pytest.raises(ConduitContractError):
        conduit_type_suffix(value)


def test_pp_id_keeps_material_code_instead_of_russian_prefix_transliteration():
    with pytest.raises(ConduitContractError, match="suffix must be PP25"):
        parse_conduit_id("001.PPL25", "ППЛ25")
