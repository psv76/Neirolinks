from nl_project_2.presentation.specification_workspace import SpecificationWorkspaceDialog
from nl_project_2.specification import SpecificationService


def test_specification_ui_displays_unknown_and_trace(qtbot, database):
    dialog = SpecificationWorkspaceDialog(
        SpecificationService(database.engine), database.test_project_id
    )
    qtbot.addWidget(dialog)
    assert dialog.table.objectName() == "specificationTable"
    assert dialog.workshop.objectName() == "workshopControlTable"
    assert "Известная сумма NEIROLINKS" in dialog.summary.text()
