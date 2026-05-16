"""
Global Supply Chain Pulse - Streamlit Overview (light theme).

The dashboard is multipage:
    app.py                        - this overview
    pages/1_Flights.py            - live air traffic
    pages/2_Ships.py              - vessel positions & port congestion
    pages/3_Events.py             - searchable global event feed
    pages/4_Commodities.py        - full commodity / macro time series
    pages/5_Regional_Detail.py    - drill into one region
    pages/6_Port_Detail.py        - drill into one port
    pages/7_Chokepoints.py        - chokepoint health & exposure
    pages/8_Trends_News.py        - news volume + market trends
"""

from __future__ import annotations

import subprocess
import sys

import streamlit as st

import config
from analytics.risk_score import compute_regional_risk, load_signals, top_risks
from analytics.history import score_deltas
from components import (
    render_world_map,
    render_activity_feed,
    render_risk_panel,
    render_trends,
    render_exec_summary,
    render_filters_sidebar,
    apply_filters,
    filter_summary_caption,
    render_briefing,
    render_pressure_heatmap,
    render_top_movers,
    render_api_status,
    render_cold_start_banner_if_needed,
    inject_global_css,
    TEXT, TEXT_MUTED, ACCENT, BORDER,
)
from pipelines import bootstrap
from pipelines.flights import read_snapshot as read_flights
from pipelines.ports_vessels import read_snapshot as read_vessels, is_demo_snapshot


