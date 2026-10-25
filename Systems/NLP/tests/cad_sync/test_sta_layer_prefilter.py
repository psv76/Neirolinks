from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from tools.autocad_sta_bridge import (
    _scan,
    _scan_handles,
    _source_metadata,
    is_working_layer_for_scan,
)

_EXPENSIVE = {
    "EffectiveName",
    "Name",
    "Handle",
    "InsertionPoint",
    "IsDynamicBlock",
    "HasAttributes",
    "GetAttributes",
}


class Block:
    def __init__(self, layer, handle, *, name="SOCKET_IN", forbidden=False, layer_error=None):
        self.reads = []
        self.forbidden = forbidden
        self.layer_error = layer_error
        self.ObjectName = "AcDbBlockReference"
        self.Layer = layer
        self.EffectiveName = self.Name = name
        self.Handle = handle
        self.InsertionPoint = (1, 2, 0)
        self.IsDynamicBlock = name == "DALI_GROUP"
        self.HasAttributes = True

    def __getattribute__(self, key):
        if key in _EXPENSIVE or key in {"ObjectName", "Layer"}:
            reads = object.__getattribute__(self, "reads")
            reads.append(key)
            if key in _EXPENSIVE and object.__getattribute__(self, "forbidden"):
                raise AssertionError(f"Excluded entity read: {key}")
            if key == "Layer" and object.__getattribute__(self, "layer_error"):
                raise RuntimeError("Layer unavailable")
        return object.__getattribute__(self, key)

    def GetAttributes(self):
        return (SimpleNamespace(TagString="LABEL", TextString="fixture"),)


class ModelSpace:
    def __init__(self, entities):
        self.entities = entities
        self.passes = 0

    def __iter__(self):
        self.passes += 1
        assert self.passes == 1, "Unexpected second ModelSpace traversal"
        return iter(self.entities)


class Blocks:
    def __init__(self):
        self.calls = []

    def Item(self, name):
        self.calls.append(name)
        assert not name.startswith("EXCLUDED")
        return (SimpleNamespace(ObjectName="AcDbAttributeDefinition", TagString="LABEL"),)


class Document:
    Name = "fixture.dwg"
    FullName = "C:/fixture/fixture.dwg"
    ReadOnly = False
    Saved = True

    def __init__(self, entities):
        self.ModelSpace = ModelSpace(entities)
        self.Blocks = Blocks()

    def GetVariable(self, name):
        assert name == "DBMOD"
        return 0


VALID = [
    "100_Socket",
    "200_Keys",
    "300_Общий свет",
    "400_LED",
    "500_Sensors",
    "600_HVAC",
    "700_HDMI",
    "800_Network",
    "900_Bus",
]
INVALID = ["300", "300_", "ARCH_WALLS", "350_X", "POWER", "DALI_GROUPS", "300_ Свет", "400_Свет "]


@pytest.mark.parametrize("layer", VALID)
def test_working_layer_predicate(layer):
    assert is_working_layer_for_scan(layer) is True


@pytest.mark.parametrize("layer", [*INVALID, None, 300, b"300_Light", ""])
def test_invalid_layer_predicate(layer):
    assert is_working_layer_for_scan(layer) is False


def test_mixed_scan_filters_before_any_expensive_read_and_preserves_payloads():
    accepted = [
        Block(layer, str(i), name="DALI_GROUP" if i in (2, 3) else "SOCKET_IN")
        for i, layer in enumerate(VALID)
    ]
    rejected = [
        Block(layer, f"X{i}", name=f"EXCLUDED{i}", forbidden=True)
        for i, layer in enumerate(INVALID)
    ]
    nonblock = SimpleNamespace(ObjectName="AcDbLine")  # No Layer property available.
    document = Document([nonblock, *accepted, *rejected])
    progress = []
    result = _scan(
        document, "identity", None, progress.append, include_layer=is_working_layer_for_scan
    )
    legacy = _scan(Document(accepted), "identity")
    assert result["observations"] == legacy["observations"]
    assert result["document_identity"] == "identity"
    assert document.ModelSpace.passes == 1
    assert document.Blocks.calls == ["SOCKET_IN", "DALI_GROUP"]
    assert progress == ["scan_modelspace_started", "scan_modelspace_completed"]
    assert result["source_metadata"] == {
        **_source_metadata(document),
        "layer_filter_applied": True,
        "skipped_block_references": len(rejected),
        "scan_is_complete_for_reconciliation": False,
    }
    for block in rejected:
        assert block.reads == ["ObjectName", "Layer"]
    for block in accepted:
        assert block.reads[:2] == ["ObjectName", "Layer"]
        assert {"EffectiveName", "Handle", "GetAttributes", "InsertionPoint"} <= set(block.reads)


