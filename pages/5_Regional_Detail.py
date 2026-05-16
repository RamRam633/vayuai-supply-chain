"""
Regional Detail page — drill into one region with score trend, component
breakdown, signal mix, and a sortable signal table.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import config
from analytics.risk_score import compute_regional_risk, load_signals
from analytics.history import region_trend
from pipelines.base import regions_for_point
from components import (
    render_filters_sidebar, apply_filters,
    inject_global_css, apply_light,
    render_api_status, render_cold_start_banner_if_needed,
    TEXT, TEXT_MUTED, ACCENT, CRITICAL, WARNING,
)
from pipelines import bootstrap


st.set_page_config(page_title="Region — Pulse", layout="wide")
inject_global_css()
bootstrap.ensure_bootstrap()
st.markdown("## Regional drill-down")
render_cold_start_banner_if_needed()

flt = render_filters_sidebar()
region = st.selectbox("Region", options=list(config.REGIONS.keys()))

blob = load_signals()
all_signals = blob.get("signals", [])
signals = apply_filters(all_signals, flt)
regional = compute_regional_risk(signals, lookback_hours=flt["lookback_hours"])
meta = regional.get(region) or {"score": 0, "components": {}, "n_signals": 0}


# --------------------------------------------------------------------------- #
# Header — gauge + components
# --------------------------------------------------------------------------- #
left, right = st.columns([1, 1.1])

with left:
    st.markdown(f"### {region}")
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=meta["score"],
        number={"suffix": "/100", "font": {"size": 36, "color": "#f5f1e8"}},
        gauge={
            "axis":  {"range": [0, 100], "tickfont": {"color": TEXT_MUTED}},
            "bar":   {"color": "#d4af37", "thickness": 0.20},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "steps": [
                {"range": [0, 20],   "color": "#1c2a22"},
                {"range": [20, 45],  "color": "#3a3320"},
                {"range": [45, 70],  "color": "#4a3320"},
                {"range": [70, 100], "color": "#4a2020"},
            ],
        },
    ))
    apply_light(fig, height=300, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)
    st.metric("Signals contributing", meta["n_signals"])

with right:
    st.markdown("### Component breakdown")
    comp = meta["components"] or {}
    if comp:
        rows = pd.DataFrame(
            [{"component": k, "level": round(v, 3)} for k, v in comp.items()]
        ).sort_values("level", ascending=True)
        fig2 = px.bar(
            rows, x="level", y="component", orientation="h",
            color="level",
            color_continuous_scale=[[0, "#10A37F"], [0.5, "#D97706"], [1, "#DC2626"]],
        )
        apply_light(fig2, height=300, xaxis=dict(range=[0, 1]),
                    coloraxis_showscale=False)
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No component data in window.")


# --------------------------------------------------------------------------- #
# Score trend (if we have history)
# --------------------------------------------------------------------------- #
trend = region_trend(region, hours=flt["lookback_hours"])
if not trend.empty and len(trend) > 1:
    st.markdown("### Score trend")
    fig_trend = go.Figure(
        go.Scatter(
            x=trend["timestamp_utc"], y=trend["score"], mode="lines+markers",
            line=dict(color=ACCENT, width=2.0),
        )
    )
    apply_light(fig_trend, height=240, yaxis=dict(range=[0, 100]))
    st.plotly_chart(fig_trend, use_container_width=True)
else:
    st.caption(
        "Trend chart appears once at least two snapshots have been written "
        "(refresh again later to populate)."
    )


# --------------------------------------------------------------------------- #
# Signals in this region
# --------------------------------------------------------------------------- #
st.markdown(f"### Signals tagged to {region}")

def _in_region(sig: dict) -> bool:
    if sig.get("category") in ("commodity", "macro"):
        return True
    if sig.get("region") == region:
        return True
    if sig.get("lat") is not None and sig.get("lon") is not None:
        return region in regions_for_point(sig["lat"], sig["lon"])
    return False

in_region = [s for s in signals if _in_region(s)]
if not in_region:
    st.info("No signals matched for this region.")
else:
    df = pd.DataFrame(in_region)
    cb = df["category"].value_counts().reset_index()
    cb.columns = ["category", "count"]
    fig3 = px.bar(cb, x="category", y="count", color="category")
    apply_light(fig3, height=260, showlegend=False)
    st.plotly_chart(fig3, use_container_width=True)

    st.dataframe(
        df[["timestamp_utc", "category", "severity", "source", "title", "url"]]
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
