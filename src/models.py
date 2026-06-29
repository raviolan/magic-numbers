from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CellValue:
    ref: str
    row: int
    column: int
    value: Any
    formula: str | None = None
    data_type: str | None = None
    style_id: int | None = None


@dataclass
class SheetData:
    name: str
    state: str
    cells: dict[str, CellValue]
    max_row: int
    max_column: int

    def iter_rows(self) -> list[list[CellValue]]:
        rows: dict[int, list[CellValue]] = {}
        for cell in self.cells.values():
            rows.setdefault(cell.row, []).append(cell)
        return [sorted(row, key=lambda cell: cell.column) for _, row in sorted(rows.items())]


@dataclass
class WorkbookData:
    path: str
    sheets: list[SheetData]
    shared_strings_count: int = 0


@dataclass
class AuditRecord:
    workbook_name: str
    workbook_path: str
    sheet_name: str
    sheet_index: int
    sheet_state: str
    classification: str
    classification_reasons: list[str] = field(default_factory=list)
    is_overview_sheet: bool = False
    overview_reasons: list[str] = field(default_factory=list)
    detected_budget: dict[str, Any] | None = None
    detected_agency_fee: dict[str, Any] | None = None
    paid_section_detected: bool = False
    paid_section: dict[str, Any] | None = None
    paid_section_location: str | None = None
    paid_relative_to_profiles: str = "not_found"
    paid_included_in_main_budget: bool = False
    profile_section_detected: bool = False
    profile_section: dict[str, Any] | None = None
    profile_section_location: str | None = None
    likely_profile_size_cells: list[str] = field(default_factory=list)
    profile_row_count: int = 0
    current_profile_size_values: list[str] = field(default_factory=list)
    normalized_profile_tiers_found: list[int] = field(default_factory=list)
    invalid_or_legacy_profile_values: list[str] = field(default_factory=list)
    supported_channels_found: list[str] = field(default_factory=list)
    unsupported_channels_found: list[str] = field(default_factory=list)
    cpm_values_detected: list[str] = field(default_factory=list)
    diff_detected: dict[str, Any] | None = None
    formula_cache_warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    max_row: int = 0
    max_column: int = 0
    non_empty_cell_count: int = 0

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json_dict(cls, payload: dict[str, Any]) -> "AuditRecord":
        return cls(**payload)


@dataclass
class CanonicalSource:
    workbook_name: str
    workbook_path: str
    sheet_name: str
    sheet_index: int
    classification: str


@dataclass
class CanonicalProfileSection:
    anchor_cell: str | None
    location: str | None
    row_count: int


@dataclass
class CanonicalProfileRow:
    row_index: int
    profile_size_cell: str | None
    current_profile_size: int | None
    workbook_raw_profile_size_value: Any = None
    market: str | None = None
    channel: str | None = None
    raw_channel_label: str | None = None
    cpm: Any = None
    cpm_cell: str | None = None
    cpm_value: Any = None
    activations: Any = None
    activations_cell: str | None = None
    activations_value: Any = None
    impressions_cell: str | None = None
    impressions_value: Any = None
    profile_fee_cell: str | None = None
    profile_fee_value: Any = None
    locked: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class CanonicalDiff:
    cell: str | None
    value: Any = None


