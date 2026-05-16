"""
Cold-start bootstrap for Render free tier.

Render free tier has no persistent disk and no cron. signals.json is empty
after every container start and never auto-refreshes. This module gives
the live deploy a soft scheduler that lives inside the web service:

    1. On the first Streamlit page render, kick off a background refresh
       loop that re-runs every pipeline every REFRESH_INTERVAL_MINUTES.
       The first iteration always runs, populating signals.json within
       ~30s of the container booting.

    2. If AISSTREAM_API_KEY is set, spawn an AIS WebSocket listener that
       collects ~60s of position reports, sleeps, repeats - so the Ships
       page shows real vessel positions instead of the demo snapshot.

Threads are daemons; they exit with the process. Streamlit re-runs the
page script on every interaction, so ensure_bootstrap() is idempotent -
the module-level lock guarantees we only spawn the workers once per
process.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import config


# How stale signals.json can be before the loop refreshes it.
STALE_AFTER_MINUTES = max(5, config.REFRESH_INTERVAL_MINUTES)

# How long the AIS worker sleeps between WebSocket collect cycles.
AIS_RECOLLECT_MINUTES = 15


_LOCK = threading.Lock()
_STATE: dict[str, object] = {
    "bootstrap_started":    False,
    "refresh_thread":       None,
    "ais_thread":           None,
    "last_refresh_ok_at":   0.0,
    "last_refresh_error":   "",
    "in_flight_refresh":    False,
    "ais_active":           False,
    "ais_last_ok_at":       0.0,
}


# --------------------------------------------------------------------------- #
# Inspectors used by the UI
# --------------------------------------------------------------------------- #
def _signals_path() -> Path:
    return Path(config.DATA_DIR) / "signals.json"


def signals_age_seconds() -> float | None:
    p = _signals_path()
    if not p.exists():
        return None
    return time.time() - p.stat().st_mtime


def _is_signals_stale() -> bool:
    age = signals_age_seconds()
    return age is None or age > STALE_AFTER_MINUTES * 60


def is_refreshing() -> bool:
    return bool(_STATE.get("in_flight_refresh"))


def state_snapshot() -> dict:
    """Read-only snapshot of bootstrap state for the API-status footer."""
    return {
        "bootstrap_started":  bool(_STATE["bootstrap_started"]),
        "refreshing":         is_refreshing(),
        "last_refresh_ok_at": float(_STATE["last_refresh_ok_at"] or 0.0),
        "last_refresh_error": str(_STATE["last_refresh_error"] or ""),
        "ais_active":         bool(_STATE["ais_active"]),
        "ais_last_ok_at":     float(_STATE["ais_last_ok_at"] or 0.0),
        "signals_age_s":      signals_age_seconds(),
    }


# --------------------------------------------------------------------------- #
# Workers
# --------------------------------------------------------------------------- #
def _refresh_once() -> None:
    """Run every pipeline once. Writes signals.json + history. Idempotent."""
    _STATE["in_flight_refresh"] = True
    try:
        from scripts.refresh_data import refresh_all
        refresh_all()
        _STATE["last_refresh_ok_at"] = time.time()
        _STATE["last_refresh_error"] = ""
    except Exception as e:
        _STATE["last_refresh_error"] = f"{type(e).__name__}: {e}"
        print(f"[bootstrap] refresh failed: {e}")
    finally:
        _STATE["in_flight_refresh"] = False


def _refresh_worker_loop() -> None:
    """First iteration always refreshes; subsequent iterations gate on staleness."""
    # First iteration: always run, even if signals.json exists (cold start
    # may have served a stale snapshot from cache).
    _refresh_once()

    interval_s = max(5, config.REFRESH_INTERVAL_MINUTES) * 60
    # Check every 5 minutes max so the next interval kicks in promptly
    # after each cycle finishes.
    check_every_s = min(interval_s, 5 * 60)
    while True:
        time.sleep(check_every_s)
        try:
            if _is_signals_stale():
                _refresh_once()
        except Exception as e:
            print(f"[bootstrap] refresh loop tick failed: {e}")


def _ais_worker_loop() -> None:
    """Periodic AIS WebSocket listener. Runs forever in a daemon thread."""
    if not config.AISSTREAM_API_KEY:
        return

    import asyncio
    try:
        from scripts.refresh_ais import collect
    except Exception as e:
        print(f"[bootstrap] AIS import failed: {e}")
        return

    while True:
        try:
            asyncio.run(collect())
            _STATE["ais_active"] = True
            _STATE["ais_last_ok_at"] = time.time()
        except Exception as e:
            print(f"[bootstrap] AIS collect cycle failed: {e}")
        time.sleep(AIS_RECOLLECT_MINUTES * 60)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def ensure_bootstrap() -> None:
    """Spawn refresh + AIS threads once per process. Safe to call every page load."""
    with _LOCK:
        if _STATE["bootstrap_started"]:
            return
        _STATE["bootstrap_started"] = True

        t = threading.Thread(
            target=_refresh_worker_loop,
            name="pulse-refresh-loop",
            daemon=True,
        )
        _STATE["refresh_thread"] = t
        t.start()

        if config.AISSTREAM_API_KEY:
            ais = threading.Thread(
                target=_ais_worker_loop,
                name="pulse-ais-loop",
                daemon=True,
            )
            _STATE["ais_thread"] = ais
            ais.start()
