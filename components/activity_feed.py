"""
Global activity feed — vertical list of recent signals, severity-ranked.
Light-theme cards with a category-colored left rail.
"""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from .theme import (
    CATEGORY_COLOR, BG, BG_MUTED, BORDER, TEXT, TEXT_MUTED,
    CRITICAL, WARNING, ACCENT_DEEP,
)

CATEGORY_LABEL = {
    "geopolitical": "geopolitical",
    "weather":      "weather",
    "tropical":     "tropical",
    "seismic":      "seismic",
    "volcanic":     "volcanic",
    "natural":      "natural",
    "commodity":    "market",
    "freight":      "freight",
    "macro":        "macro",
    "flight":       "aviation",
}


def _humanize(ts: str) -> str:
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - t
        mins = int(delta.total_seconds() // 60)
        if mins < 1:
            return "just now"
        if mins < 60:
            return f"{mins}m ago"
        hours = mins // 60
        if hours < 24:
            return f"{hours}h ago"
        return f"{hours // 24}d ago"
    except Exception:
        return ts[:16] if ts else ""


def _sev_dot(sev: float) -> str:
    if sev >= 0.7:
        return CRITICAL
    if sev >= 0.4:
        return WARNING
    return ACCENT_DEEP


def render_activity_feed(signals: list[dict], limit: int = 40) -> None:
    if not signals:
        st.info(
            "No recent signals match the filters. "
            "Try widening the time window or clearing categories."
        )
        return

    ranked = sorted(
        signals,
        key=lambda s: (s.get("timestamp_utc", ""), s.get("severity", 0)),
        reverse=True,
    )[:limit]

    for s in ranked:
        cat = s.get("category", "")
        rail_color = CATEGORY_COLOR.get(cat, "#9CA3AF")
        sev = float(s.get("severity", 0.0))
        sev_color = _sev_dot(sev)
        title = s.get("title", "")
        url = s.get("url")
        when = _humanize(s.get("timestamp_utc", ""))
        title_md = f"<a href='{url}' style='color:{TEXT};text-decoration:none'>{title}</a>" if url else title

        st.markdown(
            f"""
            <div style='border:1px solid {BORDER};border-left:3px solid {rail_color};
                        background:{BG};border-radius:10px;padding:10px 14px;
                        margin-bottom:8px'>
              <div style='display:flex;align-items:center;justify-content:space-between;
                          font-size:0.72rem;color:{TEXT_MUTED};margin-bottom:4px'>
                <div>
                  <span style='font-weight:600;color:{rail_color};text-transform:uppercase;
                               letter-spacing:0.04em'>{CATEGORY_LABEL.get(cat, cat)}</span>
                  · <span>{s.get('source', '')}</span>
                  · <span>{when}</span>
                </div>
                <div style='display:flex;align-items:center;gap:6px'>
                  <span style='width:8px;height:8px;border-radius:50%;
                               background:{sev_color};display:inline-block'></span>
                  <span style='font-family:ui-monospace,monospace;font-size:0.72rem;
                               color:{TEXT_MUTED}'>sev {sev:.2f}</span>
                </div>
              </div>
              <div style='font-size:0.94rem;color:{TEXT};line-height:1.35'>
                {title_md}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
