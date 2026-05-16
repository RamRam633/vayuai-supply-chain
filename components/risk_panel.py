"""
Regional risk score panel — horizontal bars + component breakdown table.
Light-theme palette, colour ramp warming as score rises.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .theme import apply_light, ACCENT, CRITICAL, WARNING, INFO


def _score_color(score: float) -> str:
    if score >= 70:
        return "#DC2626"   # critical
    if score >= 45:
        return "#D97706"   # warning
    if score >= 20:
        return "#F59E0B"   # caution
    return "#10A37F"       # calm


def render_risk_panel(regional: dict[str, dict]) -> None:
    if not regional:
        st.warning("Risk panel: no regional data yet.")
        return

    rows = [
        {
            "Region": r,
            "Score": m["score"],
            "Signals": m["n_signals"],
            **{k: round(v * 100, 1) for k, v in m["components"].items()},
        }
        for r, m in regional.items()
    ]
    df = pd.DataFrame(rows).sort_values("Score", ascending=True)

    fig = go.Figure(
        go.Bar(
            x=df["Score"], y=df["Region"], orientation="h",
            marker_color=[_score_color(s) for s in df["Score"]],
            text=[f"{s:.0f}" for s in df["Score"]],
            textposition="outside",
            customdata=df[["Signals"] + list(df.columns[3:])],
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Score: %{x:.0f}/100<br>"
                "Signals: %{customdata[0]}<extra></extra>"
            ),
        )
    )
    apply_light(
        fig,
        height=420,
        xaxis=dict(range=[0, 100], title="Composite risk (0-100)"),
        yaxis=dict(title=""),
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Component breakdown"):
        st.dataframe(
            df.sort_values("Score", ascending=False).reset_index(drop=True),
            use_container_width=True,
            hide_index=True,
        )
