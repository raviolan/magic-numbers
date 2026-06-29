from __future__ import annotations

from typing import Any


_OPTION_UI_LABELS = {
    "closest_positive_diff": "Closest positive diff",
    "best_mathematical_fit": "Closest diff",
    "best_strategic_fit": "Strategic mix",
    "balanced_option": "Balanced option",
    "larger_profile_alternative": "Larger-profile option",
    "fallback_option": "Fallback",
    "current_workbook_mix": "Current workbook mix",
}


def option_ui_label(option_label: str, recommended_option_label: str) -> str:
    if option_label == recommended_option_label:
        return "Recommended"
    return _OPTION_UI_LABELS.get(option_label, "Fallback")


def format_option_label(option_label: str) -> str:
    return _OPTION_UI_LABELS.get(option_label, "Fallback")


def tier_mix_summary(tier_counts: dict[str, Any] | None) -> str:
    if not isinstance(tier_counts, dict):
        return "n/a"
    order = [15000, 35000, 75000, 125000, 175000]
    parts: list[str] = []
    for size in order:
        count = tier_counts.get(str(size), 0)
        try:
            count_int = int(count)
        except (TypeError, ValueError):
            count_int = 0
        if count_int > 0:
            parts.append(f"{int(size/1000)}K x {count_int}")
    return " \u00b7 ".join(parts) if parts else "none"


def select_option_label(option_labels: list[str], recommended_option_label: str, selected: str | None = None) -> str:
    if selected and selected in option_labels:
        return selected
    if recommended_option_label in option_labels:
        return recommended_option_label
    if not option_labels:
        raise ValueError("No option labels available.")
    return option_labels[0]


def at_a_glance_option_labels(result: dict[str, Any]) -> list[str]:
    options = [opt for opt in result.get("options", []) if opt.get("option_label")]
    if not options:
        return []

    by_label = {str(opt["option_label"]): opt for opt in options}
    recommended_label = str(result.get("recommended_option_label", ""))

    picked: list[str] = []

    def add(label: str | None) -> None:
        if label and label in by_label and label not in picked:
            picked.append(label)

    add(recommended_label)

    closest_positive_label = str(result.get("closest_positive_diff_option_label") or "")
    add(closest_positive_label or None)

    closest = min(options, key=lambda opt: abs(float(opt.get("optimized_diff", 0))))
    add(str(closest.get("option_label")))

    add("best_strategic_fit")
    add("balanced_option")
    add("larger_profile_alternative")

    for opt in options:
        add(str(opt.get("option_label")))
        if len(picked) >= 4:
            break

    return picked[:4]


def option_signature(option: dict[str, Any]) -> tuple[Any, ...]:
    lines = tuple(tier_mix_by_channel_lines(option.get("fill_instructions", [])))
    return (
        round(float(option.get("optimized_diff", 0)), 6),
        lines,
    )


def option_diff_delta_vs_recommended(option: dict[str, Any], recommended_option: dict[str, Any]) -> float:
    return float(option.get("optimized_diff", 0)) - float(recommended_option.get("optimized_diff", 0))


def option_tradeoff_summary(option: dict[str, Any], recommended_option: dict[str, Any]) -> str:
    if str(option.get("option_label")) == str(recommended_option.get("option_label")):
        return "Best balance"
    delta = option_diff_delta_vs_recommended(option, recommended_option)
    if delta > 0:
        return "More buffer"
    if delta < 0:
        return "Closer diff"
    option_lines = tier_mix_by_channel_lines(option.get("fill_instructions", []))
    rec_lines = tier_mix_by_channel_lines(recommended_option.get("fill_instructions", []))
    return "Different tier mix" if option_lines != rec_lines else "Similar mix"


def build_option_quick_compare_cards(result: dict[str, Any]) -> list[dict[str, Any]]:
    options = [option for option in result.get("options", []) if option.get("option_label")]
    if not options:
        return []
    recommended_label = str(result.get("recommended_option_label", ""))
    by_label = {str(option["option_label"]): option for option in options}
    recommended = by_label.get(recommended_label)
    if recommended is None:
        recommended = options[0]

    picked: list[dict[str, Any]] = []
    used_signatures: set[tuple[Any, ...]] = set()

    def add(option: dict[str, Any] | None) -> None:
        if option is None:
            return
        signature = option_signature(option)
        if signature in used_signatures:
            return
        if str(option.get("option_label")) == "fallback_option" and len(picked) >= 2:
            return
        used_signatures.add(signature)
        picked.append(option)

    add(recommended)
    closest_positive_label = str(result.get("closest_positive_diff_option_label") or "")
    add(by_label.get(closest_positive_label))
    for label in ("best_strategic_fit", "balanced_option", "larger_profile_alternative"):
        add(by_label.get(label))
        if len(picked) >= 3:
            break
    if len(picked) < 2:
        for option in options:
            add(option)
            if len(picked) >= 3:
                break

    cards: list[dict[str, Any]] = []
    for option in picked[:3]:
        delta = option_diff_delta_vs_recommended(option, recommended)
        cards.append(
            {
                "option_label": str(option.get("option_label")),
                "title": option_ui_label(str(option.get("option_label")), str(recommended.get("option_label"))),
                "diff": option.get("optimized_diff"),
                "delta_vs_recommended": delta,
                "tradeoff": option_tradeoff_summary(option, recommended),
                "tier_mix_lines": tier_mix_by_channel_lines(option.get("fill_instructions", [])),
                "main_note": main_option_note(option),
                "warnings": [str(item) for item in option.get("strategic_warnings", []) if str(item).strip()],
            }
        )
    return cards


