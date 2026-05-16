"""
News & social-trend pipeline.

Sources (all free, no key):
  * Google News RSS - article volume per supply-chain query
  * Reddit RSS      - community discussion on r/supplychain, r/shipping,
                      r/Logistics, r/geopolitics

We emit one Signal per article. Severity = base severity of the query type
(higher for active-crisis terms like "Houthi" or "Red Sea attack") plus a
mild recency boost so articles from the last few hours float to the top.

Cached for 15 minutes per feed via the shared requests-cache session.
"""

from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timezone
from html import unescape

import feedparser

from .base import Signal, get_session
import config

GOOGLE_NEWS_TEMPLATE = (
    "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
)
REDDIT_RSS_TEMPLATE = "https://www.reddit.com/r/{sub}/new/.rss"

# (query, base severity, theme tag). Themes group queries into buckets so the
# Trends/News page can chart "theme volume over time" cleanly.
QUERIES: list[tuple[str, float, str]] = [
    ("supply chain disruption",  0.55, "logistics"),
    ("port congestion",          0.55, "logistics"),
    ("shipping crisis",          0.65, "logistics"),
    ("container shortage",       0.50, "logistics"),
    ("port strike",              0.65, "labor"),
    ("dockworker strike",        0.65, "labor"),
    ("trade war",                0.55, "geopolitics"),
    ("tariff",                   0.45, "geopolitics"),
    ("sanctions",                0.55, "geopolitics"),
    ("export ban",               0.55, "geopolitics"),
    ("Suez Canal",               0.65, "chokepoint"),
    ("Panama Canal",             0.60, "chokepoint"),
    ("Red Sea shipping",         0.70, "chokepoint"),
    ("Houthi attack",            0.75, "chokepoint"),
    ("Strait of Hormuz",         0.70, "chokepoint"),
    ("Taiwan Strait tension",    0.65, "chokepoint"),
    ("semiconductor shortage",   0.55, "sector"),
    ("automotive plant closure", 0.50, "sector"),
    ("oil price",                0.40, "markets"),
    ("OPEC",                     0.45, "markets"),
    ("wheat prices",             0.45, "markets"),
    ("commodity prices",         0.40, "markets"),
]

SUBREDDITS = [
    "supplychain",
    "shipping",
    "Logistics",
    "geopolitics",
    "energy",
]

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return _TAG_RE.sub("", unescape(s or "")).strip()


def _entry_timestamp(entry) -> datetime:
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                continue
    return datetime.now(timezone.utc)


def _recency_boost(ts: datetime) -> float:
    """Up to +0.1 severity for articles in the last 6 hours, decaying to 0 at 48h."""
    age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
    if age_h <= 0:
        return 0.10
    if age_h >= 48:
        return 0.0
    return max(0.0, 0.10 * (1.0 - age_h / 48.0))


def _fetch_feed(url: str):
    session = get_session(expire_after=config.CACHE_TTL.get("news", 15 * 60))
    try:
        r = session.get(
            url, timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            },
        )
        r.raise_for_status()
        return feedparser.parse(r.text)
    except Exception as e:
        print(f"[news] fetch failed {url[:80]}: {e}")
        return None


# --------------------------------------------------------------------------- #
# Google News
# --------------------------------------------------------------------------- #
def fetch_google_news(per_query: int = 6) -> list[Signal]:
    sigs: list[Signal] = []
    for query, base_sev, theme in QUERIES:
        url = GOOGLE_NEWS_TEMPLATE.format(q=urllib.parse.quote(query))
        feed = _fetch_feed(url)
        if not feed or not getattr(feed, "entries", None):
            continue
        for entry in feed.entries[:per_query]:
            ts = _entry_timestamp(entry)
            sev = min(1.0, base_sev + _recency_boost(ts))

            outlet = ""
            src_node = getattr(entry, "source", None)
            if src_node is not None:
                outlet = getattr(src_node, "title", "") or str(src_node)

            title = _strip_html(entry.title)
            sigs.append(
                Signal(
                    source="google-news",
                    category="news",
                    title=f"{outlet}: {title}"[:280] if outlet else title[:280],
                    severity=sev,
                    timestamp_utc=ts.isoformat(),
                    url=getattr(entry, "link", None),
                    payload={
                        "query":   query,
                        "theme":   theme,
                        "outlet":  outlet,
                        "summary": _strip_html(getattr(entry, "summary", ""))[:500],
                    },
                )
            )
    return sigs


# --------------------------------------------------------------------------- #
# Reddit RSS
# --------------------------------------------------------------------------- #
def fetch_reddit(per_sub: int = 8) -> list[Signal]:
    sigs: list[Signal] = []
    for sub in SUBREDDITS:
        url = REDDIT_RSS_TEMPLATE.format(sub=sub)
        feed = _fetch_feed(url)
        if not feed or not getattr(feed, "entries", None):
            continue
        for entry in feed.entries[:per_sub]:
            ts = _entry_timestamp(entry)
            title = _strip_html(entry.title)
            sigs.append(
                Signal(
                    source="reddit",
                    category="news",
                    title=f"r/{sub}: {title}"[:280],
                    severity=0.30,            # community chatter; low default sev
                    timestamp_utc=ts.isoformat(),
                    url=getattr(entry, "link", None),
                    payload={
                        "subreddit": sub,
                        "theme":     "social",
                        "summary":   _strip_html(getattr(entry, "summary", ""))[:400],
                    },
                )
            )
    return sigs


def fetch() -> list[Signal]:
    """Combined news pipeline entrypoint."""
    return fetch_google_news() + fetch_reddit()
