from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cpm_library import (
    CURRENCY_UNKNOWN,
    FULL_LIBRARY_VISIBLE_COLUMNS,
    SUPPORTED_CURRENCIES,
    add_manual_reference_cpm,
    approve_calculation,
    build_full_library_display_rows,
    build_cpm_observations_from_approved_option,
    load_cpm_observations,
    normalize_currency,
    get_currency_channel_medians,
    seed_reference_cpm_observations,
    summarize_cpm_library_by_currency_and_channel,
    update_observation_currency,
    update_observation_from_display_row,
    validate_currency,
)


def build_result(fill_instructions: list[dict], recommended: str = "best_strategic_fit") -> dict:
    return {
        "recommended_option_label": recommended,
        "options": [
            {
                "option_label": "best_strategic_fit",
                "optimized_diff": 1000,
                "profile_fee_sum": 250000,
                "profile_budget_target": 251000,
                "tier_counts": {"15000": 1, "35000": 2, "75000": 0, "125000": 0, "175000": 0},
                "total_impressions": 100,
                "impressions_by_channel": {"TikTok": 100},
                "impressions_by_market": {"SE": 100},
                "fill_instructions": fill_instructions,
            },
            {
                "option_label": "best_mathematical_fit",
                "optimized_diff": 500,
                "profile_fee_sum": 250500,
                "profile_budget_target": 251000,
                "tier_counts": {"15000": 0, "35000": 3, "75000": 0, "125000": 0, "175000": 0},
                "total_impressions": 120,
                "impressions_by_channel": {"Instagram": 120},
                "impressions_by_market": {"SE": 120},
                "fill_instructions": [{"channel": "Instagram", "market": "SE", "cpm": 570, "row_fee": 1000}],
            },
        ],
    }


