"""
Global trends — what the world is searching and reading right now.

Two free, no-key sources:

    1. Google Trends daily "Trending now" RSS, per country. Each entry is
       a search query that surged in the last ~24h, with an approximate
       traffic estimate ("200+", "2K+", "1M+") and one linked news
       article. Endpoint:
            https://trends.google.com/trending/rss?geo=<ISO-3166-1 alpha-2>

    2. Wikipedia pageviews "top" — the most-viewed articles on the
       English Wikipedia for a given day. Endpoint:
            https://wikimedia.org/api/rest_v1/metrics/pageviews/top/
              en.wikipedia/all-access/YYYY/MM/DD

These don't emit Signal records — they're surfaced directly on the
Trends & News page as a "world pulse" panel alongside the existing
supply-chain news feed.
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timedelta, timezone

import feedparser

from .base import get_session
import config


# --------------------------------------------------------------------------- #
# Google Trends — daily trending searches per country
# --------------------------------------------------------------------------- #
GOOGLE_TRENDS_RSS = "https://trends.google.com/trending/rss?geo={geo}"

# (ISO-3166-1 alpha-2, display label). Add more by extending this list.
TRENDS_GEOS: list[tuple[str, str]] = [
    ("US", "United States"),
    ("GB", "United Kingdom"),
    ("IN", "India"),
    ("DE", "Germany"),
    ("BR", "Brazil"),
    ("JP", "Japan"),
    ("CA", "Canada"),
    ("AU", "Australia"),
]


def _parse_traffic(traffic: str) -> int | None:
    """Convert '500+' -> 500, '2K+' -> 2000, '1M+' -> 1_000_000."""
    if not traffic:
        return None
    s = traffic.replace(",", "").replace("+", "").strip().upper()
    try:
        if s.endswith("K"):
            return int(float(s[:-1]) * 1_000)
        if s.endswith("M"):
            return int(float(s[:-1]) * 1_000_000)
        return int(float(s))
    except (ValueError, TypeError):
        return None


def fetch_google_trends(geo: str = "US", limit: int = 25) -> list[dict]:
    """Return [{query, traffic_str, traffic_int, news_title, news_url, image, ...}]."""
    session = get_session(expire_after=config.CACHE_TTL.get("news", 15 * 60))
    url = GOOGLE_TRENDS_RSS.format(geo=geo)
    try:
        r = session.get(
            url, timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36",
            },
        )
        r.raise_for_status()
        feed = feedparser.parse(r.text)
    except Exception as e:
        print(f"[trends-{geo}] fetch failed: {e}")
        return []

    rows: list[dict] = []
    for entry in (feed.entries or [])[:limit]:
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        traffic_str = str(entry.get("ht_approx_traffic", "") or "").strip()
        rows.append({
            "geo":         geo,
            "query":       title,
            "traffic_str": traffic_str,
            "traffic_int": _parse_traffic(traffic_str),
            "news_title":  (entry.get("ht_news_item_title") or "")[:240],
            "news_url":    entry.get("ht_news_item_url") or entry.get("link") or "",
            "image":       entry.get("ht_picture") or "",
            "image_credit": entry.get("ht_picture_source") or "",
            "published":   entry.get("published") or "",
        })
    return rows


def fetch_all_trends(geos: list[str] | None = None) -> dict[str, list[dict]]:
    """Return {country_label: [trend rows]} for each requested geo."""
    if geos is None:
        geos = [code for code, _ in TRENDS_GEOS]
    label_for = dict(TRENDS_GEOS)
    out: dict[str, list[dict]] = {}
    for code in geos:
        rows = fetch_google_trends(code)
        if rows:
            out[label_for.get(code, code)] = rows
    return out


# --------------------------------------------------------------------------- #
# Wikipedia — most-viewed English-Wikipedia articles
# --------------------------------------------------------------------------- #
WIKI_TOP_URL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/"
    "all-access/{y}/{m:02d}/{d:02d}"
)

# Skip these — they're not real "what the world is reading" entries.
_WIKI_BLOCKLIST_EXACT = {"Main_Page"}
_WIKI_BLOCKLIST_PREFIX = (
    "Special:", "Wikipedia:", "File:", "Portal:", "Help:", "Category:",
)


def fetch_wikipedia_top(limit: int = 25, lag_days: int = 1) -> list[dict]:
    """Most-viewed Wikipedia articles for `lag_days` ago (default: yesterday).

    Wikipedia's pageviews API publishes the prior day's totals; we lag by 1
    by default so the call always succeeds. If that 404s, retry with lag=2.
    """
    session = get_session(expire_after=12 * 60 * 60)
    for lag in (lag_days, lag_days + 1, lag_days + 2):
        d = datetime.now(timezone.utc) - timedelta(days=lag)
        url = WIKI_TOP_URL.format(y=d.year, m=d.month, d=d.day)
        try:
            r = session.get(
                url, timeout=15,
                headers={"User-Agent": config.NOAA_USER_AGENT},
            )
            if r.status_code == 404:
                continue
            r.raise_for_status()
            data = r.json() or {}
            break
        except Exception as e:
            print(f"[wikipedia] fetch failed for {d.date()}: {e}")
            data = {}
    else:
        return []

    items = (data.get("items") or [{}])[0].get("articles") or []
    rows: list[dict] = []
    for item in items:
        slug = item.get("article", "")
        if not slug or slug in _WIKI_BLOCKLIST_EXACT:
            continue
        if any(slug.startswith(p) for p in _WIKI_BLOCKLIST_PREFIX):
            continue
        title = slug.replace("_", " ")
        rows.append({
            "rank":  item.get("rank"),
            "title": title,
            "views": int(item.get("views", 0) or 0),
            "url":   f"https://en.wikipedia.org/wiki/{urllib.parse.quote(slug)}",
        })
        if len(rows) >= limit:
            break
    return rows
