from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from calculation_engine import (
    calculate_campaign,
    calculate_captured_impressions_row_fee,
    calculate_row_cost,
    calculate_row_impressions,
    calculate_thousands_rounded_impressions,
    calculate_thousands_rounded_row_fee,
    choose_selected_row_fee_formula,
    classify_validation_status,
    load_normalized_models,
    mround_nearest_5,
    run_validation,
)
from models import (
    CanonicalCampaignModel,
    CanonicalDiff,
    CanonicalProfileRow,
    CanonicalProfileSection,
    CanonicalSource,
)
from sheet_interpreter import run_interpreter


class CalculationEngineTests(unittest.TestCase):
    def test_mround_nearest_5_examples(self) -> None:
        self.assertEqual(mround_nearest_5(28001), 28000)
        self.assertEqual(mround_nearest_5(28002), 28000)
        self.assertEqual(mround_nearest_5(28003), 28005)
        self.assertEqual(mround_nearest_5(28002.5), 28005)
        self.assertEqual(mround_nearest_5(24500), 24500)

    def test_impression_calculations_for_supported_channels(self) -> None:
        self.assertEqual(calculate_row_impressions(15000, "TikTok"), 12000)
        self.assertEqual(calculate_row_impressions(35000, "Instagram"), 24500)
        self.assertEqual(calculate_row_impressions(35000, "TikTok"), 28000)
        self.assertEqual(calculate_row_impressions(35000, "YouTube"), 17500)

    def test_row_cost_uses_cpm_and_activations(self) -> None:
        self.assertEqual(calculate_row_cost(35000, "TikTok", 35, 1), 980)
        self.assertEqual(calculate_row_cost(35000, "TikTok", 35, 2), 1960)
        self.assertEqual(calculate_thousands_rounded_row_fee(35000, "TikTok", 35, 1), 1050)
        self.assertEqual(calculate_captured_impressions_row_fee(30, 35, 2), 2100)

    def test_thousands_rounded_and_captured_impressions_paths(self) -> None:
        self.assertEqual(calculate_thousands_rounded_impressions(35000, "TikTok"), 30)
        self.assertEqual(calculate_thousands_rounded_row_fee(35000, "TikTok", 800, 1), 24000)
        self.assertEqual(calculate_captured_impressions_row_fee(30, 800, 1), 24000)

    def test_paid_media_inclusion_and_exclusion(self) -> None:
        excluded_model = CanonicalCampaignModel(
            source=CanonicalSource("Book", "path.xlsx", "Sheet", 0, "canonical_candidate"),
            budget=10000,
            agency_fee=1000,
            paid_media=500,
            paid_media_included=False,
            profile_budget_target_multiplier=0.925,
            profile_budget_target_cell="H3",
            profile_budget_target_value=8325,
            profile_fee_sum_cell="H4",
            profile_fee_sum_value=980,
            profile_section=CanonicalProfileSection("A1", "A1 (row 1)", 1),
            profile_rows=[
                CanonicalProfileRow(
                    row_index=2,
                    profile_size_cell="B2",
                    current_profile_size=35000,
                    workbook_raw_profile_size_value=35,
                    market=None,
                    channel="TikTok",
                    raw_channel_label="TikTok",
                    cpm=35,
                    cpm_cell="G2",
                    activations=1,
                    activations_cell="C2",
                    activations_value=1,
                    impressions_cell="F2",
                    impressions_value=28,
                    profile_fee_cell="H2",
                    profile_fee_value=980,
                )
            ],
            diff=CanonicalDiff(cell="H5", value=7345),
        )
        included_model = CanonicalCampaignModel(
            source=CanonicalSource("Book", "path.xlsx", "Sheet", 0, "canonical_candidate"),
            budget=10000,
            agency_fee=1000,
            paid_media=500,
            paid_media_included=True,
            profile_budget_target_multiplier=0.925,
            profile_budget_target_cell="H3",
            profile_budget_target_value=7862.5,
            profile_fee_sum_cell="H4",
            profile_fee_sum_value=980,
            profile_section=CanonicalProfileSection("A1", "A1 (row 1)", 1),
            profile_rows=[
                CanonicalProfileRow(
                    row_index=2,
                    profile_size_cell="B2",
                    current_profile_size=35000,
                    workbook_raw_profile_size_value=35,
                    market=None,
                    channel="TikTok",
                    raw_channel_label="TikTok",
                    cpm=35,
                    cpm_cell="G2",
                    activations=1,
                    activations_cell="C2",
                    activations_value=1,
                    impressions_cell="F2",
                    impressions_value=28,
                    profile_fee_cell="H2",
                    profile_fee_value=980,
                )
            ],
            diff=CanonicalDiff(cell="H5", value=6882.5),
        )

        excluded_result = calculate_campaign(excluded_model)
        included_result = calculate_campaign(included_model)

        self.assertEqual(excluded_result.totals.included_paid_media_cost, 0)
        self.assertEqual(included_result.totals.included_paid_media_cost, 500)

    def test_campaign_total_and_diff_for_synthetic_model(self) -> None:
        model = CanonicalCampaignModel(
            source=CanonicalSource("Book", "path.xlsx", "Sheet", 0, "canonical_candidate"),
            budget=10000,
            agency_fee=1000,
            paid_media=500,
            paid_media_included=False,
            profile_budget_target_multiplier=0.925,
            profile_budget_target_cell="H3",
            profile_budget_target_value=8325,
            profile_fee_sum_cell="H4",
            profile_fee_sum_value=980,
            profile_section=CanonicalProfileSection("A1", "A1 (row 1)", 1),
            profile_rows=[
                CanonicalProfileRow(
                    row_index=2,
                    profile_size_cell="B2",
                    current_profile_size=35000,
                    workbook_raw_profile_size_value=35,
                    market=None,
                    channel="TikTok",
                    raw_channel_label="TikTok",
                    cpm=35,
                    cpm_cell="G2",
                    activations=1,
                    activations_cell="C2",
                    activations_value=1,
                    impressions_cell="F2",
                    impressions_value=28,
                    profile_fee_cell="H2",
                    profile_fee_value=980,
                )
            ],
            diff=CanonicalDiff(cell="H5", value=7345),
        )

        result = calculate_campaign(model)

        self.assertEqual(result.totals.calculated_profile_cost, 980)
        self.assertEqual(result.totals.calculated_total_cost, 1980)
        self.assertEqual(result.totals.calculated_diff, 8020)
        self.assertEqual(result.diagnostics.selected_row_fee_formula, "thousands_rounded_path")
        self.assertEqual(result.diagnostics.selected_deterministic_row_fee_sum, 1050)
        self.assertEqual(result.diagnostics.profile_budget_target, 8325)
        self.assertEqual(result.diagnostics.captured_workbook_profile_fee_sum, 980)
        self.assertEqual(result.diagnostics.workbook_style_calculated_diff, 7345)
        self.assertEqual(result.validation.row_fee_sum_delta, 70)
        self.assertEqual(result.validation.workbook_style_diff_delta_vs_workbook, 0)
        self.assertEqual(result.validation.validation_status, "pass")

    def test_profile_budget_target_formula_with_and_without_paid_media(self) -> None:
        excluded_model = CanonicalCampaignModel(
            source=CanonicalSource("Book", "path.xlsx", "Sheet", 0, "canonical_candidate"),
            budget=10000,
            agency_fee=1000,
            paid_media=500,
            paid_media_included=False,
            profile_budget_target_multiplier=0.925,
            profile_fee_sum_value=980,
            profile_rows=[],
            diff=CanonicalDiff(cell="H5", value=7345),
        )
        included_model = CanonicalCampaignModel(
            source=CanonicalSource("Book", "path.xlsx", "Sheet", 0, "canonical_candidate"),
            budget=10000,
            agency_fee=1000,
            paid_media=500,
            paid_media_included=True,
            profile_budget_target_multiplier=0.925,
            profile_fee_sum_value=980,
            profile_rows=[],
            diff=CanonicalDiff(cell="H5", value=6882.5),
        )

        excluded_result = calculate_campaign(excluded_model)
        included_result = calculate_campaign(included_model)

        self.assertEqual(excluded_result.diagnostics.profile_budget_target, 8325)
        self.assertEqual(included_result.diagnostics.profile_budget_target, 7862.5)

    def test_missing_activation_and_profile_fee_evidence_warns(self) -> None:
        model = CanonicalCampaignModel(
            source=CanonicalSource("Book", "path.xlsx", "Sheet", 0, "canonical_candidate"),
            budget=10000,
            agency_fee=1000,
            paid_media=0,
            paid_media_included=False,
            profile_budget_target_multiplier=0.925,
            profile_rows=[
                CanonicalProfileRow(
                    row_index=2,
                    profile_size_cell="B2",
                    current_profile_size=35000,
                    workbook_raw_profile_size_value=35,
                    market=None,
                    channel="TikTok",
                    raw_channel_label="TikTok",
                    cpm=35,
                    cpm_cell="G2",
                    activations=None,
                )
            ],
            diff=CanonicalDiff(cell="H5", value=0),
        )

        result = calculate_campaign(model)

        self.assertIn(
            "Activation evidence missing on one or more profile rows; defaulted to 1 for deterministic calculation.",
            result.validation.warnings,
        )
        self.assertIn(
            "Profile fee evidence missing on one or more profile rows; workbook-style validation may be incomplete.",
            result.validation.warnings,
        )

    def test_selected_formula_is_returned_and_used(self) -> None:
        model = CanonicalCampaignModel(
            source=CanonicalSource("Book", "path.xlsx", "Sheet", 0, "canonical_candidate"),
            budget=10000,
            agency_fee=1000,
            paid_media=0,
            paid_media_included=False,
            profile_budget_target_multiplier=0.925,
            profile_fee_sum_value=24000,
            profile_rows=[
                CanonicalProfileRow(
                    row_index=2,
                    profile_size_cell="B2",
                    current_profile_size=35000,
                    workbook_raw_profile_size_value=35,
                    market=None,
                    channel="TikTok",
                    raw_channel_label="TikTok",
                    cpm=800,
                    cpm_cell="G2",
                    cpm_value=800,
                    activations=1,
                    activations_cell="C2",
                    activations_value=1,
                    impressions_cell="F2",
                    impressions_value=30,
                    profile_fee_cell="H2",
                    profile_fee_value=24000,
                )
            ],
            diff=CanonicalDiff(cell="H5", value=-15675),
        )

        selected_formula = choose_selected_row_fee_formula([model])
        result = calculate_campaign(model, selected_formula)

        self.assertEqual(selected_formula, "thousands_rounded_path")
        self.assertEqual(result.row_calculations[0].selected_row_fee_formula, "thousands_rounded_path")
        self.assertEqual(result.row_calculations[0].selected_row_fee_value, 24000)
        self.assertEqual(result.validation.row_fee_sum_delta, 0)

    def test_validation_status_thresholds(self) -> None:
        self.assertEqual(classify_validation_status(0), "pass")
        self.assertEqual(classify_validation_status(0.5), "close")
        self.assertEqual(classify_validation_status(5), "mismatch")

    def test_run_validation_writes_outputs_for_real_models(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            normalized_output = Path(temp_dir) / "canonical_normalized_models.json"
            json_output = Path(temp_dir) / "calculation_validation.json"
            markdown_output = Path(temp_dir) / "calculation_validation.md"
            run_interpreter(Path("data/audit/calculator_audit.json"), normalized_output)
            payload = run_validation(
                normalized_output,
                json_output,
                markdown_output,
            )
            json_payload = json.loads(json_output.read_text(encoding="utf-8"))
            markdown = markdown_output.read_text(encoding="utf-8")

        self.assertEqual(payload["campaign_count"], 6)
        self.assertEqual(len(json_payload["records"]), 6)
        self.assertEqual(payload["selected_row_fee_formula"], "thousands_rounded_path")
        self.assertIn("# Calculation Validation", markdown)
        self.assertIn("5311 Dear Dahlia Kalkyl (V.A).xlsx / 10 profiler", markdown)
        self.assertIn("5312 Medclair Kalkyl (V.A).xlsx / 600K", markdown)
        self.assertIn("Selected row-fee formula", markdown)
        self.assertIn("thousands_rounded_path", markdown)
        self.assertIn("Workbook-style calculated diff", markdown)
        self.assertNotIn("optimizer", markdown.lower())

    def test_real_model_paid_media_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            normalized_output = Path(temp_dir) / "canonical_normalized_models.json"
            run_interpreter(Path("data/audit/calculator_audit.json"), normalized_output)
            _, models = load_normalized_models(normalized_output)
        records = [calculate_campaign(model) for model in models]
        dear_dahlia = [record for record in records if "Dear Dahlia" in record.source.workbook_name]
        medclair = [record for record in records if "Medclair" in record.source.workbook_name]

        self.assertTrue(all(record.inputs.paid_media_included is False for record in dear_dahlia))
        self.assertTrue(all(record.totals.included_paid_media_cost == 0 for record in dear_dahlia))
        self.assertTrue(all(record.inputs.paid_media_included is True for record in medclair))
        self.assertTrue(all(record.totals.included_paid_media_cost > 0 for record in medclair))
        self.assertTrue(all(record.validation.validation_status in {"pass", "close"} for record in dear_dahlia + medclair))

    def test_real_models_include_row_fee_formula_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            normalized_output = Path(temp_dir) / "canonical_normalized_models.json"
            run_interpreter(Path("data/audit/calculator_audit.json"), normalized_output)
            payload = run_validation(
                normalized_output,
                Path(temp_dir) / "calculation_validation.json",
                Path(temp_dir) / "calculation_validation.md",
            )

        self.assertEqual(payload["selected_row_fee_formula"], "thousands_rounded_path")
        self.assertTrue(all(record["validation"]["validation_status"] == "pass" for record in payload["records"]))
        self.assertTrue(all("selected_row_fee_formula" in record["diagnostics"] for record in payload["records"]))
        self.assertTrue(all("raw_impressions_path" in record["row_calculations"][0] for record in payload["records"]))


if __name__ == "__main__":
    unittest.main()
