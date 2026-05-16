"""
Ports & vessels.

Live AIS data comes from `scripts/refresh_ais.py` (a separate WebSocket
listener) which requires a free AISStream key. When that snapshot is
present we read it. When it isn't, we fall back to a deterministic
*synthetic* vessel distribution clustered around real ports, chokepoints
and the busiest shipping lanes - so the dashboard is never blank.

The Streamlit Ships page surfaces a clear banner when the snapshot is
synthetic so users know the source.
"""

from __future__ import annotations

import json
import math
import random
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .base import Signal
import config

SNAPSHOT_DB = Path(config.DATA_DIR) / "ais_snapshot.sqlite"
DEMO_MARKER = Path(config.DATA_DIR) / "ais_demo.marker"

SHIP_TYPES         = ["Container", "Cargo", "Tanker", "Bulk Carrier",
                      "Vehicle Carrier", "LNG Carrier", "Tug", "Passenger",
                      "Fishing"]
SHIP_TYPE_WEIGHTS  = [0.26, 0.22, 0.20, 0.14, 0.05, 0.04, 0.04, 0.03, 0.02]
NAME_PREFIXES      = ["EVER", "MAERSK", "MSC", "ONE", "COSCO", "HAPAG",
                      "CMA CGM", "YANG MING", "HMM", "ZIM", "OOCL", "PIL",
                      "EVERGREEN", "WAN HAI", "X-PRESS"]
NAME_SUFFIXES      = ["ACE", "BEACON", "CROWN", "DAWN", "EAGLE", "FORTUNE",
                      "GLORY", "HORIZON", "ICON", "JUPITER", "KING", "LEGEND",
                      "MERIDIAN", "NORTH", "ORION", "PHOENIX", "QUEEN",
                      "RIVER", "SUMMIT", "TRADER", "UNITY", "VOYAGER"]


# --------------------------------------------------------------------------- #
# Snapshot DB
# --------------------------------------------------------------------------- #
def _ensure_db():
    SNAPSHOT_DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(SNAPSHOT_DB)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS vessels (
            mmsi      INTEGER PRIMARY KEY,
            lat       REAL,
            lon       REAL,
            sog       REAL,
            cog       REAL,
            ship_type TEXT,
            name      TEXT,
            ts_utc    TEXT
        )
        """
    )
    con.commit()
    con.close()


def write_snapshot(rows: list[dict]) -> int:
    _ensure_db()
    con = sqlite3.connect(SNAPSHOT_DB)
    cur = con.cursor()
    for row in rows:
        cur.execute(
            """
            INSERT OR REPLACE INTO vessels
              (mmsi, lat, lon, sog, cog, ship_type, name, ts_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(row["mmsi"]),
                float(row["lat"]),
                float(row["lon"]),
                float(row.get("sog") or 0.0),
                float(row.get("cog") or 0.0),
                str(row.get("ship_type") or ""),
                str(row.get("name") or ""),
                row.get("ts_utc") or datetime.now(timezone.utc).isoformat(),
            ),
        )
    con.commit()
    n = cur.execute("SELECT COUNT(*) FROM vessels").fetchone()[0]
    con.close()
    # Real data was written - drop the demo marker if it exists.
    try:
        DEMO_MARKER.unlink(missing_ok=True)
    except Exception:
        pass
    return n


# --------------------------------------------------------------------------- #
# Synthetic vessel generation (used when no AISStream key / data).
# --------------------------------------------------------------------------- #
def _make_vessel(rng: random.Random, lat: float, lon: float,
                 mmsi_seed: int) -> dict:
    st = rng.choices(SHIP_TYPES, weights=SHIP_TYPE_WEIGHTS)[0]
    return {
        "mmsi": 200_000_000 + mmsi_seed,
        "lat": round(lat, 4),
        "lon": round(lon, 4),
        "sog": round(rng.uniform(0.0, 22.0), 1),
        "cog": round(rng.uniform(0.0, 360.0), 1),
        "ship_type": st,
        "name": f"{rng.choice(NAME_PREFIXES)} {rng.choice(NAME_SUFFIXES)} "
                f"{rng.randint(1, 99)}",
        "ts_utc": datetime.now(timezone.utc).isoformat(),
    }


def _scatter(rng: random.Random, center_lat: float, center_lon: float,
             radius_km: float) -> tuple[float, float]:
    r = rng.uniform(0, radius_km)
    theta = rng.uniform(0, 2 * math.pi)
    dlat = (r / 111.0) * math.sin(theta)
    cos_lat = max(0.2, math.cos(math.radians(center_lat)))
    dlon = (r / (111.0 * cos_lat)) * math.cos(theta)
    return center_lat + dlat, center_lon + dlon


