"""
Listen on AISStream WebSocket for N seconds and dump positions to SQLite.

Run as a background cron job, e.g. every 5 minutes:
    */5 * * * * python scripts/refresh_ais.py

On Render: set up a separate background worker, or a cron job add-on.
Locally: run it in another terminal while Streamlit is up.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make the project root importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import websockets
import config
from pipelines.ports_vessels import write_snapshot

LISTEN_SECONDS = 60  # collect for ~1 minute then exit


async def collect():
    if not config.AISSTREAM_API_KEY:
        print("[ais] AISSTREAM_API_KEY missing - skipping.")
        return

    # Subscribe to a worldwide bounding box. AISStream lets you scope geos;
    # we sample globally and trim later.
    subscribe_msg = {
        "APIKey": config.AISSTREAM_API_KEY,
        "BoundingBoxes": [[[-90, -180], [90, 180]]],
        "FilterMessageTypes": ["PositionReport"],
    }

    uri = "wss://stream.aisstream.io/v0/stream"
    buffer: dict[int, dict] = {}

    try:
        async with websockets.connect(uri, ping_interval=20, max_size=2 ** 22) as ws:
            await ws.send(json.dumps(subscribe_msg))
            loop = asyncio.get_event_loop()
            start = loop.time()
            while loop.time() - start < LISTEN_SECONDS:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5)
                except asyncio.TimeoutError:
                    continue
                msg = json.loads(raw)
                meta = msg.get("MetaData", {}) or {}
                pos = (msg.get("Message", {}) or {}).get("PositionReport", {}) or {}
                mmsi = meta.get("MMSI")
                lat = pos.get("Latitude")
                lon = pos.get("Longitude")
                if not (mmsi and lat is not None and lon is not None):
                    continue
                buffer[int(mmsi)] = {
                    "mmsi": int(mmsi),
                    "lat": float(lat),
                    "lon": float(lon),
                    "sog": pos.get("Sog"),
                    "cog": pos.get("Cog"),
                    "ship_type": meta.get("ShipType"),
                    "name": meta.get("ShipName"),
                    "ts_utc": datetime.now(timezone.utc).isoformat(),
                }
    except Exception as e:
        print(f"[ais] socket error: {e}")

    if buffer:
        n = write_snapshot(list(buffer.values()))
        print(f"[ais] snapshot updated. total vessels in DB: {n}")
    else:
        print("[ais] no positions collected (network? key? quota?)")


if __name__ == "__main__":
    asyncio.run(collect())
