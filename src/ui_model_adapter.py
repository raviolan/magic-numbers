from __future__ import annotations

from decimal import Decimal
import math
import re
from typing import Any, Callable

from calculation_engine import to_decimal
from models import CanonicalCampaignModel, CanonicalProfileRow, CanonicalProfileSection, CanonicalSource
from optimizer import VALID_PROFILE_TIERS


SUPPORTED_CHANNELS = {"Instagram", "TikTok", "YouTube"}
SUPPORTED_CHANNELS_ORDERED = ["Instagram", "TikTok", "YouTube"]
DEFAULT_SELECTED_MANUAL_CHANNELS = ("Instagram", "TikTok")
MANUAL_FEE_MODES = ("Fixed amount", "Percentage of budget", "Percentage range")
DEFAULT_MANUAL_FEE_MODE = "Percentage of budget"
DEFAULT_AGENCY_FEE_PERCENT_TEXT = "32%"
DEFAULT_PAID_MEDIA_PERCENT_TEXT = "15%"
DEFAULT_PAID_MEDIA_INCLUDED = True
DEFAULT_PROFILE_FEE_DEDUCTION_PERCENT = Decimal("7.5")
MAX_MANUAL_FEE_COMBINATIONS = 200
PERCENT_RANGE_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*[-–]\s*([0-9]+(?:\.[0-9]+)?)\s*%?\s*$")


