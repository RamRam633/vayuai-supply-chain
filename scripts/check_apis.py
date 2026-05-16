"""Exercise every pipeline's fetch() and report which APIs are live."""
from __future__ import annotations

import importlib
import time
import traceback

import config

PIPELINES = [
    "pipelines.commodities",
    "pipelines.flights",
    "pipelines.geopolitics",
    "pipelines.macro",
    "pipelines.natural_events",
    "pipelines.news",
    "pipelines.ports_vessels",
    "pipelines.seismic",
    "pipelines.tropical",
    "pipelines.weather",
]


def run_one(modname: str) -> tuple[str, int | None, str | None, float]:
    t0 = time.time()
    try:
        mod = importlib.import_module(modname)
        out = mod.fetch()
        elapsed = time.time() - t0
        n = len(out) if hasattr(out, "__len__") else None
        return modname, n, None, elapsed
    except Exception as e:
        elapsed = time.time() - t0
        tb = traceback.format_exc(limit=2)
        return modname, None, f"{type(e).__name__}: {e}\n{tb}", elapsed


def main() -> None:
    print("=" * 78)
    print("API connectivity check — exercising each pipeline.fetch()")
    print("=" * 78)
    print(f"AISSTREAM_API_KEY:   {'SET' if config.AISSTREAM_API_KEY else 'EMPTY'}")
    print(f"FRED_API_KEY:        {'SET' if config.FRED_API_KEY else 'EMPTY'}")
    print(f"ANTHROPIC_API_KEY:   {'SET' if config.ANTHROPIC_API_KEY else 'EMPTY'}")
    print(f"NOAA_USER_AGENT:     {config.NOAA_USER_AGENT!r}")
    print("-" * 78)

    results = []
    for name in PIPELINES:
        print(f"[..] {name} ...", flush=True)
        r = run_one(name)
        results.append(r)
        modname, n, err, secs = r
        if err is None:
            status = "OK" if (n or 0) > 0 else "EMPTY"
            print(f"[{status:>5}] {modname}: {n} signals  ({secs:.2f}s)")
        else:
            print(f"[FAIL ] {modname}: ({secs:.2f}s)")
            print("        " + err.replace("\n", "\n        "))
        print()

    print("=" * 78)
    print("Summary")
    print("=" * 78)
    ok = [r for r in results if r[2] is None and (r[1] or 0) > 0]
    empty = [r for r in results if r[2] is None and (r[1] or 0) == 0]
    fail = [r for r in results if r[2] is not None]
    print(f"OK:    {len(ok)} / {len(results)}")
    print(f"EMPTY: {len(empty)}  -> {[r[0] for r in empty]}")
    print(f"FAIL:  {len(fail)}   -> {[r[0] for r in fail]}")


if __name__ == "__main__":
    main()
