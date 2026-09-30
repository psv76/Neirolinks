from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from nl_project_2.bulk_actions import (
    BulkActionPreview,
    BulkActionReceipt,
    BulkMapping,
    BulkOwner,
    BulkSelectionSnapshot,
    BulkVariant,
    BulkVariantQuery,
)
from nl_project_2.guided_actions import (
    CandidateQuery,
    CandidateState,
    GuidedAction,
    GuidedActionPreview,
    GuidedActionReceipt,
    GuidedCandidate,
)
from nl_project_2.presentation.bulk_action_dialog import BulkActionDialog
from nl_project_2.presentation.guided_action_dialog import GuidedActionDialog


class FakeGuidedService:
    confirmed = False

    @staticmethod
    def candidates(action, _project_id, _owner_id):
        return CandidateQuery(
            action,
            action.label,
            "401 — Подсветка кухни",
            7,
            (
                GuidedCandidate(
                    "candidate-ok",
                    "A01 / Channel1",
                    "A01",
                    "ЩР-1",
                    CandidateState.SELECTABLE,
                    True,
                    (),
                    "Совместимый свободный канал",
                    technical_identity="A01 / PWM_OUTPUT[0]",
                ),
                GuidedCandidate(
                    "candidate-busy",
                    "A01 / Channel2",
                    "A01",
                    "ЩР-1",
                    CandidateState.UNAVAILABLE,
                    False,
                    ("OCCUPIED",),
                    "Канал уже занят",
                ),
            ),
            "READY",
            "Доступно вариантов: 1",
        )

    @staticmethod
    def preview(action, _project_id, _owner_id, _candidate_id):
        return GuidedActionPreview(
            action,
            action.label,
            "401 — Подсветка кухни",
            "A01 / Channel1",
            ("Назначить выход/канал", "Выбран A01 / Channel1"),
            (),
            (),
            (),
            7,
            "fingerprint",
            "token",
        )

    def confirm(self, preview, *, confirmed):
        assert preview.target_label == "A01 / Channel1"
        assert confirmed
        self.confirmed = True
        return GuidedActionReceipt(
            GuidedAction.OUTPUT,
            GuidedAction.OUTPUT.label,
            7,
            8,
            "CABLE_LINE_ASSIGNMENT",
            1,
            "401 — Подсветка кухни",
            "Назначено: A01 / Channel1",
        )


class FakeBulkService:
    confirmed = False

    @staticmethod
    def selection_snapshot(action, *, project_id, owner_ids):
        owners = tuple(BulkOwner(owner_id, owner_id, "CABLE_LINE") for owner_id in owner_ids)
        return BulkSelectionSnapshot(project_id, 5, action, action.label, owners, "selection")

    @staticmethod
    def candidate_variants(snapshot):
        return BulkVariantQuery(
            snapshot.action,
            snapshot.action_label,
            snapshot.fingerprint,
            snapshot.project_revision,
            (
                BulkVariant(
                    "variant",
                    "WB-LED / Channel",
                    "controller.wb_led_v1",
                    "product.wirenboard.wb_led_v1",
                    "PWM_OUTPUT",
                    True,
                    2,
                    True,
                    True,
                ),
            ),
            "READY",
        )

    @staticmethod
    def preview(snapshot, *, chosen_variant_identity, proposed_designations):
        assert chosen_variant_identity == "variant"
        return BulkActionPreview(
            snapshot.project_id,
            snapshot.project_revision,
            snapshot.action,
            snapshot.action_label,
            2,
            "variant",
            "WB-LED / Channel",
            (
                BulkMapping("line-1", "101", "A01", "EXISTING", ("Channel1",), "map", "ASSIGN", 1),
                BulkMapping("line-2", "102", "A01", "EXISTING", ("Channel2",), "map", "ASSIGN", 1),
            ),
            (),
            proposed_designations,
            0,
            0,
            2,
            (),
            (),
            "preview",
            "token",
            "correlation",
        )

    def confirm(self, preview, *, confirmed):
        assert preview.confirmable and confirmed
        self.confirmed = True
        return BulkActionReceipt(
            "receipt",
            "command",
            preview.action,
            preview.action_label,
            2,
            (),
            2,
            5,
            6,
            "APPLIED",
            "correlation",
            "variant",
        )


def test_guided_dialog_keeps_blocked_reason_and_confirms_full_preview(qtbot, monkeypatch):
    service = FakeGuidedService()
    dialog = GuidedActionDialog(service, GuidedAction.OUTPUT, "project", "line-1")
    qtbot.addWidget(dialog)
    assert dialog.candidates.rowCount() == 2
    assert dialog.candidates.item(1, 2).text() == "Канал уже занят"
    dialog.candidates.selectRow(0)
    dialog.build_preview()
    assert "A01 / Channel1" in dialog.preview_text.toPlainText()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    dialog.confirm_preview()
    assert service.confirmed


def test_bulk_dialog_uses_variants_preview_and_all_or_none_confirm(qtbot, monkeypatch):
    service = FakeBulkService()
    dialog = BulkActionDialog(service, GuidedAction.OUTPUT, "project", ("line-1", "line-2"))
    qtbot.addWidget(dialog)
    assert dialog.summary.text().startswith("Выбрано: 2")
    assert dialog.variants.item(0, 2).text() == "Да"
    dialog.variants.selectRow(0)
    dialog.build_preview()
    assert "101 → A01 / Channel1" in dialog.preview_text.toPlainText()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    dialog.confirm_preview()
    assert service.confirmed
