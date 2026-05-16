"""
Live flights pipeline with multi-source fallback.

Primary source: OpenSky Network /states/all. Anonymous access works from
most IPs but is throttled aggressively and (as we observed in 2026)
occasionally returns nothing from shared cloud IPs. Two ways to lift
the throttle:

    1. Set a User-Agent identifying the deploy (we always do).
    2. Set OPENSKY_USERNAME + OPENSKY_PASSWORD env vars. OpenSky honors
       HTTP Basic Auth and bumps the quota to ~4000 credits/day per
       authenticated account.

Fallback: ADSB.lol /v2/lat/<lat>/lon/<lon>/dist/<nm>. Free, no auth,
geo-bounded. When OpenSky is empty we issue 250nm-radius queries
around the world's top cargo airports and merge by ICAO hex. That
gives us coverage where it matters most (cargo hubs) even if the
global feed is dark.

Snapshot is persisted to data/flights_snapshot.sqlite so the Streamlit
Flights and Logistics pages can read it without re-hitting any API.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .base import Signal, get_session
import config


OPENSKY_URL = "https://opensky-network.org/api/states/all"
ADSB_LOL_URL = "https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{nm}"

# Centers we query on the ADSB.lol fallback. We pick the world's biggest
# cargo airports so the fallback covers the supply-chain-relevant air space.
# A 250nm radius around each ~= 460km coverage, which overlaps neatly into
# every major hub region without spamming the endpoint.
_ADSB_FALLBACK_RADIUS_NM = 250
_ADSB_FALLBACK_CENTERS = [
    # (lat, lon) of major cargo hubs - matches config.MAJOR_AIRPORTS order
    ( 35.04,  -89.98),   # MEM - FedEx Superhub
    ( 38.17,  -85.74),   # SDF - UPS Worldport
    ( 61.17, -150.00),   # ANC - Anchorage cargo
    ( 33.94, -118.41),   # LAX
    ( 25.79,  -80.29),   # MIA
    ( 41.98,  -87.91),   # ORD - Chicago O'Hare
    ( 50.03,    8.57),   # FRA - Frankfurt
    ( 49.01,    2.55),   # CDG - Paris
    ( 52.31,    4.76),   # AMS - Amsterdam
    ( 51.47,   -0.45),   # LHR - London
    ( 50.64,    5.44),   # LGG - Liege (DHL)
    ( 25.27,   55.37),   # DXB - Dubai
    ( 25.27,   51.61),   # DOH - Doha
    ( 22.31,  113.92),   # HKG - Hong Kong
    ( 31.14,  121.81),   # PVG - Shanghai Pudong
    ( 37.46,  126.44),   # ICN - Incheon
    ( 25.08,  121.23),   # TPE - Taipei
    ( 35.77,  140.39),   # NRT - Tokyo Narita
    (  1.36,  103.99),   # SIN - Singapore
    ( 19.09,   72.87),   # BOM - Mumbai
    (-23.43,  -46.48),   # GRU - Sao Paulo
    (-33.94,  151.18),   # SYD - Sydney
]

FLIGHT_SNAPSHOT_DB = Path(config.DATA_DIR) / "flights_snapshot.sqlite"

# OpenSky returns positional vectors as a list; these are the column indices.
# Docs: https://openskynetwork.github.io/opensky-api/rest.html
_IDX = {
    "icao24":         0,
    "callsign":       1,
    "origin_country": 2,
    "time_position":  3,
    "last_contact":   4,
    "lon":            5,
    "lat":            6,
    "baro_alt":       7,
    "on_ground":      8,
    "velocity":       9,
    "true_track":    10,
    "vertical_rate": 11,
    "geo_alt":       13,
    "squawk":        14,
}

# Density thresholds - calibrated against a quiet evening at major hubs.
AIRPORT_RADIUS_KM = 80
AIRPORT_CONGESTION_HIGH = 30   # signal level
AIRPORT_CONGESTION_MAX = 80    # severity = 1.0 at/above this

# Unit conversions for normalizing ADSB.lol rows into the same schema as OpenSky.
_FT_TO_M     = 0.3048
_KT_TO_MS    = 0.514444
_FPM_TO_MS   = 0.00508


# --------------------------------------------------------------------------- #
# Snapshot DB - Streamlit pages read this.
# --------------------------------------------------------------------------- #
def _ensure_db() -> None:
    FLIGHT_SNAPSHOT_DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(FLIGHT_SNAPSHOT_DB)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS flights (
            icao24         TEXT PRIMARY KEY,
            callsign       TEXT,
            origin_country TEXT,
            lat            REAL,
            lon            REAL,
            baro_alt_m     REAL,
            geo_alt_m      REAL,
            velocity_ms    REAL,
            true_track     REAL,
            vertical_rate  REAL,
            on_ground      INTEGER,
            ts_utc         TEXT
        )
        """
    )
    con.commit()
    con.close()


