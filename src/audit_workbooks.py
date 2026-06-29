from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
from typing import Any

from interpreter_utils import (
    VALID_PROFILE_TIERS,
    detect_channels,
    detect_diff,
    detect_formula_cache_warnings,
    detect_overview,
    detect_paid_section,
    detect_profile_section,
    find_first_label,
    find_nearest_numeric_value,
    inspect_profile_size_value,
    normalize_text,
)
from models import AuditRecord, CellValue, SheetData
from xlsx_reader import load_workbook


TEMPLATE_KEYWORDS = ("kalkylmall", "template")
INPUT_CANDIDATES = [
    Path("data/raw/kalkyler"),
    Path("data/reference_workbooks/raw"),
]
OUTPUT_DIR = Path("data/audit")
PRIMARY_INPUT_DIR = INPUT_CANDIDATES[0]
AUDIT_JSON_PATH = OUTPUT_DIR / "calculator_audit.json"
AUDIT_CSV_PATH = OUTPUT_DIR / "calculator_audit.csv"
CANONICAL_REVIEW_PATH = OUTPUT_DIR / "canonical_audit_review.md"


def build_detected_value(label_cell: CellValue | None, value_cell: CellValue | None) -> dict[str, Any] | None:
    if label_cell is None and value_cell is None:
        return None
    return {
        "label_cell": label_cell.ref if label_cell else None,
        "label_value": label_cell.value if label_cell else None,
        "value_cell": value_cell.ref if value_cell else None,
        "value": value_cell.value if value_cell else None,
    }


def build_profile_section_payload(
    header_cell: CellValue | None,
    columns: dict[str, int],
    profile_rows: list[dict[str, object]],
) -> tuple[dict[str, Any] | None, str | None]:
    if header_cell is None:
        return None, None
    payload = {
        "header_cell": header_cell.ref,
        "header_row": header_cell.row,
        "columns": columns,
        "row_count": len(profile_rows),
    }
    return payload, f"{header_cell.ref} (row {header_cell.row})"


def build_paid_section_payload(paid_cell: CellValue | None) -> tuple[dict[str, Any] | None, str | None]:
    if paid_cell is None:
        return None, None
    payload = {
        "label_cell": paid_cell.ref,
        "label_value": paid_cell.value,
        "row": paid_cell.row,
    }
    return payload, paid_cell.ref


