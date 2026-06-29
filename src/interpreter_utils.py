from __future__ import annotations

from typing import Iterable
import re

from models import CellValue, SheetData


VALID_PROFILE_TIERS = {15000, 35000, 75000, 125000, 175000}
VALID_PROFILE_TIER_INPUTS = {15000, 35000, 75000, 125000, 175000, 15, 35, 75, 125, 175}
SUPPORTED_CHANNEL_ALIASES = {
    "Instagram": {"ig", "instagram"},
    "TikTok": {"tik tok", "tiktok", "tt"},
    "YouTube": {"youtube", "you tube", "yt"},
}
UNSUPPORTED_CHANNEL_ALIASES = {
    "Snapchat": {"snapchat"},
    "LinkedIn": {"linkedin"},
    "Meta": {"meta"},
    "Egna kanaler": {"egna kanaler", "egna kanal"},
}
OVERVIEW_KEYWORDS = ("overview", "summering", "summary", "masskampanj")


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower().replace("\n", " ")
    return re.sub(r"\s+", " ", text)


def compact_text(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", normalize_text(value))


def stringify_cell_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def get_rows(sheet: SheetData) -> dict[int, list[CellValue]]:
    rows: dict[int, list[CellValue]] = {}
    for cell in sheet.cells.values():
        rows.setdefault(cell.row, []).append(cell)
    for row in rows.values():
        row.sort(key=lambda item: item.column)
    return rows


def find_first_label(sheet: SheetData, candidates: Iterable[str]) -> CellValue | None:
    candidate_list = [normalize_text(candidate) for candidate in candidates]
    matches = []
    for cell in sheet.cells.values():
        text = normalize_text(cell.value)
        if text and any(candidate in text for candidate in candidate_list):
            matches.append(cell)
    if not matches:
        return None
    return sorted(matches, key=lambda item: (item.row, item.column))[0]


def find_nearest_numeric_value(sheet: SheetData, label_cell: CellValue) -> CellValue | None:
    by_position = {(cell.row, cell.column): cell for cell in sheet.cells.values()}
    candidate_offsets = [
        (0, 1),
        (0, 2),
        (0, 3),
        (0, 4),
        (0, 5),
        (0, 6),
        (0, 7),
        (0, 8),
        (1, 0),
        (1, 1),
        (1, 2),
        (1, 3),
        (2, 0),
        (2, 1),
        (2, 2),
    ]
    for row_offset, col_offset in candidate_offsets:
        candidate = by_position.get((label_cell.row + row_offset, label_cell.column + col_offset))
        if candidate and isinstance(candidate.value, (int, float)):
            return candidate
    return None


def detect_overview(sheet: SheetData) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    sheet_name = normalize_text(sheet.name)
    matched = [keyword for keyword in OVERVIEW_KEYWORDS if keyword in sheet_name]
    if matched:
        reasons.append(f"Sheet name matched overview keywords: {', '.join(sorted(matched))}.")
    return bool(reasons), reasons


def inspect_profile_size_value(value: object) -> dict[str, object]:
    raw_display = stringify_cell_value(value)
    if value is None or raw_display == "":
        return {
            "raw_display": raw_display,
            "normalized_tier": None,
            "invalid_display": None,
        }

    if isinstance(value, (int, float)):
        numeric_value = int(value)
        if numeric_value in VALID_PROFILE_TIERS:
            return {"raw_display": raw_display, "normalized_tier": numeric_value, "invalid_display": None}
        if numeric_value in VALID_PROFILE_TIER_INPUTS:
            candidate = numeric_value if numeric_value >= 1000 else numeric_value * 1000
            if candidate in VALID_PROFILE_TIERS:
                return {"raw_display": raw_display, "normalized_tier": candidate, "invalid_display": None}
        if numeric_value > 0:
            invalid_value = numeric_value if numeric_value >= 1000 else numeric_value * 1000
            return {"raw_display": raw_display, "normalized_tier": None, "invalid_display": str(invalid_value)}
        return {"raw_display": raw_display, "normalized_tier": None, "invalid_display": raw_display}

    text = normalize_text(value)
    if not text:
        return {"raw_display": raw_display, "normalized_tier": None, "invalid_display": None}

    if re.search(r"\d[\d\s,.]*\s*-\s*\d", text) or re.search(r"\d[\d\s,.]*\s+to\s+\d", text):
        return {"raw_display": raw_display, "normalized_tier": None, "invalid_display": raw_display}

    compact_numeric_text = re.sub(r"(?<=\d)[\s,](?=\d{3}\b)", "", text)
    matches = re.findall(r"\d+(?:[.,]\d+)?", compact_numeric_text)
    if len(matches) != 1:
        return {"raw_display": raw_display, "normalized_tier": None, "invalid_display": raw_display}

    number = float(matches[0].replace(",", "."))
    if number <= 0:
        return {"raw_display": raw_display, "normalized_tier": None, "invalid_display": raw_display}

    if "k" in compact_numeric_text and number < 1000:
        candidate = int(number * 1000)
    elif number < 1000:
        candidate = int(number * 1000)
    else:
        candidate = int(number)

    if candidate in VALID_PROFILE_TIERS:
        return {"raw_display": raw_display, "normalized_tier": candidate, "invalid_display": None}
    return {"raw_display": raw_display, "normalized_tier": None, "invalid_display": str(candidate)}


def detect_profile_section(sheet: SheetData) -> tuple[CellValue | None, dict[str, int], list[dict[str, object]]]:
    rows = get_rows(sheet)
    size_keywords = ("follower size", "profilstorlek", "profile á", "profile a")
    for row_number in sorted(rows):
        row = rows[row_number]
        labels = {normalize_text(cell.value): cell.column for cell in row if isinstance(cell.value, str)}
        joined = " | ".join(labels.keys())
        has_channel = "channel" in joined
        has_size = any(keyword in joined for keyword in size_keywords)
        has_cpm = "cpm" in joined
        if has_channel and has_size and has_cpm:
            header_cell = min(row, key=lambda item: item.column)
            columns = {
                "channel": next(column for label, column in labels.items() if "channel" in label),
                "size": next(column for label, column in labels.items() if any(keyword in label for keyword in size_keywords)),
                "cpm": next(column for label, column in labels.items() if "cpm" in label),
            }
            if any("activation" in label for label in labels):
                columns["activation"] = next(column for label, column in labels.items() if "activation" in label)
            if any("impressions" in label for label in labels):
                columns["impressions"] = next(column for label, column in labels.items() if "impressions" in label)
            if any("profile fee" in label or "profie fee" in label for label in labels):
                columns["profile_fee"] = next(
                    column
                    for label, column in labels.items()
                    if "profile fee" in label or "profie fee" in label
                )
            profile_rows = extract_profile_rows(rows, row_number, columns)
            return header_cell, columns, profile_rows
    return None, {}, []


def extract_profile_rows(
    rows: dict[int, list[CellValue]],
    header_row: int,
    columns: dict[str, int],
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    empty_run = 0
    lookup = {
        row_number: {cell.column: cell for cell in row_cells}
        for row_number, row_cells in rows.items()
    }
    end_row = max(rows) if rows else header_row
    for row_number in range(header_row + 1, end_row + 1):
        row = lookup.get(row_number, {})
        channel_cell = row.get(columns["channel"])
        size_cell = row.get(columns["size"])
        cpm_cell = row.get(columns["cpm"])
        activation_cell = row.get(columns["activation"]) if "activation" in columns else None
        impressions_cell = row.get(columns["impressions"]) if "impressions" in columns else None
        profile_fee_cell = row.get(columns["profile_fee"]) if "profile_fee" in columns else None
        row_text = " ".join(normalize_text(cell.value) for cell in row.values())

        if any(stop_word in row_text for stop_word in ("total", "diff", "paid", "total campaign", "kontroll")):
            break

        size_inspection = inspect_profile_size_value(size_cell.value if size_cell else None)
        channel_text = normalize_text(channel_cell.value if channel_cell else None)
        cpm_value = cpm_cell.value if cpm_cell else None
        activation_value = activation_cell.value if activation_cell else None
        impressions_value = impressions_cell.value if impressions_cell else None
        profile_fee_value = profile_fee_cell.value if profile_fee_cell else None

        if (
            not channel_text
            and not size_inspection["raw_display"]
            and cpm_value is None
            and activation_value is None
            and impressions_value is None
            and profile_fee_value is None
        ):
            empty_run += 1
            if empty_run >= 2:
                break
            continue

        empty_run = 0
        if (
            channel_text
            or size_inspection["raw_display"]
            or isinstance(cpm_value, (int, float))
            or activation_value is not None
            or isinstance(impressions_value, (int, float))
            or isinstance(profile_fee_value, (int, float))
        ):
            results.append(
                {
                    "row": row_number,
                    "channel": channel_cell.value if channel_cell else None,
                    "channel_cell": channel_cell.ref if channel_cell else None,
                    "size_raw": size_cell.value if size_cell else None,
                    "size_display": size_inspection["raw_display"],
                    "size_cell": size_cell.ref if size_cell else None,
                    "normalized_tier": size_inspection["normalized_tier"],
                    "invalid_profile_value": size_inspection["invalid_display"],
                    "cpm": cpm_value if isinstance(cpm_value, (int, float)) else None,
                    "cpm_cell": cpm_cell.ref if cpm_cell else None,
                    "activation": activation_value if isinstance(activation_value, (int, float)) else activation_value,
                    "activation_cell": activation_cell.ref if activation_cell else None,
                    "impressions": impressions_value if isinstance(impressions_value, (int, float)) else None,
                    "impressions_cell": impressions_cell.ref if impressions_cell else None,
                    "profile_fee": profile_fee_value if isinstance(profile_fee_value, (int, float)) else None,
                    "profile_fee_cell": profile_fee_cell.ref if profile_fee_cell else None,
                }
            )
    return results


def _label_matches_alias(text: str, collapsed: str, alias: str) -> bool:
    alias_normalized = normalize_text(alias)
    alias_compact = compact_text(alias)
    return text == alias_normalized or collapsed == alias_compact or f" {alias_normalized} " in f" {text} "


def normalize_supported_channel(raw_label: object) -> str | None:
    text = normalize_text(raw_label)
    collapsed = compact_text(raw_label)
    for label, aliases in SUPPORTED_CHANNEL_ALIASES.items():
        for alias in aliases:
            if _label_matches_alias(text, collapsed, alias):
                return label
    return None


def normalize_unsupported_channel(raw_label: object) -> str | None:
    text = normalize_text(raw_label)
    collapsed = compact_text(raw_label)
    for label, aliases in UNSUPPORTED_CHANNEL_ALIASES.items():
        for alias in aliases:
            if _label_matches_alias(text, collapsed, alias):
                return label
    return None


def detect_channels(profile_rows: list[dict[str, object]]) -> tuple[list[str], list[str]]:
    supported: set[str] = set()
    unsupported: set[str] = set()
    for row in profile_rows:
        raw_label = row.get("channel")
        supported_label = normalize_supported_channel(raw_label)
        unsupported_label = normalize_unsupported_channel(raw_label)
        if supported_label:
            supported.add(supported_label)
        if unsupported_label:
            unsupported.add(unsupported_label)
    return sorted(supported), sorted(unsupported)


def split_market_channel(raw_label: object) -> tuple[str | None, str | None]:
    if raw_label is None:
        return None, None
    raw_text = stringify_cell_value(raw_label).strip()
    normalized_channel = normalize_supported_channel(raw_text)
    if normalized_channel is None:
        return None, None

    text = normalize_text(raw_text)
    for alias in sorted(SUPPORTED_CHANNEL_ALIASES[normalized_channel], key=len, reverse=True):
        alias_normalized = normalize_text(alias)
        if text == alias_normalized:
            return None, normalized_channel
        if text.endswith(f" {alias_normalized}"):
            suffix_length = len(alias_normalized)
            market = raw_text[: len(raw_text) - suffix_length].strip()
            if market:
                return market, normalized_channel
    return None, normalized_channel


def detect_paid_section(sheet: SheetData, profile_header: CellValue | None) -> tuple[bool, str, bool, CellValue | None]:
    paid_cell = find_first_label(sheet, ["paid", "paid media", "betald"])
    if paid_cell is None:
        return False, "not_found", False, None
    if profile_header is None:
        return True, "unknown_without_profiles", False, paid_cell
    if paid_cell.row < profile_header.row:
        return True, "before_profiles", True, paid_cell
    return True, "after_profiles", False, paid_cell


def detect_formula_cache_warnings(sheet: SheetData) -> list[str]:
    warnings: list[str] = []
    for cell in sorted(sheet.cells.values(), key=lambda item: (item.row, item.column)):
        if cell.formula and cell.value is None:
            warnings.append(f"{cell.ref} has formula without cached value")
    return warnings


def detect_diff(sheet: SheetData) -> tuple[CellValue | None, CellValue | None]:
    label_cell = find_first_label(sheet, ["diff"])
    if label_cell is None:
        return None, None

    row_matches = [
        cell
        for cell in sheet.cells.values()
        if cell.row == label_cell.row and cell.column > label_cell.column and isinstance(cell.value, (int, float))
    ]
    if row_matches:
        return label_cell, sorted(row_matches, key=lambda item: item.column)[0]

    below_matches = [
        cell
        for cell in sheet.cells.values()
        if cell.column == label_cell.column + 1 and cell.row > label_cell.row and isinstance(cell.value, (int, float))
    ]
    if below_matches:
        return label_cell, sorted(below_matches, key=lambda item: item.row)[0]

    return label_cell, None
