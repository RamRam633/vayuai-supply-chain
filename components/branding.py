"""
VayuAI branding helpers for the Supply Chain Pulse dashboard.

Lessons from the first iteration: do NOT embed PNGs as base64 data URIs
inside `st.markdown(unsafe_allow_html=True)` blocks. Streamlit's
markdown sanitizer chokes on extremely long attribute values, which
made the brand header / footer fall apart in two ways:

    * the inline <img> would fail to render and its alt text "VayuAI"
      would show next to the wordmark "VayuAI" (the doubled brand
      problem)
    * after the broken image the parser couldn't find its way back
      to HTML mode, so the rest of the footer would serialize as raw
      `<div>` text on the page

This module avoids both by:

    1. Using Streamlit's native `st.logo()` for the corner logo. It
       gets the official upper-left slot and a sidebar treatment for
       free, and Streamlit handles the asset serving.
    2. Keeping every other brand element pure text. Wordmark, nav,
       footer - all small HTML blocks that the markdown sanitizer
       handles cleanly.

Public surface:
    setup_brand()
        Calls st.logo() once. Call right after st.set_page_config on
        every page.
    render_brand_topbar(section=None)
        Horizontal strip at the top of the main content area.
    render_brand_header()
        Caption-style brand block at the top of the sidebar.
    render_brand_footer()
        Bottom-of-page strip.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from .theme import (
    BG, BG_MUTED, BORDER, TEXT, TEXT_MUTED, TEXT_SUBTLE,
    ACCENT, ACCENT_DEEP,
)


VAYUAI_URL   = "https://vayuai.ai"
VAYUAI_NAME  = "VayuAI"
PRODUCT_NAME = "Supply Chain Pulse"
TAGLINE      = "AI with purpose. Automation with consciousness."

_REPO_ROOT   = Path(__file__).resolve().parent.parent
LOGO_PATH    = _REPO_ROOT / "assets" / "brand" / "logo.png"
LOGO_PATH_64 = _REPO_ROOT / "assets" / "brand" / "logo-64.png"


# --------------------------------------------------------------------------- #
# Streamlit-native logo slot - put the logo in the official corner
# --------------------------------------------------------------------------- #
_BRAND_SETUP_DONE = False


def setup_brand() -> None:
    """Register the VayuAI logo with Streamlit's native upper-left slot.

    Idempotent within a page run. Call right after st.set_page_config().
    Falls back silently if st.logo() isn't available (Streamlit < 1.31).
    """
    global _BRAND_SETUP_DONE
    if _BRAND_SETUP_DONE:
        return
    if not LOGO_PATH.exists():
        _BRAND_SETUP_DONE = True
        return
    try:
        # st.logo signature varies slightly across Streamlit versions; pass
        # only the args every supported version accepts.
        st.logo(str(LOGO_PATH), link=VAYUAI_URL)
    except Exception:
        pass
    _BRAND_SETUP_DONE = True


# --------------------------------------------------------------------------- #
# Wordmark
# --------------------------------------------------------------------------- #
def _wordmark_html(size_rem: float = 1.2, weight: int = 600) -> str:
    """The 'Vayu' + gold 'AI' wordmark, Fraunces serif. Text only."""
    return (
        f"<span style=\"font-family:Fraunces,ui-serif,Georgia,serif;"
        f"font-size:{size_rem}rem;font-weight:{weight};"
        f"letter-spacing:-0.015em;color:{TEXT}\">"
        f"Vayu<span style=\"color:{ACCENT}\">AI</span></span>"
    )


# --------------------------------------------------------------------------- #
# Top brand bar
# --------------------------------------------------------------------------- #
def render_brand_topbar(section: str | None = None) -> None:
    """Horizontal brand strip at the top of the main content area."""

    section_html = ""
    if section:
        section_html = (
            f"<span style=\"color:{TEXT_SUBTLE};margin:0 8px\">/</span>"
            f"<span style=\"font-family:Fraunces,ui-serif,serif;"
            f"font-size:0.95rem;color:{TEXT};font-weight:500\">"
            f"{section}</span>"
        )

    st.markdown(
        f"""<div style="display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;gap:14px;padding:8px 4px 14px 4px;margin-bottom:18px;border-bottom:1px solid {BORDER}">