def classify_sheet(
    workbook_name: str,
    sheet: SheetData,
    is_overview_sheet: bool,
    overview_reasons: list[str],
    profile_header: CellValue | None,
    normalized_profile_tiers_found: list[int],
    invalid_or_legacy_profile_values: list[str],
    supported_channels: list[str],
    unsupported_channels: list[str],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    sheet_name = normalize_text(sheet.name)
    workbook_key = normalize_text(workbook_name)

    if is_overview_sheet:
        return "overview_ignore", overview_reasons.copy()

    if any(keyword in sheet_name for keyword in TEMPLATE_KEYWORDS):
        reasons.append("Template-like sheet name.")
        return "legacy_reference_only", reasons

    if sheet.state != "visible":
        reasons.append("Hidden sheet.")
        return "legacy_reference_only", reasons

    if profile_header is None:
        reasons.append("No standard profile section detected.")
        return "unsupported_structure", reasons

    if unsupported_channels:
        reasons.append("Unsupported profile channels present in profile section.")
        return "legacy_reference_only", reasons

    if "medclair" in workbook_key or "dear dahlia" in workbook_key:
        reasons.append("Modern workbook selected as a reliable canonical Phase 0 reference.")
        return "canonical_candidate", reasons

    if normalized_profile_tiers_found:
        reasons.append("At least one valid v1 profile tier was detected.")
    if invalid_or_legacy_profile_values:
        reasons.append("Legacy or invalid profile size values were detected.")

    if supported_channels:
        return "usable_with_standardization", reasons

    reasons.append("No supported channels detected in profile section.")
    return "unsupported_structure", reasons


def audit_sheet(workbook_path: Path | str, sheet_index: int, sheet: SheetData) -> AuditRecord:
    workbook_path = Path(workbook_path)
    workbook_name = workbook_path.name
    profile_header, profile_columns, profile_rows = detect_profile_section(sheet)
    supported_channels, unsupported_channels = detect_channels(profile_rows)
    paid_detected, paid_relative_to_profiles, paid_included, paid_cell = detect_paid_section(sheet, profile_header)
    is_overview_sheet, overview_reasons = detect_overview(sheet)

    budget_label = find_first_label(sheet, ["kampanjbudget", "new campaign total", "campaign total", "target"])
    budget_value_cell = find_nearest_numeric_value(sheet, budget_label) if budget_label else None
    fee_label = find_first_label(
        sheet,
        [
            "nine agency hantering",
            "smarton/nine agency hantering",
            "nine hantering",
            "nine-arvode",
        ],
    )
    fee_value_cell = find_nearest_numeric_value(sheet, fee_label) if fee_label else None
    diff_label_cell, diff_value_cell = detect_diff(sheet)
    formula_cache_warnings = detect_formula_cache_warnings(sheet)

    profile_section, profile_section_location = build_profile_section_payload(profile_header, profile_columns, profile_rows)
    paid_section, paid_section_location = build_paid_section_payload(paid_cell)

    likely_profile_size_cells = [str(row["size_cell"]) for row in profile_rows if row.get("size_cell")]
    current_profile_size_values = [
        f"{row['size_cell']}={row['size_display']}"
        for row in profile_rows
        if row.get("size_cell") and row.get("size_display")
    ]
    normalized_profile_tiers_found = sorted(
        {
            int(row["normalized_tier"])
            for row in profile_rows
            if isinstance(row.get("normalized_tier"), int)
        }
    )
    invalid_or_legacy_profile_values = sorted(
        {
            f"{row['size_cell']}={row['size_display']}"
            for row in profile_rows
            if row.get("size_cell") and row.get("invalid_profile_value")
        }
    )

    cpm_values_detected = []
    for row in profile_rows:
        channel = row.get("channel")
        cpm = row.get("cpm")
        cell_ref = row.get("cpm_cell")
        if channel and isinstance(cpm, (int, float)) and cell_ref:
            cpm_values_detected.append(f"{channel}@{cell_ref}={cpm}")

    classification, classification_reasons = classify_sheet(
        workbook_name,
        sheet,
        is_overview_sheet,
        overview_reasons,
        profile_header,
        normalized_profile_tiers_found,
        invalid_or_legacy_profile_values,
        supported_channels,
        unsupported_channels,
    )

    notes: list[str] = []
    warnings: list[str] = []

    if paid_detected and paid_relative_to_profiles == "before_profiles":
        notes.append("Paid section appears before profile section and is included in main budget context.")
    elif paid_detected and paid_relative_to_profiles == "after_profiles":
        notes.append("Paid section appears after profile section and is excluded from main optimization.")
    elif paid_detected and paid_relative_to_profiles == "unknown_without_profiles":
        warnings.append("Paid section detected but relative placement is unknown because no profile section was found.")

    if formula_cache_warnings:
        warnings.extend(formula_cache_warnings)

    if invalid_or_legacy_profile_values:
        notes.append("Legacy or invalid profile size values were preserved without coercion.")

    diff_detected = None
    if diff_label_cell or diff_value_cell:
        diff_detected = {
            "label_cell": diff_label_cell.ref if diff_label_cell else None,
            "label_value": diff_label_cell.value if diff_label_cell else None,
            "value_cell": diff_value_cell.ref if diff_value_cell else None,
            "value": diff_value_cell.value if diff_value_cell else None,
        }

    return AuditRecord(
        workbook_name=workbook_name,
        workbook_path=str(workbook_path),
        sheet_name=sheet.name,
        sheet_index=sheet_index,
        sheet_state=sheet.state,
        classification=classification,
        classification_reasons=classification_reasons,
        is_overview_sheet=is_overview_sheet,
        overview_reasons=overview_reasons,
        detected_budget=build_detected_value(budget_label, budget_value_cell),
        detected_agency_fee=build_detected_value(fee_label, fee_value_cell),
        paid_section_detected=paid_detected,
        paid_section=paid_section,
        paid_section_location=paid_section_location,
        paid_relative_to_profiles=paid_relative_to_profiles,
        paid_included_in_main_budget=paid_included,
        profile_section_detected=profile_header is not None,
        profile_section=profile_section,
        profile_section_location=profile_section_location,
        likely_profile_size_cells=likely_profile_size_cells,
        profile_row_count=len(profile_rows),
        current_profile_size_values=current_profile_size_values,
        normalized_profile_tiers_found=normalized_profile_tiers_found,
        invalid_or_legacy_profile_values=invalid_or_legacy_profile_values,
        supported_channels_found=supported_channels,
        unsupported_channels_found=unsupported_channels,
        cpm_values_detected=cpm_values_detected,
        diff_detected=diff_detected,
        formula_cache_warnings=formula_cache_warnings,
        notes=notes,
        warnings=warnings,
        max_row=sheet.max_row,
        max_column=sheet.max_column,
        non_empty_cell_count=len(sheet.cells),
    )


def choose_input_dir() -> Path:
    for candidate in INPUT_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "No workbook input directory found. Checked: "
        + ", ".join(str(candidate) for candidate in INPUT_CANDIDATES)
    )


def build_audit_warnings(input_dir: Path) -> list[str]:
    if input_dir == PRIMARY_INPUT_DIR:
        return []
    return [
        (
            f"Preferred input directory {PRIMARY_INPUT_DIR} was not available. "
            f"Audit used fallback directory {input_dir}."
        )
    ]


