from nl_project_2.buses import (
    QtNativeRenderer,
    TopologyResult,
    WebViewPrototypeRenderer,
)


def _full_test_object_topology():
    chains = (
        ("1QF", "XT.01", "QFD.01", "KM.01", "301"),
        ("XT.01", "SF.01", "A01/COM1", "A01/K1", "KM.01/COIL"),
        ("XT.01", "QF.02", "FI.01", "PSU.1", "A02/POWER", "A02/PWM1", "302"),
        ("XT.01", "SF.02", "PSU.2", "UPS.01", "WB.01"),
        ("WB.01/RS485-1", "UPS.01/RS485", "A01/RS485", "A02/RS485"),
    )
    nodes = tuple(dict.fromkeys(node for chain in chains for node in chain))
    edges = tuple(
        dict.fromkeys(edge for chain in chains for edge in zip(chain, chain[1:], strict=False))
    )
    return TopologyResult("VERIFIED", nodes, edges, 0, ())


def test_qt_native_and_webview_prototypes_use_identical_full_read_model(qtbot):
    topology = _full_test_object_topology()
    qt_scene = QtNativeRenderer().render(topology)
    web_document = WebViewPrototypeRenderer().render(topology)
    qtbot.addWidget(web_document.view)
    assert len(topology.nodes) == 23
    assert len(topology.edges) == 21
    assert len(qt_scene.items()) == 44
    assert all(node in web_document.html for node in topology.nodes)
    assert web_document.html.count("→") == len(topology.edges)

    changed = TopologyResult(
        topology.status,
        (*topology.nodes, "NEW-NODE"),
        (*topology.edges, ("WB.01", "NEW-NODE")),
        topology.total_length_mm,
        topology.errors,
    )
    assert len(QtNativeRenderer().render(changed).items()) == 46
    changed_web = WebViewPrototypeRenderer().render(changed)
    qtbot.addWidget(changed_web.view)
    assert changed_web.html != web_document.html
