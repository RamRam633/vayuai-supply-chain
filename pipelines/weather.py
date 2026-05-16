"""
Weather pipeline.

Sources:
  - NOAA NWS alerts (free, US-focused but covers PR/AK/HI and shipping zones)
  - Open-Meteo (free, global, no key) - used to check storm conditions
    near each MAJOR_PORT.

For the MVP we treat 'active NOAA alert' and 'high wind/precip near port'
as the two weather signals. Tropical storm advisories from JTWC could be
layered in later (no clean free API; would require scraping).
"""

from __future__ import annotations

from datetime import datetime, timezone

from .base import Signal, get_session
import config

NOAA_ALERTS_URL = "https://api.weather.gov/alerts/active"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_noaa_alerts() -> list[Signal]:
    """Pull active US-area NWS alerts. Severity from event severity tag."""
    session = get_session(expire_after=config.CACHE_TTL["noaa_alerts"])
    signals: list[Signal] = []

    headers = {"User-Agent": config.NOAA_USER_AGENT, "Accept": "application/geo+json"}
    try:
        r = session.get(NOAA_ALERTS_URL, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json() or {}
    except Exception as e:
        print(f"[noaa] fetch failed: {e}")
        return signals

    severity_map = {
        "Extreme": 1.0,
        "Severe": 0.75,
        "Moderate": 0.4,
        "Minor": 0.2,
        "Unknown": 0.1,
    }

    for feat in data.get("features", []):
        props = feat.get("properties", {}) or {}
        event = props.get("event", "Alert")
        sev_str = props.get("severity", "Unknown")
        severity = severity_map.get(sev_str, 0.1)

        # NWS alerts come polygon-based; we sample the first coordinate
        # for an approximate map pin.
        geom = feat.get("geometry") or {}
        lat, lon = None, None
        if geom.get("type") == "Polygon":
            try:
                first = geom["coordinates"][0][0]
                lon, lat = first[0], first[1]
            except Exception:
                pass

        signals.append(
            Signal(
                source="noaa",
                category="weather",
                title=f"{event} - {props.get('areaDesc', '')[:120]}",
                severity=severity,
                lat=lat,
                lon=lon,
                timestamp_utc=props.get("sent") or datetime.now(timezone.utc).isoformat(),
                url=props.get("@id"),
                payload={"event": event, "severity_tag": sev_str},
            )
        )

    return signals


def fetch_port_weather() -> list[Signal]:
    """For each major port, query Open-Meteo for current conditions.

    Emits a Signal only when wind/precip exceeds a disruption threshold.
    Cheap call: ~15 ports * 1 req = 15 requests, all cached for 1h.
    """
    session = get_session(expire_after=config.CACHE_TTL["open_meteo"])
    signals: list[Signal] = []

    for port in config.MAJOR_PORTS:
        params = {
            "latitude": port["lat"],
            "longitude": port["lon"],
            "current": "wind_speed_10m,wind_gusts_10m,precipitation,weather_code",
            "wind_speed_unit": "kmh",
        }
        try:
            r = session.get(OPEN_METEO_URL, params=params, timeout=15)
            r.raise_for_status()
            data = r.json() or {}
        except Exception as e:
            print(f"[open-meteo] {port['name']} fetch failed: {e}")
            continue

        cur = (data or {}).get("current") or {}
        wind = float(cur.get("wind_gusts_10m") or 0.0)
        precip = float(cur.get("precipitation") or 0.0)

        # Severity rule: gusts >60 kph or heavy rain -> port operations risk
        if wind < 60 and precip < 10:
            continue

        sev = max(0.0, min(1.0, (wind - 60) / 60 + precip / 50))
        signals.append(
            Signal(
                source="open-meteo",
                category="weather",
                title=f"Adverse weather at {port['name']}: gusts {wind:.0f} kph, precip {precip:.1f} mm/h",
                severity=sev,
                lat=port["lat"],
                lon=port["lon"],
                region=None,  # filled by analytics layer
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                payload={"port": port["name"], "wind_gusts_kmh": wind, "precip_mm_h": precip},
            )
        )

    return signals


def fetch() -> list[Signal]:
    return fetch_noaa_alerts() + fetch_port_weather()
