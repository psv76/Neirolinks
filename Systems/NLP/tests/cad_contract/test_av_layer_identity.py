import pytest

from nl_project_2.cad_contract.av_layer_identity import (
    av_line_identity,
    duplicate_av_identities,
    is_av_working_layer,
    normalize_av_cable_id,
)


@pytest.mark.parametrize("layer", ["700_HDMI", "700_Акустика", "700_Living Room", "700_A__B"])
def test_av_layers(layer: str) -> None:
    assert is_av_working_layer(layer) is True


@pytest.mark.parametrize(
    "layer",
    [
        "AV",
        "700",
        "700_",
        "700_ HDMI",
        "700_HDMI ",
        "701_HDMI",
        "600_Отопление",
        None,
        700,
        True,
        b"700_HDMI",
        [],
        {},
    ],
)
def test_non_av_layers(layer: object) -> None:
    assert is_av_working_layer(layer) is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("hdmi tv", "HDMI TV"),
        (" Speaker Left ", "SPEAKER LEFT"),
        ("hdmi-1", "HDMI-1"),
        (" акустика левая ", "АКУСТИКА ЛЕВАЯ"),
        ("701", "701"),
        ("001.02", "001.02"),
        ("", ""),
        ("   ", ""),
        ("\t hdmi  tv\tleft \n", "HDMI  TV\tLEFT"),
        (" A__b!? ", "A__B!?"),
    ],
)
def test_normalization_preserves_free_text(raw: str, expected: str) -> None:
    assert normalize_av_cable_id(raw) == expected


@pytest.mark.parametrize("value", [None, 701, 1.5, True, b"hdmi", [], {}])
def test_non_string_ids_raise_type_error(value: object) -> None:
    with pytest.raises(TypeError, match="cable_id must be a string"):
        normalize_av_cable_id(value)
    with pytest.raises(TypeError, match="cable_id must be a string"):
        av_line_identity("", value)
    with pytest.raises(TypeError, match="cable_id must be a string"):
        duplicate_av_identities([("AV.01", value)])


@pytest.mark.parametrize("board", [None, 701, True, b"Board", [], {}])
def test_non_string_boards_raise_type_error(board: object) -> None:
    with pytest.raises(TypeError, match="board must be a string"):
        av_line_identity(board, "hdmi")
    with pytest.raises(TypeError, match="board must be a string"):
        duplicate_av_identities([(board, "hdmi")])


@pytest.mark.parametrize(
    ("board", "cable_id", "expected"),
    [
        (" AV.01 ", " hdmi tv ", ("AV.01", "HDMI TV")),
        (" Стойка Гостиная ", " левый ", ("Стойка Гостиная", "ЛЕВЫЙ")),
        ("custom Board!?", "701", ("custom Board!?", "701")),
        ("", "hdmi", None),
        (" \t", "hdmi", None),
        ("AV.01", "", None),
        ("AV.01", " \n", None),
        ("", "", None),
    ],
)
def test_composite_identity(board: str, cable_id: str, expected: tuple[str, str] | None) -> None:
    assert av_line_identity(board, cable_id) == expected


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ([], frozenset()),
        (
            [("AV.01", "hdmi"), (" AV.01 ", " HDMI "), ("AV.01", "HdMi")],
            frozenset({("AV.01", "HDMI")}),
        ),
        ([("AV.01", "hdmi"), ("AV.02", "HDMI")], frozenset()),
        ([("Board", "hdmi"), ("board", "HDMI")], frozenset()),
        ([("", "hdmi"), (" ", "HDMI"), ("AV.01", ""), ("AV.01", " ")], frozenset()),
        (
            [("A", "left"), ("A", "LEFT"), ("B", "right"), ("B", "RIGHT")],
            frozenset({("A", "LEFT"), ("B", "RIGHT")}),
        ),
    ],
)
def test_duplicate_identity_scope(rows: list[tuple[str, str]], expected: frozenset) -> None:
    before = rows.copy()
    result = duplicate_av_identities(iter(rows))
    assert isinstance(result, frozenset)
    assert result == expected
    assert rows == before


def test_read_only_av_contract_inventory(block_contract) -> None:
    rules = block_contract.av_rules
    assert rules["identity"] == ["BOARD", "CABLE_ID"]
    assert rules["normalize_cable_id"] == ["TRIM", "UPPERCASE"]
    assert rules["incomplete_is_scannable"] is True
    assert rules["duplicate_identity_blocks_save"] is True
    assert block_contract.load_types["AV"] == frozenset({"SPEAKER_CABLE", "HDMI"})


@pytest.mark.parametrize("cable_id", ["301", "701", "HDMI living room", "Левая акустика"])
def test_helpers_do_not_select_products_or_calculate_lengths(monkeypatch, cable_id: str) -> None:
    from nl_project_2.cables.service import CableService

    def forbidden(*args, **kwargs):
        pytest.fail("AV identity helpers must not select HDMI products or calculate quantities")

    monkeypatch.setattr(CableService, "auto_select_hdmi", forbidden)
    monkeypatch.setattr(CableService, "select_hdmi_manually", forbidden)
    monkeypatch.setattr(CableService, "calculate_and_save_length", forbidden)
    monkeypatch.setattr(CableService, "effective_length", forbidden)
    assert is_av_working_layer("700_HDMI") is True
    assert av_line_identity("User Board", cable_id) == ("User Board", cable_id.upper())
    assert duplicate_av_identities([("User Board", cable_id)]) == frozenset()
