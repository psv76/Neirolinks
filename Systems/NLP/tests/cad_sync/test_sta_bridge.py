from __future__ import annotations

from tools.autocad_sta_bridge import _scan, _write_attributes


class _AttributeDefinition:
    ObjectName = "AcDbAttributeDefinition"
    TagString = "DEVICE_TYPE"


class _Definition:
    def __iter__(self):
        return iter((object(), _AttributeDefinition()))


class _Blocks:
    def __init__(self):
        self.calls = []

    def Item(self, name):
        self.calls.append(name)
        return _Definition()


class _BlockReference:
    ObjectName = "AcDbBlockReference"
    IsDynamicBlock = False
    InsertionPoint = (1, 2, 0)
    Layer = "POWER"
    HasAttributes = False

    def __init__(self, name, handle):
        self.EffectiveName = name
        self.Name = name
        self.Handle = handle


class _Document:
    Name = "fixture.dwg"
    FullName = "C:/fixture/fixture.dwg"
    ReadOnly = False
    Saved = True

    def __init__(self):
        self.Blocks = _Blocks()
        self.ModelSpace = (
            _BlockReference("KNOWN", "A1"),
            _BlockReference("KNOWN", "A2"),
            _BlockReference("UNKNOWN", "A3"),
        )

    @staticmethod
    def GetVariable(name):
        assert name == "DBMOD"
        return 0


def test_scan_caches_definition_metadata_and_tolerates_non_entity_proxy():
    document = _Document()

    result = _scan(document, document.FullName, {"KNOWN"})

    assert document.Blocks.calls == ["KNOWN"]
    assert result["observations"][0]["definition_tags"] == ["DEVICE_TYPE"]
    assert result["observations"][1]["definition_tags"] == ["DEVICE_TYPE"]
    assert result["observations"][2]["definition_tags"] is None


class _WritableAttribute:
    def __init__(self, tag, value, *, fails=False):
        self.TagString = tag
        self._value = value
        self.fails = fails

    @property
    def TextString(self):
        return self._value

    @TextString.setter
    def TextString(self, value):
        if self.fails:
            raise RuntimeError("injected write failure")
        self._value = value


class _WritableBlock:
    ObjectName = "AcDbBlockReference"
    EffectiveName = "SOCKET_IN"
    Layer = "POWER"

    def __init__(self, handle, attribute):
        self.Handle = handle
        self.attribute = attribute

    def GetAttributes(self):
        return (self.attribute,)


class _ModelSpace:
    def __init__(self, blocks):
        self.blocks = {block.Handle: block for block in blocks}

    def Item(self, handle):
        return self.blocks[handle]


class _WritableDocument:
    Saved = False

    def __init__(self, blocks):
        self.ModelSpace = _ModelSpace(blocks)
        self.undo_calls = []

    def HandleToObject(self, handle):
        return self.ModelSpace.Item(handle)

    def StartUndoMark(self):
        self.undo_calls.append("start")

    def EndUndoMark(self):
        self.undo_calls.append("end")


def test_write_uses_one_undo_group_and_reports_nth_partial_without_save():
    first = _WritableBlock("A1", _WritableAttribute("ROOM", "Old 1"))
    second = _WritableBlock("A2", _WritableAttribute("ROOM", "Old 2", fails=True))
    document = _WritableDocument((first, second))
    changes = [
        {
            "handle": handle,
            "tag": "ROOM",
            "old_value": old,
            "new_value": new,
            "expected_block_name": "SOCKET_IN",
            "expected_layer": "POWER",
        }
        for handle, old, new in (
            ("A1", "Old 1", "New 1"),
            ("A2", "Old 2", "New 2"),
        )
    ]

    result = _write_attributes(document, "C:/fixture.dwg", changes)

    assert document.undo_calls == ["start", "end"]
    assert result["status"] == "PARTIAL"
    assert result["readback"] == [{"handle": "A1", "tag": "ROOM", "value": "New 1"}]
    assert result["failures"][0]["handle"] == "A2"
    assert result["no_save_confirmed"] and not result["document_saved"]


def test_expected_old_mismatch_rejects_before_undo_group_or_write():
    block = _WritableBlock("A1", _WritableAttribute("ROOM", "Changed after scan"))
    document = _WritableDocument((block,))

    try:
        _write_attributes(
            document,
            "C:/fixture.dwg",
            [
                {
                    "handle": "A1",
                    "tag": "ROOM",
                    "old_value": "Old snapshot",
                    "new_value": "Project value",
                    "expected_block_name": "SOCKET_IN",
                    "expected_layer": "POWER",
                }
            ],
        )
    except RuntimeError as exc:
        assert "old-value precondition failed" in str(exc)
    else:
        raise AssertionError("stale expected-old precondition was accepted")
    assert document.undo_calls == []
    assert block.attribute.TextString == "Changed after scan"
