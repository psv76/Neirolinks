# ruff: noqa: E501
from __future__ import annotations

from decimal import Decimal
from html import escape
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

_SCOPE_LABELS = {
    "NEIROLINKS": "Поставка NEIROLINKS",
    "CUSTOMER": "Поставка заказчика",
    "ASSEMBLY_WORKSHOP": "Сборочный цех",
    "BY_CONTRACT": "По договору",
    None: "Нужны данные",
}

_HEADERS = (
    "Позиция",
    "Артикул",
    "Количество",
    "Ед.",
    "Поставка",
    "Состояние",
    "В спецификации",
    "В смете",
    "Цена",
    "Стоимость",
    "Примечание",
)


def export_specification_xlsx(service, project_id: str, path: str | Path) -> Path:
    target = Path(path)
    result = service.build(project_id)
    rows = []
    for row in result["rows"]:
        rows.append(
            (
                row.name,
                row.article or "Нужны данные",
                row.quantity,
                row.unit,
                _SCOPE_LABELS.get(row.supply_scope, row.supply_scope or "Нужны данные"),
                _row_status(row),
                "Да" if row.specification_included else "Нет",
                "Да" if row.budget_included else "Нет",
                "Стоимость не указана" if row.unit_price is None else row.unit_price,
                "Стоимость не указана" if row.cost is None else row.cost,
                row.note or "",
            )
        )
    _write_xlsx(target, rows)
    return target


def _row_status(row) -> str:
    if row.article is None or row.quantity is None or row.supply_scope is None:
        return "Нужны данные"
    if row.budget_included and row.cost is None:
        return "Нужны данные"
    return "Готово"


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


def _sheet_xml(rows: list[tuple]) -> str:
    xml_rows = [
        '<row r="1" ht="27" customHeight="1">' + _cell("A1", "Спецификация", style=1) + "</row>",
        '<row r="2" ht="34" customHeight="1">'
        + "".join(_cell(f"{_col_name(i)}2", value, style=2) for i, value in enumerate(_HEADERS, 1))
        + "</row>",
    ]
    numeric_columns = {3, 9, 10}
    for row_index, row in enumerate(rows, 3):
        cells = []
        for col_index, value in enumerate(row, 1):
            style = 4 if col_index in numeric_columns and isinstance(value, (Decimal, int)) else 3
            cells.append(_cell(f"{_col_name(col_index)}{row_index}", value, style=style))
        xml_rows.append(f'<row r="{row_index}">' + "".join(cells) + "</row>")

    last = max(2, len(rows) + 2)
    cols = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate((42, 20, 14, 10, 22, 18, 16, 12, 18, 18, 44), 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="A1:K{last}"/>
<sheetViews><sheetView workbookViewId="0"><pane ySplit="2" topLeftCell="A3" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
<cols>{cols}</cols>
<sheetData>{"".join(xml_rows)}</sheetData>
<autoFilter ref="A2:K{last}"/>
<mergeCells count="1"><mergeCell ref="A1:K1"/></mergeCells>
<pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>
<pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>
</worksheet>'''


def _write_xlsx(path: Path, rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _ROOT_RELS)
        archive.writestr("xl/workbook.xml", _WORKBOOK)
        archive.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        archive.writestr("xl/styles.xml", _STYLES)
        archive.writestr("xl/worksheets/sheet1.xml", _sheet_xml(rows))


_CONTENT_TYPES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>'''

_ROOT_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''

_WORKBOOK = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Спецификация" sheetId="1" r:id="rId1"/></sheets>
</workbook>'''

_WORKBOOK_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
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
