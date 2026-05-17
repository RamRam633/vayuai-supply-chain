"""
Commodity prices - FRED-first, with Datahub.io daily mirrors for the three
energy series.

History (2026-05):
    yfinance was the original source. Yahoo started rate-limiting it
    aggressively from cloud IPs, and the Stooq fallback is geo-blocked
    from most US data centers. Both have been removed. The pipeline now
    relies on:

        1. FRED (St. Louis Fed) - primary, requires a free FRED_API_KEY.
           Covers all 10 commodities; daily for oil/gas/gold, monthly for
           grains/metals (forward-filled to daily on display).
        2. Datahub.io daily CSV mirrors - secondary, no key. Covers WTI,
           Brent, Natural Gas, Gold. Useful even without the FRED key.
        3. Synthetic deterministic series - only used for the few
           commodities neither source can supply. Clearly flagged via
           data/commodities_demo.marker so the UI can surface a banner.

The wide-DataFrame shape (date index, commodity-display-name columns) and
the public API (`fetch_prices`, `fetch`, `is_demo_prices`) are unchanged
so the UI keeps working.
"""

from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import pandas as pd

from .base import Signal, get_session
import config

DEMO_MARKER = Path(config.DATA_DIR) / "commodities_demo.marker"


# --------------------------------------------------------------------------- #
# Source maps
# --------------------------------------------------------------------------- #
# FRED series IDs per commodity display name.
# Daily series: DCOILWTICO, DCOILBRENTEU, DHHNGSP, GOLDPMGBD228NLBM.
# Everything else is the IMF Primary Commodity Prices monthly bundle,
# distributed via FRED with the P{ABBR}USDM naming convention.
_FRED_IDS = {
    # Energy (daily)
    "Crude Oil (WTI)": "DCOILWTICO",
    "Brent Crude":     "DCOILBRENTEU",
    "Natural Gas":     "DHHNGSP",
    # Precious metals
    "Gold":            "GOLDPMGBD228NLBM",   # daily, London PM fix
    "Silver":          "PSILVUSDM",          # monthly
    # Industrial metals (monthly)
    "Copper":          "PCOPPUSDM",
    "Aluminum":        "PALUMUSDM",
    "Nickel":          "PNICKUSDM",
    "Zinc":            "PZINCUSDM",
    "Iron Ore":        "PIORECRUSDM",
    "Uranium":         "PURANUSDM",
    # Grains (monthly)
    "Wheat":           "PWHEAMTUSDM",
    "Corn":            "PMAIZMTUSDM",
    "Soybeans":        "PSOYBUSDM",
    # Soft agriculture (monthly)
    "Coffee":          "PCOFFOTMUSDM",
    "Sugar":           "PSUGAISAUSDM",
    "Cocoa":           "PCOCOUSDM",
    "Cotton":          "PCOTTINDUSDM",
}

# Datahub.io curated CSV mirrors - Date,Price columns. Used as a secondary
# source so the energy series still light up without a FRED key.
_DATAHUB_CSVS = {
    "Crude Oil (WTI)": "https://datahub.io/core/oil-prices/r/wti-daily.csv",
    "Brent Crude":     "https://datahub.io/core/oil-prices/r/brent-daily.csv",
    "Natural Gas":     "https://datahub.io/core/natural-gas/r/daily.csv",
    "Gold":            "https://datahub.io/core/gold-prices/r/monthly.csv",
}

