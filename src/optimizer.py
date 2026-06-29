from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
import json
import re
from pathlib import Path
import subprocess
from typing import Any

from calculation_engine import (
    calculate_row_impressions,
    calculate_thousands_rounded_impressions,
    calculate_thousands_rounded_row_fee,
    choose_selected_row_fee_formula,
    json_number,
    load_normalized_models,
    to_decimal,
)
from models import CanonicalCampaignModel, CanonicalProfileRow
from option_eligibility import is_option_diff_recommendable


INPUT_PATH = Path("data/normalized/canonical_normalized_models.json")
OUTPUT_DIR = Path("data/optimizer")
JSON_OUTPUT_PATH = OUTPUT_DIR / "optimizer_results.json"
MARKDOWN_OUTPUT_PATH = OUTPUT_DIR / "optimizer_results.md"
VALID_PROFILE_TIERS = (15000, 35000, 75000, 125000, 175000)
SIMPLIFIED_BUDGET_PROFILE_GUIDANCE = {
    100000: {"recommended_max_tier": 35000, "anchor_tier_limit": 0},
    150000: {"recommended_max_tier": 75000, "anchor_tier_limit": 0},
    200000: {"recommended_max_tier": 75000, "anchor_tier_limit": 0},
    250000: {"recommended_max_tier": 175000, "anchor_tier_limit": 1},
    300000: {"recommended_max_tier": 175000, "anchor_tier_limit": None},
    350000: {"recommended_max_tier": 175000, "anchor_tier_limit": None},
    400000: {"recommended_max_tier": 175000, "anchor_tier_limit": None},
}
SELECTED_ROW_FEE_FORMULA = "thousands_rounded_path"
DEFAULT_BEAM_WIDTH = 1000
DEFAULT_TOP_N = 5
DEFAULT_EXACT_MAX_STATES = 250000
PARTIAL_FEE_BUCKET_SIZE = Decimal("5000")
PARTIAL_IMPRESSIONS_BUCKET_SIZE = Decimal("25")
STRATEGIC_ABS_DIFF_TOLERANCE = Decimal("5000")
BASELINE_COMPARISON_TOLERANCE = Decimal("0.01")
OPTIMIZATION_METHODS = ("fast_closest_diff", "exact_closest_diff")
PAID_AD_PRICE = Decimal("2000")
PAID_CPM_BY_CHANNEL = {
    "Instagram": Decimal("20"),
    "TikTok": Decimal("15"),
}
PAID_DELIVERY_MULTIPLIER = Decimal("0.85")


class ExactSearchStateLimitError(ValueError):
    """Raised when exact search reaches an unsafe state count."""


@dataclass(frozen=True)
class RowCandidate:
    row_index: int
    profile_size_cell: str | None
    previous_profile_size: int | None
    recommended_profile_size: int
    channel: str | None
    market: str | None
    cpm: Any
    activations: Any
    impressions: Decimal
    row_fee: Decimal


@dataclass
class SearchState:
    next_row_index: int
    profile_fee_sum: Decimal
    total_impressions: Decimal
    tier_counts: dict[int, int]
    impressions_by_channel: dict[str, Decimal]
    impressions_by_market: dict[str, Decimal]
    assignments: list[RowCandidate] = field(default_factory=list)


def assignment_signature_from_assignments(assignments: list[RowCandidate]) -> tuple[int, ...]:
    return tuple(candidate.recommended_profile_size for candidate in assignments)


def parse_bool_flag(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"Expected a boolean value, got {value!r}.")


def normalize_allowed_tiers(allowed_tiers: list[int] | tuple[int, ...] | None) -> tuple[int, ...]:
    if allowed_tiers is None:
        return VALID_PROFILE_TIERS
    normalized = tuple(sorted({int(tier) for tier in allowed_tiers}))
    invalid = [tier for tier in normalized if tier not in VALID_PROFILE_TIERS]
    if invalid:
        raise ValueError(f"allowed_tiers contains unsupported tiers: {invalid}. Supported tiers: {list(VALID_PROFILE_TIERS)}.")
    if not normalized:
        raise ValueError("At least one allowed profile size tier is required.")
    return normalized


