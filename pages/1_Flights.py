"""
Flights page - live aircraft snapshot + per-airport congestion drilldown.
"""

from __future__ import annotations

import math

import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st

import config
from pipelines.flights import (
    read_snapshot as read_flights,
    AIRPORT_RADIUS_KM,
)
from analytics.risk_score import load_signals
from components import (
    render_filters_sidebar, apply_filters, filter_summary_caption,
    inject_global_css, apply_light, map_kwargs,
    render_api_status, render_cold_start_banner_if_needed,
    render_brand_topbar, render_brand_header, render_brand_footer, LOGO_PATH,
    TEXT, TEXT_MUTED, BORDER, ACCENT,
)
from pipelines import bootstrap


st.set_page_config(
    page_title="Flights - Supply Chain Pulse",
    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else None,
    layout="wide",
)
inject_global_css()
bootstrap.ensure_bootstrap()
render_brand_topbar(section="Flights")
render_brand_header()
st.markdown("## Live air traffic")

flt = render_filters_sidebar()
render_cold_start_banner_if_needed()

flights  = read_flights()
airborne = [f for f in flights if not f.get("on_ground")]
on_ground = [f for f in flights if f.get("on_ground")]

# --------------------------------------------------------------------------- #
# KPIs
# --------------------------------------------------------------------------- #
k1, k2, k3, k4 = st.columns(4)
k1.metric("Aircraft tracked", f"{len(flights):,}")
k2.metric("Airborne",         f"{len(airborne):,}")
k3.metric("On ground",        f"{len(on_ground):,}")
snap_ts = flights[0]["ts_utc"] if flights else None
k4.metric("Snapshot", snap_ts[11:19] + " UTC" if snap_ts else "-")

if not flights:
    st.info(
        "No flight snapshot yet. The background refresh fetches a global "
        "OpenSky snapshot every few minutes - try again shortly, or click "
        "**Refresh data now** in the sidebar to force a fetch."
    )
    render_api_status()
    render_brand_footer()
    st.stop()


# --------------------------------------------------------------------------- #
# Map
# --------------------------------------------------------------------------- #
flight_df = pd.DataFrame(flights)
flight_df["color"] = flight_df["on_ground"].map(
    lambda g: [245, 158, 11, 130] if g else [14, 116, 144, 200]
)
airport_df = pd.DataFrame(config.MAJOR_AIRPORTS)

deck = pdk.Deck(
    initial_view_state=pdk.ViewState(latitude=20, longitude=20, zoom=1.3),
    layers=[
        pdk.Layer(
            "ScatterplotLayer",
            data=airport_df,
            get_position="[lon, lat]",
            get_radius=AIRPORT_RADIUS_KM * 1000,
            get_fill_color=[14, 116, 144, 25],
            stroked=True,
            get_line_color=[14, 116, 144, 150],
            line_width_min_pixels=1,
            pickable=True,
        ),
        pdk.Layer(
            "ScatterplotLayer",
            data=flight_df,
            get_position="[lon, lat]",
            get_radius=6000,
            get_fill_color="color",
            opacity=0.65,
        ),
    ],
    tooltip={"text": "{name} ({iata})"},
    **map_kwargs(),
)
st.pydeck_chart(deck, use_container_width=True)


# --------------------------------------------------------------------------- #
# Airport-density leaderboard
# --------------------------------------------------------------------------- #
def _hav(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


leaderboard = []
for ap in config.MAJOR_AIRPORTS:
    nearby = sum(
        1 for f in airborne
        if _hav(ap["lat"], ap["lon"], f["lat"], f["lon"]) <= AIRPORT_RADIUS_KM
    )
    leaderboard.append({
        "Airport": ap["name"], "IATA": ap["iata"],
        "Cargo rank": ap.get("cargo_rank"),
        f"Aircraft within {AIRPORT_RADIUS_KM} km": nearby,
    })
lb = pd.DataFrame(leaderboard).sort_values(
    f"Aircraft within {AIRPORT_RADIUS_KM} km", ascending=False
).reset_index(drop=True)

st.markdown("### Per-airport airborne density")
fig = px.bar(
    lb, x="Airport", y=f"Aircraft within {AIRPORT_RADIUS_KM} km",
    color=f"Aircraft within {AIRPORT_RADIUS_KM} km",
    color_continuous_scale=[[0, "#10A37F"], [0.5, "#D97706"], [1.0, "#DC2626"]],
)
apply_light(fig, height=400, margin=dict(l=10, r=10, t=10, b=110),
            xaxis_tickangle=-35, coloraxis_showscale=False)
st.plotly_chart(fig, use_container_width=True)

with st.expander("Full airport table"):
    st.dataframe(lb, use_container_width=True, hide_index=True)


# --------------------------------------------------------------------------- #
# Top origin countries
# --------------------------------------------------------------------------- #
st.markdown("### Top origin countries (airborne)")
oc = (
    pd.DataFrame(airborne)
    .groupby("origin_country").size()
    .sort_values(ascending=False)
    .head(25)
    .rename("aircraft")
    .reset_index()
)
fig2 = px.bar(oc, x="origin_country", y="aircraft", color="aircraft",
              color_continuous_scale=[[0, "#3a3530"], [1, "#7ecbe0"]])
apply_light(fig2, height=320, margin=dict(l=10, r=10, t=10, b=100),
            xaxis_tickangle=-35, coloraxis_showscale=False)
st.plotly_chart(fig2, use_container_width=True)


# --------------------------------------------------------------------------- #
# Altitude distribution
# --------------------------------------------------------------------------- #
st.markdown("### Altitude distribution (airborne)")
fdf = pd.DataFrame(airborne)
fdf = fdf[(fdf["baro_alt_m"] > 0) & (fdf["baro_alt_m"] < 15000)]
fig3 = px.histogram(fdf, x="baro_alt_m", nbins=40, color_discrete_sequence=["#0E7490"])
apply_light(fig3, height=260, bargap=0.05, xaxis_title="Barometric altitude (m)")
st.plotly_chart(fig3, use_container_width=True)


# --------------------------------------------------------------------------- #
# Flight signals
# --------------------------------------------------------------------------- #
st.markdown("### Flight-derived signals")
blob = load_signals()
sigs = apply_filters(blob.get("signals", []), flt)
flight_sigs = [s for s in sigs if s.get("category") == "flight"]
filter_summary_caption(flt, len(blob.get("signals", [])), len(sigs))
if not flight_sigs:
    st.info("No airport-congestion signals fired with the current filters.")
else:
    df = pd.DataFrame(flight_sigs)
    st.dataframe(
        df[["timestamp_utc", "severity", "title", "url"]]
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
