import pytest

from nl_project_2.cad_contract.layer_names import parse_working_layer_name


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("100_Socket", 100),
        ("100_Line", 100),
        ("200_сценарники", 200),
        ("300_Light 230V floor", 300),
        ("300_Свет", 300),
        ("300_свет", 300),
        ("300_LIGHT", 300),
        ("300_light", 300),
        ("300_Свет__этаж_2", 300),
        ("400_LED карнизы", 400),
        ("500_Произвольное имя", 500),
        ("600_Отопление", 600),
        ("600_Вентиляция", 600),
        ("700_HDMI", 700),
        ("700_Акустика", 700),
        ("800_NETWORK", 800),
        ("900_RS-485 карнизы", 900),
        ("100__", 100),
        ("100_!?", 100),
        ("100_A\tБ", 100),
    ],
)
def test_working_layer_names(name: str, expected: int) -> None:
    result = parse_working_layer_name(name)
    assert type(result) is int
    assert result == expected


@pytest.mark.parametrize(
    "name",
    [
        "300",
        "300_",
        "300_  ",
        "300_ Свет",
        "300_Свет ",
        "350_Свет",
        "000_Свет",
        "1000_Свет",
        "DALI_GROUPS",
        "ARCH_WALLS",
        "",
        " 300_Свет",
        "0300_Свет",
        "+300_Свет",
        "300-Свет",
        "٣00_Свет",
        "３００_Свет",
        "300_\tСвет",
        "300_Свет\n",
        "300_\u00a0Свет",
        "300_Свет\u00a0",
    ],
)
def test_invalid_layer_names(name: str) -> None:
    assert parse_working_layer_name(name) is None


@pytest.mark.parametrize("name", [None, 300, 300.0, True, b"300_Light", [], {}, object()])
def test_non_string_input_returns_none(name: object) -> None:
    assert parse_working_layer_name(name) is None
