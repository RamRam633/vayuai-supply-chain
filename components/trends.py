"""
Commodity & macro trend charts — light theme, with graceful empty-state.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from pipelines.commodities import fetch_prices
from pipelines.macro import fetch_all_series, is_demo_macro
from .theme import apply_light, ACCENT, TEXT_MUTED


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        s = out[col].dropna()
        if s.empty:
            continue
        base = s.iloc[0]
        if base:
            out[col] = out[col] / base * 100
    return out


def render_trends() -> None:
    tab_c, tab_m = st.tabs(["Commodities (90d, rebased)", "Macro / Freight"])

    with tab_c:
        df = fetch_prices()
        if df.empty:
            st.info(
                "No commodity data available. yfinance is occasionally blocked "
                "by Yahoo; Stooq fallback runs automatically — refresh data "
                "from the sidebar to retry."
            )
        else:
            norm = _normalize(df.tail(90))
            fig = go.Figure()
            for col in norm.columns:
                fig.add_trace(
                    go.Scatter(
                        x=norm.index, y=norm[col], mode="lines", name=col,
                        line=dict(width=1.6),
                        hovertemplate=f"<b>{col}</b><br>%{{x|%Y-%m-%d}}<br>idx %{{y:.1f}}<extra></extra>",
                    )
                )
            apply_light(
                fig,
                height=420,
                hovermode="x unified",
                yaxis_title="Index (start = 100)",
                legend=dict(orientation="h", y=-0.2),
            )
            st.plotly_chart(fig, use_container_width=True)

    with tab_m:
        if not config.FRED_API_KEY:
            st.warning(
                "Set `FRED_API_KEY` in `.env` to enable macro/freight series. "
                "Free key: https://fredaccount.stlouisfed.org/apikeys"
            )
            return
        series = fetch_all_series()
        if not series:
            st.info("Macro series unavailable. FRED may be rate-limiting.")
            return
        for name, s in series.items():
            tail = s.tail(180)
            fig = go.Figure(
                go.Scatter(x=tail.index, y=tail.values, mode="lines",
                           line=dict(color=ACCENT, width=1.8))
            )
            apply_light(
                fig,
                height=200,
                margin=dict(l=10, r=10, t=30, b=10),
                title=dict(text=name, font=dict(size=13)),
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)