def flatten_record_for_csv(record: AuditRecord) -> dict[str, Any]:
    payload = record.to_json_dict()
    flattened: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, list):
            flattened[key] = "; ".join(str(item) for item in value)
        elif isinstance(value, dict):
            flattened[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            flattened[key] = value
    return flattened


def write_csv(path: Path, records: list[AuditRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if records:
        fieldnames = list(flatten_record_for_csv(records[0]).keys())
    else:
        fieldnames = list(AuditRecord.__dataclass_fields__.keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(flatten_record_for_csv(record))


def build_classification_counts(records: list[AuditRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.classification] = counts.get(record.classification, 0) + 1
    return dict(sorted(counts.items()))


def write_json(path: Path, input_dir: Path, records: list[AuditRecord], warnings: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "requested_input_directory": str(PRIMARY_INPUT_DIR),
        "input_directory": str(input_dir),
        "used_fallback_input_directory": input_dir != PRIMARY_INPUT_DIR,
        "workbook_count": len({record.workbook_name for record in records}),
        "sheet_count": len(records),
        "classification_counts": build_classification_counts(records),
        "warnings": warnings or [],
        "records": [record.to_json_dict() for record in records],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_audit_records(path: Path = AUDIT_JSON_PATH) -> tuple[dict[str, Any], list[AuditRecord]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload, [AuditRecord.from_json_dict(record) for record in payload.get("records", [])]


def format_detected_numeric(field_name: str, payload: dict[str, Any] | None) -> str:
    if payload is None:
        return "null"
    label_cell = payload.get("label_cell")
    value_cell = payload.get("value_cell")
    value = payload.get("value")
    if value is not None:
        if value_cell:
            return f"{value} ({value_cell})"
        return str(value)
    if label_cell:
        return f"null (label at {label_cell} unresolved)"
    return f"null ({field_name} not detected)"


def format_diff(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return "null"
    cell = payload.get("value_cell") or payload.get("label_cell")
    value = payload.get("value")
    if value is None:
        if cell:
            return f"null ({cell})"
        return "null"
    return f"{value} ({cell})" if cell else str(value)


def write_canonical_review(path: Path, records: list[AuditRecord]) -> None:
    canonical_records = [record for record in records if record.classification == "canonical_candidate"]
    lines = [
        "# Canonical Audit Review",
        "",
        f"- Canonical sheets: {len(canonical_records)}",
        f"- Source audit records considered: {len(records)}",
        "",
    ]
    for record in canonical_records:
        warnings = record.warnings or []
        lines.extend(
            [
                f"## {record.workbook_name} / {record.sheet_name}",
                "",
                f"- Workbook name: `{record.workbook_name}`",
                f"- Sheet name: `{record.sheet_name}`",
                f"- Budget: {format_detected_numeric('budget', record.detected_budget)}",
                f"- Agency fee: {format_detected_numeric('agency fee', record.detected_agency_fee)}",
                (
                    "- Paid included: "
                    + (
                        "yes"
                        if record.paid_included_in_main_budget is True
                        else "no"
                        if record.paid_section_detected
                        else "null"
                    )
                ),
                f"- Profile section location: {record.profile_section_location or 'null'}",
                f"- Profile row count: {record.profile_row_count}",
                (
                    "- Supported channels: "
                    + (", ".join(record.supported_channels_found) if record.supported_channels_found else "none")
                ),
                (
                    "- Unsupported channels: "
                    + (", ".join(record.unsupported_channels_found) if record.unsupported_channels_found else "none")
                ),
                (
                    "- CPM values detected: "
                    + ("; ".join(record.cpm_values_detected) if record.cpm_values_detected else "none")
                ),
                f"- Diff cell/value: {format_diff(record.diff_detected)}",
                f"- Warnings: {'; '.join(warnings) if warnings else 'none'}",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def run_audit(input_dir: Path | None = None) -> list[AuditRecord]:
    workbook_dir = input_dir or choose_input_dir()
    records: list[AuditRecord] = []
    for workbook_path in sorted(workbook_dir.glob("*.xlsx")):
        workbook = load_workbook(workbook_path)
        for sheet_index, sheet in enumerate(workbook.sheets):
            records.append(audit_sheet(workbook_path, sheet_index, sheet))
    return records


def run_audit_cli(input_dir: Path) -> list[AuditRecord]:
    records = run_audit(input_dir)
    warnings = build_audit_warnings(input_dir)
    write_csv(AUDIT_CSV_PATH, records)
    write_json(AUDIT_JSON_PATH, input_dir, records, warnings)
    print(f"Audited {len(records)} sheets from {input_dir}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    print(AUDIT_CSV_PATH)
    print(AUDIT_JSON_PATH)
    return records


def run_canonical_review(path: Path = CANONICAL_REVIEW_PATH) -> Path:
    if AUDIT_JSON_PATH.exists():
        _, records = load_audit_records(AUDIT_JSON_PATH)
    else:
        records = run_audit_cli(choose_input_dir())
    write_canonical_review(path, records)
    print(path)
    return path


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if args and args[0] == "--canonical-review":
        run_canonical_review()
        return 0

    input_dir = Path(args[0]) if args else choose_input_dir()
    run_audit_cli(input_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
