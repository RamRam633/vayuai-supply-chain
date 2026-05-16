"""
Active tropical cyclones — National Hurricane Center (NOAA NHC).

Free, no key. Covers Atlantic + Eastern Pacific basins. Western Pacific
typhoons need JTWC scraping (no clean free API) — left for later.

NHC publishes a JSON of active storms with classification, intensity, and
current position. We emit one Signal per active storm, severity scaled by
wind speed (Saffir-Simpson tier).
"""

from __future__ import annotations

from datetime import datetime, timezone

from .base import Signal, get_session
import config

NHC_CURRENT_STORMS = "https://www.nhc.noaa.gov/CurrentStorms.json"


def _wind_severity(wind_kt: float) -> float:
    """Map sustained wind (knots) to 0..1 severity along the Saffir-Simpson scale."""
    if wind_kt <= 0:
        return 0.0
    # 34kt = tropical storm, 64kt = cat1, 96kt = cat3 (major), 137kt = cat5.
    if wind_kt < 34:
        return 0.30
    if wind_kt < 64:
        return 0.55
    if wind_kt < 83:
        return 0.70   # cat 1
    if wind_kt < 96:
        return 0.80   # cat 2
    if wind_kt < 113:
        return 0.88   # cat 3
    if wind_kt < 137:
        return 0.94   # cat 4
    return 1.00       # cat 5


def fetch() -> list[Signal]:
    """Return one Signal per active tropical storm."""
    session = get_session(expire_after=config.CACHE_TTL.get("noaa_alerts", 600))
    headers = {"User-Agent": config.NOAA_USER_AGENT}

    try:
        r = session.get(NHC_CURRENT_STORMS, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json() or {}
    except Exception as e:
        print(f"[nhc] fetch failed: {e}")
        return []

    signals: list[Signal] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for storm in data.get("activeStorms", []) or []:
        try:
            wind_kt = float(storm.get("intensity") or 0.0)
        except (TypeError, ValueError):
            wind_kt = 0.0

        lat = storm.get("latitudeNumeric")
        lon = storm.get("longitudeNumeric")
        try:
            lat = float(lat) if lat is not None else None
            lon = float(lon) if lon is not None else None
        except (TypeError, ValueError):
            lat, lon = None, None

        classification = storm.get("classification") or ""
        name = storm.get("name") or storm.get("id") or "Unnamed storm"
        title = (
            f"{classification} {name}: {int(wind_kt)} kt sustained winds"
            if wind_kt > 0
            else f"{classification} {name}"
        )

        signals.append(
            Signal(
                source="nhc",
                category="tropical",
                title=title,
                severity=_wind_severity(wind_kt),
                lat=lat,
                lon=lon,
                timestamp_utc=storm.get("lastUpdate") or now_iso,
                url=storm.get("publicAdvisory", {}).get("url")
                    if isinstance(storm.get("publicAdvisory"), dict)
                    else None,
                payload={
                    "id":             storm.get("id"),
                    "name":           name,
                    "classification": classification,
                    "wind_kt":        wind_kt,
                    "pressure_mb":    storm.get("pressure"),
                    "movement":       storm.get("movement"),
                    "basin":          storm.get("binNumber"),
                },
            )
        )

    return signals
