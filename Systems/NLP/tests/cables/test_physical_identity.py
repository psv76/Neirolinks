"""Canonical Project physical-owner identity for ordinary cables and BUS."""

from __future__ import annotations

from nl_project_2.cables.physical_identity import (
    PhysicalOwnerIndex,
    resolve_bus_segment,
    resolve_cable_endpoint,
    resolve_cable_segment,
)


def uid(number: int) -> str:
    return f"00000000-0000-4000-8000-{number:012d}"


BOARD = uid(1)
BOX_POINT = uid(2)
DEVICE = uid(3)
RESOURCE = uid(4)
PORT = uid(5)


def owners(
    *,
    point_id: str = BOX_POINT,
    point_kind: str = "EL_BOX",
    members: tuple[str, ...] = (),
) -> PhysicalOwnerIndex:
    return PhysicalOwnerIndex(
        board_ids=frozenset({BOARD}),
        resource_ids=frozenset({RESOURCE}),
        device_ids=frozenset({DEVICE}),
        port_device_ids={PORT: DEVICE},
        cable_points={
            point_id: {
                "id": point_id,
                "point_kind": point_kind,
                "logical_identity": "BOX.010",
            },
            uid(20): {"id": uid(20), "point_kind": "INTERNAL_SOURCE"},
            uid(21): {"id": uid(21), "point_kind": "INTERNAL_SOURCE"},
        },
        point_devices={point_id: members} if members else {},
    )


def cable_example(line_number: int, *, point_id: str = BOX_POINT) -> tuple[dict, dict, dict]:
    line_id = uid(100 + line_number)
    src_id = uid(200 + line_number)
    target_id = uid(300 + line_number)
    line = {"id": line_id, "board_id": BOARD}
    endpoints = {
        src_id: {
            "id": src_id,
            "cable_line_id": line_id,
            "endpoint_kind": "TOPOLOGY_POINT",
            "cable_point_id": uid(20 + line_number),
        },
        target_id: {
            "id": target_id,
            "cable_line_id": line_id,
            "endpoint_kind": "TOPOLOGY_POINT",
            "cable_point_id": point_id,
        },
    }
    segment = {
        "id": uid(400 + line_number),
        "cable_line_id": line_id,
        "source_endpoint_id": src_id,
        "target_endpoint_id": target_id,
    }
    return line, endpoints, segment


def test_shared_el_box_point_can_serve_two_cablelines_after_migration_14():
    # Distinct line-local endpoint IDs point to the very same physical point.
    line_a, ep_a, seg_a = cable_example(0)
    line_b, ep_b, seg_b = cable_example(1)
    idx = owners()
    a = resolve_cable_segment(seg_a, line=line_a, endpoints=ep_a, owners=idx)
    b = resolve_cable_segment(seg_b, line=line_b, endpoints=ep_b, owners=idx)
    assert a.complete and b.complete
    assert a.span.key() == b.span.key()
    assert a.target.boundary.identity == BOX_POINT
    assert a.target.boundary.kind == "EL_BOX"
    assert seg_a["target_endpoint_id"] != seg_b["target_endpoint_id"]


def test_same_display_box_label_different_persisted_physical_ids_never_merge():
    line_a, ep_a, seg_a = cable_example(0)
    line_b, ep_b, seg_b = cable_example(1, point_id=uid(88))
    idx_a = owners()
    idx_b = owners(point_id=uid(88))
    a = resolve_cable_segment(seg_a, line=line_a, endpoints=ep_a, owners=idx_a)
    b = resolve_cable_segment(seg_b, line=line_b, endpoints=ep_b, owners=idx_b)
    assert a.complete and b.complete
    assert a.target.boundary.identity != b.target.boundary.identity
    assert a.span.key() != b.span.key()


