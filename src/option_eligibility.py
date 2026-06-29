from __future__ import annotations

from typing import Any


MAX_RECOMMENDABLE_POSITIVE_DIFF = 10000.0
"""Temporary global product threshold until a budget-aware value is specified."""


def _parse_optimized_diff(option_or_diff: Any) -> float | None:
    value = option_or_diff.get("optimized_diff") if isinstance(option_or_diff, dict) else option_or_diff
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_option_diff_recommendable(option_or_diff: Any) -> bool:
    diff = _parse_optimized_diff(option_or_diff)
    if diff is None:
        return False
    return diff <= MAX_RECOMMENDABLE_POSITIVE_DIFF


def option_diff_disabled_reason(option_or_diff: Any) -> str | None:
    diff = _parse_optimized_diff(option_or_diff)
    if diff is None:
        return "invalid_or_missing_diff"
    if diff > MAX_RECOMMENDABLE_POSITIVE_DIFF:
        return "positive_diff_above_threshold"
    return None
