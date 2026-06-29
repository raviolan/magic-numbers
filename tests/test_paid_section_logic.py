from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from audit_workbooks import detect_paid_section
from models import CellValue, SheetData


class PaidSectionLogicTests(unittest.TestCase):
    def test_paid_before_profiles_is_included(self) -> None:
        sheet = SheetData(
            name="Example",
            state="visible",
            cells={
                "A5": CellValue("A5", 5, 1, "Paid"),
                "A10": CellValue("A10", 10, 1, "Channel"),
            },
            max_row=10,
            max_column=1,
        )

        detected, position, included, _ = detect_paid_section(sheet, sheet.cells["A10"])

        self.assertTrue(detected)
        self.assertEqual(position, "before_profiles")
        self.assertTrue(included)

    def test_paid_after_profiles_is_excluded(self) -> None:
        sheet = SheetData(
            name="Example",
            state="visible",
            cells={
                "A10": CellValue("A10", 10, 1, "Channel"),
                "A20": CellValue("A20", 20, 1, "Paid"),
            },
            max_row=20,
            max_column=1,
        )

        detected, position, included, _ = detect_paid_section(sheet, sheet.cells["A10"])

        self.assertTrue(detected)
        self.assertEqual(position, "after_profiles")
        self.assertFalse(included)


if __name__ == "__main__":
    unittest.main()