def _generate_demo_vessels(seed: int = 42) -> list[dict]:
    """Deterministic synthetic vessel snapshot.

    ~80 vessels per major port, ~45 per chokepoint, ~150 along each major
    lane. Realistic ship-type distribution + believable callsign names.
    """
    rng = random.Random(seed)
    vessels: list[dict] = []
    mmsi = 0

    # Clusters around major ports
    for port in config.MAJOR_PORTS:
        n = rng.randint(60, 110)
        for _ in range(n):
            mmsi += rng.randint(1, 50)
            lat, lon = _scatter(rng, port["lat"], port["lon"], 80.0)
            vessels.append(_make_vessel(rng, lat, lon, mmsi))

    # Clusters at chokepoints
    for ck in config.CHOKEPOINTS:
        n = rng.randint(30, 55)
        for _ in range(n):
            mmsi += rng.randint(1, 50)
            lat, lon = _scatter(rng, ck["lat"], ck["lon"], 150.0)
            vessels.append(_make_vessel(rng, lat, lon, mmsi))

    # Vessels in transit along major shipping lanes (linear interpolation
    # plus scatter - fine for visualization, not for navigation).
    ports_by = {p["name"]: p for p in config.MAJOR_PORTS}
    lanes = [
        ("Shanghai",            "Los Angeles"),
        ("Shanghai",            "Rotterdam"),
        ("Singapore",           "Rotterdam"),
        ("Dubai (Jebel Ali)",   "Singapore"),
        ("New York/NJ",         "Rotterdam"),
        ("Santos",              "Shanghai"),
        ("Durban",              "Singapore"),
        ("Shanghai",            "Long Beach"),
        ("Mumbai (JNPT)",       "Hamburg"),
        ("Busan",               "Long Beach"),
        ("Hamburg",             "New York/NJ"),
    ]
    for start, end in lanes:
        s, e = ports_by.get(start), ports_by.get(end)
        if not s or not e:
            continue
        for i in range(1, 151):
            t = i / 152.0
            lat = s["lat"] + (e["lat"] - s["lat"]) * t + rng.uniform(-1.6, 1.6)
            lon = s["lon"] + (e["lon"] - s["lon"]) * t + rng.uniform(-1.6, 1.6)
            mmsi += rng.randint(1, 50)
            vessels.append(_make_vessel(rng, lat, lon, mmsi))

    return vessels


def _ensure_demo_snapshot_if_empty() -> bool:
    """If the AIS DB is empty, populate it with synthetic data.

    Returns True iff the snapshot just served is synthetic.
    """
    _ensure_db()
    con = sqlite3.connect(SNAPSHOT_DB)
    n = con.execute("SELECT COUNT(*) FROM vessels").fetchone()[0]
    con.close()
    if n > 0:
        return DEMO_MARKER.exists()

    # No real vessels - generate demo set.
    demo = _generate_demo_vessels()
    con = sqlite3.connect(SNAPSHOT_DB)
    cur = con.cursor()
    for v in demo:
        cur.execute(
            """
            INSERT OR REPLACE INTO vessels
              (mmsi, lat, lon, sog, cog, ship_type, name, ts_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (v["mmsi"], v["lat"], v["lon"], v["sog"], v["cog"],
             v["ship_type"], v["name"], v["ts_utc"]),
        )
    con.commit()
    con.close()
    DEMO_MARKER.write_text(
        json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(),
                    "n_vessels": len(demo)})
    )
    return True


def is_demo_snapshot() -> bool:
    """True if the current vessel snapshot was generated, not collected live."""
    return DEMO_MARKER.exists()


def read_snapshot() -> list[dict]:
    """Return all vessels in the snapshot DB.

    If the DB is empty, a deterministic synthetic snapshot is generated and
    persisted (with a marker file flagging it as demo).
    """
    _ensure_demo_snapshot_if_empty()
    if not SNAPSHOT_DB.exists():
        return []
    con = sqlite3.connect(SNAPSHOT_DB)
    cur = con.cursor()
    cur.execute(
        "SELECT mmsi, lat, lon, sog, cog, ship_type, name, ts_utc FROM vessels"
    )
    cols = ["mmsi", "lat", "lon", "sog", "cog", "ship_type", "name", "ts_utc"]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    con.close()
    return rows


# --------------------------------------------------------------------------- #
# Port congestion proxy
# --------------------------------------------------------------------------- #
def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def port_congestion() -> list[dict]:
    """Per-port vessel counts and normalized congestion 0..1."""
    vessels = read_snapshot()
    out: list[dict] = []
    RADIUS_KM = 50
    for p in config.MAJOR_PORTS:
        if not vessels:
            n = 0
        else:
            n = sum(
                1 for v in vessels
                if _haversine(p["lat"], p["lon"], v["lat"], v["lon"]) <= RADIUS_KM
            )
        congestion = min(1.0, n / 50.0)
        out.append(
            {
                "port": p["name"], "country": p["country"],
                "vessels_nearby": n, "congestion": congestion,
                "lat": p["lat"], "lon": p["lon"],
            }
        )
    return out


def chokepoint_traffic() -> list[dict]:
    """Vessels within each chokepoint's radius. Useful for the Chokepoints page."""
    vessels = read_snapshot()
    out: list[dict] = []
    for ck in config.CHOKEPOINTS:
        rkm = ck.get("radius_km", 150)
        if not vessels:
            n = 0
        else:
            n = sum(
                1 for v in vessels
                if _haversine(ck["lat"], ck["lon"], v["lat"], v["lon"]) <= rkm
            )
        out.append(
            {
                "name":            ck["name"],
                "lat":             ck["lat"],
                "lon":             ck["lon"],
                "radius_km":       rkm,
                "vessels_nearby":  n,
                "intensity":       min(1.0, n / 80.0),  # rough 0..1
            }
        )
    return out


def fetch() -> list[Signal]:
    """Emit a Signal per port whose congestion proxy is elevated."""
    signals: list[Signal] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for row in port_congestion():
        if row["congestion"] < 0.5:
            continue
        signals.append(
            Signal(
                source="ais-snapshot",
                category="freight",
                title=f"Elevated vessel density near {row['port']}: "
                      f"{row['vessels_nearby']} ships within 50km",
                severity=row["congestion"],
                lat=row["lat"],
                lon=row["lon"],
                timestamp_utc=now_iso,
                payload=row,
            )
        )
    return signals
