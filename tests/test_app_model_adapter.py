from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from calculation_engine import load_normalized_models
from optimizer import compute_profile_budget_target, run_optimizer_for_models
from ui_model_adapter import (
    DEFAULT_AGENCY_FEE_PERCENT_TEXT,
    DEFAULT_MANUAL_FEE_MODE,
    DEFAULT_PAID_MEDIA_INCLUDED,
    DEFAULT_PAID_MEDIA_PERCENT_TEXT,
    DEFAULT_SELECTED_MANUAL_CHANNELS,
    DEFAULT_PROFILE_FEE_DEDUCTION_PERCENT,
    MANUAL_FEE_MODES,
    MAX_MANUAL_FEE_COMBINATIONS,
    SIMPLIFIED_FIXED_CPMS,
    SIMPLIFIED_OPTIMIZATION_FOCUS_LARGER_PROFILES,
    SIMPLIFIED_OPTIMIZATION_FOCUS_MANY_PROFILES,
    build_manual_campaign_model,
    build_fee_paid_combinations,
    build_simplified_budget_setup,
    deduction_percent_to_multiplier,
    evaluate_fee_paid_combinations,
    expand_percentage_range,
    format_display_number,
    apply_project_cpms_to_rows,
    choose_option_for_fill_view,
    generate_profile_rows,
    normalize_selected_channels,
    parse_channel_percentage_split,
    parse_friendly_amount,
    profile_size_to_k_display,
    parse_percentage_range,
    parse_channel_split,
    resolve_project_cpms,
    resolve_fee_candidates,
    validate_rows_use_selected_channels,
    validate_project_cpms_for_rows,
    validate_manual_campaign_input,
)
from option_eligibility import MAX_RECOMMENDABLE_POSITIVE_DIFF


