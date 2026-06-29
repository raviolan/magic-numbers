from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from results_view_helpers import (
    at_a_glance_option_labels,
    build_option_display_metadata,
    build_option_quick_compare_cards,
    build_channel_mix_summary,
    build_diff_status,
    find_closest_positive_diff_option_label,
    build_simplified_fill_rows,
    build_tier_mix_by_channel,
    build_tier_mix_chips,
    format_option_label,
    main_option_note,
    option_ui_label,
    option_diff_delta_vs_recommended,
    option_tradeoff_summary,
    select_option_label,
    tier_mix_by_channel_lines,
    tier_mix_summary,
)
from option_eligibility import MAX_RECOMMENDABLE_POSITIVE_DIFF, is_option_diff_recommendable


class ResultsViewHelpersTests(unittest.TestCase):
    def test_positive_diff_threshold_value_is_current_product_default(self) -> None:
        self.assertEqual(MAX_RECOMMENDABLE_POSITIVE_DIFF, 10000.0)

    def test_tier_mix_summary_uses_expected_display(self) -> None:
        summary = tier_mix_summary({"15000": 2, "35000": 4, "75000": 1, "125000": 0, "175000": 0})
        self.assertEqual(summary, "15K x 2 · 35K x 4 · 75K x 1")

    def test_at_a_glance_option_labels_deduplicates_and_limits(self) -> None:
        result = {
            "recommended_option_label": "best_mathematical_fit",
            "closest_positive_diff_option_label": "best_mathematical_fit",
            "options": [
                {"option_label": "best_mathematical_fit", "optimized_diff": 1000},
                {"option_label": "best_strategic_fit", "optimized_diff": 1500},
                {"option_label": "larger_profile_alternative", "optimized_diff": 3000},
                {"option_label": "current_workbook_mix", "optimized_diff": 7000},
                {"option_label": "best_mathematical_fit", "optimized_diff": 1000},
            ],
        }
        labels = at_a_glance_option_labels(result)
        self.assertEqual(labels[0], "best_mathematical_fit")
        self.assertEqual(len(labels), len(set(labels)))
        self.assertLessEqual(len(labels), 4)

    def test_find_closest_positive_diff_option_label(self) -> None:
        label = find_closest_positive_diff_option_label(
            [
                {"option_label": "a", "optimized_diff": -10, "diagnostics": {"non_negative_diff": False}},
                {"option_label": "b", "optimized_diff": 50, "diagnostics": {"non_negative_diff": True}},
                {"option_label": "c", "optimized_diff": 5, "diagnostics": {"non_negative_diff": True}},
            ]
        )
        self.assertEqual(label, "c")

    def test_select_option_label_defaults_to_recommended(self) -> None:
        labels = ["best_mathematical_fit", "best_strategic_fit"]
        self.assertEqual(select_option_label(labels, "best_mathematical_fit"), "best_mathematical_fit")

    def test_build_simplified_fill_rows_hides_technical_fields_and_formats_size(self) -> None:
        rows, include_market, include_activations = build_simplified_fill_rows(
            [
                {
                    "profile_size_cell": "B9",
                    "previous_profile_size": 35000,
                    "recommended_profile_size": 15000,
                    "channel": "TikTok",
                    "market": None,
                    "cpm": 35,
                    "activations": 1,
                    "row_fee": 350,
                }
            ]
        )
        self.assertFalse(include_market)
        self.assertFalse(include_activations)
        self.assertEqual(rows[0]["Storlek"], "15")
        self.assertNotIn("Row", rows[0])
        self.assertNotIn("previous_profile_size", rows[0])
        self.assertNotIn("Aktiveringar", rows[0])
        self.assertNotIn("profile_size_cell", rows[0])

    def test_build_simplified_fill_rows_shows_market_when_present(self) -> None:
        rows, include_market, _ = build_simplified_fill_rows(
            [{"profile_size_cell": "B9", "recommended_profile_size": 35000, "channel": "Instagram", "market": "SE", "cpm": 100, "activations": 1, "row_fee": 1000}]
        )
        self.assertTrue(include_market)
        self.assertIn("Marknad", rows[0])

    def test_build_simplified_fill_rows_shows_activations_when_needed(self) -> None:
        rows, _, include_activations = build_simplified_fill_rows(
            [{"profile_size_cell": "B9", "recommended_profile_size": 35000, "channel": "Instagram", "market": "", "cpm": 100, "activations": 2, "row_fee": 1000}]
        )
        self.assertTrue(include_activations)
        self.assertIn("Aktiveringar", rows[0])

    def test_option_ui_label(self) -> None:
        self.assertEqual(option_ui_label("best_mathematical_fit", "best_mathematical_fit"), "Rekommenderat förslag")
        self.assertEqual(option_ui_label("best_strategic_fit", "best_mathematical_fit"), "Strategiskt förslag")

    def test_format_option_label_mapping(self) -> None:
        self.assertEqual(format_option_label("best_mathematical_fit"), "Bästa matematiska träff")
        self.assertEqual(format_option_label("balanced_option"), "Balanserat förslag")

    def test_positive_diff_at_threshold_is_selectable(self) -> None:
        display = build_option_display_metadata(
            option={"option_label": "best_strategic_fit", "optimized_diff": MAX_RECOMMENDABLE_POSITIVE_DIFF},
            recommended_option={"option_label": "best_mathematical_fit", "optimized_diff": 100},
            strategic_option={"option_label": "best_strategic_fit", "optimized_diff": MAX_RECOMMENDABLE_POSITIVE_DIFF},
        )
        self.assertEqual(display["display_label"], "Strategiskt förslag")
        self.assertTrue(display["is_selectable"])
        self.assertIsNone(display["disabled_reason"])
        self.assertIsNone(display["replacement_body_text"])

    def test_positive_diff_above_threshold_is_not_selectable(self) -> None:
        display = build_option_display_metadata(
            option={"option_label": "best_strategic_fit", "optimized_diff": MAX_RECOMMENDABLE_POSITIVE_DIFF + 1},
            recommended_option={"option_label": "best_mathematical_fit", "optimized_diff": 100},
            strategic_option={"option_label": "best_strategic_fit", "optimized_diff": MAX_RECOMMENDABLE_POSITIVE_DIFF + 1},
        )
        self.assertEqual(display["display_label"], "Strategiskt förslag")
        self.assertFalse(display["is_selectable"])
        self.assertEqual(display["disabled_reason"], "positive_diff_above_threshold")
        self.assertEqual(
            display["replacement_body_text"],
            "Det här alternativet visas inte i ifyllnadsinstruktioner.",
        )

    def test_large_negative_diff_is_not_disabled_by_positive_diff_threshold(self) -> None:
        self.assertTrue(is_option_diff_recommendable(-100000))
        display = build_option_display_metadata(
            option={"option_label": "balanced_option", "optimized_diff": -100000},
            recommended_option={"option_label": "best_mathematical_fit", "optimized_diff": 100},
            strategic_option={"option_label": "best_strategic_fit", "optimized_diff": 1500},
        )
        self.assertEqual(display["display_label"], "Balanserat förslag")
        self.assertTrue(display["is_selectable"])
        self.assertIsNone(display["disabled_reason"])
        self.assertIsNone(display["replacement_body_text"])

    def test_best_mathematical_fit_with_acceptable_positive_diff_remains_selectable(self) -> None:
        display = build_option_display_metadata(
            option={"option_label": "best_mathematical_fit", "optimized_diff": 4500},
            recommended_option={"option_label": "best_mathematical_fit", "optimized_diff": 100},
            strategic_option={"option_label": "best_strategic_fit", "optimized_diff": 15000},
        )
        self.assertEqual(display["display_label"], "Rekommenderat förslag")
        self.assertTrue(display["is_selectable"])
        self.assertIsNone(display["disabled_reason"])
        self.assertIsNone(display["replacement_body_text"])

    def test_quick_compare_cards_include_disabled_reason(self) -> None:
        result = {
            "recommended_option_label": "best_mathematical_fit",
            "closest_positive_diff_option_label": "best_strategic_fit",
            "options": [
                {
                    "option_label": "best_mathematical_fit",
                    "optimized_diff": 100,
                    "fill_instructions": [{"channel": "Instagram", "recommended_profile_size": 35000}],
                    "main_note": "A",
                    "strategic_warnings": [],
                },
                {
                    "option_label": "best_strategic_fit",
                    "optimized_diff": MAX_RECOMMENDABLE_POSITIVE_DIFF + 1,
                    "fill_instructions": [{"channel": "TikTok", "recommended_profile_size": 75000}],
                    "main_note": "B",
                    "strategic_warnings": [],
                },
            ],
        }

        cards = build_option_quick_compare_cards(result)
        strategic_card = next(card for card in cards if card["option_label"] == "best_strategic_fit")

        self.assertFalse(strategic_card["is_selectable"])
        self.assertEqual(strategic_card["disabled_reason"], "positive_diff_above_threshold")

    def test_build_tier_mix_chips_omits_zero_by_default(self) -> None:
        chips = build_tier_mix_chips({"15000": 1, "35000": 0, "75000": 2})
        self.assertEqual(chips, ["15K × 1", "75K × 2"])

    def test_build_channel_mix_summary_counts_profiles(self) -> None:
        summary = build_channel_mix_summary(
            [
                {"channel": "Instagram", "row_fee": 100},
                {"channel": "Instagram", "row_fee": 200},
                {"channel": "TikTok", "row_fee": 50},
            ]
        )
        self.assertEqual(summary[0]["channel"], "Instagram")
        self.assertEqual(summary[0]["profiles"], 2)
        self.assertEqual(summary[0]["fee_sum"], 300.0)
        self.assertEqual(summary[1]["channel"], "TikTok")
        self.assertEqual(summary[1]["profiles"], 1)

    def test_build_diff_status(self) -> None:
        self.assertEqual(build_diff_status(100)[0], "positive")
        self.assertEqual(build_diff_status(-100)[0], "negative")
        self.assertEqual(build_diff_status(0)[0], "neutral")

    def test_build_tier_mix_by_channel_groups_rows(self) -> None:
        summary = build_tier_mix_by_channel(
            [
                {"channel": "Instagram", "recommended_profile_size": 35000},
                {"channel": "Instagram", "recommended_profile_size": 75000},
                {"channel": "Instagram", "recommended_profile_size": 75000},
                {"channel": "TikTok", "recommended_profile_size": 125000},
            ]
        )
        self.assertEqual(summary["Instagram"]["35000"], 1)
        self.assertEqual(summary["Instagram"]["75000"], 2)
        self.assertEqual(summary["TikTok"]["125000"], 1)

    def test_build_tier_mix_by_channel_handles_unknown_channel(self) -> None:
        summary = build_tier_mix_by_channel(
            [
                {"channel": "Snapchat", "recommended_profile_size": 75000},
                {"channel": "", "recommended_profile_size": 35000},
            ]
        )
        self.assertIn("Other", summary)
        self.assertEqual(summary["Other"]["75000"], 1)

    def test_tier_mix_by_channel_lines_omits_zero_count_tiers(self) -> None:
        lines = tier_mix_by_channel_lines(
            [
                {"channel": "Instagram", "recommended_profile_size": 15000},
                {"channel": "Instagram", "recommended_profile_size": 15000},
                {"channel": "TikTok", "recommended_profile_size": 75000},
            ]
        )
        self.assertEqual(lines[0], "Instagram: 15K × 2")
        self.assertEqual(lines[1], "TikTok: 75K × 1")

    def test_main_option_note_prefers_warning(self) -> None:
        option = {"strategic_warnings": ["Too aggressive mix"], "main_note": "fallback note"}
        self.assertEqual(main_option_note(option), "Too aggressive mix")

    def test_option_diff_delta_vs_recommended(self) -> None:
        recommended = {"optimized_diff": 100}
        option = {"optimized_diff": 130}
        self.assertEqual(option_diff_delta_vs_recommended(option, recommended), 30.0)

    def test_option_tradeoff_summary_is_deterministic(self) -> None:
        recommended = {"option_label": "best_mathematical_fit", "optimized_diff": 100, "fill_instructions": []}
        option = {"option_label": "best_strategic_fit", "optimized_diff": 120, "fill_instructions": []}
        self.assertEqual(option_tradeoff_summary(option, recommended), "Mer marginal")

    def test_build_option_quick_compare_cards_limits_and_dedupes(self) -> None:
        result = {
            "recommended_option_label": "best_mathematical_fit",
            "closest_positive_diff_option_label": "closest_positive_diff",
            "options": [
                {
                    "option_label": "best_mathematical_fit",
                    "optimized_diff": 100,
                    "fill_instructions": [{"channel": "Instagram", "recommended_profile_size": 15000}],
                    "main_note": "A",
                    "strategic_warnings": [],
                },
                {
                    "option_label": "closest_positive_diff",
                    "optimized_diff": 100,
                    "fill_instructions": [{"channel": "Instagram", "recommended_profile_size": 15000}],
                    "main_note": "B",
                    "strategic_warnings": [],
                },
                {
                    "option_label": "best_strategic_fit",
                    "optimized_diff": 150,
                    "fill_instructions": [{"channel": "TikTok", "recommended_profile_size": 35000}],
                    "main_note": "C",
                    "strategic_warnings": [],
                },
                {
                    "option_label": "fallback_option",
                    "optimized_diff": 300,
                    "fill_instructions": [{"channel": "YouTube", "recommended_profile_size": 75000}],
                    "main_note": "D",
                    "strategic_warnings": [],
                },
            ],
        }
        cards = build_option_quick_compare_cards(result)
        self.assertLessEqual(len(cards), 3)
        self.assertEqual(cards[0]["option_label"], "best_mathematical_fit")
        self.assertNotIn("fallback_option", [card["option_label"] for card in cards])

    def test_build_option_quick_compare_cards_includes_closest_positive_when_distinct(self) -> None:
        result = {
            "recommended_option_label": "best_mathematical_fit",
            "closest_positive_diff_option_label": "closest_positive_diff",
            "options": [
                {
                    "option_label": "best_mathematical_fit",
                    "optimized_diff": -10,
                    "fill_instructions": [{"channel": "Instagram", "recommended_profile_size": 15000}],
                    "main_note": "A",
                    "strategic_warnings": [],
                },
                {
                    "option_label": "closest_positive_diff",
                    "optimized_diff": 5,
                    "fill_instructions": [{"channel": "TikTok", "recommended_profile_size": 35000}],
                    "main_note": "B",
                    "strategic_warnings": [],
                },
            ],
        }
        cards = build_option_quick_compare_cards(result)
        self.assertIn("closest_positive_diff", [card["option_label"] for card in cards])


if __name__ == "__main__":
    unittest.main()
    find_closest_positive_diff_option_label,
