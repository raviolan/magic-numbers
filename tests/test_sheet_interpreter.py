from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from audit_workbooks import load_audit_records, write_canonical_review
from interpreter_utils import normalize_supported_channel, split_market_channel
from sheet_interpreter import interpret_canonical_record, run_interpreter
from xlsx_reader import load_workbook


class SheetInterpreterTests(unittest.TestCase):
    def test_channel_normalization_and_market_splitting(self) -> None:
        self.assertEqual(normalize_supported_channel("UK TikTok"), "TikTok")
        self.assertEqual(normalize_supported_channel("Instagram"), "Instagram")
        self.assertEqual(normalize_supported_channel("YT"), "YouTube")
        self.assertIsNone(normalize_supported_channel("Meta"))
        self.assertEqual(split_market_channel("UK TikTok"), ("UK", "TikTok"))
        self.assertEqual(split_market_channel("Instagram"), (None, "Instagram"))
        self.assertEqual(split_market_channel("YT"), (None, "YouTube"))

    def test_canonical_sheet_interpretation_produces_required_fields(self) -> None:
        _, records = load_audit_records()
        record = next(
            item
            for item in records
            if item.workbook_name == "5312 Medclair Kalkyl (V.A).xlsx" and item.sheet_name == "600K"
        )
        workbook = load_workbook(record.workbook_path)
        sheet = workbook.sheets[record.sheet_index]

        model, skip_reason = interpret_canonical_record(record, sheet)

        self.assertIsNone(skip_reason)
        self.assertIsNotNone(model)
        assert model is not None
        self.assertEqual(model.source.classification, "canonical_candidate")
        self.assertEqual(model.budget, 600000)
        self.assertEqual(model.agency_fee, 286605)
        self.assertTrue(model.paid_media_included)
        self.assertEqual(model.profile_section.anchor_cell, "A19")
        self.assertGreater(len(model.profile_rows), 0)
        self.assertEqual(model.profile_rows[0].channel, "TikTok")
        self.assertIn(model.profile_rows[0].current_profile_size, {15000, 35000, 75000, 125000, 175000})
        self.assertEqual(model.profile_rows[0].workbook_raw_profile_size_value, 15)
        self.assertEqual(model.profile_rows[0].activations_cell, "C20")
        self.assertEqual(model.profile_rows[0].activations_value, 1)
        self.assertEqual(model.profile_rows[0].impressions_cell, "F20")
        self.assertEqual(model.profile_rows[0].impressions_value, 10)
        self.assertEqual(model.profile_rows[0].profile_fee_cell, "H20")
        self.assertEqual(model.profile_rows[0].profile_fee_value, 8000)
        self.assertEqual(model.profile_budget_target_multiplier, 0.925)
        self.assertEqual(model.profile_budget_target_cell, "H33")
        self.assertEqual(model.profile_budget_target_value, 206640.375)
        self.assertEqual(model.profile_fee_sum_cell, "H32")
        self.assertEqual(model.profile_fee_sum_value, 205000)
        self.assertEqual(model.diff.cell, "H34")
        self.assertEqual(model.diff.value, 1640.375)

    def test_run_interpreter_writes_combined_json_and_skips_noncanonical(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "canonical_normalized_models.json"
            summary = run_interpreter(Path("data/audit/calculator_audit.json"), output_path)
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(summary["canonical_records_considered"], 6)
        self.assertEqual(summary["normalized_models_written"], 6)
        self.assertEqual(len(payload["models"]), 6)
        self.assertTrue(
            any("5254 Etoro Kalkyl (V.A).xlsx / Summary: classification overview_ignore" in item for item in payload["skipped_records"])
        )
        self.assertTrue(
            any("NEW 5239 Gandalf Kalkyl (V.A).xlsx / SUMMERING: classification overview_ignore" in item for item in payload["skipped_records"])
        )

    def test_write_canonical_review_outputs_canonical_only_markdown(self) -> None:
        _, records = load_audit_records()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "canonical_audit_review.md"
            write_canonical_review(output_path, records)
            content = output_path.read_text(encoding="utf-8")

        self.assertIn("# Canonical Audit Review", content)
        self.assertIn("5311 Dear Dahlia Kalkyl (V.A).xlsx / 10 profiler", content)
        self.assertIn("5312 Medclair Kalkyl (V.A).xlsx / 600K", content)
        self.assertNotIn("5254 Etoro Kalkyl (V.A).xlsx / Summary", content)


if __name__ == "__main__":
    unittest.main()
