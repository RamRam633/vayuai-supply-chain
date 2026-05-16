"""
Lightweight score-history log so we can show 'movers vs last refresh'.

Persistence is a single parquet at data/score_history.parquet. Each refresh
appends one row per region with the timestamp + composite score. Cheap, no
ceremony, easy to chart later for trend lines.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import config

HISTORY_PATH = Path(config.DATA_DIR) / "score_history.parquet"


def append_scores(regional: dict[str, dict]) -> None:
    """Write one row per region to the history parquet."""
    if not regional:
        return
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {"timestamp_utc": now, "region": r, "score": float(m.get("score", 0))}
        for r, m in regional.items()
    ]
    new = pd.DataFrame(rows)
    if HISTORY_PATH.exists():
        try:
            existing = pd.read_parquet(HISTORY_PATH)
            df = pd.concat([existing, new], ignore_index=True)
        except Exception:
            df = new
    else:
        df = new
    try:
        df.to_parquet(HISTORY_PATH)
    except Exception as e:
        print(f"[history] write failed: {e}")


def load_history() -> pd.DataFrame:
    if not HISTORY_PATH.exists():
        return pd.DataFrame(columns=["timestamp_utc", "region", "score"])
    try:
        return pd.read_parquet(HISTORY_PATH)
    except Exception:
        return pd.DataFrame(columns=["timestamp_utc", "region", "score"])


def score_deltas() -> dict[str, float]:
    """Per-region score delta: latest - previous snapshot.

    Returns empty dict if we don't have at least 2 snapshots yet.
    """
    df = load_history()
    if df.empty:
        return {}
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp_utc"]).sort_values("timestamp_utc")
    if df.empty:
        return {}
    snaps = df["timestamp_utc"].unique()
    if len(snaps) < 2:
        return {}
    latest_ts, prev_ts = snaps[-1], snaps[-2]
    latest = df[df["timestamp_utc"] == latest_ts].set_index("region")["score"]
    prev   = df[df["timestamp_utc"] == prev_ts].set_index("region")["score"]
    common = latest.index.intersection(prev.index)
    return {r: float(latest[r] - prev[r]) for r in common}


def region_trend(region: str, hours: int = 72) -> pd.DataFrame:
    """Time-series of one region's score for trend charts."""
    df = load_history()
    if df.empty:
        return df
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp_utc"])
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=hours)
    return df[(df["region"] == region) & (df["timestamp_utc"] >= cutoff)].sort_values(
        "timestamp_utc"
    )
