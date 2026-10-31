"""Read-only Q216 BUS tube quantity candidates (not procurement approval)."""

from decimal import Decimal

import pytest

from nl_project_2.cables.bus_conduit_preview import preview_bus_conduit_candidates
from nl_project_2.cables.conduit_audit import ConduitAudit
from nl_project_2.cables.length_policy import LengthPolicy
from nl_project_2.cables.physical_conduit import PhysicalBoundary, PhysicalSpan


def _uid(n):
    return f"00000000-0000-4000-8000-{n:012d}"


SPAN = PhysicalSpan(
    PhysicalBoundary("INSTANCE_RESOURCE", _uid(1)),
    PhysicalBoundary("FIELD_DEVICE", _uid(2)),
)
POLICY = LengthPolicy(
    nonlinearity_percent=Decimal("2"),
    bypass_percent=Decimal("5"),
    rounding_step_m=Decimal("1"),
)


def _tube(**changes):
    return {
        "id": _uid(10),
        "designation": "322.PP20",
        "length_m_decimal": None,
        "conduit_type": "ППЛ20",
        "color": "Синий",
        "path_json": {
            "origin": "AUTO_BUS_SEGMENT",
            "initial_length_status": "PENDING_SEGMENT_LENGTH",
        },
        **changes,
    }


def _bus(**changes):
    return {
        "id": _uid(20),
        "connection_kind": "CABLE",
        "migration_state": "CONFIRMED",
        "gofra_type": "ППЛ20",
        "gofra_color": "Синий",
        "mount_way": "По полу",
        "length_m_decimal": "7.02656",
        **changes,
    }


def _audit(*, state="PHYSICAL_MATCH", member_keys=None, span=SPAN):
    if member_keys is None:
        member_keys = (("BUS", _uid(20)),)
    return ConduitAudit(
        _uid(10),
        state,
        member_keys,
        span if state == "PHYSICAL_MATCH" else None,
        (),
    )


def _preview(tube=None, bus=None, audit=None):
    return preview_bus_conduit_candidates(
        audits=(_audit() if audit is None else audit,),
        conduit_rows=(_tube() if tube is None else tube,),
        bus_segments=(_bus() if bus is None else bus,),
        policy=POLICY,
    )[0]


def test_singular_confirmed_bus_is_only_a_readonly_candidate():
    result = _preview()
    assert result.status == "CANDIDATE"
    assert result.geometry_m == Decimal("7.02656")
    assert result.automatic_m == Decimal("8")
    assert result.bus_segment_id == _uid(20)
    assert result.issues == ()
    assert result.can_publish is False


def test_candidate_uses_project_route_percentages_then_rounds_one_physical_tube():
    result = _preview(bus=_bus(length_m_decimal="10"))
    assert result.geometry_m == Decimal("10")
    assert result.automatic_m == Decimal("11")
    assert not result.can_publish


@pytest.mark.parametrize(
    ("audit", "expected"),
    [
        (_audit(state="UNRESOLVED"), "Q03_UNRESOLVED"),
        (_audit(state="BOUNDARY_CONFLICT"), "Q03_BOUNDARY_CONFLICT"),
        (_audit(member_keys=(("BUS", _uid(20)), ("CABLE", _uid(99)))), "NOT_SINGLE_BUS_ONLY"),
        (_audit(member_keys=(("BUS", _uid(20)), ("BUS", _uid(21)))), "NOT_SINGLE_BUS_ONLY"),
    ],
)
def test_unknown_or_shared_physical_tube_is_blocked(audit, expected):
    result = _preview(audit=audit)
    assert result.status == "BLOCKED"
    assert expected in result.issues
    assert result.automatic_m is None


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"length_m_decimal": None}, "BUS_GEOMETRY_MISSING"),
        ({"length_m_decimal": "NaN"}, "BUS_GEOMETRY_MISSING"),
        ({"length_m_decimal": "-2"}, "BUS_GEOMETRY_MISSING"),
        ({"migration_state": "UNCONFIRMED"}, "BUS_GEOMETRY_NOT_CONFIRMED"),
        ({"connection_kind": "TRACK"}, "NOT_PHYSICAL_BUS_CABLE"),
        ({"mount_way": "В кабель-канале"}, "PROTECTED_MOUNT_WAY_NOT_CONFIRMED"),
        ({"mount_way": "bad"}, "PROTECTED_MOUNT_WAY_NOT_CONFIRMED"),
        ({"gofra_type": "ППЛ25"}, "CONDUIT_TYPE_MISMATCH"),
        ({"gofra_color": "Красный"}, "CONDUIT_COLOR_MISMATCH"),
    ],
)
def test_invalid_bus_length_or_technical_fields_fail_closed(changes, expected):
    result = _preview(bus=_bus(**changes))
    assert result.status == "BLOCKED"
    assert expected in result.issues
    assert result.automatic_m is None


def test_known_length_and_non_bus_origin_not_overwritten():
    for tube in (
        _tube(length_m_decimal="20"),
        _tube(path_json={"origin": "DWG"}),
    ):
        assert (
            preview_bus_conduit_candidates(
                audits=(_audit(),),
                conduit_rows=(tube,),
                bus_segments=(_bus(),),
                policy=POLICY,
            )
            == ()
        )


def test_missing_segment_or_audit_fails_closed():
    missing_segment = preview_bus_conduit_candidates(
        audits=(_audit(),),
        conduit_rows=(_tube(),),
        bus_segments=(),
        policy=POLICY,
    )[0]
    assert missing_segment.status == "BLOCKED"
    assert "BUS_SEGMENT_MISSING" in missing_segment.issues

    missing_audit = preview_bus_conduit_candidates(
        audits=(),
        conduit_rows=(_tube(),),
        bus_segments=(_bus(),),
        policy=POLICY,
    )[0]
    assert missing_audit.status == "BLOCKED"
    assert "PHYSICAL_AUDIT_MISSING" in missing_audit.issues


def test_duplicate_segment_identity_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        preview_bus_conduit_candidates(
            audits=(_audit(),),
            conduit_rows=(_tube(),),
            bus_segments=(_bus(), _bus()),
            policy=POLICY,
        )


def test_empty_auto_bus_conduit_stays_blocked():
    preview = _preview(audit=_audit(state="EMPTY", member_keys=()))
    assert preview.status == "BLOCKED"
    assert set(preview.issues) == {"Q03_EMPTY", "NOT_SINGLE_BUS_ONLY"}
    assert preview.automatic_m is None
    assert preview.can_publish is False
