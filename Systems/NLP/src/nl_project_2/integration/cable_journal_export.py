# ruff: noqa: E501
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import select

from nl_project_2.persistence.schema import board, bus, instance_resource, project_instance

_HEADERS = (
    "Откуда\n(щит)",
    "Куда\n(помещение)",
    "ID\nлинии",
    "Назначение линии",
    "Тип кабеля",
    "Способ прокладки",
    "Длина линии, м",
    "Система",
    "Точка\nподключения",
)


def export_cable_journal_xlsx(service, project_id: str, path: str | Path) -> Path:
    """Export the current Project cable journal and cable totals to one XLSX."""

    target = Path(path)
    rows = _journal_rows(service, project_id)
    totals: dict[str, dict[str, Decimal | int]] = defaultdict(
        lambda: {"length": Decimal("0"), "count": 0}
    )
    for row in rows:
        cable_type = str(row[4] or "").strip() or "Не указан"
        length = _decimal(row[6])
        if length is not None:
            totals[cable_type]["length"] += length
        totals[cable_type]["count"] += 1

    summary_rows = [
        (cable_type, values["length"], values["count"])
        for cable_type, values in sorted(totals.items(), key=lambda item: item[0].casefold())
    ]
    _write_xlsx(target, rows, summary_rows)
    return target


def _journal_rows(service, project_id: str) -> list[tuple]:
    result: list[tuple] = []

    for card in service.cables.line_cards(project_id):
        connection_point = ""
        try:
            topology = service.cables.topology(project_id, card["id"])
            root = dict(topology.get("root_endpoint") or {})
            if root.get("kind") == "FIELD_PORT":
                connection_point = str(root.get("reference") or root.get("label") or "")
        except Exception:
            connection_point = ""

        result.append(
            (
                str(card.get("board") or ""),
                str(card.get("room_names") or ""),
                str(card.get("designation") or ""),
                str(card.get("load_name") or ""),
                str(card.get("cable_type") or ""),
                str(card.get("mount_way") or ""),
                _decimal(card.get("effective_m")),
                str(card.get("system_kind") or ""),
                connection_point,
            )
        )

    if service.buses is not None:
        board_by_bus = _bus_board_designations(service.engine, project_id)
        for card in service.buses.journal_cards(project_id):
            root = service.buses.journal_topology(project_id, card["id"]).get("root_endpoint") or {}
            result.append(
                (
                    board_by_bus.get(str(card["id"]), ""),
                    str(card.get("room_names") or ""),
                    str(card.get("designation") or ""),
                    str(card.get("load_name") or ""),
                    str(card.get("cable_type") or ""),
                    str(card.get("mount_way") or ""),
                    _decimal(card.get("effective_m")),
                    str(card.get("system_kind") or card.get("bus_kind") or ""),
                    str(root.get("label") or root.get("reference") or ""),
                )
            )

    return sorted(result, key=lambda row: _natural_key(str(row[2])))


def _bus_board_designations(engine, project_id: str) -> dict[str, str]:
    if engine is None:
        return {}
    with engine.connect() as connection:
        rows = connection.execute(
            select(bus.c.id, board.c.designation)
            .select_from(bus)
            .join(instance_resource, instance_resource.c.id == bus.c.root_resource_id)
            .join(project_instance, project_instance.c.id == instance_resource.c.project_instance_id)
            .outerjoin(board, board.c.id == project_instance.c.board_id)
            .where(bus.c.project_id == project_id, bus.c.lifecycle == "ACTIVE")
        ).all()
    return {str(bus_id): str(designation or "") for bus_id, designation in rows}


def _decimal(value) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _natural_key(value: str) -> tuple:
    import re

    return tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value))


def _cell(ref: str, value, *, style: int = 0) -> str:
    style_attr = f' s="{style}"' if style else ""
    if isinstance(value, Decimal):
        return f'<c r="{ref}"{style_attr}><v>{value}</v></c>'
    if isinstance(value, int):
        return f'<c r="{ref}"{style_attr}><v>{value}</v></c>'
    text = "" if value is None else str(value)
    return (
        f'<c r="{ref}" t="inlineStr"{style_attr}><is><t xml:space="preserve">'
        f'{escape(text)}</t></is></c>'
    )