def test_default_positional_scan_still_returns_legacy_and_invalid_layers():
    blocks = [Block(layer, str(i)) for i, layer in enumerate([*VALID, *INVALID])]
    document = Document(blocks)
    result = _scan(document, "identity", None, None)
    assert [row["layer"] for row in result["observations"]] == [*VALID, *INVALID]
    assert set(result) == {"document_identity", "observations", "source_metadata"}
    assert result["source_metadata"] == _source_metadata(document)
    assert all(block.reads.index("EffectiveName") < block.reads.index("Layer") for block in blocks)
    assert document.ModelSpace.passes == 1


@pytest.mark.parametrize("entities", [[], [Block("300_Light", "A")]])
def test_filter_is_non_authoritative_even_when_nothing_was_excluded(entities):
    result = _scan(Document(entities), "identity", include_layer=is_working_layer_for_scan)
    metadata = result["source_metadata"]
    assert metadata["skipped_block_references"] == 0
    assert metadata["layer_filter_applied"] is True
    assert metadata["scan_is_complete_for_reconciliation"] is False
    # Existing envelope conversion retains evidence; it does NOT enforce a deletion gate.
    from nl_project_2.cad_sync.bridge import _batch_from_payload

    assert _batch_from_payload(json.loads(json.dumps(result))).source_metadata == metadata


@pytest.mark.parametrize("failure", ["layer", "predicate"])
def test_failures_propagate_without_partial_success(failure):
    block = Block("300_Light", "B", forbidden=True, layer_error=failure == "layer")
    document = Document([Block("100_First", "A"), block])
    progress = []

    def predicate(layer):
        if layer == "300_Light":
            raise RuntimeError("predicate failed")
        return True

    with pytest.raises(RuntimeError, match="Layer unavailable|predicate failed"):
        _scan(document, "identity", progress=progress.append, include_layer=predicate)
    assert block.reads == ["ObjectName", "Layer"]
    assert "scan_modelspace_completed" not in progress


def test_progress_counts_all_entities_in_single_enumeration():
    rejected = [Block("ARCH_WALLS", str(i), forbidden=True) for i in range(251)]
    progress = []
    result = _scan(
        Document(rejected),
        "identity",
        progress=progress.append,
        include_layer=is_working_layer_for_scan,
    )
    assert progress == [
        "scan_modelspace_started",
        "scan_modelspace_progress_250",
        "scan_modelspace_completed",
    ]
    assert result["observations"] == []
    assert result["source_metadata"]["skipped_block_references"] == 251


def test_incremental_handles_still_include_legacy_layers_without_enumeration():
    block = Block("POWER", "A")
    document = Document([])
    calls = []

    def lookup(handle):
        calls.append(handle)
        return block

    document.HandleToObject = lookup
    result = _scan_handles(document, "identity", ["A"])
    assert calls == ["A"]
    assert document.ModelSpace.passes == 0
    assert result["observations"][0]["layer"] == "POWER"
    assert result["source_metadata"] == _source_metadata(document)


