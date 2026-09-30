from nl_project_2.cables.presentation import format_cable_mark


def test_legacy_short_cable_marks_are_presented_without_new_rules():
    assert format_cable_mark("3x1,5") == "ВВГнг(А)-LS 3х1,5"
    assert format_cable_mark("3х2,5") == "ВВГнг(А)-LS 3х2,5"
    assert format_cable_mark("2x0,75") == "МКШнг-LS 2х0,75"
    assert format_cable_mark("UTP 5e") == "UTP 5e 4х2х0,5"


def test_unknown_or_full_cable_mark_is_not_rewritten():
    assert format_cable_mark("КПСнг(А)-FRLS 1x2x0,75") == "КПСнг(А)-FRLS 1x2x0,75"
    assert format_cable_mark("ВВГнг(А)-LS 3х1,5") == "ВВГнг(А)-LS 3х1,5"
