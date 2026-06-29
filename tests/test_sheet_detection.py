from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from audit_workbooks import detect_channels, detect_profile_section
from models import CellValue, SheetData


class SheetDetectionTests(unittest.TestCase):
    def test_detect_profile_section_and_channels(self) -> None:
        sheet = SheetData(
            name="Profiles",
            state="visible",
            cells={
                "A8": CellValue("A8", 8, 1, "Channel"),
                "B8": CellValue("B8", 8, 2, "Follower size"),
                "G8": CellValue("G8", 8, 7, "CPM (profile)"),
                "A9": CellValue("A9", 9, 1, "Instagram"),
                "B9": CellValue("B9", 9, 2, 35),
                "G9": CellValue("G9", 9, 7, 46),
                "A10": CellValue("A10", 10, 1, "TikTok"),
                "B10": CellValue("B10", 10, 2, 75),
                "G10": CellValue("G10", 10, 7, 35),
                "A11": CellValue("A11", 11, 1, "Total"),
            },
            max_row=11,
            max_column=7,
        )

        header, columns, profile_rows = detect_profile_section(sheet)
        supported, unsupported = detect_channels(profile_rows)

        self.assertIsNotNone(header)
        self.assertEqual(columns["channel"], 1)
        self.assertEqual(columns["size"], 2)
        self.assertEqual(len(profile_rows), 2)
        self.assertEqual(supported, ["Instagram", "TikTok"])
        self.assertEqual(unsupported, [])


if __name__ == "__main__":
    unittest.main()
