from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any

from audit_workbooks import AUDIT_JSON_PATH, load_audit_records
from interpreter_utils import (
    detect_profile_section,
    find_first_label,
    find_nearest_numeric_value,
    normalize_supported_channel,
    normalize_unsupported_channel,
    split_market_channel,
)
from models import (
    AuditRecord,
    CanonicalCampaignModel,
    CanonicalDiff,
    CanonicalProfileRow,
    CanonicalProfileSection,
    CanonicalSource,
)
from xlsx_reader import load_workbook


OUTPUT_PATH = Path("data/normalized/canonical_normalized_models.json")
CELL_REF_RE = re.compile(r"\b[A-Z]+[0-9]+\b")
MULTIPLIER_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)")


def resolve_sheet(record: AuditRecord, workbook_cache: dict[str, Any]):
    workbook_path = Path(record.workbook_path)
    cache_key = str(workbook_path)
    workbook = workbook_cache.get(cache_key)
    if workbook is None:
        workbook = load_workbook(workbook_path)
        workbook_cache[cache_key] = workbook

    if 0 <= record.sheet_index < len(workbook.sheets):
        candidate = workbook.sheets[record.sheet_index]
        if candidate.name == record.sheet_name:
            return candidate

    for sheet in workbook.sheets:
        if sheet.name == record.sheet_name:
            return sheet
    return None


def resolve_detected_numeric(
    sheet,
    detected_payload: dict[str, Any] | None,
    label_candidates: list[str],
    field_name: str,
    warnings: list[str],
) -> Any:
    label_cell = None
    if detected_payload and detected_payload.get("label_cell"):
        label_cell = sheet.cells.get(detected_payload["label_cell"])
    if label_cell is None:
        label_cell = find_first_label(sheet, label_candidates)

    if label_cell is None:
        return None

    value_cell = None
    if detected_payload and detected_payload.get("value_cell"):
        value_cell = sheet.cells.get(detected_payload["value_cell"])
    if value_cell is None:
        value_cell = find_nearest_numeric_value(sheet, label_cell)

    if value_cell is None or not isinstance(value_cell.value, (int, float)):
        warnings.append(f"{field_name.capitalize()} label found at {label_cell.ref} but numeric value was not resolved.")
        return None
    return value_cell.value


def resolve_paid_media(sheet, record: AuditRecord, warnings: list[str]) -> Any:
    if not record.paid_section_detected:
        return None
    if record.paid_section is None or not record.paid_section.get("label_cell"):
        warnings.append("Paid section detected but paid media anchor cell was not preserved in the audit record.")
        return None

    label_cell = sheet.cells.get(record.paid_section["label_cell"])
    if label_cell is None:
        warnings.append(
            f"Paid section anchor {record.paid_section['label_cell']} could not be resolved in the workbook sheet."
        )
        return None

    value_cell = find_nearest_numeric_value(sheet, label_cell)
    if value_cell is None or not isinstance(value_cell.value, (int, float)):
        warnings.append(f"Paid section found at {label_cell.ref} but paid media numeric value was not resolved.")
        return None
    return value_cell.value


def extract_cell_references(formula: str | None) -> list[str]:
    if not formula:
        return []
    return CELL_REF_RE.findall(formula.upper())


def detect_profile_budget_target_evidence(sheet, diff_cell_ref: str | None, warnings: list[str]) -> dict[str, Any]:
    evidence = {
        "profile_budget_target_multiplier": None,
        "profile_budget_target_cell": None,
        "profile_budget_target_value": None,
        "profile_fee_sum_cell": None,
        "profile_fee_sum_value": None,
    }
    if not diff_cell_ref:
        warnings.append("Diff cell reference is missing; profile budget target evidence could not be inspected.")
        return evidence

    diff_cell = sheet.cells.get(diff_cell_ref)
    if diff_cell is None or not diff_cell.formula:
        warnings.append(f"Diff cell {diff_cell_ref} formula was not available for target-path inspection.")
        return evidence

    diff_refs = extract_cell_references(diff_cell.formula)
    if len(diff_refs) >= 2:
        target_ref, fee_sum_ref = diff_refs[0], diff_refs[1]
        target_cell = sheet.cells.get(target_ref)
        fee_sum_cell = sheet.cells.get(fee_sum_ref)
        evidence["profile_budget_target_cell"] = target_ref
        evidence["profile_budget_target_value"] = target_cell.value if target_cell else None
        evidence["profile_fee_sum_cell"] = fee_sum_ref
        evidence["profile_fee_sum_value"] = fee_sum_cell.value if fee_sum_cell else None

        if target_cell and target_cell.formula:
            multiplier_match = re.search(r"\*\s*([0-9]+(?:\.[0-9]+)?)", target_cell.formula)
            if multiplier_match:
                evidence["profile_budget_target_multiplier"] = float(multiplier_match.group(1))
            else:
                warnings.append(
                    f"Profile budget target cell {target_ref} formula was present but multiplier could not be identified."
                )
        else:
            warnings.append(f"Profile budget target cell {target_ref} formula was not available.")
    else:
        warnings.append(f"Diff cell {diff_cell_ref} formula did not expose both target and fee-sum references.")
    return evidence