@dataclass
class CanonicalCampaignModel:
    source: CanonicalSource
    budget: Any = None
    agency_fee: Any = None
    paid_media: Any = None
    paid_media_included: bool | None = None
    profile_budget_target_multiplier: Any = None
    profile_budget_target_cell: str | None = None
    profile_budget_target_value: Any = None
    profile_fee_sum_cell: str | None = None
    profile_fee_sum_value: Any = None
    profile_section: CanonicalProfileSection | None = None
    profile_rows: list[CanonicalProfileRow] = field(default_factory=list)
    diff: CanonicalDiff | None = None
    warnings: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json_dict(cls, payload: dict[str, Any]) -> "CanonicalCampaignModel":
        return cls(
            source=CanonicalSource(**payload["source"]),
            budget=payload.get("budget"),
            agency_fee=payload.get("agency_fee"),
            paid_media=payload.get("paid_media"),
            paid_media_included=payload.get("paid_media_included"),
            profile_budget_target_multiplier=payload.get("profile_budget_target_multiplier"),
            profile_budget_target_cell=payload.get("profile_budget_target_cell"),
            profile_budget_target_value=payload.get("profile_budget_target_value"),
            profile_fee_sum_cell=payload.get("profile_fee_sum_cell"),
            profile_fee_sum_value=payload.get("profile_fee_sum_value"),
            profile_section=CanonicalProfileSection(**payload["profile_section"]) if payload.get("profile_section") else None,
            profile_rows=[CanonicalProfileRow(**row) for row in payload.get("profile_rows", [])],
            diff=CanonicalDiff(**payload["diff"]) if payload.get("diff") else None,
            warnings=list(payload.get("warnings", [])),
        )


@dataclass
class ValidationSource:
    workbook_name: str
    sheet_name: str
    workbook_diff_cell: str | None
    workbook_diff_value: Any = None


@dataclass
class ValidationInputs:
    budget: Any = None
    agency_fee: Any = None
    paid_media: Any = None
    paid_media_included: bool | None = None
    profile_budget_target_multiplier: Any = None


@dataclass
class RowCalculation:
    row_index: int
    profile_size: int | None
    profile_size_cell: str | None
    workbook_raw_profile_size_value: Any = None
    channel: str | None = None
    market: str | None = None
    multiplier: Any = None
    impressions: Any = None
    captured_workbook_impressions: Any = None
    impressions_cell: str | None = None
    cpm: Any = None
    cpm_cell: str | None = None
    activations: Any = None
    activations_cell: str | None = None
    calculated_row_cost: Any = None
    captured_workbook_row_fee: Any = None
    profile_fee_cell: str | None = None
    raw_impressions_path: dict[str, Any] | None = None
    thousands_rounded_path: dict[str, Any] | None = None
    captured_impressions_path: dict[str, Any] | None = None
    selected_row_fee_formula: str | None = None
    selected_row_fee_value: Any = None
    selected_row_fee_delta_vs_workbook: Any = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class ValidationTotals:
    calculated_profile_cost: Any = None
    included_paid_media_cost: Any = None
    agency_fee: Any = None
    calculated_total_cost: Any = None
    calculated_diff: Any = None


@dataclass
class ValidationResult:
    diff_delta_vs_workbook: Any = None
    abs_diff_delta_vs_workbook: Any = None
    row_fee_sum_delta: Any = None
    workbook_style_diff_delta_vs_workbook: Any = None
    validation_status: str = "mismatch"
    warnings: list[str] = field(default_factory=list)


@dataclass
class ValidationDiagnostics:
    selected_row_fee_formula: str | None = None
    legacy_campaign_total_cost: Any = None
    legacy_campaign_total_diff: Any = None
    cpm_derived_profile_fee_sum: Any = None
    raw_impressions_profile_fee_sum: Any = None
    thousands_rounded_profile_fee_sum: Any = None
    captured_impressions_profile_fee_sum: Any = None
    selected_deterministic_row_fee_sum: Any = None
    captured_workbook_profile_fee_sum: Any = None
    profile_budget_target: Any = None
    profile_budget_target_cell: str | None = None
    profile_fee_sum_cell: str | None = None
    workbook_style_calculated_diff: Any = None


@dataclass
class CampaignValidationRecord:
    source: ValidationSource
    inputs: ValidationInputs
    diagnostics: ValidationDiagnostics = field(default_factory=ValidationDiagnostics)
    row_calculations: list[RowCalculation] = field(default_factory=list)
    totals: ValidationTotals = field(default_factory=ValidationTotals)
    validation: ValidationResult = field(default_factory=ValidationResult)

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)
