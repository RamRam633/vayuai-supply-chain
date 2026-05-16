"""
Shared light theme — fonts, colors, plotly + pydeck helpers.

Inspired by 2026-era OpenAI surfaces: off-white background, near-black text,
hairline borders, lots of whitespace, a single restrained accent (#10A37F).
Every component imports from here so the look stays consistent.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st


# --------------------------------------------------------------------------- #
# Color tokens
# --------------------------------------------------------------------------- #
BG               = "#FFFFFF"
BG_MUTED         = "#F7F7F8"
BG_SUBTLE        = "#FAFAFA"
BORDER           = "#E5E7EB"
BORDER_STRONG    = "#D1D5DB"
TEXT             = "#0E0E0E"
TEXT_MUTED       = "#6B7280"
TEXT_SUBTLE      = "#9CA3AF"

ACCENT           = "#10A37F"   # OpenAI green-ish
ACCENT_DEEP      = "#0E7A60"

CRITICAL         = "#DC2626"
WARNING          = "#D97706"
INFO             = "#2563EB"
SUCCESS          = "#16A34A"
PURPLE           = "#7C3AED"

# Category color tokens — used by the map and tables.
CATEGORY_COLOR = {
    "geopolitical": "#DC2626",
    "weather":      "#2563EB",
    "tropical":     "#DB2777",
    "seismic":      "#D97706",
    "volcanic":     "#EA580C",
    "natural":      "#16A34A",
    "freight":      "#0891B2",
    "commodity":    "#7C3AED",
    "macro":        "#475569",
    "flight":       "#0E7490",
    "news":         "#1F2937",
}

CATEGORY_COLOR_RGBA = {
    "geopolitical": [220,  38,  38, 200],
    "weather":      [ 37,  99, 235, 200],
    "tropical":     [219,  39, 119, 220],
    "seismic":      [217, 119,   6, 200],
    "volcanic":     [234,  88,  12, 220],
    "natural":      [ 22, 163,  74, 200],
    "freight":      [  8, 145, 178, 200],
    "commodity":    [124,  58, 237, 200],
    "macro":        [ 71,  85, 105, 180],
    "flight":       [ 14, 116, 144, 200],
    "news":         [ 31,  41,  55, 180],
}

# Discrete plot palette — order tuned for 5-8 series.
PALETTE = [
    "#0E0E0E", "#10A37F", "#2563EB", "#D97706", "#DC2626",
    "#7C3AED", "#0891B2", "#65A30D", "#DB2777", "#6B7280",
]


# --------------------------------------------------------------------------- #
# Plotly helper
# --------------------------------------------------------------------------- #
def apply_light(fig: go.Figure, **overrides) -> go.Figure:
    """Apply the light theme to a Plotly Figure in place. Returns the figure."""
    layout = dict(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            color=TEXT,
            family="ui-sans-serif, -apple-system, system-ui, sans-serif",
            size=12,
        ),
        colorway=PALETTE,
        margin=dict(l=10, r=10, t=10, b=10),
        hoverlabel=dict(
            bgcolor="#FFFFFF",
            font_size=12,
            font_family="ui-sans-serif, -apple-system, system-ui, sans-serif",
            bordercolor=BORDER,
        ),
        xaxis=dict(
            gridcolor=BORDER, zerolinecolor=BORDER,
            tickfont=dict(color=TEXT_MUTED),
        ),
        yaxis=dict(
            gridcolor=BORDER, zerolinecolor=BORDER,
            tickfont=dict(color=TEXT_MUTED),
        ),
    )
    layout.update(overrides)
    fig.update_layout(**layout)
    return fig


# --------------------------------------------------------------------------- #
# Global CSS — apply once per page via inject_global_css()
# --------------------------------------------------------------------------- #
GLOBAL_CSS = f"""
<style>
  /* Layout */
  .block-container {{
    padding-top: 1.0rem;
    padding-bottom: 2rem;
    max-width: 1500px;
  }}

  /* Typography */
  html, body, [class*="stApp"] {{
    font-family: ui-sans-serif, -apple-system, system-ui, "Segoe UI",
                 Roboto, sans-serif !important;
    color: {TEXT};
    background-color: {BG};
  }}
  h1, h2, h3, h4, h5 {{
    color: {TEXT};
    letter-spacing: -0.01em;
    font-weight: 600;
  }}
  h1 {{ font-weight: 650; }}
  p, label, .stMarkdown {{ color: {TEXT}; }}

  /* Sidebar */
  [data-testid="stSidebar"] {{
    background-color: {BG_MUTED};
    border-right: 1px solid {BORDER};
  }}
  [data-testid="stSidebar"] .stMarkdown,
  [data-testid="stSidebar"] label {{
    color: {TEXT};
  }}

  /* Metric cards */
  [data-testid="stMetric"] {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 14px 16px;
  }}
  [data-testid="stMetricLabel"] {{
    color: {TEXT_MUTED} !important;
    font-size: 0.78rem !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}
  [data-testid="stMetricValue"] {{
    color: {TEXT} !important;
    font-weight: 600 !important;
  }}

  /* Buttons — light, OpenAI-style. Streamlit wraps the label in <p>; we
     force the <p> color explicitly so the global p{{color:...}} rule loses. */
  .stButton > button {{
    background: {BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    font-weight: 500;
    padding: 6px 14px;
    transition: all 0.15s ease;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  }}
  .stButton > button:hover {{
    background: {BG_MUTED};
    border-color: {BORDER_STRONG};
  }}
  .stButton > button p,
  .stButton > button div {{
    color: {TEXT} !important;
    font-weight: 500;
    margin: 0;
  }}
  /* Optional "primary" button via st.button(..., type="primary") */
  .stButton > button[kind="primary"] {{
    background: {TEXT};
    border-color: {TEXT};
  }}
  .stButton > button[kind="primary"] p,
  .stButton > button[kind="primary"] div {{
    color: #FFFFFF !important;
  }}
  .stButton > button[kind="primary"]:hover {{
    background: {ACCENT_DEEP};
    border-color: {ACCENT_DEEP};
  }}

  /* Dataframes / tables */
  div[data-testid="stDataFrame"] {{
    border: 1px solid {BORDER};
    border-radius: 10px;
  }}

  /* Expanders */
  details {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    background: {BG};
  }}

  /* Tabs */
  div[data-baseweb="tab-list"] {{
    border-bottom: 1px solid {BORDER};
  }}

  /* Plotly chart container — no extra border */
  .stPlotlyChart {{
    background: {BG};
    border-radius: 12px;
  }}

  /* Hide Streamlit chrome */
  #MainMenu {{ visibility: hidden; }}
  footer {{ visibility: hidden; }}
  header {{ background: {BG} !important; }}

  /* Custom card utility */
  .pulse-card {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 12px;
  }}
  .pulse-card-muted {{
    background: {BG_MUTED};
  }}

  /* Pill / tag utility */
  .pulse-pill {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    background: {BG_MUTED};
    color: {TEXT_MUTED};
    font-size: 0.72rem;
    font-weight: 500;
    border: 1px solid {BORDER};
    margin-right: 4px;
  }}
  .pulse-pill-accent {{
    background: {ACCENT}22;
    color: {ACCENT_DEEP};
    border-color: {ACCENT}55;
  }}
  .pulse-pill-critical {{
    background: {CRITICAL}11;
    color: {CRITICAL};
    border-color: {CRITICAL}44;
  }}
</style>
"""


def inject_global_css() -> None:
    """Call once at the top of every page."""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# pydeck helpers
# --------------------------------------------------------------------------- #
def map_kwargs() -> dict:
    """Shared pydeck Deck() kwargs that give a clean light basemap.

    Uses CARTO's free Positron tiles via pydeck's "carto" map_provider —
    no Mapbox token required.
    """
    return {
        "map_provider": "carto",
        "map_style": "light",
    }
