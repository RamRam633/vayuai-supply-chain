"""
Chokepoints page - global supply-chain choke health.

For each of the 8 strategic chokepoints we surface:
  * vessel density inside the radius
  * any signals (any category) within the radius
  * a 'choke health' score combining vessel intensity + event severity
  * a focused list of the highest-impact signals in the radius
"""

from __future__ import annotations

import math

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

import config
from pipelines.ports_vessels import read_snapshot as read_vessels, chokepoint_traffic
from analytics.risk_score import load_signals
from components import (
    render_filters_sidebar, apply_filters,
    inject_global_css, apply_light, map_kwargs,
    render_api_status, render_cold_start_banner_if_needed,
    render_brand_topbar, render_brand_header, render_brand_footer, LOGO_PATH,
    TEXT, TEXT_MUTED, ACCENT, CRITICAL, WARNING, INFO, BORDER,
)
from pipelines import bootstrap


st.set_page_config(
    page_title="Chokepoints - Supply Chain Pulse",
    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else None,
    layout="wide",
)
inject_global_css()
bootstrap.ensure_bootstrap()
render_brand_topbar(section="Chokepoints")
render_brand_header()
st.markdown("## Strategic chokepoint health")
st.caption(
    "Eight global chokepoints account for the majority of seaborne trade. "
    "Each card combines real-time vessel density inside the radius with any "
    "geopolitical, weather, seismic or other signals firing nearby."
)


flt = render_filters_sidebar()
render_cold_start_banner_if_needed()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _hav(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _signals_near(signals: list[dict], ck: dict) -> list[dict]:
    rkm = ck.get("radius_km", 150)
    out = []
    for s in signals:
        if s.get("lat") is None or s.get("lon") is None:
            continue
        if _hav(ck["lat"], ck["lon"], s["lat"], s["lon"]) <= rkm:
            d = dict(s)
            d["distance_km"] = round(
                _hav(ck["lat"], ck["lon"], s["lat"], s["lon"]), 1
            )
            out.append(d)
    return out


def _health_score(vessel_intensity: float, signals_nearby: list[dict]) -> float:
    """0..100. Higher = MORE pressure on this chokepoint.

    35% from vessel intensity (congestion proxy).
    65% from the max severity of nearby signals, weighted by count.
    """
    sev_component = 0.0
    if signals_nearby:
        max_sev = max(float(s.get("severity", 0) or 0) for s in signals_nearby)
        count_w = min(1.0, len(signals_nearby) / 10.0)
        sev_component = max_sev * (0.7 + 0.3 * count_w)
    return round(min(100.0, 100 * (0.35 * vessel_intensity + 0.65 * sev_component)), 1)


def _health_color(score: float) -> str:
    if score >= 60:
        return CRITICAL
    if score >= 35:
        return WARNING
    if score >= 15:
        return "#F59E0B"
    return ACCENT


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
blob = load_signals()
all_signals = blob.get("signals", [])
signals = apply_filters(all_signals, flt)

traffic = {t["name"]: t for t in chokepoint_traffic()}

# Composite table
rows = []
for ck in config.CHOKEPOINTS:
    near = _signals_near(signals, ck)
    t = traffic.get(ck["name"], {"vessels_nearby": 0, "intensity": 0.0})
    score = _health_score(t["intensity"], near)
    rows.append(
        {
            "Chokepoint":      ck["name"],
            "lat":             ck["lat"],
            "lon":             ck["lon"],
            "radius_km":       ck["radius_km"],
            "Vessels in zone": t["vessels_nearby"],
            "Vessel intensity (0-1)": round(t["intensity"], 2),
            "Signals in zone": len(near),
            "Top severity":    round(
                max([float(s.get("severity", 0) or 0) for s in near], default=0.0),
                2,
            ),
            "Health score":    score,
            "_near":           near,
        }
    )
ck_df = pd.DataFrame(rows).sort_values("Health score", ascending=False)


# --------------------------------------------------------------------------- #
# Map of chokepoints sized by health score
# --------------------------------------------------------------------------- #
map_df = ck_df.copy()
map_df["radius_m"] = map_df["radius_km"] * 1000
map_df["fill"] = map_df["Health score"].apply(
    lambda s: [220, 38, 38, 120] if s >= 60
    else [217, 119, 6, 120] if s >= 35
    else [16, 163, 116, 90]
)

deck = pdk.Deck(
    initial_view_state=pdk.ViewState(latitude=22, longitude=40, zoom=1.5),
    layers=[
        pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position="[lon, lat]",
            get_radius="radius_m",
            get_fill_color="fill",
            stroked=True,
            get_line_color=[120, 120, 120, 200],
            line_width_min_pixels=1,
            pickable=True,
        ),
    ],
    tooltip={"text": "{Chokepoint}\nHealth: {Health score}"},
    **map_kwargs(),
)
st.pydeck_chart(deck, use_container_width=True)


# --------------------------------------------------------------------------- #
# Composite leaderboard
# --------------------------------------------------------------------------- #
st.markdown("### Chokepoint health leaderboard")
fig = px.bar(
    ck_df, x="Chokepoint", y="Health score",
    color="Health score",
    color_continuous_scale=[[0, "#10A37F"], [0.4, "#D97706"], [0.7, "#DC2626"]],
)
apply_light(fig, height=340, margin=dict(l=10, r=10, t=10, b=80),
            xaxis_tickangle=-20, coloraxis_showscale=False)
st.plotly_chart(fig, use_container_width=True)


# --------------------------------------------------------------------------- #
# Per-chokepoint cards
# --------------------------------------------------------------------------- #
st.markdown("### Per-chokepoint detail")

for _, row in ck_df.iterrows():
    score = row["Health score"]
    color = _health_color(score)
    near  = row["_near"]

    st.markdown(
        f"""
        <div class='pulse-card' style='border-left:3px solid {color}'>
          <div style='display:flex;align-items:baseline;justify-content:space-between'>
            <div style='font-size:1.1rem;font-weight:600;color:{TEXT}'>
              {row['Chokepoint']}
            </div>
            <div style='font-size:1.1rem;font-weight:600;color:{color}'>
              {score:.0f}<span style='font-size:0.7rem;color:{TEXT_MUTED};
              font-weight:500;margin-left:4px'>/100</span>
            </div>
          </div>
          <div style='margin-top:4px;color:{TEXT_MUTED};font-size:0.85rem'>
            {row['Vessels in zone']:,} vessels in zone  ·
            {row['Signals in zone']} nearby signals  ·
            radius {row['radius_km']} km
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if near:
        with st.expander(f"Signals near {row['Chokepoint']}"):
            df = pd.DataFrame(near)
            st.dataframe(
                df[["timestamp_utc", "category", "severity", "title",
                    "distance_km", "url"]]
                  .sort_values("severity", ascending=False),
                use_container_width=True, hide_index=True,
                column_config={
                    "severity": st.column_config.ProgressColumn(
                        "severity", min_value=0.0, max_value=1.0, format="%.2f"
                    ),
                    "url": st.column_config.LinkColumn("url"),
                },
            )


# --------------------------------------------------------------------------- #
# API health footer
# --------------------------------------------------------------------------- #
render_api_status()
render_brand_footer()
