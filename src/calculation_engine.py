from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR
import json
from pathlib import Path
import sys
from typing import Any

from models import (
    CampaignValidationRecord,
    CanonicalCampaignModel,
    ValidationDiagnostics,
    RowCalculation,
    ValidationInputs,
    ValidationResult,
    ValidationSource,
    ValidationTotals,
)


INPUT_PATH = Path("data/normalized/canonical_normalized_models.json")
OUTPUT_DIR = Path("data/validation")
JSON_OUTPUT_PATH = OUTPUT_DIR / "calculation_validation.json"
MARKDOWN_OUTPUT_PATH = OUTPUT_DIR / "calculation_validation.md"
PASS_ABS_DELTA_MAX = Decimal("0.01")
CLOSE_ABS_DELTA_MAX = Decimal("1.0")
CHANNEL_MULTIPLIERS = {
    "Instagram": Decimal("0.7"),
    "TikTok": Decimal("0.8"),
    "YouTube": Decimal("0.5"),
}
ROW_FEE_FORMULA_PRIORITY = [
    "thousands_rounded_path",
    "captured_impressions_path",
    "raw_impressions_path",
]


def to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return Decimal(int(value))
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        return Decimal(stripped)
    raise TypeError(f"Unsupported numeric value: {value!r}")


def json_number(value: Decimal | int | float | None) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return value


