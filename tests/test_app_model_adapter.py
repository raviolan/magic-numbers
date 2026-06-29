from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from calculation_engine import load_normalized_models
from optimizer import run_optimizer_for_models
from ui_model_adapter import (
    DEFAULT_AGENCY_FEE_PERCENT_TEXT,
    DEFAULT_MANUAL_FEE_MODE,
    DEFAULT_PAID_MEDIA_INCLUDED,
    DEFAULT_PAID_MEDIA_PERCENT_TEXT,
    DEFAULT_SELECTED_MANUAL_CHANNELS,
    DEFAULT_PROFILE_FEE_DEDUCTION_PERCENT,
    MANUAL_FEE_MODES,
    MAX_MANUAL_FEE_COMBINATIONS,
    build_manual_campaign_model,
    build_fee_paid_combinations,
    deduction_percent_to_multiplier,
    evaluate_fee_paid_combinations,
    expand_percentage_range,
    format_display_number,
    apply_project_cpms_to_rows,
    choose_option_for_fill_view,
    generate_profile_rows,
    normalize_selected_channels,
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
                {"Item": "Total budget", "Value": "100 000"},
                {"Item": "Agency fee", "Value": "-10 000"},
                {"Item": "Paid media included in target", "Value": "-5 000"},
                {"Item": "Remaining profile-fee base", "Value": "85 000"},
                {"Item": "Profile fee deduction / extra agency fee, 7.5%", "Value": "-6 375"},
                {"Item": "Available profile-fee target", "Value": "78 625"},
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
        self.assertEqual(DEFAULT_AGENCY_FEE_PERCENT_TEXT, "32%")
        self.assertEqual(DEFAULT_PAID_MEDIA_PERCENT_TEXT, "15%")
        self.assertTrue(DEFAULT_PAID_MEDIA_INCLUDED)
        self.assertEqual(DEFAULT_SELECTED_MANUAL_CHANNELS, ("Instagram", "TikTok"))

    def test_default_deduction_percent_is_7_5_and_maps_to_0_925_multiplier(self) -> None:
        self.assertEqual(float(DEFAULT_PROFILE_FEE_DEDUCTION_PERCENT), 7.5)
        self.assertEqual(deduction_percent_to_multiplier(DEFAULT_PROFILE_FEE_DEDUCTION_PERCENT), 0.925)

    def test_deduction_percent_to_multiplier_conversion(self) -> None:
        self.assertEqual(deduction_percent_to_multiplier(0), 1.0)
        self.assertEqual(deduction_percent_to_multiplier(7.5), 0.925)
        self.assertEqual(deduction_percent_to_multiplier(10), 0.9)

    def test_fixed_agency_fee_mode(self) -> None:
        candidates = resolve_fee_candidates(mode="Fixed amount", budget=100000, fixed_amount=25000, field_name="agency_fee")
        self.assertEqual(candidates, [{"amount": 25000.0, "percent": None}])

    def test_percentage_agency_fee_mode(self) -> None:
        candidates = resolve_fee_candidates(mode="Percentage of budget", budget=100000, percent_value="32%", field_name="agency_fee")
        self.assertEqual(candidates, [{"amount": 32000.0, "percent": 32.0}])

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
