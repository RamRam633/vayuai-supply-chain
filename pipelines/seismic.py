"""
Seismic activity — USGS GeoJSON feed.
Free, no key, real-time. We pull M4.5+ in the last 7 days.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .base import Signal, get_session
import config

USGS_FEED = (
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"
)


def fetch() -> list[Signal]:
    """Return earthquake Signals with severity scaled to magnitude."""
    session = get_session(expire_after=config.CACHE_TTL["usgs_quakes"])
    signals: list[Signal] = []

    try:
        r = session.get(USGS_FEED, timeout=20)
        r.raise_for_status()
        data = r.json() or {}
    except Exception as e:
        print(f"[usgs] fetch failed: {e}")
        return signals

    for feat in data.get("features", []):
        props = feat.get("properties", {}) or {}
        geom = feat.get("geometry", {}) or {}
        coords = geom.get("coordinates") or [None, None, None]
        lon, lat = coords[0], coords[1]

        mag = float(props.get("mag") or 0.0)
        # Severity: M4.5 -> 0.1, M9 -> 1.0 (rough linear map above threshold).
        severity = max(0.0, min(1.0, (mag - 4.5) / 4.5))

        ts_ms = props.get("time")
        try:
            ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
        except Exception:
            ts = datetime.now(timezone.utc).isoformat()

        signals.append(
            Signal(
                source="usgs",
                category="seismic",
                title=f"M{mag:.1f} — {props.get('place', 'Unknown location')}",
                severity=severity,
                lat=lat,
                lon=lon,
                timestamp_utc=ts,
                url=props.get("url"),
                payload={"magnitude": mag, "depth_km": coords[2] if len(coords) > 2 else None},
            )
        )

    return signals