def decimal_to_bucket(value: Decimal, bucket_size: Decimal) -> int:
    if bucket_size <= 0:
        return int(value)
    return int(value // bucket_size)


def format_money(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return str(int(value))
        return format_money(float(value))
    return str(value)


def format_zero_decimal_number(value: Any) -> str:
    decimal_value = to_decimal(value)
    if decimal_value is None:
        return "null"
    return str(int(decimal_value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


def compare_against_baseline(best_diff: Any, baseline_diff: Any, tolerance: Decimal = BASELINE_COMPARISON_TOLERANCE) -> str:
    best_abs_diff = abs(to_decimal(best_diff))
    baseline_abs_diff = abs(to_decimal(baseline_diff))
    delta = best_abs_diff - baseline_abs_diff
    if abs(delta) <= tolerance:
        return "equals"
    if delta < 0:
        return "improves"
    return "worse"


def to_float(value: Any) -> float:
    return float(to_decimal(value))


def filter_models(
    models: list[CanonicalCampaignModel],
    workbook: str | None = None,
    sheet: str | None = None,
) -> list[CanonicalCampaignModel]:
    filtered = []
    for model in models:
        if workbook and model.source.workbook_name != workbook:
            continue
        if sheet and model.source.sheet_name != sheet:
            continue
        filtered.append(model)
    return filtered


def resolve_unique_sheet_selection(
    models: list[CanonicalCampaignModel],
    workbook: str | None = None,
    sheet: str | None = None,
) -> list[CanonicalCampaignModel]:
    if not sheet:
        return filter_models(models, workbook=workbook, sheet=sheet)
    if workbook:
        filtered = filter_models(models, workbook=workbook, sheet=sheet)
        if not filtered:
            raise ValueError(f'No canonical sheet matched workbook "{workbook}" and sheet "{sheet}".')
        return filtered
    matches = [model for model in models if model.source.sheet_name == sheet]
    if not matches:
        raise ValueError(f'No canonical sheet matched sheet name "{sheet}".')
    if len(matches) > 1:
        lines = [f'Sheet name "{sheet}" matched multiple canonical sheets:']
        for model in matches:
            lines.append(f"- {model.source.workbook_name} / {model.source.sheet_name}")
        raise ValueError("\n".join(lines))
    return matches


def slugify_result_name(text: str) -> str:
    normalized = text.lower()
    normalized = re.sub(r"[^\w]+", "-", normalized)
    normalized = re.sub(r"_+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized)
    return normalized.strip("-")


def choose_output_paths(
    models: list[CanonicalCampaignModel],
    json_output_path: Path = JSON_OUTPUT_PATH,
    markdown_output_path: Path = MARKDOWN_OUTPUT_PATH,
) -> tuple[Path, Path]:
    if len(models) != 1:
        return json_output_path, markdown_output_path
    model = models[0]
    workbook_stem = Path(model.source.workbook_name).stem
    slug = slugify_result_name(f"{workbook_stem}-{model.source.sheet_name}")
    base_name = f"optimizer_results_{slug}"
    return OUTPUT_DIR / f"{base_name}.json", OUTPUT_DIR / f"{base_name}.md"


def build_terminal_summary(payload: dict[str, Any], markdown_path: Path, json_path: Path) -> str:
    lines = [
        f"Processed {payload['campaign_count']} campaign{'s' if payload['campaign_count'] != 1 else ''}",
        f"Markdown: {markdown_path}",
        f"JSON: {json_path}",
    ]
    for result in payload["results"]:
        recommended = next(option for option in result["options"] if option["option_label"] == result["recommended_option_label"])
        baseline = next((option for option in result["options"] if option["option_label"] == "current_workbook_mix"), None)
        major_warnings = recommended["strategic_warnings"] if recommended["strategic_warnings"] else ["none"]
        baseline_diff_text = format_money(baseline["optimized_diff"]) if baseline is not None else "unavailable"
        improves_text = "yes" if recommended["improves_on_baseline"] else ("unavailable" if baseline is None else "no")
        lines.extend(
            [
                f"{result['source']['workbook_name']} / {result['source']['sheet_name']}",
                f"Recommended: {result['recommended_option_label']}",
                f"Recommended diff: {format_money(recommended['optimized_diff'])}",
                f"Baseline diff: {baseline_diff_text}",
                f"Improves baseline: {improves_text}",
                f"Warnings: {'; '.join(major_warnings)}",
            ]
        )
    return "\n".join(lines)


def open_report(markdown_path: Path) -> str | None:
    try:
        subprocess.run(["open", str(markdown_path)], check=True)
        return None
    except Exception as error:  # pragma: no cover - exercised with mock in tests
        return f"Warning: failed to open report at {markdown_path}: {error}"


def compute_profile_budget_target(model: CanonicalCampaignModel) -> Decimal:
    budget = to_decimal(model.budget)
    agency_fee = to_decimal(model.agency_fee)
    if budget is None or agency_fee is None:
        raise ValueError("Budget and agency fee are required to compute the profile budget target.")

    included_paid_media = Decimal("0")
    if model.paid_media_included is True:
        paid_media = to_decimal(model.paid_media)
        if paid_media is None:
            raise ValueError("Paid media is marked as included but the numeric paid_media value is missing.")
        included_paid_media = paid_media

    multiplier = to_decimal(model.profile_budget_target_multiplier)
    if multiplier is None:
        multiplier = Decimal("0.925")
    return multiplier * (budget - agency_fee - included_paid_media)


def build_budget_breakdown(model: CanonicalCampaignModel) -> dict[str, Any]:
    budget = to_decimal(model.budget)
    agency_fee = to_decimal(model.agency_fee)
    paid_media = to_decimal(model.paid_media)
    multiplier = to_decimal(model.profile_budget_target_multiplier)
    if multiplier is None:
        multiplier = Decimal("0.925")

    return {
        "budget": json_number(budget),
        "agency_fee": json_number(agency_fee),
        "paid_media": json_number(paid_media),
        "paid_media_included": model.paid_media_included,
        "profile_budget_target_multiplier": json_number(multiplier),
        "profile_budget_target": json_number(compute_profile_budget_target(model)),
    }


def calculate_candidate_row_impressions(profile_size: int, channel: str | None) -> Decimal:
    impressions = calculate_thousands_rounded_impressions(profile_size, channel)
    if impressions is None:
        raise ValueError(f"Could not calculate impressions for profile_size={profile_size} channel={channel!r}.")
    return impressions


def calculate_candidate_row_fee(profile_size: int, channel: str | None, cpm: Any, activations: Any) -> Decimal:
    row_fee = calculate_thousands_rounded_row_fee(profile_size, channel, cpm, activations)
    if row_fee is None:
        raise ValueError(
            f"Could not calculate row fee for profile_size={profile_size}, channel={channel!r}, cpm={cpm!r}, activations={activations!r}."
        )
    return row_fee


def calculate_paid_amplification_breakdown(
    *,
    paid_media_included: bool,
    paid_budget: Any,
    assignments: list[RowCandidate],
) -> dict[str, Any]:
    paid_budget_decimal = to_decimal(paid_budget) or Decimal("0")
    paid_channels = tuple(PAID_CPM_BY_CHANNEL.keys())
    channel_profile_counts = {
        channel: sum(1 for candidate in assignments if candidate.channel == channel)
        for channel in paid_channels
    }
    ad_count = sum(channel_profile_counts.values()) if paid_media_included else 0
    ad_cost = PAID_AD_PRICE * Decimal(ad_count)
    remaining_paid_budget = max(Decimal("0"), paid_budget_decimal - ad_cost) if paid_media_included else Decimal("0")
    eligible_profile_count = sum(channel_profile_counts.values())

    channel_budget: dict[str, Decimal] = {}
    channel_paid_impressions: dict[str, Decimal] = {}
    for channel in paid_channels:
        count = channel_profile_counts[channel]
        if paid_media_included and eligible_profile_count > 0:
            budget_share = remaining_paid_budget * Decimal(count) / Decimal(eligible_profile_count)
        else:
            budget_share = Decimal("0")
        channel_budget[channel] = budget_share
        full_paid_impressions = (
            budget_share * Decimal("1000") / PAID_CPM_BY_CHANNEL[channel] * PAID_DELIVERY_MULTIPLIER
            if budget_share > 0
            else Decimal("0")
        )
        channel_paid_impressions[channel] = full_paid_impressions / Decimal("1000")

    return {
        "paid_media_included": bool(paid_media_included),
        "paid_budget": json_number(paid_budget_decimal if paid_media_included else Decimal("0")),
        "ad_count": int(ad_count),
        "ad_cost": json_number(ad_cost if paid_media_included else Decimal("0")),
        "remaining_paid_budget": json_number(remaining_paid_budget),
        "channel_profile_counts": {channel: int(count) for channel, count in channel_profile_counts.items()},
        "channel_budget": {channel: json_number(value) for channel, value in channel_budget.items()},
        "channel_paid_impressions": {channel: json_number(value) for channel, value in channel_paid_impressions.items()},
    }


def paid_impressions_total_from_breakdown(breakdown: dict[str, Any]) -> Decimal:
    total = Decimal("0")
    for value in breakdown.get("channel_paid_impressions", {}).values():
        parsed = to_decimal(value)
        if parsed is not None:
            total += parsed
    return total


def calculate_project_cpm(total_budget: Any, total_project_impressions: Decimal) -> Decimal | None:
    budget = to_decimal(total_budget)
    if budget is None or total_project_impressions <= 0:
        return None
    return budget / total_project_impressions


def generate_row_candidates(row: CanonicalProfileRow, allowed_tiers: tuple[int, ...] = VALID_PROFILE_TIERS) -> list[RowCandidate]:
    candidates: list[RowCandidate] = []
    activations = row.activations if row.activations is not None else 1
    for profile_size in allowed_tiers:
        candidates.append(
            RowCandidate(
                row_index=row.row_index,
                profile_size_cell=row.profile_size_cell,
                previous_profile_size=row.current_profile_size,
                recommended_profile_size=profile_size,
                channel=row.channel,
                market=row.market,
                cpm=row.cpm,
                activations=activations,
                impressions=calculate_candidate_row_impressions(profile_size, row.channel),
                row_fee=calculate_candidate_row_fee(profile_size, row.channel, row.cpm, activations),
            )
        )
    return candidates


def initialize_search_state() -> SearchState:
    return SearchState(
        next_row_index=0,
        profile_fee_sum=Decimal("0"),
        total_impressions=Decimal("0"),
        tier_counts={tier: 0 for tier in VALID_PROFILE_TIERS},
        impressions_by_channel={},
        impressions_by_market={},
        assignments=[],
    )


def build_current_assignment_state(row_candidates: list[list[RowCandidate]], model: CanonicalCampaignModel) -> SearchState:
    state = initialize_search_state()
    for row, candidates in zip(model.profile_rows, row_candidates):
        match = next((candidate for candidate in candidates if candidate.recommended_profile_size == row.current_profile_size), None)
        if match is None:
            raise ValueError(
                f"Current workbook profile size {row.current_profile_size!r} for row {row.row_index} is not available in optimizer candidates."
            )
        state = extend_search_state(state, match)
    return state


def extend_search_state(state: SearchState, candidate: RowCandidate) -> SearchState:
    tier_counts = dict(state.tier_counts)
    tier_counts[candidate.recommended_profile_size] += 1

    impressions_by_channel = dict(state.impressions_by_channel)
    if candidate.channel:
        impressions_by_channel[candidate.channel] = impressions_by_channel.get(candidate.channel, Decimal("0")) + candidate.impressions

    impressions_by_market = dict(state.impressions_by_market)
    if candidate.market:
        impressions_by_market[candidate.market] = impressions_by_market.get(candidate.market, Decimal("0")) + candidate.impressions

    return SearchState(
        next_row_index=state.next_row_index + 1,
        profile_fee_sum=state.profile_fee_sum + candidate.row_fee,
        total_impressions=state.total_impressions + candidate.impressions,
        tier_counts=tier_counts,
        impressions_by_channel=impressions_by_channel,
        impressions_by_market=impressions_by_market,
        assignments=state.assignments + [candidate],
    )


def build_remaining_fee_bounds(row_candidates: list[list[RowCandidate]]) -> tuple[list[Decimal], list[Decimal]]:
    row_count = len(row_candidates)
    min_remaining = [Decimal("0")] * (row_count + 1)
    max_remaining = [Decimal("0")] * (row_count + 1)
    for row_index in range(row_count - 1, -1, -1):
        min_fee = min(candidate.row_fee for candidate in row_candidates[row_index])
        max_fee = max(candidate.row_fee for candidate in row_candidates[row_index])
        min_remaining[row_index] = min_remaining[row_index + 1] + min_fee
        max_remaining[row_index] = max_remaining[row_index + 1] + max_fee
    return min_remaining, max_remaining


def best_reachable_abs_diff(
    state: SearchState,
    target: Decimal,
    min_remaining: list[Decimal],
    max_remaining: list[Decimal],
) -> Decimal:
    min_possible_sum = state.profile_fee_sum + min_remaining[state.next_row_index]
    max_possible_sum = state.profile_fee_sum + max_remaining[state.next_row_index]
    if min_possible_sum <= target <= max_possible_sum:
        return Decimal("0")
    if target < min_possible_sum:
        return min_possible_sum - target
    return target - max_possible_sum


def non_negative_reachable(
    state: SearchState,
    target: Decimal,
    min_remaining: list[Decimal],
) -> bool:
    min_possible_sum = state.profile_fee_sum + min_remaining[state.next_row_index]
    return min_possible_sum <= target


def partial_state_score(
    state: SearchState,
    target: Decimal,
    min_remaining: list[Decimal],
    max_remaining: list[Decimal],
) -> tuple[Any, ...]:
    large_tier_count = state.tier_counts[125000] + state.tier_counts[175000]
    return (
        best_reachable_abs_diff(state, target, min_remaining, max_remaining),
        0 if non_negative_reachable(state, target, min_remaining) else 1,
        abs(target - state.profile_fee_sum),
        state.tier_counts[15000],
        -large_tier_count,
        -state.tier_counts[75000],
        -state.total_impressions,
        tuple(candidate.recommended_profile_size for candidate in state.assignments),
    )


def dedupe_state_signature(state: SearchState) -> tuple[Any, ...]:
    return (
        state.next_row_index,
        decimal_to_bucket(state.profile_fee_sum, PARTIAL_FEE_BUCKET_SIZE),
        decimal_to_bucket(state.total_impressions, PARTIAL_IMPRESSIONS_BUCKET_SIZE),
        tuple(state.tier_counts[tier] for tier in VALID_PROFILE_TIERS),
    )


def final_math_score(option: dict[str, Any]) -> tuple[Any, ...]:
    diff = to_decimal(option["optimized_diff"])
    abs_diff = abs(diff)
    if diff >= 0:
        return (abs_diff, 0, diff, -option["strategic_metrics"]["avg_profile_size"])
    return (abs_diff, 1, abs_diff, -option["strategic_metrics"]["avg_profile_size"])


def final_strategic_score(option: dict[str, Any]) -> tuple[Any, ...]:
    diff = to_decimal(option["optimized_diff"])
    tier_counts = option["tier_counts"]
    row_count = max(1, sum(int(value) for value in tier_counts.values()))
    max_tier_count = max(int(value) for value in tier_counts.values())
    non_zero_tiers = sum(1 for value in tier_counts.values() if int(value) > 0)
    return (
        max_tier_count,
        -non_zero_tiers,
        abs(diff),
        0 if diff >= 0 else 1,
        diff if diff >= 0 else abs(diff),
        row_count,
    )


def balance_score(option: dict[str, Any]) -> tuple[Any, ...]:
    tier_counts = option["tier_counts"]
    max_tier_count = max(tier_counts.values()) if tier_counts else 0
    non_zero_tiers = sum(1 for value in tier_counts.values() if value > 0)
    diff = to_decimal(option["optimized_diff"])
    return (
        max_tier_count,
        -non_zero_tiers,
        abs(diff),
        0 if diff >= 0 else 1,
    )


def strategic_notes_for_option(option: dict[str, Any]) -> list[str]:
    metrics = option["strategic_metrics"]
    tier_counts = option["tier_counts"]
    row_count = max(1, metrics["row_count"])
    max_tier_count = max(int(value) for value in tier_counts.values()) if tier_counts else 0
    non_zero_tiers = sum(1 for value in tier_counts.values() if int(value) > 0)
    notes: list[str] = []
    if non_zero_tiers >= 4:
        notes.append("Uses a broad mix of tiers.")
    if max_tier_count >= max(2, row_count // 2):
        notes.append("Concentrated tier mix.")
    if metrics["mid_tier_count"] <= max(1, row_count // 5):
        notes.append("Low mid-tier representation.")
    if (
        metrics["count_15k"] >= max(2, metrics["row_count"] // 3)
        and metrics["count_175k"] >= max(2, metrics["row_count"] // 6)
        and metrics["mid_tier_count"] <= max(1, metrics["row_count"] // 5)
    ):
        notes.append("Polarized mix: heavy use of smallest and largest tiers.")
    return notes


def build_option_from_assignment(
    model: CanonicalCampaignModel,
    state: SearchState,
    option_label: str,
    rank: int,
) -> dict[str, Any]:
    target = compute_profile_budget_target(model)
    optimized_diff = target - state.profile_fee_sum
    tier_counts = {str(tier): state.tier_counts[tier] for tier in VALID_PROFILE_TIERS}
    fill_instructions = []
    organic_impressions_total = Decimal("0")
    organic_impressions_by_channel: dict[str, Decimal] = {}
    for candidate in state.assignments:
        organic_impressions = calculate_thousands_rounded_impressions(candidate.recommended_profile_size, candidate.channel)
        if organic_impressions is not None:
            organic_impressions_total += organic_impressions
            if candidate.channel:
                organic_impressions_by_channel[candidate.channel] = (
                    organic_impressions_by_channel.get(candidate.channel, Decimal("0")) + organic_impressions
                )
        fill_instructions.append(
            {
                "profile_size_cell": candidate.profile_size_cell,
                "recommended_profile_size": candidate.recommended_profile_size,
                "previous_profile_size": candidate.previous_profile_size,
                "channel": candidate.channel,
                "market": candidate.market,
                "organic_impressions": json_number(organic_impressions),
                "cpm": candidate.cpm,
                "activations": candidate.activations,
                "row_fee": json_number(candidate.row_fee),
            }
        )
    paid_breakdown = calculate_paid_amplification_breakdown(
        paid_media_included=model.paid_media_included is True,
        paid_budget=model.paid_media,
        assignments=state.assignments,
    )
    paid_impressions_total = paid_impressions_total_from_breakdown(paid_breakdown)
    total_project_impressions = organic_impressions_total + paid_impressions_total
    project_cpm = calculate_project_cpm(model.budget, total_project_impressions)

    avg_profile_size = sum(candidate.recommended_profile_size for candidate in state.assignments) / max(1, len(state.assignments))
    strategic_metrics = {
        "row_count": len(state.assignments),
        "count_15k": state.tier_counts[15000],
        "count_75k_plus": state.tier_counts[75000] + state.tier_counts[125000] + state.tier_counts[175000],
        "count_125k_plus": state.tier_counts[125000] + state.tier_counts[175000],
        "count_175k": state.tier_counts[175000],
        "mid_tier_count": state.tier_counts[35000] + state.tier_counts[75000] + state.tier_counts[125000],
        "avg_profile_size": avg_profile_size,
    }
    option = {
        "option_label": option_label,
        "rank": rank,
        "optimized_diff": json_number(optimized_diff),
        "profile_fee_sum": json_number(state.profile_fee_sum),
        "profile_budget_target": json_number(target),
        "tier_counts": tier_counts,
        "total_impressions": json_number(state.total_impressions),
        "impressions_by_channel": {channel: json_number(value) for channel, value in sorted(state.impressions_by_channel.items())},
        "impressions_by_market": {market: json_number(value) for market, value in sorted(state.impressions_by_market.items())},
        "organic_impressions_total": json_number(organic_impressions_total),
        "organic_impressions_by_channel": {
            channel: json_number(value) for channel, value in sorted(organic_impressions_by_channel.items())
        },
        "paid_impressions_total": json_number(paid_impressions_total),
        "total_project_impressions": json_number(total_project_impressions),
        "project_cpm": json_number(project_cpm),
        "paid_amplification_breakdown": paid_breakdown,
        "fill_instructions": fill_instructions,
        "diagnostics": {
            "non_negative_diff": optimized_diff >= 0,
            "abs_diff": json_number(abs(optimized_diff)),
            "strategic_notes": [],
        },
        "strategic_metrics": strategic_metrics,
        "assignment_signature": assignment_signature_from_assignments(state.assignments),
    }
    option["diagnostics"]["strategic_notes"] = strategic_notes_for_option(option)
    return option


def sort_options_for_math(options: list[dict[str, Any]], allow_negative: bool) -> list[dict[str, Any]]:
    if not allow_negative:
        non_negative = [option for option in options if to_decimal(option["optimized_diff"]) >= 0]
        if non_negative:
            options = non_negative
    return sorted(options, key=final_math_score)


def sort_options_for_strategy(options: list[dict[str, Any]], allow_negative: bool) -> list[dict[str, Any]]:
    math_sorted = sort_options_for_math(options, allow_negative)
    if not math_sorted:
        return []
    best_abs_diff = abs(to_decimal(math_sorted[0]["optimized_diff"]))

    def strategic_key(option: dict[str, Any]) -> tuple[Any, ...]:
        abs_diff = abs(to_decimal(option["optimized_diff"]))
        return (
            0 if abs_diff <= best_abs_diff + STRATEGIC_ABS_DIFF_TOLERANCE else 1,
            *final_strategic_score(option),
        )

    return sorted(math_sorted, key=strategic_key)


def pick_distinct_option(
    options: list[dict[str, Any]],
    used_signatures: set[tuple[Any, ...]],
    predicate=None,
) -> dict[str, Any] | None:
    for option in options:
        signature = option["assignment_signature"]
        if signature in used_signatures:
            continue
        if predicate and not predicate(option):
            continue
        used_signatures.add(signature)
        return option
    return None


def group_recommended_options(
    options: list[dict[str, Any]],
    baseline_option: dict[str, Any] | None,
    top_n: int,
    allow_negative: bool,
    strategy: str,
) -> list[dict[str, Any]]:
    if not options:
        return [baseline_option] if baseline_option is not None else []

    math_sorted = sort_options_for_math(options, allow_negative)
    strategic_sorted = sort_options_for_strategy(options, allow_negative)
    used_signatures: set[tuple[Any, ...]] = set()
    grouped: list[dict[str, Any]] = []

    primary_label = "best_strategic_fit" if strategy == "strategic" else "best_mathematical_fit"
    primary_list = strategic_sorted if strategy == "strategic" else math_sorted
    primary = pick_distinct_option(primary_list, used_signatures)
    if primary is not None:
        primary["option_label"] = primary_label
        grouped.append(primary)

    secondary_label = "best_mathematical_fit" if strategy == "strategic" else "best_strategic_fit"
    secondary_list = math_sorted if strategy == "strategic" else strategic_sorted
    secondary = pick_distinct_option(secondary_list, used_signatures)
    if secondary is not None:
        secondary["option_label"] = secondary_label
        grouped.append(secondary)

    closest_positive = next(
        (option for option in math_sorted if option.get("diagnostics", {}).get("non_negative_diff") is True),
        None,
    )
    if closest_positive is not None:
        closest_signature = closest_positive["assignment_signature"]
        existing_index = next(
            (index for index, option in enumerate(grouped) if option["assignment_signature"] == closest_signature),
            None,
        )
        if existing_index is not None:
            if grouped[existing_index]["option_label"] != "best_mathematical_fit":
                grouped[existing_index]["option_label"] = "closest_positive_diff"
        elif closest_signature not in used_signatures:
            used_signatures.add(closest_signature)
            closest_positive["option_label"] = "closest_positive_diff"
            grouped.append(closest_positive)

    best_math = next((option for option in grouped if option["option_label"] == "best_mathematical_fit"), None)
    larger_profile_alternative = pick_distinct_option(
        strategic_sorted,
        used_signatures,
        predicate=(
            None
            if best_math is None
            else lambda option: (
                max(int(value) for value in option["tier_counts"].values())
                < max(int(value) for value in best_math["tier_counts"].values())
            )
            or (
                sum(1 for value in option["tier_counts"].values() if int(value) > 0)
                > sum(1 for value in best_math["tier_counts"].values() if int(value) > 0)
            )
        ),
    )
    if larger_profile_alternative is not None:
        larger_profile_alternative["option_label"] = "larger_profile_alternative"
        grouped.append(larger_profile_alternative)

    balanced_candidate = pick_distinct_option(
        sorted(math_sorted, key=balance_score),
        used_signatures,
    )
    if balanced_candidate is not None:
        balanced_candidate["option_label"] = "balanced_option"
        grouped.append(balanced_candidate)

    fallback_candidate = pick_distinct_option(math_sorted, used_signatures)
    if fallback_candidate is not None:
        fallback_candidate["option_label"] = "fallback_option"
        grouped.append(fallback_candidate)

    best_math = next((option for option in grouped if option["option_label"] == "best_mathematical_fit"), None)
    larger_profile_alternative = next((option for option in grouped if option["option_label"] == "larger_profile_alternative"), None)
    if best_math is not None and larger_profile_alternative is not None:
        best_math_abs_diff = to_decimal(best_math["diagnostics"]["abs_diff"])
        larger_abs_diff = to_decimal(larger_profile_alternative["diagnostics"]["abs_diff"])
        if larger_abs_diff > best_math_abs_diff + STRATEGIC_ABS_DIFF_TOLERANCE:
            larger_profile_alternative["diagnostics"]["strategic_notes"].append(
                "Larger-profile alternative is mathematically much worse than the best mathematical fit."
            )

    limited_grouped = grouped[: max(1, top_n)]
    if baseline_option is not None:
        baseline_copy = dict(baseline_option)
        baseline_copy["option_label"] = "current_workbook_mix"
        limited_grouped.append(baseline_copy)
    return limited_grouped


def search_best_assignments(
    model: CanonicalCampaignModel,
    beam_width: int = DEFAULT_BEAM_WIDTH,
    top_n: int = DEFAULT_TOP_N,
    allow_negative: bool = False,
    strategy: str = "math",
    baseline_enabled: bool = True,
    allowed_tiers: list[int] | tuple[int, ...] | None = None,
    optimization_method: str = "fast_closest_diff",
    max_exact_states: int = DEFAULT_EXACT_MAX_STATES,
) -> dict[str, Any]:
    normalized_allowed_tiers = normalize_allowed_tiers(allowed_tiers)
    if optimization_method not in OPTIMIZATION_METHODS:
        raise ValueError(f"Unsupported optimization_method {optimization_method!r}. Expected one of {OPTIMIZATION_METHODS}.")
    row_candidates = [generate_row_candidates(row, allowed_tiers=normalized_allowed_tiers) for row in model.profile_rows]
    target = compute_profile_budget_target(model)
    min_remaining, max_remaining = build_remaining_fee_bounds(row_candidates)
    baseline_full_state = build_current_assignment_state(row_candidates, model) if baseline_enabled else None
    baseline_prefix_state = initialize_search_state() if baseline_enabled else None

    if optimization_method == "exact_closest_diff":
        states_by_fee: dict[Decimal, SearchState] = {Decimal("0"): initialize_search_state()}
        stats = {
            "row_count": len(row_candidates),
            "candidate_count_per_row": [len(candidates) for candidates in row_candidates],
            "max_frontier_before_prune": 1,
            "max_frontier_after_prune": 1,
            "expanded_state_count": 0,
            "retained_state_count": 1,
            "beam_width": None,
            "search_method": "exact_fee_sum_search",
            "bounded_search": False,
            "approximate_search": False,
            "global_optimality_guaranteed": True,
            "allowed_tiers": [int(tier) for tier in normalized_allowed_tiers],
            "current_baseline_available": baseline_enabled,
            "current_baseline_included": baseline_enabled,
            "current_baseline_profile_fee_sum": json_number(baseline_full_state.profile_fee_sum) if baseline_full_state else None,
            "current_baseline_diff": json_number(target - baseline_full_state.profile_fee_sum) if baseline_full_state else None,
            "current_baseline_retained_by_protection": baseline_enabled,
            "current_baseline_would_have_been_pruned_by_deduplication": False,
            "current_baseline_would_have_been_pruned_by_beam_limit": False,
            "exact_state_limit": int(max_exact_states),
            "exact_state_count": 1,
        }
        for candidates in row_candidates:
            next_states_by_fee: dict[Decimal, SearchState] = {}
            for state in states_by_fee.values():
                for candidate in candidates:
                    next_state = extend_search_state(state, candidate)
                    stats["expanded_state_count"] += 1
                    fee_key = next_state.profile_fee_sum
                    incumbent = next_states_by_fee.get(fee_key)
                    if incumbent is None or partial_state_score(next_state, target, min_remaining, max_remaining) < partial_state_score(
                        incumbent,
                        target,
                        min_remaining,
                        max_remaining,
                    ):
                        next_states_by_fee[fee_key] = next_state
            state_count = len(next_states_by_fee)
            stats["exact_state_count"] = state_count
            stats["max_frontier_before_prune"] = max(stats["max_frontier_before_prune"], state_count)
            stats["max_frontier_after_prune"] = max(stats["max_frontier_after_prune"], state_count)
            if state_count > max_exact_states:
                raise ExactSearchStateLimitError(
                    f"Exact search exceeded safe state limit ({state_count} > {max_exact_states}). Use Fast closest diff or reduce rows/tiers."
                )
            states_by_fee = next_states_by_fee
            stats["retained_state_count"] = len(states_by_fee)

        ranked_final_states = sorted(
            states_by_fee.values(),
            key=lambda state: partial_state_score(state, target, min_remaining, max_remaining),
        )
        if baseline_enabled and baseline_full_state is not None:
            baseline_final_signature = assignment_signature_from_assignments(baseline_full_state.assignments)
            if not any(assignment_signature_from_assignments(state.assignments) == baseline_final_signature for state in ranked_final_states):
                ranked_final_states.append(baseline_full_state)
                ranked_final_states = sorted(
                    ranked_final_states,
                    key=lambda state: partial_state_score(state, target, min_remaining, max_remaining),
                )
    else:
        beam: list[SearchState] = [initialize_search_state()]
        stats = {
            "row_count": len(row_candidates),
            "candidate_count_per_row": [len(candidates) for candidates in row_candidates],
            "max_frontier_before_prune": 1,
            "max_frontier_after_prune": 1,
            "expanded_state_count": 0,
            "retained_state_count": 1,
            "beam_width": beam_width,
            "search_method": "bounded_beam_search",
            "bounded_search": True,
            "approximate_search": True,
            "global_optimality_guaranteed": False,
            "allowed_tiers": [int(tier) for tier in normalized_allowed_tiers],
            "current_baseline_available": baseline_enabled,
            "current_baseline_included": baseline_enabled,
            "current_baseline_profile_fee_sum": json_number(baseline_full_state.profile_fee_sum) if baseline_full_state else None,
            "current_baseline_diff": json_number(target - baseline_full_state.profile_fee_sum) if baseline_full_state else None,
            "current_baseline_retained_by_protection": baseline_enabled,
            "current_baseline_would_have_been_pruned_by_deduplication": False,
            "current_baseline_would_have_been_pruned_by_beam_limit": False,
        }

        for row_index, candidates in enumerate(row_candidates):
            expanded_states: list[SearchState] = []
            for state in beam:
                for candidate in candidates:
                    expanded_states.append(extend_search_state(state, candidate))
            stats["expanded_state_count"] += len(expanded_states)
            stats["max_frontier_before_prune"] = max(stats["max_frontier_before_prune"], len(expanded_states))
            baseline_signature = None
            if baseline_enabled and baseline_prefix_state is not None:
                baseline_prefix_state = extend_search_state(
                    baseline_prefix_state,
                    next(
                        candidate
                        for candidate in candidates
                        if candidate.recommended_profile_size == model.profile_rows[row_index].current_profile_size
                    ),
                )
                baseline_signature = assignment_signature_from_assignments(baseline_prefix_state.assignments)

            deduped: dict[tuple[Any, ...], SearchState] = {}
            for state in expanded_states:
                signature = dedupe_state_signature(state)
                incumbent = deduped.get(signature)
                if incumbent is None or partial_state_score(state, target, min_remaining, max_remaining) < partial_state_score(
                    incumbent,
                    target,
                    min_remaining,
                    max_remaining,
                ):
                    deduped[signature] = state

            deduped_states = list(deduped.values())
            baseline_present_after_deduplication = True
            if baseline_enabled and baseline_signature is not None:
                baseline_present_after_deduplication = any(
                    assignment_signature_from_assignments(state.assignments) == baseline_signature for state in deduped_states
                )
                if not baseline_present_after_deduplication:
                    stats["current_baseline_would_have_been_pruned_by_deduplication"] = True
            sorted_deduped_states = sorted(
                deduped_states,
                key=lambda state: partial_state_score(state, target, min_remaining, max_remaining),
            )
            tentative_beam = sorted_deduped_states[:beam_width]
            baseline_present_after_beam_limit = True
            if baseline_enabled and baseline_signature is not None:
                baseline_present_after_beam_limit = any(
                    assignment_signature_from_assignments(state.assignments) == baseline_signature for state in tentative_beam
                )
                if not baseline_present_after_beam_limit:
                    stats["current_baseline_would_have_been_pruned_by_beam_limit"] = True

            beam = tentative_beam
            if baseline_enabled and baseline_prefix_state is not None and not baseline_present_after_beam_limit:
                if len(beam) >= beam_width and beam:
                    beam = beam[:-1]
                beam.append(baseline_prefix_state)
                beam = sorted(
                    beam,
                    key=lambda state: partial_state_score(state, target, min_remaining, max_remaining),
                )
            stats["retained_state_count"] = len(beam)
            stats["max_frontier_after_prune"] = max(stats["max_frontier_after_prune"], len(beam))

            if row_index == len(row_candidates) - 1:
                break

        ranked_final_states = sorted(beam, key=lambda state: partial_state_score(state, target, min_remaining, max_remaining))
        if baseline_enabled and baseline_full_state is not None:
            baseline_final_signature = assignment_signature_from_assignments(baseline_full_state.assignments)
            if not any(assignment_signature_from_assignments(state.assignments) == baseline_final_signature for state in ranked_final_states):
                ranked_final_states.append(baseline_full_state)
                ranked_final_states = sorted(
                    ranked_final_states,
                    key=lambda state: partial_state_score(state, target, min_remaining, max_remaining),
                )

    ranked_options = [
        build_option_from_assignment(model, state, option_label="candidate", rank=index + 1)
        for index, state in enumerate(ranked_final_states)
    ]
    baseline_option = (
        build_option_from_assignment(model, baseline_full_state, option_label="current_workbook_mix", rank=0)
        if baseline_enabled and baseline_full_state is not None
        else None
    )
    grouped_options = group_recommended_options(
        ranked_options + ([baseline_option] if baseline_option is not None else []),
        baseline_option=baseline_option,
        top_n=top_n,
        allow_negative=allow_negative,
        strategy=strategy,
    )
    best_math_option = next((option for option in grouped_options if option["option_label"] == "best_mathematical_fit"), None)
    if best_math_option is not None and baseline_option is not None:
        baseline_comparison = compare_against_baseline(
            best_math_option["optimized_diff"],
            baseline_option["optimized_diff"],
        )
    elif baseline_option is None:
        baseline_comparison = "unavailable"
    else:
        baseline_comparison = "worse"
    stats["best_mathematical_fit_baseline_comparison"] = baseline_comparison
    stats["best_mathematical_fit_improves_on_current_baseline"] = baseline_comparison == "improves"
    stats["best_mathematical_fit_equals_current_baseline"] = baseline_comparison == "equals"
    return {
        "options": grouped_options,
        "search_diagnostics": stats,
    }


def build_option_main_note(option: dict[str, Any]) -> str:
    if option.get("strategic_warnings"):
        return option["strategic_warnings"][0]
    if option.get("strategic_notes"):
        return option["strategic_notes"][0]
    return "No notable distribution risk flags."


def _budget_guidance_for_option(
    budget: Any,
    optimization_focus: str | None,
    count_75k: int,
    count_125k: int,
    count_175k: int,
) -> tuple[list[str], list[str]]:
    budget_decimal = to_decimal(budget)
    if budget_decimal is None or budget_decimal != budget_decimal.to_integral_value():
        return [], []
    guidance = SIMPLIFIED_BUDGET_PROFILE_GUIDANCE.get(int(budget_decimal))
    if guidance is None:
        return [], []
    if int(budget_decimal) == 100000 and optimization_focus == "Larger profile sizes":
        guidance = {**guidance, "recommended_max_tier": 175000}

    warnings: list[str] = []
    notes: list[str] = []
    budget_label = f"{int(budget_decimal / Decimal('1000'))}K budget"
    recommended_max_tier = int(guidance["recommended_max_tier"])

    above_recommended_max = 0
    if recommended_max_tier < 75000:
        above_recommended_max += count_75k
    if recommended_max_tier < 125000:
        above_recommended_max += count_125k
    if recommended_max_tier < 175000:
        above_recommended_max += count_175k

    if above_recommended_max:
        warnings.append(
            f"{budget_label}: profile sizes above {int(recommended_max_tier / 1000)}K are outside the recommended max for this preset."
        )

    anchor_count = count_125k + count_175k
    anchor_tier_limit = guidance["anchor_tier_limit"]
    if anchor_tier_limit == 1 and anchor_count == 1:
        notes.append("250K budget: one 125K+ anchor profile is borderline; keep the rest of the mix efficient.")
    elif anchor_tier_limit is not None and anchor_count > int(anchor_tier_limit):
        warnings.append(f"{budget_label}: use at most {int(anchor_tier_limit)} profile at 125K or larger.")

    return warnings, notes


def analyze_option_strategy(
    option: dict[str, Any],
    baseline_option: dict[str, Any] | None,
    row_count: int,
    best_mathematical_label: str,
    budget: Any = None,
    optimization_focus: str | None = None,
) -> dict[str, Any]:
    tier_counts = option["tier_counts"]
    count_15k = int(tier_counts.get("15000", 0))
    count_35k = int(tier_counts.get("35000", 0))
    count_75k = int(tier_counts.get("75000", 0))
    count_125k = int(tier_counts.get("125000", 0))
    count_175k = int(tier_counts.get("175000", 0))
    count_75k_plus = count_75k + count_125k + count_175k
    max_tier_count = max(count_15k, count_35k, count_75k, count_125k, count_175k)
    non_zero_tier_count = sum(1 for value in (count_15k, count_35k, count_75k, count_125k, count_175k) if value > 0)
    mid_tier_count = count_35k + count_75k + count_125k
    share_15k = Decimal(count_15k) / Decimal(max(1, row_count))
    concentrated_tier_mix = max_tier_count >= max(2, row_count // 2)
    polarized_mix = (
        count_15k >= max(2, row_count // 3)
        and count_175k >= max(2, row_count // 6)
        and mid_tier_count <= max(1, row_count // 5)
    )
    low_mid_tier_representation = mid_tier_count <= max(1, row_count // 5)
    balanced_mid_tiers = mid_tier_count >= max(2, row_count // 2) and not polarized_mix
    broad_tier_mix = non_zero_tier_count >= 4 and not concentrated_tier_mix

    strategic_notes = list(option.get("diagnostics", {}).get("strategic_notes", []))
    strategic_warnings: list[str] = []
    if concentrated_tier_mix:
        strategic_warnings.append("Highly concentrated tier mix")
    if polarized_mix:
        strategic_warnings.append("Polarized mix: heavy use of smallest and largest tiers")
    if low_mid_tier_representation:
        strategic_warnings.append("Low mid-tier representation")
    budget_guidance_warnings, budget_guidance_notes = _budget_guidance_for_option(
        budget=budget,
        optimization_focus=optimization_focus,
        count_75k=count_75k,
        count_125k=count_125k,
        count_175k=count_175k,
    )
    strategic_warnings.extend(budget_guidance_warnings)
    for note in budget_guidance_notes:
        if note not in strategic_notes:
            strategic_notes.append(note)
    if balanced_mid_tiers and "Balanced tier distribution." not in strategic_notes:
        strategic_notes.append("Balanced tier distribution.")
    if broad_tier_mix and "Uses a broad mix of tiers." not in strategic_notes:
        strategic_notes.append("Uses a broad mix of tiers.")
    if option["option_label"] == best_mathematical_label and strategic_warnings:
        strategic_notes.append("Closest mathematical fit, but distribution has risk flags.")

    if baseline_option is None:
        baseline_comparison = "unavailable"
    else:
        baseline_comparison = compare_against_baseline(option["optimized_diff"], baseline_option["optimized_diff"])
    option["baseline_comparison"] = baseline_comparison
    option["improves_on_baseline"] = baseline_comparison == "improves" if baseline_option is not None else None
    option["count_15k"] = count_15k
    option["count_75k_plus"] = count_75k_plus
    option["mid_tier_count"] = mid_tier_count
    option["share_15k"] = to_float(share_15k)
    option["high_15k_share"] = False
    option["very_high_15k_share"] = False
    option["polarized_mix"] = polarized_mix
    option["concentrated_tier_mix"] = concentrated_tier_mix
    option["low_mid_tier_representation"] = low_mid_tier_representation
    option["balanced_mid_tiers"] = balanced_mid_tiers
    option["budget_guidance_warning_count"] = len(budget_guidance_warnings)
    option["strategic_notes"] = strategic_notes
    option["strategic_warnings"] = strategic_warnings
    option["strategic_warning_count"] = len(strategic_warnings)
    option["main_note"] = build_option_main_note(option)
    return option


def compute_recommendation_score(option: dict[str, Any]) -> dict[str, Any]:
    abs_diff = abs(to_float(option["optimized_diff"]))
    row_count = max(1, option.get("count_15k", 0) + int(option["tier_counts"].get("35000", 0)) + int(option["tier_counts"].get("75000", 0)) + int(option["tier_counts"].get("125000", 0)) + int(option["tier_counts"].get("175000", 0)))
    non_zero_tier_count = sum(1 for value in option["tier_counts"].values() if int(value) > 0)
    math_fit_score = max(0.0, 100000.0 - abs_diff)
    non_negative_bonus = 5000.0 if option["diagnostics"]["non_negative_diff"] else 0.0
    baseline_improvement_bonus = 3000.0 if option["baseline_comparison"] == "improves" else (1000.0 if option["baseline_comparison"] == "equals" else 0.0)
    small_tier_penalty = 0.0
    concentration_penalty = -1800.0 if option.get("concentrated_tier_mix") else 0.0
    polarization_penalty = -2500.0 if option["polarized_mix"] else 0.0
    budget_guidance_penalty = -3500.0 * int(option.get("budget_guidance_warning_count", 0))
    mid_tier_balance_bonus = 1200.0 if option["balanced_mid_tiers"] else 0.0
    broad_tier_mix_bonus = 900.0 if non_zero_tier_count >= 4 else 0.0
    large_profile_bonus = 0.0
    total_score = (
        math_fit_score
        + non_negative_bonus
        + baseline_improvement_bonus
        + small_tier_penalty
        + concentration_penalty
        + polarization_penalty
        + budget_guidance_penalty
        + mid_tier_balance_bonus
        + broad_tier_mix_bonus
        + large_profile_bonus
    )
    return {
        "math_fit_score": round(math_fit_score, 3),
        "non_negative_bonus": round(non_negative_bonus, 3),
        "baseline_improvement_bonus": round(baseline_improvement_bonus, 3),
        "small_tier_penalty": round(small_tier_penalty, 3),
        "concentration_penalty": round(concentration_penalty, 3),
        "polarization_penalty": round(polarization_penalty, 3),
        "budget_guidance_penalty": round(budget_guidance_penalty, 3),
        "mid_tier_balance_bonus": round(mid_tier_balance_bonus, 3),
        "broad_tier_mix_bonus": round(broad_tier_mix_bonus, 3),
        "large_profile_bonus": round(large_profile_bonus, 3),
        "total_score": round(total_score, 3),
    }


def recommendation_sort_key(option: dict[str, Any]) -> tuple[Any, ...]:
    score = option["recommendation_score_breakdown"]
    return (
        -score["total_score"],
        abs(to_decimal(option["optimized_diff"])),
        0 if option["diagnostics"]["non_negative_diff"] else 1,
        option["option_label"],
    )


def select_recommended_option(options: list[dict[str, Any]]) -> tuple[str, str]:
    if not options:
        raise ValueError("Cannot select a recommended option from an empty option list.")
    recommendable = [option for option in options if is_option_diff_recommendable(option)]
    if recommendable:
        non_negative = [option for option in recommendable if option["diagnostics"]["non_negative_diff"]]
        candidates = non_negative if non_negative else recommendable
    else:
        non_negative = [option for option in options if option["diagnostics"]["non_negative_diff"]]
        candidates = non_negative if non_negative else options
    sorted_candidates = sorted(candidates, key=recommendation_sort_key)
    recommended = sorted_candidates[0]
    best_math = next((option for option in options if option["option_label"] == "best_mathematical_fit"), None)
    if not recommendable:
        reason = "No option was within the positive-diff recommendation threshold; selected deterministic fallback."
    elif best_math and recommended["option_label"] != "best_mathematical_fit":
        reason = "Recommended as best balance between diff fit and distribution."
    elif recommended["strategic_warning_count"] > 0:
        reason = "Closest mathematical fit."
    else:
        reason = "Closest mathematical fit."
    return recommended["option_label"], reason


def rank_options_for_presentation(options: list[dict[str, Any]], recommended_label: str) -> list[dict[str, Any]]:
    ranked = sorted(options, key=recommendation_sort_key)
    for index, option in enumerate(ranked, start=1):
        option["recommendation_rank"] = index
        option["is_recommended"] = option["option_label"] == recommended_label
    ranked.sort(
        key=lambda option: (
            0 if option["option_label"] == recommended_label else 1,
            option["recommendation_rank"],
        )
    )
    return ranked


def build_option_comparison(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for option in options:
        rows.append(
            {
                "option_label": option["option_label"],
                "recommendation_rank": option["recommendation_rank"],
                "optimized_diff": option["optimized_diff"],
                "profile_fee_sum": option["profile_fee_sum"],
                "tier_counts": option["tier_counts"],
                "count_15k": option["count_15k"],
                "count_75k_plus": option["count_75k_plus"],
                "total_impressions": option["total_impressions"],
                "organic_impressions_total": option.get("organic_impressions_total"),
                "paid_impressions_total": option.get("paid_impressions_total"),
                "total_project_impressions": option.get("total_project_impressions"),
                "project_cpm": option.get("project_cpm"),
                "strategic_warning_count": option["strategic_warning_count"],
                "improves_on_baseline": option["improves_on_baseline"],
                "main_note": option["main_note"],
            }
        )
    return rows


def build_executive_summary_entry(result: dict[str, Any]) -> dict[str, Any]:
    recommended = next(option for option in result["options"] if option["option_label"] == result["recommended_option_label"])
    baseline = next((option for option in result["options"] if option["option_label"] == "current_workbook_mix"), None)
    baseline_abs = abs(to_decimal(baseline["optimized_diff"])) if baseline is not None else None
    recommended_abs = abs(to_decimal(recommended["optimized_diff"]))
    return {
        "workbook_name": result["source"]["workbook_name"],
        "sheet_name": result["source"]["sheet_name"],
        "recommended_option_label": result["recommended_option_label"],
        "recommended_diff": recommended["optimized_diff"],
        "baseline_diff": baseline["optimized_diff"] if baseline is not None else None,
        "improvement_vs_baseline": json_number(baseline_abs - recommended_abs) if baseline_abs is not None else None,
        "main_note": result["recommendation_reason"],
    }


def optimize_model(
    model: CanonicalCampaignModel,
    beam_width: int = DEFAULT_BEAM_WIDTH,
    top_n: int = DEFAULT_TOP_N,
    allow_negative: bool = False,
    strategy: str = "math",
    allowed_tiers: list[int] | tuple[int, ...] | None = None,
    optimization_method: str = "fast_closest_diff",
    max_exact_states: int = DEFAULT_EXACT_MAX_STATES,
    optimization_focus: str | None = None,
) -> dict[str, Any]:
    warnings = list(model.warnings)
    normalized_allowed_tiers = normalize_allowed_tiers(allowed_tiers)
    baseline_available = True
    for row in model.profile_rows:
        if row.channel is None or row.cpm is None:
            raise ValueError(f"Row {row.row_index} is missing required optimization fields.")
        if row.current_profile_size not in normalized_allowed_tiers:
            baseline_available = False

    search_payload = search_best_assignments(
        model,
        beam_width=beam_width,
        top_n=top_n,
        allow_negative=allow_negative,
        strategy=strategy,
        baseline_enabled=baseline_available,
        allowed_tiers=normalized_allowed_tiers,
        optimization_method=optimization_method,
        max_exact_states=max_exact_states,
    )

    if len(search_payload["options"]) < 2:
        if optimization_method == "exact_closest_diff":
            warnings.append("Fewer than two meaningfully distinct optimizer options were retained after exact search.")
        else:
            warnings.append("Fewer than two meaningfully distinct optimizer options were retained after bounded search.")
    if not baseline_available:
        warnings.append("Baseline unavailable because one or more current profile sizes were blank, invalid, or excluded by allowed profile sizes.")
    options = [strip_internal_option_fields(option) for option in search_payload["options"]]
    baseline_option = next((option for option in options if option["option_label"] == "current_workbook_mix"), None)
    best_math_label = "best_mathematical_fit"
    analyzed_options = [
        analyze_option_strategy(
            option,
            baseline_option,
            len(model.profile_rows),
            best_math_label,
            budget=model.budget,
            optimization_focus=optimization_focus,
        )
        for option in options
    ]
    for option in analyzed_options:
        option["recommendation_score_breakdown"] = compute_recommendation_score(option)

    recommended_label, recommendation_reason = select_recommended_option(analyzed_options)
    ranked_options = rank_options_for_presentation(analyzed_options, recommended_label)
    recommended_option = next(option for option in ranked_options if option["option_label"] == recommended_label)
    if recommended_label != "best_mathematical_fit":
        recommended_option["strategic_notes"].append("Recommended as best balance between diff fit and distribution.")

    if baseline_option is not None:
        baseline_diff = baseline_option["optimized_diff"]
        improvement_vs_baseline = json_number(
            abs(to_decimal(baseline_option["optimized_diff"])) - abs(to_decimal(recommended_option["optimized_diff"]))
        )
    else:
        baseline_diff = None
        improvement_vs_baseline = None

    executive_summary = {
        "recommended_diff": recommended_option["optimized_diff"],
        "baseline_diff": baseline_diff,
        "improvement_vs_baseline": improvement_vs_baseline,
        "main_note": recommendation_reason,
    }
    non_negative_options = [option for option in ranked_options if option.get("diagnostics", {}).get("non_negative_diff") is True]
    if non_negative_options:
        closest_positive_option = min(non_negative_options, key=lambda option: abs(to_decimal(option["optimized_diff"])))
        closest_positive_label = str(closest_positive_option.get("option_label"))
        closest_positive_value = closest_positive_option.get("optimized_diff")
    else:
        closest_positive_label = None
        closest_positive_value = None
    return {
        "source": {
            "workbook_name": model.source.workbook_name,
            "sheet_name": model.source.sheet_name,
        },
        "profile_budget_target": json_number(compute_profile_budget_target(model)),
        "budget_breakdown": build_budget_breakdown(model),
        "row_count": len(model.profile_rows),
        "recommended_option_label": recommended_label,
        "recommendation_reason": recommendation_reason,
        "recommendation_score_breakdown": recommended_option["recommendation_score_breakdown"],
        "executive_summary": executive_summary,
        "closest_positive_diff_option_label": closest_positive_label,
        "closest_positive_diff_value": closest_positive_value,
        "options": ranked_options,
        "option_comparison": build_option_comparison(ranked_options),
        "warnings": warnings,
        "search_diagnostics": search_payload["search_diagnostics"],
    }


def strip_internal_option_fields(option: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in option.items()
        if key not in {"assignment_signature"}
    }


def build_optimizer_payload(
    input_path: Path,
    models: list[CanonicalCampaignModel],
    beam_width: int = DEFAULT_BEAM_WIDTH,
    top_n: int = DEFAULT_TOP_N,
    allow_negative: bool = False,
    strategy: str = "math",
    allowed_tiers: list[int] | tuple[int, ...] | None = None,
    optimization_method: str = "fast_closest_diff",
    max_exact_states: int = DEFAULT_EXACT_MAX_STATES,
    optimization_focus: str | None = None,
) -> dict[str, Any]:
    normalized_allowed_tiers = normalize_allowed_tiers(allowed_tiers)
    selected_formula = choose_selected_row_fee_formula(models) if models else SELECTED_ROW_FEE_FORMULA
    results = [
        optimize_model(
            model,
            beam_width=beam_width,
            top_n=top_n,
            allow_negative=allow_negative,
            strategy=strategy,
            allowed_tiers=normalized_allowed_tiers,
            optimization_method=optimization_method,
            max_exact_states=max_exact_states,
            optimization_focus=optimization_focus,
        )
        for model in models
    ]

    payload_warnings: list[str] = []
    if selected_formula != SELECTED_ROW_FEE_FORMULA:
        payload_warnings.append(
            f"Validation-selected formula was {selected_formula!r}; optimizer still enforced {SELECTED_ROW_FEE_FORMULA!r}."
        )

    option_count = sum(len(result["options"]) for result in results)
    executive_summary = [build_executive_summary_entry(result) for result in results]
    search_name = "bounded_beam_search" if optimization_method == "fast_closest_diff" else "exact_fee_sum_search"
    search_bounded = optimization_method == "fast_closest_diff"
    search_approx = optimization_method == "fast_closest_diff"
    search_guaranteed = optimization_method == "exact_closest_diff"
    return {
        "input_file": str(input_path),
        "selected_formula": SELECTED_ROW_FEE_FORMULA,
        "search_method": {
            "name": search_name,
            "bounded": search_bounded,
            "approximate": search_approx,
            "global_optimality_guaranteed": search_guaranteed,
        },
        "optimization_method": optimization_method,
        "campaign_count": len(results),
        "options_generated": option_count,
        "strategy": strategy,
        "allow_negative": allow_negative,
        "beam_width": beam_width,
        "allowed_tiers": list(normalized_allowed_tiers),
        "max_exact_states": int(max_exact_states),
        "warnings": payload_warnings,
        "executive_summary": executive_summary,
        "results": results,
    }


def run_optimizer_for_models(
    models: list[CanonicalCampaignModel],
    input_label: str,
    beam_width: int = DEFAULT_BEAM_WIDTH,
    top_n: int = DEFAULT_TOP_N,
    allow_negative: bool = False,
    strategy: str = "math",
    allowed_tiers: list[int] | tuple[int, ...] | None = None,
    optimization_method: str = "fast_closest_diff",
    max_exact_states: int = DEFAULT_EXACT_MAX_STATES,
    optimization_focus: str | None = None,
) -> dict[str, Any]:
    return build_optimizer_payload(
        Path(input_label),
        models,
        beam_width=beam_width,
        top_n=top_n,
        allow_negative=allow_negative,
        strategy=strategy,
        allowed_tiers=allowed_tiers,
        optimization_method=optimization_method,
        max_exact_states=max_exact_states,
        optimization_focus=optimization_focus,
    )


def write_optimizer_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def render_optimizer_markdown(payload: dict[str, Any]) -> str:
    method = payload.get("search_method", {})
    method_name = method.get("name", "bounded_beam_search")
    method_bounded = method.get("bounded", True)
    method_approx = method.get("approximate", True)
    method_guaranteed = method.get("global_optimality_guaranteed", False)
    allowed_tiers_text = ", ".join(str(tier) for tier in payload.get("allowed_tiers", list(VALID_PROFILE_TIERS)))
    lines = [
        "# Optimizer Results",
        "",
        f"- Input file: `{payload['input_file']}`",
        f"- Selected formula: `{payload['selected_formula']}`",
        f"- Search method: {method_name}",
        f"- Search details: bounded={method_bounded}, approximate={method_approx}, global_optimality_guaranteed={method_guaranteed}",
        f"- Campaign count: {payload['campaign_count']}",
        f"- Options generated: {payload['options_generated']}",
        f"- Strategy: `{payload['strategy']}`",
        f"- Allow negative: `{payload['allow_negative']}`",
        f"- Beam width: {payload['beam_width']}",
        f"- Allowed profile sizes: {allowed_tiers_text}",
        f"- Warnings: {'; '.join(payload['warnings']) if payload['warnings'] else 'none'}",
        "",
        "## Executive Summary",
        "",
        "| Workbook | Sheet | Recommended Option | Recommended Diff | Baseline Diff | Improvement vs Baseline | Main Note |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for entry in payload.get("executive_summary", []):
        lines.append(
            "| {workbook} | {sheet} | {recommended} | {recommended_diff} | {baseline_diff} | {improvement} | {main_note} |".format(
                workbook=entry["workbook_name"],
                sheet=entry["sheet_name"],
                recommended=entry["recommended_option_label"],
                recommended_diff=format_money(entry["recommended_diff"]),
                baseline_diff=format_money(entry["baseline_diff"]),
                improvement=format_money(entry["improvement_vs_baseline"]),
                main_note=entry["main_note"],
            )
        )
    lines.append("")

    for result in payload["results"]:
        recommended_option = next(option for option in result["options"] if option["option_label"] == result["recommended_option_label"])
        strategic_warning_lines = []
        for option in result["options"]:
            for warning in option["strategic_warnings"]:
                strategic_warning_lines.append(f"{option['option_label']}: {warning}")
        if not strategic_warning_lines:
            strategic_warning_lines = ["none"]
        budget_breakdown = result.get("budget_breakdown", {})
        multiplier = budget_breakdown.get("profile_budget_target_multiplier")
        deduction_percent = None if multiplier is None else (1 - float(multiplier)) * 100

        lines.extend(
            [
                f"## Sheet: {result['source']['workbook_name']} / {result['source']['sheet_name']}",
                "",
                "### Recommendation",
                result["recommendation_reason"],
                "",
                "### Budget Breakdown",
                f"- Total budget: {format_money(budget_breakdown.get('budget'))}",
                f"- Agency fee: {format_money(budget_breakdown.get('agency_fee'))}",
                f"- Paid media: {format_money(budget_breakdown.get('paid_media'))}",
                f"- Paid media included in target: {'yes' if budget_breakdown.get('paid_media_included') is True else 'no'}",
                f"- Profile fee deduction / extra agency fee: {deduction_percent:.1f}%" if deduction_percent is not None else "- Profile fee deduction / extra agency fee: unavailable",
                f"- Available profile-fee target: {format_money(budget_breakdown.get('profile_budget_target'))}",
                f"- Recommended organic impressions (K): {format_zero_decimal_number(recommended_option.get('organic_impressions_total'))}",
                f"- Recommended paid impressions (K): {format_zero_decimal_number(recommended_option.get('paid_impressions_total'))}",
                f"- Recommended total project impressions (K): {format_zero_decimal_number(recommended_option.get('total_project_impressions'))}",
                f"- Recommended project CPM: {format_zero_decimal_number(recommended_option.get('project_cpm'))}",
                "",
                "### Option Comparison",
                "| Option | Rec Rank | Diff | Fee Sum | 15K Count | 75K+ Count | Organic Impressions (K) | Paid Impressions (K) | Total Project Impressions (K) | Project CPM | Warning Count | Improves Baseline | Main Note |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
            ]
        )
        for comparison in result["option_comparison"]:
            lines.extend(
                [
                    "| {option_label} | {rank} | {diff} | {fee_sum} | {count_15k} | {count_75k_plus} | {organic_impressions} | {paid_impressions} | {total_project_impressions} | {project_cpm} | {warning_count} | {improves} | {main_note} |".format(
                        option_label=comparison["option_label"],
                        rank=comparison["recommendation_rank"],
                        diff=format_money(comparison["optimized_diff"]),
                        fee_sum=format_money(comparison["profile_fee_sum"]),
                        count_15k=comparison["count_15k"],
                        count_75k_plus=comparison["count_75k_plus"],
                        organic_impressions=format_zero_decimal_number(comparison.get("organic_impressions_total")),
                        paid_impressions=format_zero_decimal_number(comparison.get("paid_impressions_total")),
                        total_project_impressions=format_zero_decimal_number(comparison.get("total_project_impressions")),
                        project_cpm=format_zero_decimal_number(comparison.get("project_cpm")),
                        warning_count=comparison["strategic_warning_count"],
                        improves=(
                            "yes"
                            if comparison["improves_on_baseline"] is True
                            else ("no" if comparison["improves_on_baseline"] is False else "unavailable")
                        ),
                        main_note=comparison["main_note"],
                    )
                ]
            )
        lines.extend(
            [
                "",
                "### Fill Instructions for Recommended Option",
                "| Cell | Previous Size | Recommended Size | Channel | Market | Organic Impressions (K) | CPM | Activations | Row Fee |",
                "|---|---:|---:|---|---|---:|---:|---:|---:|",
            ]
        )
        for instruction in recommended_option["fill_instructions"]:
            lines.append(
                "| {cell} | {previous_size} | {recommended_size} | {channel} | {market} | {organic_impressions} | {cpm} | {activations} | {row_fee} |".format(
                    cell=instruction["profile_size_cell"] or "manual row",
                    previous_size=instruction["previous_profile_size"] or "null",
                    recommended_size=instruction["recommended_profile_size"],
                    channel=instruction["channel"] or "null",
                    market=instruction["market"] or "null",
                    organic_impressions=format_zero_decimal_number(instruction.get("organic_impressions")),
                    cpm=format_money(instruction["cpm"]),
                    activations=format_money(instruction["activations"]),
                    row_fee=format_money(instruction["row_fee"]),
                )
            )
        lines.extend(["", "### Other Options"])
        for option in result["options"]:
            if option["option_label"] == result["recommended_option_label"]:
                continue
            lines.append(
                "- {label}: diff={diff}, warnings={warnings}, note={note}".format(
                    label=option["option_label"],
                    diff=format_money(option["optimized_diff"]),
                    warnings=option["strategic_warning_count"],
                    note=option["main_note"],
                )
            )
        lines.extend(
            [
                "",
                "### Warnings and Diagnostics",
                f"- Search strategy: {result['search_diagnostics']['search_method']} (bounded={result['search_diagnostics']['bounded_search']}, approximate={result['search_diagnostics']['approximate_search']}, global_optimality_guaranteed={result['search_diagnostics']['global_optimality_guaranteed']})",
                f"- Allowed profile sizes: {', '.join(str(value) for value in result['search_diagnostics'].get('allowed_tiers', list(VALID_PROFILE_TIERS)))}",
                f"- Beam width: {result['search_diagnostics']['beam_width']}; expanded={result['search_diagnostics']['expanded_state_count']}; retained={result['search_diagnostics']['retained_state_count']}",
                f"- Baseline comparison for best mathematical fit: {result['search_diagnostics']['best_mathematical_fit_baseline_comparison']}",
                f"- Recommended differs from best mathematical fit: {'yes' if result['recommended_option_label'] != 'best_mathematical_fit' else 'no'}",
                f"- Strategic warnings: {'; '.join(strategic_warning_lines)}",
                f"- Result warnings: {'; '.join(result['warnings']) if result['warnings'] else 'none'}",
                "",
            ]
        )
    return "\n".join(lines)


def write_optimizer_markdown(path: Path, payload: dict[str, Any]) -> None:
    markdown = render_optimizer_markdown(payload)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")


def run_optimizer(
    input_path: Path = INPUT_PATH,
    json_output_path: Path = JSON_OUTPUT_PATH,
    markdown_output_path: Path = MARKDOWN_OUTPUT_PATH,
    workbook: str | None = None,
    sheet: str | None = None,
    top_n: int = DEFAULT_TOP_N,
    strategy: str = "math",
    allow_negative: bool = False,
    beam_width: int = DEFAULT_BEAM_WIDTH,
    optimization_method: str = "fast_closest_diff",
    allowed_tiers: list[int] | tuple[int, ...] | None = None,
    max_exact_states: int = DEFAULT_EXACT_MAX_STATES,
    open_report_after: bool = False,
) -> dict[str, Any]:
    _, models = load_normalized_models(input_path)
    filtered_models = resolve_unique_sheet_selection(models, workbook=workbook, sheet=sheet)
    if not filtered_models:
        raise ValueError("No canonical campaigns were selected.")
    resolved_json_output_path, resolved_markdown_output_path = choose_output_paths(
        filtered_models,
        json_output_path=json_output_path,
        markdown_output_path=markdown_output_path,
    )
    payload = run_optimizer_for_models(
        filtered_models,
        input_label=str(input_path),
        beam_width=beam_width,
        top_n=top_n,
        allow_negative=allow_negative,
        strategy=strategy,
        allowed_tiers=allowed_tiers,
        optimization_method=optimization_method,
        max_exact_states=max_exact_states,
    )
    write_optimizer_json(resolved_json_output_path, payload)
    write_optimizer_markdown(resolved_markdown_output_path, payload)
    summary_text = build_terminal_summary(payload, resolved_markdown_output_path, resolved_json_output_path)
    open_warning = None
    if open_report_after:
        open_warning = open_report(resolved_markdown_output_path)
    return {
        "payload": payload,
        "json_output_path": resolved_json_output_path,
        "markdown_output_path": resolved_markdown_output_path,
        "summary_text": summary_text,
        "open_warning": open_warning,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic optimizer for canonical influencer calculator sheets.")
    parser.add_argument("--input", type=Path, default=INPUT_PATH)
    parser.add_argument("--workbook")
    parser.add_argument("--sheet")
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    parser.add_argument("--strategy", choices=("math", "strategic"), default="math")
    parser.add_argument("--allow-negative", type=parse_bool_flag, default=False)
    parser.add_argument("--beam-width", type=int, default=DEFAULT_BEAM_WIDTH)
    parser.add_argument("--optimization-method", choices=OPTIMIZATION_METHODS, default="fast_closest_diff")
    parser.add_argument("--allowed-tiers", type=str)
    parser.add_argument("--max-exact-states", type=int, default=DEFAULT_EXACT_MAX_STATES)
    parser.add_argument("--open-report", action="store_true")
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()
    cli_allowed_tiers = None
    if args.allowed_tiers:
        try:
            cli_allowed_tiers = [int(part.strip()) for part in args.allowed_tiers.split(",") if part.strip()]
        except ValueError as error:
            print(f"Error: --allowed-tiers must be a comma-separated list of integers: {error}")
            return 1
    try:
        run_result = run_optimizer(
            input_path=args.input,
            workbook=args.workbook,
            sheet=args.sheet,
            top_n=args.top_n,
            strategy=args.strategy,
            allow_negative=args.allow_negative,
            beam_width=args.beam_width,
            optimization_method=args.optimization_method,
            allowed_tiers=cli_allowed_tiers,
            max_exact_states=args.max_exact_states,
            open_report_after=args.open_report,
        )
    except ValueError as error:
        print(f"Error: {error}")
        return 1

    print(run_result["summary_text"])
    if run_result["open_warning"]:
        print(run_result["open_warning"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
