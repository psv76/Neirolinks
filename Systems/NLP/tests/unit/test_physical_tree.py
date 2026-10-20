"""Qt-independent contract tests for Lines' physical topology renderer."""

from __future__ import annotations

from nl_project_2.presentation.physical_tree import (
    compact_physical_edge_rows,
    physical_edge_layout,
)


def endpoint(identity: str, *, kind: str = "TOPOLOGY_POINT", box: bool = False) -> dict:
    return {
        "kind": kind,
        "reference": identity,
        "label": identity,
        "point_kind": "EL_BOX" if box else "DEVICE_POINT",
    }


def edge(
    source: str,
    target: str,
    *,
    source_kind: str = "TOPOLOGY_POINT",
    box: bool = False,
    incomplete: bool = False,
) -> dict:
    return {
        "segment_id": f"{source}->{target}",
        "source": endpoint(source, kind=source_kind),
        "target": endpoint(target, box=box),
        "depth": 99,  # Not a usable physical topology contract.
        "calculation_status": "INCOMPLETE" if incomplete else "READY",
        "gofra_id": target,
    }


def test_board_roots_are_distinct_without_a_synthetic_common_cable():
    rows = physical_edge_layout(
        [
            edge("BOARD", "FIRST", source_kind="BOARD_OUTPUT"),
            edge("BOARD", "SECOND", source_kind="BOARD_OUTPUT"),
            edge("BOARD", "THIRD", source_kind="BOARD_OUTPUT"),
        ]
    )
    assert len(rows) == 3
    assert all(row.is_root and row.parent_index is None for row in rows)
    assert all(row.prefix == "↳ " for row in rows)
    assert [row.edge["segment_id"] for row in rows] == [
        "BOARD->FIRST",
        "BOARD->SECOND",
        "BOARD->THIRD",
    ]


def test_el_box_branch_guides_come_from_real_endpoint_graph_not_depth():
    rows = physical_edge_layout(
        [
            edge("BOX", "ROOM1"),
            edge("BOARD", "BOX", source_kind="BOARD_OUTPUT", box=True),
            edge("BOX", "ROOM2"),
            edge("ROOM2", "LAMP"),
        ]
    )
    assert [row.index for row in rows] == [1, 0, 2, 3]
    assert [row.parent_index for row in rows] == [None, 1, 1, 2]
    assert [row.prefix for row in rows] == ["↳ ", "   ├─ ", "   └─ ", "      └─ "]


def test_equal_display_labels_without_stable_ids_must_not_join():
    first = edge("BOARD", "FIRST", source_kind="BOARD_OUTPUT")
    second = edge("SECOND", "LAST")
    first["target"] = {"kind": "TOPOLOGY_POINT", "label": "same"}
    second["source"] = {"kind": "TOPOLOGY_POINT", "label": "same"}
    rows = physical_edge_layout([first, second])
    assert [row.parent_index for row in rows] == [None, None]


def test_equal_refs_with_distinct_endpoint_types_must_not_join():
    rows = physical_edge_layout(
        [
            edge("BOARD", "SAME", source_kind="BOARD_OUTPUT"),
            edge("SAME", "DEVICE", source_kind="FIELD_PORT"),
        ]
    )
    assert [row.parent_index for row in rows] == [None, None]


def test_converging_references_must_not_pick_a_random_parent():
    rows = physical_edge_layout(
        [
            edge("BOARD", "FIRST", source_kind="BOARD_OUTPUT"),
            edge("BOARD", "SECOND", source_kind="BOARD_OUTPUT"),
            edge("FIRST", "JOIN"),
            edge("SECOND", "JOIN"),
            edge("JOIN", "LAST"),
        ]
    )
    assert len(rows) == 5
    outgoing = next(row for row in rows if row.edge["segment_id"] == "JOIN->LAST")
    assert outgoing.is_root
    assert outgoing.parent_index is None


def test_compact_preserves_all_roots_boxes_forks_issues_and_ancestry():
    edges = [
        edge(
            "BOARD" if i == 0 else f"P{i}",
            f"P{i + 1}",
            source_kind="BOARD_OUTPUT" if i == 0 else "TOPOLOGY_POINT",
            box=i == 4,
            incomplete=i == 7,
        )
        for i in range(12)
    ]
    edges.extend(
        [
            edge("BOARD", "ANOTHER", source_kind="BOARD_OUTPUT"),
            edge("P4", "FORK"),
        ]
    )
    rows = physical_edge_layout(edges)
    selected, omitted = compact_physical_edge_rows(rows)
    retained = {row.index for row in selected}
    assert omitted > 0
    assert {0, 4, 7, 12, 13}.issubset(retained)
    assert set(range(8)).issubset(retained)  # every ancestor of the diagnostic
    assert len(selected) + omitted == len(rows)


def test_full_layout_preserves_each_segment_exactly_once():
    edges = [
        edge("BOARD", "A", source_kind="BOARD_OUTPUT"),
        edge("A", "B"),
        edge("BOARD", "C", source_kind="BOARD_OUTPUT"),
    ]
    rows = physical_edge_layout(edges)
    assert len(rows) == len(edges)
    assert len({row.index for row in rows}) == len(edges)
    assert [row.edge["segment_id"] for row in rows] == [
        "BOARD->A",
        "A->B",
        "BOARD->C",
    ]
