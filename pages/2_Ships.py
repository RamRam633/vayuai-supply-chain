"""
Ships page - AIS vessel snapshot + per-port congestion + chokepoint traffic.

Reads pipelines.ports_vessels.read_snapshot(). When no AISStream key is
configured we serve a deterministic synthetic snapshot (clearly marked as
DEMO) so the page is always useful.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st

import config
from pipelines.ports_vessels import (
    read_snapshot as read_vessels,
    port_congestion, chokepoint_traffic, is_demo_snapshot,
)
from analytics.risk_score import load_signals
from components import (
    render_filters_sidebar, apply_filters,
    inject_global_css, apply_light, map_kwargs,
    render_api_status, render_cold_start_banner_if_needed,
    render_brand_header, render_brand_footer, LOGO_PATH,
    TEXT_MUTED, BORDER, ACCENT, WARNING,
)
from pipelines import bootstrap


st.set_page_config(
    page_title="Ships - Supply Chain Pulse",
    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else None,
    layout="wide",
)
inject_global_css()
bootstrap.ensure_bootstrap()
render_brand_header()
st.markdown("## Live vessel traffic")

flt = render_filters_sidebar()
render_cold_start_banner_if_needed()

vessels    = read_vessels()
congestion = port_congestion()
chokes     = chokepoint_traffic()


# --------------------------------------------------------------------------- #
# KPIs
# --------------------------------------------------------------------------- #
k1, k2, k3, k4 = st.columns(4)
k1.metric("Vessels tracked", f"{len(vessels):,}")
k2.metric("Ports monitored", len(config.MAJOR_PORTS))
elevated = sum(1 for c in congestion if c["congestion"] >= 0.5)
k3.metric("Ports with elevated density", elevated)
snap_ts = vessels[0]["ts_utc"] if vessels else None
k4.metric("Snapshot", snap_ts[11:19] + " UTC" if snap_ts else "-")


# --------------------------------------------------------------------------- #
# Map
# --------------------------------------------------------------------------- #
port_df = pd.DataFrame(congestion)
port_df["radius"] = (port_df["vessels_nearby"].astype(float) * 4000 + 35000).astype(int)
port_df["fill"]   = port_df["congestion"].apply(
    lambda c: [220, 38, 38, 180] if c >= 0.7
    else [217, 119, 6, 180] if c >= 0.4
    else [16, 163, 116, 180]
)

vessel_df = pd.DataFrame(vessels) if vessels else pd.DataFrame(columns=["lat", "lon"])

deck = pdk.Deck(
    initial_view_state=pdk.ViewState(latitude=20, longitude=20, zoom=1.3),
    layers=[
        pdk.Layer(
            "ScatterplotLayer",
            data=vessel_df,
            get_position="[lon, lat]",
            get_radius=9000,
            get_fill_color=[8, 145, 178, 130],
            opacity=0.55,
        ),
        pdk.Layer(
            "ScatterplotLayer",
            data=port_df,
            get_position="[lon, lat]",
            get_radius="radius",
            get_fill_color="fill",
            stroked=True,
            get_line_color=[255, 255, 255, 230],
            line_width_min_pixels=1,
            pickable=True,
        ),
    ],
    tooltip={"text": "{port}: {vessels_nearby} vessels within 50km"},
    **map_kwargs(),
)
st.pydeck_chart(deck, use_container_width=True)


# --------------------------------------------------------------------------- #
# Port congestion leaderboard
# --------------------------------------------------------------------------- #
st.markdown("### Port congestion proxy")
lb = pd.DataFrame(congestion).sort_values("vessels_nearby", ascending=False)
fig = px.bar(
    lb, x="port", y="vessels_nearby", color="congestion",
    color_continuous_scale=[[0, "#10A37F"], [0.5, "#D97706"], [1, "#DC2626"]],
    labels={"vessels_nearby": "Vessels within 50 km"},
)
apply_light(fig, height=380, margin=dict(l=10, r=10, t=10, b=100),
            xaxis_tickangle=-35, coloraxis_showscale=False)
st.plotly_chart(fig, use_container_width=True)

with st.expander("Full port table"):
    st.dataframe(lb, use_container_width=True, hide_index=True)


# --------------------------------------------------------------------------- #
# Chokepoint traffic
# --------------------------------------------------------------------------- #
st.markdown("### Chokepoint traffic")
ck = pd.DataFrame(chokes).sort_values("vessels_nearby", ascending=False)
fig2 = px.bar(
    ck, x="name", y="vessels_nearby", color="intensity",
    color_continuous_scale=[[0, "#10A37F"], [0.5, "#D97706"], [1, "#DC2626"]],
)
apply_light(fig2, height=320, margin=dict(l=10, r=10, t=10, b=80),
            xaxis_tickangle=-25, coloraxis_showscale=False)
st.plotly_chart(fig2, use_container_width=True)


# --------------------------------------------------------------------------- #
# Vessel type breakdown
# --------------------------------------------------------------------------- #
if vessels:
    st.markdown("### Vessel type breakdown")
    vt = pd.DataFrame(vessels)
    vt["ship_type"] = vt["ship_type"].replace("", "Unknown").fillna("Unknown")
    counts = vt.groupby("ship_type").size().sort_values(ascending=False).head(25)
    fig3 = px.bar(counts.reset_index(name="count"), x="ship_type", y="count",
                  color_discrete_sequence=["#0891B2"])
    apply_light(fig3, height=320, margin=dict(l=10, r=10, t=10, b=80),
                xaxis_tickangle=-25)
    st.plotly_chart(fig3, use_container_width=True)


# --------------------------------------------------------------------------- #
# Freight signals
# --------------------------------------------------------------------------- #
st.markdown("### Freight / port congestion signals")
blob = load_signals()
sigs = apply_filters(blob.get("signals", []), flt)
freight_sigs = [s for s in sigs if s.get("category") == "freight"]
if not freight_sigs:
    st.info("No freight signals with the current filters.")
else:
    df = pd.DataFrame(freight_sigs)
    st.dataframe(
        df[["timestamp_utc", "severity", "title"]]
          .sort_values("severity", ascending=False),
        use_container_width=True, hide_index=True,
        column_config={
            "severity": st.column_config.ProgressColumn(
                "severity", min_value=0.0, max_value=1.0, format="%.2f"
            ),
        },
    )


# --------------------------------------------------------------------------- #
# API health footer
# --------------------------------------------------------------------------- #
render_api_status()
render_brand_footer()
