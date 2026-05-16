"""
Run every pipeline once and persist Signals to disk.

Usable two ways:

  * As a script:
        python scripts/refresh_data.py
    Suitable for a local cron job or one-off warm-up.

  * As an import:
        from scripts.refresh_data import refresh_all
        refresh_all()
    The Streamlit web service calls this from pipelines.bootstrap so the
    free-tier deploy gets an in-process scheduler.

Streamlit reads the on-disk snapshot, so the dashboard never blocks on
slow external APIs.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make the project root importable when run as a standalone script.
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


def refresh_all() -> dict:
    """Run every pipeline. Write signals.json + score history. Return summary."""
    all_signals: list[dict] = []
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
        "summary":      summary,
        "signals":      all_signals,
    }
    target = Path(config.DATA_DIR) / "signals.json"
    target.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {len(all_signals)} signals to {target}")

    # Append regional scores to history parquet for 'biggest movers' panel.
    try:
        from analytics.risk_score import compute_regional_risk
        from analytics.history import append_scores
        regional = compute_regional_risk(all_signals)
        append_scores(regional)
    except Exception as e:
        print(f"[history] append failed: {e}")

    return out


def main() -> None:
    refresh_all()


if __name__ == "__main__":
    main()
