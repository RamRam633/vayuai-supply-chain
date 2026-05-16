"""
Port Detail page - pick any major port and see local vessel density,
nearby events, current live weather, and a 90-day commodity view that
filters to commodities most relevant to the port's region.
"""

from __future__ import annotations

import math

import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st

import config
from pipelines.ports_vessels import read_snapshot as read_vessels, port_congestion
from analytics.risk_score import load_signals
from components import (
    render_filters_sidebar, apply_filters,
    inject_global_css, apply_light, map_kwargs,
    render_api_status, render_cold_start_banner_if_needed,
    ACCENT, TEXT_MUTED,
)
from pipelines import bootstrap


st.set_page_config(page_title="Port - Pulse", layout="wide")
inject_global_css()
bootstrap.ensure_bootstrap()
st.markdown("## Port drill-down")
render_cold_start_banner_if_needed()

flt = render_filters_sidebar()
port_names = [p["name"] for p in config.MAJOR_PORTS]
choice = st.selectbox("Port", options=port_names)
port = next(p for p in config.MAJOR_PORTS if p["name"] == choice)

vessels = read_vessels()


def _hav(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


local_vessels = [
    v for v in vessels
    if _hav(port["lat"], port["lon"], v["lat"], v["lon"]) <= 100.0
]


# --------------------------------------------------------------------------- #
# Map
# --------------------------------------------------------------------------- #
deck = pdk.Deck(
    initial_view_state=pdk.ViewState(
        latitude=port["lat"], longitude=port["lon"], zoom=8
    ),
    layers=[
        pdk.Layer(
            "ScatterplotLayer",
            data=pd.DataFrame([port]),
            get_position="[lon, lat]",
            get_radius=4000,
            get_fill_color=[245, 158, 11, 220],
            stroked=True,
            get_line_color=[255, 255, 255, 230],
            line_width_min_pixels=2,
        ),
        pdk.Layer(
            "ScatterplotLayer",
            data=pd.DataFrame(local_vessels) if local_vessels else pd.DataFrame(columns=["lat", "lon"]),
            get_position="[lon, lat]",
            get_radius=1100,
            get_fill_color=[8, 145, 178, 200],
            opacity=0.75,
        ),
    ],
    **map_kwargs(),
)
st.pydeck_chart(deck, use_container_width=True)


# --------------------------------------------------------------------------- #
# KPIs
# --------------------------------------------------------------------------- #
cong = next((c for c in port_congestion() if c["port"] == port["name"]),
            {"vessels_nearby": 0, "congestion": 0.0})
k1, k2, k3, k4 = st.columns(4)
k1.metric("Port", port["name"])
k2.metric("Country", port["country"])
k3.metric("Vessels within 50 km", cong["vessels_nearby"])
k4.metric("Congestion proxy", f"{cong['congestion']:.2f}")


# --------------------------------------------------------------------------- #
# Nearby signals
# --------------------------------------------------------------------------- #
st.markdown("### Nearby signals (≤ 500 km)")
blob = load_signals()
all_signals = blob.get("signals", [])
signals = apply_filters(all_signals, flt)


def _near(sig: dict) -> bool:
    if sig.get("lat") is None or sig.get("lon") is None:
        return False
    return _hav(port["lat"], port["lon"], sig["lat"], sig["lon"]) <= 500.0


near = [s for s in signals if _near(s)]
if not near:
    st.info("No location-tagged signals within 500 km of this port.")
else:
    df = pd.DataFrame(near)
    df["distance_km"] = df.apply(
        lambda r: round(_hav(port["lat"], port["lon"], r["lat"], r["lon"]), 1),
        axis=1,
    )
    cb = df["category"].value_counts().reset_index()
    cb.columns = ["category", "count"]
    fig = px.bar(cb, x="category", y="count", color="category")
    apply_light(fig, height=260, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        df[["timestamp_utc", "category", "severity", "title", "distance_km", "url"]]
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
# Current weather
# --------------------------------------------------------------------------- #
st.markdown("### Current weather at the port (Open-Meteo)")
from pipelines.base import get_session

session = get_session(expire_after=config.CACHE_TTL["open_meteo"])
try:
    r = session.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": port["lat"], "longitude": port["lon"],
            "current": "temperature_2m,wind_speed_10m,wind_gusts_10m,precipitation,weather_code",
            "wind_speed_unit": "kmh",
        },
        timeout=15,
    )
    r.raise_for_status()
    wx = (r.json() or {}).get("current") or {}
except Exception as e:
    wx = {}
    st.warning(f"Open-Meteo fetch failed: {e}")

if wx:
    w1, w2, w3, w4 = st.columns(4)
    w1.metric("Temp (°C)",    f"{wx.get('temperature_2m', 0):.1f}")
    w2.metric("Wind (km/h)",  f"{wx.get('wind_speed_10m', 0):.0f}")
    w3.metric("Gusts (km/h)", f"{wx.get('wind_gusts_10m', 0):.0f}")
    w4.metric("Precip (mm)",  f"{wx.get('precipitation', 0):.1f}")


# --------------------------------------------------------------------------- #
# API health footer
# --------------------------------------------------------------------------- #
render_api_status()