class CpmLibraryTests(unittest.TestCase):
    def test_currency_normalization(self) -> None:
        self.assertEqual(normalize_currency(" SEK "), "SEK")
        self.assertEqual(normalize_currency("eur"), "EUR")
        self.assertEqual(normalize_currency(""), CURRENCY_UNKNOWN)
        self.assertEqual(normalize_currency(None), CURRENCY_UNKNOWN)

    def test_currency_validation_rejects_unknown_when_strict(self) -> None:
        self.assertEqual(validate_currency("sek", allow_unknown=False), "SEK")
        with self.assertRaisesRegex(ValueError, "Unsupported currency"):
            validate_currency("usd", allow_unknown=False)

    def test_approval_requires_calculation_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            approved_path = Path(tmp_dir) / "approved.json"
            cpm_path = Path(tmp_dir) / "cpm.json"
            with self.assertRaisesRegex(ValueError, "Calculation name is required"):
                approve_calculation(
                    result=build_result([]),
                    calculation_name="  ",
                    source={"mode": "manual_campaign_builder", "workbook_name": None, "sheet_name": "Manual"},
                    budget_inputs={"budget": 100000},
                    currency="SEK",
                    approved_calculations_path=approved_path,
                    cpm_observations_path=cpm_path,
                )

    def test_approved_manual_calc_stores_selected_currency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            approved_path = Path(tmp_dir) / "approved.json"
            cpm_path = Path(tmp_dir) / "cpm.json"
            result = approve_calculation(
                result=build_result([{"channel": "TikTok", "market": "SE", "cpm": 425, "row_fee": 2000}]),
                calculation_name="Manual campaign A",
                comment="",
                source={"mode": "manual_campaign_builder", "workbook_name": None, "sheet_name": "Manual campaign A"},
                budget_inputs={"budget": 100000, "agency_fee": 10000},
                currency="EUR",
                approved_calculations_path=approved_path,
                cpm_observations_path=cpm_path,
                created_at="2026-04-27T10:00:00+00:00",
            )
            approved_records = json.loads(approved_path.read_text(encoding="utf-8"))
            observations = json.loads(cpm_path.read_text(encoding="utf-8"))

            self.assertEqual(len(approved_records), 1)
            self.assertEqual(approved_records[0]["currency"], "EUR")
            self.assertEqual(result["added_cpm_observation_count"], 1)
            self.assertEqual(observations[0]["source_type"], "approved_manual")
            self.assertEqual(observations[0]["currency"], "EUR")

    def test_approved_canonical_calc_stores_selected_currency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            approved_path = Path(tmp_dir) / "approved.json"
            cpm_path = Path(tmp_dir) / "cpm.json"
            approve_calculation(
                result=build_result([{"channel": "YouTube", "market": "UK", "cpm": 1000, "row_fee": 3000}]),
                calculation_name="Book A / 10 profiler",
                comment="canonical",
                source={"mode": "canonical_sheet", "workbook_name": "Book A.xlsx", "sheet_name": "10 profiler"},
                budget_inputs={"budget": 500000, "agency_fee": 50000},
                currency="SEK",
                approved_calculations_path=approved_path,
                cpm_observations_path=cpm_path,
                created_at="2026-04-27T10:00:00+00:00",
            )
            observations = load_cpm_observations(cpm_path)
            self.assertEqual(len(observations), 1)
            self.assertEqual(observations[0]["source_type"], "approved_canonical")
            self.assertEqual(observations[0]["workbook_name"], "Book A.xlsx")
            self.assertEqual(observations[0]["sheet_name"], "10 profiler")
            self.assertEqual(observations[0]["currency"], "SEK")

    def test_cpm_extraction_uses_only_fill_instructions_and_groups_duplicates(self) -> None:
        observations = build_cpm_observations_from_approved_option(
            calculation_id="calc-1",
            calculation_name="Campaign",
            source_type="approved_manual",
            workbook_name=None,
            sheet_name="Campaign",
            currency="SEK",
            comment=None,
            approved_option={
                "fill_instructions": [
                    {"channel": "TikTok", "market": "SE", "cpm": 425},
                    {"channel": "TikTok", "market": "SE", "cpm": 425},
                    {"channel": "TikTok", "market": "US", "cpm": 800},
                    {"channel": "Instagram", "market": None, "cpm": 570},
                    {"channel": "TikTok", "market": "SE", "cpm": 450},
                ]
            },
            created_at="2026-04-27T10:00:00+00:00",
        )

        self.assertEqual(len(observations), 4)
        grouped = {(obs["channel"], obs["market"], obs["cpm"], obs["currency"]): obs["used_row_count"] for obs in observations}
        self.assertEqual(grouped[("TikTok", "SE", 425, "SEK")], 2)
        self.assertEqual(grouped[("TikTok", "US", 800, "SEK")], 1)
        self.assertEqual(grouped[("TikTok", "SE", 450, "SEK")], 1)
        self.assertEqual(grouped[("Instagram", None, 570, "SEK")], 1)
        self.assertNotIn(("YouTube", None, 1000, "SEK"), grouped)

    def test_reference_seeding_uses_currency_mapping_and_handles_unmapped(self) -> None:
        models = [
            {
                "source": {"workbook_name": "5311 Dear Dahlia Kalkyl (V.A).xlsx", "sheet_name": "10 profiler"},
                "profile_rows": [{"channel": "TikTok", "market": "SE", "cpm": 425}],
            },
            {
                "source": {"workbook_name": "5312 Medclair Kalkyl (V.A).xlsx", "sheet_name": "1.2M"},
                "profile_rows": [{"channel": "Instagram", "market": "SE", "cpm": 570}],
            },
            {
                "source": {"workbook_name": "Unmapped.xlsx", "sheet_name": "A"},
                "profile_rows": [{"channel": "YouTube", "market": "US", "cpm": 1000}],
            },
        ]

        seeded, added = seed_reference_cpm_observations(models, [], created_at="2026-04-27T10:00:00+00:00")
        self.assertEqual(added, 3)

        by_workbook = {record["workbook_name"]: record for record in seeded}
        self.assertEqual(by_workbook["5311 Dear Dahlia Kalkyl (V.A).xlsx"]["currency"], "EUR")
        self.assertEqual(by_workbook["5312 Medclair Kalkyl (V.A).xlsx"]["currency"], "SEK")
        self.assertEqual(by_workbook["Unmapped.xlsx"]["currency"], CURRENCY_UNKNOWN)

    def test_reference_seeding_is_idempotent_and_migrates_legacy_missing_currency(self) -> None:
        models = [
            {
                "source": {"workbook_name": "5312 Medclair Kalkyl (V.A).xlsx", "sheet_name": "1.2M"},
                "profile_rows": [{"channel": "TikTok", "market": "SE", "cpm": 425}],
            }
        ]
        legacy_existing = [
            {
                "id": "legacy-1",
                "created_at": "2026-04-27T10:00:00+00:00",
                "source_type": "reference_canonical",
                "calculation_id": None,
                "calculation_name": "5312 Medclair Kalkyl (V.A).xlsx / 1.2M",
                "workbook_name": "5312 Medclair Kalkyl (V.A).xlsx",
                "sheet_name": "1.2M",
                "channel": "TikTok",
                "market": "SE",
                "cpm": 425,
                "used_row_count": 1,
                "comment": None,
            }
        ]

        seeded_once, added_once = seed_reference_cpm_observations(models, legacy_existing, created_at="2026-04-27T10:00:00+00:00")
        seeded_twice, added_twice = seed_reference_cpm_observations(models, seeded_once, created_at="2026-04-27T10:05:00+00:00")

        self.assertEqual(added_once, 0)
        self.assertEqual(added_twice, 0)
        self.assertEqual(len(seeded_once), 1)
        self.assertEqual(seeded_once[0]["currency"], "SEK")
        self.assertEqual(len(seeded_twice), 1)

    def test_summary_by_currency_is_separate_and_unknown_is_excluded(self) -> None:
        summary = summarize_cpm_library_by_currency_and_channel(
            [
                {"channel": "TikTok", "currency": "SEK", "cpm": 425},
                {"channel": "TikTok", "currency": "SEK", "cpm": 525},
                {"channel": "TikTok", "currency": "EUR", "cpm": 35},
                {"channel": "Instagram", "currency": "EUR", "cpm": 46},
                {"channel": "Instagram", "currency": "unknown", "cpm": 580},
                {"channel": "Instagram", "currency": None, "cpm": 600},
            ]
        )

        self.assertEqual(set(summary["by_currency"].keys()), set(SUPPORTED_CURRENCIES))
        sek_rows = {row["channel"]: row for row in summary["by_currency"]["SEK"]}
        eur_rows = {row["channel"]: row for row in summary["by_currency"]["EUR"]}
        self.assertEqual(sek_rows["TikTok"]["average_cpm"], 475.0)
        self.assertEqual(sek_rows["TikTok"]["median_cpm"], 475.0)
        self.assertEqual(eur_rows["TikTok"]["average_cpm"], 35.0)
        self.assertEqual(eur_rows["Instagram"]["average_cpm"], 46.0)
        self.assertEqual(summary["unknown_currency_observation_count"], 2)

    def test_get_currency_channel_medians_ignores_unknown_and_splits_sek_eur(self) -> None:
        medians = get_currency_channel_medians(
            [
                {"channel": "Instagram", "currency": "SEK", "cpm": 570},
                {"channel": "Instagram", "currency": "SEK", "cpm": 590},
                {"channel": "Instagram", "currency": "EUR", "cpm": 46},
                {"channel": "Instagram", "currency": CURRENCY_UNKNOWN, "cpm": 900},
                {"channel": "TikTok", "currency": "SEK", "cpm": 450},
            ]
        )
        self.assertEqual(medians["SEK"]["Instagram"], 580.0)
        self.assertEqual(medians["SEK"]["TikTok"], 450.0)
        self.assertEqual(medians["EUR"]["Instagram"], 46.0)
        self.assertNotIn(CURRENCY_UNKNOWN, medians)

    def test_update_observation_currency_preserves_other_fields(self) -> None:
        original = [
            {
                "id": "obs-1",
                "source_type": "manual_reference",
                "currency": CURRENCY_UNKNOWN,
                "cpm": 500,
                "comment": "note",
            }
        ]
        updated = update_observation_currency(original, "obs-1", "eur")
        self.assertEqual(updated[0]["currency"], "EUR")
        self.assertEqual(updated[0]["cpm"], 500)
        self.assertEqual(updated[0]["comment"], "note")

    def test_update_observation_from_display_row_edits_visible_fields(self) -> None:
        original = [
            {
                "id": "obs-1",
                "source_type": "manual_reference",
                "calculation_name": "Old ref",
                "workbook_name": "Old ref",
                "sheet_name": None,
                "channel": "TikTok",
                "currency": "SEK",
                "cpm": 500,
                "comment": "old",
                "used_row_count": 2,
            }
        ]

        updated = update_observation_from_display_row(
            original,
            "obs-1",
            {
                "Workbook": "New ref",
                "Sheet": "Benchmarks",
                "Channel": "Instagram",
                "Currency": "eur",
                "CPM": "625.5",
                "Comment": "updated",
            },
        )

        self.assertEqual(updated[0]["workbook_name"], "New ref")
        self.assertEqual(updated[0]["calculation_name"], "New ref")
        self.assertEqual(updated[0]["sheet_name"], "Benchmarks")
        self.assertEqual(updated[0]["channel"], "Instagram")
        self.assertEqual(updated[0]["currency"], "EUR")
        self.assertEqual(updated[0]["cpm"], 625.5)
        self.assertEqual(updated[0]["comment"], "updated")
        self.assertEqual(updated[0]["used_row_count"], 2)

    def test_update_observation_from_display_row_rejects_invalid_values(self) -> None:
        original = [{"id": "obs-1", "channel": "TikTok", "currency": "SEK", "cpm": 500}]
        with self.assertRaisesRegex(ValueError, "Channel must be one of"):
            update_observation_from_display_row(original, "obs-1", {"Channel": "LinkedIn", "Currency": "SEK", "CPM": 500})
        with self.assertRaisesRegex(ValueError, "CPM must be numeric and greater than 0"):
            update_observation_from_display_row(original, "obs-1", {"Channel": "TikTok", "Currency": "SEK", "CPM": 0})

    def test_update_observation_from_display_row_preserves_hidden_sheet_when_absent(self) -> None:
        original = [
            {
                "id": "obs-1",
                "workbook_name": "Book.xlsx",
                "sheet_name": "Hidden sheet",
                "channel": "TikTok",
                "currency": "SEK",
                "cpm": 500,
                "comment": "old",
            }
        ]

        updated = update_observation_from_display_row(
            original,
            "obs-1",
            {"Workbook": "Book.xlsx", "Channel": "Instagram", "Currency": "EUR", "CPM": 625},
        )

        self.assertEqual(updated[0]["sheet_name"], "Hidden sheet")
        self.assertEqual(updated[0]["channel"], "Instagram")
        self.assertEqual(updated[0]["currency"], "EUR")

    def test_manual_reference_row_valid_and_invalid_cases(self) -> None:
        observations: list[dict] = []
        created = add_manual_reference_cpm(
            observations=observations,
            reference_name="Ref 1",
            channel="TikTok",
            market="SE",
            currency="SEK",
            cpm=425,
            comment="manual",
            created_at="2026-04-27T10:00:00+00:00",
        )
        self.assertEqual(len(observations), 1)
        self.assertEqual(created["source_type"], "manual_reference")
        self.assertEqual(created["used_row_count"], 1)
        self.assertEqual(created["currency"], "SEK")
        self.assertEqual(created["workbook_name"], "Ref 1")

        with self.assertRaisesRegex(ValueError, "Reference/project name is required"):
            add_manual_reference_cpm(
                observations=observations,
                reference_name="",
                channel="TikTok",
                currency="SEK",
                cpm=425,
            )
        with self.assertRaisesRegex(ValueError, "CPM must be numeric and greater than 0"):
            add_manual_reference_cpm(
                observations=observations,
                reference_name="Ref 2",
                channel="TikTok",
                currency="SEK",
                cpm=0,
            )
        self.assertIn("id", observations[0])
        self.assertIn("source_type", observations[0])
        self.assertIn("used_row_count", observations[0])
        self.assertIn("created_at", observations[0])

    def test_full_library_display_rows_hide_metadata_columns(self) -> None:
        observations = [
            {
                "id": "obs-1",
                "created_at": "2026-04-27T10:00:00+00:00",
                "source_type": "approved_manual",
                "calculation_id": "calc-1",
                "calculation_name": "Campaign A",
                "workbook_name": None,
                "sheet_name": "Manual",
                "channel": "TikTok",
                "market": "SE",
                "currency": "SEK",
                "cpm": 425,
                "used_row_count": 3,
                "comment": "ok",
            }
        ]
        rows = build_full_library_display_rows(observations)
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0].keys()), set(FULL_LIBRARY_VISIBLE_COLUMNS))
        self.assertNotIn("id", rows[0])
        self.assertNotIn("calculation_name", rows[0])
        self.assertNotIn("source_type", rows[0])
        self.assertNotIn("market", rows[0])
        self.assertNotIn("used_row_count", rows[0])
        self.assertNotIn("created_at", rows[0])

    def test_invalid_json_load_is_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "cpm.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Invalid JSON in CPM observations file"):
                load_cpm_observations(path)


if __name__ == "__main__":
    unittest.main()