def interpret_profile_rows(profile_rows: list[dict[str, object]], model_warnings: list[str]) -> list[CanonicalProfileRow]:
    normalized_rows: list[CanonicalProfileRow] = []
    for row in profile_rows:
        row_warnings: list[str] = []
        raw_channel_label = row.get("channel")
        unsupported_channel = normalize_unsupported_channel(raw_channel_label)
        if unsupported_channel:
            model_warnings.append(
                f"Skipped row {row['row']}: unsupported channel {unsupported_channel} from label {raw_channel_label!r}."
            )
            continue

        market, channel = split_market_channel(raw_channel_label)
        if channel is None:
            channel = normalize_supported_channel(raw_channel_label)
        if channel is None:
            model_warnings.append(
                f"Skipped row {row['row']}: supported channel could not be resolved from label {raw_channel_label!r}."
            )
            continue

        current_profile_size = row.get("normalized_tier")
        if current_profile_size not in {15000, 35000, 75000, 125000, 175000}:
            model_warnings.append(
                f"Skipped row {row['row']}: invalid profile size {row.get('size_display')!r} at {row.get('size_cell')}."
            )
            continue

        activations = row.get("activation")
        if not isinstance(activations, (int, float)):
            activations = 1

        normalized_rows.append(
            CanonicalProfileRow(
                row_index=int(row["row"]),
                profile_size_cell=row.get("size_cell"),
                current_profile_size=int(current_profile_size),
                workbook_raw_profile_size_value=row.get("size_raw"),
                market=market,
                channel=channel,
                raw_channel_label=raw_channel_label if isinstance(raw_channel_label, str) else None,
                cpm=row.get("cpm"),
                cpm_cell=row.get("cpm_cell"),
                cpm_value=row.get("cpm"),
                activations=activations,
                activations_cell=row.get("activation_cell"),
                activations_value=row.get("activation"),
                impressions_cell=row.get("impressions_cell"),
                impressions_value=row.get("impressions"),
                profile_fee_cell=row.get("profile_fee_cell"),
                profile_fee_value=row.get("profile_fee"),
                locked=False,
                warnings=row_warnings,
            )
        )
    return normalized_rows