def test_field_port_resolves_to_physical_device_owner():
    line_id = uid(100)
    endpoint = {
        "id": uid(90),
        "cable_line_id": line_id,
        "endpoint_kind": "FIELD_PORT",
        "field_port_id": PORT,
    }
    result = resolve_cable_endpoint(
        endpoint, line={"id": line_id, "board_id": BOARD}, owners=owners()
    )
    assert result.issue is None
    assert result.boundary.kind == "FIELD_DEVICE"
    assert result.boundary.identity == DEVICE


def test_missing_board_and_ambiguous_device_group_fail_closed():
    idx = owners(point_kind="INSTALLATION_GROUP", members=(DEVICE, uid(9)))
    line_a, endpoints, segment = cable_example(0)
    unresolved = resolve_cable_segment(segment, line=line_a, endpoints=endpoints, owners=idx)
    assert unresolved.span is None
    assert "one confirmed physical owner" in unresolved.target.issue

    missing_board = PhysicalOwnerIndex(
        board_ids=frozenset(),
        resource_ids=idx.resource_ids,
        device_ids=idx.device_ids,
        port_device_ids=idx.port_device_ids,
        cable_points=idx.cable_points,
        point_devices=idx.point_devices,
    )
    unresolved = resolve_cable_segment(
        segment, line=line_a, endpoints=endpoints, owners=missing_board
    )
    assert unresolved.span is None
    assert "BOARD" in unresolved.source.issue


def test_bus_device_and_cable_device_share_canonical_owner():
    idx = owners(point_kind="DEVICE_POINT", members=(DEVICE,))
    line_a, ep_a, seg_a = cable_example(0)
    cable = resolve_cable_segment(seg_a, line=line_a, endpoints=ep_a, owners=idx)
    bus_id = uid(600)
    bus_ep_id = uid(601)
    bus_segment = {
        "id": uid(602),
        "bus_id": bus_id,
        "source_endpoint_id": None,
        "target_endpoint_id": bus_ep_id,
        "connection_kind": "CABLE",
    }
    bus_line = {"id": bus_id, "root_resource_id": RESOURCE}
    bus_eps = {
        bus_ep_id: {
            "id": bus_ep_id,
            "bus_id": bus_id,
            "endpoint_kind": "FIELD_DEVICE",
            "field_device_id": DEVICE,
        }
    }
    bus = resolve_bus_segment(bus_segment, bus=bus_line, endpoints=bus_eps, owners=idx)
    assert cable.complete and bus.complete
    assert cable.target.boundary == bus.target.boundary
    assert bus.source.boundary.kind == "INSTANCE_RESOURCE"


def test_bus_track_is_not_a_physical_cable():
    idx = owners()
    result = resolve_bus_segment(
        {
            "id": uid(602),
            "bus_id": uid(600),
            "source_endpoint_id": None,
            "target_endpoint_id": uid(601),
            "connection_kind": "TRACK",
        },
        bus={"id": uid(600), "root_resource_id": RESOURCE},
        endpoints={},
        owners=idx,
    )
    assert result is None


def test_same_endpoint_on_both_ends_is_not_an_accepted_physical_span():
    idx = owners()
    bus_id = uid(600)
    end_id = uid(601)
    result = resolve_bus_segment(
        {
            "id": uid(602),
            "bus_id": bus_id,
            "source_endpoint_id": None,
            "target_endpoint_id": end_id,
            "connection_kind": "CABLE",
        },
        bus={"id": bus_id, "root_resource_id": RESOURCE},
        endpoints={
            end_id: {
                "id": end_id,
                "bus_id": bus_id,
                "endpoint_kind": "INSTANCE_RESOURCE",
                "resource_id": RESOURCE,
            }
        },
        owners=idx,
    )
    assert not result.complete
    assert "same physical owner" in result.target.issue


def test_wrong_line_endpoint_is_not_resolved_by_matching_ids():
    idx = owners()
    line, endpoints, segment = cable_example(0)
    endpoints[segment["target_endpoint_id"]]["cable_line_id"] = uid(999)
    result = resolve_cable_segment(segment, line=line, endpoints=endpoints, owners=idx)
    assert not result.complete
    assert "another line" in result.target.issue