def test_standalone_import_and_lazy_parser_do_not_import_application():
    bridge_path = Path(__file__).resolve().parents[2] / "tools/autocad_sta_bridge.py"
    script = """
import importlib.util, sys
spec = importlib.util.spec_from_file_location('standalone_bridge', sys.argv[1])
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
assert bridge._working_layer_parser.cache_info().misses == 0
assert bridge.is_working_layer_for_scan('300_Свет')
assert not bridge.is_working_layer_for_scan('POWER')
assert bridge._working_layer_parser.cache_info().misses == 1
assert not any(n == 'nl_project_2' or n.startswith('nl_project_2.') for n in sys.modules)
assert 'sqlalchemy' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(bridge_path)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


class CensusBlock(Block):
    def __getattribute__(self, key):
        if key == "Handle":
            object.__getattribute__(self, "reads").append(key)
            return object.__getattribute__(self, key)
        return super().__getattribute__(key)


def census_document(blocks):
    document = Document([])
    document.ModelSpace = tuple(blocks)
    by_handle = {object.__getattribute__(b, "Handle"): b for b in blocks}
    document.HandleToObject = by_handle.__getitem__
    return document


@pytest.mark.parametrize("fallback", [False, True])
def test_census_filters_heavy_work_on_both_paths_and_keeps_tracked(monkeypatch, fallback):
    import tools.autocad_sta_bridge as bridge

    included = [
        CensusBlock("300_Свет", "A1", name="DALI_GROUP"),
        CensusBlock("400_LED", "A2", name="DALI_GROUP"),
        CensusBlock("ARCH", "A3"),
    ]
    excluded = [CensusBlock(layer, f"B{i:X}", forbidden=True) for i, layer in enumerate(INVALID)]
    document = census_document(included + excluded)
    selected_calls = []

    def fingerprint(doc, identity, *, timeout_seconds, handles):
        selected_calls.append(handles)
        if fallback:
            raise RuntimeError("LISP unavailable")
        # Model the selected-only LISP heavy read; real generated code is checked below.
        heavy = bridge._scan_handles(doc, identity, list(handles))
        return {
            "document_identity": identity,
            "handles": list(handles),
            "signatures": dict.fromkeys(handles, "synthetic"),
            "source_metadata": heavy["source_metadata"],
        }

    monkeypatch.setattr(bridge, "_fingerprints", fingerprint)
    result = bridge._scan_working_layers(document, document.FullName, ("A3", "DEAD"))
    assert selected_calls == [("A1", "A2", "A3")]
    assert result["census_before"] == result["census_after"]
    assert len(result["census_before"]) == len(included + excluded)
    assert result["source_metadata"]["scan_mode"] == (
        "FILTERED_COM_FALLBACK" if fallback else "FILTERED_FINGERPRINT"
    )
    assert result["source_metadata"]["scan_is_complete_for_reconciliation"] is False
    assert result["source_metadata"]["skipped_block_references"] == len(excluded)
    assert result["status"] == "REQUIRES_ATTENTION"
    for block in excluded:
        assert block.reads == ["ObjectName", "Handle", "Layer"] * 2
    for block in included:
        assert block.reads.count("GetAttributes") == 1
        assert block.reads.count("EffectiveName") == 1
    assert document.Blocks.calls == ["DALI_GROUP", "SOCKET_IN"]


@pytest.mark.parametrize("change", ["layer", "removed", "added", "identity"])
def test_filtered_read_rejects_census_or_document_drift(monkeypatch, change):
    import tools.autocad_sta_bridge as bridge

    block = CensusBlock("300_Light", "A1")
    document = census_document([block])

    def fingerprint(doc, identity, **kwargs):
        if change == "layer":
            block.Layer = "ARCH"
        elif change == "removed":
            doc.ModelSpace = ()
        elif change == "added":
            doc.ModelSpace += (CensusBlock("ARCH", "B1"),)
        else:
            doc.FullName = "other.dwg"
        return {
            "document_identity": identity,
            "handles": ["A1"],
            "signatures": {"A1": "synthetic"},
            "source_metadata": {},
        }

    monkeypatch.setattr(bridge, "_fingerprints", fingerprint)
    with pytest.raises(RuntimeError, match="changed"):
        bridge._scan_working_layers(document, document.FullName, ())


@pytest.mark.parametrize("failure", ["duplicate", "layer_error", "handle"])
def test_census_errors_stop_before_heavy_properties(monkeypatch, failure):
    import tools.autocad_sta_bridge as bridge

    first = CensusBlock("ARCH", "A1", forbidden=True)
    second = CensusBlock(
        "ARCH",
        "bad" if failure == "handle" else "A1" if failure == "duplicate" else "A2",
        forbidden=True,
        layer_error=failure == "layer_error",
    )
    document = census_document([first, second])
    monkeypatch.setattr(
        bridge, "_fingerprints", lambda *a, **k: pytest.fail("heavy read after failed census")
    )
    with pytest.raises(RuntimeError):
        bridge._scan_working_layers(document, document.FullName, ())


def test_lisp_selected_handles_are_escaped_and_selection_precedes_heavy_reads():
    from tools.autocad_sta_bridge import _fingerprint_lisp, _lisp_string

    code = _fingerprint_lisp(
        Path("C:/temp/fingerprint.txt"),
        handles=("A1", "B2"),
        expected_identity="C:/Project/Тест.dwg",
    )
    assert '(foreach h \'("A1" "B2")' in code
    assert 'ssget "_X"' not in code
    assert code.index("(handent h)") < code.index("(vla-get-EffectiveName o)")
    assert '(strcase "C:/Project/Тест.dwg")' in code
    assert _lisp_string('a"b\\c') == '"a\\"b\\\\c"'
    with pytest.raises(RuntimeError, match="handle"):
        _fingerprint_lisp(Path("out"), handles=('A1") (command',), expected_identity="doc")
    with pytest.raises(ValueError, match="Control"):
        _lisp_string("bad\npath")
    # Default fingerprint still enumerates the full model space.
    assert 'ssget "_X"' in _fingerprint_lisp(Path("out"))


def test_filtered_fallback_metadata_failure_never_returns_partial_success(monkeypatch):
    import tools.autocad_sta_bridge as bridge

    document = census_document([CensusBlock("300_Light", "A1")])

    def failed(*args, **kwargs):
        raise RuntimeError("read failed")

    monkeypatch.setattr(bridge, "_fingerprints", failed)
    document.Blocks.Item = failed
    with pytest.raises(RuntimeError, match="read failed"):
        bridge._scan_working_layers(document, document.FullName, ())
