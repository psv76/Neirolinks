"""Pure working-layer name parsing, independent of runtime group mapping."""


def parse_working_layer_name(name: object) -> int | None:
    """Return 100..900 for ``GGG_<suffix>``, otherwise None.

    Only the nine ASCII hundred prefixes are accepted. The suffix must be
    nonempty with no leading or trailing whitespace; its contents are otherwise
    unrestricted. Non-string input is rejected without coercion or trimming.
    """
    if not isinstance(name, str) or len(name) < 5:
        return None
    if name[0] not in "123456789" or name[1:4] != "00_":
        return None
    suffix = name[4:]
    if suffix[0].isspace() or suffix[-1].isspace():
        return None
    return int(name[:3])