def write_snapshot(rows: list[dict]) -> int:
    _ensure_db()
    con = sqlite3.connect(FLIGHT_SNAPSHOT_DB)
    cur = con.cursor()
    cur.execute("DELETE FROM flights")
    for r in rows:
        cur.execute(
            """
            INSERT OR REPLACE INTO flights
              (icao24, callsign, origin_country, lat, lon, baro_alt_m, geo_alt_m,
               velocity_ms, true_track, vertical_rate, on_ground, ts_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r["icao24"], r["callsign"], r["origin_country"],
                r["lat"], r["lon"], r["baro_alt_m"], r["geo_alt_m"],
                r["velocity_ms"], r["true_track"], r["vertical_rate"],
                int(bool(r["on_ground"])), r["ts_utc"],
            ),
        )
    con.commit()
    n = cur.execute("SELECT COUNT(*) FROM flights").fetchone()[0]
    con.close()
    return n


def read_snapshot() -> list[dict]:
    if not FLIGHT_SNAPSHOT_DB.exists():
        return []
    con = sqlite3.connect(FLIGHT_SNAPSHOT_DB)
    cur = con.cursor()
    cur.execute(
        "SELECT icao24, callsign, origin_country, lat, lon, baro_alt_m, "
        "geo_alt_m, velocity_ms, true_track, vertical_rate, on_ground, ts_utc "
        "FROM flights"
    )
    cols = [
        "icao24", "callsign", "origin_country", "lat", "lon", "baro_alt_m",
        "geo_alt_m", "velocity_ms", "true_track", "vertical_rate",
        "on_ground", "ts_utc",
    ]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    con.close()
    return rows


def snapshot_source() -> str | None:
    """Which source produced the last snapshot ('opensky', 'adsb.lol', or None)."""
    marker = Path(config.DATA_DIR) / "flights_source.marker"
    if not marker.exists():
        return None
    try:
        return marker.read_text().strip() or None
    except Exception:
        return None


def _write_source(name: str) -> None:
    try:
        (Path(config.DATA_DIR) / "flights_source.marker").write_text(name)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Geo helpers
# --------------------------------------------------------------------------- #
def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _user_agent() -> str:
    """Identifying UA per OpenSky's etiquette. Embeds the NOAA_USER_AGENT contact."""
    contact = getattr(config, "NOAA_USER_AGENT", "VayuAI/0.1")
    return f"VayuAI-SupplyChainPulse/0.2 ({contact})"


# --------------------------------------------------------------------------- #
# Source #1 - OpenSky /states/all (global)
# --------------------------------------------------------------------------- #
def _opensky_auth() -> tuple[str, str] | None:
    u = getattr(config, "OPENSKY_USERNAME", "")
    p = getattr(config, "OPENSKY_PASSWORD", "")
    return (u, p) if (u and p) else None


def _fetch_opensky() -> list[dict]:
    """Pull the global /states/all snapshot from OpenSky."""
    session = get_session(expire_after=60)
    auth = _opensky_auth()
    headers = {"User-Agent": _user_agent()}
    try:
        r = session.get(OPENSKY_URL, timeout=30, headers=headers, auth=auth)
        if r.status_code != 200:
            print(f"[opensky] status {r.status_code}; auth={'on' if auth else 'off'}")
            return []
        data = r.json() or {}
    except Exception as e:
        print(f"[opensky] fetch failed: {e}")
        return []

    now_iso = datetime.now(timezone.utc).isoformat()
    parsed: list[dict] = []
    for s in data.get("states") or []:
        try:
            lat = s[_IDX["lat"]]
            lon = s[_IDX["lon"]]
            if lat is None or lon is None:
                continue
            parsed.append({
                "icao24":         (s[_IDX["icao24"]] or "").strip(),
                "callsign":       (s[_IDX["callsign"]] or "").strip(),
                "origin_country": s[_IDX["origin_country"]] or "",
                "lat":            float(lat),
                "lon":            float(lon),
                "baro_alt_m":     float(s[_IDX["baro_alt"]] or 0.0),
                "geo_alt_m":      float(s[_IDX["geo_alt"]] or 0.0),
                "velocity_ms":    float(s[_IDX["velocity"]] or 0.0),
                "true_track":     float(s[_IDX["true_track"]] or 0.0),
                "vertical_rate":  float(s[_IDX["vertical_rate"]] or 0.0),
                "on_ground":      bool(s[_IDX["on_ground"]]),
                "ts_utc":         now_iso,
            })
        except (IndexError, TypeError, ValueError):
            continue
    return parsed


# --------------------------------------------------------------------------- #
# Source #2 - ADSB.lol geo-bounded queries around cargo hubs
# --------------------------------------------------------------------------- #
def _fetch_adsb_lol_region(lat: float, lon: float, nm: int = _ADSB_FALLBACK_RADIUS_NM) -> list[dict]:
    """ADSB.lol returns every aircraft within nm of (lat, lon). No auth."""
    session = get_session(expire_after=60)
    url = ADSB_LOL_URL.format(lat=lat, lon=lon, nm=nm)
    try:
        r = session.get(url, timeout=15, headers={"User-Agent": _user_agent()})
        if r.status_code != 200:
            return []
        data = r.json() or {}
    except Exception as e:
        print(f"[adsb.lol] ({lat:.1f},{lon:.1f}) failed: {e}")
        return []

    now_iso = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []
    for ac in (data.get("ac") or []):
        try:
            la = ac.get("lat")
            lo = ac.get("lon")
            if la is None or lo is None:
                continue
            # alt_baro can be int feet, the string "ground", or null when no Mode S.
            alt_baro = ac.get("alt_baro")
            on_ground = False
            baro_alt_m = 0.0
            if isinstance(alt_baro, (int, float)):
                baro_alt_m = float(alt_baro) * _FT_TO_M
            elif alt_baro == "ground":
                on_ground = True
            alt_geom = ac.get("alt_geom")
            geo_alt_m = (
                float(alt_geom) * _FT_TO_M
                if isinstance(alt_geom, (int, float)) else 0.0
            )
            gs = ac.get("gs") or 0
            velocity_ms = float(gs) * _KT_TO_MS if gs is not None else 0.0
            baro_rate = ac.get("baro_rate") or 0
            vertical_rate = (
                float(baro_rate) * _FPM_TO_MS if baro_rate is not None else 0.0
            )
            rows.append({
                "icao24":         (ac.get("hex") or "").strip().lower(),
                "callsign":       (ac.get("flight") or "").strip(),
                "origin_country": "",  # ADSB.lol doesn't report this directly
                "lat":            float(la),
                "lon":            float(lo),
                "baro_alt_m":     baro_alt_m,
                "geo_alt_m":      geo_alt_m,
                "velocity_ms":    velocity_ms,
                "true_track":     float(ac.get("track") or 0.0),
                "vertical_rate":  vertical_rate,
                "on_ground":      on_ground,
                "ts_utc":         now_iso,
            })
        except (TypeError, ValueError):
            continue
    return rows


def _fetch_adsb_lol_fallback() -> list[dict]:
    """Query ADSB.lol around each cargo hub and merge by icao24."""
    merged: dict[str, dict] = {}
    for lat, lon in _ADSB_FALLBACK_CENTERS:
        rows = _fetch_adsb_lol_region(lat, lon)
        for row in rows:
            hx = row["icao24"]
            if not hx:
                continue
            merged.setdefault(hx, row)   # first-seen wins; centers overlap heavily
    return list(merged.values())


# --------------------------------------------------------------------------- #
# Public fetcher with fallback chain
# --------------------------------------------------------------------------- #
def fetch_states() -> list[dict]:
    """Try OpenSky first; fall back to ADSB.lol if OpenSky returns nothing."""
    rows = _fetch_opensky()
    if rows:
        _write_source("opensky")
        return rows
    rows = _fetch_adsb_lol_fallback()
    if rows:
        print(f"[flights] OpenSky empty, ADSB.lol fallback returned {len(rows)} aircraft")
        _write_source("adsb.lol")
    return rows


def fetch() -> list[Signal]:
    """Persist snapshot + emit congestion signals near major cargo airports."""
    flights = fetch_states()
    if not flights:
        return []

    try:
        write_snapshot(flights)
    except Exception as e:
        print(f"[flights] snapshot write failed: {e}")

    now_iso = datetime.now(timezone.utc).isoformat()
    airborne = [f for f in flights if not f["on_ground"]]

    signals: list[Signal] = []
    for ap in getattr(config, "MAJOR_AIRPORTS", []):
        nearby = sum(
            1 for f in airborne
            if _haversine(ap["lat"], ap["lon"], f["lat"], f["lon"]) <= AIRPORT_RADIUS_KM
        )
        if nearby < AIRPORT_CONGESTION_HIGH:
            continue
        sev = min(
            1.0,
            (nearby - AIRPORT_CONGESTION_HIGH)
            / max(1, AIRPORT_CONGESTION_MAX - AIRPORT_CONGESTION_HIGH),
        )
        signals.append(
            Signal(
                source="opensky",
                category="flight",
                title=f"Elevated air traffic near {ap['name']}: {nearby} aircraft "
                      f"within {AIRPORT_RADIUS_KM}km",
                severity=float(max(0.2, sev)),  # floor so signals stay visible
                lat=ap["lat"],
                lon=ap["lon"],
                timestamp_utc=now_iso,
                payload={
                    "airport": ap["name"],
                    "iata": ap.get("iata"),
                    "aircraft_nearby": nearby,
                    "radius_km": AIRPORT_RADIUS_KM,
                    "cargo_rank": ap.get("cargo_rank"),
                },
            )
        )

    return signals
