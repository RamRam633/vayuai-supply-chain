"""
Unified API health footer.

Replaces the scattered "demo / synthetic" banners that used to litter
every page. One subtle status strip at the bottom of each page reports:

    * Snapshot age (how long since the last successful refresh)
    * In-flight refresh indicator
    * Per-source dots: live / cached / partial-demo / down

Sources are grouped so the footer stays compact:

    Geopolitics  ·  Maritime  ·  Aviation  ·  Weather  ·  Earth  ·
    Markets  ·  News
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import streamlit as st

import config
from analytics.risk_score import load_signals
from pipelines import bootstrap
from pipelines.commodities import (
    is_demo_prices,
    synthetic_columns as commo_synthetic_columns,
)
from pipelines.ports_vessels import is_demo_snapshot as is_demo_vessels
from pipelines.macro import is_demo_macro
from .theme import (
    BG, BG_MUTED, BORDER, TEXT, TEXT_MUTED, ACCENT, ACCENT_DEEP,
    CRITICAL, WARNING, SUCCESS,
)


# --------------------------------------------------------------------------- #
# Status helpers
# --------------------------------------------------------------------------- #
_OK   = "live"
_WARN = "partial"
_DOWN = "down"

_DOT_COLORS = {
    _OK:   SUCCESS,
    _WARN: WARNING,
    _DOWN: CRITICAL,
}


def _humanize_seconds(s: float | None) -> str:
    if s is None:
        return "never"
    s = max(0.0, float(s))
    if s < 60:
        return f"{int(s)}s ago"
    if s < 3600:
        return f"{int(s // 60)}m ago"
    return f"{int(s // 3600)}h ago"


def _summary_count(summary: dict, key: str) -> int:
    try:
        return int(summary.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _group_status(
    n: int,
    *,
    demo: bool = False,
    requires_key: str | None = None,
) -> str:
    """Translate (count, demo flag, key requirement) into one of live/partial/down."""
    if requires_key and not getattr(config, requires_key, ""):
        return _WARN
    if demo:
        return _WARN
    if n > 0:
        return _OK
    return _DOWN


def _dot(color: str, size: int = 9) -> str:
    return (
        f"<span style='display:inline-block;width:{size}px;height:{size}px;"
        f"border-radius:50%;background:{color};margin-right:6px'></span>"
    )


# --------------------------------------------------------------------------- #
# Public render
# --------------------------------------------------------------------------- #
def render_api_status() -> None:
    """Render the compact API health strip. Safe to call on every page."""

    boot = bootstrap.state_snapshot()
    blob = load_signals()
    summary = blob.get("summary", {}) or {}
    generated_at = blob.get("generated_at")

    age_s = boot.get("signals_age_s")
    refreshing = boot.get("refreshing", False)

    if generated_at:
        try:
            ts = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            age_label = _humanize_seconds((datetime.now(timezone.utc) - ts).total_seconds())
        except Exception:
            age_label = _humanize_seconds(age_s)
    else:
        age_label = "never"

    n_geo  = _summary_count(summary, "geopolitics") + _summary_count(summary, "news")
    n_sea  = _summary_count(summary, "ports_vessels")
    n_air  = _summary_count(summary, "flights")
    n_wx   = _summary_count(summary, "weather") + _summary_count(summary, "tropical")
    n_eart = _summary_count(summary, "seismic")  + _summary_count(summary, "natural_events")
    n_mkt  = _summary_count(summary, "commodities") + _summary_count(summary, "macro")

    groups: list[tuple[str, str]] = [
        ("Geopolitics", _group_status(n_geo)),
        ("Maritime",    _group_status(n_sea, demo=is_demo_vessels(),
                                       requires_key="AISSTREAM_API_KEY")),
        ("Aviation",    _group_status(n_air)),
        ("Weather",     _group_status(n_wx)),
        ("Earth",       _group_status(n_eart)),
        ("Markets",     _group_status(n_mkt, demo=is_demo_prices() or is_demo_macro(),
                                       requires_key="FRED_API_KEY")),
    ]

    chips_html = "".join(
        f"<span style='display:inline-flex;align-items:center;margin-right:14px;"
        f"font-size:0.78rem;color:{TEXT_MUTED}'>"
        f"{_dot(_DOT_COLORS[status])}{label}</span>"
        for label, status in groups
    )

    # Top-line status pill: green if everything live, amber if any partial,
    # red if everything is down or no snapshot yet.
    statuses = [s for _, s in groups]
    if generated_at is None:
        overall = _DOWN
        overall_label = "Booting" if refreshing else "No data yet"
    elif _DOWN in statuses:
        overall = _WARN
        overall_label = "Degraded"
    elif _WARN in statuses:
        overall = _WARN
        overall_label = "Partial"
    else:
        overall = _OK
        overall_label = "All systems live"

    refresh_chip = ""
    if refreshing:
        refresh_chip = (
            f"<span style='display:inline-flex;align-items:center;"
            f"font-size:0.78rem;color:{ACCENT_DEEP};margin-left:10px'>"
            f"{_dot(ACCENT)}refreshing…</span>"
        )

    st.markdown(
        f"""
        <div style='margin-top:18px;padding:10px 14px;background:{BG_MUTED};
                    border:1px solid {BORDER};border-radius:10px;
                    display:flex;flex-wrap:wrap;align-items:center;
                    gap:6px 18px;font-size:0.78rem;color:{TEXT_MUTED}'>
          <span style='display:inline-flex;align-items:center;font-weight:600;
                       color:{TEXT}'>
            {_dot(_DOT_COLORS[overall], size=10)}{overall_label}
          </span>
          <span>· snapshot {age_label}</span>
          {refresh_chip}
          <span style='flex:1'></span>
          {chips_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Detail expander — only renders if anything is degraded so the page
    # stays clean when everything's live.
    if overall != _OK:
        with st.expander("Source detail"):
            _render_detail(summary, groups)


def _render_detail(summary: dict, groups: list[tuple[str, str]]) -> None:
    """Verbose per-source breakdown shown when something's amiss."""

    rows: list[str] = []

    def _row(label: str, status: str, note: str) -> str:
        return (
            f"<tr><td style='padding:4px 12px 4px 0;white-space:nowrap'>"
            f"{_dot(_DOT_COLORS[status])}{label}</td>"
            f"<td style='padding:4px 0;color:{TEXT_MUTED}'>{note}</td></tr>"
        )

    # Per-pipeline detail
    rows.append(_row(
        "GDELT + GDACS (geopolitical)",
        _group_status(_summary_count(summary, "geopolitics")),
        f"{_summary_count(summary, 'geopolitics')} signals on last refresh "
        "(GDELT rate-limits cloud IPs aggressively; GDACS is the durable feed)",
    ))
    rows.append(_row(
        "Google News + Reddit RSS",
        _group_status(_summary_count(summary, "news")),
        f"{_summary_count(summary, 'news')} news signals",
    ))
    ais_status = _group_status(
        _summary_count(summary, "ports_vessels"),
        demo=is_demo_vessels(), requires_key="AISSTREAM_API_KEY",
    )
    ais_note = (
        "AISSTREAM_API_KEY missing — using deterministic synthetic vessel positions"
        if not config.AISSTREAM_API_KEY
        else ("Live AISStream WebSocket — positions refreshed every "
              f"{bootstrap.AIS_RECOLLECT_MINUTES} min")
        if not is_demo_vessels()
        else "AIS listener hasn't completed its first cycle yet — showing demo positions"
    )
    rows.append(_row("AISStream (vessels)", ais_status, ais_note))
    rows.append(_row(
        "OpenSky Network (flights)",
        _group_status(_summary_count(summary, "flights")),
        f"{_summary_count(summary, 'flights')} airport-congestion signals; "
        "global aircraft snapshot in flights_snapshot.sqlite",
    ))
    rows.append(_row(
        "NOAA NWS alerts + Open-Meteo (weather)",
        _group_status(_summary_count(summary, "weather")),
        f"{_summary_count(summary, 'weather')} weather signals",
    ))
    rows.append(_row(
        "NHC tropical cyclones",
        _group_status(_summary_count(summary, "tropical")),
        f"{_summary_count(summary, 'tropical')} active storms (Atlantic + East Pacific basins)",
    ))
    rows.append(_row(
        "USGS earthquakes",
        _group_status(_summary_count(summary, "seismic")),
        f"{_summary_count(summary, 'seismic')} M4.5+ in last 7d",
    ))
    rows.append(_row(
        "NASA EONET natural events",
        _group_status(_summary_count(summary, "natural_events")),
        f"{_summary_count(summary, 'natural_events')} open events "
        "(wildfires / volcanoes / floods / storms)",
    ))

    commo_synth = commo_synthetic_columns()
    commo_status = _group_status(
        _summary_count(summary, "commodities"),
        demo=bool(commo_synth), requires_key="FRED_API_KEY",
    )
    commo_note = (
        "FRED_API_KEY missing — falling back to Datahub.io daily mirrors plus synthetic"
        if not config.FRED_API_KEY
        else (
            f"All commodity series live (FRED + Datahub)"
            if not commo_synth
            else f"Synthetic fallback for: {', '.join(commo_synth)}"
        )
    )
    rows.append(_row("Commodities (FRED + Datahub)", commo_status, commo_note))

    macro_status = _group_status(
        _summary_count(summary, "macro"),
        demo=is_demo_macro(), requires_key="FRED_API_KEY",
    )
    macro_note = (
        "FRED_API_KEY missing — using Datahub mirrors + Frankfurter FX basket + synthetic"
        if not config.FRED_API_KEY
        else "FRED macro series live"
    )
    rows.append(_row("Macro / freight (FRED)", macro_status, macro_note))

    table = "<table style='border-collapse:collapse;font-size:0.82rem'>" + "".join(rows) + "</table>"
    st.markdown(table, unsafe_allow_html=True)

    if bootstrap.state_snapshot().get("last_refresh_error"):
        st.caption(
            f"Last refresh error: `{bootstrap.state_snapshot()['last_refresh_error']}`"
        )


# --------------------------------------------------------------------------- #
# Cold-start banner — shows above the page body when there's no snapshot yet
# --------------------------------------------------------------------------- #
def render_cold_start_banner_if_needed() -> bool:
    """If signals.json doesn't exist yet, show a friendly loading hint.

    Returns True if the banner was rendered (so callers can decide to skip
    rendering empty charts below).
    """
    boot = bootstrap.state_snapshot()
    blob = load_signals()
    generated_at = blob.get("generated_at")
    if generated_at:
        return False

    if boot.get("refreshing"):
        msg = (
            "**Live data is loading.** First snapshot typically lands within "
            "30 seconds of a cold start. Refresh the page in a moment to see "
            "events, ships, and commodity signals populate."
        )
        st.info(msg)
    else:
        st.warning(
            "No snapshot available yet. Use **Refresh data now** in the sidebar — "
            "every public feed will populate in ~30 seconds."
        )
    return True
