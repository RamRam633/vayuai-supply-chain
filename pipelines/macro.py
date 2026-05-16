"""
Macro / freight indices — resilient three-tier fetch:

    1. FRED API                        (if FRED_API_KEY is set)
    2. Free, key-less mirrors          (Datahub.io for oil/gas, Frankfurter.app
                                        for FX basket → synthetic DXY-like)
    3. Synthetic deterministic series  (clearly flagged via demo marker)

The Trends/Macro panel works out of the box without any API key.
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

DEMO_MARKER = Path(config.DATA_DIR) / "macro_demo.marker"


# --------------------------------------------------------------------------- #
# Tier 1 — FRED
# --------------------------------------------------------------------------- #
FRED_OBS_URL = "https://api.stlouisfed.org/fred/series/observations"


def _fred_series(series_id: str, limit: int = 365) -> pd.Series:
    if not config.FRED_API_KEY:
        return pd.Series(dtype=float)
    session = get_session(expire_after=config.CACHE_TTL["fred"])
    params = {
        "series_id": series_id,
        "api_key":   config.FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    }
    try:
        r = session.get(FRED_OBS_URL, params=params, timeout=20)
        r.raise_for_status()
        data = r.json() or {}
    except Exception as e:
        print(f"[fred] {series_id} failed: {e}")
        return pd.Series(dtype=float)

    rows = data.get("observations") or []
    parsed: list[tuple] = []
    for o in rows:
        try:
            parsed.append((o["date"], float(o["value"])))
        except (ValueError, KeyError):
            continue
    if not parsed:
        return pd.Series(dtype=float)
    s = pd.Series(
        {pd.to_datetime(d): v for d, v in parsed}, name=series_id,
    ).sort_index()
    return s


# --------------------------------------------------------------------------- #
# Tier 2 — free no-key sources
# --------------------------------------------------------------------------- #
_DATAHUB = {
    "WTI Crude (USD/bbl)":     "https://datahub.io/core/oil-prices/r/wti-daily.csv",
    "Brent Crude (USD/bbl)":   "https://datahub.io/core/oil-prices/r/brent-daily.csv",
    "Natural Gas (Henry Hub)": "https://datahub.io/core/natural-gas/r/daily.csv",
}


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
        return df["Price"].astype(float).tail(365)
    except Exception as e:
        print(f"[datahub-macro] {url} failed: {e}")
        return pd.Series(dtype=float)


def _frankfurter_usd_index(days: int = 180) -> pd.Series:
    """USD trade-weighted index proxy built from ECB rates via Frankfurter.app.

    Uses a basket of EUR/JPY/GBP/CAD with broad weights similar to the Fed's
    DTWEXBGS. Result is rebased to 100 at the start of the window so it tracks
    relative strength, not absolute level.
    """
    end   = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    url = (
        f"https://api.frankfurter.app/{start.isoformat()}.."
        f"{end.isoformat()}?from=USD&to=EUR,JPY,GBP,CAD,CHF,SEK"
    )
    session = get_session(expire_after=config.CACHE_TTL["fred"])
    try:
        r = session.get(url, timeout=15)
        r.raise_for_status()
        data = r.json() or {}
    except Exception as e:
        print(f"[frankfurter] failed: {e}")
        return pd.Series(dtype=float)

    rates = data.get("rates") or {}
    if not rates:
        return pd.Series(dtype=float)

    # Fed DTWEXBGS broad weights (approx); we normalize to the available subset.
    weights = {"EUR": 0.576, "JPY": 0.136, "GBP": 0.119,
               "CAD": 0.091, "CHF": 0.036, "SEK": 0.042}
    rows = []
    for d_str, day_rates in sorted(rates.items()):
        used = {k: v for k, v in day_rates.items() if k in weights}
        if not used:
            continue
        total_w = sum(weights[k] for k in used) or 1.0
        # Index level = weighted geometric mean of USD value (1/rate) — higher
        # when USD is stronger.
        log_sum = sum(weights[k] * math.log(1.0 / used[k]) for k in used)
        idx = math.exp(log_sum / total_w)
        rows.append((pd.to_datetime(d_str), idx))
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series(dict(rows)).sort_index()
    return s / s.iloc[0] * 100.0


# --------------------------------------------------------------------------- #
# Tier 3 — synthetic
# --------------------------------------------------------------------------- #
_SYNTH_ANCHORS = {
    "10Y Treasury Yield":      4.55,
    "GSCPI proxy":             0.30,
    "WTI Crude (USD/bbl)":   101.0,
    "Brent Crude (USD/bbl)": 105.0,
    "Natural Gas (Henry Hub)": 2.85,
    "USD Trade-Weighted Index": 100.0,
}
_SYNTH_VOL = {
    "10Y Treasury Yield":      0.012,
    "GSCPI proxy":             0.040,
    "WTI Crude (USD/bbl)":     0.014,
    "Brent Crude (USD/bbl)":   0.013,
    "Natural Gas (Henry Hub)": 0.028,
    "USD Trade-Weighted Index": 0.006,
}


def _synthesize(name: str, days: int = 180, seed: int = 11) -> pd.Series:
    anchor = _SYNTH_ANCHORS.get(name, 100.0)
    sigma  = _SYNTH_VOL.get(name, 0.012)
    rng = random.Random(hash((name, seed)) & 0xFFFF_FFFF)
    today = datetime.now(timezone.utc).date()
    dates = [today - timedelta(days=days - i) for i in range(days)]
    levels = [1.0]
    for _ in range(days - 1):
        prev = levels[-1]
        step = rng.gauss(0, sigma) + (1.0 - prev) * 0.01
        levels.append(prev * math.exp(step))
    scale = anchor / levels[-1]
    values = [round(v * scale, 4) for v in levels]
    return pd.Series(values, index=pd.DatetimeIndex(dates), name=name)


# --------------------------------------------------------------------------- #
# Demo marker
# --------------------------------------------------------------------------- #
def is_demo_macro() -> bool:
    return DEMO_MARKER.exists()


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
# Public API — keep same shape so trends.py / pages keep working unchanged.
# --------------------------------------------------------------------------- #
def fetch_series(series_id: str, limit: int = 365) -> pd.Series:
    """Compatibility shim — looks up display-name by series_id, then falls through."""
    name = next(
        (k for k, v in config.FRED_SERIES.items() if v == series_id),
        series_id,
    )
    series = _fred_series(series_id, limit=limit)
    if not series.empty:
        return series
    return _fallback_for(name)


def _fallback_for(name: str) -> pd.Series:
    # Tier 2 mirrors
    if name in _DATAHUB:
        s = _datahub_series(_DATAHUB[name])
        if not s.empty:
            return s
    if name == "USD Trade-Weighted Index":
        s = _frankfurter_usd_index()
        if not s.empty:
            return s
    # Tier 3 synthetic
    return _synthesize(name)


def fetch_all_series() -> dict[str, pd.Series]:
    """Return every display-named series, using whatever tier succeeds."""
    out: dict[str, pd.Series] = {}
    synthetic: list[str] = []

    for display, sid in config.FRED_SERIES.items():
        # Tier 1
        s = _fred_series(sid) if config.FRED_API_KEY else pd.Series(dtype=float)
        if not s.empty:
            out[display] = s
            continue
        # Tier 2
        s = pd.Series(dtype=float)
        if display in _DATAHUB:
            s = _datahub_series(_DATAHUB[display])
        elif display == "USD Trade-Weighted Index":
            s = _frankfurter_usd_index()
        if not s.empty:
            out[display] = s
            continue
        # Tier 3
        out[display] = _synthesize(display)
        synthetic.append(display)

    if synthetic:
        _mark_demo(synthetic)
    else:
        _clear_demo()
    return out


def fetch() -> list[Signal]:
    """Emit a Signal per series whose latest move is a shock (|z| ≥ 2)."""
    signals: list[Signal] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for display, series in fetch_all_series().items():
        if len(series) < 32:
            continue
        rets = series.pct_change(fill_method=None).dropna()
        if rets.empty:
            continue
        vol = rets.iloc[-31:-1].std()
        if not vol or pd.isna(vol):
            continue
        latest_ret = rets.iloc[-1]
        z = float(latest_ret / vol) if vol else 0.0
        if abs(z) < 2.0:
            continue
        severity = min(1.0, abs(z) / 5.0)
        signals.append(
            Signal(
                source="macro",
                category="macro",
                title=f"{display}: z={z:+.1f} (level {float(series.iloc[-1]):.2f})",
                severity=severity,
                timestamp_utc=now_iso,
                payload={
                    "series":        display,
                    "zscore":        z,
                    "latest_level":  float(series.iloc[-1]),
                },
            )
        )
    return signals
