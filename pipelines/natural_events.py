"""
Natural events pipeline - NASA EONET v3.

Free, no key. Open events across wildfires, volcanoes, severe storms, dust/haze,
floods, drought, landslides, sea/lake ice, tempExtremes, manmade incidents.

We pull all open events from the last N days, take the latest geometry of each,
and emit a Signal with category mapped from EONET's category id.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .base import Signal, get_session
import config

EONET_URL = "https://eonet.gsfc.nasa.gov/api/v3/events"

# Map EONET category id -> (our category, default severity)
_EONET_MAP = {
    "wildfires":       ("natural",  0.55),
    "volcanoes":       ("volcanic", 0.80),
    "severeStorms":    ("natural",  0.70),
    "drought":         ("natural",  0.45),
    "dustHaze":        ("natural",  0.40),
    "snow":            ("natural",  0.35),
    "floods":          ("natural",  0.70),
    "earthquakes":     ("seismic",  0.60),
    "landslides":      ("natural",  0.60),
    "tempExtremes":    ("natural",  0.40),
    "seaLakeIce":      ("natural",  0.30),
    "manmade":         ("natural",  0.50),
    "waterColor":      ("natural",  0.20),
}


def fetch(days: int = 14, limit: int = 200) -> list[Signal]:
    """Pull open EONET events. Most recent geometry wins for plotting."""
    session = get_session(expire_after=config.CACHE_TTL.get("usgs_quakes", 600))
    params = {"status": "open", "days": days, "limit": limit}

    try:
        r = session.get(EONET_URL, params=params, timeout=25)
        r.raise_for_status()
        data = r.json() or {}
    except Exception as e:
        print(f"[eonet] fetch failed: {e}")
        return []

    signals: list[Signal] = []
    for ev in data.get("events", []) or []:
        cats = ev.get("categories") or []
        if not cats:
            continue
        cat_id = (cats[0].get("id") or "").strip()
        category, default_sev = _EONET_MAP.get(
            cat_id, ("natural", 0.4)
        )

        geoms = ev.get("geometry") or []
        if not geoms:
            continue
        latest = geoms[-1]
        coords = latest.get("coordinates") or [None, None]
        # EONET coords are [lon, lat] for points; polygons return nested lists.
        lon, lat = None, None
        if isinstance(coords[0], (int, float)) and isinstance(coords[1], (int, float)):
            lon, lat = coords[0], coords[1]
        else:
            # For a Polygon, grab first ring's first point.
            try:
                lon, lat = coords[0][0]
            except Exception:
                pass

        sources = ev.get("sources") or []
        url = sources[0].get("url") if sources else None

        ts = latest.get("date") or ev.get("geometry", [{}])[0].get("date")
        try:
            # EONET uses ISO 8601; some without TZ suffix.
            ts_iso = (
                datetime.fromisoformat(ts.replace("Z", "+00:00")).isoformat()
                if ts else datetime.now(timezone.utc).isoformat()
            )
        except Exception:
            ts_iso = datetime.now(timezone.utc).isoformat()

        # Magnitude bump: some events ship a magnitudeValue (wildfire acres, etc.).
        mag_v = latest.get("magnitudeValue")
        if isinstance(mag_v, (int, float)) and mag_v > 0:
            severity = min(1.0, default_sev + min(0.2, mag_v / 100000.0))
        else:
            severity = default_sev

        signals.append(
            Signal(
                source="eonet",
                category=category,
                title=f"{cats[0].get('title', cat_id) or cat_id}: {ev.get('title', '')[:200]}",
                severity=float(severity),
                lat=lat,
                lon=lon,
                timestamp_utc=ts_iso,
                url=url,
                payload={
                    "eonet_id": ev.get("id"),
                    "eonet_category": cat_id,
                    "magnitudeValue": mag_v,
                    "magnitudeUnit": latest.get("magnitudeUnit"),
                    "sources": [s.get("id") for s in sources],
                },
            )
        )

    return signals
