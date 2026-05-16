"""
Base contract for all data pipelines.

Every pipeline normalizes its source into a Signal record so downstream
analytics (risk scoring, summarization) and UI never depend on source-
specific shapes. Add a new feed = add a new file that emits Signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any
from pathlib import Path

import requests_cache

import config


# --------------------------------------------------------------------------- #
# Shared cached HTTP session.
# Backed by SQLite at config.CACHE_DB_PATH. Per-source TTL handled in fetchers.
# --------------------------------------------------------------------------- #
_SESSION: requests_cache.CachedSession | None = None


def get_session(expire_after: int = 600) -> requests_cache.CachedSession:
    """Return a process-shared cached HTTP session.

    expire_after: default TTL in seconds; override per-call as needed.
    """
    global _SESSION
    if _SESSION is None:
        Path(config.DATA_DIR).mkdir(exist_ok=True)
        _SESSION = requests_cache.CachedSession(
            cache_name=str(config.DATA_DIR / "http_cache"),
            backend="sqlite",
            expire_after=expire_after,
            allowable_methods=("GET",),
            stale_if_error=True,
        )
    return _SESSION


# --------------------------------------------------------------------------- #
# Canonical signal record.
# --------------------------------------------------------------------------- #
@dataclass
class Signal:
    """A single normalized event/observation from any source.

    Attributes
    ----------
    source        : identifier of the originating feed (e.g. 'gdelt', 'usgs')
    category      : one of {geopolitical, weather, seismic, commodity,
                            freight, vessel, macro, news}
    title         : short human-readable summary
    severity      : 0..1 normalized intensity (used by risk engine)
    lat, lon      : optional location; some signals are global
    region        : optional pre-tagged region (falls back to lat/lon lookup)
    timestamp_utc : ISO-8601 UTC string
    url           : optional source link
    payload       : raw extra fields (whatever the source provided)
    """

    source: str
    category: str
    title: str
    severity: float = 0.0
    lat: float | None = None
    lon: float | None = None
    region: str | None = None
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    url: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Lat/lon -> region lookup.
# --------------------------------------------------------------------------- #
def regions_for_point(lat: float | None, lon: float | None) -> list[str]:
    """Return all configured regions whose bbox contains (lat, lon).

    Returns empty list if coords are None or fall outside every region.
    Some chokepoints sit on borders, so multiple matches are valid.
    """
    if lat is None or lon is None:
        return []
    hits: list[str] = []
    for name, meta in config.REGIONS.items():
        min_lon, min_lat, max_lon, max_lat = meta["bbox"]
        if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
            hits.append(name)
    return hits
