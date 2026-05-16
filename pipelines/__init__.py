"""Data pipelines for Global Supply Chain Pulse.

Each module exposes a `fetch()` function returning a list of Signal dicts.
All pipelines are cache-aware via the shared requests-cache session.
"""

from .base import Signal, get_session, regions_for_point  # noqa: F401
