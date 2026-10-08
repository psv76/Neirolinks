from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton
from sqlalchemy import func, select

from nl_project_2.cables import CableService
from nl_project_2.integration import IntegratedUiService
from nl_project_2.integration.human_models import (
    ActionableIssue,
    CableJournalRow,
    CableJournalSegment,
    EngineeringDetails,
    NavigationTarget,
    OperationJournalRow,
    UserStatus,
    aggregate_status,
)
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    cable_line,
    dwg_document_binding,
    dwg_observation,
    dwg_scan,
    operation_journal,
    project,
)
from nl_project_2.presentation.documents_workspace import DocumentsWorkspace


def _issue(status: UserStatus, code: str, *, blocking: bool = False) -> ActionableIssue:
    return ActionableIssue(
        status=status,
        title="Проверка",
        reason=f"Причина {code}",
        impact="Влияние на выпуск",
        blocking=blocking,
        required_action="Исправить данные",
        navigation=NavigationTarget("Линии", "CABLE_LINE", "line-1"),
        section="CABLES",
        source_kind="CABLE_LINE",
        source_id="line-1",
        engineering=EngineeringDetails(code, "rule", "source", ("technical-id",)),
    )


def test_four_human_statuses_have_deterministic_priority_and_keep_engineering_details():
    allowed = {status.value for status in UserStatus}
    assert allowed == {
        "Готово",
        "Требуется действие",
        "Нужны данные",
        "Ошибка проекта",
    }
    summary = aggregate_status(
        (
            _issue(UserStatus.ACTION_REQUIRED, "ACTION"),
            _issue(UserStatus.DATA_REQUIRED, "DATA"),
            _issue(UserStatus.PROJECT_ERROR, "ERROR", blocking=True),
        )
    )
    assert summary.status is UserStatus.PROJECT_ERROR
    assert summary.blocking
    assert {item.machine_code for item in summary.engineering} == {"ACTION", "DATA", "ERROR"}
    ready = aggregate_status(())
    assert ready.status is UserStatus.READY


class _DocumentsService:
    @staticmethod
    def cable_journal_rows(_project_id):
        return (
            CableJournalRow(
                "line-10",
                "10",
                "Вентилятор",
                "POWER",
                "ЩР-1",
                "Дом",
                "Кухня",
                "NYM",
                "По полу",
                "001.PND25",
                "12.5",
                "Автоматически",
                "Сумма физических сегментов",
                UserStatus.ACTION_REQUIRED,
                (
                    CableJournalSegment(
                        "segment-a",
                        "Щит",
                        "Коробка",
                        "По полу",
                        "001.PND25",
                        "7.0",
                    ),
                    CableJournalSegment(
                        "segment-b",
                        "Коробка",
                        "Вентилятор",
                        "По полу",
                        "001.PND25",
                        "5.5",
                    ),
                ),
            ),
            CableJournalRow(
                "line-2",
                "2",
                "Свет",
                "LIGHTING",
                "ЩР-1",
                "Дом",
                "Спальня",
                "ВВГнг-LS",
                "По потолку",
                "",
                "8",
                "Вручную",
                "Подтверждённая полная длина",
                UserStatus.READY,
                (),
            ),
        )

    @staticmethod
    def validation_items(_project_id):
        return (_issue(UserStatus.ACTION_REQUIRED, "ACTION"),)

    @staticmethod
    def operation_rows(_project_id):
        return (
            OperationJournalRow(
                "operation-technical-id",
                "2026-08-23 12:00:00",
                "Изменены данные кабельных линий",
                "Изменены две линии",
                "Успешно",
                "Линии 2 и 10",
                4,
                5,
                "correlation-technical-id",
                "command-technical-id",
                "OPERATION_JOURNAL",
            ),
        )


def test_documents_workspace_has_working_in_app_cable_journal_and_excel_export(qtbot):
    widget = DocumentsWorkspace(_DocumentsService(), "project")
    qtbot.addWidget(widget)
    assert [widget.tabs.tabText(index) for index in range(widget.tabs.count())] == [
        "Кабельный журнал",
        "Проверки",
        "Журнал операций",
    ]
    tree = widget.cable_journal.tree
    assert tree.topLevelItemCount() == 2
    assert [tree.topLevelItem(index).text(0) for index in range(2)] == ["2", "10"]
    branched = next(
        tree.topLevelItem(index)
        for index in range(tree.topLevelItemCount())
        if tree.topLevelItem(index).text(0) == "10"
    )
    assert branched.text(1) == "Вентилятор"
    assert branched.childCount() == 2
    assert all(branched.child(index).text(0) == "" for index in range(2))
    assert all(
        branched.child(index).data(0, Qt.ItemDataRole.UserRole) == "line-10" for index in range(2)
    )
    export_button = widget.findChild(QPushButton, "cableJournalExportExcelButton")
    assert export_button is not None
    assert export_button.text() == "Экспорт в Excel"

    widget.cable_journal.search.setText("кухня")
    assert not branched.isHidden()
    other = next(
        tree.topLevelItem(index)
        for index in range(tree.topLevelItemCount())
        if tree.topLevelItem(index).text(0) == "2"
    )
    assert other.isHidden()
    widget.cable_journal.search.clear()
    widget.cable_journal.status_filter.setCurrentIndex(
        widget.cable_journal.status_filter.findData("Готово")
    )
    assert branched.isHidden() and not other.isHidden()

    opened = []
    widget.lineRequested.connect(opened.append)
    widget.cable_journal.status_filter.setCurrentIndex(0)
    widget.cable_journal.select_line("line-10")
    widget.cable_journal._open_line()
    assert opened == ["line-10"]

    operations = widget.operations.table
    visible = " ".join(
        operations.item(0, column).text() for column in range(operations.columnCount())
    )
    assert "technical-id" not in visible
    assert "command-technical-id" in operations.item(0, 0).toolTip()


