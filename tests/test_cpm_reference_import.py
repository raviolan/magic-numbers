from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cpm_library import CURRENCY_UNKNOWN, summarize_cpm_library_by_currency_and_channel
from cpm_reference_import import (
    build_cpm_observation_from_reference_row,
    import_reference_cpm_rows,
    normalize_reference_channel,
    parse_cpm_value,
    parse_reference_cpm_rows_from_workbook,
    preview_reference_cpm_import,
)
from models import CellValue, SheetData, WorkbookData


def _column_letters(index: int) -> str:
    letters = ""
    while index > 0:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def build_sheet(name: str, rows: list[list[object]]) -> SheetData:
    cells: dict[str, CellValue] = {}
    max_column = 0
    for row_index, row_values in enumerate(rows, start=1):
        max_column = max(max_column, len(row_values))
        for column_index, value in enumerate(row_values, start=1):
            if value is None:
                continue
            ref = f"{_column_letters(column_index)}{row_index}"
            cells[ref] = CellValue(
                ref=ref,
                row=row_index,
                column=column_index,
                value=value,
            )
    return SheetData(name=name, state="visible", cells=cells, max_row=len(rows), max_column=max_column)


def build_workbook(sheets: list[SheetData], path: str = "CPMreferenser.xlsx") -> WorkbookData:
    return WorkbookData(path=path, sheets=sheets, shared_strings_count=0)