def _col_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _journal_sheet_xml(rows: list[tuple]) -> str:
    xml_rows = [
        '<row r="1" ht="27" customHeight="1">'
        + _cell("A1", "Кабельный журнал", style=1)
        + "</row>",
        '<row r="2" ht="34" customHeight="1">'
        + "".join(_cell(f"{_col_name(i)}2", value, style=2) for i, value in enumerate(_HEADERS, 1))
        + "</row>",
    ]
    for row_index, row in enumerate(rows, 3):
        cells = []
        for col_index, value in enumerate(row, 1):
            style = 4 if col_index == 7 else 3
            cells.append(_cell(f"{_col_name(col_index)}{row_index}", value, style=style))
        xml_rows.append(f'<row r="{row_index}">' + "".join(cells) + "</row>")

    last = max(2, len(rows) + 2)
    return _worksheet_xml(
        "".join(xml_rows),
        f"A1:I{last}",
        widths=(15, 31, 11, 32, 17, 20, 14, 19, 23),
        merge="A1:I1",
        autofilter=f"A2:I{last}",
    )


def _summary_sheet_xml(rows: list[tuple[str, Decimal, int]]) -> str:
    headers = ("Тип кабеля", "Итого, м", "Количество линий")
    xml_rows = [
        '<row r="1" ht="27" customHeight="1">'
        + _cell("A1", "Итоги по кабелю", style=1)
        + "</row>",
        '<row r="2" ht="28" customHeight="1">'
        + "".join(_cell(f"{_col_name(i)}2", value, style=2) for i, value in enumerate(headers, 1))
        + "</row>",
    ]
    for row_index, (cable_type, length, count) in enumerate(rows, 3):
        xml_rows.append(
            f'<row r="{row_index}">'
            + _cell(f"A{row_index}", cable_type, style=3)
            + _cell(f"B{row_index}", length, style=4)
            + _cell(f"C{row_index}", count, style=3)
            + "</row>"
        )
    last = max(2, len(rows) + 2)
    return _worksheet_xml(
        "".join(xml_rows),
        f"A1:C{last}",
        widths=(24, 15, 18),
        merge="A1:C1",
        autofilter=f"A2:C{last}",
    )


def _worksheet_xml(
    rows_xml: str,
    dimension: str,
    *,
    widths: tuple[int, ...],
    merge: str,
    autofilter: str,
) -> str:
    cols = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(widths, 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="{dimension}"/>
<sheetViews><sheetView workbookViewId="0"><pane ySplit="2" topLeftCell="A3" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
<cols>{cols}</cols>
<sheetData>{rows_xml}</sheetData>
<autoFilter ref="{autofilter}"/>
<mergeCells count="1"><mergeCell ref="{merge}"/></mergeCells>
<pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>
<pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>
</worksheet>'''


def _write_xlsx(path: Path, rows: list[tuple], summary_rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _ROOT_RELS)
        archive.writestr("xl/workbook.xml", _WORKBOOK)
        archive.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        archive.writestr("xl/styles.xml", _STYLES)
        archive.writestr("xl/worksheets/sheet1.xml", _journal_sheet_xml(rows))
        archive.writestr("xl/worksheets/sheet2.xml", _summary_sheet_xml(summary_rows))


_CONTENT_TYPES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>'''

_ROOT_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''

_WORKBOOK = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets>
<sheet name="Кабельный журнал" sheetId="1" r:id="rId1"/>
<sheet name="Итоги по кабелю" sheetId="2" r:id="rId2"/>
</sheets>
</workbook>'''

_WORKBOOK_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''

_STYLES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="3">
<font><sz val="10"/><name val="Arial"/></font>
<font><b/><sz val="16"/><name val="Arial"/></font>
<font><b/><sz val="10"/><name val="Arial"/></font>
</fonts>
<fills count="3">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFD9EAF7"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border/>
<border><left style="thin"><color rgb="FFB7B7B7"/></left><right style="thin"><color rgb="FFB7B7B7"/></right><top style="thin"><color rgb="FFB7B7B7"/></top><bottom style="thin"><color rgb="FFB7B7B7"/></bottom></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="5">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="2" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
<xf numFmtId="1" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''
