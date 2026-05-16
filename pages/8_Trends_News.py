"""
Trends & News - world pulse.

What this page answers:
    * What are people searching right now? (Google Trends, per country)
    * What are people reading right now? (top Wikipedia articles)
    * What phrases are spiking in news headlines? (bigrams over time)
    * What's the supply-chain press cycle doing today? (theme volume,
      outlet mix)
    * What just hit the wire? (live Google News + Reddit feed)

The first three blocks deliberately ignore the supply-chain category
filter - they're a generic 'what's happening in the world' band so the
dashboard isn't blind to non-supply-chain stories that nonetheless
move markets (elections, sports finals, big-tech earnings).
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.risk_score import load_signals
from components import (
    render_filters_sidebar, apply_filters, filter_summary_caption,
    inject_global_css, apply_light,
    render_api_status, render_cold_start_banner_if_needed,
    TEXT, TEXT_MUTED, BORDER, BG, BG_MUTED, ACCENT, ACCENT_DEEP, CRITICAL,
)
from pipelines import bootstrap
from pipelines.global_trends import (
    fetch_all_trends, fetch_wikipedia_top, TRENDS_GEOS,
)


st.set_page_config(page_title="Trends & News - Pulse", layout="wide")
inject_global_css()
bootstrap.ensure_bootstrap()

st.markdown("## Trends & News")
st.markdown(
    f"<div style='color:{TEXT_MUTED};font-size:0.95rem;margin-bottom:14px;"
    f"max-width:780px;line-height:1.5'>"
    "A real-time pulse on what the world is searching, reading, and writing "
    "about. The top half (Google Trends, Wikipedia, trending phrases) is "
    "global - every topic, not just supply chain. The bottom half drills "
    "back into the supply-chain news cycle."
    "</div>",
    unsafe_allow_html=True,
)
render_cold_start_banner_if_needed()


# --------------------------------------------------------------------------- #
# Sidebar filters (only affect the supply-chain news sections at the bottom)
# --------------------------------------------------------------------------- #
flt = render_filters_sidebar()
blob = load_signals()
all_signals = blob.get("signals", [])
signals = apply_filters(all_signals, flt)


# =========================================================================== #
# SECTION 1 - Google Trends per country
# =========================================================================== #
st.markdown("### Trending searches")
st.caption(
    "The queries surging on Google Search in the last ~24 hours, per country. "
    "Numbers are Google's own approximate daily-search-volume estimates."
)

with st.spinner("Fetching Google Trends..."):
    trends_data = fetch_all_trends(geos=[c for c, _ in TRENDS_GEOS[:6]])

if not trends_data:
    st.info(
        "Google Trends RSS didn't return any data. The endpoint is "
        "occasionally rate-limited; try refreshing in a minute."
    )
else:
    country_labels = list(trends_data.keys())
    tabs = st.tabs(country_labels)
    for tab, country in zip(tabs, country_labels):
        with tab:
            rows = trends_data[country]
            # Show top 15 as 3 rows of 5
            cols_per_row = 5
            rows_to_show = rows[:15]
            for i in range(0, len(rows_to_show), cols_per_row):
                chunk = rows_to_show[i:i + cols_per_row]
                cs = st.columns(cols_per_row)
                for c, item in zip(cs, chunk):
                    query = item["query"]
                    traffic = item.get("traffic_str") or "-"
                    news_url = item.get("news_url") or "#"
                    news_title = item.get("news_title") or ""
                    img = item.get("image") or ""
                    img_html = (
                        f"<img src='{img}' style='width:100%;height:90px;"
                        f"object-fit:cover;border-radius:8px;"
                        f"border:1px solid {BORDER};margin-bottom:6px'/>"
                        if img else ""
                    )
                    c.markdown(
                        f"""
                        <a href='{news_url}' target='_blank' style='text-decoration:none'>
                          <div style='border:1px solid {BORDER};
                                      border-radius:10px;padding:10px;
                                      background:{BG};margin-bottom:8px;
                                      min-height:170px'>
                            {img_html}
                            <div style='font-size:0.72rem;color:{ACCENT_DEEP};
                                        text-transform:uppercase;letter-spacing:0.04em;
                                        margin-bottom:4px;font-weight:600'>
                              {traffic} searches
                            </div>
                            <div style='font-size:0.92rem;color:{TEXT};
                                        font-weight:600;line-height:1.3;
                                        margin-bottom:6px'>
                              {query}
                            </div>
                            <div style='font-size:0.74rem;color:{TEXT_MUTED};
                                        line-height:1.35'>
                              {news_title[:90]}{'…' if len(news_title) > 90 else ''}
                            </div>
                          </div>
                        </a>
                        """,
                        unsafe_allow_html=True,
                    )


# =========================================================================== #
# SECTION 2 - Wikipedia most-viewed
# =========================================================================== #
st.markdown("### Most-read on Wikipedia")
st.caption(
    "The articles that pulled the most pageviews on English Wikipedia "
    "yesterday - a clean readout of what people actually wanted to look up."
)

with st.spinner("Fetching Wikipedia top-viewed..."):
    wiki = fetch_wikipedia_top(limit=24)

if not wiki:
    st.info("Wikipedia pageviews endpoint didn't return data.")
else:
    cols_per_row = 4
    for i in range(0, len(wiki), cols_per_row):
        chunk = wiki[i:i + cols_per_row]
        cs = st.columns(cols_per_row)
        for c, item in zip(cs, chunk):
            c.markdown(
                f"""
                <a href='{item['url']}' target='_blank' style='text-decoration:none'>
                  <div style='border:1px solid {BORDER};border-radius:10px;
                              padding:10px 12px;background:{BG};margin-bottom:8px;
                              min-height:84px'>
                    <div style='display:flex;align-items:baseline;
                                justify-content:space-between;margin-bottom:4px'>
                      <span style='font-size:0.72rem;color:{TEXT_MUTED};
                                   font-weight:600'>#{item['rank']}</span>
                      <span style='font-size:0.72rem;color:{ACCENT_DEEP};
                                   font-family:ui-monospace,monospace'>
                        {item['views']:,} views
                      </span>
                    </div>
                    <div style='font-size:0.9rem;color:{TEXT};
                                font-weight:500;line-height:1.3'>
                      {item['title']}
                    </div>
                  </div>
                </a>
                """,
                unsafe_allow_html=True,
            )


# =========================================================================== #
# SECTION 3 - Trending phrases in news (bigrams)
# =========================================================================== #
st.markdown("### Phrases trending in news")
st.caption(
    "Two-word phrases that recur most across recent news headlines. A spike "
    "here often catches a breaking story faster than a single keyword would. "
    "Built from every news + GDELT signal in your filter window - no theme "
    "buckets, no manual queries."
)

STOPWORDS = set("""
the and for with from this that into over under after before about during near
its their our your his her them they these those will would could should also
been being have has had does did not but yet new newly today week month year
days hours minutes month-year per inc llc ltd co corp company plc what who when
why how all any one two three four five six seven eight nine ten than just very
more most some such still even already once never when while because between
""".split()) | {
    "rt", "via", "amid", "amidst", "say", "says", "said",
    "report", "reports", "reported", "us", "uk", "eu", "un",
}

_word_re = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}")


def _tokens(title: str) -> list[str]:
    out = []
    for w in _word_re.findall((title or "").lower()):
        if w in STOPWORDS or len(w) < 3:
            continue
        out.append(w)
    return out


# Build bigrams from every news/geopolitical signal title in window
news_or_geo = [
    s for s in signals
    if s.get("category") in ("news", "geopolitical")
]

bigrams: Counter[str] = Counter()
for s in news_or_geo:
    toks = _tokens(s.get("title", ""))
    for a, b in zip(toks, toks[1:]):
        bigrams[f"{a} {b}"] += 1

if not bigrams:
    st.info("Not enough news in the current filter window to build phrases.")
else:
    top = bigrams.most_common(20)
    bdf = pd.DataFrame(top, columns=["phrase", "mentions"])
    bdf = bdf.sort_values("mentions", ascending=True)
    fig_bg = px.bar(
        bdf, x="mentions", y="phrase", orientation="h",
        color="mentions",
        color_continuous_scale=[[0, "#3a3530"], [0.5, "#d4af37"], [1, "#e07a35"]],
    )
    apply_light(fig_bg, height=460, coloraxis_showscale=False,
                margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_bg, use_container_width=True)


# =========================================================================== #
# SECTION 4 - Supply-chain news (the original page content, with captions)
# =========================================================================== #
st.divider()
st.markdown("## Supply-chain news cycle")
st.caption(
    "Below is the press cycle filtered to the supply-chain themes we monitor "
    "(logistics, chokepoints, markets, geopolitics, labor). Filters in the "
    "sidebar apply from here down."
)
filter_summary_caption(flt, len(all_signals), len(signals))

news_sigs = [s for s in signals if s.get("category") == "news"]
gnews = [s for s in news_sigs if s.get("source") == "google-news"]
reddit = [s for s in news_sigs if s.get("source") == "reddit"]


# KPIs
def _theme(s):
    return (s.get("payload") or {}).get("theme") or "-"


themes = Counter(_theme(s) for s in gnews)
outlets = Counter(
    (s.get("payload") or {}).get("outlet", "")
    for s in gnews if (s.get("payload") or {}).get("outlet")
)

k1, k2, k3, k4 = st.columns(4)
k1.metric("News articles",       f"{len(gnews):,}")
k2.metric("Reddit posts",        f"{len(reddit):,}")
k3.metric("Top theme",           themes.most_common(1)[0][0] if themes else "-")
k4.metric("Top outlet",
          (outlets.most_common(1)[0][0][:24] if outlets else "-"))


# Theme volume bar
st.markdown("### Theme volume")
st.caption(
    "How many articles fell into each supply-chain theme bucket in your "
    "filter window. Each bucket is a saved Google News query - see the "
    "Source detail panel for the full list."
)
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
        color_continuous_scale=[[0, "#84a17d"], [0.5, "#d4af37"], [1, "#e85a5a"]],
    )
    apply_light(fig, height=320, coloraxis_showscale=False,
                margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)


# Theme volume over time
if gnews:
    st.markdown("### Theme volume over time")
    st.caption(
        "Same buckets, but plotted hourly. A vertical climb in one band "
        "usually means a story is breaking in real time."
    )
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


# Term frequency
st.markdown("### Single-word frequency")
st.caption(
    "Most-frequent individual words across every signal title in the "
    "current filter - news, weather alerts, GDELT articles, port alerts, "
    "EONET events, all of it. Useful for catching surprise terms."
)

tokens: Counter[str] = Counter()
for s in signals:
    for w in _tokens(s.get("title", "")):
        tokens[w] += 1

if not tokens:
    st.info("No tokens to score with the current filters.")
else:
    tf = pd.DataFrame(tokens.most_common(40), columns=["term", "count"])
    fig_tf = px.bar(
        tf, x="count", y="term", orientation="h",
        color="count",
        color_continuous_scale=[[0, "#3a3530"], [1, "#e7c764"]],
    )
    apply_light(fig_tf, height=620, coloraxis_showscale=False,
                margin=dict(l=10, r=10, t=10, b=10),
                yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig_tf, use_container_width=True)


# Outlet breakdown
if outlets:
    st.markdown("### Top outlets")
    st.caption(
        "Which publications produced the most matching articles in your "
        "filter window."
    )
    odf = (
        pd.DataFrame(outlets.most_common(20), columns=["outlet", "articles"])
          .sort_values("articles", ascending=True)
    )
    fig_o = px.bar(odf, x="articles", y="outlet", orientation="h",
                   color_discrete_sequence=["#d4af37"])
    apply_light(fig_o, height=420, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_o, use_container_width=True)


# =========================================================================== #
# SECTION 5 - Live news feed (kept from previous design - user explicitly liked it)
# =========================================================================== #
st.markdown("### Live news feed")
st.caption(
    "Latest individual articles. Click any headline to open the source in "
    "a new tab."
)
feed_tabs = st.tabs(["Google News", "Reddit"])


def _humanize(ts: str) -> str:
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
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


# --------------------------------------------------------------------------- #
# API health footer
# --------------------------------------------------------------------------- #
render_api_status()
