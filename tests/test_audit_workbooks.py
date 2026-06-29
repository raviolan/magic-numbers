from pathlib import Path
import json
import tempfile
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from audit_workbooks import (
    build_audit_warnings,
    choose_input_dir,
    audit_sheet,
    inspect_profile_size_value,
    run_audit,
    write_json,
)
from xlsx_reader import load_workbook


class AuditWorkbookIntegrationTests(unittest.TestCase):
    def test_real_canonical_sheet_detection(self) -> None:
        workbook = load_workbook("data/reference_workbooks/raw/5311 Dear Dahlia Kalkyl (V.A).xlsx")
        target_sheet = next(sheet for sheet in workbook.sheets if sheet.name == "10 profiler")

        record = audit_sheet("data/reference_workbooks/raw/5311 Dear Dahlia Kalkyl (V.A).xlsx", 0, target_sheet)

        self.assertEqual(record.classification, "canonical_candidate")
        self.assertTrue(record.profile_section_detected)
        self.assertEqual(record.profile_row_count, 10)
        self.assertEqual(record.paid_relative_to_profiles, "after_profiles")
        self.assertFalse(record.paid_included_in_main_budget)
        self.assertEqual(record.diff_detected["value_cell"], "H21")
        self.assertAlmostEqual(record.diff_detected["value"], -46.2)
        self.assertEqual(record.supported_channels_found, ["Instagram", "TikTok"])
        self.assertEqual(record.normalized_profile_tiers_found, [35000, 75000])

    def test_run_audit_scans_current_reference_directory(self) -> None:
        records = run_audit(Path("data/reference_workbooks/raw"))

        self.assertEqual(len({record.workbook_name for record in records}), 22)
        self.assertEqual(len(records), 76)
        self.assertTrue(any(record.workbook_name.startswith("5311 Dear Dahlia") for record in records))

    def test_build_audit_warnings_reports_fallback_directory(self) -> None:
        warnings = build_audit_warnings(Path("data/reference_workbooks/raw"))

        self.assertEqual(len(warnings), 1)
        self.assertIn("Preferred input directory data/raw/kalkyler was not available", warnings[0])

    def test_write_json_marks_fallback_usage(self) -> None:
        records = run_audit(Path("data/reference_workbooks/raw"))

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "audit.json"
            warnings = build_audit_warnings(Path("data/reference_workbooks/raw"))
            write_json(output_path, Path("data/reference_workbooks/raw"), records, warnings)

            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["requested_input_directory"], "data/raw/kalkyler")
        self.assertEqual(payload["input_directory"], "data/reference_workbooks/raw")
        self.assertTrue(payload["used_fallback_input_directory"])
        self.assertEqual(payload["warnings"], warnings)

    def test_choose_input_dir_prefers_primary_path_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            primary = repo_root / "data" / "raw" / "kalkyler"
            fallback = repo_root / "data" / "reference_workbooks" / "raw"
            primary.mkdir(parents=True)
            fallback.mkdir(parents=True)
            current_dir = Path.cwd()
            try:
                import os

                os.chdir(repo_root)
                selected = choose_input_dir()
            finally:
                os.chdir(current_dir)

        self.assertEqual(selected, Path("data/raw/kalkyler"))

    def test_profile_size_normalization_preserves_valid_and_invalid_values(self) -> None:
        self.assertEqual(inspect_profile_size_value("15K")["normalized_tier"], 15000)
        self.assertEqual(inspect_profile_size_value("15 000")["normalized_tier"], 15000)
        self.assertEqual(inspect_profile_size_value(125)["normalized_tier"], 125000)
        self.assertIsNone(inspect_profile_size_value("50-80K")["normalized_tier"])
        self.assertEqual(inspect_profile_size_value("50-80K")["invalid_display"], "50-80K")
        self.assertIsNone(inspect_profile_size_value("Profile á 50-80K")["normalized_tier"])
        self.assertEqual(inspect_profile_size_value(120)["invalid_display"], "120000")

    def test_overview_sheets_are_classified_for_real_workbooks(self) -> None:
        records = run_audit(Path("data/reference_workbooks/raw"))
        lookup = {(record.workbook_name, record.sheet_name): record for record in records}

        self.assertEqual(lookup[("5254 Etoro Kalkyl (V.A).xlsx", "Summary")].classification, "overview_ignore")
        self.assertEqual(lookup[("NEW 5239 Gandalf Kalkyl (V.A).xlsx", "SUMMERING")].classification, "overview_ignore")


if __name__ == "__main__":
    unittest.main()
