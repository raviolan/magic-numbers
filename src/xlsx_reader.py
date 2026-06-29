from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile
import re
import xml.etree.ElementTree as ET

from models import CellValue, SheetData, WorkbookData


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"a": MAIN_NS, "r": REL_NS}

CELL_REF_RE = re.compile(r"([A-Z]+)(\d+)")


@dataclass
class WorkbookSheetRef:
    name: str
    state: str
    target: str


def column_letters_to_index(column_letters: str) -> int:
    value = 0
    for char in column_letters:
        value = value * 26 + (ord(char) - 64)
    return value


def parse_cell_reference(reference: str) -> tuple[int, int]:
    match = CELL_REF_RE.fullmatch(reference)
    if not match:
        raise ValueError(f"Unsupported cell reference: {reference}")
    column_letters, row = match.groups()
    return int(row), column_letters_to_index(column_letters)


def _load_shared_strings(archive: ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []

    strings: list[str] = []
    for item in root.findall("a:si", NS):
        parts = [node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t")]
        strings.append("".join(parts))
    return strings


def _load_sheet_refs(archive: ZipFile) -> list[WorkbookSheetRef]:
    workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
    rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels_root.findall(f"{{{PACKAGE_REL_NS}}}Relationship")
    }
    sheets: list[WorkbookSheetRef] = []
    for sheet in workbook_root.find("a:sheets", NS) or []:
        rel_id = sheet.attrib[f"{{{REL_NS}}}id"]
        sheets.append(
            WorkbookSheetRef(
                name=sheet.attrib["name"],
                state=sheet.attrib.get("state", "visible"),
                target=f"xl/{rel_map[rel_id]}",
            )
        )
    return sheets


def _decode_value(cell: ET.Element, shared_strings: list[str]) -> tuple[object | None, str | None]:
    data_type = cell.attrib.get("t")
    value_node = cell.find("a:v", NS)
    inline_text_node = cell.find("a:is", NS)

    if inline_text_node is not None:
        text_parts = [node.text or "" for node in inline_text_node.iter(f"{{{MAIN_NS}}}t")]
        return "".join(text_parts), "inlineStr"

    if value_node is None:
        return None, data_type

    raw_value = value_node.text
    if data_type == "s":
        return shared_strings[int(raw_value)], data_type
    if data_type in {"str", "inlineStr"}:
        return raw_value, data_type
    if data_type == "b":
        return raw_value == "1", data_type
    if data_type == "e":
        return raw_value, data_type

    try:
        number = float(raw_value)
    except (TypeError, ValueError):
        return raw_value, data_type

    if number.is_integer():
        return int(number), data_type
    return number, data_type


def _load_sheet(archive: ZipFile, sheet_ref: WorkbookSheetRef, shared_strings: list[str]) -> SheetData:
    root = ET.fromstring(archive.read(sheet_ref.target))
    cells: dict[str, CellValue] = {}
    max_row = 0
    max_column = 0

    for row in root.find("a:sheetData", NS) or []:
        for cell in row.findall("a:c", NS):
            reference = cell.attrib["r"]
            row_index, column_index = parse_cell_reference(reference)
            value, data_type = _decode_value(cell, shared_strings)
            formula_node = cell.find("a:f", NS)
            style_id = cell.attrib.get("s")
            cells[reference] = CellValue(
                ref=reference,
                row=row_index,
                column=column_index,
                value=value,
                formula=formula_node.text if formula_node is not None else None,
                data_type=data_type,
                style_id=int(style_id) if style_id is not None else None,
            )
            max_row = max(max_row, row_index)
            max_column = max(max_column, column_index)

    return SheetData(
        name=sheet_ref.name,
        state=sheet_ref.state,
        cells=cells,
        max_row=max_row,
        max_column=max_column,
    )


def load_workbook(path: str | Path) -> WorkbookData:
    workbook_path = Path(path)
    with ZipFile(workbook_path) as archive:
        shared_strings = _load_shared_strings(archive)
        sheet_refs = _load_sheet_refs(archive)
        sheets = [_load_sheet(archive, sheet_ref, shared_strings) for sheet_ref in sheet_refs]
    return WorkbookData(path=str(workbook_path), sheets=sheets, shared_strings_count=len(shared_strings))