def load_normalized_models(path: Path = INPUT_PATH) -> tuple[dict[str, Any], list[CanonicalCampaignModel]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    models = [CanonicalCampaignModel.from_json_dict(model) for model in payload.get("models", [])]
    return payload, models


def mround_nearest_5(value: Any) -> Decimal:
    decimal_value = to_decimal(value)
    if decimal_value is None:
        raise ValueError("MROUND requires a numeric value.")
    if decimal_value < 0:
        raise ValueError("Phase 2 MROUND only supports non-negative values.")
    if decimal_value == 0:
        return Decimal("0")

    quotient = decimal_value / Decimal("5")
    rounded_units = (quotient + Decimal("0.5")).to_integral_value(rounding=ROUND_FLOOR)
    return rounded_units * Decimal("5")


def get_channel_multiplier(channel: str | None) -> Decimal | None:
    if channel is None:
        return None
    return CHANNEL_MULTIPLIERS.get(channel)


def calculate_row_impressions(profile_size: Any, channel: str | None) -> Decimal | None:
    profile_size_decimal = to_decimal(profile_size)
    multiplier = get_channel_multiplier(channel)
    if profile_size_decimal is None or multiplier is None:
        return None
    return mround_nearest_5(profile_size_decimal * multiplier)


def calculate_row_cost(profile_size: Any, channel: str | None, cpm: Any, activations: Any = 1) -> Decimal | None:
    impressions = calculate_row_impressions(profile_size, channel)
    cpm_decimal = to_decimal(cpm)
    activations_decimal = to_decimal(activations)
    if impressions is None or cpm_decimal is None or activations_decimal is None:
        return None
    return impressions * cpm_decimal / Decimal("1000") * activations_decimal


def calculate_thousands_rounded_impressions(profile_size: Any, channel: str | None) -> Decimal | None:
    profile_size_decimal = to_decimal(profile_size)
    multiplier = get_channel_multiplier(channel)
    if profile_size_decimal is None or multiplier is None:
        return None
    return mround_nearest_5((profile_size_decimal / Decimal("1000")) * multiplier)


def calculate_thousands_rounded_row_fee(profile_size: Any, channel: str | None, cpm: Any, activations: Any = 1) -> Decimal | None:
    impressions = calculate_thousands_rounded_impressions(profile_size, channel)
    cpm_decimal = to_decimal(cpm)
    activations_decimal = to_decimal(activations)
    if impressions is None or cpm_decimal is None or activations_decimal is None:
        return None
    return impressions * cpm_decimal * activations_decimal


def calculate_captured_impressions_row_fee(workbook_impressions_value: Any, cpm: Any, activations: Any = 1) -> Decimal | None:
    impressions_decimal = to_decimal(workbook_impressions_value)
    cpm_decimal = to_decimal(cpm)
    activations_decimal = to_decimal(activations)
    if impressions_decimal is None or cpm_decimal is None or activations_decimal is None:
        return None
    return impressions_decimal * cpm_decimal * activations_decimal


def build_row_fee_path(impressions: Decimal | None, row_fee: Decimal | None, workbook_fee: Decimal | None) -> dict[str, Any]:
    delta = None
    if row_fee is not None and workbook_fee is not None:
        delta = row_fee - workbook_fee
    return {
        "impressions": json_number(impressions),
        "row_fee": json_number(row_fee),
        "delta_vs_workbook": json_number(delta),
    }


def build_row_fee_formula_candidates(row, activations_for_calc: Any, row_warnings: list[str]) -> dict[str, dict[str, Any]]:
    workbook_fee = to_decimal(row.profile_fee_value)
    raw_impressions = calculate_row_impressions(row.current_profile_size, row.channel)
    raw_row_fee = calculate_row_cost(row.current_profile_size, row.channel, row.cpm, activations_for_calc)
    thousands_impressions = calculate_thousands_rounded_impressions(row.current_profile_size, row.channel)
    thousands_row_fee = calculate_thousands_rounded_row_fee(row.current_profile_size, row.channel, row.cpm, activations_for_calc)
    captured_impressions_fee = calculate_captured_impressions_row_fee(row.impressions_value, row.cpm, activations_for_calc)
    if row.impressions_value is None:
        row_warnings.append("Captured workbook impressions missing; captured-impressions path is incomplete for this row.")
    elif raw_impressions is not None and to_decimal(row.impressions_value) != calculate_thousands_rounded_impressions(row.current_profile_size, row.channel):
        row_warnings.append("Workbook impressions evidence differs from deterministic impressions formula.")
    if row.workbook_raw_profile_size_value is not None and row.workbook_raw_profile_size_value == row.current_profile_size:
        pass
    elif row.workbook_raw_profile_size_value is not None:
        row_warnings.append("Workbook raw profile size appears to be stored in thousands-scale units.")
    return {
        "raw_impressions_path": build_row_fee_path(raw_impressions, raw_row_fee, workbook_fee),
        "thousands_rounded_path": build_row_fee_path(thousands_impressions, thousands_row_fee, workbook_fee),
        "captured_impressions_path": build_row_fee_path(to_decimal(row.impressions_value), captured_impressions_fee, workbook_fee),
    }


def choose_selected_row_fee_formula(models: list[CanonicalCampaignModel]) -> str:
    stats = {
        formula_name: {
            "total_abs_delta": Decimal("0"),
            "row_count": 0,
            "complete_count": 0,
        }
        for formula_name in ROW_FEE_FORMULA_PRIORITY
    }
    for model in models:
        for row in model.profile_rows:
            workbook_fee = to_decimal(row.profile_fee_value)
            if workbook_fee is None:
                continue
            activations_for_calc = row.activations if row.activations is not None else 1
            candidates = build_row_fee_formula_candidates(row, activations_for_calc, [])
            for formula_name, payload in candidates.items():
                delta = payload.get("delta_vs_workbook")
                row_fee = payload.get("row_fee")
                if row_fee is not None:
                    stats[formula_name]["complete_count"] += 1
                if delta is not None:
                    stats[formula_name]["row_count"] += 1
                    stats[formula_name]["total_abs_delta"] += abs(to_decimal(delta))

    def sort_key(formula_name: str) -> tuple[Decimal, int, int, int]:
        stat = stats[formula_name]
        return (
            stat["total_abs_delta"],
            -stat["row_count"],
            -stat["complete_count"],
            ROW_FEE_FORMULA_PRIORITY.index(formula_name),
        )

    return min(ROW_FEE_FORMULA_PRIORITY, key=sort_key)


def classify_validation_status(
    delta: Decimal | int | float | None,
    pass_threshold: Decimal = PASS_ABS_DELTA_MAX,
    close_threshold: Decimal = CLOSE_ABS_DELTA_MAX,
) -> str:
    if delta is None:
        return "mismatch"
    absolute_delta = abs(to_decimal(delta))
    if absolute_delta <= pass_threshold:
        return "pass"
    if absolute_delta <= close_threshold:
        return "close"
    return "mismatch"


def calculate_campaign(model: CanonicalCampaignModel, selected_formula_name: str = "thousands_rounded_path") -> CampaignValidationRecord:
    warnings = list(model.warnings)
    row_calculations: list[RowCalculation] = []
    calculated_profile_cost = Decimal("0")
    raw_impressions_profile_fee_sum = Decimal("0")
    thousands_rounded_profile_fee_sum = Decimal("0")
    captured_impressions_profile_fee_sum = Decimal("0")
    selected_deterministic_row_fee_sum = Decimal("0")
    captured_workbook_profile_fee_sum = Decimal("0")
    missing_profile_fee_evidence = False
    missing_activation_evidence = False
    unsupported_row_found = False
    missing_captured_impressions_evidence = False

    for row in model.profile_rows:
        row_warnings = list(row.warnings)
        multiplier = get_channel_multiplier(row.channel)
        if multiplier is None:
            unsupported_row_found = True
            row_warnings.append(f"Unsupported channel {row.channel!r} encountered in normalized model.")
        if row.current_profile_size is None:
            row_warnings.append("Profile size is missing in normalized model.")
        if row.cpm is None:
            row_warnings.append("CPM is missing in normalized model.")
        if row.activations is None:
            row_warnings.append("Activations value is missing in normalized model; defaulted to 1.")
            missing_activation_evidence = True

        activations_for_calc = row.activations if row.activations is not None else 1
        formula_candidates = build_row_fee_formula_candidates(row, activations_for_calc, row_warnings)
        raw_impressions_path = formula_candidates["raw_impressions_path"]
        thousands_rounded_path = formula_candidates["thousands_rounded_path"]
        captured_impressions_path = formula_candidates["captured_impressions_path"]

        if raw_impressions_path["row_fee"] is not None:
            raw_impressions_profile_fee_sum += to_decimal(raw_impressions_path["row_fee"])
            calculated_profile_cost += to_decimal(raw_impressions_path["row_fee"])
        if thousands_rounded_path["row_fee"] is not None:
            thousands_rounded_profile_fee_sum += to_decimal(thousands_rounded_path["row_fee"])
        if captured_impressions_path["row_fee"] is not None:
            captured_impressions_profile_fee_sum += to_decimal(captured_impressions_path["row_fee"])
        else:
            missing_captured_impressions_evidence = True

        selected_path = formula_candidates[selected_formula_name]
        selected_row_fee_value = selected_path["row_fee"]
        if selected_row_fee_value is not None:
            selected_deterministic_row_fee_sum += to_decimal(selected_row_fee_value)
        if row.profile_fee_value is None:
            missing_profile_fee_evidence = True
            row_warnings.append("Captured workbook profile fee evidence is missing for this row.")
        else:
            captured_workbook_profile_fee_sum += to_decimal(row.profile_fee_value)

        row_calculations.append(
            RowCalculation(
                row_index=row.row_index,
                profile_size=row.current_profile_size,
                profile_size_cell=row.profile_size_cell,
                workbook_raw_profile_size_value=row.workbook_raw_profile_size_value,
                channel=row.channel,
                market=row.market,
                multiplier=json_number(multiplier),
                impressions=raw_impressions_path["impressions"],
                captured_workbook_impressions=row.impressions_value,
                impressions_cell=row.impressions_cell,
                cpm=row.cpm,
                cpm_cell=row.cpm_cell,
                activations=activations_for_calc,
                activations_cell=row.activations_cell,
                calculated_row_cost=raw_impressions_path["row_fee"],
                captured_workbook_row_fee=row.profile_fee_value,
                profile_fee_cell=row.profile_fee_cell,
                raw_impressions_path=raw_impressions_path,
                thousands_rounded_path=thousands_rounded_path,
                captured_impressions_path=captured_impressions_path,
                selected_row_fee_formula=selected_formula_name,
                selected_row_fee_value=selected_row_fee_value,
                selected_row_fee_delta_vs_workbook=selected_path["delta_vs_workbook"],
                warnings=row_warnings,
            )
        )

    budget = to_decimal(model.budget)
    agency_fee = to_decimal(model.agency_fee)
    paid_media = to_decimal(model.paid_media)
    included_paid_media_cost = Decimal("0")
    if model.paid_media_included is True and paid_media is not None:
        included_paid_media_cost = paid_media
    elif model.paid_media_included is True and paid_media is None:
        warnings.append("Paid media is marked included but the numeric paid_media value is missing.")

    if budget is None:
        warnings.append("Budget is missing from normalized model.")
    if agency_fee is None:
        warnings.append("Agency fee is missing from normalized model.")

    calculated_total_cost = None
    calculated_diff = None
    if budget is not None and agency_fee is not None:
        calculated_total_cost = calculated_profile_cost + agency_fee + included_paid_media_cost
        calculated_diff = budget - calculated_total_cost

    profile_budget_target_multiplier = to_decimal(model.profile_budget_target_multiplier)
    if profile_budget_target_multiplier is None:
        profile_budget_target_multiplier = Decimal("0.925")
        warnings.append("Profile budget target multiplier was missing; defaulted to 0.925.")

    profile_budget_target = None
    if budget is not None and agency_fee is not None:
        profile_budget_target = profile_budget_target_multiplier * (budget - agency_fee - included_paid_media_cost)

    workbook_style_calculated_diff = None
    if profile_budget_target is not None and not missing_profile_fee_evidence:
        workbook_style_calculated_diff = profile_budget_target - captured_workbook_profile_fee_sum

    workbook_diff_value = to_decimal(model.diff.value) if model.diff else None
    diff_delta_vs_workbook = None
    if calculated_diff is not None and workbook_diff_value is not None:
        diff_delta_vs_workbook = calculated_diff - workbook_diff_value
    elif model.diff and model.diff.cell and workbook_diff_value is None:
        warnings.append(f"Workbook diff cell {model.diff.cell} exists but workbook diff value is missing.")
    else:
        warnings.append("Workbook diff value is missing from normalized model.")

    if unsupported_row_found:
        warnings.append("Unsupported channel rows were present in the normalized model.")
    if any(row.warnings for row in row_calculations):
        warnings.append("One or more profile rows had unresolved inputs during calculation.")
    if missing_captured_impressions_evidence:
        warnings.append("Captured workbook impressions missing on one or more profile rows; captured-impressions diagnostics are incomplete.")
    if missing_activation_evidence:
        warnings.append("Activation evidence missing on one or more profile rows; defaulted to 1 for deterministic calculation.")
    if missing_profile_fee_evidence:
        warnings.append("Profile fee evidence missing on one or more profile rows; workbook-style validation may be incomplete.")

    captured_workbook_profile_fee_sum_value = to_decimal(model.profile_fee_sum_value)
    if captured_workbook_profile_fee_sum_value is not None:
        captured_workbook_profile_fee_sum = captured_workbook_profile_fee_sum_value
        missing_profile_fee_evidence = False

    row_fee_sum_delta = None
    if not missing_profile_fee_evidence:
        row_fee_sum_delta = selected_deterministic_row_fee_sum - captured_workbook_profile_fee_sum
        if row_fee_sum_delta != 0:
            warnings.append("Selected deterministic row-fee formula still does not match captured workbook row fee on one or more rows.")

    workbook_style_diff_delta_vs_workbook = None
    if workbook_style_calculated_diff is not None and workbook_diff_value is not None:
        workbook_style_diff_delta_vs_workbook = workbook_style_calculated_diff - workbook_diff_value
        if workbook_style_diff_delta_vs_workbook != 0:
            warnings.append("Workbook-style diff does not match workbook diff under current captured evidence.")

    status = classify_validation_status(workbook_style_diff_delta_vs_workbook)
    validation_warnings: list[str] = []
    if status != "pass":
        validation_warnings.append("Workbook-style diff does not match workbook diff under current captured evidence.")
    if status == "mismatch":
        validation_warnings.append(
            "Possible missing inputs: row fee sum mismatch, target budget mismatch, paid inclusion mismatch, missing activation evidence, or missing profile fee evidence."
        )
    validation_warnings.extend(warnings)

    return CampaignValidationRecord(
        source=ValidationSource(
            workbook_name=model.source.workbook_name,
            sheet_name=model.source.sheet_name,
            workbook_diff_cell=model.diff.cell if model.diff else None,
            workbook_diff_value=json_number(workbook_diff_value),
        ),
        inputs=ValidationInputs(
            budget=model.budget,
            agency_fee=model.agency_fee,
            paid_media=model.paid_media,
            paid_media_included=model.paid_media_included,
            profile_budget_target_multiplier=json_number(profile_budget_target_multiplier),
        ),
        diagnostics=ValidationDiagnostics(
            selected_row_fee_formula=selected_formula_name,
            legacy_campaign_total_cost=json_number(calculated_total_cost),
            legacy_campaign_total_diff=json_number(calculated_diff),
            cpm_derived_profile_fee_sum=json_number(calculated_profile_cost),
            raw_impressions_profile_fee_sum=json_number(raw_impressions_profile_fee_sum),
            thousands_rounded_profile_fee_sum=json_number(thousands_rounded_profile_fee_sum),
            captured_impressions_profile_fee_sum=None if missing_captured_impressions_evidence else json_number(captured_impressions_profile_fee_sum),
            selected_deterministic_row_fee_sum=json_number(selected_deterministic_row_fee_sum),
            captured_workbook_profile_fee_sum=None if missing_profile_fee_evidence else json_number(captured_workbook_profile_fee_sum),
            profile_budget_target=json_number(profile_budget_target),
            profile_budget_target_cell=model.profile_budget_target_cell,
            profile_fee_sum_cell=model.profile_fee_sum_cell,
            workbook_style_calculated_diff=json_number(workbook_style_calculated_diff),
        ),
        row_calculations=row_calculations,
        totals=ValidationTotals(
            calculated_profile_cost=json_number(calculated_profile_cost),
            included_paid_media_cost=json_number(included_paid_media_cost),
            agency_fee=model.agency_fee,
            calculated_total_cost=json_number(calculated_total_cost),
            calculated_diff=json_number(calculated_diff),
        ),
        validation=ValidationResult(
            diff_delta_vs_workbook=json_number(diff_delta_vs_workbook),
            abs_diff_delta_vs_workbook=json_number(abs(diff_delta_vs_workbook)) if diff_delta_vs_workbook is not None else None,
            row_fee_sum_delta=json_number(row_fee_sum_delta),
            workbook_style_diff_delta_vs_workbook=json_number(workbook_style_diff_delta_vs_workbook),
            validation_status=status,
            warnings=validation_warnings,
        ),
    )


def build_validation_payload(input_path: Path, models: list[CanonicalCampaignModel]) -> dict[str, Any]:
    selected_formula_name = choose_selected_row_fee_formula(models)
    records = [calculate_campaign(model, selected_formula_name) for model in models]
    status_counts = {"pass": 0, "close": 0, "mismatch": 0}
    for record in records:
        status_counts[record.validation.validation_status] += 1
    return {
        "input_file": str(input_path),
        "campaign_count": len(records),
        "selected_row_fee_formula": selected_formula_name,
        "validation_thresholds": {
            "pass_abs_delta_max": json_number(PASS_ABS_DELTA_MAX),
            "close_abs_delta_max": json_number(CLOSE_ABS_DELTA_MAX),
        },
        "status_counts": status_counts,
        "records": [record.to_json_dict() for record in records],
    }


def write_validation_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def format_money(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def write_validation_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Calculation Validation",
        "",
        f"- Input file: `{payload['input_file']}`",
        f"- Campaign count: {payload['campaign_count']}",
        f"- Selected row-fee formula: `{payload['selected_row_fee_formula']}`",
        f"- Status counts: pass={payload['status_counts']['pass']}, close={payload['status_counts']['close']}, mismatch={payload['status_counts']['mismatch']}",
        "",
    ]
    for record in payload["records"]:
        warnings = record["validation"]["warnings"]
        lines.extend(
            [
                f"## {record['source']['workbook_name']} / {record['source']['sheet_name']}",
                "",
                f"- Workbook diff cell: {record['source']['workbook_diff_cell'] or 'null'}",
                f"- Workbook diff value: {format_money(record['source']['workbook_diff_value'])}",
                f"- Selected row-fee formula: {record['diagnostics']['selected_row_fee_formula']}",
                f"- Legacy campaign-total cost: {format_money(record['diagnostics']['legacy_campaign_total_cost'])}",
                f"- Legacy campaign-total diff: {format_money(record['diagnostics']['legacy_campaign_total_diff'])}",
                f"- CPM-derived profile fee sum: {format_money(record['diagnostics']['cpm_derived_profile_fee_sum'])}",
                f"- Raw-impressions profile fee sum: {format_money(record['diagnostics']['raw_impressions_profile_fee_sum'])}",
                f"- Thousands-rounded profile fee sum: {format_money(record['diagnostics']['thousands_rounded_profile_fee_sum'])}",
                f"- Captured-impressions profile fee sum: {format_money(record['diagnostics']['captured_impressions_profile_fee_sum'])}",
                f"- Selected deterministic row-fee sum: {format_money(record['diagnostics']['selected_deterministic_row_fee_sum'])}",
                f"- Captured workbook profile fee sum: {format_money(record['diagnostics']['captured_workbook_profile_fee_sum'])}",
                f"- Profile budget target: {format_money(record['diagnostics']['profile_budget_target'])}",
                f"- Workbook-style calculated diff: {format_money(record['diagnostics']['workbook_style_calculated_diff'])}",
                f"- Calculated profile cost: {format_money(record['totals']['calculated_profile_cost'])}",
                f"- Included paid media: {format_money(record['totals']['included_paid_media_cost'])}",
                f"- Agency fee: {format_money(record['totals']['agency_fee'])}",
                f"- Calculated total cost: {format_money(record['totals']['calculated_total_cost'])}",
                f"- Calculated diff: {format_money(record['totals']['calculated_diff'])}",
                f"- Diff delta vs workbook: {format_money(record['validation']['diff_delta_vs_workbook'])}",
                f"- Workbook-style diff delta vs workbook: {format_money(record['validation']['workbook_style_diff_delta_vs_workbook'])}",
                f"- Row-fee sum delta: {format_money(record['validation']['row_fee_sum_delta'])}",
                f"- Validation status: {record['validation']['validation_status']}",
                f"- Warnings: {'; '.join(warnings) if warnings else 'none'}",
                "",
                "| Row | Size Cell | Profile Size | Workbook Raw Size | Channel | Market | Multiplier | Workbook Impr. | Raw Path Fee | Raw Delta | Thousands Path Fee | Thousands Delta | Captured Impr. Fee | Captured Delta | Captured Row Fee | Selected Formula | Selected Delta | Warnings |",
                "|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|",
            ]
        )
        for row in record["row_calculations"]:
            raw_path = row.get("raw_impressions_path") or {}
            thousands_path = row.get("thousands_rounded_path") or {}
            captured_path = row.get("captured_impressions_path") or {}
            lines.append(
                "| {row_index} | {profile_size_cell} | {profile_size} | {workbook_raw_profile_size_value} | {channel} | {market} | {multiplier} | {captured_workbook_impressions} | {raw_fee} | {raw_delta} | {thousands_fee} | {thousands_delta} | {captured_fee} | {captured_delta} | {captured_workbook_row_fee} | {selected_formula} | {selected_delta} | {warnings} |".format(
                    row_index=row["row_index"],
                    profile_size_cell=row.get("profile_size_cell") or "null",
                    profile_size=format_money(row.get("profile_size")),
                    workbook_raw_profile_size_value=format_money(row.get("workbook_raw_profile_size_value")),
                    channel=row.get("channel") or "null",
                    market=row.get("market") or "null",
                    multiplier=format_money(row.get("multiplier")),
                    captured_workbook_impressions=format_money(row.get("captured_workbook_impressions")),
                    raw_fee=format_money(raw_path.get("row_fee")),
                    raw_delta=format_money(raw_path.get("delta_vs_workbook")),
                    thousands_fee=format_money(thousands_path.get("row_fee")),
                    thousands_delta=format_money(thousands_path.get("delta_vs_workbook")),
                    captured_fee=format_money(captured_path.get("row_fee")),
                    captured_delta=format_money(captured_path.get("delta_vs_workbook")),
                    captured_workbook_row_fee=format_money(row.get("captured_workbook_row_fee")),
                    selected_formula=row.get("selected_row_fee_formula") or "null",
                    selected_delta=format_money(row.get("selected_row_fee_delta_vs_workbook")),
                    warnings="; ".join(row.get("warnings", [])) if row.get("warnings") else "none",
                )
            )
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def run_validation(
    input_path: Path = INPUT_PATH,
    json_output_path: Path = JSON_OUTPUT_PATH,
    markdown_output_path: Path = MARKDOWN_OUTPUT_PATH,
) -> dict[str, Any]:
    _, models = load_normalized_models(input_path)
    payload = build_validation_payload(input_path, models)
    write_validation_json(json_output_path, payload)
    write_validation_markdown(markdown_output_path, payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    input_path = INPUT_PATH
    json_output_path = JSON_OUTPUT_PATH
    markdown_output_path = MARKDOWN_OUTPUT_PATH
    index = 0
    while index < len(args):
        if args[index] == "--input" and index + 1 < len(args):
            input_path = Path(args[index + 1])
            index += 2
            continue
        if args[index] == "--json-output" and index + 1 < len(args):
            json_output_path = Path(args[index + 1])
            index += 2
            continue
        if args[index] == "--markdown-output" and index + 1 < len(args):
            markdown_output_path = Path(args[index + 1])
            index += 2
            continue
        raise SystemExit(f"Unsupported argument: {args[index]}")

    payload = run_validation(input_path, json_output_path, markdown_output_path)
    print(f"Validated campaigns: {payload['campaign_count']}")
    print(f"Status counts: {payload['status_counts']}")
    print(json_output_path)
    print(markdown_output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