def find_closest_positive_diff_option_label(options: list[dict[str, Any]]) -> str | None:
    eligible: list[dict[str, Any]] = []
    for option in options:
        diagnostics = option.get("diagnostics", {})
        if diagnostics.get("non_negative_diff") is not True:
            continue
        eligible.append(option)
    if not eligible:
        return None
    best = min(eligible, key=lambda opt: abs(float(opt.get("optimized_diff", 0))))
    label = best.get("option_label")
    return str(label) if label else None


def build_simplified_fill_rows(fill_instructions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool, bool]:
    include_market = any(bool((row.get("market") or "").strip()) for row in fill_instructions if isinstance(row, dict))
    include_activations = any((row.get("activations") not in (None, "", 1, 1.0, "1")) for row in fill_instructions if isinstance(row, dict))
    rows: list[dict[str, Any]] = []
    for row in fill_instructions:
        if not isinstance(row, dict):
            continue
        rec_size = row.get("recommended_profile_size")
        rec_display = ""
        try:
            rec_display = str(int(float(rec_size) / 1000)) if rec_size is not None else ""
        except (TypeError, ValueError):
            rec_display = ""
        item: dict[str, Any] = {
            "Size": rec_display,
            "Channel": row.get("channel"),
            "CPM": row.get("cpm"),
            "Fee": row.get("row_fee"),
        }
        if include_market:
            item["Market"] = row.get("market")
        if include_activations:
            item["Activations"] = row.get("activations")
        rows.append(item)
    return rows, include_market, include_activations


def build_diff_status(diff: Any) -> tuple[str, str]:
    try:
        value = float(diff)
    except (TypeError, ValueError):
        return "neutral", "n/a"
    if value > 0:
        return "positive", "Positive diff"
    if value < 0:
        return "negative", "Negative diff"
    return "neutral", "Exact match"


def build_tier_mix_chips(tier_counts: dict[str, Any] | None, include_zero: bool = False) -> list[str]:
    if not isinstance(tier_counts, dict):
        return []
    order = [15000, 35000, 75000, 125000, 175000]
    chips: list[str] = []
    for tier in order:
        raw_count = tier_counts.get(str(tier), 0)
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            count = 0
        if count > 0 or include_zero:
            chips.append(f"{int(tier/1000)}K × {count}")
    return chips


def build_channel_mix_summary(fill_instructions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for row in fill_instructions:
        if not isinstance(row, dict):
            continue
        channel = str(row.get("channel") or "").strip()
        if not channel:
            continue
        if channel not in summary:
            summary[channel] = {"channel": channel, "profiles": 0, "fee_sum": 0.0}
        summary[channel]["profiles"] += 1
        try:
            summary[channel]["fee_sum"] += float(row.get("row_fee") or 0.0)
        except (TypeError, ValueError):
            pass
    order = ["Instagram", "TikTok", "YouTube"]
    return [summary[channel] for channel in order if channel in summary]


def build_tier_mix_by_channel(fill_instructions: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for row in fill_instructions:
        if not isinstance(row, dict):
            continue
        channel_raw = str(row.get("channel") or "").strip()
        if not channel_raw:
            continue
        channel = channel_raw if channel_raw in {"Instagram", "TikTok", "YouTube"} else "Other"
        size = row.get("recommended_profile_size")
        try:
            size_int = int(float(size))
        except (TypeError, ValueError):
            continue
        if size_int <= 0:
            continue
        channel_bucket = summary.setdefault(channel, {})
        key = str(size_int)
        channel_bucket[key] = channel_bucket.get(key, 0) + 1
    ordered: dict[str, dict[str, int]] = {}
    for channel in ("Instagram", "TikTok", "YouTube", "Other"):
        if channel in summary:
            ordered[channel] = summary[channel]
    return ordered


def tier_mix_by_channel_lines(fill_instructions: list[dict[str, Any]]) -> list[str]:
    by_channel = build_tier_mix_by_channel(fill_instructions)
    lines: list[str] = []
    for channel, tier_counts in by_channel.items():
        chips = build_tier_mix_chips(tier_counts)
        if chips:
            lines.append(f"{channel}: " + " · ".join(chips))
    return lines


def main_option_note(option: dict[str, Any]) -> str:
    warnings = [str(item) for item in option.get("strategic_warnings", []) if str(item).strip()]
    if warnings:
        return warnings[0]
    note = str(option.get("main_note") or "").strip()
    return note if note else "No major warnings."
