"""
Commodity prices — resilient three-tier fetch:

   1. yfinance bulk download                (often blocked → moves on)
   2. Stooq daily CSV                       (geo-blocked from some IPs → moves on)
   3. Datahub.io curated CSV mirrors        (works without keys, recent data
                                             for WTI / Brent / Natural Gas / Gold)
   4. Synthetic deterministic fallback      (clearly flagged so the dashboard
                                             is never blank)

When any column ends up synthetic, we write `data/commodities_demo.marker`
so the UI can surface a "demo data" banner.
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
# Stooq mapping. Endpoint is daily CSV: https://stooq.com/q/d/l/?s=cl.f&i=d
# --------------------------------------------------------------------------- #
_STOOQ_CODES = {
    "Crude Oil (WTI)":     "cl.f",
    "Brent Crude":         "bz.f",
    "Natural Gas":         "ng.f",
    "Wheat":               "zw.f",
    "Corn":                "zc.f",
    "Soybeans":            "zs.f",
    "Copper":              "hg.f",
    "Gold":                "gc.f",
    "Silver":              "si.f",
}

# Datahub.io curated CSV mirrors — Date,Price columns.
_DATAHUB_CSVS = {
    "Crude Oil (WTI)": "https://datahub.io/core/oil-prices/r/wti-daily.csv",
    "Brent Crude":     "https://datahub.io/core/oil-prices/r/brent-daily.csv",
    "Natural Gas":     "https://datahub.io/core/natural-gas/r/daily.csv",
    "Gold":            "https://datahub.io/core/gold-prices/r/monthly.csv",
}

# Approximate 2026 levels used as the anchor for synthetic fallback series.
_SYNTH_ANCHORS = {
    "Crude Oil (WTI)":  101.0,
    "Brent Crude":      105.0,
    "Natural Gas":        2.85,
    "Wheat":              5.40,
    "Corn":               4.25,
    "Soybeans":          11.80,
    "Copper":             6.10,
    "Gold":            2850.0,
    "Silver":            32.0,
    "Aluminum":        2500.0,
}
_SYNTH_VOL = {
    "Crude Oil (WTI)":  0.014,
    "Brent Crude":      0.013,
    "Natural Gas":      0.030,
    "Wheat":            0.018,
    "Corn":             0.018,
    "Soybeans":         0.016,
    "Copper":           0.018,
    "Gold":             0.010,
    "Silver":           0.020,
    "Aluminum":         0.015,
}


# --------------------------------------------------------------------------- #
# Demo marker helpers
# --------------------------------------------------------------------------- #
def is_demo_prices() -> bool:
    return DEMO_MARKER.exists()


def _mark_demo(columns: list[str]) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "synthetic_columns": columns,
    }
    try:
        DEMO_MARKER.write_text(json.dumps(payload))
    except Exception:
        pass


def _clear_demo() -> None:
    try:
        DEMO_MARKER.unlink(missing_ok=True)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Source #1 — yfinance
# --------------------------------------------------------------------------- #
def _yfinance_close_frame(period: str = "180d") -> pd.DataFrame:
    import yfinance as yf

    tickers = list(config.COMMODITIES.values())
    try:
        raw = yf.download(
            tickers, period=period, interval="1d",
            progress=False, group_by="ticker", auto_adjust=False,
        )
    except Exception as e:
        print(f"[yfinance] download failed: {e}")
        return pd.DataFrame()

    closes: dict[str, pd.Series] = {}
    for name, ticker in config.COMMODITIES.items():
        try:
            series = raw[ticker]["Close"].dropna()
            if not series.empty:
                closes[name] = series
        except Exception:
            continue
    return pd.DataFrame(closes).dropna(how="all")


# --------------------------------------------------------------------------- #
# Source #2 — Stooq
# --------------------------------------------------------------------------- #
def _stooq_close(stooq_code: str) -> pd.Series:
    session = get_session(expire_after=config.CACHE_TTL["yfinance"])
    url = f"https://stooq.com/q/d/l/?s={stooq_code}&i=d"
    try:
        r = session.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        })
        r.raise_for_status()
        text = r.text or ""
        if not text or "Date" not in text.split("\n", 1)[0]:
            return pd.Series(dtype=float)
        df = pd.read_csv(StringIO(text))
        if df.empty or "Close" not in df.columns:
            return pd.Series(dtype=float)
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"]).set_index("Date").sort_index()
        return df["Close"].astype(float)
    except Exception as e:
        print(f"[stooq] {stooq_code} failed: {e}")
        return pd.Series(dtype=float)


# --------------------------------------------------------------------------- #
# Source #3 — Datahub.io curated CSV mirrors
# --------------------------------------------------------------------------- #
def _datahub_close(url: str) -> pd.Series:
    session = get_session(expire_after=config.CACHE_TTL["yfinance"])
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
# Source #4 — synthetic deterministic fallback (clearly labeled demo)
# --------------------------------------------------------------------------- #
def _synthesize(name: str, days: int = 180, seed: int = 7) -> pd.Series:
    """Deterministic random-walk series anchored at a plausible recent level."""
    anchor = _SYNTH_ANCHORS.get(name, 100.0)
    sigma  = _SYNTH_VOL.get(name, 0.015)
    rng = random.Random(hash((name, seed)) & 0xFFFF_FFFF)

    today = datetime.now(timezone.utc).date()
    dates = [today - timedelta(days=days - i) for i in range(days)]
    # Build series ending close to the anchor: simulate forward then re-anchor.
    levels = [1.0]
    for _ in range(days - 1):
        # Mean-revert lightly toward 1.0 so the walk doesn't drift off.
        prev = levels[-1]
        step = rng.gauss(0, sigma) + (1.0 - prev) * 0.01
        levels.append(prev * math.exp(step))
    # Scale so the final level == anchor.
    scale = anchor / levels[-1]
    values = [round(l * scale, 4) for l in levels]
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

    df = _yfinance_close_frame(period=period)

    # Tier 2: Stooq for anything yfinance missed.
    for name, stooq_code in _STOOQ_CODES.items():
        if name in df.columns and not df[name].dropna().empty:
            continue
        s = _stooq_close(stooq_code)
        if not s.empty:
            df = df.reindex(df.index.union(s.index))
            df[name] = s.reindex(df.index)

    # Tier 3: Datahub.io curated mirrors.
    for name, url in _DATAHUB_CSVS.items():
        if name in df.columns and not df[name].dropna().empty:
            continue
        s = _datahub_close(url)
        if not s.empty:
            # Take last 365 days so the chart isn't dominated by decades.
            s = s.tail(365)
            df = df.reindex(df.index.union(s.index))
            df[name] = s.reindex(df.index)

    # Tier 4: synthetic for any name still missing.
    synthetic: list[str] = []
    for name in config.COMMODITIES.keys():
        if name not in df.columns or df.get(name, pd.Series(dtype=float)).dropna().empty:
            synth = _synthesize(name)
            df = df.reindex(df.index.union(synth.index))
            df[name] = synth.reindex(df.index)
            synthetic.append(name)

    if synthetic:
        _mark_demo(synthetic)
    else:
        _clear_demo()

    # Snap to a clean daily index — Datahub mirrors only carry business days,
    # synthetic series carry every day. Without this step weekend rows show up
    # as NaN for the real series and create visible gaps in line charts.
    df = df.sort_index().dropna(how="all")
    if not df.empty:
        # Normalise to dates (drop time-of-day) so duplicate same-day rows merge.
        df.index = pd.to_datetime(df.index).normalize()
        df = df.groupby(level=0).last()
        full_idx = pd.date_range(df.index.min(), df.index.max(), freq="D")
        df = df.reindex(full_idx).ffill(limit=4)
        df.index.name = "Date"

    try:
        df.to_parquet(cache_file)
    except Exception as e:
        print(f"[commodities] cache write failed: {e}")
    return df


def fetch() -> list[Signal]:
    """Emit shock signals (|z| >= 2 on 1d return vs trailing 20d stdev)."""
    df = fetch_prices()
    if df.empty or len(df) < 21:
        return []

    returns = df.pct_change(fill_method=None)
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
        latest_price = float(df[name].iloc[-1]) if name in df.columns else 0.0
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
