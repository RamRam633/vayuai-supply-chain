"""Smoke tests: pipelines must import and the Signal contract must hold.

These don't hit external APIs - they verify the wiring. Run real fetchers
with `python scripts/refresh_data.py`.
"""

from __future__ import annotations

import importlib

import pytest


PIPELINES = [
    "pipelines.geopolitics",
    "pipelines.seismic",
    "pipelines.weather",
    "pipelines.commodities",
    "pipelines.macro",
    "pipelines.ports_vessels",
]


@pytest.mark.parametrize("modname", PIPELINES)
def test_pipeline_imports(modname: str) -> None:
    mod = importlib.import_module(modname)
    assert hasattr(mod, "fetch"), f"{modname} must expose fetch()"


def test_signal_contract() -> None:
    from pipelines.base import Signal
    s = Signal(source="x", category="weather", title="t", severity=0.5,
               lat=10, lon=20)
    d = s.to_dict()
    for k in ("source", "category", "title", "severity", "lat", "lon",
             "region", "timestamp_utc", "url", "payload"):
        assert k in d


def test_risk_score_empty() -> None:
    from analytics.risk_score import compute_regional_risk
    out = compute_regional_risk([])
    # All regions present, all scores zero.
    assert len(out) > 0
    assert all(v["score"] == 0.0 for v in out.values())


def test_risk_score_geo_signal() -> None:
    from analytics.risk_score import compute_regional_risk
    sig = [{
        "source": "test", "category": "geopolitical", "title": "war",
        "severity": 0.9, "lat": 50.4, "lon": 30.5,  # Kyiv -> Europe
        "region": None,
        "timestamp_utc": "2099-01-01T00:00:00+00:00",
        "url": None, "payload": {}
    }]
    out = compute_regional_risk(sig, lookback_hours=24 * 365 * 100)
    assert out["Europe"]["score"] > 0
