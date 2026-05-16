"""
Trends & News page — public-discourse view.

Sources: Google News RSS + Reddit RSS (no keys). We chart:
  * theme volume (article count per theme over time)
  * term frequency (top words across recent signal titles, all categories)
  * outlet breakdown
  * live news feed (Google News + Reddit) with filters
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.risk_score import load_signals
from components import (
    render_filters_sidebar, apply_filters, filter_summary_caption,
    inject_global_css, apply_light,
    TEXT, TEXT_MUTED, BORDER, BG, BG_MUTED, ACCENT, ACCENT_DEEP, CRITICAL,
)


st.set_page_config(page_title="Trends & News — Pulse", layout="wide")
inject_global_css()
st.markdown("## Trends & News")
st.caption(
    "Public-discourse view: live headlines, theme volume, and the words "
    "moving through every monitored channel right now."
)


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
flt = render_filters_sidebar()
blob = load_signals()
all_signals = blob.get("signals", [])
signals = apply_filters(all_signals, flt)
filter_summary_caption(flt, len(all_signals), len(signals))

news_sigs = [s for s in signals if s.get("category") == "news"]
gnews = [s for s in news_sigs if s.get("source") == "google-news"]
reddit = [s for s in news_sigs if s.get("source") == "reddit"]


# --------------------------------------------------------------------------- #
# KPIs
# --------------------------------------------------------------------------- #
def _theme(s):
    return (s.get("payload") or {}).get("theme") or "—"


themes = Counter(_theme(s) for s in gnews)
outlets = Counter(
    (s.get("payload") or {}).get("outlet", "")
    for s in gnews if (s.get("payload") or {}).get("outlet")
)
subs = Counter(
    (s.get("payload") or {}).get("subreddit", "")
    for s in reddit if (s.get("payload") or {}).get("subreddit")
)

k1, k2, k3, k4 = st.columns(4)
k1.metric("News articles", f"{len(gnews):,}")
k2.metric("Reddit posts",  f"{len(reddit):,}")
top_theme  = themes.most_common(1)[0][0]  if themes  else "—"
top_outlet = outlets.most_common(1)[0][0] if outlets else "—"
k3.metric("Top theme",     top_theme)
k4.metric("Top outlet",    top_outlet[:24] if top_outlet else "—")


# --------------------------------------------------------------------------- #
# Theme volume — bar
# --------------------------------------------------------------------------- #
st.markdown("### Theme volume")
if not themes:
    st.info(
        "No news signals matched. Try the **News & social** preset in the "
        "sidebar to widen filters."
    )
else:
    tdf = (
        pd.DataFrame(themes.most_common(), columns=["theme", "articles"])
          .sort_values("articles", ascending=True)
    )
    fig = px.bar(
        tdf, x="articles", y="theme", orientation="h",
        color="articles",
        color_continuous_scale=[[0, "#10A37F"], [0.5, "#D97706"], [1, "#DC2626"]],
    )
    apply_light(fig, height=320, coloraxis_showscale=False,
                margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)


# --------------------------------------------------------------------------- #
# Theme volume over time (hourly area)
# --------------------------------------------------------------------------- #
if gnews:
    st.markdown("### Theme volume over time")
    rows = []
    for s in gnews:
        try:
            ts = pd.to_datetime(s["timestamp_utc"], errors="coerce", utc=True)
            if pd.isna(ts):
                continue
            rows.append({"ts": ts.floor("h"), "theme": _theme(s)})
        except Exception:
            continue
    if rows:
        tdf2 = (
            pd.DataFrame(rows).groupby(["ts", "theme"]).size()
            .reset_index(name="count")
        )
        fig2 = px.area(tdf2, x="ts", y="count", color="theme",
                       line_shape="spline")
        apply_light(fig2, height=300, hovermode="x unified",
                    legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(fig2, use_container_width=True)


# --------------------------------------------------------------------------- #
# Term frequency (across ALL filtered signals — not just news)
# --------------------------------------------------------------------------- #
st.markdown("### Term frequency")
st.caption(
    "Tokens that recur across every signal title in the current filter set — "
    "news, weather alerts, GDELT articles, port alerts, EONET events, all of it."
)

STOPWORDS = set("""
the and for with from this that into over under after before about during near
its their our your his her them they these those will would could should also
been being have has had does did not but yet new newly today week month year
days hours minutes month-year per inc llc ltd co corp company plc
""".split()) | {
    "rt", "via", "amid", "amidst",
    "—", "-", "•", "&amp;", "&", "|", "—",
    "say", "says", "said", "report", "reports", "reported",
    "u.s.", "us", "u.k.", "uk", "eu", "un",
}

_word_re = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}")
tokens: Counter[str] = Counter()
for s in signals:
    title = (s.get("title") or "").lower()
    for w in _word_re.findall(title):
        if w in STOPWORDS or len(w) < 3:
            continue
        tokens[w] += 1

if not tokens:
    st.info("No tokens to score with the current filters.")
else:
    tf = pd.DataFrame(tokens.most_common(40), columns=["term", "count"])
    fig_tf = px.bar(
        tf, x="count", y="term", orientation="h",
        color="count",
        color_continuous_scale=[[0, "#E5E7EB"], [1, "#0E0E0E"]],
    )
    apply_light(fig_tf, height=620, coloraxis_showscale=False,
                margin=dict(l=10, r=10, t=10, b=10),
                yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig_tf, use_container_width=True)


# --------------------------------------------------------------------------- #
# Outlet breakdown
# --------------------------------------------------------------------------- #
if outlets:
    st.markdown("### Top outlets")
    odf = (
        pd.DataFrame(outlets.most_common(20), columns=["outlet", "articles"])
          .sort_values("articles", ascending=True)
    )
    fig_o = px.bar(odf, x="articles", y="outlet", orientation="h",
                   color_discrete_sequence=["#1F2937"])
    apply_light(fig_o, height=420, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_o, use_container_width=True)


# --------------------------------------------------------------------------- #
# Live news feed
# --------------------------------------------------------------------------- #
st.markdown("### Live news feed")
feed_tabs = st.tabs(["Google News", "Reddit"])


def _humanize(ts: str) -> str:
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - t
        mins = int(delta.total_seconds() // 60)
        if mins < 60:
            return f"{mins}m ago"
        if mins < 24 * 60:
            return f"{mins // 60}h ago"
        return f"{mins // (24 * 60)}d ago"
    except Exception:
        return ""


def _render_news_card(s: dict) -> None:
    pl = s.get("payload") or {}
    when = _humanize(s.get("timestamp_utc", ""))
    title = s.get("title", "")
    url = s.get("url")
    title_md = (
        f"<a href='{url}' target='_blank' style='color:{TEXT};"
        f"text-decoration:none'>{title}</a>" if url else title
    )
    meta_parts = []
    if pl.get("outlet"):
        meta_parts.append(pl["outlet"])
    if pl.get("subreddit"):
        meta_parts.append(f"r/{pl['subreddit']}")
    if pl.get("theme"):
        meta_parts.append(pl["theme"])
    meta = " · ".join(meta_parts) or s.get("source", "")
    sev = float(s.get("severity", 0) or 0)
    rail = (
        CRITICAL if sev >= 0.7 else "#D97706" if sev >= 0.45 else ACCENT_DEEP
    )
    summary = (pl.get("summary") or "").strip()
    summary_html = (
        f"<div style='font-size:0.83rem;color:{TEXT_MUTED};margin-top:4px;"
        f"line-height:1.4'>{summary[:240]}</div>" if summary else ""
    )
    st.markdown(
        f"""
        <div style='border:1px solid {BORDER};border-left:3px solid {rail};
                    background:{BG};border-radius:10px;padding:12px 14px;
                    margin-bottom:8px'>
          <div style='font-size:0.72rem;color:{TEXT_MUTED};
                      margin-bottom:4px'>
            {meta} · {when} · sev {sev:.2f}
          </div>
          <div style='font-size:0.95rem;color:{TEXT};line-height:1.35;
                      font-weight:500'>
            {title_md}
          </div>
          {summary_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


with feed_tabs[0]:
    if not gnews:
        st.info("No Google News articles in the current filters.")
    else:
        ordered = sorted(gnews, key=lambda s: s.get("timestamp_utc", ""),
                         reverse=True)[:50]
        for s in ordered:
            _render_news_card(s)

with feed_tabs[1]:
    if not reddit:
        st.info("No Reddit posts in the current filters.")
    else:
        ordered = sorted(reddit, key=lambda s: s.get("timestamp_utc", ""),
                         reverse=True)[:50]
        for s in ordered:
            _render_news_card(s)
