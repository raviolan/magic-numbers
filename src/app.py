from __future__ import annotations

import base64
import csv
import io
import json
import math
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import streamlit as st

from calculation_engine import load_normalized_models
from cpm_library import (
    CURRENCY_UNKNOWN,
    FULL_LIBRARY_VISIBLE_COLUMNS,
    SUPPORTED_CHANNELS,
    SUPPORTED_CURRENCIES,
    add_manual_reference_cpm,
    approve_calculation,
    build_full_library_display_rows,
    get_currency_channel_medians,
    infer_reference_currency,
    load_approved_calculations,
    load_cpm_observations,
    save_cpm_observations,
    seed_reference_cpm_observations,
    summarize_cpm_library_by_currency_and_channel,
    update_observation_from_display_row,
)
from optimizer import (
    INPUT_PATH,
    DEFAULT_BEAM_WIDTH,
    DEFAULT_EXACT_MAX_STATES,
    DEFAULT_TOP_N,
    VALID_PROFILE_TIERS,
    render_optimizer_markdown,
    run_optimizer_for_models,
)
from cpm_reference_import import import_reference_cpm_rows, preview_reference_cpm_import
from ui_model_adapter import (
    MANUAL_FEE_MODES,
    SIMPLIFIED_FIXED_BUDGETS,
    SIMPLIFIED_FIXED_CPMS,
    SIMPLIFIED_MANUAL_CHANNELS,
    SIMPLIFIED_OPTIMIZATION_FOCUS_LARGER_PROFILES,
    SIMPLIFIED_OPTIMIZATION_FOCUS_MANY_PROFILES,
    SIMPLIFIED_OPTIMIZATION_FOCUS_OPTIONS,
    build_simplified_budget_setup,
    DEFAULT_MANUAL_FEE_MODE,
    DEFAULT_AGENCY_FEE_PERCENT_TEXT,
    DEFAULT_PAID_MEDIA_PERCENT_TEXT,
    DEFAULT_PAID_MEDIA_INCLUDED,
    DEFAULT_SELECTED_MANUAL_CHANNELS,
    DEFAULT_PROFILE_FEE_DEDUCTION_PERCENT,
    MAX_MANUAL_FEE_COMBINATIONS,
    build_manual_campaign_model,
    build_fee_paid_combinations,
    deduction_percent_to_multiplier,
    evaluate_fee_paid_combinations,
    generate_profile_rows,
    parse_channel_percentage_split,
    parse_channel_split,
    normalize_selected_channels,
    resolve_project_cpms,
    resolve_fee_candidates,
    choose_option_for_fill_view,
    format_display_number,
    parse_friendly_amount,
    profile_size_to_k_display,
    validate_rows_use_selected_channels,
    validate_project_cpms_for_rows,
)
from results_view_helpers import (
    build_option_quick_compare_cards,
    build_diff_status,
    build_simplified_fill_rows,
    format_option_label,
    select_option_label,
    tier_mix_by_channel_lines,
    translate_result_note,
)
from option_eligibility import is_option_diff_recommendable

APP_ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = APP_ROOT / "assets" / "fonts"
GYST_KURSIV_FONT_PATH = FONT_DIR / "Gyst kursiv.otf"
UPGRADE_FONT_PATH = FONT_DIR / "Upgrade.38091.otf"
UPGRADE_CAPTION_FONT_PATH = FONT_DIR / "Upgrade.38095.otf"

UI_TRANSLATIONS = {
    "sv": {
        "page_title": "Magisk kalkyl",
        "app_caption": "Generera kalkyler för enklare kundprojekt",
        "campaign_setup_title": "1. Kampanjregler",
        "campaign_setup_description": "Välj budgetnivå, paid och optimering för profiler.",
        "channels_title": "2. Kanaler",
        "channels_description": "Välj mellan tiktok och instagram.",
        "optional_split": "Kanaluppdelning",
        "current_setup_title": "3. Förhandsgranska detaljer (frivilligt)",
        "current_setup_caption": "",
        "optimization_focus_label": "Optimera kampanjen för",
        "focus_many_profiles": "så många profiler som möjligt",
        "focus_larger_profiles": "så stora profiler som möjligt",
        "run_optimizer_title": "4. Kör kalkyl",
        "run_optimizer_description": "Du kommer få tre förslag att välja mellan",
        "run_optimizer_button": "Kör kalkyl",
    },
    "en": {
        "page_title": "Magic Numbers",
        "app_caption": "Simplified manual campaign builder with deterministic profile-size optimization.",
        "campaign_setup_title": "1. Campaign setup",
        "campaign_setup_description": "Choose the campaign budget and paid amplification treatment.",
        "channels_title": "2. Channels",
        "channels_description": "Select Instagram and/or TikTok for generated profile rows.",
        "optional_split": "Optional percentage split",
        "current_setup_title": "3. Current setup",
        "current_setup_caption": "Quick check before running the optimizer.",
        "optimization_focus_label": "Optimize for",
        "focus_many_profiles": "Many profiles",
        "focus_larger_profiles": "Larger profile sizes",
        "run_optimizer_title": "4. Run optimizer",
        "run_optimizer_description": "Generate three deterministic recommendation options.",
        "run_optimizer_button": "Run optimizer",
    },
}


def _ui_language_from_url(url: str | None) -> str:
    if not url:
        return "sv"
    path = urlparse(str(url)).path
    return "en" if "/en/" in f"{path}/" else "sv"


def _ui_text(language: str, key: str) -> str:
    return UI_TRANSLATIONS.get(language, UI_TRANSLATIONS["sv"]).get(key, UI_TRANSLATIONS["en"].get(key, key))


def _optimization_focus_display_label(language: str, focus: str) -> str:
    if focus == SIMPLIFIED_OPTIMIZATION_FOCUS_MANY_PROFILES:
        return _ui_text(language, "focus_many_profiles")
    if focus == SIMPLIFIED_OPTIMIZATION_FOCUS_LARGER_PROFILES:
        return _ui_text(language, "focus_larger_profiles")
    return str(focus)


def _format_cpm(value: float | int | None) -> str:
    return format_display_number(value)


def _mround_to_5(value: float | int | None) -> float | int | None:
    if value is None:
        return None
    scaled = float(value) / 5.0
    return math.floor(scaled + 0.5) * 5


def _format_table_rows(rows: list[dict]) -> list[dict]:
    formatted_rows: list[dict] = []
    for row in rows:
        formatted_rows.append(
            {
                key: (
                    format_display_number(value)
                    if isinstance(value, (int, float)) and not isinstance(value, bool)
                    else value
                )
                for key, value in row.items()
            }
        )
    return formatted_rows


def _font_data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:font/otf;base64,{encoded}"


