"""
Live flights pipeline.

Source: OpenSky Network /states/all - global aircraft state-vectors, free,
anonymous (rate-limited to ~once per 10 s). No key required.

We do three things per refresh:
  1. Pull a global snapshot of in-air aircraft.
  2. Persist them to a small SQLite snapshot so the Streamlit Flights page can
     plot live positions without re-hitting the API.
  3. Emit a Signal per major cargo airport whose nearby airborne density is
     anomalously high (proxy for holding patterns / ground-stop downstream).

Falls back to empty list on any failure - never crashes the dashboard.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .base import Signal, get_session
import config

OPENSKY_URL = "https://opensky-network.org/api/states/all"
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


# --------------------------------------------------------------------------- #
# Snapshot DB - Streamlit Flights page reads this.
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
    # Replace prior snapshot wholesale - aircraft move fast and old rows are
    # noise once a new snapshot arrives.
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


# --------------------------------------------------------------------------- #
# Fetcher
# --------------------------------------------------------------------------- #
def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def fetch_states() -> list[dict]:
    """Pull the global /states/all snapshot. Returns parsed rows; empty on failure."""
    session = get_session(expire_after=60)  # cache 1 minute - aircraft move fast
    try:
        r = session.get(OPENSKY_URL, timeout=25)
        r.raise_for_status()
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
            parsed.append(
                {
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
                }
            )
        except (IndexError, TypeError, ValueError):
            continue
    return parsed


def fetch() -> list[Signal]:
    """Persist snapshot + emit congestion signals near major cargo airports."""
    flights = fetch_states()
    if not flights:
        return []

    try:
        write_snapshot(flights)
    except Exception as e:
        print(f"[opensky] snapshot write failed: {e}")

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
