"""
Regional risk scoring.

Inputs: the on-disk Signal store written by scripts/refresh_data.py.
Output: a dict {region_name: {score: 0..100, components: {...}, signals: [...]}}

Each signal contributes to the component it belongs to. The component score
for a region is the mean severity of recent signals in that region, capped
at 1.0. The composite is the weighted sum (config.RISK_WEIGHTS) rescaled
to 0..100.

Important: this is a transparent heuristic, not a validated model. Tune the
weights in config.py once you have ground-truth disruption events.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import config
from pipelines.base import regions_for_point

SIGNAL_PATH = Path(config.DATA_DIR) / "signals.json"
DEFAULT_LOOKBACK_HOURS = 36


def load_signals() -> dict[str, Any]:
    """Read the latest signals.json snapshot. Empty dict if absent."""
    if not SIGNAL_PATH.exists():
        return {"generated_at": None, "summary": {}, "signals": []}
    try:
        return json.loads(SIGNAL_PATH.read_text())
    except Exception as e:
        print(f"[risk] failed to load signals: {e}")
        return {"generated_at": None, "summary": {}, "signals": []}


def _tag_region(sig: dict) -> list[str]:
    """Decide which regions a signal belongs to."""
    if sig.get("region"):
        # Country name pre-tagged by source. Map to region best-effort.
        return _country_to_regions(sig["region"])
    return regions_for_point(sig.get("lat"), sig.get("lon"))


# Minimal country->region mapping. Extend as needed; falls through to "Global".
_COUNTRY_REGION = {
    "United States": "North America", "Canada": "North America", "Mexico": "North America",
    "Brazil": "South America", "Argentina": "South America", "Chile": "South America",
    "Germany": "Europe", "France": "Europe", "United Kingdom": "Europe", "Netherlands": "Europe",
    "Italy": "Europe", "Spain": "Europe", "Poland": "Europe", "Ukraine": "Europe",
    "Russia": "Europe", "Turkey": "Middle East", "Iran": "Middle East", "Iraq": "Middle East",
    "Saudi Arabia": "Middle East", "Yemen": "Middle East", "Israel": "Middle East",
    "Egypt": "Africa", "Nigeria": "Africa", "South Africa": "Africa", "Kenya": "Africa",
    "India": "South Asia", "Pakistan": "South Asia", "Bangladesh": "South Asia",
    "China": "East Asia", "Japan": "East Asia", "South Korea": "East Asia", "Taiwan": "East Asia",
    "Vietnam": "Southeast Asia", "Thailand": "Southeast Asia", "Indonesia": "Southeast Asia",
    "Philippines": "Southeast Asia", "Malaysia": "Southeast Asia", "Singapore": "Southeast Asia",
    "Australia": "Oceania", "New Zealand": "Oceania",
}


def _country_to_regions(name: str) -> list[str]:
    region = _COUNTRY_REGION.get(name)
    return [region] if region else []


_CATEGORY_TO_COMPONENT = {
    "geopolitical": "geopolitical_intensity",
    "weather":      "weather_alerts",
    "tropical":     "weather_alerts",            # NHC cyclones rolled into weather
    "seismic":      "seismic_activity",
    "volcanic":     "seismic_activity",          # EONET volcanoes
    "commodity":    "commodity_volatility",
    "freight":      "port_congestion_proxy",
    "flight":       "aviation_disruption",       # OpenSky-derived airport congestion
    "natural":      "natural_disasters",         # EONET wildfires/floods/drought/etc
    "macro":        "commodity_volatility",      # macro shocks rolled into commodity bucket
    "news":         "geopolitical_intensity",    # GoogleNews/Reddit chatter feeds geopolitical
}


def compute_regional_risk(
    signals: list[dict] | None = None,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
) -> dict[str, dict[str, Any]]:
    """Return {region: {score, components, n_signals}} for every configured region.

    Commodity / macro signals are global → applied uniformly to all regions.
    """
    if signals is None:
        signals = load_signals().get("signals", [])

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    fresh: list[dict] = []
    for s in signals:
        try:
            ts = datetime.fromisoformat(s["timestamp_utc"].replace("Z", "+00:00"))
            # Some upstream feeds (notably GDACS) emit tz-naive ISO strings.
            # Treat them as UTC so the comparison below never crashes.
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if ts >= cutoff:
            fresh.append(s)

    # Bucket severities by (region, component).
    buckets: dict[str, dict[str, list[float]]] = {
        r: {c: [] for c in config.RISK_WEIGHTS} for r in config.REGIONS
    }

    for sig in fresh:
        comp = _CATEGORY_TO_COMPONENT.get(sig.get("category", ""))
        if not comp:
            continue
        sev = float(sig.get("severity", 0.0) or 0.0)
        if sev <= 0:
            continue

        # Global signals (no geo) hit every region equally.
        if sig.get("category") in ("commodity", "macro"):
            for r in buckets:
                buckets[r][comp].append(sev)
            continue

        for r in _tag_region(sig):
            if r in buckets:
                buckets[r][comp].append(sev)

    weights = config.RISK_WEIGHTS
    total_w = sum(weights.values()) or 1.0

    out: dict[str, dict[str, Any]] = {}
    for r, comps in buckets.items():
        components: dict[str, float] = {}
        for c, sevs in comps.items():
            # Mean severity, then dampened by count saturation so 1 huge event
            # ≈ 5 moderate events.
            if not sevs:
                components[c] = 0.0
                continue
            mean_sev = sum(sevs) / len(sevs)
            count_factor = min(1.0, len(sevs) / 5.0)
            components[c] = min(1.0, mean_sev * (0.6 + 0.4 * count_factor))

        composite_unit = sum(components[c] * weights[c] for c in components) / total_w
        score = round(min(100.0, composite_unit * 100.0), 1)

        out[r] = {
            "score": score,
            "components": components,
            "n_signals": sum(len(v) for v in comps.values()),
        }
    return out


def top_risks(regional: dict[str, dict[str, Any]], n: int = 3) -> list[tuple[str, float]]:
    """Return the n highest-scoring regions, descending."""
    ranked = sorted(regional.items(), key=lambda kv: kv[1]["score"], reverse=True)
    return [(r, m["score"]) for r, m in ranked[:n]]