def inject_app_css() -> None:
    gyst_kursiv_url = _font_data_url(GYST_KURSIV_FONT_PATH)
    upgrade_url = _font_data_url(UPGRADE_FONT_PATH)
    upgrade_caption_url = _font_data_url(UPGRADE_CAPTION_FONT_PATH)
    st.markdown(
        f"""
        <style>
        @font-face {{
            font-family: 'Nine Gyst Kursiv';
            src: url("{gyst_kursiv_url}") format('opentype');
            font-weight: 400;
            font-style: italic;
            font-display: swap;
        }}
        @font-face {{
            font-family: 'Nine Upgrade';
            src: url("{upgrade_url}") format('opentype');
            font-weight: 400;
            font-style: normal;
            font-display: swap;
        }}
        @font-face {{
            font-family: 'Nine Upgrade Caption';
            src: url("{upgrade_caption_url}") format('opentype');
            font-weight: 400;
            font-style: normal;
            font-display: swap;
        }}
        html,
        body,
        .stApp,
        .stApp p,
        .stApp span:not([class*="material"]):not([data-testid*="stIcon"]),
        .stApp label,
        .stApp li,
        .stApp th,
        .stApp td,
        div[data-testid="stAppViewContainer"],
        div[data-testid="stSidebar"],
        div[data-baseweb],
        button,
        input,
        textarea,
        select,
        label,
        table {{
            font-family: 'Nine Upgrade', Arial, sans-serif !important;
        }}
        .stApp {{
            background: #3b3821;
            color: #3b3821;
        }}
        div[data-testid="stAppViewContainer"],
        section[data-testid="stSidebar"],
        header[data-testid="stHeader"] {{
            background: #3b3821;
        }}
        .stApp p,
        .stApp li,
        .stApp label,
        .stApp span:not([class*="material"]):not([data-testid*="stIcon"]),
        .stMarkdown,
        .stMarkdown p,
        div[data-testid="stMarkdownContainer"],
        div[data-testid="stMarkdownContainer"] p,
        div[data-testid="stWidgetLabel"],
        div[data-testid="stWidgetLabel"] p,
        div[data-baseweb="select"] span,
        div[data-baseweb="input"] input,
        div[data-baseweb="textarea"] textarea {{
            color: #3b3821 !important;
        }}
        .app-caption {{
            color: #f9e9d4;
            font-size: 0.92rem;
            margin-bottom: 1rem;
        }}
        div[data-testid="stExpander"] {{
            position: relative;
            z-index: 1;
            background: #f9e9d4 !important;
            border-radius: 8px;
        }}
        div[data-testid="stExpander"] details {{
            background: #f9e9d4 !important;
            border-radius: 8px !important;
            overflow: hidden;
        }}
        div[data-testid="stExpander"] summary,
        div[data-testid="stExpander"] details > div {{
            position: relative;
            z-index: 2;
            background: #f9e9d4 !important;
        }}
        """
        + """
        .section-card {
            border: 1px solid #e5e7eb;
            border-radius: 14px;
            padding: 0.9rem 1rem 1rem 1rem;
            margin-bottom: 0.9rem;
            background: #f9e9d4;
        }
        .soft-green { border-left: 6px solid #9ae6b4; background: #f9e9d4; }
        .soft-blue { border-left: 6px solid #90cdf4; background: #f9e9d4; }
        .soft-purple { border-left: 6px solid #d6bcfa; background: #f9e9d4; }
        .soft-yellow { border-left: 6px solid #f6e05e; background: #f9e9d4; }
        .soft-gray { border-left: 6px solid #cbd5e0; background: #f9e9d4; }
        .section-title { font-weight: 700; margin-bottom: 0.15rem; }
        .section-caption {
            color: #4a5568;
            font-family: 'Nine Upgrade Caption', 'Nine Upgrade', Arial, sans-serif !important;
            font-size: 0.92rem;
            margin-bottom: 0.55rem;
        }
        .status-badge {
            display: inline-block;
            padding: 0.15rem 0.5rem;
            border-radius: 999px;
            font-size: 0.8rem;
            border: 1px solid #d1d5db;
            background: #f8fafc;
            margin-right: 0.35rem;
            margin-bottom: 0.25rem;
        }
        .hero-card {
            border-radius: 14px;
            padding: 0.9rem 1rem;
            border: 1px solid #d1d5db;
            margin-bottom: 0.75rem;
            background: #f9e9d4;
        }
        .hero-positive { background: #f5fff8; border-color: #b7e4c7; }
        .hero-negative { background: #fff8f1; border-color: #f6ad55; }
        .hero-neutral { background: #f7fbff; border-color: #bfdbfe; }
        .hero-kpi {
            font-size: 2rem;
            font-weight: 800;
            line-height: 1.1;
            margin: 0.15rem 0 0.25rem 0;
        }
        .metric-card {
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 0.6rem 0.7rem;
            background: #f9e9d4;
            margin-bottom: 0.4rem;
        }
        .metric-label { font-size: 0.78rem; color: #4b5563; margin-bottom: 0.2rem; }
        .metric-value { font-size: 1.05rem; font-weight: 700; }
        .chip {
            display: inline-block;
            border: 1px solid #d1d5db;
            border-radius: 999px;
            padding: 0.2rem 0.55rem;
            margin: 0 0.35rem 0.35rem 0;
            background: #f8fafc;
            font-size: 0.8rem;
        }
        .option-click-area {
            position: relative;
            border-radius: 8px;
            padding: 0.65rem 0.7rem;
            width: 100%;
            box-sizing: border-box;
            min-height: 215px;
            margin-bottom: 0.45rem;
            overflow: visible;
            overflow-wrap: anywhere;
            word-break: normal;
        }
        .option-click-selected {
            border: 1px solid #16a34a;
            background: #f0fdf4;
            color: #3b3821;
        }
        .option-click-positive-buffer {
            border: 1px solid #d1d5db;
            background: #fbf1e4;
            color: #3b3821;
        }
        .option-click-unselected {
            border: 1px solid #d1d5db;
            background: #fbf1e4;
            color: #3b3821;
        }
        .option-click-disabled {
            border: 1px solid transparent;
            background: #f3f4f6;
            color: #6b7280;
            opacity: 0.72;
        }
        .option-click-unselected:hover {
            background: #fff7ed;
            cursor: pointer;
        }
        .option-click-positive-buffer:hover {
            background: #fff7ed;
            cursor: pointer;
        }
        .option-click-selected:hover {
            background: #dcfce7;
            cursor: pointer;
        }
        .option-click-disabled:hover {
            background: #f3f4f6;
            cursor: default;
        }
        .option-click-title {
            font-weight: 700;
            margin-bottom: 0.35rem;
            padding-right: 0.25rem;
        }
        .option-summary-title {
            font-weight: 700;
            margin-bottom: 0.25rem;
        }
        .option-summary-line {
            font-size: 0.9rem;
            margin-bottom: 0.22rem;
        }
        div[class*="st-key-optionselect_"] {
            min-width: 0;
            width: 100%;
            box-sizing: border-box;
        }
        div[class*="st-key-optionselect_selected_"] div[data-testid="stButton"] button {
            background: #f0fc03 !important;
            border-color: #f0fc03 !important;
            color: #3b3821 !important;
        }
        div[class*="st-key-optionselect_selected_"] div[data-testid="stButton"] button:hover,
        div[class*="st-key-optionselect_selected_"] div[data-testid="stButton"] button:focus {
            background: #e1eb00 !important;
            border-color: #e1eb00 !important;
            color: #3b3821 !important;
        }
        div[class*="st-key-optionselect_unselected_"] div[data-testid="stButton"] button {
            background: #fbf1e4 !important;
            border-color: #d1d5db !important;
            color: #3b3821 !important;
        }
        div[class*="st-key-optionselect_unselected_"] div[data-testid="stButton"] button:hover,
        div[class*="st-key-optionselect_unselected_"] div[data-testid="stButton"] button:focus {
            background: #fff7ed !important;
            border-color: #cbd5e0 !important;
            color: #3b3821 !important;
        }
        .st-key-cardresultscomparison div[data-testid="column"] {
            min-width: 0;
        }
        .section-banner {
            border-radius: 10px;
            padding: 0.55rem 0.7rem;
            margin-bottom: 0.65rem;
            border: 1px solid #e5e7eb;
            background: #f9e9d4;
        }
        .st-key-cardbudget,
        .st-key-cardresultsrecommendation,
        .st-key-cardapproval {
            background: #f9e9d4;
            border: 1px solid #b7e4c7;
            border-radius: 14px;
            padding: 0.75rem 0.85rem 0.85rem 0.85rem;
            margin-bottom: 0.9rem;
        }
        .st-key-cardchannels,
        .st-key-cardcurrentsetup {
            background: #f9e9d4;
            border: 1px solid #bfdbfe;
            border-radius: 14px;
            padding: 0.75rem 0.85rem 0.85rem 0.85rem;
            margin-bottom: 0.9rem;
        }
        .st-key-cardcpmsetup {
            background: #f9e9d4;
            border: 1px solid #d6bcfa;
            border-radius: 14px;
            padding: 0.75rem 0.85rem 0.85rem 0.85rem;
            margin-bottom: 0.9rem;
        }
        .st-key-cardprofilestructure,
        .st-key-cardprofilerows,
        .st-key-cardresultsfill {
            background: #f9e9d4;
            border: 1px solid #f6e05e;
            border-radius: 14px;
            padding: 0.75rem 0.85rem 0.85rem 0.85rem;
            margin-bottom: 0.9rem;
        }
        .st-key-cardoptimizersettings,
        .st-key-cardresultsdetails,
        .st-key-cardresultsdiagnostics,
        .st-key-carddownloads {
            background: #f9e9d4;
            border: 1px solid #d1d5db;
            border-radius: 14px;
            padding: 0.75rem 0.85rem 0.85rem 0.85rem;
            margin-bottom: 0.9rem;
        }
        .st-key-cardresultscomparison {
            background: #f9e9d4;
            border: 1px solid #d1d5db;
            border-radius: 14px;
            padding: 0.75rem 0.85rem 1.75rem 0.85rem;
            margin-bottom: 0.9rem;
            overflow: visible;
        }
        .st-key-cardrunoptimizer {
            background: #f9e9d4;
            border: 3px solid #f0fc03;
            border-radius: 14px;
            padding: 0.75rem 0.85rem 0.85rem 0.85rem;
            margin-bottom: 0.9rem;
        }
        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div,
        div[data-baseweb="textarea"] > div,
        div[data-testid="stNumberInput"] div[data-baseweb="input"] > div,
        div[data-testid="stTextInput"] div[data-baseweb="input"] > div,
        div[data-testid="stTextArea"] div[data-baseweb="textarea"] > div {
            background: #fbf1e4 !important;
            border: 1px solid #cbd5e0 !important;
            border-radius: 8px !important;
            box-shadow: none !important;
        }
        div[data-baseweb="input"] input,
        div[data-baseweb="select"] input,
        div[data-baseweb="textarea"] textarea {
            background: #fbf1e4 !important;
            color: #3b3821 !important;
        }
        div[data-baseweb="input"] > div:focus-within,
        div[data-baseweb="select"] > div:focus-within,
        div[data-baseweb="textarea"] > div:focus-within {
            border: 1px solid #93c5fd !important;
            box-shadow: 0 0 0 1px rgba(147, 197, 253, 0.35) !important;
        }
        div[data-testid="stDataEditor"] [data-testid="stDataFrameResizable"] div[role="gridcell"] {
            background: #fbf1e4 !important;
        }
        .magic-title,
        .magic-title * {
            font-family: 'Nine Gyst Kursiv', 'Nine Upgrade', Arial, sans-serif !important;
            color: #f0fc03 !important;
            font-style: italic !important;
            font-weight: 400 !important;
        }
        .magic-title {
            display: block;
            margin: 0 0 0.35rem 0;
            line-height: 1.05;
            font-size: clamp(2.5rem, 8vw, 5.25rem);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _section_header(title: str, description: str, tone_class: str = "soft-gray") -> None:
    st.markdown(
        f"""
        <div class="section-banner {tone_class}">
          <div class="section-title">{title}</div>
          <div class="section-caption">{description}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_badges(labels: list[str]) -> None:
    if not labels:
        return
    badges = "".join([f'<span class="status-badge">{label}</span>' for label in labels])
    st.markdown(badges, unsafe_allow_html=True)


def _render_metric_card(label: str, value: str, caption: str | None = None) -> None:
    caption_html = f'<div class="section-caption" style="margin:0.25rem 0 0 0;">{caption}</div>' if caption else ""
    st.markdown(
        f"""
        <div class="metric-card">
          <div class="metric-label">{label}</div>
          <div class="metric-value">{value}</div>
          {caption_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _get_currency_median_cpms(observations: list[dict], currency: str) -> dict[str, float]:
    medians = get_currency_channel_medians(observations)
    return medians.get(currency, {})


def _apply_library_medians_to_state(currency: str, observations: list[dict], selected_channels: list[str] | None = None) -> None:
    medians = _get_currency_median_cpms(observations, currency)
    selected = normalize_selected_channels(selected_channels) if selected_channels is not None else ["Instagram", "TikTok", "YouTube"]
    for channel, key in (
        ("Instagram", "project_cpm_instagram"),
        ("TikTok", "project_cpm_tiktok"),
        ("YouTube", "project_cpm_youtube"),
    ):
        if channel in selected:
            value = medians.get(channel)
            rounded = _mround_to_5(value) if value is not None else None
            st.session_state[key] = format_display_number(rounded) if rounded is not None else ""


def _build_setup_summary_rows(
    *,
    budget: float | None,
    agency_amount: float | None,
    paid_amount: float | None,
    agency_text: str,
    paid_text: str,
    paid_media_included: bool,
    profile_fee_deduction_percent: float,
    total_profiles: int,
    selected_channels: list[str],
    channel_split_summary: str,
    cpm_currency: str,
    project_cpms: dict[str, float | None],
    generated_row_count: int | None = None,
    row_status_text: str | None = None,
) -> list[dict[str, str]]:
    available_target = None
    if budget is not None and agency_amount is not None and paid_amount is not None:
        base = budget - agency_amount - (paid_amount if paid_media_included else 0.0)
        available_target = base * (1 - profile_fee_deduction_percent / 100.0)

    cpm_rows = []
    for channel in selected_channels:
        cpm_rows.append({"Field": f"{channel} CPM", "Value": format_display_number(project_cpms.get(channel))})

    rows = [
        {"Field": "Total budget", "Value": format_display_number(budget) if budget is not None else "Invalid budget"},
        {"Field": "Agency fee", "Value": agency_text},
        {"Field": "Paid media", "Value": paid_text},
        {"Field": "Paid media included in target", "Value": "yes" if paid_media_included else "no"},
        {"Field": "Profile fee deduction", "Value": f"{profile_fee_deduction_percent:.1f}%"},
        {"Field": "Available profile-fee target", "Value": format_display_number(available_target) if available_target is not None else "varies by setup"},
        {"Field": "Total profiles", "Value": str(total_profiles)},
        {"Field": "Selected channels", "Value": ", ".join(selected_channels)},
        {"Field": "Channel split", "Value": channel_split_summary},
        {"Field": "CPM currency", "Value": cpm_currency},
    ] + cpm_rows
    if generated_row_count is not None:
        rows.append({"Field": "Generated profile rows", "Value": str(generated_row_count)})
        if row_status_text:
            rows.append({"Field": "Row status", "Value": row_status_text})
    return rows


def _channel_counts_from_rows(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        channel = str(row.get("channel") or "").strip()
        if not channel:
            continue
        counts[channel] = counts.get(channel, 0) + 1
    return counts


def _profile_row_status(requested_total_profiles: int, rows: list[dict]) -> dict[str, object]:
    generated = len(rows)
    counts = _channel_counts_from_rows(rows)
    summary = ", ".join(f"{channel} x{count}" for channel, count in sorted(counts.items())) if counts else "none"
    return {
        "requested_total_profiles": int(requested_total_profiles),
        "generated_row_count": int(generated),
        "matches_requested_total": int(generated) == int(requested_total_profiles),
        "channel_summary": summary,
    }


def _profile_structure_signature(
    *,
    total_profiles: int,
    selected_channels: list[str],
    instagram_count: str,
    tiktok_count: str,
    youtube_count: str,
    project_cpms: dict[str, float | None],
) -> tuple:
    return (
        int(total_profiles),
        tuple(sorted(selected_channels)),
        instagram_count.strip(),
        tiktok_count.strip(),
        youtube_count.strip(),
        tuple((channel, project_cpms.get(channel)) for channel in ("Instagram", "TikTok", "YouTube")),
    )


def _current_setup_row_background(field: str) -> str:
    if field == "Total budget":
        return "#f0fdf4"  # light green
    if field.startswith("Agency fee"):
        return "#fff7ed"  # light orange
    if field.startswith("Paid media"):
        return "#faf5ff"  # light purple
    if field == "Profile fee deduction":
        return ""
    if field in {"Total profiles", "Selected channels", "Channel split"}:
        return "#fffbeb"  # light yellow
    if field.endswith("CPM"):
        return "#fffbeb"  # light yellow
    return ""


def _style_current_setup_rows(frame: pd.DataFrame) -> pd.io.formats.style.Styler:
    def _row_style(row: pd.Series) -> list[str]:
        background = _current_setup_row_background(str(row.get("Field", "")))
        if not background:
            return [""] * len(row)
        return [f"background-color: {background}"] * len(row)

    return frame.style.apply(_row_style, axis=1)


def result_to_fill_csv(result: dict) -> str:
    recommended = next(option for option in result["options"] if option["option_label"] == result["recommended_option_label"])
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "profile_size_cell",
            "previous_profile_size",
            "recommended_profile_size",
            "channel",
            "market",
            "cpm",
            "activations",
            "row_fee",
        ],
    )
    writer.writeheader()
    for row in recommended["fill_instructions"]:
        writer.writerow(
            {
                "profile_size_cell": row.get("profile_size_cell") or "manual row",
                "previous_profile_size": row.get("previous_profile_size"),
                "recommended_profile_size": row.get("recommended_profile_size"),
                "channel": row.get("channel"),
                "market": row.get("market"),
                "cpm": row.get("cpm"),
                "activations": row.get("activations"),
                "row_fee": row.get("row_fee"),
            }
        )
    return buffer.getvalue()


def _recommended_option(result: dict) -> dict:
    return next(option for option in result["options"] if option["option_label"] == result["recommended_option_label"])


def _coalesce(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _format_amount_with_percent(amount, percent) -> str:
    if amount in (None, ""):
        return "0"
    amount_text = format_display_number(amount)
    if percent is None:
        return amount_text
    return f"{amount_text} ({float(percent):.2f}%)"


def _build_result_budget_view(
    result: dict,
    manual_context: dict | None = None,
    budget_inputs: dict | None = None,
) -> dict:
    breakdown = result.get("budget_breakdown") if isinstance(result.get("budget_breakdown"), dict) else {}
    budget_inputs = budget_inputs if isinstance(budget_inputs, dict) else {}
    manual_context = manual_context if isinstance(manual_context, dict) else {}

    budget = _coalesce(breakdown.get("budget"), budget_inputs.get("budget"), manual_context.get("budget"))
    agency_fee = _coalesce(
        breakdown.get("agency_fee"),
        budget_inputs.get("agency_fee"),
        manual_context.get("selected_agency_fee_amount"),
    )
    paid_media = _coalesce(
        breakdown.get("paid_media"),
        budget_inputs.get("paid_media"),
        manual_context.get("selected_paid_media_amount"),
        manual_context.get("paid_media"),
    )
    paid_media_included = _coalesce(
        breakdown.get("paid_media_included"),
        budget_inputs.get("paid_media_included"),
        manual_context.get("paid_media_included"),
    )
    multiplier = _coalesce(
        breakdown.get("profile_budget_target_multiplier"),
        None if budget_inputs.get("profile_fee_deduction_percent") is None else 1 - float(budget_inputs["profile_fee_deduction_percent"]) / 100.0,
        None if manual_context.get("profile_fee_deduction_percent") is None else 1 - float(manual_context["profile_fee_deduction_percent"]) / 100.0,
    )
    profile_budget_target = _coalesce(
        breakdown.get("profile_budget_target"),
        budget_inputs.get("profile_budget_target"),
        result.get("profile_budget_target"),
    )
    agency_fee_percent = _coalesce(
        budget_inputs.get("agency_fee_percent"),
        manual_context.get("selected_agency_fee_percent"),
    )
    paid_media_percent = _coalesce(
        budget_inputs.get("paid_media_percent"),
        manual_context.get("selected_paid_media_percent"),
    )

    detailed_budget_rows: list[dict[str, str]] = []
    if budget is not None and agency_fee is not None:
        paid_media_included_bool = bool(paid_media_included)
        paid_media_amount = float(paid_media or 0)
        included_paid_media = paid_media_amount if paid_media_included_bool else 0.0
        remaining_profile_fee_base = float(budget) - float(agency_fee) - included_paid_media
        deduction_percent = (1 - float(multiplier)) * 100 if multiplier is not None else None
        if deduction_percent is not None:
            deduction_amount = remaining_profile_fee_base * (deduction_percent / 100.0)
            available_profile_fee_target = (
                float(profile_budget_target)
                if profile_budget_target is not None
                else remaining_profile_fee_base - deduction_amount
            )
            deduction_label = f"Profilavdrag / extra byråarvode, {deduction_percent:.1f}%"
            deduction_value = format_display_number(-deduction_amount)
        else:
            available_profile_fee_target = profile_budget_target
            deduction_label = "Profilavdrag / extra byråarvode"
            deduction_value = "saknas"
        detailed_budget_rows = [
            {"Post": "Total budget", "Värde": format_display_number(budget)},
            {"Post": "Byråarvode", "Värde": format_display_number(-float(agency_fee))},
            {"Post": "Paid media inkluderad", "Värde": format_display_number(-included_paid_media)},
            {"Post": "Kvar före profilavdrag", "Värde": format_display_number(remaining_profile_fee_base)},
            {"Post": deduction_label, "Värde": deduction_value},
            {"Post": "Tillgänglig profilbudget", "Värde": format_display_number(available_profile_fee_target)},
        ]

    caption = None
    if manual_context:
        caption = (
            "Vald arvodesmodell: byråarvode "
            + _format_amount_with_percent(agency_fee, agency_fee_percent)
            + ", paid media "
            + _format_amount_with_percent(paid_media, paid_media_percent)
            + f", testade kombinationer: {manual_context.get('combinations_evaluated')}"
        )

    return {
        "agency_fee_text": _format_amount_with_percent(agency_fee, agency_fee_percent),
        "paid_media_text": "Ingår inte"
        if paid_media_included is False
        else _format_amount_with_percent(paid_media, paid_media_percent),
        "detailed_budget_rows": detailed_budget_rows,
        "detailed_budget_caption": caption,
    }


def _build_selectable_fill_view(result: dict, selected_option_label: str | None = None) -> dict:
    cards = build_option_quick_compare_cards(result)
    option_labels = [
        str(card["option_label"])
        for card in cards
        if card.get("option_label") and card.get("is_selectable", True)
    ]
    if not option_labels:
        option_labels = [
            str(option.get("option_label"))
            for option in result.get("options", [])
            if option.get("option_label") and is_option_diff_recommendable(option)
        ]
    recommended_label = str(result.get("recommended_option_label", ""))
    if not option_labels and recommended_label:
        option_labels = [recommended_label]
    selected_label = select_option_label(option_labels, recommended_label, selected=selected_option_label)
    selected_option = choose_option_for_fill_view(
        options=result.get("options", []),
        recommended_option_label=recommended_label,
        selected_option_label=selected_label,
    )
    selected_label = str(selected_option.get("option_label") or selected_label)
    simple_fill_rows, include_market, include_activations = build_simplified_fill_rows(
        selected_option.get("fill_instructions", [])
    )
    return {
        "cards": cards,
        "option_labels": option_labels,
        "selected_label": selected_label,
        "selected_option": selected_option,
        "simple_fill_rows": simple_fill_rows,
        "include_market": include_market,
        "include_activations": include_activations,
    }


def _main_fill_selector_key(run_id: object) -> str:
    return f"main_fill_option_selector_{run_id}"


def _set_main_fill_option(selector_key: str, option_label: str) -> None:
    st.session_state[selector_key] = option_label


def _option_has_positive_buffer_above_recommended(card: dict) -> bool:
    return float(card.get("diff", 0)) > 0 and float(card.get("delta_vs_recommended", 0)) > 0


def _option_card_click_class(card: dict, is_selected: bool) -> str:
    if not bool(card.get("is_selectable", True)):
        return "option-click-disabled"
    if is_selected:
        return "option-click-selected"
    if _option_has_positive_buffer_above_recommended(card):
        return "option-click-unselected"
    return "option-click-unselected"


def _render_downloads(payload: dict, result: dict) -> None:
    markdown = render_optimizer_markdown(payload)
    fill_csv = result_to_fill_csv(result)
    json_text = json.dumps(payload, indent=2, ensure_ascii=False)

    with st.container(border=True, key="carddownloads"):
        _section_header("Nedladdningar", "Exportera ifyllnadsinstruktioner, JSON och rapport.", "soft-gray")
        st.download_button("Ladda ner ifyllnadsinstruktioner CSV", data=fill_csv, file_name="fill_instructions.csv", mime="text/csv")
        st.download_button("Ladda ner optimeringsresultat JSON", data=json_text, file_name="optimizer_results.json", mime="application/json")
        st.download_button("Ladda ner rapport Markdown", data=markdown, file_name="optimizer_results.md", mime="text/markdown")


def render_result(
    payload: dict,
    result: dict,
    manual_context: dict | None = None,
    budget_inputs: dict | None = None,
) -> None:
    recommended = _recommended_option(result)
    budget_view = _build_result_budget_view(result, manual_context=manual_context, budget_inputs=budget_inputs)
    run_id = st.session_state.get("latest_run_data", {}).get("run_id", "current")
    fill_selector_key = _main_fill_selector_key(run_id)
    selected_from_state = st.session_state.get(fill_selector_key)
    fill_view = _build_selectable_fill_view(result, selected_from_state)

    st.markdown("### 8. Resultat")
    with st.container(border=True, key="cardresultsrecommendation"):
        _section_header("Rekommendation", "Använd detta förslag om inget annat i kundcaset väger tyngre.", "soft-blue")
        status_tone, status_text = build_diff_status(recommended.get("optimized_diff"))
        hero_class = {"positive": "hero-positive", "negative": "hero-negative", "neutral": "hero-neutral"}[status_tone]
        diff_value = format_display_number(recommended["optimized_diff"])
        diff_signed = diff_value if diff_value.startswith("-") else f"+{diff_value}"
        st.markdown(
            f"""
            <div class="hero-card {hero_class}">
              <div class="section-title">Rekommenderat förslag</div>
              <div style="font-size:1.05rem;font-weight:700;">{format_option_label(str(recommended.get("option_label")))}</div>
              <div class="hero-kpi">Diff {diff_signed}</div>
              <div class="section-caption" style="margin-bottom:0.35rem;">{status_text}</div>
              <div><strong>Byråarvode:</strong> {budget_view['agency_fee_text']}</div>
              <div><strong>Paid media:</strong> {budget_view['paid_media_text']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        for line in tier_mix_by_channel_lines(recommended.get("fill_instructions", [])):
            st.write(line)

    with st.container(border=True, key="cardresultscomparison"):
        _section_header("Jämför förslag", "Tre möjliga upplägg att välja mellan.", "soft-gray")
        cards = fill_view["cards"]
        if cards:
            cols = st.columns(len(cards))
            for idx, card in enumerate(cards):
                with cols[idx]:
                    option_label = str(card.get("option_label"))
                    is_selected = option_label == str(fill_view["selected_label"])
                    delta = float(card["delta_vs_recommended"])
                    if delta > 0:
                        delta_text = f"{format_display_number(delta)} mer marginal än rekommenderat förslag"
                    elif delta < 0:
                        delta_text = f"{format_display_number(abs(delta))} närmare än rekommenderat förslag"
                    elif not is_selected:
                        delta_text = "Samma diff som rekommenderat förslag"
                    else:
                        delta_text = ""
                    is_selectable = bool(card.get("is_selectable", True))
                    replacement_body_text = card.get("replacement_body_text")
                    click_class = _option_card_click_class(card, is_selected)
                    tier_lines = "".join(
                        f'<div class="option-summary-line">{line}</div>'
                        for line in card["tier_mix_lines"]
                    )
                    delta_line = f'<div class="option-summary-line">{delta_text}</div>' if delta_text else ""
                    option_select_key_prefix = "optionselect_selected" if is_selected else "optionselect_unselected"
                    with st.container(key=f"{option_select_key_prefix}_{run_id}_{idx}"):
                        if is_selectable:
                            card_body = f"""
                              <div class="option-summary-line"><strong>Diff:</strong> {format_display_number(card['diff'])}</div>
                              {delta_line}
                              <div class="option-summary-line"><strong>Avvägning:</strong> {card['tradeoff']}</div>
                              {tier_lines}
                            """
                        else:
                            card_body = f'<div class="option-summary-line">{replacement_body_text}</div>'
                        st.markdown(
                            f"""
                            <div class="option-click-area {click_class}">
                              <div class="option-click-title">{card['title']}</div>
                              {card_body}
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        if is_selectable:
                            st.button(
                                "Välj förslag",
                                key=f"{fill_selector_key}_{idx}_{option_label}",
                                use_container_width=True,
                                type="secondary",
                                on_click=_set_main_fill_option,
                                args=(fill_selector_key, option_label),
                            )

    with st.container(border=True, key="cardresultsfill"):
        selected_display_label = format_option_label(fill_view["selected_label"])
        _section_header(
            f"Ifyllnadsinstruktioner: {selected_display_label}",
            "Rekommenderade profilval för kalkylen.",
            "soft-yellow",
        )
        st.dataframe(_format_table_rows(fill_view["simple_fill_rows"]), use_container_width=True)

    with st.container(border=True, key="cardresultsactions"):
        _section_header("Åtgärder och detaljer", "Nedladdningar och tekniska detaljer.", "soft-gray")
        with st.expander("Åtgärder och detaljer", expanded=False):
            st.markdown("**Nedladdningar**")
            _render_downloads(payload, result)
            if result.get("closest_positive_diff_option_label") is None:
                st.caption("Inget alternativ med positiv diff hittades bland sparade kandidater.")
            with st.expander("Detaljerade ifyllnadsinstruktioner", expanded=False):
                option_labels = [str(option.get("option_label")) for option in result.get("options", []) if option.get("option_label")]
                selected_default = select_option_label(option_labels, str(result.get("recommended_option_label", "")))
                selected_fill_label = st.selectbox(
                    "Förslag",
                    options=option_labels,
                    index=option_labels.index(selected_default) if selected_default in option_labels else 0,
                    format_func=format_option_label,
                    key=f"detailed_fill_option_selector_{result.get('source', {}).get('workbook_name', 'manual')}_{result.get('source', {}).get('sheet_name', 'manual')}",
                )
                detailed_option = choose_option_for_fill_view(
                    options=result.get("options", []),
                    recommended_option_label=result.get("recommended_option_label", ""),
                    selected_option_label=selected_fill_label,
                )
                fill_rows = []
                for row in detailed_option.get("fill_instructions", []):
                    fill_rows.append(
                        {
                            "Cell": row.get("profile_size_cell") or "manuell rad",
                            "Tidigare storlek": row.get("previous_profile_size"),
                            "Rekommenderad storlek (K)": profile_size_to_k_display(row.get("recommended_profile_size")),
                            "Kanal": row.get("channel"),
                            "Marknad": row.get("market"),
                            "CPM": row.get("cpm"),
                            "Aktiveringar": row.get("activations"),
                            "Radkostnad": row.get("row_fee"),
                        }
                    )
                st.dataframe(_format_table_rows(fill_rows), use_container_width=True)

            with st.expander("Detaljerad jämförelse", expanded=False):
                comparison_rows = []
                for row in result["option_comparison"]:
                    comparison_rows.append(
                        {
                            "Förslag": format_option_label(str(row.get("option_label"))),
                            "Rank": row.get("recommendation_rank"),
                            "Diff": row.get("optimized_diff"),
                            "Profilkostnad totalt": row.get("profile_fee_sum"),
                            "Storleksfördelning": row.get("tier_counts"),
                            "Totala visningar": row.get("total_impressions"),
                            "Varningar": [translate_result_note(item) for item in row.get("strategic_warnings", [])],
                            "Förbättrar nuvarande upplägg": row.get("improves_on_baseline"),
                        }
                    )
                st.dataframe(_format_table_rows(comparison_rows), use_container_width=True)

            if budget_view["detailed_budget_rows"]:
                with st.expander("Detaljerad budgetfördelning", expanded=False):
                    st.table(budget_view["detailed_budget_rows"])
                    if budget_view["detailed_budget_caption"]:
                        st.caption(budget_view["detailed_budget_caption"])

            with st.expander("Diagnostik", expanded=False):
                diagnostics = result["search_diagnostics"]
                st.write(
                    f"Sökstrategi: {diagnostics['search_method']} "
                    f"(bounded={diagnostics['bounded_search']}, approximate={diagnostics['approximate_search']}, "
                    f"global_optimality_guaranteed={diagnostics['global_optimality_guaranteed']})"
                )
                st.write(
                    "Tillåtna profilstorlekar: "
                    + ", ".join(f"{int(value/1000)}K" for value in diagnostics.get("allowed_tiers", list(VALID_PROFILE_TIERS)))
                )
                st.write(
                    f"Beam width: {diagnostics['beam_width']}, expanderade tillstånd: {diagnostics['expanded_state_count']}, "
                    f"sparade tillstånd: {diagnostics['retained_state_count']}"
                )
                if diagnostics.get("search_method") == "exact_fee_sum_search":
                    st.write(f"Exakta tillstånd: {diagnostics.get('exact_state_count')} / {diagnostics.get('exact_state_limit')}")
                if not diagnostics.get("current_baseline_available", True):
                    st.warning(
                        "Nuvarande upplägg saknas eftersom en eller flera profilstorlekar var tomma, ogiltiga eller utanför tillåtna storlekar."
                    )
            with st.expander("Poängfördelning för rekommendation", expanded=False):
                st.json(result.get("recommendation_score_breakdown", {}))


def run_and_render(
    models: list,
    input_label: str,
    beam_width: int,
    top_n: int,
    allow_negative: bool,
    strategy: str,
    optimization_method: str = "fast_closest_diff",
    allowed_tiers: list[int] | None = None,
    max_exact_states: int = DEFAULT_EXACT_MAX_STATES,
    manual_context: dict | None = None,
    optimization_focus: str | None = None,
) -> tuple[dict, dict]:
    payload = run_optimizer_for_models(
        models=models,
        input_label=input_label,
        beam_width=beam_width,
        top_n=top_n,
        allow_negative=allow_negative,
        strategy=strategy,
        optimization_method=optimization_method,
        allowed_tiers=allowed_tiers,
        max_exact_states=max_exact_states,
        optimization_focus=optimization_focus,
    )
    result = payload["results"][0]
    return payload, result


def manual_rows_default() -> list[dict]:
    return [
        {
            "row_index": 1,
            "profile_size_cell": "",
            "current_profile_size": "",
            "channel": "Instagram",
            "market": "",
            "cpm": 1000,
            "activations": 1,
        },
        {
            "row_index": 2,
            "profile_size_cell": "",
            "current_profile_size": "",
            "channel": "TikTok",
            "market": "",
            "cpm": 1000,
            "activations": 1,
        },
    ]


def render_allowed_profile_sizes(section_key: str = "global") -> list[int]:
    st.markdown("**Allowed profile sizes**")
    st.caption("Choose which profile tiers the optimizer is allowed to use.")
    tier_labels = [(15000, "15K"), (35000, "35K"), (75000, "75K"), (125000, "125K"), (175000, "175K")]
    allowed_tiers: list[int] = []
    tier_cols = st.columns(len(tier_labels))
    for idx, (tier_value, label) in enumerate(tier_labels):
        key = f"{section_key}_allowed_tier_{tier_value}"
        with tier_cols[idx]:
            checked = st.checkbox(label, value=True, key=key)
        if checked:
            allowed_tiers.append(tier_value)
    return sorted(allowed_tiers)


def render_advanced_settings() -> tuple[int, int, bool, str, str, int, float]:
    with st.expander("Advanced optimizer settings", expanded=False):
        optimization_method_label = st.selectbox(
            "Optimization method",
            ["Fast closest diff", "Exact closest diff"],
            help="Fast uses bounded beam search. Exact uses deterministic fee-sum search and can be slower.",
        )
        optimization_method = "fast_closest_diff" if optimization_method_label == "Fast closest diff" else "exact_closest_diff"
        beam_width = st.number_input(
            "Beam width",
            min_value=50,
            max_value=5000,
            value=DEFAULT_BEAM_WIDTH,
            step=50,
            help="How many possible mixes the optimizer keeps while searching. Higher can be more thorough but slower.",
        )
        top_n = st.number_input(
            "Number of options to compare",
            min_value=1,
            max_value=20,
            value=DEFAULT_TOP_N,
            step=1,
            help="How many strong candidate mixes are kept for comparison in the report. Higher may show more alternatives, but usually the default is fine.",
        )
        strategy = st.selectbox(
            "Recommendation emphasis",
            ["math", "strategic"],
            help="Math prioritizes closest diff. Strategic gives more weight to sellable profile mixes.",
        )
        st.caption(
            "Fast closest diff: bounded search, approximate, no global-optimum guarantee. "
            "Exact closest diff: deterministic exact fee-sum search with a safe state limit."
        )
        max_exact_states = st.number_input(
            "Exact search max states",
            min_value=5000,
            max_value=2000000,
            value=DEFAULT_EXACT_MAX_STATES,
            step=5000,
            help="Safety guard for Exact closest diff. If exceeded, exact search stops with a warning.",
        )
        allow_negative = st.checkbox(
            "Allow negative diff",
            value=False,
            help="Allows recommendations that exceed the available profile-fee budget. Usually keep this off.",
        )
        profile_fee_deduction_percent = st.number_input(
            "Profile fee deduction (%)",
            value=float(DEFAULT_PROFILE_FEE_DEDUCTION_PERCENT),
            step=0.1,
            format="%.1f",
            help="The calculator keeps 7.5% aside from the remaining profile-fee budget. This equals the workbook's 0.925 rule.",
        )
    return (
        int(beam_width),
        int(top_n),
        bool(allow_negative),
        str(strategy),
        str(optimization_method),
        int(max_exact_states),
        float(profile_fee_deduction_percent),
    )


def _manual_mode_fee_inputs(prefix: str, default_fixed: float, default_percent: str) -> tuple[str, str | None, str | None, str | None, float]:
    mode = st.selectbox(
        f"{prefix} mode",
        list(MANUAL_FEE_MODES),
        index=list(MANUAL_FEE_MODES).index(DEFAULT_MANUAL_FEE_MODE),
        key=f"{prefix.lower().replace(' ', '_')}_mode",
    )
    fixed_amount = None
    percent_value = None
    percent_range = None
    range_step = 0.5
    if mode == "Fixed amount":
        fixed_amount = st.text_input(f"{prefix} amount", value=format_display_number(default_fixed), key=f"{prefix}_fixed")
    elif mode == "Percentage of budget":
        percent_value = st.text_input(f"{prefix} percent", value=default_percent, key=f"{prefix}_percent")
    else:
        percent_range = st.text_input(f"{prefix} percent range", value="10-15%", key=f"{prefix}_range")
        range_step = st.number_input(
            f"{prefix} range step (percentage points)",
            value=0.5,
            min_value=0.1,
            step=0.1,
            key=f"{prefix}_step",
        )
    return mode, fixed_amount, percent_value, percent_range, float(range_step)


def _load_seeded_cpm_library(models: list) -> tuple[list[dict], list[dict], str | None]:
    try:
        observations = load_cpm_observations()
        seeded, _ = seed_reference_cpm_observations(models, observations)
        if seeded != observations:
            save_cpm_observations(seeded)
        approved = load_approved_calculations()
        return seeded, approved, None
    except ValueError as error:
        return [], [], str(error)


def _render_sidebar_cpm_library(observations: list[dict], error_message: str | None) -> None:
    st.markdown("---")
    st.subheader("CPM Library")
    if error_message:
        st.error(error_message)
        return
    summary = summarize_cpm_library_by_currency_and_channel(observations)
    has_any_rows = False
    for currency in SUPPORTED_CURRENCIES:
        st.caption(f"CPM library ({currency})")
        currency_rows = summary["by_currency"].get(currency, [])
        if not currency_rows:
            st.caption(f"No {currency} observations yet.")
            continue
        has_any_rows = True
        st.table(
            [
                {
                    "Channel": row["channel"],
                    "Average": _format_cpm(_mround_to_5(row["average_cpm"])),
                    "Median": _format_cpm(_mround_to_5(row["median_cpm"])),
                }
                for row in currency_rows
            ]
        )
    if not has_any_rows:
        st.caption("CPM library is empty. Approve a calculation or add a reference CPM row.")
    unknown_count = int(summary.get("unknown_currency_observation_count", 0))
    if unknown_count > 0:
        st.caption("Some CPM observations are missing currency and are excluded from currency summaries.")

    with st.expander("Open CPM library", expanded=False):
        if not observations:
            st.caption("No CPM observations yet.")
        else:
            editable_rows = sorted(observations, key=lambda item: str(item.get("created_at") or ""), reverse=True)
            row_ids = [str(row.get("id")) for row in editable_rows]
            editor_rows = build_full_library_display_rows(editable_rows)
            edited_rows = st.data_editor(
                editor_rows,
                use_container_width=True,
                num_rows="fixed",
                key="cpm_library_editor",
                column_config={
                    "Sheet": None,
                    "Channel": st.column_config.SelectboxColumn("Channel", options=list(SUPPORTED_CHANNELS)),
                    "Currency": st.column_config.SelectboxColumn("Currency", options=[*SUPPORTED_CURRENCIES, CURRENCY_UNKNOWN]),
                    "CPM": st.column_config.NumberColumn("CPM", min_value=0.01),
                },
                column_order=[column for column in FULL_LIBRARY_VISIBLE_COLUMNS if column != "Sheet"],
            )
            edited_records = edited_rows.to_dict("records") if hasattr(edited_rows, "to_dict") else list(edited_rows)
            if st.button("Save library changes"):
                try:
                    current = load_cpm_observations()
                    if len(edited_records) != len(row_ids):
                        raise ValueError("CPM library rows changed unexpectedly during edit; reload and try again.")
                    for index, row in enumerate(edited_records):
                        obs_id = row_ids[index]
                        current = update_observation_from_display_row(current, obs_id, row)
                    save_cpm_observations(current)
                    st.success("CPM library updated.")
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
    with st.expander("Add reference CPM row", expanded=False):
        ref_name = st.text_input("Reference/project name", key="manual_reference_name")
        ref_channel = st.selectbox("Channel", options=list(SUPPORTED_CHANNELS), key="manual_reference_channel")
        ref_market = st.text_input("Market (optional)", key="manual_reference_market")
        ref_currency = st.selectbox("Currency", options=list(SUPPORTED_CURRENCIES), key="manual_reference_currency")
        ref_cpm = st.text_input("CPM", value="", key="manual_reference_cpm")
        ref_comment = st.text_area("Comment (optional)", value="", key="manual_reference_comment")

        if st.button("Add reference CPM"):
            try:
                current = load_cpm_observations()
                add_manual_reference_cpm(
                    observations=current,
                    reference_name=ref_name,
                    channel=ref_channel,
                    market=ref_market,
                    currency=ref_currency,
                    cpm=ref_cpm,
                    comment=ref_comment,
                )
                save_cpm_observations(current)
                st.success("Reference CPM row added.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))

    with st.expander("Import reference CPM sheet", expanded=False):
        import_default_path = "/Users/viola/Downloads/CPMreferenser.xlsx"
        import_path = st.text_input("Reference workbook path", value=import_default_path, key="reference_import_path")
        import_default_currency = st.selectbox(
            "Default import currency (when missing)",
            options=[*SUPPORTED_CURRENCIES, CURRENCY_UNKNOWN],
            index=0,
            key="reference_import_default_currency",
        )

        if st.button("Preview CPM reference import"):
            try:
                current = load_cpm_observations()
                preview = preview_reference_cpm_import(
                    path=import_path,
                    existing_observations=current,
                    default_currency=import_default_currency,
                )
                st.session_state.reference_import_preview = preview
            except Exception as error:
                st.error(str(error))

        preview_payload = st.session_state.get("reference_import_preview")
        if preview_payload and preview_payload.get("path") == import_path:
            counts = preview_payload.get("counts", {})
            st.caption(
                f"Preview: total={counts.get('total', 0)}, valid={counts.get('valid', 0)}, "
                f"invalid={counts.get('invalid', 0)}, duplicate={counts.get('duplicate', 0)}"
            )
            preview_rows = []
            for row in preview_payload.get("rows", []):
                preview_rows.append(
                    {
                        "status": row.get("status"),
                        "reference_name": row.get("calculation_name"),
                        "source_sheet": row.get("source_sheet"),
                        "channel": row.get("channel"),
                        "market": row.get("market"),
                        "currency": row.get("currency"),
                        "cpm": row.get("cpm"),
                        "used_row_count": row.get("used_row_count"),
                        "comment": row.get("comment"),
                        "message": row.get("validation_message"),
                    }
                )
            st.dataframe(_format_table_rows(preview_rows), use_container_width=True)

            if st.button("Import valid rows"):
                try:
                    current = load_cpm_observations()
                    import_result = import_reference_cpm_rows(
                        path=import_path,
                        existing_observations=current,
                        default_currency=import_default_currency,
                    )
                    save_cpm_observations(import_result["updated_observations"])
                    st.success(
                        f"Imported {import_result['imported_count']} rows. "
                        f"Skipped {import_result['invalid_count']} invalid and {import_result['duplicate_count']} duplicate rows."
                    )
                    st.session_state.reference_import_preview = import_result["preview"]
                    st.rerun()
                except Exception as error:
                    st.error(str(error))


def _build_budget_inputs(
    *,
    result: dict,
    budget: float,
    agency_fee_amount: float,
    paid_media_amount: float,
    paid_media_included: bool,
    profile_fee_deduction_percent: float,
    agency_fee_percent: float | None,
    paid_media_percent: float | None,
) -> dict:
    recommended = _recommended_option(result)
    return {
        "budget": budget,
        "agency_fee": agency_fee_amount,
        "agency_fee_percent": agency_fee_percent,
        "paid_media": paid_media_amount,
        "paid_media_percent": paid_media_percent,
        "paid_media_included": paid_media_included,
        "profile_fee_deduction_percent": profile_fee_deduction_percent,
        "profile_budget_target": recommended.get("profile_budget_target"),
    }


def _render_approval_section() -> None:
    run_data = st.session_state.get("latest_run_data")
    if not run_data:
        return

    result = run_data["result"]
    options = [option["option_label"] for option in result["options"]]
    recommended_label = result["recommended_option_label"]
    default_index = options.index(recommended_label) if recommended_label in options else 0
    st.session_state.setdefault("approval_calculation_name", run_data.get("default_calculation_name", ""))
    st.session_state.setdefault("approval_comment", "")
    st.session_state.setdefault("approval_option_label", recommended_label)
    st.session_state.setdefault("approval_currency", run_data.get("default_currency", "SEK"))

    with st.container(border=True, key="cardapproval"):
        _section_header("Klar att använda", "Spara valt förslag i det lokala biblioteket för godkända kalkyler.", "soft-blue")
        calculation_name = st.text_input("Kalkylnamn", key="approval_calculation_name")
        approval_currency = st.selectbox("Valuta", options=list(SUPPORTED_CURRENCIES), key="approval_currency")
        comment = st.text_area("Valfri kommentar", key="approval_comment")
        approved_option_label = st.selectbox(
            "Förslag att godkänna",
            options=options,
            index=default_index,
            key="approval_option_label",
            format_func=format_option_label,
        )

        if st.button("Godkänn / spara kalkyl"):
            if not calculation_name.strip():
                st.error("Kalkylnamn krävs innan kalkylen kan sparas.")
                return
            try:
                approval_result = approve_calculation(
                    result=result,
                    calculation_name=calculation_name,
                    comment=comment,
                    currency=approval_currency,
                    approved_option_label=approved_option_label,
                    source=run_data["source"],
                    budget_inputs=run_data["budget_inputs"],
                )
                st.success(
                    f"Godkände kalkylen '{approval_result['approved_record']['calculation_name']}'. "
                    f"Lade till {approval_result['added_cpm_observation_count']} CPM-observation(er)."
                )
                st.rerun()
            except ValueError as error:
                st.error(str(error))


def main() -> None:
    language = _ui_language_from_url(getattr(st.context, "url", None))
    st.set_page_config(page_title=_ui_text(language, "page_title"), layout="wide")
    inject_app_css()
    st.markdown(f'<div class="magic-title">{_ui_text(language, "page_title")}</div>', unsafe_allow_html=True)
    app_caption = _ui_text(language, "app_caption")
    if app_caption:
        st.markdown(f'<div class="app-caption">{app_caption}</div>', unsafe_allow_html=True)

    profile_fee_deduction_percent = float(DEFAULT_PROFILE_FEE_DEDUCTION_PERCENT)
    profile_budget_target_multiplier = deduction_percent_to_multiplier(profile_fee_deduction_percent)
    project_cpms = dict(SIMPLIFIED_FIXED_CPMS)
    allowed_tiers = list(VALID_PROFILE_TIERS)

    with st.container(border=True, key="cardbudget"):
        _section_header(
            _ui_text(language, "campaign_setup_title"),
            _ui_text(language, "campaign_setup_description"),
            "soft-green",
        )
        campaign_name = "Manual builder"
        budget_options = list(SIMPLIFIED_FIXED_BUDGETS)
        selected_budget = st.selectbox(
            "Budget",
            options=budget_options,
            index=0,
            format_func=lambda value: f"{format_display_number(value)} SEK",
        )
        optimization_focus = st.selectbox(
            _ui_text(language, "optimization_focus_label"),
            options=list(SIMPLIFIED_OPTIMIZATION_FOCUS_OPTIONS),
            index=list(SIMPLIFIED_OPTIMIZATION_FOCUS_OPTIONS).index(SIMPLIFIED_OPTIMIZATION_FOCUS_MANY_PROFILES),
            key="manual_optimization_focus",
            format_func=lambda focus: _optimization_focus_display_label(language, str(focus)),
        )
        paid_media_included = st.checkbox("Paid amplification included", value=DEFAULT_PAID_MEDIA_INCLUDED)
        budget_setup = build_simplified_budget_setup(
            selected_budget,
            paid_media_included=paid_media_included,
            profile_budget_target_multiplier=profile_budget_target_multiplier,
            optimization_focus=optimization_focus,
        )

    with st.container(border=True, key="cardchannels"):
        _section_header(
            _ui_text(language, "channels_title"),
            _ui_text(language, "channels_description"),
            "soft-blue",
        )
        for channel in SIMPLIFIED_MANUAL_CHANNELS:
            key = f"manual_selected_{channel.lower()}"
            if key not in st.session_state:
                st.session_state[key] = channel in DEFAULT_SELECTED_MANUAL_CHANNELS
        channel_cols = st.columns(2)
        with channel_cols[0]:
            st.checkbox("Instagram", key="manual_selected_instagram")
        with channel_cols[1]:
            st.checkbox("TikTok", key="manual_selected_tiktok")
        selected_channels = normalize_selected_channels(
            [
                channel
                for channel in SIMPLIFIED_MANUAL_CHANNELS
                if st.session_state.get(f"manual_selected_{channel.lower()}")
            ]
        )
        if not selected_channels:
            st.error("At least one channel must be selected.")

        total_profiles = int(budget_setup["total_profiles"])
        percentage_inputs = {channel: 100 if len(selected_channels) == 1 else 50 for channel in selected_channels}
        if len(selected_channels) == 1:
            st.caption(f"{selected_channels[0]} receives all {total_profiles} profiles.")
        elif selected_channels:
            with st.expander(_ui_text(language, "optional_split"), expanded=False):
                split_cols = st.columns(len(selected_channels))
                for index, channel in enumerate(selected_channels):
                    with split_cols[index]:
                        percentage_inputs[channel] = st.number_input(
                            f"{channel} %",
                            min_value=0,
                            max_value=100,
                            value=50,
                            step=5,
                            key=f"manual_split_percent_{channel.lower()}",
                        )

        split_error: str | None = None
        try:
            channel_split = parse_channel_percentage_split(
                total_profiles=total_profiles,
                percentages=percentage_inputs,
                selected_channels=selected_channels,
            )
        except ValueError as error:
            channel_split = {"Instagram": 0, "TikTok": 0, "YouTube": 0}
            split_error = str(error)
            st.warning(split_error)

    current_rows: list[dict] = []
    if selected_channels and split_error is None:
        try:
            current_rows = generate_profile_rows(
                total_profiles=total_profiles,
                project_cpms=project_cpms,
                channel_split=channel_split,
                selected_channels=selected_channels,
            )
        except ValueError as error:
            st.warning(str(error))

    row_status = _profile_row_status(total_profiles, current_rows)
    channel_split_summary = (
        ", ".join(f"{channel}: {channel_split[channel]}" for channel in selected_channels)
        if selected_channels and split_error is None
        else "invalid split"
    )

    with st.expander(_ui_text(language, "current_setup_title"), expanded=False):
        current_setup_caption = _ui_text(language, "current_setup_caption")
        if current_setup_caption:
            st.caption(current_setup_caption)
        setup_rows = _build_setup_summary_rows(
            budget=float(budget_setup["budget"]),
            agency_amount=float(budget_setup["agency_fee"]),
            paid_amount=float(budget_setup["paid_media"]),
            agency_text=f"Fixed preset ({format_display_number(budget_setup['agency_fee'])})",
            paid_text=f"15.00% ({format_display_number(budget_setup['paid_media'])})",
            paid_media_included=paid_media_included,
            profile_fee_deduction_percent=profile_fee_deduction_percent,
            total_profiles=total_profiles,
            selected_channels=selected_channels,
            channel_split_summary=channel_split_summary,
            cpm_currency="SEK",
            project_cpms=project_cpms,
            generated_row_count=len(current_rows),
            row_status_text=(
                "Rows ready"
                if len(current_rows) == total_profiles and split_error is None
                else "Setup needs attention"
            ),
        )
        setup_rows.insert(
            5,
            {
                "Field": "Available before deduction",
                "Value": format_display_number(budget_setup["available_before_deduction"]),
            },
        )
        if int(budget_setup["budget"]) >= 200000:
            setup_rows.insert(
                1,
                {
                    "Field": "Optimize for",
                    "Value": _optimization_focus_display_label(language, str(budget_setup["optimization_focus"])),
                },
            )
        setup_df = pd.DataFrame(setup_rows)
        st.dataframe(_style_current_setup_rows(setup_df), use_container_width=True, hide_index=True)

    with st.container(border=True, key="cardrunoptimizer"):
        _section_header(
            _ui_text(language, "run_optimizer_title"),
            _ui_text(language, "run_optimizer_description"),
            "soft-blue",
        )
        if st.button(_ui_text(language, "run_optimizer_button")):
            try:
                if not selected_channels:
                    raise ValueError("At least one channel must be selected.")
                if split_error is not None:
                    raise ValueError(split_error)
                validate_rows_use_selected_channels(current_rows, selected_channels)
                validate_project_cpms_for_rows(current_rows, project_cpms)
                model = build_manual_campaign_model(
                    campaign_name=campaign_name,
                    budget=budget_setup["budget"],
                    agency_fee=budget_setup["agency_fee"],
                    paid_media=budget_setup["paid_media"],
                    paid_media_included=paid_media_included,
                    profile_budget_target_multiplier=profile_budget_target_multiplier,
                    rows=current_rows,
                )
                payload, result = run_and_render(
                    models=[model],
                    input_label="manual_campaign_builder",
                    beam_width=DEFAULT_BEAM_WIDTH,
                    top_n=3,
                    allow_negative=False,
                    strategy="math",
                    optimization_method="fast_closest_diff",
                    allowed_tiers=allowed_tiers,
                    max_exact_states=DEFAULT_EXACT_MAX_STATES,
                    optimization_focus=str(budget_setup.get("optimization_focus") or ""),
                )
            except ValueError as error:
                st.error(str(error))
                return

            manual_context = {
                "budget": budget_setup["budget"],
                "selected_agency_fee_amount": budget_setup["agency_fee"],
                "selected_agency_fee_percent": None,
                "selected_paid_media_amount": budget_setup["paid_media"],
                "selected_paid_media_percent": budget_setup["paid_media_percent"],
                "paid_media": budget_setup["paid_media"],
                "paid_media_included": paid_media_included,
                "profile_fee_deduction_percent": profile_fee_deduction_percent,
                "combinations_evaluated": 1,
            }
            run_id = int(st.session_state.get("latest_run_id", 0)) + 1
            st.session_state.latest_run_id = run_id
            st.session_state.latest_run_data = {
                "run_id": run_id,
                "payload": payload,
                "result": result,
                "manual_context": manual_context,
                "default_calculation_name": campaign_name,
                "default_currency": "SEK",
                "source": {
                    "mode": "manual_campaign_builder",
                    "workbook_name": None,
                    "sheet_name": campaign_name,
                },
                "budget_inputs": _build_budget_inputs(
                    result=result,
                    budget=float(budget_setup["budget"]),
                    agency_fee_amount=float(budget_setup["agency_fee"]),
                    agency_fee_percent=None,
                    paid_media_amount=float(budget_setup["paid_media"]),
                    paid_media_percent=float(budget_setup["paid_media_percent"]),
                    paid_media_included=paid_media_included,
                    profile_fee_deduction_percent=profile_fee_deduction_percent,
                ),
            }

    if "latest_run_data" in st.session_state:
        run_data = st.session_state.latest_run_data
        render_result(
            run_data["payload"],
            run_data["result"],
            manual_context=run_data.get("manual_context"),
            budget_inputs=run_data.get("budget_inputs"),
        )


if __name__ == "__main__":
    main()
