from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterable
from uuid import uuid4


LIBRARY_DIR = Path("data/library")
APPROVED_CALCULATIONS_PATH = LIBRARY_DIR / "approved_calculations.json"
CPM_OBSERVATIONS_PATH = LIBRARY_DIR / "cpm_observations.json"

SUPPORTED_CURRENCIES = ("SEK", "EUR")
CURRENCY_UNKNOWN = "Unknown"
SUPPORTED_CHANNELS = ("Instagram", "TikTok", "YouTube")
FULL_LIBRARY_VISIBLE_COLUMNS = ("Workbook", "Sheet", "Channel", "Currency", "CPM", "Comment")

REFERENCE_WORKBOOK_CURRENCY_MAP = {
    "5311 Dear Dahlia Kalkyl (V.A).xlsx": "EUR",
    "5312 Medclair Kalkyl (V.A).xlsx": "SEK",
}


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    return text or None


def _normalize_cpm(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        value = raw
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric.is_integer():
        return int(numeric)
    return numeric


def normalize_currency(value: Any, allow_unknown: bool = True) -> str:
    if value is None:
        return CURRENCY_UNKNOWN if allow_unknown else _raise_invalid_currency(value, allow_unknown)
    normalized = str(value).strip().upper()
    if normalized in SUPPORTED_CURRENCIES:
        return normalized
    if normalized in {"", "UNKNOWN"} and allow_unknown:
        return CURRENCY_UNKNOWN
    return CURRENCY_UNKNOWN if allow_unknown else _raise_invalid_currency(value, allow_unknown)


def _raise_invalid_currency(value: Any, allow_unknown: bool) -> str:
    if allow_unknown:
        raise ValueError("Unexpected currency validation state.")
    raise ValueError(f"Unsupported currency: {value!r}. Allowed values: {', '.join(SUPPORTED_CURRENCIES)}")


def validate_currency(value: Any, allow_unknown: bool = False) -> str:
    return normalize_currency(value, allow_unknown=allow_unknown)


def infer_reference_currency(workbook_name: str | None, sheet_name: str | None = None) -> str:
    mapped = REFERENCE_WORKBOOK_CURRENCY_MAP.get(workbook_name or "")
    if mapped in SUPPORTED_CURRENCIES:
        return mapped
    return CURRENCY_UNKNOWN


def _dedupe_key(record: dict[str, Any], key_fields: Iterable[str]) -> tuple[Any, ...]:
    return tuple(record.get(field) for field in key_fields)


def _load_json_list(path: Path, label: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in {label} file: {path} ({error})") from error
    if not isinstance(payload, list):
        raise ValueError(f"Invalid {label} file: expected a JSON list at {path}")
    return [record for record in payload if isinstance(record, dict)]


def _save_json_list(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_approved_calculations(path: Path = APPROVED_CALCULATIONS_PATH) -> list[dict[str, Any]]:
    return _load_json_list(path, "approved calculations")


def save_approved_calculations(records: list[dict[str, Any]], path: Path = APPROVED_CALCULATIONS_PATH) -> None:
    _save_json_list(path, records)


def load_cpm_observations(path: Path = CPM_OBSERVATIONS_PATH) -> list[dict[str, Any]]:
    return _load_json_list(path, "CPM observations")


def save_cpm_observations(records: list[dict[str, Any]], path: Path = CPM_OBSERVATIONS_PATH) -> None:
    _save_json_list(path, records)


def dedupe_observations(
    observations: list[dict[str, Any]],
    key_fields: tuple[str, ...] = (
        "source_type",
        "workbook_name",
        "sheet_name",
        "channel",
        "market",
        "currency",
        "cpm",
        "calculation_id",
    ),
) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    deduped: list[dict[str, Any]] = []
    for record in observations:
        key = _dedupe_key(record, key_fields)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def migrate_or_normalize_observation_currency(observation: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    migrated = dict(observation)
    source_type = _normalize_optional_text(observation.get("source_type"))
    current_currency = observation.get("currency")
    normalized_currency = normalize_currency(current_currency, allow_unknown=True)

    if source_type == "reference_canonical" and normalized_currency == CURRENCY_UNKNOWN:
        normalized_currency = infer_reference_currency(
            _normalize_optional_text(observation.get("workbook_name")),
            _normalize_optional_text(observation.get("sheet_name")),
        )

    changed = current_currency != normalized_currency
    if changed:
        migrated["currency"] = normalized_currency
    return migrated, changed


def _extract_model_fields(model: Any) -> tuple[str | None, str | None, list[dict[str, Any]]]:
    if isinstance(model, dict):
        source = model.get("source") or {}
        rows = model.get("profile_rows") or []
        return source.get("workbook_name"), source.get("sheet_name"), rows

    source = getattr(model, "source", None)
    workbook_name = getattr(source, "workbook_name", None)
    sheet_name = getattr(source, "sheet_name", None)
    rows = []
    for row in getattr(model, "profile_rows", []):
        rows.append(
            {
                "channel": getattr(row, "channel", None),
                "market": getattr(row, "market", None),
                "cpm": getattr(row, "cpm", None),
            }
        )
    return workbook_name, sheet_name, rows


def seed_reference_cpm_observations(
    normalized_models: list[Any],
    existing_observations: list[dict[str, Any]] | None = None,
    created_at: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    observations = []
    for record in list(existing_observations or []):
        migrated, _ = migrate_or_normalize_observation_currency(record)
        observations.append(migrated)

    timestamp = created_at or _utc_timestamp()
    added_count = 0

    existing_reference_keys = {
        (
            record.get("source_type"),
            record.get("workbook_name"),
            record.get("sheet_name"),
            record.get("channel"),
            record.get("market"),
            normalize_currency(record.get("currency"), allow_unknown=True),
            record.get("cpm"),
        )
        for record in observations
        if record.get("source_type") == "reference_canonical"
    }

    grouped: dict[tuple[Any, ...], int] = defaultdict(int)
    for model in normalized_models:
        workbook_name, sheet_name, rows = _extract_model_fields(model)
        currency = infer_reference_currency(_normalize_optional_text(workbook_name), _normalize_optional_text(sheet_name))
        for row in rows:
            channel = _normalize_optional_text(row.get("channel"))
            if channel is None:
                continue
            cpm = _normalize_cpm(row.get("cpm"))
            if cpm is None:
                continue
            market = _normalize_optional_text(row.get("market"))
            grouped[(workbook_name, sheet_name, channel, market, currency, cpm)] += 1

    for (workbook_name, sheet_name, channel, market, currency, cpm), used_row_count in grouped.items():
        dedupe_key = ("reference_canonical", workbook_name, sheet_name, channel, market, currency, cpm)
        if dedupe_key in existing_reference_keys:
            continue
        existing_reference_keys.add(dedupe_key)
        observations.append(
            {
                "id": str(uuid4()),
                "created_at": timestamp,
                "source_type": "reference_canonical",
                "calculation_id": None,
                "calculation_name": f"{workbook_name} / {sheet_name}",
                "workbook_name": workbook_name,
                "sheet_name": sheet_name,
                "channel": channel,
                "market": market,
                "currency": currency,
                "cpm": cpm,
                "used_row_count": used_row_count,
                "comment": None,
            }
        )
        added_count += 1
    return observations, added_count


def build_cpm_observations_from_approved_option(
    calculation_id: str,
    calculation_name: str,
    source_type: str,
    approved_option: dict[str, Any],
    workbook_name: str | None,
    sheet_name: str | None,
    currency: str,
    comment: str | None = None,
    created_at: str | None = None,
) -> list[dict[str, Any]]:
    timestamp = created_at or _utc_timestamp()
    normalized_currency = validate_currency(currency, allow_unknown=False)
    grouped: dict[tuple[Any, ...], int] = defaultdict(int)

    for row in approved_option.get("fill_instructions", []):
        channel = _normalize_optional_text(row.get("channel"))
        if channel is None:
            continue
        cpm = _normalize_cpm(row.get("cpm"))
        if cpm is None:
            continue
        market = _normalize_optional_text(row.get("market"))
        grouped[(channel, market, normalized_currency, cpm)] += 1

    observations: list[dict[str, Any]] = []
    for (channel, market, grouped_currency, cpm), used_row_count in grouped.items():
        observations.append(
            {
                "id": str(uuid4()),
                "created_at": timestamp,
                "source_type": source_type,
                "calculation_id": calculation_id,
                "calculation_name": calculation_name,
                "workbook_name": workbook_name,
                "sheet_name": sheet_name,
                "channel": channel,
                "market": market,
                "currency": grouped_currency,
                "cpm": cpm,
                "used_row_count": used_row_count,
                "comment": comment,
            }
        )
    return observations


def approve_calculation(
    *,
    result: dict[str, Any],
    calculation_name: str,
    source: dict[str, Any],
    budget_inputs: dict[str, Any],
    currency: str,
    approved_option_label: str | None = None,
    comment: str | None = None,
    approved_calculations_path: Path = APPROVED_CALCULATIONS_PATH,
    cpm_observations_path: Path = CPM_OBSERVATIONS_PATH,
    created_at: str | None = None,
) -> dict[str, Any]:
    normalized_name = _normalize_optional_text(calculation_name)
    if not normalized_name:
        raise ValueError("Calculation name is required.")

    normalized_currency = validate_currency(currency, allow_unknown=False)

    selected_option_label = approved_option_label or result.get("recommended_option_label")
    approved_option = next((option for option in result.get("options", []) if option.get("option_label") == selected_option_label), None)
    if approved_option is None:
        raise ValueError(f"Approved option not found: {selected_option_label!r}.")

    timestamp = created_at or _utc_timestamp()
    calculation_id = str(uuid4())
    normalized_comment = _normalize_optional_text(comment)

    source_mode = _normalize_optional_text(source.get("mode"))
    workbook_name = _normalize_optional_text(source.get("workbook_name"))
    sheet_name = _normalize_optional_text(source.get("sheet_name"))

    approved_record = {
        "id": calculation_id,
        "created_at": timestamp,
        "calculation_name": normalized_name,
        "currency": normalized_currency,
        "comment": normalized_comment,
        "source": {
            "mode": source_mode,
            "workbook_name": workbook_name,
            "sheet_name": sheet_name,
        },
        "approved_option_label": selected_option_label,
        "budget_inputs": budget_inputs,
        "result_summary": {
            "optimized_diff": approved_option.get("optimized_diff"),
            "profile_fee_sum": approved_option.get("profile_fee_sum"),
            "tier_counts": approved_option.get("tier_counts"),
            "total_impressions": approved_option.get("total_impressions"),
            "impressions_by_channel": approved_option.get("impressions_by_channel"),
            "impressions_by_market": approved_option.get("impressions_by_market"),
        },
        "fill_instructions": approved_option.get("fill_instructions", []),
    }

    approved_records = load_approved_calculations(approved_calculations_path)
    approved_records.append(approved_record)
    save_approved_calculations(approved_records, approved_calculations_path)

    mode_to_source_type = {
        "manual_campaign_builder": "approved_manual",
        "canonical_sheet": "approved_canonical",
    }
    source_type = mode_to_source_type.get(source_mode, "approved_manual")
    new_observations = build_cpm_observations_from_approved_option(
        calculation_id=calculation_id,
        calculation_name=normalized_name,
        source_type=source_type,
        approved_option=approved_option,
        workbook_name=workbook_name,
        sheet_name=sheet_name,
        currency=normalized_currency,
        comment=normalized_comment,
        created_at=timestamp,
    )

    observations = load_cpm_observations(cpm_observations_path)
    observations.extend(new_observations)
    observations = dedupe_observations(observations)
    save_cpm_observations(observations, cpm_observations_path)

    return {
        "approved_record": approved_record,
        "added_cpm_observation_count": len(new_observations),
    }


def summarize_cpm_library_by_currency_and_channel(observations: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, dict[str, list[float]]] = {currency: defaultdict(list) for currency in SUPPORTED_CURRENCIES}
    unknown_count = 0

    for record in observations:
        channel = _normalize_optional_text(record.get("channel"))
        cpm = _normalize_cpm(record.get("cpm"))
        if channel is None or cpm is None:
            continue

        currency = normalize_currency(record.get("currency"), allow_unknown=True)
        if currency not in SUPPORTED_CURRENCIES:
            unknown_count += 1
            continue
        grouped[currency][channel].append(float(cpm))

    order = {"Instagram": 0, "TikTok": 1, "YouTube": 2}
    by_currency: dict[str, list[dict[str, Any]]] = {}
    for currency in SUPPORTED_CURRENCIES:
        rows: list[dict[str, Any]] = []
        for channel, values in grouped[currency].items():
            rows.append(
                {
                    "channel": channel,
                    "average_cpm": statistics.mean(values),
                    "median_cpm": statistics.median(values),
                    "observation_count": len(values),
                }
            )
        rows.sort(key=lambda row: (order.get(row["channel"], 99), row["channel"]))
        by_currency[currency] = rows

    return {"by_currency": by_currency, "unknown_currency_observation_count": unknown_count}


def get_currency_channel_medians(observations: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    summary = summarize_cpm_library_by_currency_and_channel(observations)
    medians: dict[str, dict[str, float]] = {}
    for currency, rows in summary["by_currency"].items():
        medians[currency] = {row["channel"]: float(row["median_cpm"]) for row in rows}
    return medians


def summarize_cpm_library_by_channel(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, list[float]] = defaultdict(list)
    summary = summarize_cpm_library_by_currency_and_channel(observations)
    for currency_rows in summary["by_currency"].values():
        for row in currency_rows:
            channel = row["channel"]
            merged[channel].append(float(row["average_cpm"]))

    order = {"Instagram": 0, "TikTok": 1, "YouTube": 2}
    rows = []
    for channel, values in merged.items():
        rows.append(
            {
                "channel": channel,
                "average_cpm": statistics.mean(values),
                "median_cpm": statistics.median(values),
                "observation_count": len(values),
            }
        )
    rows.sort(key=lambda row: (order.get(row["channel"], 99), row["channel"]))
    return rows


def add_manual_reference_cpm(
    *,
    observations: list[dict[str, Any]],
    reference_name: str,
    channel: str,
    currency: str,
    cpm: Any,
    market: Any = None,
    comment: Any = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    normalized_name = _normalize_optional_text(reference_name)
    if not normalized_name:
        raise ValueError("Reference/project name is required.")

    normalized_channel = _normalize_optional_text(channel)
    if normalized_channel not in SUPPORTED_CHANNELS:
        raise ValueError(f"Channel must be one of: {', '.join(SUPPORTED_CHANNELS)}")

    normalized_currency = validate_currency(currency, allow_unknown=False)
    normalized_cpm = _normalize_cpm(cpm)
    if normalized_cpm is None or float(normalized_cpm) <= 0:
        raise ValueError("CPM must be numeric and greater than 0.")

    record = {
        "id": str(uuid4()),
        "created_at": created_at or _utc_timestamp(),
        "source_type": "manual_reference",
        "calculation_id": None,
        "calculation_name": normalized_name,
        "workbook_name": normalized_name,
        "sheet_name": None,
        "channel": normalized_channel,
        "market": _normalize_optional_text(market),
        "currency": normalized_currency,
        "cpm": normalized_cpm,
        "used_row_count": 1,
        "comment": _normalize_optional_text(comment),
    }
    observations.append(record)
    return record


def update_observation_currency(
    observations: list[dict[str, Any]],
    observation_id: str,
    currency: str,
) -> list[dict[str, Any]]:
    normalized_currency = validate_currency(currency, allow_unknown=True)
    updated = []
    found = False
    for record in observations:
        row = dict(record)
        if str(row.get("id")) == str(observation_id):
            row["currency"] = normalized_currency
            found = True
        updated.append(row)
    if not found:
        raise ValueError(f"Observation id not found: {observation_id}")
    return updated


def update_observation_from_display_row(
    observations: list[dict[str, Any]],
    observation_id: str,
    display_row: dict[str, Any],
) -> list[dict[str, Any]]:
    normalized_channel = _normalize_optional_text(display_row.get("Channel"))
    if normalized_channel not in SUPPORTED_CHANNELS:
        raise ValueError(f"Channel must be one of: {', '.join(SUPPORTED_CHANNELS)}")

    normalized_currency = validate_currency(display_row.get("Currency"), allow_unknown=True)
    normalized_cpm = _normalize_cpm(display_row.get("CPM"))
    if normalized_cpm is None or float(normalized_cpm) <= 0:
        raise ValueError("CPM must be numeric and greater than 0.")

    updated = []
    found = False
    for record in observations:
        row = dict(record)
        if str(row.get("id")) == str(observation_id):
            if "Workbook" in display_row:
                row["workbook_name"] = _normalize_optional_text(display_row.get("Workbook"))
            if "Sheet" in display_row:
                row["sheet_name"] = _normalize_optional_text(display_row.get("Sheet"))
            row["channel"] = normalized_channel
            row["currency"] = normalized_currency
            row["cpm"] = normalized_cpm
            if "Comment" in display_row:
                row["comment"] = _normalize_optional_text(display_row.get("Comment"))
            if row.get("source_type") == "manual_reference" and row["workbook_name"]:
                row["calculation_name"] = row["workbook_name"]
            found = True
        updated.append(row)
    if not found:
        raise ValueError(f"Observation id not found: {observation_id}")
    return updated


def build_full_library_display_rows(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in observations:
        rows.append(
            {
                "Workbook": record.get("workbook_name"),
                "Sheet": record.get("sheet_name"),
                "Channel": record.get("channel"),
                "Currency": normalize_currency(record.get("currency"), allow_unknown=True),
                "CPM": _normalize_cpm(record.get("cpm")),
                "Comment": record.get("comment"),
            }
        )
    return rows