def _quantize_percent(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.001"))


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def format_display_number(value: Any) -> str:
    decimal_value = to_decimal(value)
    if decimal_value is None:
        return "-"
    float_value = float(decimal_value)
    if float_value.is_integer():
        return f"{int(float_value):,}".replace(",", " ")
    formatted = f"{float_value:,.2f}".replace(",", " ")
    return formatted.rstrip("0").rstrip(".")


def parse_friendly_amount(value: Any, field_name: str) -> float:
    if isinstance(value, (int, float, Decimal)):
        numeric = float(value)
    else:
        raw = str(value).strip().lower().replace("\u00a0", " ")
        if not raw:
            raise ValueError(f"{field_name} is required.")

        suffix = ""
        if raw.endswith("m") or raw.endswith("k"):
            suffix = raw[-1]
            raw = raw[:-1].strip()

        raw = raw.replace(" ", "")
        if "," in raw and "." in raw:
            if raw.rfind(",") > raw.rfind("."):
                raw = raw.replace(".", "").replace(",", ".")
            else:
                raw = raw.replace(",", "")
        elif "," in raw:
            if re.fullmatch(r"\d{1,3}(,\d{3})+", raw):
                raw = raw.replace(",", "")
            else:
                raw = raw.replace(",", ".")

        try:
            numeric = float(raw)
        except ValueError as error:
            raise ValueError(f"{field_name} must be a valid number.") from error

        if suffix == "m":
            numeric *= 1_000_000
        elif suffix == "k":
            numeric *= 1_000

    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be finite.")
    return numeric


def profile_size_to_k_display(value: Any) -> int | str | None:
    parsed = to_decimal(value)
    if parsed is None:
        return None
    if parsed == 0:
        return 0
    if parsed % Decimal("1000") == 0:
        return int(parsed / Decimal("1000"))
    if parsed == parsed.to_integral_value():
        return int(parsed)
    return float(parsed)


def choose_option_for_fill_view(
    options: list[dict[str, Any]],
    recommended_option_label: str,
    selected_option_label: str | None = None,
) -> dict[str, Any]:
    by_label = {str(option.get("option_label")): option for option in options}
    if selected_option_label and selected_option_label in by_label:
        return by_label[selected_option_label]
    if recommended_option_label in by_label:
        return by_label[recommended_option_label]
    if not options:
        raise ValueError("No options available for fill-instruction view.")
    return options[0]


def _to_required_decimal(value: Any, field_name: str) -> Decimal:
    decimal_value = to_decimal(value)
    if decimal_value is None:
        raise ValueError(f"{field_name} is required and must be numeric.")
    return decimal_value


def _parse_optional_tier(value: Any, row_number: int) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    parsed = int(to_decimal(value))
    if parsed not in VALID_PROFILE_TIERS:
        raise ValueError(
            f"Row {row_number}: current_profile_size must be one of {list(VALID_PROFILE_TIERS)}, got {parsed}."
        )
    return parsed


def deduction_percent_to_multiplier(deduction_percent: Any) -> float:
    deduction = _to_required_decimal(deduction_percent, "profile_fee_deduction_percent")
    if deduction < 0 or deduction >= 100:
        raise ValueError("profile_fee_deduction_percent must be between 0 and 100.")
    return float((Decimal("1") - (deduction / Decimal("100"))).quantize(Decimal("0.000001")))


def parse_percentage_value(value: Any, field_name: str) -> Decimal:
    if isinstance(value, (int, float, Decimal)):
        percent = _to_required_decimal(value, field_name)
    else:
        raw = str(value).strip()
        if not raw:
            raise ValueError(f"{field_name} is required.")
        if raw.endswith("%"):
            raw = raw[:-1].strip()
        percent = _to_required_decimal(raw, field_name)
    if percent < 0:
        raise ValueError(f"{field_name} must be >= 0.")
    return _quantize_percent(percent)


def parse_percentage_range(value: Any, field_name: str) -> tuple[Decimal, Decimal]:
    raw = str(value).strip()
    match = PERCENT_RANGE_RE.match(raw)
    if not match:
        raise ValueError(f'{field_name} must be a range like "29-35%" or "29-35".')
    start = parse_percentage_value(match.group(1), f"{field_name}_start")
    end = parse_percentage_value(match.group(2), f"{field_name}_end")
    if end < start:
        raise ValueError(f"{field_name} end must be greater than or equal to start.")
    return start, end


def expand_percentage_range(range_input: Any, step_input: Any, field_name: str) -> list[Decimal]:
    start, end = parse_percentage_range(range_input, field_name)
    step = parse_percentage_value(step_input, f"{field_name}_step")
    if step <= 0:
        raise ValueError(f"{field_name} step must be > 0.")

    values: list[Decimal] = []
    current = start
    epsilon = Decimal("0.000001")
    while current <= end + epsilon:
        values.append(_quantize_percent(current))
        current += step
    if values and values[-1] > end:
        values[-1] = end
    if values and values[-1] != end:
        values.append(end)
    return sorted(set(values))


def resolve_fee_candidates(
    mode: str,
    budget: Any,
    fixed_amount: Any | None = None,
    percent_value: Any | None = None,
    percent_range: Any | None = None,
    range_step: Any | None = None,
    field_name: str = "fee",
) -> list[dict[str, float | None]]:
    budget_decimal = _to_required_decimal(budget, "budget")
    if mode == "Fixed amount":
        amount = _to_required_decimal(fixed_amount, f"{field_name}_amount")
        return [{"amount": float(amount), "percent": None}]
    if mode == "Percentage of budget":
        percent = parse_percentage_value(percent_value, f"{field_name}_percent")
        amount = (budget_decimal * percent) / Decimal("100")
        return [{"amount": float(amount), "percent": float(percent)}]
    if mode == "Percentage range":
        values = expand_percentage_range(percent_range, range_step, f"{field_name}_percent_range")
        candidates: list[dict[str, float | None]] = []
        for percent in values:
            amount = (budget_decimal * percent) / Decimal("100")
            candidates.append({"amount": float(amount), "percent": float(percent)})
        return candidates
    raise ValueError(f"Unsupported {field_name} mode: {mode!r}.")


def build_fee_paid_combinations(
    agency_candidates: list[dict[str, float | None]],
    paid_media_candidates: list[dict[str, float | None]],
    max_combinations: int = MAX_MANUAL_FEE_COMBINATIONS,
) -> list[tuple[dict[str, float | None], dict[str, float | None]]]:
    combinations = [(agency, paid) for agency in agency_candidates for paid in paid_media_candidates]
    if len(combinations) > max_combinations:
        raise ValueError(
            f"Too many fee/paid combinations ({len(combinations)}). Narrow the ranges or increase the step (max {max_combinations})."
        )
    return combinations


def _manual_result_sort_key(result: dict[str, Any]) -> tuple[Any, ...]:
    recommended = next(option for option in result["options"] if option["option_label"] == result["recommended_option_label"])
    score = recommended.get("recommendation_score_breakdown", {}).get("total_score", 0)
    return (
        0 if recommended["diagnostics"]["non_negative_diff"] else 1,
        -float(score),
        abs(float(recommended["optimized_diff"])),
        result["recommended_option_label"],
    )


def evaluate_fee_paid_combinations(
    combinations: list[tuple[dict[str, float | None], dict[str, float | None]]],
    build_model_fn: Callable[[dict[str, float | None], dict[str, float | None]], CanonicalCampaignModel],
    run_optimizer_fn: Callable[[CanonicalCampaignModel], dict[str, Any]],
) -> dict[str, Any]:
    best_payload: dict[str, Any] | None = None
    best_result: dict[str, Any] | None = None
    best_agency: dict[str, float | None] | None = None
    best_paid: dict[str, float | None] | None = None

    for agency_candidate, paid_candidate in combinations:
        model = build_model_fn(agency_candidate, paid_candidate)
        payload = run_optimizer_fn(model)
        result = payload["results"][0]
        if best_result is None or _manual_result_sort_key(result) < _manual_result_sort_key(best_result):
            best_payload = payload
            best_result = result
            best_agency = agency_candidate
            best_paid = paid_candidate

    if best_payload is None or best_result is None or best_agency is None or best_paid is None:
        raise ValueError("No valid fee/paid combination could be evaluated.")
    return {
        "payload": best_payload,
        "result": best_result,
        "selected_agency": best_agency,
        "selected_paid_media": best_paid,
        "combinations_evaluated": len(combinations),
    }


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return int(_to_required_decimal(value, "value"))


def _optional_positive_decimal(value: Any, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    parsed = _to_required_decimal(value, field_name)
    if parsed <= 0:
        raise ValueError(f"{field_name} must be greater than 0.")
    return parsed


def normalize_selected_channels(selected_channels: list[str] | tuple[str, ...] | None) -> list[str]:
    if selected_channels is None:
        return list(SUPPORTED_CHANNELS_ORDERED)
    normalized: list[str] = []
    seen: set[str] = set()
    for channel in selected_channels:
        text = _normalize_optional_string(channel)
        if text is None:
            continue
        if text not in SUPPORTED_CHANNELS:
            raise ValueError(f"Unsupported selected channel: {text!r}.")
        if text not in seen:
            normalized.append(text)
            seen.add(text)
    return [channel for channel in SUPPORTED_CHANNELS_ORDERED if channel in normalized]


def parse_channel_split(
    total_profiles: Any,
    instagram_count: Any = None,
    tiktok_count: Any = None,
    youtube_count: Any = None,
    selected_channels: list[str] | tuple[str, ...] | None = None,
) -> dict[str, int]:
    total = int(_to_required_decimal(total_profiles, "total_profiles"))
    if total <= 0:
        raise ValueError("total_profiles must be greater than 0.")
    selected = normalize_selected_channels(selected_channels)
    if not selected:
        raise ValueError("At least one channel must be selected.")

    provided = {
        "Instagram": _optional_int(instagram_count),
        "TikTok": _optional_int(tiktok_count),
        "YouTube": _optional_int(youtube_count),
    }
    for channel in SUPPORTED_CHANNELS_ORDERED:
        if channel not in selected and provided[channel] is not None:
            raise ValueError(f"{channel} count cannot be set because {channel} is not selected.")
    for channel, value in provided.items():
        if value is not None and value < 0:
            raise ValueError(f"{channel} profile count must be >= 0.")

    specified_total = sum(provided[channel] for channel in selected if provided[channel] is not None)
    missing_channels = [channel for channel in selected if provided[channel] is None]

    if specified_total > total:
        raise ValueError("Channel split exceeds total profiles.")
    if len(missing_channels) > 1 and specified_total > 0:
        raise ValueError("Provide counts for all but at most one channel when using explicit channel split.")
    if len(missing_channels) == 1:
        provided[missing_channels[0]] = total - specified_total
    elif len(missing_channels) == 0 and specified_total != total:
        raise ValueError("Channel split must sum to total profiles.")
    elif len(missing_channels) == len(selected):
        # Deterministic default distribution.
        base = total // len(selected)
        remainder = total % len(selected)
        for index, channel in enumerate(selected):
            provided[channel] = base + (1 if index < remainder else 0)

    resolved = {channel: (int(provided[channel] or 0) if channel in selected else 0) for channel in SUPPORTED_CHANNELS_ORDERED}
    if sum(resolved.values()) != total:
        raise ValueError("Resolved channel split does not equal total profiles.")
    return resolved


def resolve_project_cpms(
    instagram_cpm: Any = None,
    tiktok_cpm: Any = None,
    youtube_cpm: Any = None,
) -> dict[str, float | None]:
    parsed = {
        "Instagram": _optional_positive_decimal(instagram_cpm, "instagram_cpm"),
        "TikTok": _optional_positive_decimal(tiktok_cpm, "tiktok_cpm"),
        "YouTube": _optional_positive_decimal(youtube_cpm, "youtube_cpm"),
    }
    return {channel: (float(value) if value is not None else None) for channel, value in parsed.items()}


def validate_project_cpms_for_rows(rows: list[dict[str, Any]], project_cpms: dict[str, float | None]) -> None:
    used_channels = {str(row.get("channel")).strip() for row in rows if row.get("channel")}
    for channel in used_channels:
        if channel not in SUPPORTED_CHANNELS:
            raise ValueError(f"Unsupported channel {channel!r} in profile rows.")
        if project_cpms.get(channel) is None:
            raise ValueError(f"{channel} CPM is required because {channel} is used in profile rows.")


def generate_profile_rows(
    total_profiles: Any,
    project_cpms: dict[str, float | None],
    channel_split: dict[str, int],
    selected_channels: list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    total = int(_to_required_decimal(total_profiles, "total_profiles"))
    if sum(channel_split.values()) != total:
        raise ValueError("Channel split must equal total profiles.")
    selected = normalize_selected_channels(selected_channels)
    if not selected:
        raise ValueError("At least one channel must be selected.")

    rows: list[dict[str, Any]] = []
    row_index = 1
    for channel in selected:
        count = int(channel_split.get(channel, 0))
        if count > 0 and project_cpms.get(channel) is None:
            raise ValueError(f"{channel} CPM must be set before generating rows.")
        for _ in range(count):
            rows.append(
                {
                    "row_index": row_index,
                    "profile_size_cell": "",
                    "current_profile_size": "",
                    "channel": channel,
                    "market": "",
                    "cpm": project_cpms.get(channel),
                    "activations": 1,
                }
            )
            row_index += 1
    return rows


def apply_project_cpms_to_rows(rows: list[dict[str, Any]], project_cpms: dict[str, float | None]) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for row in rows:
        channel = str(row.get("channel")).strip() if row.get("channel") else None
        updated_row = dict(row)
        if channel in SUPPORTED_CHANNELS and project_cpms.get(channel) is not None:
            updated_row["cpm"] = project_cpms[channel]
        updated.append(updated_row)
    return updated


def validate_rows_use_selected_channels(
    rows: list[dict[str, Any]],
    selected_channels: list[str] | tuple[str, ...],
) -> None:
    selected = set(normalize_selected_channels(selected_channels))
    if not selected:
        raise ValueError("At least one channel must be selected.")
    offending = []
    for row in rows:
        channel = _normalize_optional_string(row.get("channel"))
        if channel and channel not in selected:
            offending.append(channel)
    if offending:
        unique = ", ".join(sorted(set(offending)))
        raise ValueError(f"Profile rows include {unique}, but those channels are not selected for this campaign.")


def validate_manual_campaign_input(
    budget: Any,
    agency_fee: Any,
    paid_media: Any,
    profile_budget_target_multiplier: Any,
    rows: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    for field_name, value in (
        ("budget", budget),
        ("agency_fee", agency_fee),
        ("paid_media", paid_media),
        ("profile_budget_target_multiplier", profile_budget_target_multiplier),
    ):
        try:
            _to_required_decimal(value, field_name)
        except ValueError as error:
            errors.append(str(error))

    if not rows:
        errors.append("At least one profile row is required.")
        return errors

    for index, row in enumerate(rows, start=1):
        channel = _normalize_optional_string(row.get("channel"))
        if channel not in SUPPORTED_CHANNELS:
            errors.append(f"Row {index}: channel must be one of {sorted(SUPPORTED_CHANNELS)}.")
        if to_decimal(row.get("cpm")) is None:
            errors.append(f"Row {index}: cpm is required and must be numeric.")
        activations = to_decimal(row.get("activations"))
        if activations is None:
            errors.append(f"Row {index}: activations is required and must be numeric.")
        elif activations <= 0:
            errors.append(f"Row {index}: activations must be greater than 0.")
        try:
            _parse_optional_tier(row.get("current_profile_size"), index)
        except ValueError as error:
            errors.append(str(error))
    return errors


def build_manual_campaign_model(
    campaign_name: str,
    budget: Any,
    agency_fee: Any,
    paid_media: Any,
    paid_media_included: bool,
    profile_budget_target_multiplier: Any,
    rows: list[dict[str, Any]],
) -> CanonicalCampaignModel:
    validation_errors = validate_manual_campaign_input(
        budget=budget,
        agency_fee=agency_fee,
        paid_media=paid_media,
        profile_budget_target_multiplier=profile_budget_target_multiplier,
        rows=rows,
    )
    if validation_errors:
        raise ValueError("\n".join(validation_errors))

    normalized_rows: list[CanonicalProfileRow] = []
    for index, row in enumerate(rows, start=1):
        row_index = int(row.get("row_index") or index)
        current_profile_size = _parse_optional_tier(row.get("current_profile_size"), index)
        normalized_rows.append(
            CanonicalProfileRow(
                row_index=row_index,
                profile_size_cell=_normalize_optional_string(row.get("profile_size_cell")),
                current_profile_size=current_profile_size,
                workbook_raw_profile_size_value=current_profile_size // 1000 if current_profile_size else None,
                market=_normalize_optional_string(row.get("market")),
                channel=_normalize_optional_string(row.get("channel")),
                raw_channel_label=_normalize_optional_string(row.get("channel")),
                cpm=float(_to_required_decimal(row.get("cpm"), f"row {index} cpm")),
                cpm_cell=None,
                cpm_value=float(_to_required_decimal(row.get("cpm"), f"row {index} cpm")),
                activations=float(_to_required_decimal(row.get("activations"), f"row {index} activations")),
                activations_cell=None,
                activations_value=float(_to_required_decimal(row.get("activations"), f"row {index} activations")),
                impressions_cell=None,
                impressions_value=None,
                profile_fee_cell=None,
                profile_fee_value=None,
                locked=False,
                warnings=[],
            )
        )

    resolved_campaign_name = campaign_name.strip() if campaign_name and campaign_name.strip() else "Manual builder"
    return CanonicalCampaignModel(
        source=CanonicalSource(
            workbook_name="Manual campaign",
            workbook_path="",
            sheet_name=resolved_campaign_name,
            sheet_index=0,
            classification="manual_campaign_builder",
        ),
        budget=float(_to_required_decimal(budget, "budget")),
        agency_fee=float(_to_required_decimal(agency_fee, "agency_fee")),
        paid_media=float(_to_required_decimal(paid_media, "paid_media")),
        paid_media_included=bool(paid_media_included),
        profile_budget_target_multiplier=float(_to_required_decimal(profile_budget_target_multiplier, "profile_budget_target_multiplier")),
        profile_budget_target_cell=None,
        profile_budget_target_value=None,
        profile_fee_sum_cell=None,
        profile_fee_sum_value=None,
        profile_section=CanonicalProfileSection(anchor_cell=None, location="manual builder", row_count=len(normalized_rows)),
        profile_rows=normalized_rows,
        diff=None,
        warnings=[],
    )