<a href="{VAYUAI_URL}" target="_blank" style="text-decoration:none;display:inline-flex;align-items:baseline;gap:10px">
{_wordmark_html(1.3, 600)}
<span style="color:{TEXT_SUBTLE};font-weight:300">|</span>
<span style="font-family:'JetBrains Mono',ui-monospace,monospace;font-size:0.72rem;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:0.08em">{PRODUCT_NAME}</span>
{section_html}
</a>
<div style="display:flex;align-items:center;gap:14px;font-size:0.8rem">
<a href="{VAYUAI_URL}/work" target="_blank" style="color:{TEXT_MUTED};text-decoration:none">Work</a>
<a href="{VAYUAI_URL}/writing" target="_blank" style="color:{TEXT_MUTED};text-decoration:none">Writing</a>
<a href="{VAYUAI_URL}/contact" target="_blank" style="color:{TEXT_MUTED};text-decoration:none">Contact</a>
<a href="{VAYUAI_URL}" target="_blank" style="padding:5px 14px;border-radius:999px;border:1px solid {ACCENT}55;background:{ACCENT}1A;color:{ACCENT_DEEP};text-decoration:none;font-weight:500">vayuai.ai</a>
</div>
</div>""",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Sidebar brand caption - text only (logo is rendered by st.logo)
# --------------------------------------------------------------------------- #
def render_brand_header() -> None:
    """Caption-style brand block at the top of the sidebar. Text only."""
    st.sidebar.markdown(
        f"""<div style="margin:-4px 0 14px 0;padding:12px 14px;border:1px solid {BORDER};border-radius:12px;background:{BG}">
<a href="{VAYUAI_URL}" target="_blank" style="text-decoration:none;display:block">
{_wordmark_html(1.2, 600)}
<div style="font-family:'JetBrains Mono',ui-monospace,monospace;font-size:0.68rem;color:{TEXT_SUBTLE};text-transform:uppercase;letter-spacing:0.08em;margin-top:3px">{PRODUCT_NAME}</div>
</a>
</div>""",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Bottom-of-page brand strip
# --------------------------------------------------------------------------- #
def render_brand_footer() -> None:
    """Bottom-of-page brand strip. Text only."""
    year = datetime.now(timezone.utc).year
    st.markdown(
        f"""<div style="margin-top:32px;padding-top:20px;border-top:1px solid {BORDER}">
<div style="display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;gap:14px">
<a href="{VAYUAI_URL}" target="_blank" style="text-decoration:none">
{_wordmark_html(1.1, 600)}
<span style="color:{TEXT_SUBTLE};margin:0 10px">&middot;</span>
<span style="color:{TEXT_MUTED};font-size:0.85rem">{PRODUCT_NAME}</span>
</a>
<div style="display:flex;align-items:center;gap:18px;font-size:0.78rem">
<a href="{VAYUAI_URL}" target="_blank" style="color:{TEXT_MUTED};text-decoration:none">vayuai.ai</a>
<a href="{VAYUAI_URL}/work" target="_blank" style="color:{TEXT_MUTED};text-decoration:none">Work</a>
<a href="{VAYUAI_URL}/contact" target="_blank" style="color:{TEXT_MUTED};text-decoration:none">Contact</a>
</div>
</div>
<div style="margin-top:14px;font-size:0.7rem;color:{TEXT_SUBTLE};font-family:'JetBrains Mono',ui-monospace,monospace;letter-spacing:0.02em">
&copy; {year} Vivek &middot; {VAYUAI_NAME} &middot; {TAGLINE}
</div>
</div>""",
        unsafe_allow_html=True,
    )
