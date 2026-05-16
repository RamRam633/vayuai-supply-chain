"""
Run every pipeline once and persist Signals to disk.

Use as a cron job to keep the cache warm:
    */15 * * * * python scripts/refresh_data.py

Streamlit reads the on-disk snapshot, so the dashboard never blocks on
slow external APIs. This is what makes a free-tier deploy feel snappy.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from pipelines import (
    geopolitics,
    seismic,
    weather,
    commodities,
    macro,
    ports_vessels,
    flights,
    natural_events,
    tropical,
    news,
)


PIPELINES = {
    "geopolitics":      geopolitics.fetch,
    "seismic":          seismic.fetch,
    "weather":          weather.fetch,
    "commodities":      commodities.fetch,
    "macro":            macro.fetch,
    "ports_vessels":    ports_vessels.fetch,
    "flights":          flights.fetch,
    "natural_events":   natural_events.fetch,
    "tropical":         tropical.fetch,
    "news":             news.fetch,
}


def main() -> None:
    all_signals = []
    summary: dict[str, int | str] = {}
    for name, fn in PIPELINES.items():
        try:
            sigs = fn() or []
        except Exception as e:
            print(f"[{name}] FAILED: {e}")
            sigs = []
            summary[f"{name}_error"] = str(e)
        all_signals.extend(s.to_dict() for s in sigs)
        summary[name] = len(sigs)
        print(f"[{name}] {len(sigs)} signals")

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "signals": all_signals,
    }
    target = Path(config.DATA_DIR) / "signals.json"
    target.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {len(all_signals)} signals to {target}")

    # Append regional scores to the history parquet so the UI can show
    # 'biggest movers vs last refresh' and per-region trend lines.
    try:
        from analytics.risk_score import compute_regional_risk
        from analytics.history import append_scores
        regional = compute_regional_risk(all_signals)
        append_scores(regional)
    except Exception as e:
        print(f"[history] append failed: {e}")


if __name__ == "__main__":
    main()
