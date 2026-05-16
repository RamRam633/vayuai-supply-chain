"""
Events page - searchable, filterable global event feed with intelligence.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.risk_score import load_signals
from components import (
    render_filters_sidebar, apply_filters, filter_summary_caption,
    inject_global_css, apply_light,
    render_api_status, render_cold_start_banner_if_needed,
    setup_brand, render_brand_topbar, render_brand_header, render_brand_footer, LOGO_PATH,
    TEXT, TEXT_MUTED, BORDER,
)
from pipelines import bootstrap


st.set_page_config(
    page_title="Events - Supply Chain Pulse",
    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else None,
    layout="wide",
)
inject_global_css()
setup_brand()
bootstrap.ensure_bootstrap()
render_brand_topbar(section="Events")
render_brand_header()
st.markdown("## Global event feed")

blob = load_signals()
all_signals = blob.get("signals", [])
country_options = sorted({s["region"] for s in all_signals if s.get("region")})
flt = render_filters_sidebar(country_options=country_options)

signals = apply_filters(all_signals, flt)
filter_summary_caption(flt, len(all_signals), len(signals))

# Cold-start banner - explains the empty state on first load.
cold = render_cold_start_banner_if_needed()

if not signals:
    if not cold:
        st.info(
            "No signals match the current filters. Try widening the time "
            "window, clearing categories, or hitting **Refresh data now** "
            "in the sidebar."
        )
    render_api_status()
    render_brand_footer()
    st.stop()

df = pd.DataFrame(signals)

# --------------------------------------------------------------------------- #
# Top-line breakdowns
# --------------------------------------------------------------------------- #
c1, c2 = st.columns(2)
with c1:
    st.markdown("#### By category")
    cc = df["category"].value_counts().reset_index()
    cc.columns = ["category", "count"]
    fig = px.bar(cc, x="category", y="count", color="category")
    apply_light(fig, height=300, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

with c2:
    st.markdown("#### By source")
    sc = df["source"].value_counts().reset_index()
    sc.columns = ["source", "count"]
    fig2 = px.bar(sc, x="source", y="count",
                  color_discrete_sequence=["#d4af37"])
    apply_light(fig2, height=300, xaxis_tickangle=-25)
    st.plotly_chart(fig2, use_container_width=True)


# --------------------------------------------------------------------------- #
# Severity distribution + signal volume over time
# --------------------------------------------------------------------------- #
c3, c4 = st.columns(2)
with c3:
    st.markdown("#### Severity distribution")
    fig3 = px.histogram(df, x="severity", nbins=20, color="category")
    apply_light(fig3, height=300, bargap=0.05)
    st.plotly_chart(fig3, use_container_width=True)

with c4:
    st.markdown("#### Signal volume over time")
    df["ts"] = pd.to_datetime(df["timestamp_utc"], errors="coerce", utc=True)
    tdf = df.dropna(subset=["ts"]).copy()
    if not tdf.empty:
        tdf["hour"] = tdf["ts"].dt.floor("h")
        vol = tdf.groupby(["hour", "category"]).size().reset_index(name="count")
        fig4 = px.area(vol, x="hour", y="count", color="category")
        apply_light(fig4, height=300)
        st.plotly_chart(fig4, use_container_width=True)


# --------------------------------------------------------------------------- #
# Full sortable table
# --------------------------------------------------------------------------- #
st.markdown("#### All matching signals")
sort_col = st.selectbox("Sort by",
                        ["timestamp_utc", "severity", "category", "source"],
                        index=1)
ascending = st.toggle("Ascending", value=False)
view = df.sort_values(sort_col, ascending=ascending).reset_index(drop=True)
view["timestamp_utc"] = pd.to_datetime(view["timestamp_utc"], errors="coerce").astype(str)

st.dataframe(
    view[["timestamp_utc", "source", "category", "severity", "title", "region", "url"]],
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
