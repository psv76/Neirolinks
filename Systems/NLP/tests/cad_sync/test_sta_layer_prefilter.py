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
