"""
Geopolitical events pipeline.

Sources:
  - GDELT 2.0 DOC API (free, no key) — global event firehose with tone scoring
  - GDACS (free, no key) — UN-affiliated humanitarian disaster alerts
    (replaces ReliefWeb v1, which started returning 410 Gone in 2026)

Both feeds are noisy. We filter to supply-chain-relevant themes and weight by
GDELT's GoldsteinScale (more negative = more disruptive) for severity.
"""

from __future__ import annotations

import time
import urllib.parse
from datetime import datetime, timedelta, timezone

from .base import Signal, get_session, regions_for_point
import config

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# In-process cooldown so a 429 from GDELT doesn't get hammered on every refresh.
_GDELT_BACKOFF_UNTIL = 0.0

# Themes GDELT tags with that are relevant to global supply chains.
SUPPLY_CHAIN_THEMES = [
    "ECON_TRADE_DISPUTE",
    "ECON_TRADE",
    "MARITIME_PIRACY",
    "MARITIME_INCIDENT",
    "BLOCKADE",
    "SANCTIONS",
    "STRIKE",
    "PROTEST",
    "DISASTER_TRANSPORT",
    "TRANSPORT",
    "MANUFACTURING",
    "ENERGY_SUPPLY",
    "INFRASTRUCTURE",
]


def fetch_gdelt(hours_back: int = 24, max_records: int = 75) -> list[Signal]:
    """Pull recent GDELT articles tagged with supply-chain themes.

    Returns Signals with severity derived from negative tone.
    Falls back to empty list on any error — never break the dashboard.
    """
    global _GDELT_BACKOFF_UNTIL
    signals: list[Signal] = []

    if time.time() < _GDELT_BACKOFF_UNTIL:
        return signals

    session = get_session(expire_after=config.CACHE_TTL["gdelt"])

    query = "(" + " OR ".join(f'theme:{t}' for t in SUPPLY_CHAIN_THEMES) + ")"
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": max_records,
        "timespan": f"{hours_back}h",
        "sort": "DateDesc",
    }

    try:
        r = session.get(GDELT_DOC_URL, params=params, timeout=20)
        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", "300"))
            _GDELT_BACKOFF_UNTIL = time.time() + max(60, min(retry_after, 1800))
            print(f"[gdelt] rate-limited; backing off {retry_after}s")
            return signals
        r.raise_for_status()
        data = r.json() or {}
    except Exception as e:
        # Log and return empty — dashboard should degrade, not crash.
        print(f"[gdelt] fetch failed: {e}")
        return signals

    for art in data.get("articles", []):
        tone = float(art.get("tone", 0.0) or 0.0)
        # Map tone (-10..+10) to severity (0..1); only negative tone matters.
        severity = max(0.0, min(1.0, -tone / 10.0))

        signal = Signal(
            source="gdelt",
            category="geopolitical",
            title=art.get("title", "")[:280],
            severity=severity,
            url=art.get("url"),
            timestamp_utc=_parse_gdelt_ts(art.get("seendate")),
            payload={
                "domain": art.get("domain"),
                "language": art.get("language"),
                "tone": tone,
            },
        )
        signals.append(signal)

    return signals


def _parse_gdelt_ts(ts: str | None) -> str:
    """GDELT timestamps are like '20260516T123000Z'. Normalize to ISO."""
    if not ts:
        return datetime.now(timezone.utc).isoformat()
    try:
        return datetime.strptime(ts, "%Y%m%dT%H%M%SZ").replace(
            tzinfo=timezone.utc
        ).isoformat()
    except ValueError:
        return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# GDACS — Global Disaster Alert and Coordination System.
# Replaces ReliefWeb v1/disasters, which started returning 410 Gone in 2026.
# Free, no key, UN-affiliated. Returns active disasters with alert level,
# country, type and coordinates.
# --------------------------------------------------------------------------- #
GDACS_EVENTS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/MAP"

_GDACS_TYPE_LABEL = {
    "EQ": "Earthquake",
    "TC": "Tropical Cyclone",
    "FL": "Flood",
    "DR": "Drought",
    "VO": "Volcano",
    "WF": "Wildfire",
    "TS": "Tsunami",
}

_GDACS_ALERT_SEVERITY = {"red": 0.9, "orange": 0.6, "green": 0.3}


def fetch_gdacs(limit: int = 60) -> list[Signal]:
    """Pull active disasters from GDACS with country + alert-level metadata."""
    session = get_session(expire_after=config.CACHE_TTL.get("gdacs", 1800))
    signals: list[Signal] = []

    try:
        r = session.get(
            GDACS_EVENTS_URL,
            timeout=20,
            headers={"User-Agent": config.NOAA_USER_AGENT},
        )
        r.raise_for_status()
        data = r.json() or {}
    except Exception as e:
        print(f"[gdacs] fetch failed: {e}")
        return signals

    features = data.get("features") or []
    for feat in features[:limit]:
        p = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates")
        # Only Point geometries give us a clean lat/lon. Drought / large-area
        # events come back as MultiPolygon and we just leave them unlocated.
        lon, lat = None, None
        if geom.get("type") == "Point" and isinstance(coords, list) and len(coords) >= 2:
            try:
                lon, lat = float(coords[0]), float(coords[1])
            except (TypeError, ValueError):
                lon, lat = None, None

        evt_type = p.get("eventtype")
        type_name = _GDACS_TYPE_LABEL.get(evt_type, evt_type or "Disaster")
        alert = (p.get("alertlevel") or "").lower()
        severity = _GDACS_ALERT_SEVERITY.get(alert, 0.3)
        country = p.get("country")
        name = p.get("eventname") or p.get("name") or "Disaster"

        url_field = p.get("url")
        if isinstance(url_field, dict):
            link = url_field.get("report") or url_field.get("details")
        else:
            link = url_field

        signals.append(
            Signal(
                source="gdacs",
                category="geopolitical",
                title=f"{type_name}: {name}"[:280],
                severity=severity,
                lat=lat,
                lon=lon,
                region=country,
                timestamp_utc=p.get("fromdate")
                or datetime.now(timezone.utc).isoformat(),
                url=link,
                payload={
                    "alertlevel": p.get("alertlevel"),
                    "alertscore": p.get("alertscore"),
                    "eventtype": evt_type,
                    "country":   country,
                },
            )
        )

    return signals


def fetch() -> list[Signal]:
    """Pipeline entrypoint — combine all geopolitical sources."""
    sigs = fetch_gdelt()
    try:
        sigs += fetch_gdacs()
    except Exception as e:
        print(f"[gdacs] disabled / failed: {e}")
    return sigs
