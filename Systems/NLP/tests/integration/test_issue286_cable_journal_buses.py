"""In-app cable journal must include the same buses as Lines/Excel."""

from PySide6.QtCore import Qt

from nl_project_2.integration.human_models import UserStatus
from nl_project_2.integration.human_service import IntegratedUiService
from nl_project_2.presentation.documents_workspace import CableJournalWidget


class _FakeBuses:
    @staticmethod
    def journal_cards(_project_id):
        return [
            {
                "id": "bus-941",
                "designation": "941",
                "bus_kind": "DALI",
                "load_name": "DALI · LIGHT_IN_DALI_230V",
                "board": "A04 / DA1",
                "building_names": "Дом_2",
                "room_names": "Гостиная",
                "unresolved_room_names": (),
                "cable_type": "2x1,5",
                "mount_way": "По полу",
                "gofra_id": "120.PP25",
                "effective_m": "25",
                "length_mode": "Автоматическая",
                "length_explanation": "По фактическим точкам",
            },
            {
                "id": "bus-903",
                "designation": "903",
                "bus_kind": "RS485",
                "load_name": "RS485 · SENSOR_MSW",
                "board": "WB-21 / RS485-1",
                "building_names": "Дом_2",
                "room_names": "Прихожая",
                "unresolved_room_names": (),
                "cable_type": "FTP 5e",
                "mount_way": "По потолку",
                "gofra_id": "",
                "effective_m": None,
                "length_mode": "Не рассчитана",
                "length_explanation": "",
            },
            {
                "id": "bus-946",
                "designation": "946",
                "bus_kind": "DALI",
                "load_name": "DALI",
                "board": "A02 / DA3",
                "building_names": "",
                "room_names": "",
                "unresolved_room_names": (),
                "cable_type": "",
                "mount_way": "",
                "gofra_id": "",
                "effective_m": None,
                "length_mode": "Не рассчитана",
                "length_explanation": "",
            },
        ]

    @staticmethod
    def journal_topology(_project_id, bus_id):
        if bus_id == "bus-946":
            return {"edges": ()}
        source = {"label": "A04 / DA1" if bus_id == "bus-941" else "WB-21 / RS485-1"}
        return {
            "edges": (
                {
                    "segment_id": "segment-" + bus_id,
                    "source": source,
                    "target": {"label": "941.001" if bus_id == "bus-941" else "903.001"},
                    "mount_way": "По полу",
                    "gofra_id": "120.PP25",
                    "cable_length_m": "20.42" if bus_id == "bus-941" else None,
                },
            )
        }


def test_journal_includes_dali_rs485_and_true_physical_segments(qtbot):
    service = IntegratedUiService(
        constructor=None,
        cables=None,
        panels=None,
        specification=None,
        buses=_FakeBuses(),
    )
    # No ordinary lines exist in this fixture.
    service.line_statuses = lambda _project_id: {}
    rows = service.cable_journal_rows("project")
    assert [row.cable_id for row in rows] == ["903", "941", "946"]
    ready = rows[1]
    assert ready.status == UserStatus.READY
    assert ready.board == "A04 / DA1"
    assert ready.total_length_m == "25"
    assert len(ready.segments) == 1
    assert ready.segments[0].source_label == "A04 / DA1"
    assert ready.segments[0].target_label == "941.001"
    assert ready.segments[0].length_m == "20.42"
    assert rows[0].status == UserStatus.DATA_REQUIRED
    assert rows[0].segments[0].length_m is None
    assert rows[2].status == UserStatus.DATA_REQUIRED
    assert rows[2].segments == ()

    journal = CableJournalWidget(service, "project")
    qtbot.addWidget(journal)
    assert journal.tree.topLevelItemCount() == 3
    assert journal.tree.topLevelItem(1).text(0) == "941"
    assert journal.tree.topLevelItem(1).text(9) == "25"
    assert journal.tree.topLevelItem(1).childCount() == 1
    assert journal.tree.topLevelItem(1).child(0).text(1) == "Участок: A04 / DA1 → 941.001"
    assert journal.tree.topLevelItem(1).data(0, Qt.ItemDataRole.UserRole) == "bus-941"
    opened = []
    journal.lineRequested.connect(opened.append)
    assert journal.select_line("bus-941")
    journal._open_line()
    assert opened == ["bus-941"]

    journal.search.setText("941")
    assert sum(not journal.tree.topLevelItem(i).isHidden() for i in range(3)) == 1
    journal.search.clear()
    journal.status_filter.setCurrentIndex(
        journal.status_filter.findData(UserStatus.DATA_REQUIRED.value)
    )
    assert sum(not journal.tree.topLevelItem(i).isHidden() for i in range(3)) == 2
