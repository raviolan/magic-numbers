from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app import (
    GYST_KURSIV_FONT_PATH,
    UPGRADE_CAPTION_FONT_PATH,
    UPGRADE_FONT_PATH,
    _current_setup_row_background,
    inject_app_css,
)


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

    def test_required_font_assets_are_present(self) -> None:
        self.assertTrue(GYST_KURSIV_FONT_PATH.exists())
        self.assertTrue(UPGRADE_FONT_PATH.exists())
        self.assertTrue(UPGRADE_CAPTION_FONT_PATH.exists())

    def test_injected_css_contains_brand_style_requirements(self) -> None:
        with patch("app.st.markdown") as markdown:
            inject_app_css()

        css = markdown.call_args.args[0]
        self.assertTrue(markdown.call_args.kwargs["unsafe_allow_html"])
        self.assertIn("@font-face", css)
        self.assertIn("font-family: 'Nine Gyst Kursiv'", css)
        self.assertIn("font-family: 'Nine Upgrade'", css)
        self.assertIn("font-family: 'Nine Upgrade Caption'", css)
        self.assertIn(".magic-title,", css)
        self.assertIn(".magic-title *", css)
        self.assertNotIn(".app-title", css)
        self.assertIn("color: #f0fc03 !important;", css)
        self.assertIn("font-style: italic !important;", css)
        self.assertIn("font-weight: 400 !important;", css)
        self.assertIn(".section-caption", css)
        self.assertIn("font-family: 'Nine Upgrade Caption', 'Nine Upgrade', Arial, sans-serif !important;", css)
        self.assertIn(".app-caption", css)
        self.assertIn("color: #f9e9d4;", css)
        self.assertNotIn(".stApp .app-caption", css)
        self.assertNotIn(
            '.stApp div:not([data-testid*="stIcon"]),\n        .stMarkdown',
            css,
        )
        self.assertNotIn(
            '.stApp div:not([data-testid*="stIcon"]),\n        .stApp label',
            css,
        )
        self.assertIn("data:font/otf;base64,", css)
        self.assertNotIn(".stApp *,", css)
        self.assertIn('div[data-testid="stExpander"]', css)
        self.assertIn("background: #f9e9d4 !important;", css)
        self.assertIn("background: #f9e9d4;", css)
        self.assertIn("background: #fbf1e4 !important;", css)
        self.assertNotIn("background: #fafafa;", css)
        self.assertIn("box-sizing: border-box;", css)
        self.assertIn("overflow-wrap: anywhere;", css)
        self.assertIn('div[data-testid="column"]', css)
        self.assertIn("min-height: 100%;", css)
        self.assertIn("margin-bottom: 0.6rem;", css)
        self.assertIn("padding: 0.75rem 0.85rem 1.75rem 0.85rem;", css)
        self.assertIn(".results-title", css)
        self.assertIn("margin: 0.25rem 0 0.45rem 0;", css)
        self.assertIn("margin-bottom: 0.35rem;", css)
        self.assertIn(".run-feedback", css)
        self.assertIn(".run-feedback-ready", css)
        self.assertIn("background: #f0fc03;", css)
        self.assertIn(".option-detail-block", css)
        self.assertIn(".option-profile-channel", css)
        self.assertIn(".option-diff-line", css)


if __name__ == "__main__":
    unittest.main()
