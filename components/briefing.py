"""
Auto-generated briefing strip + supporting intelligence widgets.

The briefing strip is the "what should I know in the next 30 seconds"
card — three to five computed insights pulled from the current signal
snapshot, with no LLM call. It runs every page load.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

import config
from analytics.risk_score import top_risks
from components.theme import (
    apply_light, ACCENT, ACCENT_DEEP, CRITICAL, WARNING, INFO, TEXT, TEXT_MUTED,
    BG, BORDER,
)


# --------------------------------------------------------------------------- #
# Insight extractors
# --------------------------------------------------------------------------- #
def _top_region_insight(regional: dict) -> str | None:
    top = top_risks(regional, n=2)
    if not top or top[0][1] <= 0:
        return None
    region, score = top[0]
    runner = (
        f"; {top[1][0]} at {top[1][1]:.0f}" if len(top) > 1 and top[1][1] > 0 else ""
    )
    return f"**{region}** carries the highest pressure at **{score:.0f}/100**{runner}."


def _commodity_mover_insight(signals: list[dict]) -> str | None:
    cm = [s for s in signals if s.get("category") in ("commodity", "macro")]
    if not cm:
        return None
    top = max(cm, key=lambda s: s.get("severity", 0))
    return f"Markets: **{top['title']}**."


def _natural_event_insight(signals: list[dict]) -> str | None:
    nats = [s for s in signals if s.get("category") in ("natural", "volcanic")]
    if not nats:
        return None
    cnt = Counter()
    for s in nats:
        cat = (s.get("payload") or {}).get("eonet_category") or s.get("category")
        cnt[cat] += 1
    parts = ", ".join(f"{n} {k}" for k, n in cnt.most_common(3))
    return f"Natural events open: **{parts}** ({len(nats)} total)."


def _tropical_insight(signals: list[dict]) -> str | None:
    trop = [s for s in signals if s.get("category") == "tropical"]
    if not trop:
        return None
    worst = max(trop, key=lambda s: s.get("severity", 0))
    return f"Tropical: **{worst['title']}** ({len(trop)} active)."


def _aviation_insight(signals: list[dict]) -> str | None:
    av = [s for s in signals if s.get("category") == "flight"]
    if not av:
        return None
    worst = max(av, key=lambda s: s.get("severity", 0))
    return f"Aviation: **{worst['title']}**."


def _seismic_insight(signals: list[dict]) -> str | None:
    sm = [s for s in signals if s.get("category") == "seismic"]
    if not sm:
        return None
    # Largest magnitude in payload
    biggest = max(
        sm,
        key=lambda s: float((s.get("payload") or {}).get("magnitude", 0) or 0),
    )
    mag = (biggest.get("payload") or {}).get("magnitude")
    if mag and float(mag) >= 5.5:
        return f"Seismic: **{biggest['title']}**."
    return f"Seismic activity: **{len(sm)} M4.5+ events** logged."


def _chokepoint_insight(signals: list[dict]) -> str | None:
    """Any signal with coords within a chokepoint's radius is flagged."""
    import math

    def _hav(lat1, lon1, lat2, lon2):
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
            math.radians(lat2)
        ) * math.sin(dlon / 2) ** 2
        return 2 * R * math.asin(math.sqrt(a))

    hits = Counter()
    for s in signals:
        if s.get("lat") is None or s.get("lon") is None:
            continue
        for ck in config.CHOKEPOINTS:
            if _hav(ck["lat"], ck["lon"], s["lat"], s["lon"]) <= ck["radius_km"]:
                hits[ck["name"]] += 1
                break
    if not hits:
        return None
    top = hits.most_common(1)[0]
    return f"Chokepoint exposure: **{top[1]} signals** near **{top[0]}**."


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #
def render_briefing(signals: list[dict], regional: dict) -> None:
    """Top-of-page intelligence card — 3 to 6 computed bullets."""
    extractors = [
        _top_region_insight(regional),
        _commodity_mover_insight(signals),
        _tropical_insight(signals),
        _aviation_insight(signals),
        _natural_event_insight(signals),
        _seismic_insight(signals),
        _chokepoint_insight(signals),
    ]
    insights = [x for x in extractors if x]
    if not insights:
        return

    bullets = "".join(
        f"<li style='margin:4px 0;color:{TEXT};line-height:1.45'>{x}</li>"
        for x in insights[:6]
    )
    st.markdown(
        f"""
        <div class='pulse-card' style='border-left:3px solid {ACCENT};
                    padding-left:18px;background:{BG}'>
          <div style='font-size:0.72rem;color:{TEXT_MUTED};
                      text-transform:uppercase;letter-spacing:0.06em;
                      margin-bottom:6px'>
            Today's briefing
          </div>
          <ul style='margin:0;padding-left:18px;font-size:0.95rem'>
            {bullets}
          </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Pressure heatmap (region × component)
# --------------------------------------------------------------------------- #
def render_pressure_heatmap(regional: dict) -> None:
    """Heatmap of regions × risk components — at-a-glance pressure map."""
    if not regional:
        return
    rows = []
    for r, m in regional.items():
        row = {"region": r, **(m.get("components") or {})}
        rows.append(row)
    df = pd.DataFrame(rows).set_index("region").fillna(0.0)
    # Show as 0..100 for human readability.
    df = (df * 100).round(0)

    fig = px.imshow(
        df,
        color_continuous_scale=[
            [0.0,  "#F7F7F8"],
            [0.25, "#FEF3C7"],
            [0.50, "#FED7AA"],
            [0.75, "#FCA5A5"],
            [1.00, "#DC2626"],
        ],
        aspect="auto",
        origin="upper",
        text_auto=".0f",
        labels={"color": "level (0-100)"},
        zmin=0, zmax=100,
    )
    apply_light(
        fig,
        height=380, margin=dict(l=10, r=10, t=10, b=80),
        xaxis=dict(tickangle=-35, side="bottom"),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig, use_container_width=True)


# --------------------------------------------------------------------------- #
# Top movers strip — uses analytics.history.score_deltas() if available
# --------------------------------------------------------------------------- #
def render_top_movers(regional: dict, deltas: dict[str, float] | None) -> None:
    """Compact strip showing regions whose score moved most since last refresh."""
    if not deltas:
        return
    movers = sorted(deltas.items(), key=lambda kv: abs(kv[1]), reverse=True)[:5]
    if not movers:
        return
    chips = []
    for region, delta in movers:
        score = regional.get(region, {}).get("score", 0)
        color = CRITICAL if delta > 0 else "#16A34A"
        arrow = "▲" if delta > 0 else "▼"
        chips.append(
            f"<div style='border:1px solid {BORDER};border-radius:10px;"
            f"padding:8px 12px;background:{BG};display:inline-block;"
            f"margin-right:8px;margin-bottom:6px'>"
            f"<div style='font-size:0.7rem;color:{TEXT_MUTED};"
            f"text-transform:uppercase;letter-spacing:0.05em'>{region}</div>"
            f"<div style='font-size:1.05rem;font-weight:600;color:{TEXT}'>"
            f"{score:.0f} <span style='color:{color};font-size:0.85rem;"
            f"font-weight:500'>{arrow} {abs(delta):.1f}</span></div></div>"
        )
    st.markdown(
        "<div style='margin-bottom:6px;font-size:0.74rem;"
        f"color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:0.06em'>"
        "Biggest movers vs last refresh</div>"
        + "".join(chips),
        unsafe_allow_html=True,
    )