class ManualCampaignAdapterTests(unittest.TestCase):
    def test_profile_size_to_k_display_formats_supported_tiers(self) -> None:
        self.assertEqual(profile_size_to_k_display(15000), 15)
        self.assertEqual(profile_size_to_k_display(35000), 35)
        self.assertEqual(profile_size_to_k_display(75000), 75)
        self.assertEqual(profile_size_to_k_display(125000), 125)
        self.assertEqual(profile_size_to_k_display(175000), 175)

    def test_profile_size_to_k_display_nonstandard_falls_back_safely(self) -> None:
        self.assertEqual(profile_size_to_k_display(15250), 15250)
        self.assertEqual(profile_size_to_k_display(None), None)

    def test_choose_option_for_fill_view_defaults_to_recommended(self) -> None:
        options = [{"option_label": "best_mathematical_fit"}, {"option_label": "best_strategic_fit"}]
        selected = choose_option_for_fill_view(options, recommended_option_label="best_strategic_fit")
        self.assertEqual(selected["option_label"], "best_strategic_fit")

    def test_choose_option_for_fill_view_selects_requested_when_present(self) -> None:
        options = [{"option_label": "best_mathematical_fit"}, {"option_label": "best_strategic_fit"}]
        selected = choose_option_for_fill_view(
            options,
            recommended_option_label="best_strategic_fit",
            selected_option_label="best_mathematical_fit",
        )
        self.assertEqual(selected["option_label"], "best_mathematical_fit")

    def test_app_mround_to_5_helper_behavior(self) -> None:
        import app

        self.assertEqual(app._mround_to_5(572.5), 575)
        self.assertEqual(app._mround_to_5(461.5), 460)
        self.assertEqual(app._mround_to_5(955), 955)

    def test_selectable_fill_view_uses_selected_non_recommended_option(self) -> None:
        import app

        result = {
            "recommended_option_label": "best_mathematical_fit",
            "options": [
                {
                    "option_label": "best_mathematical_fit",
                    "optimized_diff": 100,
                    "fill_instructions": [{"channel": "Instagram", "recommended_profile_size": 15000}],
                    "main_note": "A",
                    "strategic_warnings": [],
                },
                {
                    "option_label": "best_strategic_fit",
                    "optimized_diff": 200,
                    "fill_instructions": [{"channel": "TikTok", "recommended_profile_size": 75000}],
                    "main_note": "B",
                    "strategic_warnings": [],
                },
            ],
        }

        view = app._build_selectable_fill_view(result, selected_option_label="best_strategic_fit")

        self.assertEqual(view["selected_label"], "best_strategic_fit")
        self.assertEqual(view["simple_fill_rows"][0]["Kanal"], "TikTok")
        self.assertEqual(view["simple_fill_rows"][0]["Storlek"], "75")

    def test_selectable_fill_view_invalid_selection_falls_back_to_recommended(self) -> None:
        import app

        result = {
            "recommended_option_label": "best_mathematical_fit",
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
                    "optimized_diff": 200,
                    "fill_instructions": [{"channel": "TikTok", "recommended_profile_size": 75000}],
                    "main_note": "B",
                    "strategic_warnings": [],
                },
            ],
        }

        view = app._build_selectable_fill_view(result, selected_option_label="missing_option")

        self.assertEqual(view["selected_label"], "best_mathematical_fit")
        self.assertEqual(view["simple_fill_rows"][0]["Kanal"], "Instagram")
        self.assertEqual(view["simple_fill_rows"][0]["Storlek"], "35")

    def test_selectable_fill_view_uses_balanced_option_when_diff_is_below_5k(self) -> None:
        import app

        result = {
            "recommended_option_label": "best_mathematical_fit",
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
                    "optimized_diff": 500,
                    "fill_instructions": [{"channel": "TikTok", "recommended_profile_size": 75000}],
                    "main_note": "B",
                    "strategic_warnings": [],
                },
                {
                    "option_label": "balanced_option",
                    "optimized_diff": 800,
                    "fill_instructions": [{"channel": "TikTok", "recommended_profile_size": 125000}],
                    "main_note": "C",
                    "strategic_warnings": [],
                },
            ],
        }

        view = app._build_selectable_fill_view(result, selected_option_label="balanced_option")

        self.assertEqual(view["selected_label"], "balanced_option")
        self.assertIn("balanced_option", view["option_labels"])
        balanced_card = next(card for card in view["cards"] if card["option_label"] == "balanced_option")
        self.assertTrue(balanced_card["is_selectable"])
        self.assertEqual(balanced_card["title"], "Alternativ 3")
        self.assertEqual(view["simple_fill_rows"][0]["Kanal"], "TikTok")

    def test_selectable_fill_view_non_recommended_strategic_is_not_selectable(self) -> None:
        import app

        result = {
            "recommended_option_label": "best_mathematical_fit",
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
                    "optimized_diff": 10101,
                    "fill_instructions": [{"channel": "TikTok", "recommended_profile_size": 75000}],
                    "main_note": "B",
                    "strategic_warnings": [],
                },
            ],
        }

        view = app._build_selectable_fill_view(result, selected_option_label="best_strategic_fit")

        self.assertEqual(view["selected_label"], "best_mathematical_fit")
        self.assertNotIn("best_strategic_fit", view["option_labels"])
        strategic_card = next(card for card in view["cards"] if card["option_label"] == "best_strategic_fit")
        self.assertFalse(strategic_card["is_selectable"])
        self.assertEqual(strategic_card["title"], "Alternativ 2")

    def test_selectable_fill_view_option_labels_are_derived_from_current_result(self) -> None:
        import app

        result = {
            "recommended_option_label": "custom_recommended",
            "options": [
                {
                    "option_label": "custom_recommended",
                    "optimized_diff": 100,
                    "fill_instructions": [{"channel": "Instagram", "recommended_profile_size": 15000}],
                    "main_note": "A",
                    "strategic_warnings": [],
                },
                {
                    "option_label": "custom_alternative",
                    "optimized_diff": 300,
                    "fill_instructions": [{"channel": "TikTok", "recommended_profile_size": 35000}],
                    "main_note": "B",
                    "strategic_warnings": [],
                },
            ],
        }

        view = app._build_selectable_fill_view(result)

        self.assertEqual(view["option_labels"], ["custom_recommended", "custom_alternative"])
        self.assertNotIn("best_strategic_fit", view["option_labels"])

    def test_main_fill_selector_key_changes_between_results(self) -> None:
        import app

        self.assertNotEqual(app._main_fill_selector_key(1), app._main_fill_selector_key(2))

    def test_set_main_fill_option_updates_session_state(self) -> None:
        import app

        with mock.patch.object(app.st, "session_state", {}):
            app._set_main_fill_option("main_fill_option_selector_1", "best_strategic_fit")
            self.assertEqual(app.st.session_state["main_fill_option_selector_1"], "best_strategic_fit")

    def test_selected_option_impression_summary_uses_reporting_fields(self) -> None:
        import app

        summary = app._build_selected_option_impression_summary(
            {
                "organic_impressions_total": 45000,
                "paid_impressions_total": 1834583.333,
                "total_project_impressions": 1879583.333,
                "project_cpm": 53.203,
            }
        )

        self.assertEqual(
            summary,
            [
                {"label": "Organiska impressions (K)", "value": 45000},
                {"label": "Paid impressions (K)", "value": 1834583.333},
                {"label": "Totala impressions (K)", "value": 1879583.333},
                {"label": "Project CPM", "value": 53.203},
            ],
        )

    def test_pitch_profile_lines_group_instagram_tiers(self) -> None:
        import app

        lines = app._build_pitch_profile_lines(
            [
                {"channel": "Instagram", "recommended_profile_size": 15000},
                {"channel": "Instagram", "recommended_profile_size": 15000},
                {"channel": "TikTok", "recommended_profile_size": 15000},
            ],
            "Instagram",
        )

        self.assertEqual(lines, "2x Profil á 10-20K följare / 10K snittvisningar")

    def test_pitch_profile_lines_join_multiple_tiers_with_line_breaks(self) -> None:
        import app

        lines = app._build_pitch_profile_lines(
            [
                {"channel": "Instagram", "recommended_profile_size": 15000},
                {"channel": "Instagram", "recommended_profile_size": 35000},
                {"channel": "Instagram", "recommended_profile_size": 35000},
            ],
            "Instagram",
        )

        self.assertEqual(
            lines,
            "1x Profil á 10-20K följare / 10K snittvisningar\n"
            "2x Profil á 20-50K följare / 25K snittvisningar",
        )

    def test_pitch_profile_lines_group_tiktok_tiers(self) -> None:
        import app

        lines = app._build_pitch_profile_lines(
            [
                {"channel": "TikTok", "recommended_profile_size": 75000},
                {"channel": "TikTok", "recommended_profile_size": 75000},
                {"channel": "TikTok", "recommended_profile_size": 75000},
                {"channel": "Instagram", "recommended_profile_size": 75000},
            ],
            "TikTok",
        )

        self.assertEqual(lines, "3x Profil á 50-100K följare / 60K snittvisningar")

    def test_pitch_table_rows_include_instagram_and_tiktok_lines(self) -> None:
        import app

        rows = app._build_pitch_table_rows(
            {"budget_breakdown": {"budget": 100000, "paid_media": 15000, "paid_media_included": True}},
            {
                "fill_instructions": [
                    {"channel": "Instagram", "recommended_profile_size": 15000},
                    {"channel": "TikTok", "recommended_profile_size": 75000},
                ],
                "total_project_impressions": 1880,
                "project_cpm": 53.2,
            },
        )

        self.assertEqual(rows[0]["Post"], "Influencer Marketing Instagram")
        self.assertEqual(rows[0]["Värde"], "1x Profil á 10-20K följare / 10K snittvisningar")
        self.assertEqual(rows[1]["Post"], "Influencer Marketing TikTok")
        self.assertEqual(rows[1]["Värde"], "1x Profil á 50-100K följare / 60K snittvisningar")

    def test_pitch_table_rows_localize_english_without_changing_values(self) -> None:
        import app

        result = {"budget_breakdown": {"budget": 100000, "paid_media": 15000, "paid_media_included": True}}
        selected_option = {
            "fill_instructions": [
                {"channel": "Instagram", "recommended_profile_size": 15000},
                {"channel": "Instagram", "recommended_profile_size": 35000},
                {"channel": "TikTok", "recommended_profile_size": 75000},
            ],
            "total_project_impressions": 1880,
            "project_cpm": 53.2,
        }

        swedish_rows = app._build_pitch_table_rows(result, selected_option)
        english_rows = app._build_pitch_table_rows(result, selected_option, "en")
        english_by_post = {row["Post"]: row["Värde"] for row in english_rows}

        self.assertEqual(
            english_by_post["Influencer Marketing Instagram"],
            "1x Profile with 10-20K followers / 10K avg. views\n"
            "1x Profile with 20-50K followers / 25K avg. views",
        )
        self.assertEqual(
            english_by_post["Influencer Marketing TikTok"],
            "1x Profile with 50-100K followers / 60K avg. views",
        )
        self.assertEqual(english_by_post["Content rights"], "7-30 days")
        self.assertEqual(english_by_post["Activations"], "1x Instagram Reel / TikTok video per profile")
        self.assertEqual(english_by_post["Paid Amplification"], "15 000 SEK")
        self.assertEqual(english_by_post["Impressions"], "1 880 000")
        self.assertEqual(english_by_post["Total"], "100 000 SEK")
        self.assertEqual(english_by_post["CPM"], "53 SEK")

        self.assertEqual(swedish_rows[4]["Värde"], english_rows[4]["Värde"])
        self.assertEqual(swedish_rows[5]["Värde"], english_rows[5]["Värde"])
        self.assertEqual(swedish_rows[6]["Värde"], english_rows[6]["Värde"])
        self.assertEqual(swedish_rows[7]["Värde"], english_rows[7]["Värde"])

    def test_pitch_table_rows_use_selected_option_and_full_budget_breakdown_values(self) -> None:
        import app

        rows = app._build_pitch_table_rows(
            {"budget_breakdown": {"budget": 100000, "paid_media": 15000, "paid_media_included": True}},
            {
                "fill_instructions": [],
                "total_project_impressions": 1880,
                "project_cpm": 53.2,
            },
        )
        by_post = {row["Post"]: row["Värde"] for row in rows}

        self.assertEqual(by_post["Paid"], "15 000 SEK")
        self.assertEqual(by_post["Antal exponeringar"], "1 880 000")
        self.assertEqual(by_post["Total"], "100 000 SEK")
        self.assertEqual(by_post["CPM"], "53 SEK")

    def test_pitch_total_impressions_formats_k_units_as_full_impressions(self) -> None:
        import app

        self.assertEqual(app._format_pitch_total_impressions(1880), "1 880 000")
        self.assertEqual(app._format_pitch_total_impressions(1880.4), "1 880 400")

    def test_pitch_table_html_renders_line_breaks_inside_value_cell(self) -> None:
        import app

        rendered = app._pitch_table_html(
            [
                {
                    "Post": "Influencer Marketing Instagram",
                    "Värde": "1x Profil á 10-20K följare\n2x Profil á 20-50K följare",
                }
            ]
        )

        self.assertIn("1x Profil á 10-20K följare<br>2x Profil á 20-50K följare", rendered)
        self.assertNotIn("följare\n2x", rendered)
        self.assertIn('<tr><th aria-label="Post"></th><th aria-label="Värde"></th></tr>', rendered)
        self.assertNotIn(">Post<", rendered)
        self.assertNotIn(">Värde<", rendered)
        self.assertEqual(rendered.count("<th "), 2)
        self.assertIn("pitch-copy-status", rendered)
        self.assertIn('aria-live="polite"', rendered)
        self.assertIn("Kopierad!", rendered)
        self.assertIn("is-visible", rendered)
        self.assertIn("setTimeout", rendered)
        self.assertTrue(rendered.startswith('<div class="pitch-table-toolbar">'))
        self.assertNotRegex(rendered, r"(?m)^[ \t]+<(?:div|table|thead|tbody|tr)")

    def test_pitch_table_html_localizes_english_copy_and_aria_text(self) -> None:
        import app

        rendered = app._pitch_table_html(
            [
                {
                    "Post": "Influencer Marketing Instagram",
                    "Värde": "1x Profile with 10-20K followers / 10K avg. views\n"
                    "2x Profile with 20-50K followers / 25K avg. views",
                },
                {"Post": "Content rights", "Värde": "7-30 days"},
                {"Post": "Activations", "Värde": "1x Instagram Reel / TikTok video per profile"},
                {"Post": "Paid Amplification", "Värde": "15 000 SEK"},
                {"Post": "Impressions", "Värde": "1 880 000"},
            ],
            "en",
        )

        self.assertIn('aria-label="Copy table"', rendered)
        self.assertIn('title="Copy table"', rendered)
        self.assertIn("Copied!", rendered)
        self.assertIn("Could not copy", rendered)
        self.assertIn('<tr><th aria-label="Item"></th><th aria-label="Value"></th></tr>', rendered)
        self.assertNotIn('aria-label="Post"', rendered)
        self.assertIn("Profile with 10-20K followers / 10K avg. views<br>", rendered)

    def test_pitch_table_clipboard_text_uses_tabs_and_preserves_value_line_breaks(self) -> None:
        import app

        copied = app._pitch_table_clipboard_text(
            [
                {
                    "Post": "Influencer Marketing Instagram",
                    "Värde": "1x Profil á 10-20K följare\n2x Profil á 20-50K följare",
                },
                {"Post": "CPM", "Värde": "53 SEK"},
            ]
        )

        self.assertIn("Influencer Marketing Instagram\t1x Profil á 10-20K följare\n2x Profil á 20-50K följare", copied)
        self.assertIn("\nCPM\t53 SEK", copied)

    def test_pitch_table_clipboard_text_uses_current_english_table_language(self) -> None:
        import app

        rows = app._build_pitch_table_rows(
            {"budget_breakdown": {"budget": 100000, "paid_media": 15000, "paid_media_included": True}},
            {
                "fill_instructions": [
                    {"channel": "Instagram", "recommended_profile_size": 15000},
                    {"channel": "Instagram", "recommended_profile_size": 35000},
                ],
                "total_project_impressions": 1880,
                "project_cpm": 53.2,
            },
            "en",
        )

        copied = app._pitch_table_clipboard_text(rows)

        self.assertIn(
            "Influencer Marketing Instagram\t1x Profile with 10-20K followers / 10K avg. views\n"
            "1x Profile with 20-50K followers / 25K avg. views",
            copied,
        )
        self.assertIn("\nPaid Amplification\t15 000 SEK", copied)
        self.assertIn("\nImpressions\t1 880 000", copied)

    def test_render_pitch_table_uses_html_component_for_clipboard_javascript(self) -> None:
        import app

        rows = [{"Post": "CPM", "Värde": "53 SEK"}]

        with mock.patch.object(app.components, "html") as component_html:
            app._render_pitch_table(rows, "en")

        html_arg = component_html.call_args.args[0]
        self.assertIn("navigator.clipboard.writeText", html_arg)
        self.assertIn("pitch-output-table", html_arg)
        self.assertIn('aria-label="Copy table"', html_arg)
        self.assertIn('<tr><th aria-label="Item"></th><th aria-label="Value"></th></tr>', html_arg)
        self.assertIn("table-layout: fixed", html_arg)
        self.assertIn("border: 1px solid", html_arg)
        self.assertIn("td:first-child { width: 36%; }", html_arg)
        self.assertIn("td:nth-child(2) { width: 64%; }", html_arg)
        self.assertEqual(component_html.call_args.kwargs["height"], 420)
        self.assertFalse(component_html.call_args.kwargs["scrolling"])

    def test_option_pitch_profile_summary_uses_pitch_channel_lines(self) -> None:
        import app

        summary = app._build_option_pitch_profile_summary(
            {
                "fill_instructions": [
                    {"channel": "Instagram", "recommended_profile_size": 15000},
                    {"channel": "Instagram", "recommended_profile_size": 15000},
                    {"channel": "TikTok", "recommended_profile_size": 75000},
                ]
            }
        )

        self.assertEqual(
            summary,
            [
                ("Instagram", "2x Profil á 10-20K följare / 10K snittvisningar"),
                ("TikTok", "1x Profil á 50-100K följare / 60K snittvisningar"),
            ],
        )

    def test_option_card_body_orders_profiles_cpm_impressions_and_diff(self) -> None:
        import app

        rendered = app._build_option_card_body_html(
            {
                "fill_instructions": [
                    {"channel": "Instagram", "recommended_profile_size": 15000},
                    {"channel": "TikTok", "recommended_profile_size": 75000},
                ],
                "project_cpm": 53.2,
                "total_project_impressions": 1880,
                "optimized_diff": 1500,
            }
        )

        profile_position = rendered.index("Profil á 10-20K följare")
        cpm_position = rendered.index("Total CPM:")
        impressions_position = rendered.index("Totala impressions:")
        diff_position = rendered.index("Diff:")
        self.assertLess(profile_position, cpm_position)
        self.assertLess(cpm_position, impressions_position)
        self.assertLess(impressions_position, diff_position)
        self.assertIn("53 SEK", rendered)
        self.assertIn("1 880 000", rendered)
        self.assertIn("+1 500", rendered)

    def test_ui_language_defaults_to_swedish_and_supports_en_path(self) -> None:
        import app

        self.assertEqual(app._ui_language_from_url(None), "sv")
        self.assertEqual(app._ui_language_from_url("http://localhost:8502/"), "sv")
        self.assertEqual(app._ui_language_from_url("http://localhost:8502/en/"), "en")
        self.assertEqual(app._ui_language_from_url("http://localhost:8502/en/?x=1"), "en")
        self.assertEqual(app._ui_text("sv", "page_title"), "Magisk kalkyl")
        self.assertEqual(app._ui_text("sv", "app_caption"), "Generera kalkyler för enklare kundprojekt")
        self.assertEqual(app._ui_text("en", "page_title"), "Magic Numbers")
        self.assertEqual(app._ui_text("sv", "optimization_focus_label"), "Optimera kampanjen för")
        self.assertEqual(
            app._optimization_focus_display_label("sv", SIMPLIFIED_OPTIMIZATION_FOCUS_MANY_PROFILES),
            "så många profiler som möjligt",
        )
        self.assertEqual(
            app._optimization_focus_display_label("sv", SIMPLIFIED_OPTIMIZATION_FOCUS_LARGER_PROFILES),
            "så stora profiler som möjligt",
        )

    def test_positive_buffer_above_recommended_gets_attention_highlight(self) -> None:
        import app

        self.assertTrue(app._option_has_positive_buffer_above_recommended({"diff": 250, "delta_vs_recommended": 100}))
        self.assertFalse(app._option_has_positive_buffer_above_recommended({"diff": -50, "delta_vs_recommended": 100}))
        self.assertFalse(app._option_has_positive_buffer_above_recommended({"diff": 250, "delta_vs_recommended": 0}))
        self.assertFalse(app._option_has_positive_buffer_above_recommended({"diff": 100, "delta_vs_recommended": -50}))

    def test_option_card_click_class_separates_disabled_from_unselected(self) -> None:
        import app

        self.assertEqual(
            app._option_card_click_class({"is_selectable": False, "diff": 100, "delta_vs_recommended": 100}, False),
            "option-click-disabled",
        )
        self.assertEqual(
            app._option_card_click_class({"is_selectable": True, "diff": 100, "delta_vs_recommended": 0}, False),
            "option-click-unselected",
        )
        self.assertEqual(
            app._option_card_click_class({"is_selectable": True, "diff": 100, "delta_vs_recommended": 100}, False),
            "option-click-unselected",
        )
        self.assertEqual(
            app._option_card_click_class({"is_selectable": True, "diff": 100, "delta_vs_recommended": 100}, True),
            "option-click-selected",
        )

    def test_realistic_positive_diff_above_old_threshold_remains_eligible(self) -> None:
        import app

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
                    "optimized_diff": 7600.5,
                    "fill_instructions": [{"channel": "TikTok", "recommended_profile_size": 75000}],
                    "main_note": "B",
                    "strategic_warnings": [],
                },
            ],
        }

        view = app._build_selectable_fill_view(result)
        strategic_card = next(card for card in view["cards"] if card["option_label"] == "best_strategic_fit")

        self.assertTrue(strategic_card["is_selectable"])
        self.assertIn("best_strategic_fit", view["option_labels"])
        self.assertEqual(app._option_card_click_class(strategic_card, False), "option-click-unselected")

    def test_over_threshold_card_is_disabled_and_excluded_from_fill_options(self) -> None:
        import app

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

        view = app._build_selectable_fill_view(result, selected_option_label="best_strategic_fit")
        strategic_card = next(card for card in view["cards"] if card["option_label"] == "best_strategic_fit")

        self.assertFalse(strategic_card["is_selectable"])
        self.assertEqual(strategic_card["disabled_reason"], "positive_diff_above_threshold")
        self.assertNotIn("best_strategic_fit", view["option_labels"])
        self.assertEqual(view["selected_label"], "best_mathematical_fit")
        self.assertEqual(app._option_card_click_class(strategic_card, False), "option-click-disabled")

    def test_result_budget_view_prefers_result_breakdown_and_formats_agency_fee(self) -> None:
        import app

        view = app._build_result_budget_view(
            {
                "profile_budget_target": 78625,
                "budget_breakdown": {
                    "budget": 100000,
                    "agency_fee": 10000,
                    "paid_media": 5000,
                    "paid_media_included": True,
                    "profile_budget_target_multiplier": 0.925,
                    "profile_budget_target": 78625,
                },
            },
            budget_inputs={
                "budget": 999999,
                "agency_fee": 99999,
                "agency_fee_percent": 10.0,
                "paid_media": 99999,
                "paid_media_percent": 5.0,
                "paid_media_included": True,
            },
        )

        self.assertEqual(view["agency_fee_text"], "10 000 (10.00%)")
        self.assertEqual(view["paid_media_text"], "5 000 (5.00%)")
        self.assertEqual(
            view["detailed_budget_rows"],
            [
                {"Post": "Total budget", "Värde": "100 000"},
                {"Post": "Byråarvode", "Värde": "-10 000"},
                {"Post": "Paid media inkluderad", "Värde": "-5 000"},
                {"Post": "Kvar före profilavdrag", "Värde": "85 000"},
                {"Post": "Profilavdrag / extra byråarvode, 7.5%", "Värde": "-6 375"},
                {"Post": "Tillgänglig profilbudget", "Värde": "78 625"},
            ],
        )

    def test_apply_library_medians_uses_mround_to_5_without_mutating_source_medians(self) -> None:
        import app

        observations = [
            {"channel": "Instagram", "currency": "SEK", "cpm": 570},
            {"channel": "Instagram", "currency": "SEK", "cpm": 575},
            {"channel": "TikTok", "currency": "SEK", "cpm": 460},
            {"channel": "TikTok", "currency": "SEK", "cpm": 463},
            {"channel": "YouTube", "currency": "SEK", "cpm": 955},
        ]
        raw_medians = app._get_currency_median_cpms(observations, "SEK")
        self.assertEqual(raw_medians["Instagram"], 572.5)
        self.assertEqual(raw_medians["TikTok"], 461.5)
        self.assertEqual(raw_medians["YouTube"], 955.0)

        with mock.patch.object(app.st, "session_state", {}):
            app._apply_library_medians_to_state("SEK", observations, ["Instagram", "TikTok", "YouTube"])
            self.assertEqual(app.st.session_state["project_cpm_instagram"], "575")
            self.assertEqual(app.st.session_state["project_cpm_tiktok"], "460")
            self.assertEqual(app.st.session_state["project_cpm_youtube"], "955")

    def test_display_number_formatting_uses_space_thousands_and_trimmed_decimals(self) -> None:
        self.assertEqual(format_display_number(1000), "1 000")
        self.assertEqual(format_display_number(1_000_000), "1 000 000")
        self.assertEqual(format_display_number(1_000_000.0), "1 000 000")
        self.assertEqual(format_display_number(1_000_000.25), "1 000 000.25")
        self.assertEqual(format_display_number(950), "950")

    def test_zero_decimal_reporting_format_rounds_without_decimals(self) -> None:
        import app

        self.assertEqual(app._format_zero_decimal_number(1834583.333), "1 834 583")
        self.assertEqual(app._format_zero_decimal_number(53.5), "54")

    def test_parse_friendly_amount_accepts_common_human_formats(self) -> None:
        self.assertEqual(parse_friendly_amount("1000000", "budget"), 1_000_000.0)
        self.assertEqual(parse_friendly_amount("1 000 000", "budget"), 1_000_000.0)
        self.assertEqual(parse_friendly_amount("1000000,00", "budget"), 1_000_000.0)
        self.assertEqual(parse_friendly_amount("1 000 000,00", "budget"), 1_000_000.0)
        self.assertEqual(parse_friendly_amount("1,000,000", "budget"), 1_000_000.0)

    def test_parse_friendly_amount_rejects_invalid_values_clearly(self) -> None:
        with self.assertRaisesRegex(ValueError, "budget is required"):
            parse_friendly_amount("", "budget")
        with self.assertRaisesRegex(ValueError, "budget must be a valid number"):
            parse_friendly_amount("invalid", "budget")

    def test_manual_builder_default_mode_and_percent_defaults(self) -> None:
        self.assertEqual(DEFAULT_MANUAL_FEE_MODE, "Percentage of budget")
        self.assertIn(DEFAULT_MANUAL_FEE_MODE, MANUAL_FEE_MODES)
        self.assertEqual(DEFAULT_AGENCY_FEE_PERCENT_TEXT, "0%")
        self.assertEqual(DEFAULT_PAID_MEDIA_PERCENT_TEXT, "15%")
        self.assertTrue(DEFAULT_PAID_MEDIA_INCLUDED)
        self.assertEqual(DEFAULT_SELECTED_MANUAL_CHANNELS, ("Instagram", "TikTok"))

    def test_default_deduction_percent_is_7_5_and_maps_to_0_925_multiplier(self) -> None:
        self.assertEqual(float(DEFAULT_PROFILE_FEE_DEDUCTION_PERCENT), 7.5)
        self.assertEqual(deduction_percent_to_multiplier(DEFAULT_PROFILE_FEE_DEDUCTION_PERCENT), 0.925)

    def test_simplified_budget_setup_uses_fixed_preset_fee_paid_media_and_deduction(self) -> None:
        setup = build_simplified_budget_setup(100000, paid_media_included=True)
        self.assertEqual(setup["optimization_focus"], SIMPLIFIED_OPTIMIZATION_FOCUS_MANY_PROFILES)
        self.assertEqual(setup["agency_fee"], 36828.0)
        self.assertIsNone(setup["agency_fee_percent"])
        self.assertEqual(setup["paid_media"], 15000.0)
        self.assertEqual(setup["available_before_deduction"], 48172.0)
        self.assertEqual(setup["available_after_deduction"], 44559.1)
        self.assertEqual(setup["total_profiles"], 2)

    def test_simplified_budget_setup_100k_and_150k_support_larger_profile_focus(self) -> None:
        setup_100k = build_simplified_budget_setup(
            100000,
            paid_media_included=True,
            optimization_focus=SIMPLIFIED_OPTIMIZATION_FOCUS_LARGER_PROFILES,
        )
        setup_150k = build_simplified_budget_setup(
            150000,
            paid_media_included=True,
            optimization_focus=SIMPLIFIED_OPTIMIZATION_FOCUS_LARGER_PROFILES,
        )
        self.assertEqual(setup_100k["optimization_focus"], SIMPLIFIED_OPTIMIZATION_FOCUS_LARGER_PROFILES)
        self.assertEqual(setup_100k["agency_fee"], 25839.0)
        self.assertEqual(setup_100k["total_profiles"], 1)
        self.assertEqual(setup_150k["optimization_focus"], SIMPLIFIED_OPTIMIZATION_FOCUS_LARGER_PROFILES)
        self.assertEqual(setup_150k["agency_fee"], 36828.0)
        self.assertEqual(setup_150k["total_profiles"], 2)

    def test_simplified_budget_setup_250k_uses_exact_preset_values(self) -> None:
        setup = build_simplified_budget_setup(250000, paid_media_included=True)
        self.assertEqual(setup["agency_fee"], 80784.0)
        self.assertIsNone(setup["agency_fee_percent"])
        self.assertEqual(setup["paid_media"], 37500.0)
        self.assertEqual(setup["available_before_deduction"], 131716.0)
        self.assertEqual(setup["available_after_deduction"], 121837.3)
        self.assertEqual(setup["total_profiles"], 6)

    def test_simplified_budget_setup_many_profiles_200k_uses_default_variant(self) -> None:
        setup = build_simplified_budget_setup(
            200000,
            paid_media_included=True,
            optimization_focus=SIMPLIFIED_OPTIMIZATION_FOCUS_MANY_PROFILES,
        )
        self.assertEqual(setup["optimization_focus"], SIMPLIFIED_OPTIMIZATION_FOCUS_MANY_PROFILES)
        self.assertEqual(setup["agency_fee"], 69795.0)
        self.assertEqual(setup["paid_media"], 30000.0)
        self.assertEqual(setup["total_profiles"], 5)

    def test_simplified_budget_setup_larger_profiles_200k_uses_variant(self) -> None:
        setup = build_simplified_budget_setup(
            200000,
            paid_media_included=True,
            optimization_focus=SIMPLIFIED_OPTIMIZATION_FOCUS_LARGER_PROFILES,
        )
        self.assertEqual(setup["optimization_focus"], SIMPLIFIED_OPTIMIZATION_FOCUS_LARGER_PROFILES)
        self.assertEqual(setup["agency_fee"], 58806.0)
        self.assertEqual(setup["paid_media"], 30000.0)
        self.assertEqual(setup["available_before_deduction"], 111194.0)
        self.assertEqual(setup["available_after_deduction"], 102854.45)
        self.assertEqual(setup["total_profiles"], 4)

    def test_simplified_budget_setup_larger_profiles_300k_uses_variant(self) -> None:
        setup = build_simplified_budget_setup(
            300000,
            paid_media_included=True,
            optimization_focus=SIMPLIFIED_OPTIMIZATION_FOCUS_LARGER_PROFILES,
        )
        self.assertEqual(setup["agency_fee"], 80784.0)
        self.assertEqual(setup["paid_media"], 45000.0)
        self.assertEqual(setup["total_profiles"], 6)

    def test_simplified_budget_setup_larger_profiles_400k_uses_variant(self) -> None:
        setup = build_simplified_budget_setup(
            400000,
            paid_media_included=True,
            optimization_focus=SIMPLIFIED_OPTIMIZATION_FOCUS_LARGER_PROFILES,
        )
        self.assertEqual(setup["agency_fee"], 124740.0)
        self.assertEqual(setup["paid_media"], 60000.0)
        self.assertEqual(setup["total_profiles"], 10)

    def test_simplified_budget_setup_agency_fee_comes_from_preset_not_percentage(self) -> None:
        setup = build_simplified_budget_setup(300000, paid_media_included=True)
        self.assertEqual(setup["agency_fee"], 102762.0)
        self.assertNotEqual(setup["agency_fee"], 96000.0)
        self.assertEqual(setup["total_profiles"], 8)

    def test_simplified_fixed_cpms_and_default_channels_exclude_youtube(self) -> None:
        self.assertEqual(SIMPLIFIED_FIXED_CPMS["Instagram"], 570.0)
        self.assertEqual(SIMPLIFIED_FIXED_CPMS["TikTok"], 430.0)
        self.assertIsNone(SIMPLIFIED_FIXED_CPMS["YouTube"])
        self.assertEqual(DEFAULT_SELECTED_MANUAL_CHANNELS, ("Instagram", "TikTok"))
        self.assertNotIn("YouTube", DEFAULT_SELECTED_MANUAL_CHANNELS)

    def test_deduction_percent_to_multiplier_conversion(self) -> None:
        self.assertEqual(deduction_percent_to_multiplier(0), 1.0)
        self.assertEqual(deduction_percent_to_multiplier(7.5), 0.925)
        self.assertEqual(deduction_percent_to_multiplier(10), 0.9)

    def test_fixed_agency_fee_mode(self) -> None:
        candidates = resolve_fee_candidates(mode="Fixed amount", budget=100000, fixed_amount=25000, field_name="agency_fee")
        self.assertEqual(candidates, [{"amount": 25000.0, "percent": None}])

    def test_percentage_agency_fee_mode(self) -> None:
        candidates = resolve_fee_candidates(mode="Percentage of budget", budget=100000, percent_value="30%", field_name="agency_fee")
        self.assertEqual(candidates, [{"amount": 30000.0, "percent": 30.0}])

    def test_agency_fee_range_expansion(self) -> None:
        values = expand_percentage_range("29-30%", 0.5, "agency_fee")
        self.assertEqual([float(v) for v in values], [29.0, 29.5, 30.0])

    def test_fixed_paid_media_mode(self) -> None:
        candidates = resolve_fee_candidates(mode="Fixed amount", budget=100000, fixed_amount=15000, field_name="paid_media")
        self.assertEqual(candidates, [{"amount": 15000.0, "percent": None}])

    def test_percentage_paid_media_mode(self) -> None:
        candidates = resolve_fee_candidates(mode="Percentage of budget", budget=100000, percent_value=15, field_name="paid_media")
        self.assertEqual(candidates, [{"amount": 15000.0, "percent": 15.0}])

    def test_paid_media_range_expansion(self) -> None:
        values = expand_percentage_range("10–11%", 0.5, "paid_media")
        self.assertEqual([float(v) for v in values], [10.0, 10.5, 11.0])

    def test_invalid_percentage_ranges(self) -> None:
        with self.assertRaises(ValueError):
            parse_percentage_range("35-29%", "agency_fee")
        with self.assertRaises(ValueError):
            expand_percentage_range("invalid", 0.5, "paid_media")

    def test_max_combination_guard(self) -> None:
        agency_candidates = [{"amount": float(i), "percent": None} for i in range(30)]
        paid_candidates = [{"amount": float(i), "percent": None} for i in range(10)]
        with self.assertRaisesRegex(ValueError, "Too many fee/paid combinations"):
            build_fee_paid_combinations(agency_candidates, paid_candidates, max_combinations=MAX_MANUAL_FEE_COMBINATIONS)

    def test_manual_campaign_input_converts_to_model_shape(self) -> None:
        model = build_manual_campaign_model(
            campaign_name="Manual Test",
            budget=100000,
            agency_fee=10000,
            paid_media=20000,
            paid_media_included=True,
            profile_budget_target_multiplier=0.925,
            rows=[
                {
                    "row_index": 1,
                    "profile_size_cell": "",
                    "current_profile_size": "",
                    "channel": "Instagram",
                    "market": "SE",
                    "cpm": 1000,
                    "activations": 1,
                },
                {
                    "row_index": 2,
                    "profile_size_cell": "B2",
                    "current_profile_size": 35000,
                    "channel": "TikTok",
                    "market": "",
                    "cpm": 900,
                    "activations": 2,
                },
            ],
        )
        self.assertEqual(model.source.workbook_name, "Manual campaign")
        self.assertEqual(model.source.sheet_name, "Manual Test")
        self.assertEqual(model.source.classification, "manual_campaign_builder")
        self.assertEqual(len(model.profile_rows), 2)
        self.assertIsNone(model.profile_rows[0].current_profile_size)
        self.assertEqual(model.profile_rows[1].current_profile_size, 35000)
        self.assertEqual(model.profile_rows[1].channel, "TikTok")
        self.assertEqual(model.profile_budget_target_multiplier, 0.925)

    def test_validation_rejects_invalid_channel(self) -> None:
        errors = validate_manual_campaign_input(
            budget=100,
            agency_fee=10,
            paid_media=0,
            profile_budget_target_multiplier=0.925,
            rows=[{"channel": "LinkedIn", "cpm": 1000, "activations": 1, "current_profile_size": ""}],
        )
        self.assertTrue(any("channel must be one of" in error for error in errors))

    def test_validation_rejects_invalid_current_profile_size(self) -> None:
        errors = validate_manual_campaign_input(
            budget=100,
            agency_fee=10,
            paid_media=0,
            profile_budget_target_multiplier=0.925,
            rows=[{"channel": "Instagram", "cpm": 1000, "activations": 1, "current_profile_size": 25000}],
        )
        self.assertTrue(any("current_profile_size must be one of" in error for error in errors))

    def test_validation_rejects_missing_cpm_or_activations_or_zero_rows(self) -> None:
        errors_zero_rows = validate_manual_campaign_input(
            budget=100,
            agency_fee=10,
            paid_media=0,
            profile_budget_target_multiplier=0.925,
            rows=[],
        )
        self.assertTrue(any("At least one profile row is required" in error for error in errors_zero_rows))

        errors = validate_manual_campaign_input(
            budget=100,
            agency_fee=10,
            paid_media=0,
            profile_budget_target_multiplier=0.925,
            rows=[{"channel": "Instagram", "cpm": "", "activations": 0, "current_profile_size": ""}],
        )
        self.assertTrue(any("cpm is required" in error for error in errors))
        self.assertTrue(any("activations must be greater than 0" in error for error in errors))

    def test_manual_mode_baseline_unavailable_does_not_crash(self) -> None:
        model = build_manual_campaign_model(
            campaign_name="No baseline",
            budget=100000,
            agency_fee=10000,
            paid_media=0,
            paid_media_included=False,
            profile_budget_target_multiplier=0.925,
            rows=[
                {"row_index": 1, "channel": "Instagram", "market": "SE", "cpm": 1000, "activations": 1, "current_profile_size": ""},
                {"row_index": 2, "channel": "TikTok", "market": "SE", "cpm": 1000, "activations": 1, "current_profile_size": ""},
            ],
        )
        payload = run_optimizer_for_models([model], input_label="manual")
        result = payload["results"][0]
        self.assertFalse(result["search_diagnostics"]["current_baseline_available"])
        self.assertTrue(any("Baseline unavailable" in warning for warning in result["warnings"]))
        self.assertIsNone(next((option for option in result["options"] if option["option_label"] == "current_workbook_mix"), None))

    def test_manual_mode_with_valid_current_sizes_exposes_baseline(self) -> None:
        model = build_manual_campaign_model(
            campaign_name="With baseline",
            budget=100000,
            agency_fee=10000,
            paid_media=0,
            paid_media_included=False,
            profile_budget_target_multiplier=0.925,
            rows=[
                {"row_index": 1, "channel": "Instagram", "market": "SE", "cpm": 1000, "activations": 1, "current_profile_size": 35000},
                {"row_index": 2, "channel": "TikTok", "market": "SE", "cpm": 1000, "activations": 1, "current_profile_size": 75000},
            ],
        )
        payload = run_optimizer_for_models([model], input_label="manual")
        result = payload["results"][0]
        self.assertTrue(result["search_diagnostics"]["current_baseline_available"])
        self.assertIsNotNone(next((option for option in result["options"] if option["option_label"] == "current_workbook_mix"), None))

    def test_manual_optimizer_run_across_fee_paid_combinations_and_selected_values(self) -> None:
        base_rows = [
            {"row_index": 1, "channel": "Instagram", "market": "SE", "cpm": 1000, "activations": 1, "current_profile_size": ""},
            {"row_index": 2, "channel": "TikTok", "market": "SE", "cpm": 1000, "activations": 1, "current_profile_size": ""},
        ]
        agency_candidates = resolve_fee_candidates(
            mode="Percentage range",
            budget=100000,
            percent_range="10-11%",
            range_step=1,
            field_name="agency_fee",
        )
        paid_candidates = resolve_fee_candidates(
            mode="Percentage range",
            budget=100000,
            percent_range="0-1%",
            range_step=1,
            field_name="paid_media",
        )
        combinations = build_fee_paid_combinations(agency_candidates, paid_candidates, max_combinations=20)
        evaluation = evaluate_fee_paid_combinations(
            combinations=combinations,
            build_model_fn=lambda agency_candidate, paid_candidate: build_manual_campaign_model(
                campaign_name="Combo test",
                budget=100000,
                agency_fee=agency_candidate["amount"],
                paid_media=paid_candidate["amount"],
                paid_media_included=True,
                profile_budget_target_multiplier=0.925,
                rows=base_rows,
            ),
            run_optimizer_fn=lambda model: run_optimizer_for_models([model], input_label="manual"),
        )
        self.assertEqual(evaluation["combinations_evaluated"], len(combinations))
        self.assertIn("amount", evaluation["selected_agency"])
        self.assertIn("percent", evaluation["selected_agency"])
        self.assertIn("amount", evaluation["selected_paid_media"])
        self.assertIn("percent", evaluation["selected_paid_media"])
        self.assertIn("results", evaluation["payload"])
        self.assertIn("recommended_option_label", evaluation["result"])

    def test_manual_fee_combination_sort_prefers_non_negative_recommendation_over_closer_negative(self) -> None:
        combinations = [
            ({"amount": 10000.0, "percent": 10.0}, {"amount": 0.0, "percent": 0.0}),
            ({"amount": 11000.0, "percent": 11.0}, {"amount": 0.0, "percent": 0.0}),
        ]

        def _payload(label: str, diff: int, non_negative: bool, score: int) -> dict:
            return {
                "results": [
                    {
                        "recommended_option_label": label,
                        "options": [
                            {
                                "option_label": label,
                                "optimized_diff": diff,
                                "diagnostics": {"non_negative_diff": non_negative},
                                "recommendation_score_breakdown": {"total_score": score},
                            }
                        ],
                    }
                ]
            }

        payloads_by_agency = {
            10000.0: _payload("negative_closer", -1, False, 100000),
            11000.0: _payload("positive_buffer", 1000, True, 1),
        }
        evaluation = evaluate_fee_paid_combinations(
            combinations=combinations,
            build_model_fn=lambda agency_candidate, paid_candidate: agency_candidate,
            run_optimizer_fn=lambda agency_candidate: payloads_by_agency[agency_candidate["amount"]],
        )

        self.assertEqual(evaluation["selected_agency"]["amount"], 11000.0)
        self.assertEqual(evaluation["result"]["recommended_option_label"], "positive_buffer")

    def test_project_cpms_apply_to_generated_rows(self) -> None:
        project_cpms = resolve_project_cpms(instagram_cpm=1200, tiktok_cpm=950, youtube_cpm=800)
        split = parse_channel_split(total_profiles=5, instagram_count=2, tiktok_count=2, youtube_count=1)
        rows = generate_profile_rows(total_profiles=5, project_cpms=project_cpms, channel_split=split)
        self.assertEqual(len(rows), 5)
        self.assertEqual([row["row_index"] for row in rows], [1, 2, 3, 4, 5])
        self.assertEqual(sum(1 for row in rows if row["channel"] == "Instagram"), 2)
        self.assertEqual(sum(1 for row in rows if row["channel"] == "TikTok"), 2)
        self.assertEqual(sum(1 for row in rows if row["channel"] == "YouTube"), 1)
        for row in rows:
            self.assertEqual(row["cpm"], project_cpms[row["channel"]])

    def test_row_level_cpm_can_be_overridden_then_reapplied(self) -> None:
        project_cpms = resolve_project_cpms(instagram_cpm=1000, tiktok_cpm=900, youtube_cpm=700)
        rows = generate_profile_rows(
            total_profiles=3,
            project_cpms=project_cpms,
            channel_split={"Instagram": 1, "TikTok": 1, "YouTube": 1},
        )
        rows[0]["cpm"] = 1234
        self.assertEqual(rows[0]["cpm"], 1234)
        updated = apply_project_cpms_to_rows(rows, project_cpms)
        self.assertEqual(updated[0]["cpm"], 1000)

    def test_missing_cpm_for_used_channel_fails_validation_and_unused_is_ignored(self) -> None:
        rows = [
            {"channel": "Instagram", "cpm": 1000, "activations": 1},
            {"channel": "TikTok", "cpm": 900, "activations": 1},
        ]
        project_cpms_missing_used = resolve_project_cpms(instagram_cpm=1000, tiktok_cpm="", youtube_cpm="")
        with self.assertRaisesRegex(ValueError, "TikTok CPM is required"):
            validate_project_cpms_for_rows(rows, project_cpms_missing_used)

        project_cpms_unused_blank = resolve_project_cpms(instagram_cpm=1000, tiktok_cpm=900, youtube_cpm="")
        validate_project_cpms_for_rows(rows, project_cpms_unused_blank)

    def test_parse_channel_split_infers_single_blank_and_rejects_overflow(self) -> None:
        inferred = parse_channel_split(total_profiles=10, instagram_count=5, tiktok_count="", youtube_count=0)
        self.assertEqual(inferred, {"Instagram": 5, "TikTok": 5, "YouTube": 0})

        with self.assertRaisesRegex(ValueError, "exceeds total profiles"):
            parse_channel_split(total_profiles=10, instagram_count=6, tiktok_count=6, youtube_count=0)

    def test_parse_channel_split_blank_defaults_are_deterministic(self) -> None:
        split = parse_channel_split(total_profiles=8, instagram_count="", tiktok_count="", youtube_count="")
        self.assertEqual(split, {"Instagram": 3, "TikTok": 3, "YouTube": 2})

    def test_parse_channel_split_selected_channels_only(self) -> None:
        split = parse_channel_split(
            total_profiles=4,
            instagram_count="",
            tiktok_count="",
            youtube_count="",
            selected_channels=["Instagram", "TikTok"],
        )
        self.assertEqual(split, {"Instagram": 2, "TikTok": 2, "YouTube": 0})
        with self.assertRaisesRegex(ValueError, "not selected"):
            parse_channel_split(
                total_profiles=4,
                instagram_count=2,
                tiktok_count=2,
                youtube_count=1,
                selected_channels=["Instagram", "TikTok"],
            )

    def test_percentage_split_conversion_sums_to_total_profiles(self) -> None:
        split = parse_channel_percentage_split(
            total_profiles=7,
            percentages={"Instagram": 70, "TikTok": 30},
            selected_channels=["Instagram", "TikTok"],
        )
        self.assertEqual(sum(split.values()), 7)
        self.assertEqual(split, {"Instagram": 5, "TikTok": 2, "YouTube": 0})

    def test_percentage_split_requires_selected_channels_to_sum_to_100(self) -> None:
        with self.assertRaisesRegex(ValueError, "sum to 100"):
            parse_channel_percentage_split(
                total_profiles=7,
                percentages={"Instagram": 60, "TikTok": 30},
                selected_channels=["Instagram", "TikTok"],
            )

    def test_percentage_split_single_channel_gets_all_profiles(self) -> None:
        split = parse_channel_percentage_split(
            total_profiles=8,
            percentages={"TikTok": 20},
            selected_channels=["TikTok"],
        )
        self.assertEqual(split, {"Instagram": 0, "TikTok": 8, "YouTube": 0})

    def test_sync_two_channel_split_changing_instagram_sets_tiktok_remainder(self) -> None:
        import app

        with mock.patch.object(
            app.st,
            "session_state",
            {
                "manual_split_percent_instagram": 70,
                "manual_split_percent_tiktok": 50,
            },
        ):
            app._sync_two_channel_percentage_split("Instagram", ["Instagram", "TikTok"])
            self.assertEqual(app.st.session_state["manual_split_percent_instagram"], 70)
            self.assertEqual(app.st.session_state["manual_split_percent_tiktok"], 30)

    def test_sync_two_channel_split_changing_tiktok_sets_instagram_remainder(self) -> None:
        import app

        with mock.patch.object(
            app.st,
            "session_state",
            {
                "manual_split_percent_instagram": 50,
                "manual_split_percent_tiktok": 25,
            },
        ):
            app._sync_two_channel_percentage_split("TikTok", ["Instagram", "TikTok"])
            self.assertEqual(app.st.session_state["manual_split_percent_instagram"], 75)
            self.assertEqual(app.st.session_state["manual_split_percent_tiktok"], 25)

    def test_ensure_two_channel_split_preserves_existing_valid_state(self) -> None:
        import app

        with mock.patch.object(
            app.st,
            "session_state",
            {
                "manual_split_percent_instagram": 70,
                "manual_split_percent_tiktok": 30,
            },
        ):
            app._ensure_two_channel_percentage_split_state(["Instagram", "TikTok"])
            self.assertEqual(app.st.session_state["manual_split_percent_instagram"], 70)
            self.assertEqual(app.st.session_state["manual_split_percent_tiktok"], 30)

    def test_ensure_two_channel_split_normalizes_stale_state_from_first_channel(self) -> None:
        import app

        with mock.patch.object(
            app.st,
            "session_state",
            {
                "manual_split_percent_instagram": 70,
                "manual_split_percent_tiktok": 50,
            },
        ):
            app._ensure_two_channel_percentage_split_state(["Instagram", "TikTok"])
            self.assertEqual(app.st.session_state["manual_split_percent_instagram"], 70)
            self.assertEqual(app.st.session_state["manual_split_percent_tiktok"], 30)

    def test_single_channel_percentage_split_does_not_require_ui_sync(self) -> None:
        import app

        with mock.patch.object(app.st, "session_state", {}):
            app._ensure_two_channel_percentage_split_state(["TikTok"])
            split = parse_channel_percentage_split(
                total_profiles=8,
                percentages={"TikTok": app.st.session_state.get("manual_split_percent_tiktok")},
                selected_channels=["TikTok"],
            )
            self.assertEqual(app.st.session_state, {})
            self.assertEqual(split, {"Instagram": 0, "TikTok": 8, "YouTube": 0})

    def test_generate_profile_rows_respects_selected_channels(self) -> None:
        project_cpms = resolve_project_cpms(instagram_cpm=1000, tiktok_cpm=900, youtube_cpm="")
        rows = generate_profile_rows(
            total_profiles=4,
            project_cpms=project_cpms,
            channel_split={"Instagram": 2, "TikTok": 2, "YouTube": 0},
            selected_channels=["Instagram", "TikTok"],
        )
        self.assertEqual(len(rows), 4)
        self.assertEqual({row["channel"] for row in rows}, {"Instagram", "TikTok"})
        self.assertNotIn("YouTube", {row["channel"] for row in rows})

    def test_generate_profile_rows_single_selected_channel(self) -> None:
        project_cpms = resolve_project_cpms(instagram_cpm="", tiktok_cpm=900, youtube_cpm="")
        rows = generate_profile_rows(
            total_profiles=3,
            project_cpms=project_cpms,
            channel_split={"Instagram": 0, "TikTok": 3, "YouTube": 0},
            selected_channels=["TikTok"],
        )
        self.assertEqual(len(rows), 3)
        self.assertEqual({row["channel"] for row in rows}, {"TikTok"})

    def test_validate_rows_use_selected_channels(self) -> None:
        rows = [
            {"channel": "Instagram", "cpm": 1000, "activations": 1},
            {"channel": "YouTube", "cpm": 900, "activations": 1},
        ]
        with self.assertRaisesRegex(ValueError, "not selected"):
            validate_rows_use_selected_channels(rows, ["Instagram", "TikTok"])

    def test_validate_project_cpms_for_rows_ignores_unselected_channel(self) -> None:
        rows = [{"channel": "Instagram", "cpm": 1000, "activations": 1}]
        project_cpms = resolve_project_cpms(instagram_cpm=1000, tiktok_cpm="", youtube_cpm="")
        validate_project_cpms_for_rows(rows, project_cpms)
        rows_missing_selected = [{"channel": "TikTok", "cpm": 900, "activations": 1}]
        with self.assertRaisesRegex(ValueError, "TikTok CPM is required"):
            validate_project_cpms_for_rows(rows_missing_selected, project_cpms)

    def test_normalize_selected_channels_requires_supported_values(self) -> None:
        self.assertEqual(normalize_selected_channels(["TikTok", "Instagram"]), ["Instagram", "TikTok"])
        with self.assertRaisesRegex(ValueError, "Unsupported selected channel"):
            normalize_selected_channels(["LinkedIn"])

    def test_generate_profile_rows_requires_cpm_for_used_channel(self) -> None:
        project_cpms = resolve_project_cpms(instagram_cpm=1000, tiktok_cpm="", youtube_cpm=500)
        with self.assertRaisesRegex(ValueError, "TikTok CPM must be set"):
            generate_profile_rows(
                total_profiles=2,
                project_cpms=project_cpms,
                channel_split={"Instagram": 0, "TikTok": 2, "YouTube": 0},
            )

    def test_manual_builder_generated_rows_convert_and_run_optimizer(self) -> None:
        project_cpms = resolve_project_cpms(instagram_cpm=1000, tiktok_cpm=900, youtube_cpm=800)
        split = parse_channel_split(total_profiles=4, instagram_count=2, tiktok_count=2, youtube_count=0)
        rows = generate_profile_rows(total_profiles=4, project_cpms=project_cpms, channel_split=split)
        model = build_manual_campaign_model(
            campaign_name="Generated rows",
            budget=200000,
            agency_fee=20000,
            paid_media=10000,
            paid_media_included=True,
            profile_budget_target_multiplier=0.925,
            rows=rows,
        )
        payload = run_optimizer_for_models([model], input_label="manual")
        self.assertEqual(payload["campaign_count"], 1)
        self.assertGreaterEqual(len(payload["results"][0]["options"]), 2)

    def test_optimizer_runs_with_simplified_generated_rows(self) -> None:
        setup = build_simplified_budget_setup(100000, paid_media_included=True)
        split = parse_channel_percentage_split(
            total_profiles=setup["total_profiles"],
            percentages={"Instagram": 50, "TikTok": 50},
            selected_channels=["Instagram", "TikTok"],
        )
        rows = generate_profile_rows(
            total_profiles=setup["total_profiles"],
            project_cpms=SIMPLIFIED_FIXED_CPMS,
            channel_split=split,
            selected_channels=["Instagram", "TikTok"],
        )
        model = build_manual_campaign_model(
            campaign_name="Simplified generated rows",
            budget=setup["budget"],
            agency_fee=setup["agency_fee"],
            paid_media=setup["paid_media"],
            paid_media_included=True,
            profile_budget_target_multiplier=setup["profile_budget_target_multiplier"],
            rows=rows,
        )
        payload = run_optimizer_for_models([model], input_label="manual", top_n=3, allowed_tiers=None)
        self.assertEqual(payload["campaign_count"], 1)
        self.assertEqual(payload["results"][0]["profile_budget_target"], 44559.1)
        self.assertGreaterEqual(len(payload["results"][0]["options"]), 2)

    def test_paid_included_vs_excluded_changes_profile_budget_target(self) -> None:
        included_setup = build_simplified_budget_setup(100000, paid_media_included=True)
        excluded_setup = build_simplified_budget_setup(100000, paid_media_included=False)
        split = parse_channel_percentage_split(
            total_profiles=included_setup["total_profiles"],
            percentages={"Instagram": 50, "TikTok": 50},
            selected_channels=["Instagram", "TikTok"],
        )
        rows = generate_profile_rows(
            total_profiles=included_setup["total_profiles"],
            project_cpms=SIMPLIFIED_FIXED_CPMS,
            channel_split=split,
            selected_channels=["Instagram", "TikTok"],
        )
        included_model = build_manual_campaign_model(
            campaign_name="Included paid",
            budget=included_setup["budget"],
            agency_fee=included_setup["agency_fee"],
            paid_media=included_setup["paid_media"],
            paid_media_included=True,
            profile_budget_target_multiplier=included_setup["profile_budget_target_multiplier"],
            rows=rows,
        )
        excluded_model = build_manual_campaign_model(
            campaign_name="Excluded paid",
            budget=excluded_setup["budget"],
            agency_fee=excluded_setup["agency_fee"],
            paid_media=excluded_setup["paid_media"],
            paid_media_included=False,
            profile_budget_target_multiplier=excluded_setup["profile_budget_target_multiplier"],
            rows=rows,
        )
        self.assertEqual(float(compute_profile_budget_target(included_model)), 44559.1)
        self.assertEqual(float(compute_profile_budget_target(excluded_model)), 58434.1)

    def test_optimizer_allowed_tiers_flow_from_run_payload(self) -> None:
        project_cpms = resolve_project_cpms(instagram_cpm=1000, tiktok_cpm=900, youtube_cpm=800)
        rows = generate_profile_rows(
            total_profiles=3,
            project_cpms=project_cpms,
            channel_split={"Instagram": 2, "TikTok": 1, "YouTube": 0},
            selected_channels=["Instagram", "TikTok"],
        )
        model = build_manual_campaign_model(
            campaign_name="Allowed tiers",
            budget=200000,
            agency_fee=20000,
            paid_media=10000,
            paid_media_included=True,
            profile_budget_target_multiplier=0.925,
            rows=rows,
        )
        payload = run_optimizer_for_models(
            [model],
            input_label="manual",
            allowed_tiers=[15000, 35000],
            optimization_method="fast_closest_diff",
        )
        result = payload["results"][0]
        self.assertEqual(result["search_diagnostics"]["allowed_tiers"], [15000, 35000])
        for option in result["options"]:
            if option["option_label"] == "current_workbook_mix":
                continue
            for instruction in option["fill_instructions"]:
                self.assertIn(instruction["recommended_profile_size"], [15000, 35000])

    def test_optimizer_requires_at_least_one_allowed_tier(self) -> None:
        model = build_manual_campaign_model(
            campaign_name="No tiers",
            budget=100000,
            agency_fee=10000,
            paid_media=0,
            paid_media_included=False,
            profile_budget_target_multiplier=0.925,
            rows=[
                {"row_index": 1, "channel": "Instagram", "market": "SE", "cpm": 1000, "activations": 1, "current_profile_size": 35000},
            ],
        )
        with self.assertRaisesRegex(ValueError, "At least one allowed profile size tier is required"):
            run_optimizer_for_models([model], input_label="manual", allowed_tiers=[])

    def test_canonical_model_in_process_run_smoke(self) -> None:
        _, models = load_normalized_models(Path("data/normalized/canonical_normalized_models.json"))
        payload = run_optimizer_for_models([models[0]], input_label="canonical")
        self.assertEqual(payload["campaign_count"], 1)
        self.assertGreaterEqual(len(payload["results"][0]["options"]), 2)


if __name__ == "__main__":
    unittest.main()