def test_scalar_line_edit_creates_one_canonical_human_operation(database):
    project_id = database.test_project_id
    line_id = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            cable_line.insert().values(
                id=line_id,
                project_id=project_id,
                designation="LINE.1",
                system_kind="POWER",
                cable_facts_json={"BOARD": "OLD", "CABLE_TYPE": "NYM"},
                lifecycle="ACTIVE",
            )
        )
    service = CableService(database.engine)
    service.batch_update_line_fields(
        project_id=project_id,
        edits=(
            {"cable_line_id": line_id, "field": "BOARD", "value": "ЩР-1"},
            {"cable_line_id": line_id, "field": "CABLE_TYPE", "value": "ВВГнг-LS"},
        ),
    )
    with database.engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(operation_journal)
                .where(operation_journal.c.project_id == project_id)
            )
            == 1
        )
        stored = (
            connection.execute(
                select(operation_journal).where(operation_journal.c.project_id == project_id)
            )
            .mappings()
            .one()
        )
    assert stored["project_revision_after"] == stored["project_revision_before"] + 1
    assert stored["command_type"] == "LINE_SCALAR_BATCH_UPDATE"
    assert stored["summary_json"]["canonical_fact_count"] == 2

    integrated = IntegratedUiService(
        constructor=None,
        cables=service,
        panels=None,
        specification=None,
        engine=database.engine,
    )
    row = integrated.operation_rows(project_id)[0]
    assert row.action == "Изменены данные кабельных линий"
    assert row.status == "Успешно"
    assert "Изменений: 2" in row.summary


def test_operation_presenter_removes_trace_and_sql_from_main_summary(database):
    project_id = database.test_project_id
    command_id = new_id()
    now = datetime.now(UTC)
    with database.engine.begin() as connection:
        connection.execute(
            operation_journal.insert().values(
                id=new_id(),
                project_id=project_id,
                command_id=command_id,
                command_type="TEST_ACTION",
                project_revision_before=0,
                project_revision_after=0,
                correlation_id=command_id,
                status="FAILED",
                started_at_utc=now,
                completed_at_utc=now,
                summary_json={
                    "human_summary": "Не удалось завершить действие",
                    "message": "Traceback\nSELECT * FROM hidden_table\nПроверьте данные",
                },
            )
        )
    rows = IntegratedUiService(
        constructor=None,
        cables=None,
        panels=None,
        specification=None,
        engine=database.engine,
    ).operation_rows(project_id)
    main_text = " ".join((rows[0].action, rows[0].summary, rows[0].status, rows[0].context))
    assert "traceback" not in main_text.casefold()
    assert "select " not in main_text.casefold()
    assert "Проверьте данные" in main_text


