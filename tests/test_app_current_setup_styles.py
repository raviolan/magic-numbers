from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app import _current_setup_row_background


class CurrentSetupRowStyleTests(unittest.TestCase):
    def test_total_budget_is_green(self) -> None:
        self.assertEqual(_current_setup_row_background("Total budget"), "#f0fdf4")

    def test_agency_fee_is_orange(self) -> None:
        self.assertEqual(_current_setup_row_background("Agency fee"), "#fff7ed")

    def test_paid_media_is_purple(self) -> None:
        self.assertEqual(_current_setup_row_background("Paid media"), "#faf5ff")

    def test_profile_fee_deduction_is_default(self) -> None:
        self.assertEqual(_current_setup_row_background("Profile fee deduction"), "")

    def test_cpm_row_is_yellow(self) -> None:
        self.assertEqual(_current_setup_row_background("Instagram CPM"), "#fffbeb")


if __name__ == "__main__":
    unittest.main()