def interpret_canonical_record(record: AuditRecord, sheet) -> tuple[CanonicalCampaignModel | None, str | None]:
    warnings = list(record.warnings)

    budget = resolve_detected_numeric(
        sheet,
        record.detected_budget,
        ["kampanjbudget", "new campaign total", "campaign total", "target"],
        "budget",
        warnings,
    )
    agency_fee = resolve_detected_numeric(
        sheet,
        record.detected_agency_fee,
        ["nine agency hantering", "smarton/nine agency hantering", "nine hantering", "nine-arvode"],
        "agency fee",
        warnings,
    )
    paid_media = resolve_paid_media(sheet, record, warnings) if record.paid_section_detected else None

    profile_header, _, profile_rows = detect_profile_section(sheet)
    normalized_rows = interpret_profile_rows(profile_rows, warnings)
    if not normalized_rows:
        return None, "no usable canonical profile rows remained after validation"

    diff_cell = None
    diff_value = None
    if record.diff_detected:
        diff_cell = record.diff_detected.get("value_cell") or record.diff_detected.get("label_cell")
        diff_value = record.diff_detected.get("value")
        if diff_cell and diff_value is None:
            warnings.append(f"Diff cell found at {diff_cell} but numeric value was not resolved.")
    target_evidence = detect_profile_budget_target_evidence(sheet, diff_cell, warnings)

    for normalized_row in normalized_rows:
        if normalized_row.activations_cell is None:
            normalized_row.warnings.append("Activation cell could not be identified from workbook evidence.")
        if normalized_row.impressions_cell is None or normalized_row.impressions_value is None:
            normalized_row.warnings.append("Workbook impressions evidence could not be identified for this row.")
        if normalized_row.profile_fee_cell is None or normalized_row.profile_fee_value is None:
            normalized_row.warnings.append("Workbook profile fee evidence could not be identified for this row.")

    profile_section = CanonicalProfileSection(
        anchor_cell=profile_header.ref if profile_header else None,
        location=f"{profile_header.ref} (row {profile_header.row})" if profile_header else None,
        row_count=len(normalized_rows),
    )
    model = CanonicalCampaignModel(
        source=CanonicalSource(
            workbook_name=record.workbook_name,
            workbook_path=record.workbook_path,
            sheet_name=record.sheet_name,
            sheet_index=record.sheet_index,
            classification=record.classification,
        ),
        budget=budget,
        agency_fee=agency_fee,
        paid_media=paid_media,
        paid_media_included=record.paid_included_in_main_budget if record.paid_section_detected else None,
        profile_budget_target_multiplier=target_evidence["profile_budget_target_multiplier"],
        profile_budget_target_cell=target_evidence["profile_budget_target_cell"],
        profile_budget_target_value=target_evidence["profile_budget_target_value"],
        profile_fee_sum_cell=target_evidence["profile_fee_sum_cell"],
        profile_fee_sum_value=target_evidence["profile_fee_sum_value"],
        profile_section=profile_section,
        profile_rows=normalized_rows,
        diff=CanonicalDiff(cell=diff_cell, value=diff_value),
        warnings=warnings,
    )
    return model, None


def write_normalized_models(
    output_path: Path,
    audit_payload: dict[str, Any],
    models: list[CanonicalCampaignModel],
    skipped_records: list[str],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_audit_json": str(AUDIT_JSON_PATH),
        "input_directory": audit_payload.get("input_directory"),
        "canonical_records_considered": len([r for r in audit_payload.get("records", []) if r.get("classification") == "canonical_candidate"]),
        "normalized_models_written": len(models),
        "skipped_records": skipped_records,
        "models": [model.to_json_dict() for model in models],
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def run_interpreter(audit_json_path: Path = AUDIT_JSON_PATH, output_path: Path = OUTPUT_PATH) -> dict[str, Any]:
    audit_payload, audit_records = load_audit_records(audit_json_path)
    workbook_cache: dict[str, Any] = {}
    normalized_models: list[CanonicalCampaignModel] = []
    skipped_records: list[str] = []
    warning_count = 0

    for record in audit_records:
        record_label = f"{record.workbook_name} / {record.sheet_name}"
        if record.classification != "canonical_candidate":
            skipped_records.append(f"Skipped {record_label}: classification {record.classification}")
            continue

        sheet = resolve_sheet(record, workbook_cache)
        if sheet is None:
            skipped_records.append(f"Skipped {record_label}: sheet could not be located in workbook")
            continue

        model, skip_reason = interpret_canonical_record(record, sheet)
        if model is None:
            skipped_records.append(f"Skipped {record_label}: {skip_reason}")
            continue

        if model.warnings:
            warning_count += 1
        normalized_models.append(model)

    write_normalized_models(output_path, audit_payload, normalized_models, skipped_records)
    return {
        "canonical_records_considered": len([r for r in audit_records if r.classification == "canonical_candidate"]),
        "normalized_models_written": len(normalized_models),
        "skipped_records": skipped_records,
        "records_with_warnings": warning_count,
        "output_path": str(output_path),
    }


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    audit_json_path = AUDIT_JSON_PATH
    output_path = OUTPUT_PATH
    index = 0
    while index < len(args):
        if args[index] == "--audit-json" and index + 1 < len(args):
            audit_json_path = Path(args[index + 1])
            index += 2
            continue
        if args[index] == "--output" and index + 1 < len(args):
            output_path = Path(args[index + 1])
            index += 2
            continue
        raise SystemExit(f"Unsupported argument: {args[index]}")

    summary = run_interpreter(audit_json_path, output_path)
    print(f"Canonical records considered: {summary['canonical_records_considered']}")
    print(f"Normalized models written: {summary['normalized_models_written']}")
    print(f"Skipped records: {len(summary['skipped_records'])}")
    print(f"Records with warnings: {summary['records_with_warnings']}")
    for message in summary["skipped_records"]:
        print(message)
    print(summary["output_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