# Approximate 2026 levels used as the anchor for synthetic fallback series.
# Units match what FRED reports for each: USD/bbl for oil, USD/mmBtu for gas,
# USD/troy oz for gold/silver, USD/metric ton for industrial metals,
# USD/bushel for grains, USD/lb for cotton/sugar/coffee, USD/kg for cocoa.
_SYNTH_ANCHORS = {
    "Crude Oil (WTI)":   101.0,
    "Brent Crude":       105.0,
    "Natural Gas":         2.85,
    "Gold":             2850.0,
    "Silver":             32.0,
    "Copper":           9200.0,    # IMF reports in USD/ton
    "Aluminum":         2500.0,
    "Nickel":          18000.0,
    "Zinc":             2800.0,
    "Iron Ore":          110.0,
    "Uranium":            80.0,
    "Wheat":               5.40,
    "Corn":                4.25,
    "Soybeans":           11.80,
    "Coffee":              2.00,
    "Sugar":               0.21,
    "Cocoa":               6.50,
    "Cotton":              0.80,
}
_SYNTH_VOL = {
    "Crude Oil (WTI)":  0.014,
    "Brent Crude":      0.013,
    "Natural Gas":      0.030,
    "Gold":             0.010,
    "Silver":           0.020,
    "Copper":           0.018,
    "Aluminum":         0.015,
    "Nickel":           0.025,
    "Zinc":             0.020,
    "Iron Ore":         0.025,
    "Uranium":          0.020,
    "Wheat":            0.018,
    "Corn":             0.018,
    "Soybeans":         0.016,
    "Coffee":           0.025,
    "Sugar":            0.020,
    "Cocoa":            0.025,
    "Cotton":           0.015,
}


# --------------------------------------------------------------------------- #
# Demo marker - surfaced in the UI as a soft "some series simulated" pill.
# --------------------------------------------------------------------------- #
def is_demo_prices() -> bool:
    return DEMO_MARKER.exists()


def synthetic_columns() -> list[str]:
    """Which series ended up synthetic on the last refresh."""
    if not DEMO_MARKER.exists():
        return []
    try:
        return json.loads(DEMO_MARKER.read_text()).get("synthetic_columns", [])
    except Exception:
        return []


def _mark_demo(columns: list[str]) -> None:
    try:
        DEMO_MARKER.write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "synthetic_columns": columns,
        }))
    except Exception:
        pass


def _clear_demo() -> None:
    try:
        DEMO_MARKER.unlink(missing_ok=True)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Source #1 - FRED (preferred)
# --------------------------------------------------------------------------- #
FRED_OBS_URL = "https://api.stlouisfed.org/fred/series/observations"


def _fred_series(series_id: str, limit: int = 730) -> pd.Series:
    """Pull a single FRED series. Empty Series on failure / no key."""
    if not config.FRED_API_KEY:
        return pd.Series(dtype=float)
    session = get_session(expire_after=config.CACHE_TTL["fred"])
    params = {
        "series_id":  series_id,
        "api_key":    config.FRED_API_KEY,
        "file_type":  "json",
        "sort_order": "desc",
        "limit":      limit,
    }
    try:
        r = session.get(FRED_OBS_URL, params=params, timeout=20)
        r.raise_for_status()
        data = r.json() or {}
    except Exception as e:
        print(f"[fred] {series_id} failed: {e}")
        return pd.Series(dtype=float)

    rows: list[tuple] = []
    for o in data.get("observations") or []:
        v = o.get("value")
        if v in (None, ".", ""):   # FRED uses "." for missing
            continue
        try:
            rows.append((pd.to_datetime(o["date"]), float(v)))
        except (ValueError, KeyError):
            continue
    if not rows:
        return pd.Series(dtype=float)
    return pd.Series(dict(rows), name=series_id).sort_index()


# --------------------------------------------------------------------------- #
# Source #2 - Datahub.io curated CSV mirrors
# --------------------------------------------------------------------------- #
def _datahub_series(url: str) -> pd.Series:
    session = get_session(expire_after=config.CACHE_TTL["fred"])
    try:
        r = session.get(url, timeout=15)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        if df.empty or "Date" not in df.columns or "Price" not in df.columns:
            return pd.Series(dtype=float)
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"]).set_index("Date").sort_index()
        return df["Price"].astype(float)
    except Exception as e:
        print(f"[datahub] {url} failed: {e}")
        return pd.Series(dtype=float)