def test_issue_presenter_aggregates_all_available_application_contours(database):
    class Cables:
        @staticmethod
        def line_cards(_project_id):
            return ()

    class Constructor:
        @staticmethod
        def list_cable_assignments(_project_id):
            return ()

        @staticmethod
        def list_resources(_project_id):
            return ()

        @staticmethod
        def validate_required_resources(_project_id):
            return ()

    class EquipmentActions:
        @staticmethod
        def empty_instance_issues(*, project_id):
            del project_id
            return (
                SimpleNamespace(
                    target_label="MR.1",
                    target_id="instance-empty",
                    code="EMPTY_INSTANCE_ACTION_REQUIRED",
                ),
            )

    class Distribution:
        @staticmethod
        def list_instances(_project_id):
            return (
                {
                    "id": "psu-overload",
                    "designation": "PSU.1",
                    "equipment_class": "AC_DC_POWER_SUPPLY",
                },
            )

        @staticmethod
        def assess_psu_instance(_project_id, _instance_id):
            return SimpleNamespace(status="OVERLOADED", trace=("load > limit",))

    class Automation:
        @staticmethod
        def list_led_profiles(_project_id):
            return (
                {
                    "id": "led-profile",
                    "cable_line_id": "led-line",
                    "cable_designation": "LED.1",
                },
            )

        @staticmethod
        def calculate_profile(_project_id, _profile_id):
            return SimpleNamespace(packing=SimpleNamespace(status="DATA_INCOMPLETE"))

    class Buses:
        @staticmethod
        def list_buses(_project_id):
            return ({"id": "bus-1", "designation": "BUS.1"},)

        @staticmethod
        def get_bus(_project_id, _bus_id):
            return {"endpoints": ()}

        @staticmethod
        def connection_states(_project_id, _bus_id):
            return ()

    class Panels:
        @staticmethod
        def list_boards(_project_id):
            return ({"id": "board-1", "board_kind": "BOARD"},)

        @staticmethod
        def board_layout(*, project_id, board_id):
            del project_id, board_id
            return {
                "rails": (),
                "instances": (
                    {
                        "id": "unplaced-instance",
                        "designation": "QF.1",
                        "layout_state": "UNPLACED",
                    },
                ),
            }

    class Specification:
        @staticmethod
        def build(_project_id):
            return {
                "issues": (
                    SimpleNamespace(
                        message="Нарушена область поставки",
                        code="SUPPLY_SCOPE_CONFLICT",
                        source_kind="PROJECT_INSTANCE",
                        source_id="spec-instance",
                    ),
                ),
                "rows": (),
            }

    service = IntegratedUiService(
        constructor=Constructor(),
        cables=Cables(),
        panels=Panels(),
        specification=Specification(),
        engine=database.engine,
        equipment_actions=EquipmentActions(),
        distribution=Distribution(),
        automation=Automation(),
        buses=Buses(),
    )
    with database.engine.connect() as connection:
        before = connection.scalar(
            select(project.c.project_revision).where(project.c.id == database.test_project_id)
        )
    issues = service.issues(database.test_project_id)
    with database.engine.connect() as connection:
        after = connection.scalar(
            select(project.c.project_revision).where(project.c.id == database.test_project_id)
        )
    assert before == after
    assert {item.section for item in issues} >= {
        "EQUIPMENT",
        "DISTRIBUTION",
        "AUTOMATION",
        "BUSES",
        "PANELS",
        "SPECIFICATION",
    }
    assert all(
        item.reason and item.impact and item.required_action and item.navigation.section
        for item in issues
    )


def test_frame_ip44_dwg_diagnostic_is_actionable_without_live_cad(database):
    project_id = database.test_project_id
    binding_id = new_id()
    scan_id = new_id()
    observation_id = new_id()
    now = datetime.now(UTC)
    with database.engine.begin() as connection:
        connection.execute(
            dwg_document_binding.insert().values(
                id=binding_id,
                project_id=project_id,
                application_uuid=new_id(),
                normalized_last_path="test-only.dwg",
                document_signature="test-only",
                fingerprint="test-only",
                confirmed_at_utc=now,
                status="CONFIRMED",
            )
        )
        connection.execute(
            dwg_scan.insert().values(
                id=scan_id,
                project_id=project_id,
                dwg_document_binding_id=binding_id,
                adapter_version="TEST",
                protocol_version="TEST",
                contract_version="TEST",
                started_at_utc=now,
                completed_at_utc=now,
                document_facts_json={},
                content_sha256="0" * 64,
                status="ACCEPTED",
            )
        )
        connection.execute(
            dwg_observation.insert().values(
                id=observation_id,
                project_id=project_id,
                dwg_scan_id=scan_id,
                entity_handle="A1B2",
                effective_block_name="FRAME",
                layer_name="0",
                space_name="MODEL",
                geometry_json={},
                raw_attributes_json={},
                diagnostics_json=(
                    {
                        "code": "FRAME_IP44_POSTS_DEFICIT",
                        "message": "Для рамки IP44 недостаточно постов",
                        "severity": "ERROR",
                        "blocks_acceptance": True,
                        "field": "MECHANISM_COUNT",
                    },
                ),
            )
        )
    with database.engine.connect() as connection:
        before = connection.scalar(
            select(project.c.project_revision).where(project.c.id == project_id)
        )
    issue = next(
        item
        for item in IntegratedUiService(
            constructor=None,
            cables=None,
            panels=None,
            specification=None,
            engine=database.engine,
        ).issues(project_id)
        if item.code == "FRAME_IP44_POSTS_DEFICIT"
    )
    with database.engine.connect() as connection:
        after = connection.scalar(
            select(project.c.project_revision).where(project.c.id == project_id)
        )
    assert before == after
    assert issue.status is UserStatus.PROJECT_ERROR
    assert issue.blocking
    assert issue.navigation.section == "DWG"
    assert issue.navigation.entity_id == observation_id
    assert issue.navigation.context == "A1B2"
    assert issue.engineering.technical_ids == ("A1B2",)
