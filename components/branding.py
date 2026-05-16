"""
VayuAI branding for the Supply Chain Pulse dashboard.

Two helpers:
    render_brand_header(sidebar=True)
        Logo + 'Vayu' / gold 'AI' wordmark, with 'Supply Chain Pulse' as
        the product sub-mark and a small link back to vayuai.ai. Goes at
        the top of the sidebar on every page.

    render_brand_footer()
        Bottom-of-page strip matching the main vayuai.ai footer: logo,
        product attribution, link home. Renders below the API status
        footer.

The logo is loaded from assets/brand/logo-64.png and inlined as a
base64 data URI so it survives across reruns without needing
Streamlit's static-serving feature enabled.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import streamlit as st

from .theme import (
    BG, BG_MUTED, BORDER, TEXT, TEXT_MUTED, TEXT_SUBTLE,
    ACCENT, ACCENT_DEEP,
)


VAYUAI_URL  = "https://vayuai.ai"
VAYUAI_NAME = "VayuAI"
PRODUCT_NAME = "Supply Chain Pulse"
TAGLINE     = "AI with purpose. Automation with consciousness."

_REPO_ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH    = _REPO_ROOT / "assets" / "brand" / "logo.png"
LOGO_PATH_64 = _REPO_ROOT / "assets" / "brand" / "logo-64.png"


@lru_cache(maxsize=1)
def _logo_data_uri_64() -> str:
    """Base64-encoded data URI for the 64px logo. Cached once per process."""
    if not LOGO_PATH_64.exists():
        return ""
    try:
        b = LOGO_PATH_64.read_bytes()
        return "data:image/png;base64," + base64.b64encode(b).decode("ascii")
    except Exception:
        return ""


def _wordmark_html(size_rem: float = 1.2) -> str:
    """The 'Vayu' + gold 'AI' wordmark, Fraunces serif."""
    return (
        f"<span style='font-family:Fraunces, ui-serif, serif;"
        f"font-size:{size_rem}rem;font-weight:600;letter-spacing:-0.01em;"
        f"color:{TEXT}'>"
        f"Vayu<span style='color:{ACCENT}'>AI</span></span>"
    )


# --------------------------------------------------------------------------- #
# Sidebar header - render once per page near the top of the sidebar
# --------------------------------------------------------------------------- #
def render_brand_header() -> None:
    """Render the VayuAI brand strip at the top of the sidebar."""
    logo = _logo_data_uri_64()
    logo_html = (
        f"<img src='{logo}' style='width:36px;height:36px;border-radius:8px;"
        f"flex-shrink:0' alt='VayuAI'/>"
        if logo else ""
    )

    st.sidebar.markdown(
        f"""
        <a href='{VAYUAI_URL}' target='_blank' style='text-decoration:none;
           display:block;margin:-4px 0 14px 0'>
          <div style='display:flex;align-items:center;gap:12px;
                      padding:10px 12px;border:1px solid {BORDER};
                      border-radius:12px;background:{BG};
                      transition:border-color 0.15s ease'>
            {logo_html}
            <div style='display:flex;flex-direction:column;line-height:1.15'>
              {_wordmark_html(1.15)}
              <span style='font-size:0.68rem;color:{TEXT_SUBTLE};
                           font-family:JetBrains Mono, ui-monospace, monospace;
                           text-transform:uppercase;letter-spacing:0.08em;
                           margin-top:2px'>
                {PRODUCT_NAME}
              </span>
            </div>
          </div>
        </a>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Page footer - bottom-of-page brand strip
# --------------------------------------------------------------------------- #
def render_brand_footer() -> None:
    """Bottom-of-page brand strip. Render below the API status footer."""
    logo = _logo_data_uri_64()
    logo_html = (
        f"<img src='{logo}' style='width:28px;height:28px;border-radius:6px;"
        f"flex-shrink:0' alt='VayuAI'/>"
        if logo else ""
    )
    year = datetime.now(timezone.utc).year

    st.markdown(
        f"""
        <div style='margin-top:32px;padding:24px 0;
                    border-top:1px solid {BORDER}'>
          <div style='display:flex;align-items:center;justify-content:space-between;
                      flex-wrap:wrap;gap:18px'>
            <a href='{VAYUAI_URL}' target='_blank' style='text-decoration:none;
               display:flex;align-items:center;gap:12px'>
              {logo_html}
              <div style='display:flex;flex-direction:column;line-height:1.2'>
                {_wordmark_html(1.05)}
                <span style='font-size:0.72rem;color:{TEXT_SUBTLE};
                             font-family:JetBrains Mono, ui-monospace, monospace;
                             text-transform:uppercase;letter-spacing:0.07em;
                             margin-top:1px'>
                  {PRODUCT_NAME}
                </span>
              </div>
            </a>

            <div style='display:flex;align-items:center;gap:18px;
                        font-size:0.78rem;color:{TEXT_MUTED}'>
              <a href='{VAYUAI_URL}' target='_blank'
                 style='color:{TEXT_MUTED};text-decoration:none;
                        transition:color 0.15s ease'>
                vayuai.ai
              </a>
              <a href='{VAYUAI_URL}/work' target='_blank'
                 style='color:{TEXT_MUTED};text-decoration:none'>
                Work
              </a>
              <a href='{VAYUAI_URL}/contact' target='_blank'
                 style='color:{TEXT_MUTED};text-decoration:none'>
                Contact
              </a>
            </div>
          </div>

          <div style='margin-top:18px;font-size:0.72rem;color:{TEXT_SUBTLE};
                      font-family:JetBrains Mono, ui-monospace, monospace;
                      letter-spacing:0.02em'>
            &copy; {year} Vivek &middot; {VAYUAI_NAME} &middot;
            {TAGLINE}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