st.set_page_config(
    page_title="Supply Chain Pulse",
    page_icon="globe",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_global_css()

# Kick the cold-start bootstrap on the very first render of this process.
# Idempotent - subsequent reruns are no-ops.
bootstrap.ensure_bootstrap()


# --------------------------------------------------------------------------- #
# Sidebar - snapshot info, refresh, filters
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown(
        "<div style='display:flex;align-items:center;gap:8px;margin-bottom:4px'>"
        f"<span style='width:8px;height:8px;border-radius:50%;background:{ACCENT}'></span>"
        f"<span style='font-weight:600;color:{TEXT};font-size:1.0rem'>Supply Chain Pulse</span></div>",
        unsafe_allow_html=True,
    )
    st.caption("External intelligence · free-tier data")

    blob = load_signals()
    generated_at = blob.get("generated_at")
    if generated_at:
        st.caption(f"Snapshot: {generated_at[:19].replace('T', ' ')} UTC")
    elif bootstrap.is_refreshing():
        st.caption("Snapshot: building (first run after cold start)…")
    else:
        st.warning("No snapshot yet. Click below to fetch.")

    if st.button("Refresh data now", use_container_width=True, type="primary"):
        with st.spinner("Running all pipelines..."):
            r = subprocess.run(
                [sys.executable, "scripts/refresh_data.py"],
                capture_output=True, text=True
            )
            st.code(r.stdout[-2000:] or r.stderr[-2000:])
        st.rerun()

    st.divider()

# Build country options once from the data the home page already has.
all_signals = blob.get("signals", [])
country_options = sorted({s["region"] for s in all_signals if s.get("region")})
flt = render_filters_sidebar(country_options=country_options)

with st.sidebar:
    st.divider()
    st.markdown(
        "<div style='font-size:0.72rem;color:#6B7280;text-transform:uppercase;"
        "letter-spacing:0.06em;margin-bottom:4px'>Data sources</div>"
        "<div style='font-size:0.78rem;line-height:1.4'>"
        "GDELT 2.0 · GDACS · USGS · NOAA NWS · Open-Meteo · NHC · NASA EONET · "
        "OpenSky Network · AISStream · FRED · Datahub · Google News · Reddit</div>",
        unsafe_allow_html=True,
    )
    st.divider()
    show_claude = st.toggle(
        "AI executive summary",
        value=config.ENABLE_CLAUDE_SUMMARY,
        help="Requires ANTHROPIC_API_KEY in .env.",
    )
    config.ENABLE_CLAUDE_SUMMARY = show_claude and bool(config.ANTHROPIC_API_KEY)


# --------------------------------------------------------------------------- #
# Filter the signal blob
# --------------------------------------------------------------------------- #
signals = apply_filters(all_signals, flt)
regional = compute_regional_risk(signals, lookback_hours=flt["lookback_hours"])
top = top_risks(regional, n=1)
worst_region = top[0] if top else ("-", 0.0)

flights_now = read_flights()
vessels_now = read_vessels()
airborne_now = [f for f in flights_now if not f.get("on_ground")]

n_severe   = sum(1 for s in signals if (s.get("severity") or 0) >= 0.7)
n_flight   = sum(1 for s in signals if s.get("category") == "flight")
n_tropical = sum(1 for s in signals if s.get("category") == "tropical")
n_volcanic = sum(1 for s in signals if s.get("category") == "volcanic")
n_natural  = sum(1 for s in signals if s.get("category") == "natural")
n_seismic  = sum(1 for s in signals if s.get("category") == "seismic")
n_market   = sum(1 for s in signals if s.get("category") in ("commodity", "macro"))


# --------------------------------------------------------------------------- #
# Title + page header
# --------------------------------------------------------------------------- #
st.markdown(
    f"<div style='display:flex;align-items:baseline;justify-content:space-between;"
    f"margin-bottom:2px'>"
    f"<h1 style='margin:0;padding:0;font-size:1.85rem;font-weight:650'>"
    f"Supply Chain Pulse</h1>"
    f"<div style='color:{TEXT_MUTED};font-size:0.85rem'>Overview · "
    f"{flt['window_label']}</div></div>",
    unsafe_allow_html=True,
)
st.markdown(
    f"<div style='color:{TEXT_MUTED};font-size:0.95rem;margin-bottom:14px'>"
    "Live view of geopolitical, weather, tropical, seismic, volcanic, "
    "natural-disaster, commodity, freight, aviation and macro signals "
    "shaping global supply chains."
    "</div>",
    unsafe_allow_html=True,
)
filter_summary_caption(flt, len(all_signals), len(signals))

# Cold-start banner - only renders when there's no snapshot yet.
cold_start = render_cold_start_banner_if_needed()

st.markdown("&nbsp;", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Auto-briefing
# --------------------------------------------------------------------------- #
render_briefing(signals, regional)


# --------------------------------------------------------------------------- #
# Top movers strip (delta vs last refresh)
# --------------------------------------------------------------------------- #
render_top_movers(regional, score_deltas())


# --------------------------------------------------------------------------- #
# KPIs - 8 metrics, two rows
# --------------------------------------------------------------------------- #
row1 = st.columns(4)
row1[0].metric("Active signals", f"{len(signals):,}")
row1[1].metric("Highest-pressure region", worst_region[0], f"{worst_region[1]:.0f}/100")
row1[2].metric("Severe (sev ≥ 0.7)", n_severe)
row1[3].metric("Regions monitored", len(config.REGIONS))

row2 = st.columns(4)
row2[0].metric("Aircraft tracked", f"{len(airborne_now):,}",
               help="Airborne aircraft in the latest OpenSky snapshot.")
row2[1].metric("Vessels tracked", f"{len(vessels_now):,}",
               help="Live AISStream snapshot via the in-process listener."
               if not is_demo_snapshot()
               else "Synthetic vessel snapshot (no AISSTREAM_API_KEY set, or first AIS cycle still running).")
row2[2].metric("Tropical + volcanic", f"{n_tropical + n_volcanic}")
row2[3].metric("Markets shocks", n_market,
               help="Commodity z-score ≥ 2σ or FRED macro shock.")


# --------------------------------------------------------------------------- #
# Map controls + map
# --------------------------------------------------------------------------- #
with st.expander("Map overlays", expanded=False):
    c1, c2, c3 = st.columns(3)
    show_flights  = c1.checkbox("Show live aircraft", value=False,
                                help="Overlay airborne aircraft (large dataset).")
    show_vessels  = c2.checkbox("Show vessels",       value=True)
    show_airports = c3.checkbox("Show airports",      value=True)

render_world_map(
    signals,
    flights=flights_now if show_flights else None,
    vessels=vessels_now if show_vessels else None,
    show_airports=show_airports,
)

st.divider()


# --------------------------------------------------------------------------- #
# Risk panel + pressure heatmap (region × component)
# --------------------------------------------------------------------------- #
col_risk, col_heat = st.columns([1.1, 1])
with col_risk:
    st.markdown("### Regional risk score")
    render_risk_panel(regional)

with col_heat:
    st.markdown("### Pressure heatmap")
    st.caption("Region × component, 0–100. Hover for exact value.")
    render_pressure_heatmap(regional)

st.divider()


# --------------------------------------------------------------------------- #
# Trends + executive summary + activity feed
# --------------------------------------------------------------------------- #
left, right = st.columns([1.4, 1])

with left:
    st.markdown("### Commodity & macro trends")
    render_trends()

with right:
    st.markdown("### Executive summary")
    render_exec_summary()

    st.markdown("### Latest headlines")
    news_only = [
        s for s in signals
        if s.get("category") == "news" and s.get("source") == "google-news"
    ][:8]
    if not news_only:
        st.caption("No matching news in window. See **Trends & News** in the sidebar.")
    else:
        from components.theme import (
            TEXT as _TEXT, TEXT_MUTED as _MUTED, BORDER as _BORDER, BG as _BG,
        )
        from datetime import datetime as _dt, timezone as _tz
        for s in sorted(news_only, key=lambda x: x.get("timestamp_utc", ""), reverse=True):
            pl = s.get("payload") or {}
            outlet = pl.get("outlet") or s.get("source", "")
            try:
                t = _dt.fromisoformat(s["timestamp_utc"].replace("Z", "+00:00"))
                mins = int((_dt.now(_tz.utc) - t).total_seconds() // 60)
                when = f"{mins}m ago" if mins < 60 else f"{mins // 60}h ago"
            except Exception:
                when = ""
            url = s.get("url") or "#"
            st.markdown(
                f"<div style='border-bottom:1px solid {_BORDER};padding:6px 0;'>"
                f"<div style='font-size:0.7rem;color:{_MUTED};margin-bottom:2px'>"
                f"{outlet} · {when}</div>"
                f"<a href='{url}' target='_blank' style='color:{_TEXT};"
                f"font-size:0.88rem;text-decoration:none;line-height:1.35'>"
                f"{s.get('title', '')[:140]}</a></div>",
                unsafe_allow_html=True,
            )

    st.markdown("### Activity feed")
    render_activity_feed(signals, limit=40)


# --------------------------------------------------------------------------- #
# Footer - unified API health strip + disclosure
# --------------------------------------------------------------------------- #
render_api_status()

st.caption(
    "Open **Flights**, **Ships**, **Events**, **Commodities**, "
    "**Regional Detail**, **Port Detail**, **Chokepoints** in the sidebar for "
    "granular drilldowns. Public data - GDELT, GDACS, USGS, NOAA, Open-Meteo, "
    "NHC, NASA EONET, OpenSky, AISStream, FRED, Datahub, Google News, Reddit. "
    "Situational-awareness tool, not operational or investment advice."
)
