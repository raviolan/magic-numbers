from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from cpm_library import CURRENCY_UNKNOWN, SUPPORTED_CURRENCIES, normalize_currency
from models import WorkbookData
from xlsx_reader import load_workbook


SUPPORTED_CHANNELS = ("Instagram", "TikTok", "YouTube")

REFERENCE_NAME_ALIASES = {
    "reference",
    "project",
    "project name",
    "calculation name",
    "campaign",
    "client",
    "name",
    "workbook",
}
CHANNEL_ALIASES = {"channel", "platform", "kanal", "plattform", "channel "}
CPM_ALIASES = {"cpm", "cpm value", "value", "rate"}
CURRENCY_ALIASES = {"currency", "valuta", "curr"}
MARKET_ALIASES = {"market", "country", "region", "land", "marknad"}
COMMENT_ALIASES = {"comment", "comments", "notes", "note", "kommentar"}
NICHE_ALIASES = {"niche"}
USED_ROW_COUNT_ALIASES = {"used row count", "used_row_count", "row count", "count", "antal", "profiles", "profile count"}


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_header(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_reference_channel(value: Any) -> str | None:
    text = _normalize_optional_text(value)
    if not text:
        return None
    normalized = re.sub(r"[^a-z0-9]", "", text.lower())
    mapping = {
        "ig": "Instagram",
        "insta": "Instagram",
        "instagram": "Instagram",
        "tt": "TikTok",
        "tiktok": "TikTok",
        "tik tok": "TikTok",
        "youtube": "YouTube",
        "yt": "YouTube",
        "youtubeshorts": "YouTube",
    }
    if normalized in mapping:
        return mapping[normalized]
    return None


def parse_cpm_value(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
    else:
        text = str(value).strip().replace("\u00a0", " ")
        if not text:
            return None
        text = text.replace(" ", "")
        if "," in text and "." in text:
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        elif "," in text:
            if re.fullmatch(r"\d{1,3}(,\d{3})+", text):
                text = text.replace(",", "")
            else:
                text = text.replace(",", ".")
        try:
            numeric = float(text)
        except ValueError:
            return None

    if numeric <= 0:
        return None
    if float(numeric).is_integer():
        return int(numeric)
    return numeric


def _parse_used_row_count(value: Any) -> int:
    if value is None:
        return 1
    if isinstance(value, str) and not value.strip():
        return 1
    try:
        parsed = int(float(str(value).strip().replace(" ", "")))
    except (TypeError, ValueError):
        return 1
    return parsed if parsed > 0 else 1


def _combine_comment(niche_value: str | None, comment_value: str | None) -> str | None:
    if niche_value and comment_value:
        if niche_value == comment_value:
            return niche_value
        return f"Niche: {niche_value}. Comment: {comment_value}"
    return niche_value or comment_value


def load_reference_cpm_workbook(path: str | Path) -> WorkbookData:
    return load_workbook(path)


def detect_reference_cpm_columns(headers: dict[int, Any]) -> dict[str, int]:
    detected: dict[str, int] = {}
    for column_index, header in headers.items():
        normalized = _normalize_header(header)
        if normalized in REFERENCE_NAME_ALIASES and "reference_name" not in detected:
            detected["reference_name"] = column_index
        elif normalized in CHANNEL_ALIASES and "channel" not in detected:
            detected["channel"] = column_index
        elif normalized in CPM_ALIASES and "cpm" not in detected:
            detected["cpm"] = column_index
        elif normalized in CURRENCY_ALIASES and "currency" not in detected:
            detected["currency"] = column_index
        elif normalized in MARKET_ALIASES and "market" not in detected:
            detected["market"] = column_index
        elif normalized in NICHE_ALIASES and "niche" not in detected:
            detected["niche"] = column_index
        elif normalized in COMMENT_ALIASES and "comment" not in detected:
            detected["comment"] = column_index
        elif normalized in USED_ROW_COUNT_ALIASES and "used_row_count" not in detected:
            detected["used_row_count"] = column_index
    return detected


def _sheet_rows_as_indexed_dicts(sheet) -> list[dict[int, Any]]:
    indexed_rows: list[dict[int, Any]] = []
    for row in sheet.iter_rows():
        row_map: dict[int, Any] = {}
        for cell in row:
            row_map[cell.column] = cell.value
        indexed_rows.append(row_map)
    return indexed_rows


def _find_header_row(indexed_rows: list[dict[int, Any]]) -> tuple[int, dict[str, int]]:
    best_index = -1
    best_detected: dict[str, int] = {}
    for row_index, row in enumerate(indexed_rows):
        detected = detect_reference_cpm_columns(row)
        score = len(detected)
        if {"channel", "cpm"}.issubset(set(detected.keys())) and score > len(best_detected):
            best_index = row_index
            best_detected = detected
    return best_index, best_detected


def _normalize_row_currency(raw_currency: Any, default_currency: str) -> tuple[str, str | None]:
    text = _normalize_optional_text(raw_currency)
    if text is None:
        normalized = normalize_currency(default_currency, allow_unknown=True)
        return normalized, None
    normalized = normalize_currency(text, allow_unknown=True)
    if normalized not in (*SUPPORTED_CURRENCIES, CURRENCY_UNKNOWN):
        return CURRENCY_UNKNOWN, f"Unsupported currency: {text}"
    if normalized == CURRENCY_UNKNOWN and text.upper() not in {"UNKNOWN"}:
        return CURRENCY_UNKNOWN, f"Unsupported currency: {text}"
    return normalized, None


def _build_reference_import_key(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        "manual_reference_import",
        record.get("calculation_name"),
        record.get("sheet_name"),
        record.get("channel"),
        record.get("market"),
        record.get("currency"),
        record.get("cpm"),
        record.get("comment"),
    )


def _existing_import_keys(existing_observations: list[dict[str, Any]]) -> set[tuple[Any, ...]]:
    keys: set[tuple[Any, ...]] = set()
    for row in existing_observations:
        if row.get("source_type") != "manual_reference_import":
            continue
        keys.add(_build_reference_import_key(row))
    return keys


def parse_reference_cpm_rows_from_workbook(
    workbook: WorkbookData,
    default_currency: str = CURRENCY_UNKNOWN,
) -> list[dict[str, Any]]:
    workbook_stem = Path(workbook.path).stem or "CPMreferenser"
    normalized_default_currency = normalize_currency(default_currency, allow_unknown=True)

    parsed_rows: list[dict[str, Any]] = []
    for sheet in workbook.sheets:
        indexed_rows = _sheet_rows_as_indexed_dicts(sheet)
        if not indexed_rows:
            continue
        header_index, columns = _find_header_row(indexed_rows)
        if header_index < 0:
            continue

        for row_number, row in enumerate(indexed_rows[header_index + 1 :], start=header_index + 2):
            if not any(value is not None and str(value).strip() for value in row.values()):
                continue

            reference_name = _normalize_optional_text(row.get(columns.get("reference_name", -1))) or workbook_stem
            channel_raw = row.get(columns.get("channel", -1))
            channel = normalize_reference_channel(channel_raw)
            cpm = parse_cpm_value(row.get(columns.get("cpm", -1)))

            market = _normalize_optional_text(row.get(columns.get("market", -1)))
            niche = _normalize_optional_text(row.get(columns.get("niche", -1)))
            comment = _normalize_optional_text(row.get(columns.get("comment", -1)))
            combined_comment = _combine_comment(niche, comment)
            used_row_count = _parse_used_row_count(row.get(columns.get("used_row_count", -1)))

            currency, currency_error = _normalize_row_currency(
                row.get(columns.get("currency", -1)),
                default_currency=normalized_default_currency,
            )

            messages: list[str] = []
            if channel is None:
                messages.append(f"Unsupported or missing channel: {channel_raw!r}")
            if cpm is None:
                messages.append("CPM must be numeric and greater than 0")
            if currency_error:
                messages.append(currency_error)

            row_payload = {
                "source_sheet": sheet.name,
                "source_row_number": row_number,
                "calculation_name": reference_name,
                "workbook_name": None,
                "sheet_name": sheet.name,
                "channel": channel,
                "market": market,
                "currency": currency,
                "cpm": cpm,
                "used_row_count": used_row_count,
                "comment": combined_comment,
            }

            if messages:
                row_payload["status"] = "invalid"
                row_payload["validation_message"] = "; ".join(messages)
            else:
                row_payload["status"] = "valid"
                row_payload["validation_message"] = ""
            parsed_rows.append(row_payload)
    return parsed_rows


def parse_reference_cpm_rows(path: str | Path, default_currency: str = CURRENCY_UNKNOWN) -> list[dict[str, Any]]:
    workbook = load_reference_cpm_workbook(path)
    return parse_reference_cpm_rows_from_workbook(workbook, default_currency=default_currency)


def preview_reference_cpm_import(
    path: str | Path,
    existing_observations: list[dict[str, Any]],
    default_currency: str = CURRENCY_UNKNOWN,
) -> dict[str, Any]:
    parsed_rows = parse_reference_cpm_rows(path, default_currency=default_currency)
    existing_keys = _existing_import_keys(existing_observations)
    batch_seen: set[tuple[Any, ...]] = set()

    preview_rows: list[dict[str, Any]] = []
    valid_count = 0
    invalid_count = 0
    duplicate_count = 0

    for row in parsed_rows:
        preview = dict(row)
        if preview["status"] != "valid":
            invalid_count += 1
            preview_rows.append(preview)
            continue

        dedupe_key = _build_reference_import_key(preview)
        if dedupe_key in existing_keys or dedupe_key in batch_seen:
            preview["status"] = "duplicate"
            preview["validation_message"] = "Duplicate import row"
            duplicate_count += 1
        else:
            batch_seen.add(dedupe_key)
            valid_count += 1
        preview_rows.append(preview)

    return {
        "path": str(path),
        "default_currency": normalize_currency(default_currency, allow_unknown=True),
        "rows": preview_rows,
        "counts": {
            "total": len(preview_rows),
            "valid": valid_count,
            "invalid": invalid_count,
            "duplicate": duplicate_count,
        },
    }


def build_cpm_observation_from_reference_row(row: dict[str, Any], created_at: str | None = None) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "created_at": created_at or _utc_timestamp(),
        "source_type": "manual_reference_import",
        "calculation_id": None,
        "calculation_name": row.get("calculation_name"),
        "workbook_name": row.get("workbook_name"),
        "sheet_name": row.get("sheet_name"),
        "channel": row.get("channel"),
        "market": row.get("market"),
        "currency": row.get("currency"),
        "cpm": row.get("cpm"),
        "used_row_count": row.get("used_row_count") or 1,
        "comment": row.get("comment"),
    }


def import_reference_cpm_rows(
    path: str | Path,
    existing_observations: list[dict[str, Any]],
    default_currency: str = CURRENCY_UNKNOWN,
) -> dict[str, Any]:
    preview = preview_reference_cpm_import(
        path=path,
        existing_observations=existing_observations,
        default_currency=default_currency,
    )

    updated = list(existing_observations)
    imported_count = 0
    for row in preview["rows"]:
        if row["status"] != "valid":
            continue
        updated.append(build_cpm_observation_from_reference_row(row))
        imported_count += 1

    return {
        "preview": preview,
        "updated_observations": updated,
        "imported_count": imported_count,
        "invalid_count": preview["counts"]["invalid"],
        "duplicate_count": preview["counts"]["duplicate"],
    }
