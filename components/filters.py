"""
Shared sidebar filters - deep but defaulting to fully-on.

Layout (top to bottom):
    Preset chips        - one-click slicers ("Critical 24h", "Maritime",
                          "Aviation", "Disasters", "Reset")
    Time window
    Severity range
    Regions             (multi-select)
    Categories          (multi-select)
    Sources             (multi-select)
    Countries           (multi-select, populated from data)
    Free-text search

Every filter starts permissive - the user sees everything until they
deliberately narrow.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import streamlit as st

import config

ALL_CATEGORIES = [
    "geopolitical", "weather", "tropical", "seismic", "volcanic",
    "natural", "commodity", "macro", "freight", "flight", "news",
]

ALL_SOURCES = [
    "gdelt", "gdacs",
    "usgs", "noaa", "open-meteo",
    "nhc", "eonet",
    "opensky", "ais-snapshot",
    "commodities", "macro", "fred",
    "google-news", "reddit",
]

TIME_WINDOWS = {
    "Last 6h":   6,
    "Last 12h":  12,
    "Last 24h":  24,
    "Last 36h":  36,
    "Last 72h":  72,
    "Last 7d":   24 * 7,
    "All":       24 * 365 * 10,
}

PRESETS = {
    "All on (reset)":     {"min_sev": 0.0, "max_sev": 1.0, "window": "Last 36h",
                           "cats": ALL_CATEGORIES, "srcs": ALL_SOURCES},
    "Critical (24h)":     {"min_sev": 0.7, "max_sev": 1.0, "window": "Last 24h",
                           "cats": ALL_CATEGORIES, "srcs": ALL_SOURCES},
    "Maritime focus":     {"min_sev": 0.0, "max_sev": 1.0, "window": "Last 72h",
                           "cats": ["freight", "weather", "tropical"],
                           "srcs": ALL_SOURCES},
    "Aviation focus":     {"min_sev": 0.0, "max_sev": 1.0, "window": "Last 24h",
                           "cats": ["flight", "weather", "tropical"],
                           "srcs": ALL_SOURCES},
    "Natural disasters":  {"min_sev": 0.0, "max_sev": 1.0, "window": "Last 7d",
                           "cats": ["natural", "volcanic", "seismic",
                                    "tropical", "weather"],
                           "srcs": ALL_SOURCES},
    "Geopolitics":        {"min_sev": 0.3, "max_sev": 1.0, "window": "Last 72h",
                           "cats": ["geopolitical"], "srcs": ALL_SOURCES},
    "Markets only":       {"min_sev": 0.0, "max_sev": 1.0, "window": "Last 36h",
                           "cats": ["commodity", "macro"], "srcs": ALL_SOURCES},
    "News & social":      {"min_sev": 0.0, "max_sev": 1.0, "window": "Last 24h",
                           "cats": ["news"], "srcs": ["google-news", "reddit"]},
}


def _apply_preset(name: str) -> None:
    p = PRESETS[name]
    st.session_state["flt_min_sev"]    = p["min_sev"]
    st.session_state["flt_max_sev"]    = p["max_sev"]
    st.session_state["flt_window"]     = p["window"]
    st.session_state["flt_categories"] = p["cats"]
    st.session_state["flt_sources"]    = p["srcs"]
    st.session_state["flt_regions"]    = list(config.REGIONS.keys())
    st.session_state["flt_countries"]  = []
    st.session_state["flt_search"]     = ""


def render_filters_sidebar(country_options: list[str] | None = None) -> dict:
    """Render the sidebar and return the active filter dict.

    `country_options` lets a page pre-seed the country list from data it
    already has on hand (the home page does this).
    """
    st.sidebar.markdown("#### Filter signals")

    # ---- Presets --------------------------------------------------------- #
    with st.sidebar.expander("Presets", expanded=False):
        cols = st.columns(2)
        for i, name in enumerate(PRESETS):
            if cols[i % 2].button(name, key=f"preset_{i}", use_container_width=True):
                _apply_preset(name)
                st.rerun()

    # ---- Time window ----------------------------------------------------- #
    window_options = list(TIME_WINDOWS.keys())
    default_window = st.session_state.get("flt_window", "Last 36h")
    if default_window not in window_options:
        default_window = "Last 36h"
    window_label = st.sidebar.selectbox(
        "Time window", options=window_options,
        index=window_options.index(default_window),
        key="flt_window",
    )

    # ---- Severity range -------------------------------------------------- #
    sev_min, sev_max = st.sidebar.slider(
        "Severity range",
        min_value=0.0, max_value=1.0,
        value=(st.session_state.get("flt_min_sev", 0.0),
               st.session_state.get("flt_max_sev", 1.0)),
        step=0.05,
    )
    st.session_state["flt_min_sev"] = sev_min
    st.session_state["flt_max_sev"] = sev_max

    # ---- Regions --------------------------------------------------------- #
    regions = st.sidebar.multiselect(
        "Regions", options=list(config.REGIONS.keys()),
        default=st.session_state.get("flt_regions", list(config.REGIONS.keys())),
        key="flt_regions",
    )

    # ---- Categories ------------------------------------------------------ #
    categories = st.sidebar.multiselect(
        "Categories", options=ALL_CATEGORIES,
        default=st.session_state.get("flt_categories", ALL_CATEGORIES),
        key="flt_categories",
    )

    # ---- Sources --------------------------------------------------------- #
    sources = st.sidebar.multiselect(
        "Data sources", options=ALL_SOURCES,
        default=st.session_state.get("flt_sources", ALL_SOURCES),
        key="flt_sources",
    )

    # ---- Country (only shown when caller hands us a list) ---------------- #
    countries = []
    if country_options:
        countries = st.sidebar.multiselect(
            "Countries (signal-tagged)",
            options=sorted(country_options),
            default=st.session_state.get("flt_countries", []),
            key="flt_countries",
            help="Subset to signals pre-tagged with a specific country. "
                 "Leave empty to include all.",
        )

    # ---- Search ---------------------------------------------------------- #
    search = st.sidebar.text_input(
        "Search titles", value=st.session_state.get("flt_search", ""),
        key="flt_search", placeholder="e.g. wildfire, Suez, copper",
    ).strip()

    return {
        "regions":        regions,
        "categories":     categories,
        "sources":        sources,
        "countries":      countries,
        "min_severity":   sev_min,
        "max_severity":   sev_max,
        "lookback_hours": TIME_WINDOWS[window_label],
        "window_label":   window_label,
        "search":         search,
    }


def apply_filters(signals: list[dict], flt: dict) -> list[dict]:
    """Apply a filter dict to a list of Signal-as-dict records."""
    from pipelines.base import regions_for_point

    cutoff = datetime.now(timezone.utc) - timedelta(hours=flt["lookback_hours"])
    cats        = set(flt["categories"])
    srcs        = set(flt.get("sources") or [])
    sel_regions = set(flt["regions"])
    sel_countries = set(flt.get("countries") or [])
    q = (flt.get("search") or "").lower().strip()
    sev_min, sev_max = flt["min_severity"], flt["max_severity"]

    out: list[dict] = []
    for s in signals:
        # Category
        if s.get("category") not in cats:
            continue
        # Source
        if srcs and (s.get("source") not in srcs):
            continue
        # Severity range
        sev = float(s.get("severity", 0.0) or 0.0)
        if sev < sev_min or sev > sev_max:
            continue
        # Time window
        try:
            ts = datetime.fromisoformat(
                (s.get("timestamp_utc") or "").replace("Z", "+00:00")
            )
            if ts < cutoff:
                continue
        except Exception:
            pass
        # Country
        if sel_countries:
            if not s.get("region") or s["region"] not in sel_countries:
                continue
        # Free-text search
        if q and q not in (s.get("title") or "").lower():
            continue
        # Region filter - commodity/macro are global signals
        if s.get("category") in ("commodity", "macro"):
            out.append(s)
            continue
        sig_regions: list[str] = []
        if s.get("region"):
            sig_regions = [s["region"]]
        elif s.get("lat") is not None and s.get("lon") is not None:
            sig_regions = regions_for_point(s["lat"], s["lon"])
        if not sig_regions:
            if sel_regions == set(config.REGIONS.keys()):
                out.append(s)
            continue
        if any(r in sel_regions for r in sig_regions):
            out.append(s)
    return out


def filter_summary_caption(flt: dict, original: int, filtered: int) -> None:
    """Show what's been narrowed - a single line below the title."""
    chips = [
        f"<span class='pulse-pill'>{flt['window_label']}</span>",
        f"<span class='pulse-pill'>severity {flt['min_severity']:.2f}–{flt['max_severity']:.2f}</span>",
        f"<span class='pulse-pill'>{len(flt['regions'])} regions</span>",
        f"<span class='pulse-pill'>{len(flt['categories'])} categories</span>",
        f"<span class='pulse-pill'>{len(flt.get('sources') or [])} sources</span>",
    ]
    if flt.get("search"):
        chips.append(f"<span class='pulse-pill pulse-pill-accent'>search: {flt['search']}</span>")
    chips.append(
        f"<span class='pulse-pill pulse-pill-accent'>{filtered:,} / {original:,} signals</span>"
    )
    st.markdown(" ".join(chips), unsafe_allow_html=True)
