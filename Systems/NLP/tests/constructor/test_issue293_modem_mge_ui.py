"""Issue #293: operator-readable semantics, no live project modifications."""
from nl_project_2.constructor import ConstructorService
from nl_project_2.presentation.constructor_workspace import ConstructorWorkspaceDialog


def test_mge_vout_shared_switch_group_is_visible_in_constructor(database, qtbot):
    pid=database.test_project_id
    service=ConstructorService(database.engine)
    service.create_instance(project_id=pid,designation="MGE.TEST",
                            passport_key="gateway.wirenboard.wb_mge_v3_shared_vout",
                            product_key="product.wirenboard.wb_mge_v3_shared_vout",
                            supply_scope="NEIROLINKS")
    widget=ConstructorWorkspaceDialog(service,pid)
    qtbot.addWidget(widget)
    names=[]
    for row in range(widget.resources_table.rowCount()):
        if widget.resources_table.item(row,0).text()!="MGE.TEST":
            continue
        if widget.resources_table.item(row,1).text().startswith("Vout"):
            names.append(widget.resources_table.item(row,4).text())
    assert names==["Общее включение Vout-1 и Vout-2"]*2


def test_modem_installation_is_separate_from_mod_installation_in_ui(database,qtbot):
    service=ConstructorService(database.engine)
    widget=ConstructorWorkspaceDialog(service,database.test_project_id)
    qtbot.addWidget(widget)
    kinds={widget.relation_kind_combo.itemData(i):widget.relation_kind_combo.itemText(i)
           for i in range(widget.relation_kind_combo.count())}
    assert kinds["MODEM_INSTALLATION"]=="Установка 4G-модема в слот MODEM"
    assert kinds["MODULE_INSTALLATION"]=="Установка модуля в MOD-слот"
