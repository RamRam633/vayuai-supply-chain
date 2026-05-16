"""
Executive summary block - local rule-based or Claude-generated, rendered in
the light theme card.
"""

from __future__ import annotations

import streamlit as st

from analytics.summarizer import build_brief, claude_executive_summary, local_summary
import config
from .theme import BG, BORDER, ACCENT, ACCENT_DEEP, TEXT, TEXT_MUTED


def render_exec_summary() -> None:
    brief = build_brief()
    using_claude = config.ENABLE_CLAUDE_SUMMARY and bool(config.ANTHROPIC_API_KEY)
    badge_text  = "Claude-generated" if using_claude else "Rule-based"
    badge_bg    = ACCENT + "1A"
    badge_color = ACCENT_DEEP

    st.markdown(
        f"<div style='display:inline-block;padding:3px 10px;border-radius:999px;"
        f"background:{badge_bg};color:{badge_color};font-size:0.7rem;"
        f"border:1px solid {ACCENT}55;margin-bottom:10px;"
        f"text-transform:uppercase;letter-spacing:0.05em;font-weight:600'>"
        f"{badge_text}</div>",
        unsafe_allow_html=True,
    )

    text = claude_executive_summary(brief) if using_claude else local_summary(brief)
    st.markdown(
        f"<div style='font-size:0.95rem;line-height:1.5;color:{TEXT}'>{text}</div>",
        unsafe_allow_html=True,
    )

    with st.expander("Show structured brief"):
        st.json(brief, expanded=False)