class CpmReferenceImportTests(unittest.TestCase):
    def test_channel_aliases_normalize(self) -> None:
        self.assertEqual(normalize_reference_channel("IG"), "Instagram")
        self.assertEqual(normalize_reference_channel("Tik Tok"), "TikTok")
        self.assertEqual(normalize_reference_channel("yt"), "YouTube")
        self.assertIsNone(normalize_reference_channel("LinkedIn"))

    def test_parse_cpm_value_formats(self) -> None:
        self.assertEqual(parse_cpm_value("425"), 425)
        self.assertEqual(parse_cpm_value("1 100"), 1100)
        self.assertEqual(parse_cpm_value("1,100"), 1100)
        self.assertEqual(parse_cpm_value("425.5"), 425.5)
        self.assertIsNone(parse_cpm_value(""))
        self.assertIsNone(parse_cpm_value("abc"))

    def test_niche_maps_to_comment_and_missing_currency_uses_default(self) -> None:
        sheet = build_sheet(
            "Sheet1",
            [
                ["Workbook", "Marknad", "Channel", "Currency", "CPM", "Niche", "Comment"],
                ["Gandalf", "Sverige", "Youtube", "", "910", "lifestyle", "high quality"],
            ],
        )
        workbook = build_workbook([sheet])
        rows = parse_reference_cpm_rows_from_workbook(workbook, default_currency="EUR")

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["status"], "valid")
        self.assertEqual(row["channel"], "YouTube")
        self.assertEqual(row["currency"], "EUR")
        self.assertEqual(row["cpm"], 910)
        self.assertEqual(row["comment"], "Niche: lifestyle. Comment: high quality")
        self.assertEqual(row["used_row_count"], 1)

    def test_unsupported_channel_and_missing_cpm_are_invalid(self) -> None:
        sheet = build_sheet(
            "Sheet1",
            [
                ["Project", "Channel", "Currency", "CPM", "Niche"],
                ["A", "LinkedIn", "SEK", 500, "bad channel"],
                ["B", "Instagram", "SEK", "", "missing cpm"],
            ],
        )
        workbook = build_workbook([sheet])
        rows = parse_reference_cpm_rows_from_workbook(workbook, default_currency="SEK")
        self.assertEqual(rows[0]["status"], "invalid")
        self.assertIn("Unsupported or missing channel", rows[0]["validation_message"])
        self.assertEqual(rows[1]["status"], "invalid")
        self.assertIn("CPM must be numeric and greater than 0", rows[1]["validation_message"])

    def test_multi_sheet_import_parsing_preserves_sheet_and_skips_empty(self) -> None:
        sheet1 = build_sheet(
            "Sheet1",
            [
                ["Workbook", "Channel", "Currency", "CPM", "Niche"],
                ["A", "Instagram", "SEK", 500, "beauty"],
            ],
        )
        sheet2 = build_sheet(
            "Another",
            [
                ["Client", "Platform", "Valuta", "Rate"],
                ["B", "Tik Tok", "EUR", "35"],
            ],
        )
        empty_sheet = build_sheet("Empty", [[None, None]])
        workbook = build_workbook([sheet1, sheet2, empty_sheet])
        rows = parse_reference_cpm_rows_from_workbook(workbook, default_currency=CURRENCY_UNKNOWN)
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["sheet_name"] for row in rows}, {"Sheet1", "Another"})
        self.assertTrue(all(row["status"] == "valid" for row in rows))

    def test_preview_and_import_handle_duplicates_and_source_type(self) -> None:
        sheet = build_sheet(
            "Sheet1",
            [
                ["Workbook", "Marknad", "Channel", "Currency", "CPM", "Niche"],
                ["Gandalf", "Sverige", "Youtube", "sek", 910, "lifestyle"],
            ],
        )
        workbook = build_workbook([sheet])

        with mock.patch("cpm_reference_import.load_reference_cpm_workbook", return_value=workbook):
            preview = preview_reference_cpm_import("/tmp/CPMreferenser.xlsx", existing_observations=[], default_currency="SEK")
            self.assertEqual(preview["counts"]["valid"], 1)
            self.assertEqual(preview["counts"]["duplicate"], 0)

            first_import = import_reference_cpm_rows("/tmp/CPMreferenser.xlsx", existing_observations=[], default_currency="SEK")
            self.assertEqual(first_import["imported_count"], 1)
            imported_row = first_import["updated_observations"][0]
            self.assertEqual(imported_row["source_type"], "manual_reference_import")
            self.assertEqual(imported_row["sheet_name"], "Sheet1")

            second_import = import_reference_cpm_rows(
                "/tmp/CPMreferenser.xlsx",
                existing_observations=first_import["updated_observations"],
                default_currency="SEK",
            )
            self.assertEqual(second_import["imported_count"], 0)
            self.assertEqual(second_import["duplicate_count"], 1)

    def test_imported_rows_affect_currency_summary_correctly(self) -> None:
        valid_rows = [
            {
                "calculation_name": "Ref A",
                "workbook_name": None,
                "sheet_name": "Sheet1",
                "channel": "Instagram",
                "market": "SE",
                "currency": "SEK",
                "cpm": 500,
                "used_row_count": 1,
                "comment": "niche",
            },
            {
                "calculation_name": "Ref B",
                "workbook_name": None,
                "sheet_name": "Sheet1",
                "channel": "Instagram",
                "market": "DE",
                "currency": "EUR",
                "cpm": 46,
                "used_row_count": 1,
                "comment": "niche",
            },
            {
                "calculation_name": "Ref C",
                "workbook_name": None,
                "sheet_name": "Sheet1",
                "channel": "Instagram",
                "market": "US",
                "currency": CURRENCY_UNKNOWN,
                "cpm": 600,
                "used_row_count": 1,
                "comment": "niche",
            },
        ]
        observations = [build_cpm_observation_from_reference_row(row, created_at="2026-04-27T10:00:00+00:00") for row in valid_rows]
        summary = summarize_cpm_library_by_currency_and_channel(observations)

        sek = {row["channel"]: row for row in summary["by_currency"]["SEK"]}
        eur = {row["channel"]: row for row in summary["by_currency"]["EUR"]}
        self.assertEqual(sek["Instagram"]["average_cpm"], 500.0)
        self.assertEqual(eur["Instagram"]["average_cpm"], 46.0)
        self.assertEqual(summary["unknown_currency_observation_count"], 1)


if __name__ == "__main__":
    unittest.main()
