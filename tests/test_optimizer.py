from __future__ import annotations

from pathlib import Path
import json
from unittest import mock
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from models import CanonicalCampaignModel, CanonicalDiff, CanonicalProfileRow, CanonicalProfileSection, CanonicalSource
from optimizer import (
    DEFAULT_EXACT_MAX_STATES,
    VALID_PROFILE_TIERS,
    analyze_option_strategy,
    build_terminal_summary,
    choose_output_paths,
    compute_profile_budget_target,
    compute_recommendation_score,
    generate_row_candidates,
    group_recommended_options,
    normalize_allowed_tiers,
    optimize_model,
    open_report,
    render_optimizer_markdown,
    resolve_unique_sheet_selection,
    run_optimizer,
    slugify_result_name,
    select_recommended_option,
    search_best_assignments,
)


def build_row(
    row_index: int,
    channel: str = "TikTok",
    market: str | None = "SE",
    cpm: int = 800,
    activations: int = 1,
    current_profile_size: int = 35000,
) -> CanonicalProfileRow:
    return CanonicalProfileRow(
        row_index=row_index,
        profile_size_cell=f"B{row_index}",
        current_profile_size=current_profile_size,
        workbook_raw_profile_size_value=current_profile_size // 1000,
        market=market,
        channel=channel,
        raw_channel_label=channel,
        cpm=cpm,
        cpm_cell=f"G{row_index}",
        cpm_value=cpm,
        activations=activations,
        activations_cell=f"C{row_index}",
        activations_value=activations,
        impressions_cell=f"F{row_index}",
        impressions_value=None,
        profile_fee_cell=f"H{row_index}",
        profile_fee_value=None,
        locked=False,
        warnings=[],
    )


def build_model(
    rows: list[CanonicalProfileRow],
    budget: int = 100000,
    agency_fee: int = 10000,
    paid_media: int = 0,
    paid_media_included: bool = False,
    workbook_name: str = "Book.xlsx",
    sheet_name: str = "Sheet",
) -> CanonicalCampaignModel:
    return CanonicalCampaignModel(
        source=CanonicalSource(workbook_name, "path.xlsx", sheet_name, 0, "canonical_candidate"),
        budget=budget,
        agency_fee=agency_fee,
        paid_media=paid_media,
        paid_media_included=paid_media_included,
        profile_budget_target_multiplier=0.925,
        profile_budget_target_cell="H3",
        profile_budget_target_value=None,
        profile_fee_sum_cell="H4",
        profile_fee_sum_value=None,
        profile_section=CanonicalProfileSection("A1", "A1 (row 1)", len(rows)),
        profile_rows=rows,
        diff=CanonicalDiff(cell="H5", value=None),
        warnings=[],
    )


