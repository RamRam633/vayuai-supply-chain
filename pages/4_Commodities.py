"""
Commodities page — full daily history, FRED macro/freight series,
and any commodity/macro signals that fired.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import config
from pipelines.commodities import fetch_prices, is_demo_prices
from pipelines.macro import fetch_all_series
from analytics.risk_score import load_signals
from components import (
    render_filters_sidebar, apply_filters,
    inject_global_css, apply_light,
    render_api_status, render_cold_start_banner_if_needed,
    TEXT_MUTED, ACCENT,
)
from pipelines import bootstrap


st.set_page_config(page_title="Commodities — Pulse", layout="wide")
inject_global_css()
bootstrap.ensure_bootstrap()
st.markdown("## Commodity & macro detail")

flt = render_filters_sidebar()
render_cold_start_banner_if_needed()


# --------------------------------------------------------------------------- #
# Commodity price history
# --------------------------------------------------------------------------- #
df = fetch_prices()
if df.empty:
    st.warning(
        "No commodity price history available — the FRED and Datahub fetches "
        "both failed on the last refresh. Try **Refresh data now** in the "
        "sidebar; details are in the API health strip at the bottom of the page."
    )
else:
    st.markdown("### Commodity prices")
    tab1, tab2, tab3, tab4 = st.tabs([
        "Rebased (90d)",
        "Per-commodity drill-down",
        "Returns heatmap",
        "All raw price grid",
    ])

    # --- Rebased overlay --------------------------------------------------- #
    with tab1:
        norm = df.tail(90).copy()
        # Use the FIRST common date to anchor all series so curves overlap
        # cleanly without orphaned segments.
        common_start = norm.dropna(how="any").index.min()
        if pd.notna(common_start):
            norm = norm.loc[common_start:]
            for col in norm.columns:
                base = norm[col].dropna()
                if not base.empty and base.iloc[0]:
                    norm[col] = norm[col] / base.iloc[0] * 100
        fig = px.line(norm, x=norm.index, y=norm.columns)
        fig.update_traces(line=dict(width=1.6), connectgaps=True)
        apply_light(
            fig, height=440, hovermode="x unified",
            yaxis_title="Index (start = 100)",
            legend=dict(
                orientation="h", y=-0.18,
                x=0, xanchor="left",
                font=dict(size=11),
            ),
        )
        st.plotly_chart(fig, use_container_width=True)

    # --- Per-commodity with severe-event overlay -------------------------- #
    with tab2:
        c_left, c_right = st.columns([1, 3])
        choice = c_left.selectbox(
            "Commodity", options=list(df.columns), key="commo_pick"
        )
        window = c_right.selectbox(
            "Window",
            options=["30d", "60d", "90d", "180d", "365d"],
            index=2, key="commo_window",
        )
        days_map = {"30d": 30, "60d": 60, "90d": 90, "180d": 180, "365d": 365}
        series = df[choice].dropna().tail(days_map[window])

        if series.empty:
            st.info("No data for this commodity.")
        else:
            # Severe signals to overlay (any category, sev ≥ 0.6)
            blob = load_signals()
            all_sigs = blob.get("signals", [])
            severe = [
                s for s in all_sigs
                if (s.get("severity") or 0) >= 0.6
                   and s.get("timestamp_utc")
            ]

            # Bucket severe events by day so we can plot a bar height.
            ev_df = pd.DataFrame(severe)
            if not ev_df.empty:
                ev_df["day"] = pd.to_datetime(
                    ev_df["timestamp_utc"], errors="coerce", utc=True
                ).dt.tz_localize(None).dt.normalize()
                ev_df = ev_df.dropna(subset=["day"])
                ev_df = ev_df[ev_df["day"] >= series.index.min()]
                daily = (
                    ev_df.groupby("day")
                         .agg(
                             count=("severity", "size"),
                             max_sev=("severity", "max"),
                         )
                         .reset_index()
                )
            else:
                daily = pd.DataFrame(columns=["day", "count", "max_sev"])

            from plotly.subplots import make_subplots
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(
                go.Scatter(
                    x=series.index, y=series.values, mode="lines",
                    name=choice, line=dict(color=ACCENT, width=2.0),
                    hovertemplate=f"<b>{choice}</b><br>%{{x|%Y-%m-%d}}<br>"
                                  "$%{y:.2f}<extra></extra>",
                ),
                secondary_y=False,
            )
            if not daily.empty:
                fig.add_trace(
                    go.Bar(
                        x=daily["day"], y=daily["count"],
                        name="severe signals (≥0.6)",
                        marker=dict(
                            color="#DC2626", opacity=0.35,
                            line=dict(width=0),
                        ),
                        hovertemplate=(
                            "<b>%{x|%Y-%m-%d}</b><br>"
                            "severe events: %{y}<extra></extra>"
                        ),
                    ),
                    secondary_y=True,
                )
            apply_light(
                fig, height=460,
                title=dict(
                    text=f"{choice} — last close ${series.iloc[-1]:.2f}",
                    font=dict(size=14),
                ),
                legend=dict(orientation="h", y=-0.18, x=0, xanchor="left"),
                margin=dict(l=10, r=10, t=40, b=10),
            )
            fig.update_yaxes(title_text="price", secondary_y=False)
            fig.update_yaxes(title_text="# severe signals", secondary_y=True,
                             showgrid=False)
            st.plotly_chart(fig, use_container_width=True)

            # Quick stats
            ret_1d  = series.pct_change(fill_method=None).iloc[-1] if len(series) > 1 else 0
            ret_30d = (series.iloc[-1] / series.iloc[-30] - 1) if len(series) >= 30 else 0
            ret_90d = (series.iloc[-1] / series.iloc[-90] - 1) if len(series) >= 90 else 0
            vol     = series.pct_change(fill_method=None).std() * 100

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Last close", f"${series.iloc[-1]:.2f}",
                      f"{ret_1d * 100:+.2f}% 1d")
            m2.metric("30d return",  f"{ret_30d * 100:+.2f}%")
            m3.metric("90d return",  f"{ret_90d * 100:+.2f}%")
            m4.metric("Daily vol",   f"{vol:.2f}%")

    # --- Returns heatmap --------------------------------------------------- #
    with tab3:
        rets = df.pct_change(fill_method=None).tail(60) * 100
        fig3 = px.imshow(
            rets.T, color_continuous_scale="RdBu_r",
            aspect="auto", origin="lower",
            labels={"color": "% return"},
        )
        apply_light(fig3, height=440)
        st.plotly_chart(fig3, use_container_width=True)

    # --- Small-multiples grid --------------------------------------------- #
    with tab4:
        cols = list(df.columns)
        rows = [cols[i:i + 2] for i in range(0, len(cols), 2)]
        for row in rows:
            cs = st.columns(len(row))
            for col_name, ph in zip(row, cs):
                with ph:
                    s = df[col_name].dropna().tail(120)
                    if s.empty:
                        st.info(f"{col_name}: no data")
                        continue
                    fig_s = go.Figure(
                        go.Scatter(
                            x=s.index, y=s.values, mode="lines",
                            line=dict(color=ACCENT, width=1.6),
                        )
                    )
                    apply_light(
                        fig_s, height=200,
                        margin=dict(l=10, r=10, t=30, b=10),
                        title=dict(text=f"{col_name} — {s.iloc[-1]:.2f}",
                                   font=dict(size=12)),
                        showlegend=False,
                    )
                    st.plotly_chart(fig_s, use_container_width=True)

    # Latest snapshot table
    rets_all = df.pct_change(fill_method=None)
    latest = rets_all.iloc[-1]
    vol    = rets_all.iloc[-21:-1].std()
    z      = (latest / vol).fillna(0.0)
    snap = pd.DataFrame({
        "Last close":  df.iloc[-1],
        "1d return %": (latest * 100).round(2),
        "20d vol %":   (vol * 100).round(2),
        "z-score":     z.round(2),
    }).sort_values("z-score", ascending=False)
    st.markdown("### Latest snapshot")
    st.dataframe(
        snap, use_container_width=True,
        column_config={
            "z-score": st.column_config.NumberColumn("z-score", format="%.2f"),
        },
    )


# --------------------------------------------------------------------------- #
# FRED macro series
# --------------------------------------------------------------------------- #
st.markdown("### Macro & freight series")
series = fetch_all_series()
if not series:
    st.info(
        "No macro series available right now. Without a `FRED_API_KEY` the "
        "page falls back to Datahub.io daily mirrors plus a Frankfurter FX "
        "basket — both failed on the last refresh."
    )
else:
    for name, s in series.items():
        tail = s.tail(365)
        fig = go.Figure(
            go.Scatter(x=tail.index, y=tail.values, mode="lines",
                       line=dict(color=ACCENT, width=1.8))
        )
        apply_light(
            fig, height=220,
            margin=dict(l=10, r=10, t=40, b=10),
            title=dict(text=name, font=dict(size=13)),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)


# --------------------------------------------------------------------------- #
# Commodity / macro shock signals
# --------------------------------------------------------------------------- #
st.markdown("### Commodity & macro signals")
blob = load_signals()
sigs = apply_filters(blob.get("signals", []), flt)
cm = [s for s in sigs if s.get("category") in ("commodity", "macro")]
if not cm:
    st.info("No commodity/macro shock signals with the current filters.")
else:
    sdf = pd.DataFrame(cm)
    st.dataframe(
        sdf[["timestamp_utc", "category", "severity", "title"]]
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