# --------------------------------------------------------------------------- #
# Source #3 - synthetic deterministic fallback
# --------------------------------------------------------------------------- #
def _synthesize(name: str, days: int = 180, seed: int = 7) -> pd.Series:
    """Deterministic random-walk series anchored at a plausible recent level."""
    anchor = _SYNTH_ANCHORS.get(name, 100.0)
    sigma  = _SYNTH_VOL.get(name, 0.015)
    rng = random.Random(hash((name, seed)) & 0xFFFF_FFFF)

    today = datetime.now(timezone.utc).date()
    dates = [today - timedelta(days=days - i) for i in range(days)]
    levels = [1.0]
    for _ in range(days - 1):
        prev = levels[-1]
        # Mild mean-reversion toward 1.0 to keep the walk grounded.
        step = rng.gauss(0, sigma) + (1.0 - prev) * 0.01
        levels.append(prev * math.exp(step))
    scale = anchor / levels[-1]
    values = [round(v * scale, 4) for v in levels]
    return pd.Series(values, index=pd.DatetimeIndex(dates, name="Date"),
                     name=name)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def fetch_prices(period: str = "180d") -> pd.DataFrame:
    """Return wide DataFrame indexed by date, columns = commodity display names.

    Caches the merged result to data/commodity_prices.parquet for TTL.
    """
    cache_file = config.DATA_DIR / "commodity_prices.parquet"
    if cache_file.exists():
        age = datetime.now(timezone.utc).timestamp() - cache_file.stat().st_mtime
        if age < config.CACHE_TTL["yfinance"]:
            try:
                cached = pd.read_parquet(cache_file)
                if not cached.empty:
                    return cached
            except Exception:
                pass

    out: dict[str, pd.Series] = {}
    synthetic: list[str] = []

    for name in config.COMMODITIES.keys():
        # Tier 1 - FRED
        fred_id = _FRED_IDS.get(name)
        s = _fred_series(fred_id) if fred_id else pd.Series(dtype=float)
        if not s.empty:
            out[name] = s
            continue

        # Tier 2 - Datahub mirrors (oil/gas/gold)
        url = _DATAHUB_CSVS.get(name)
        if url:
            s = _datahub_series(url)
            if not s.empty:
                out[name] = s.tail(730)
                continue

        # Tier 3 - synthetic
        out[name] = _synthesize(name)
        synthetic.append(name)

    if synthetic:
        _mark_demo(synthetic)
    else:
        _clear_demo()

    df = pd.DataFrame(out).sort_index()
    if df.empty:
        return df

    df.index = pd.to_datetime(df.index).normalize()
    df = df.groupby(level=0).last()

    # Trim BEFORE the full-daily reindex. Some Datahub mirrors (notably gold,
    # monthly) carry decades of history; without the trim the daily reindex
    # builds a ~22k-row frame and chokes the UI.
    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=400)
    df = df[df.index >= cutoff]

    if df.empty:
        return df

    # Now densify to a clean daily index. Monthly series forward-fill so the
    # rebased chart stays smooth alongside daily ones.
    full_idx = pd.date_range(df.index.min(), df.index.max(), freq="D")
    df = df.reindex(full_idx).ffill(limit=40)
    df.index.name = "Date"

    try:
        df.to_parquet(cache_file)
    except Exception as e:
        print(f"[commodities] cache write failed: {e}")
    return df


def fetch() -> list[Signal]:
    """Emit shock signals (|z| >= 2 on 1d return vs trailing 20d stdev).

    Skips synthetic series so we don't fire fake shocks on simulated data.
    """
    df = fetch_prices()
    if df.empty or len(df) < 21:
        return []

    synth = set(synthetic_columns())
    real = [c for c in df.columns if c not in synth]
    if not real:
        return []

    df_real = df[real]
    returns = df_real.pct_change(fill_method=None)
    latest = returns.iloc[-1]
    vol = returns.iloc[-21:-1].std()
    z = (latest / vol).fillna(0.0)

    signals: list[Signal] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for name, zscore in z.items():
        try:
            zscore = float(zscore)
        except (TypeError, ValueError):
            continue
        if abs(zscore) < 2.0:
            continue
        severity = float(min(1.0, abs(zscore) / 5.0))
        direction = "spike" if zscore > 0 else "drop"
        latest_price = float(df_real[name].iloc[-1])
        signals.append(
            Signal(
                source="commodities",
                category="commodity",
                title=f"{name} {direction}: z={zscore:+.1f} (last close ${latest_price:.2f})",
                severity=severity,
                timestamp_utc=now_iso,
                payload={
                    "commodity":    name,
                    "zscore":       zscore,
                    "last_close":   latest_price,
                    "pct_change_1d": float(latest[name])
                                     if name in latest.index else None,
                },
            )
        )
    return signals