class OptimizerTests(unittest.TestCase):
    def _build_manual_option(
        self,
        label: str,
        diff: int | float,
        tier_counts: dict[str, int],
    ) -> dict[str, object]:
        return {
            "option_label": label,
            "optimized_diff": diff,
            "profile_fee_sum": 0,
            "profile_budget_target": 0,
            "tier_counts": tier_counts,
            "total_impressions": 0,
            "impressions_by_channel": {},
            "impressions_by_market": {},
            "fill_instructions": [],
            "diagnostics": {"non_negative_diff": diff >= 0, "abs_diff": abs(diff), "strategic_notes": []},
            "strategic_metrics": {"row_count": sum(tier_counts.values()), "avg_profile_size": 35000},
            "recommendation_score_breakdown": {},
        }

    def test_generate_row_candidates_preserves_fields_and_uses_validated_formula(self) -> None:
        row = build_row(2, channel="TikTok", market="UK", cpm=800, activations=2, current_profile_size=35000)
        candidates = generate_row_candidates(row)

        self.assertEqual(len(candidates), 5)
        self.assertEqual([candidate.recommended_profile_size for candidate in candidates], list(VALID_PROFILE_TIERS))
        candidate = candidates[1]
        self.assertEqual(candidate.row_index, row.row_index)
        self.assertEqual(candidate.profile_size_cell, row.profile_size_cell)
        self.assertEqual(candidate.channel, "TikTok")
        self.assertEqual(candidate.market, "UK")
        self.assertEqual(candidate.cpm, 800)
        self.assertEqual(candidate.activations, 2)
        self.assertEqual(candidate.impressions, 30)
        self.assertEqual(candidate.row_fee, 48000)

    def test_generate_row_candidates_respects_allowed_tiers(self) -> None:
        row = build_row(2, channel="TikTok", market="UK", cpm=800, activations=2, current_profile_size=35000)
        candidates = generate_row_candidates(row, allowed_tiers=(35000, 75000))
        self.assertEqual([candidate.recommended_profile_size for candidate in candidates], [35000, 75000])

    def test_normalize_allowed_tiers_rejects_invalid_or_empty(self) -> None:
        self.assertEqual(normalize_allowed_tiers(None), VALID_PROFILE_TIERS)
        with self.assertRaisesRegex(ValueError, "unsupported tiers"):
            normalize_allowed_tiers([12345])
        with self.assertRaisesRegex(ValueError, "At least one allowed profile size tier is required"):
            normalize_allowed_tiers([])

    def test_profile_budget_target_and_optimized_diff_use_validated_path(self) -> None:
        model = build_model([build_row(2, cpm=800)], budget=100000, agency_fee=10000, paid_media=5000, paid_media_included=True)
        target = compute_profile_budget_target(model)
        self.assertEqual(target, 78625)

        result = optimize_model(model, beam_width=20, top_n=3)
        self.assertEqual(
            result["budget_breakdown"],
            {
                "budget": 100000,
                "agency_fee": 10000,
                "paid_media": 5000,
                "paid_media_included": True,
                "profile_budget_target_multiplier": 0.925,
                "profile_budget_target": 78625,
            },
        )
        best_math = next(option for option in result["options"] if option["option_label"] == "best_mathematical_fit")
        self.assertEqual(best_math["profile_budget_target"], 78625)
        self.assertEqual(best_math["optimized_diff"], best_math["profile_budget_target"] - best_math["profile_fee_sum"])

    def test_markdown_report_includes_budget_breakdown_agency_fee(self) -> None:
        model = build_model([build_row(2, cpm=800)], budget=100000, agency_fee=10000, paid_media=5000, paid_media_included=True)
        result = optimize_model(model, beam_width=20, top_n=3)
        payload = {
            "input_file": "manual_campaign_builder",
            "selected_formula": "thousands_rounded_path",
            "search_method": {
                "name": "bounded_beam_search",
                "bounded": True,
                "approximate": True,
                "global_optimality_guaranteed": False,
            },
            "campaign_count": 1,
            "options_generated": len(result["options"]),
            "strategy": "math",
            "allow_negative": False,
            "beam_width": 20,
            "allowed_tiers": list(VALID_PROFILE_TIERS),
            "warnings": [],
            "executive_summary": [],
            "results": [result],
        }

        markdown = render_optimizer_markdown(payload)

        self.assertIn("### Budget Breakdown", markdown)
        self.assertIn("- Agency fee: 10000", markdown)
        self.assertIn("- Paid media included in target: yes", markdown)
        self.assertIn("- Available profile-fee target: 78625", markdown)

    def test_group_recommended_options_prefers_non_negative_fit_when_abs_diff_matches(self) -> None:
        baseline = {
            "option_label": "current_workbook_mix",
            "optimized_diff": 2000,
            "profile_fee_sum": 0,
            "profile_budget_target": 0,
            "tier_counts": {"15000": 1, "35000": 0, "75000": 0, "125000": 0, "175000": 0},
            "total_impressions": 0,
            "impressions_by_channel": {},
            "impressions_by_market": {},
            "fill_instructions": [],
            "diagnostics": {"non_negative_diff": True, "abs_diff": 2000, "strategic_notes": []},
            "strategic_metrics": {"row_count": 1, "count_15k": 1, "count_75k_plus": 0, "count_125k_plus": 0, "count_175k": 0, "mid_tier_count": 0, "avg_profile_size": 15000},
            "assignment_signature": (15000,),
            "rank": 0,
        }
        positive = {
            "option_label": "candidate",
            "optimized_diff": 1000,
            "profile_fee_sum": 0,
            "profile_budget_target": 0,
            "tier_counts": {"15000": 0, "35000": 1, "75000": 0, "125000": 0, "175000": 0},
            "total_impressions": 0,
            "impressions_by_channel": {},
            "impressions_by_market": {},
            "fill_instructions": [],
            "diagnostics": {"non_negative_diff": True, "abs_diff": 1000, "strategic_notes": []},
            "strategic_metrics": {"row_count": 1, "count_15k": 0, "count_75k_plus": 0, "count_125k_plus": 0, "count_175k": 0, "mid_tier_count": 1, "avg_profile_size": 35000},
            "assignment_signature": (35000,),
            "rank": 1,
        }
        negative = {
            "option_label": "candidate",
            "optimized_diff": -1000,
            "profile_fee_sum": 0,
            "profile_budget_target": 0,
            "tier_counts": {"15000": 1, "35000": 0, "75000": 0, "125000": 0, "175000": 0},
            "total_impressions": 0,
            "impressions_by_channel": {},
            "impressions_by_market": {},
            "fill_instructions": [],
            "diagnostics": {"non_negative_diff": False, "abs_diff": 1000, "strategic_notes": []},
            "strategic_metrics": {"row_count": 1, "count_15k": 1, "count_75k_plus": 0, "count_125k_plus": 0, "count_175k": 0, "mid_tier_count": 0, "avg_profile_size": 15000},
            "assignment_signature": (15000,),
            "rank": 2,
        }

        grouped = group_recommended_options([negative, positive, baseline], baseline_option=baseline, top_n=2, allow_negative=False, strategy="math")
        self.assertEqual(grouped[0]["option_label"], "best_mathematical_fit")
        self.assertEqual(grouped[0]["optimized_diff"], 1000)
        self.assertEqual(grouped[-1]["option_label"], "current_workbook_mix")

    def test_group_recommended_options_does_not_duplicate_closest_positive_when_same_as_best_math(self) -> None:
        option = {
            "option_label": "candidate",
            "optimized_diff": 100,
            "profile_fee_sum": 0,
            "profile_budget_target": 0,
            "tier_counts": {"15000": 0, "35000": 1, "75000": 0, "125000": 0, "175000": 0},
            "total_impressions": 0,
            "impressions_by_channel": {},
            "impressions_by_market": {},
            "fill_instructions": [],
            "diagnostics": {"non_negative_diff": True, "abs_diff": 100, "strategic_notes": []},
            "strategic_metrics": {"row_count": 1, "count_15k": 0, "count_75k_plus": 0, "count_125k_plus": 0, "count_175k": 0, "mid_tier_count": 1, "avg_profile_size": 35000},
            "assignment_signature": (35000,),
            "rank": 1,
        }
        grouped = group_recommended_options([option], baseline_option=None, top_n=4, allow_negative=False, strategy="math")
        labels = [entry["option_label"] for entry in grouped]
        self.assertIn("best_mathematical_fit", labels)
        self.assertNotIn("closest_positive_diff", labels)

    def test_group_recommended_options_includes_closest_positive_when_distinct(self) -> None:
        negative_best = {
            "option_label": "candidate",
            "optimized_diff": -1,
            "profile_fee_sum": 0,
            "profile_budget_target": 0,
            "tier_counts": {"15000": 1, "35000": 0, "75000": 0, "125000": 0, "175000": 0},
            "total_impressions": 0,
            "impressions_by_channel": {},
            "impressions_by_market": {},
            "fill_instructions": [],
            "diagnostics": {"non_negative_diff": False, "abs_diff": 1, "strategic_notes": []},
            "strategic_metrics": {"row_count": 1, "count_15k": 1, "count_75k_plus": 0, "count_125k_plus": 0, "count_175k": 0, "mid_tier_count": 0, "avg_profile_size": 15000},
            "assignment_signature": (15000,),
            "rank": 1,
        }
        positive = {
            "option_label": "candidate",
            "optimized_diff": 5,
            "profile_fee_sum": 0,
            "profile_budget_target": 0,
            "tier_counts": {"15000": 0, "35000": 1, "75000": 0, "125000": 0, "175000": 0},
            "total_impressions": 0,
            "impressions_by_channel": {},
            "impressions_by_market": {},
            "fill_instructions": [],
            "diagnostics": {"non_negative_diff": True, "abs_diff": 5, "strategic_notes": []},
            "strategic_metrics": {"row_count": 1, "count_15k": 0, "count_75k_plus": 0, "count_125k_plus": 0, "count_175k": 0, "mid_tier_count": 1, "avg_profile_size": 35000},
            "assignment_signature": (35000,),
            "rank": 2,
        }
        grouped = group_recommended_options([negative_best, positive], baseline_option=None, top_n=4, allow_negative=True, strategy="math")
        self.assertIn("closest_positive_diff", [entry["option_label"] for entry in grouped])

    def test_strategic_fit_can_differ_from_math_fit_when_math_is_comparable(self) -> None:
        math_best = {
            "option_label": "candidate",
            "optimized_diff": 1000,
            "profile_fee_sum": 0,
            "profile_budget_target": 0,
            "tier_counts": {"15000": 2, "35000": 0, "75000": 0, "125000": 0, "175000": 0},
            "total_impressions": 0,
            "impressions_by_channel": {},
            "impressions_by_market": {},
            "fill_instructions": [],
            "diagnostics": {"non_negative_diff": True, "abs_diff": 1000, "strategic_notes": []},
            "strategic_metrics": {"row_count": 2, "count_15k": 2, "count_75k_plus": 0, "count_125k_plus": 0, "count_175k": 0, "mid_tier_count": 0, "avg_profile_size": 15000},
            "assignment_signature": (15000, 15000),
            "rank": 1,
        }
        strategic_candidate = {
            "option_label": "candidate",
            "optimized_diff": 1500,
            "profile_fee_sum": 0,
            "profile_budget_target": 0,
            "tier_counts": {"15000": 0, "35000": 1, "75000": 1, "125000": 0, "175000": 0},
            "total_impressions": 0,
            "impressions_by_channel": {},
            "impressions_by_market": {},
            "fill_instructions": [],
            "diagnostics": {"non_negative_diff": True, "abs_diff": 1500, "strategic_notes": []},
            "strategic_metrics": {"row_count": 2, "count_15k": 0, "count_75k_plus": 1, "count_125k_plus": 0, "count_175k": 0, "mid_tier_count": 2, "avg_profile_size": 55000},
            "assignment_signature": (35000, 75000),
            "rank": 2,
        }
        fallback = {
            "option_label": "candidate",
            "optimized_diff": 5000,
            "profile_fee_sum": 0,
            "profile_budget_target": 0,
            "tier_counts": {"15000": 1, "35000": 1, "75000": 0, "125000": 0, "175000": 0},
            "total_impressions": 0,
            "impressions_by_channel": {},
            "impressions_by_market": {},
            "fill_instructions": [],
            "diagnostics": {"non_negative_diff": True, "abs_diff": 5000, "strategic_notes": []},
            "strategic_metrics": {"row_count": 2, "count_15k": 1, "count_75k_plus": 0, "count_125k_plus": 0, "count_175k": 0, "mid_tier_count": 1, "avg_profile_size": 25000},
            "assignment_signature": (15000, 35000),
            "rank": 3,
        }
        baseline = {
            "option_label": "current_workbook_mix",
            "optimized_diff": 2000,
            "profile_fee_sum": 0,
            "profile_budget_target": 0,
            "tier_counts": {"15000": 1, "35000": 1, "75000": 0, "125000": 0, "175000": 0},
            "total_impressions": 0,
            "impressions_by_channel": {},
            "impressions_by_market": {},
            "fill_instructions": [],
            "diagnostics": {"non_negative_diff": True, "abs_diff": 2000, "strategic_notes": []},
            "strategic_metrics": {"row_count": 2, "count_15k": 1, "count_75k_plus": 0, "count_125k_plus": 0, "count_175k": 0, "mid_tier_count": 1, "avg_profile_size": 25000},
            "assignment_signature": (15000, 35000),
            "rank": 0,
        }

        grouped = group_recommended_options(
            [math_best, strategic_candidate, fallback, baseline],
            baseline_option=baseline,
            top_n=3,
            allow_negative=False,
            strategy="math",
        )
        best_math = next(option for option in grouped if option["option_label"] == "best_mathematical_fit")
        best_strategic = next(option for option in grouped if option["option_label"] == "best_strategic_fit")

        self.assertEqual(best_math["assignment_signature"], (15000, 15000))
        self.assertEqual(best_strategic["assignment_signature"], (35000, 75000))
        self.assertLessEqual(best_strategic["diagnostics"]["abs_diff"], best_math["diagnostics"]["abs_diff"] + 5000)
        self.assertLess(best_strategic["tier_counts"]["15000"], best_math["tier_counts"]["15000"])

    def test_bounded_search_does_not_explode_to_full_cartesian_product(self) -> None:
        rows = [build_row(row_index=2 + index, channel="TikTok", cpm=800) for index in range(30)]
        model = build_model(rows, budget=2000000, agency_fee=100000)
        result = search_best_assignments(model, beam_width=200, top_n=3)
        diagnostics = result["search_diagnostics"]

        self.assertEqual(diagnostics["row_count"], 30)
        self.assertEqual(diagnostics["candidate_count_per_row"], [5] * 30)
        self.assertLessEqual(diagnostics["max_frontier_after_prune"], 200)
        self.assertLess(diagnostics["max_frontier_before_prune"], 5 ** 30)
        self.assertTrue(diagnostics["current_baseline_included"])

    def test_exact_search_reports_global_optimality_and_respects_allowed_tiers(self) -> None:
        rows = [build_row(2, channel="TikTok", cpm=800), build_row(3, channel="TikTok", cpm=800)]
        model = build_model(rows, budget=90000, agency_fee=10000)
        result = search_best_assignments(
            model,
            top_n=3,
            optimization_method="exact_closest_diff",
            allowed_tiers=[15000, 35000],
            max_exact_states=50000,
        )
        diagnostics = result["search_diagnostics"]
        self.assertEqual(diagnostics["search_method"], "exact_fee_sum_search")
        self.assertTrue(diagnostics["global_optimality_guaranteed"])
        self.assertEqual(diagnostics["allowed_tiers"], [15000, 35000])
        for option in result["options"]:
            for instruction in option["fill_instructions"]:
                self.assertIn(instruction["recommended_profile_size"], [15000, 35000])

    def test_exact_search_state_limit_raises_clear_error(self) -> None:
        rows = [build_row(row_index=2 + index, channel="TikTok", cpm=800) for index in range(6)]
        model = build_model(rows, budget=400000, agency_fee=10000)
        with self.assertRaisesRegex(ValueError, "Exact search exceeded safe state limit"):
            search_best_assignments(
                model,
                optimization_method="exact_closest_diff",
                max_exact_states=5,
            )

    def test_build_option_includes_fill_instructions_and_preserves_fixed_fields(self) -> None:
        model = build_model([build_row(2, channel="Instagram", market="US", cpm=1000)], budget=100000, agency_fee=10000)
        state = search_best_assignments(model, beam_width=10, top_n=2)["options"][0]
        instruction = state["fill_instructions"][0]

        self.assertIn("profile_size_cell", instruction)
        self.assertIn("previous_profile_size", instruction)
        self.assertIn("recommended_profile_size", instruction)
        self.assertIn("channel", instruction)
        self.assertIn("market", instruction)
        self.assertIn("cpm", instruction)
        self.assertIn("activations", instruction)
        self.assertIn("row_fee", instruction)
        self.assertEqual(instruction["profile_size_cell"], "B2")
        self.assertEqual(instruction["channel"], "Instagram")
        self.assertEqual(instruction["market"], "US")
        self.assertEqual(instruction["cpm"], 1000)
        self.assertEqual(instruction["activations"], 1)

    def test_current_workbook_mix_is_always_included_and_best_math_is_not_worse(self) -> None:
        rows = [build_row(2, current_profile_size=35000, cpm=800), build_row(3, current_profile_size=35000, cpm=800)]
        model = build_model(rows, budget=90000, agency_fee=10000)
        result = optimize_model(model, beam_width=20, top_n=3)

        baseline = next(option for option in result["options"] if option["option_label"] == "current_workbook_mix")
        best_math = next(option for option in result["options"] if option["option_label"] == "best_mathematical_fit")
        self.assertEqual(len(baseline["fill_instructions"]), 2)
        self.assertLessEqual(abs(best_math["optimized_diff"]), abs(baseline["optimized_diff"]))
        self.assertTrue(result["search_diagnostics"]["current_baseline_included"])
        self.assertIn("best_mathematical_fit_baseline_comparison", result["search_diagnostics"])
        self.assertIn("best_mathematical_fit_improves_on_current_baseline", result["search_diagnostics"])
        self.assertIn("best_mathematical_fit_equals_current_baseline", result["search_diagnostics"])
        self.assertIn("recommended_option_label", result)
        self.assertIn("recommendation_reason", result)
        self.assertIn("recommendation_score_breakdown", result)

    def test_optimize_model_with_excluded_baseline_tier_disables_baseline_but_keeps_allowed_recommendations(self) -> None:
        rows = [build_row(2, current_profile_size=175000, cpm=800), build_row(3, current_profile_size=175000, cpm=800)]
        model = build_model(rows, budget=90000, agency_fee=10000)
        result = optimize_model(
            model,
            allowed_tiers=[15000, 35000, 75000],
            optimization_method="fast_closest_diff",
        )
        self.assertFalse(result["search_diagnostics"]["current_baseline_available"])
        self.assertTrue(any("excluded by allowed profile sizes" in warning for warning in result["warnings"]))
        for option in result["options"]:
            if option["option_label"] == "current_workbook_mix":
                continue
            for instruction in option["fill_instructions"]:
                self.assertIn(instruction["recommended_profile_size"], [15000, 35000, 75000])

    def test_recommendation_selector_is_deterministic_and_can_differ_from_math_best(self) -> None:
        baseline = self._build_manual_option(
            "current_workbook_mix",
            1000,
            {"15000": 0, "35000": 10, "75000": 0, "125000": 0, "175000": 0},
        )
        math_best = self._build_manual_option(
            "best_mathematical_fit",
            10,
            {"15000": 8, "35000": 0, "75000": 0, "125000": 0, "175000": 2},
        )
        balanced = self._build_manual_option(
            "balanced_option",
            200,
            {"15000": 0, "35000": 4, "75000": 4, "125000": 2, "175000": 0},
        )
        analyzed = [
            analyze_option_strategy(math_best, baseline, 10, "best_mathematical_fit"),
            analyze_option_strategy(balanced, baseline, 10, "best_mathematical_fit"),
            analyze_option_strategy(baseline, baseline, 10, "best_mathematical_fit"),
        ]
        for option in analyzed:
            option["recommendation_score_breakdown"] = compute_recommendation_score(option)

        first_pick = select_recommended_option(analyzed)
        second_pick = select_recommended_option(analyzed)
        self.assertEqual(first_pick, second_pick)
        self.assertEqual(first_pick[0], "balanced_option")

    def test_recommendation_selector_prefers_positive_over_closer_negative(self) -> None:
        negative = self._build_manual_option(
            "negative_closer",
            -1,
            {"15000": 1, "35000": 0, "75000": 0, "125000": 0, "175000": 0},
        )
        positive = self._build_manual_option(
            "positive_buffer",
            1000,
            {"15000": 0, "35000": 1, "75000": 0, "125000": 0, "175000": 0},
        )
        negative["strategic_warning_count"] = 0
        negative["strategic_warnings"] = []
        negative["recommendation_score_breakdown"] = {"total_score": 100000}
        positive["strategic_warning_count"] = 0
        positive["strategic_warnings"] = []
        positive["recommendation_score_breakdown"] = {"total_score": 1}

        selected_label, _ = select_recommended_option([negative, positive])

        self.assertEqual(selected_label, "positive_buffer")

    def test_strategic_warning_rules_are_neutral_and_structural(self) -> None:
        baseline = self._build_manual_option(
            "current_workbook_mix",
            2000,
            {"15000": 2, "35000": 8, "75000": 0, "125000": 0, "175000": 0},
        )
        polarized = self._build_manual_option(
            "best_mathematical_fit",
            100,
            {"15000": 6, "35000": 0, "75000": 0, "125000": 0, "175000": 4},
        )
        analyzed = analyze_option_strategy(polarized, baseline, 10, "best_mathematical_fit")
        self.assertIn("Highly concentrated tier mix", analyzed["strategic_warnings"])
        self.assertIn("Polarized mix: heavy use of smallest and largest tiers", analyzed["strategic_warnings"])
        self.assertIn("Low mid-tier representation", analyzed["strategic_warnings"])
        self.assertIn("Closest mathematical fit, but distribution has risk flags.", analyzed["strategic_notes"])
        self.assertNotIn("Very high 15K share", analyzed["strategic_warnings"])

    def test_budget_guidance_warns_when_100k_uses_profiles_above_35k(self) -> None:
        baseline = self._build_manual_option(
            "current_workbook_mix",
            1000,
            {"15000": 2, "35000": 2, "75000": 0, "125000": 0, "175000": 0},
        )
        option = self._build_manual_option(
            "best_mathematical_fit",
            100,
            {"15000": 2, "35000": 1, "75000": 1, "125000": 0, "175000": 0},
        )
        analyzed = analyze_option_strategy(option, baseline, 4, "best_mathematical_fit", budget=100000)
        self.assertIn(
            "100K budget: profile sizes above 35K are outside the recommended max for this preset.",
            analyzed["strategic_warnings"],
        )
        self.assertEqual(analyzed["budget_guidance_warning_count"], 1)

    def test_budget_guidance_allows_100k_larger_profile_focus_above_35k(self) -> None:
        baseline = self._build_manual_option(
            "current_workbook_mix",
            1000,
            {"15000": 1, "35000": 1, "75000": 0, "125000": 0, "175000": 0},
        )
        option = self._build_manual_option(
            "best_mathematical_fit",
            100,
            {"15000": 0, "35000": 1, "75000": 1, "125000": 0, "175000": 0},
        )
        analyzed = analyze_option_strategy(
            option,
            baseline,
            2,
            "best_mathematical_fit",
            budget=100000,
            optimization_focus="Larger profile sizes",
        )
        self.assertNotIn(
            "100K budget: profile sizes above 35K are outside the recommended max for this preset.",
            analyzed["strategic_warnings"],
        )
        self.assertEqual(analyzed["budget_guidance_warning_count"], 0)

    def test_budget_guidance_treats_125k_and_175k_as_same_anchor_rule_at_250k(self) -> None:
        baseline = self._build_manual_option(
            "current_workbook_mix",
            1000,
            {"15000": 3, "35000": 2, "75000": 2, "125000": 0, "175000": 0},
        )
        one_anchor = self._build_manual_option(
            "best_mathematical_fit",
            100,
            {"15000": 3, "35000": 2, "75000": 1, "125000": 0, "175000": 1},
        )
        two_anchors = self._build_manual_option(
            "balanced_option",
            100,
            {"15000": 3, "35000": 2, "75000": 0, "125000": 1, "175000": 1},
        )

        analyzed_one = analyze_option_strategy(one_anchor, baseline, 7, "best_mathematical_fit", budget=250000)
        analyzed_two = analyze_option_strategy(two_anchors, baseline, 7, "best_mathematical_fit", budget=250000)

        self.assertIn(
            "250K budget: one 125K+ anchor profile is borderline; keep the rest of the mix efficient.",
            analyzed_one["strategic_notes"],
        )
        self.assertNotIn("250K budget: use at most 1 profile at 125K or larger.", analyzed_one["strategic_warnings"])
        self.assertIn("250K budget: use at most 1 profile at 125K or larger.", analyzed_two["strategic_warnings"])

    def test_budget_guidance_allows_125k_plus_anchor_tiers_at_300k_and_keeps_175k_valid(self) -> None:
        self.assertIn(175000, VALID_PROFILE_TIERS)
        baseline = self._build_manual_option(
            "current_workbook_mix",
            1000,
            {"15000": 2, "35000": 3, "75000": 2, "125000": 0, "175000": 0},
        )
        option = self._build_manual_option(
            "best_mathematical_fit",
            100,
            {"15000": 2, "35000": 2, "75000": 1, "125000": 1, "175000": 1},
        )
        analyzed = analyze_option_strategy(option, baseline, 7, "best_mathematical_fit", budget=300000)
        self.assertFalse(
            any("recommended max" in warning or "125K or larger" in warning for warning in analyzed["strategic_warnings"])
        )

    def test_recommendation_score_is_not_penalized_for_15k_usage_by_default(self) -> None:
        baseline = self._build_manual_option(
            "current_workbook_mix",
            1000,
            {"15000": 1, "35000": 1, "75000": 0, "125000": 0, "175000": 0},
        )
        high_15k = self._build_manual_option(
            "best_mathematical_fit",
            100,
            {"15000": 6, "35000": 2, "75000": 1, "125000": 1, "175000": 0},
        )
        analyzed = analyze_option_strategy(high_15k, baseline, 10, "best_mathematical_fit")
        score = compute_recommendation_score(analyzed)
        self.assertEqual(score["small_tier_penalty"], 0.0)

    def test_run_optimizer_smoke_on_canonical_models(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            json_output = Path(temp_dir) / "optimizer_results.json"
            markdown_output = Path(temp_dir) / "optimizer_results.md"
            run_result = run_optimizer(
                input_path=Path("data/normalized/canonical_normalized_models.json"),
                json_output_path=json_output,
                markdown_output_path=markdown_output,
                top_n=5,
                beam_width=300,
            )
            payload = run_result["payload"]
            json_payload = json.loads(json_output.read_text(encoding="utf-8"))
            markdown = markdown_output.read_text(encoding="utf-8")

        self.assertEqual(payload["campaign_count"], 6)
        self.assertEqual(json_payload["selected_formula"], "thousands_rounded_path")
        self.assertIn("# Optimizer Results", markdown)
        self.assertIn("## Executive Summary", markdown)
        self.assertIn("### Recommendation", markdown)
        self.assertIn("### Option Comparison", markdown)
        self.assertIn("### Fill Instructions for Recommended Option", markdown)
        self.assertIn("- Search method: bounded_beam_search", markdown)
        self.assertIn("global_optimality_guaranteed=False", markdown)

        summary_rows = json_payload.get("executive_summary", [])
        self.assertEqual(len(summary_rows), 6)

        recommended_differs_somewhere = False
        for result in json_payload["results"]:
            self.assertGreaterEqual(len(result["options"]), 2)
            self.assertEqual(result["row_count"], len(result["options"][0]["fill_instructions"]))
            self.assertTrue(result["search_diagnostics"]["current_baseline_included"])
            self.assertIn("recommended_option_label", result)
            self.assertIn("recommendation_reason", result)
            self.assertIn("recommendation_score_breakdown", result)
            self.assertIn("option_comparison", result)
            baseline = next(option for option in result["options"] if option["option_label"] == "current_workbook_mix")
            best_math = next(option for option in result["options"] if option["option_label"] == "best_mathematical_fit")
            recommended = next(option for option in result["options"] if option["option_label"] == result["recommended_option_label"])
            self.assertEqual(
                sum(1 for option in result["options"] if option["option_label"] == result["recommended_option_label"]),
                1,
            )
            self.assertLessEqual(abs(best_math["optimized_diff"]), abs(baseline["optimized_diff"]))
            self.assertIn("recommendation_rank", recommended)
            self.assertEqual(recommended["recommendation_rank"], 1)
            if result["recommended_option_label"] != "best_mathematical_fit":
                recommended_differs_somewhere = True
            self.assertIn(
                result["search_diagnostics"]["best_mathematical_fit_baseline_comparison"],
                {"improves", "equals", "worse"},
            )
            for option in result["options"]:
                self.assertEqual(len(option["fill_instructions"]), result["row_count"])
                for instruction in option["fill_instructions"]:
                    self.assertIn(instruction["recommended_profile_size"], VALID_PROFILE_TIERS)
                    self.assertIn("cpm", instruction)
                    self.assertIn("activations", instruction)
                self.assertIn("strategic_notes", option)
                self.assertIn("strategic_warnings", option)
                self.assertIn("recommendation_score_breakdown", option)
                self.assertIn("improves_on_baseline", option)
        self.assertTrue(recommended_differs_somewhere)

    def test_slugify_result_name(self) -> None:
        slug = slugify_result_name("5312 Medclair Kalkyl (V.A)-1.2M")
        self.assertEqual(slug, "5312-medclair-kalkyl-v-a-1-2m")

    def test_resolve_unique_sheet_selection_sheet_only_unique(self) -> None:
        models = [
            build_model([build_row(2)], workbook_name="A.xlsx", sheet_name="10 profiler"),
            build_model([build_row(2)], workbook_name="B.xlsx", sheet_name="1.2M"),
        ]
        resolved = resolve_unique_sheet_selection(models, sheet="1.2M")
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].source.workbook_name, "B.xlsx")

    def test_resolve_unique_sheet_selection_sheet_only_ambiguous(self) -> None:
        models = [
            build_model([build_row(2)], workbook_name="A.xlsx", sheet_name="Common"),
            build_model([build_row(2)], workbook_name="B.xlsx", sheet_name="Common"),
        ]
        with self.assertRaisesRegex(ValueError, 'Sheet name "Common" matched multiple canonical sheets:'):
            resolve_unique_sheet_selection(models, sheet="Common")

    def test_choose_output_paths_single_sheet_uses_slugged_filename(self) -> None:
        model = build_model([build_row(2)], workbook_name="5312 Medclair Kalkyl (V.A).xlsx", sheet_name="1.2M")
        json_path, markdown_path = choose_output_paths([model])
        self.assertEqual(json_path, Path("data/optimizer/optimizer_results_5312-medclair-kalkyl-v-a-1-2m.json"))
        self.assertEqual(markdown_path, Path("data/optimizer/optimizer_results_5312-medclair-kalkyl-v-a-1-2m.md"))

    def test_choose_output_paths_multi_sheet_keeps_default(self) -> None:
        models = [
            build_model([build_row(2)], workbook_name="A.xlsx", sheet_name="S1"),
            build_model([build_row(2)], workbook_name="B.xlsx", sheet_name="S2"),
        ]
        json_path, markdown_path = choose_output_paths(models)
        self.assertEqual(json_path, Path("data/optimizer/optimizer_results.json"))
        self.assertEqual(markdown_path, Path("data/optimizer/optimizer_results.md"))

    def test_build_terminal_summary_includes_recommendation_and_baseline_fields(self) -> None:
        payload = {
            "campaign_count": 1,
            "results": [
                {
                    "source": {"workbook_name": "Book.xlsx", "sheet_name": "Sheet"},
                    "recommended_option_label": "balanced_option",
                    "options": [
                        {
                            "option_label": "balanced_option",
                            "optimized_diff": 207.375,
                            "improves_on_baseline": False,
                            "strategic_warnings": ["Highly concentrated tier mix"],
                        },
                        {"option_label": "current_workbook_mix", "optimized_diff": 207.375},
                    ],
                }
            ],
        }
        summary = build_terminal_summary(payload, Path("a.md"), Path("a.json"))
        self.assertIn("Processed 1 campaign", summary)
        self.assertIn("Markdown: a.md", summary)
        self.assertIn("JSON: a.json", summary)
        self.assertIn("Recommended: balanced_option", summary)
        self.assertIn("Recommended diff: 207.375", summary)
        self.assertIn("Baseline diff: 207.375", summary)
        self.assertIn("Improves baseline: no", summary)

    @mock.patch("optimizer.subprocess.run")
    def test_open_report_handles_failures_without_raising(self, mocked_run: mock.Mock) -> None:
        mocked_run.side_effect = RuntimeError("boom")
        warning = open_report(Path("data/optimizer/report.md"))
        self.assertIsNotNone(warning)
        self.assertIn("Warning: failed to open report", warning)

    def test_run_optimizer_single_sheet_writes_slugged_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            run_result = run_optimizer(
                input_path=Path("data/normalized/canonical_normalized_models.json"),
                json_output_path=output_dir / "optimizer_results.json",
                markdown_output_path=output_dir / "optimizer_results.md",
                sheet="1.2M",
                top_n=5,
                beam_width=300,
            )

            self.assertEqual(run_result["payload"]["campaign_count"], 1)
            self.assertIn("optimizer_results_5312-medclair-kalkyl-v-a-1-2m.json", str(run_result["json_output_path"]))
            self.assertIn("optimizer_results_5312-medclair-kalkyl-v-a-1-2m.md", str(run_result["markdown_output_path"]))
            self.assertTrue(run_result["json_output_path"].exists())
            self.assertTrue(run_result["markdown_output_path"].exists())


if __name__ == "__main__":
    unittest.main()
