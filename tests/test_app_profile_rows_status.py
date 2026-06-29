from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import app
from ui_model_adapter import generate_profile_rows, parse_channel_split


class ProfileRowsStatusTests(unittest.TestCase):
    def test_profile_row_status_detects_match(self) -> None:
        rows = [
            {"channel": "Instagram"},
            {"channel": "TikTok"},
        ]
        status = app._profile_row_status(2, rows)
        self.assertTrue(status["matches_requested_total"])
        self.assertEqual(status["generated_row_count"], 2)

    def test_profile_row_status_detects_mismatch(self) -> None:
        rows = [
            {"channel": "Instagram"},
            {"channel": "TikTok"},
        ]
        status = app._profile_row_status(3, rows)
        self.assertFalse(status["matches_requested_total"])
        self.assertEqual(status["generated_row_count"], 2)

    def test_channel_summary_counts_rows(self) -> None:
        rows = [
            {"channel": "Instagram"},
            {"channel": "Instagram"},
            {"channel": "TikTok"},
        ]
        status = app._profile_row_status(3, rows)
        self.assertIn("Instagram x2", status["channel_summary"])
        self.assertIn("TikTok x1", status["channel_summary"])

    def test_profile_structure_signature_changes_with_inputs(self) -> None:
        sig_a = app._profile_structure_signature(
            total_profiles=4,
            selected_channels=["Instagram", "TikTok"],
            instagram_count="2",
            tiktok_count="2",
            youtube_count="",
            project_cpms={"Instagram": 100.0, "TikTok": 120.0, "YouTube": None},
        )
        sig_b = app._profile_structure_signature(
            total_profiles=5,
            selected_channels=["Instagram", "TikTok"],
            instagram_count="2",
            tiktok_count="3",
            youtube_count="",
            project_cpms={"Instagram": 100.0, "TikTok": 120.0, "YouTube": None},
        )
        self.assertNotEqual(sig_a, sig_b)

    def test_internal_row_generation_matches_total_and_selected_channels(self) -> None:
        split = parse_channel_split(
            total_profiles=4,
            instagram_count="2",
            tiktok_count="2",
            youtube_count="",
            selected_channels=["Instagram", "TikTok"],
        )
        rows = generate_profile_rows(
            total_profiles=4,
            project_cpms={"Instagram": 100.0, "TikTok": 120.0, "YouTube": None},
            channel_split=split,
            selected_channels=["Instagram", "TikTok"],
        )
        self.assertEqual(len(rows), 4)
        self.assertEqual(sorted({row["channel"] for row in rows}), ["Instagram", "TikTok"])
        self.assertTrue(all(row["activations"] == 1 for row in rows))
        self.assertTrue(all(row["cpm"] in (100.0, 120.0) for row in rows))


if __name__ == "__main__":
    unittest.main()
