"""
Shared theme - vayuai.ai dark + gold + serif.

Aligned with the main vayuai.ai site:
    background  → deep charcoal #0b0a09
    text        → warm cream    #f5f1e8
    accent      → gold          #d4af37
    headings    → Fraunces (serif, optical)
    body        → Inter
    labels/mono → JetBrains Mono

Every component imports from here so the look stays consistent across
the overview and every drilldown page.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st


# --------------------------------------------------------------------------- #
# Color tokens
# --------------------------------------------------------------------------- #
BG               = "#0b0a09"   # page background - deep charcoal
BG_MUTED         = "#131110"   # elevated surface (cards, sidebar)
BG_SUBTLE        = "#181513"   # hover / striped row tint
BORDER           = "#2a2520"   # hairline divider
BORDER_STRONG    = "#3a3530"   # button outline, focus rings

TEXT             = "#f5f1e8"   # warm cream - primary text
TEXT_MUTED       = "#b9b2a2"   # secondary text, captions
TEXT_SUBTLE      = "#807868"   # tertiary text, eyebrow labels

ACCENT           = "#d4af37"   # gold - primary accent
ACCENT_DEEP      = "#e7c764"   # soft gold - hover, highlights

CRITICAL         = "#e85a5a"   # vivid red - severity ≥ 0.7 / down dots
WARNING          = "#e07a35"   # ember - severity ≥ 0.4 / partial dots
INFO             = "#7b9aba"   # cool blue
SUCCESS          = "#84a17d"   # muted sage - live dots
PURPLE           = "#c499e8"

# Category color tokens - brightened for dark-background readability.
CATEGORY_COLOR = {
    "geopolitical": "#e85a5a",
    "weather":      "#7b9aba",
    "tropical":     "#e69aba",
    "seismic":      "#e8a050",
    "volcanic":     "#f07a4e",
    "natural":      "#a8c08a",
    "freight":      "#6cb5c9",
    "commodity":    "#c499e8",
    "macro":        "#9aa5b5",
    "flight":       "#7ecbe0",
    "news":         "#d4d4cf",
}

CATEGORY_COLOR_RGBA = {
    "geopolitical": [232,  90,  90, 220],
    "weather":      [123, 154, 186, 220],
    "tropical":     [230, 154, 186, 220],
    "seismic":      [232, 160,  80, 220],
    "volcanic":     [240, 122,  78, 220],
    "natural":      [168, 192, 138, 220],
    "freight":      [108, 181, 201, 220],
    "commodity":    [196, 153, 232, 220],
    "macro":        [154, 165, 181, 200],
    "flight":       [126, 203, 224, 220],
    "news":         [212, 212, 207, 200],
}

# Discrete plot palette - tuned for 5-10 series on dark bg, gold-led.
PALETTE = [
    "#d4af37",   # gold
    "#e7c764",   # soft gold
    "#7b9aba",   # cool blue
    "#e07a35",   # ember
    "#a8c08a",   # sage
    "#c499e8",   # purple
    "#e85a5a",   # red
    "#6cb5c9",   # cyan
    "#e69aba",   # pink
    "#b9b2a2",   # warm gray
]


# --------------------------------------------------------------------------- #
# Plotly helper - dark template + cream text + gold leading color
# --------------------------------------------------------------------------- #
def apply_light(fig: go.Figure, **overrides) -> go.Figure:
    """Apply the vayuai dark theme to a Plotly Figure in place. Returns the fig.

    Name kept as `apply_light` for backwards compatibility with every
    page; the body is now the dark/gold theme.
    """
    layout = dict(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            color=TEXT,
            family="Inter, ui-sans-serif, -apple-system, system-ui, sans-serif",
            size=12,
        ),
        colorway=PALETTE,
        margin=dict(l=10, r=10, t=10, b=10),
        hoverlabel=dict(
            bgcolor=BG_MUTED,
            font_size=12,
            font_color=TEXT,
            font_family="Inter, ui-sans-serif, system-ui, sans-serif",
            bordercolor=BORDER,
        ),
        xaxis=dict(
            gridcolor=BORDER, zerolinecolor=BORDER,
            tickfont=dict(color=TEXT_MUTED),
            linecolor=BORDER,
        ),
        yaxis=dict(
            gridcolor=BORDER, zerolinecolor=BORDER,
            tickfont=dict(color=TEXT_MUTED),
            linecolor=BORDER,
        ),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            font=dict(color=TEXT_MUTED),
        ),
    )
    layout.update(overrides)
    fig.update_layout(**layout)
    return fig


# --------------------------------------------------------------------------- #
# Global CSS - vayuai dark, Fraunces+Inter+JetBrains Mono
# --------------------------------------------------------------------------- #
_FONTS_LINK = (
    "https://fonts.googleapis.com/css2?"
    "family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&"
    "family=Inter:wght@400;500;600;700&"
    "family=JetBrains+Mono:wght@400;500;600&display=swap"
)

# Single style block. Streamlit's markdown sanitizer drops <link> tags,
# which would leak the subsequent <style> into the page as text. Importing
# fonts via @import inside <style> keeps everything in one trusted block.
GLOBAL_CSS = f"""
<style>
  @import url('{_FONTS_LINK}');

  /* Layout. Hide Streamlit's top chrome (Deploy button, hamburger,
     status indicator) entirely so the brand topbar can own the top of
     the page. Without this the topbar gets clipped behind the chrome. */
  header[data-testid="stHeader"],
  div[data-testid="stToolbar"],
  div[data-testid="stDecoration"],
  div[data-testid="stStatusWidget"] {{
    display: none !important;
  }}
  .block-container {{
    padding-top: 1.5rem;
    padding-bottom: 2rem;
    max-width: 1500px;
  }}
  [data-testid="stMainBlockContainer"],
  section.main > div.block-container {{
    padding-top: 1.5rem !important;
  }}
  .stApp {{ background: {BG}; }}
  html, body, [class*="stApp"] {{
    font-family: Inter, ui-sans-serif, -apple-system, system-ui, sans-serif !important;
    color: {TEXT};
    background-color: {BG};
  }}

  /* --- Typography ------------------------------------------------------ */
  h1, h2, h3, h4, h5 {{
    color: {TEXT} !important;
    font-family: Fraunces, ui-serif, Georgia, serif !important;
    font-weight: 600;
    letter-spacing: -0.015em;
  }}
  h1 {{ font-weight: 700; letter-spacing: -0.022em; }}
  h2, h3 {{ font-weight: 600; }}
  p, label, .stMarkdown {{ color: {TEXT}; }}

  /* Streamlit's <hr> divider */
  hr {{
    border: 0;
    border-top: 1px solid {BORDER};
    margin: 1.4rem 0;
  }}

  /* --- Sidebar --------------------------------------------------------- */
  [data-testid="stSidebar"] {{
    background-color: {BG_MUTED};
    border-right: 1px solid {BORDER};
  }}
  [data-testid="stSidebar"] .stMarkdown,
  [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] p,
  [data-testid="stSidebar"] span {{
    color: {TEXT};
  }}
  [data-testid="stSidebar"] h3,
  [data-testid="stSidebar"] h4 {{
    font-family: Inter, sans-serif !important;
    font-size: 0.88rem !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: {TEXT_SUBTLE} !important;
    font-weight: 600;
  }}

  /* --- Metric cards ---------------------------------------------------- */
  [data-testid="stMetric"] {{
    background: {BG_MUTED};
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 16px 18px;
  }}
  [data-testid="stMetricLabel"] {{
    color: {TEXT_SUBTLE} !important;
    font-size: 0.72rem !important;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    font-family: 'JetBrains Mono', ui-monospace, monospace !important;
    font-weight: 500;
  }}
  [data-testid="stMetricValue"] {{
    color: {TEXT} !important;
    font-family: Fraunces, ui-serif, serif !important;
    font-weight: 600 !important;
    font-size: 1.9rem !important;
  }}
  [data-testid="stMetricDelta"] {{
    color: {TEXT_MUTED} !important;
  }}

  /* --- Buttons --------------------------------------------------------- */
  .stButton > button {{
    background: {BG_MUTED};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 999px;
    font-family: Inter, sans-serif;
    font-weight: 500;
    padding: 6px 16px;
    transition: all 0.15s ease;
  }}
  .stButton > button:hover {{
    background: {BG_SUBTLE};
    border-color: {ACCENT}55;
    color: {ACCENT_DEEP};
  }}
  .stButton > button p,
  .stButton > button div {{
    color: inherit !important;
    font-weight: 500;
    margin: 0;
  }}
  /* Primary button - gold pill */
  .stButton > button[kind="primary"] {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: #1a1612;
  }}
  .stButton > button[kind="primary"] p,
  .stButton > button[kind="primary"] div {{
    color: #1a1612 !important;
    font-weight: 600;
  }}
  .stButton > button[kind="primary"]:hover {{
    background: {ACCENT_DEEP};
    border-color: {ACCENT_DEEP};
    color: #1a1612;
  }}

  /* --- Inputs ---------------------------------------------------------- */
  .stSelectbox > div > div,
  .stMultiSelect > div > div,
  .stTextInput > div > div > input {{
    background: {BG_MUTED} !important;
    border: 1px solid {BORDER} !important;
    color: {TEXT} !important;
    border-radius: 10px !important;
  }}
  .stTextInput input,
  .stSelectbox div,
  .stMultiSelect span,
  .stSlider {{
    color: {TEXT} !important;
  }}

  /* --- Dataframes / tables -------------------------------------------- */
  div[data-testid="stDataFrame"] {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    background: {BG_MUTED};
  }}

  /* --- Expanders ------------------------------------------------------- */
  details {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    background: {BG_MUTED};
  }}
  details > summary {{ color: {TEXT}; }}

  /* --- Tabs ------------------------------------------------------------ */
  div[data-baseweb="tab-list"] {{
    border-bottom: 1px solid {BORDER};
    gap: 4px;
  }}
  div[data-baseweb="tab"] {{
    color: {TEXT_MUTED} !important;
    font-family: Inter, sans-serif !important;
  }}
  div[data-baseweb="tab"][aria-selected="true"] {{
    color: {ACCENT_DEEP} !important;
  }}
  div[data-baseweb="tab-highlight"] {{
    background: {ACCENT} !important;
  }}

  /* --- Plotly chart container ----------------------------------------- */
  .stPlotlyChart {{
    background: transparent;
    border-radius: 12px;
  }}

  /* --- Streamlit chrome ----------------------------------------------- */
  #MainMenu {{ visibility: hidden; }}
  footer    {{ visibility: hidden; }}
  header    {{ background: {BG} !important; }}
  [data-testid="stToolbar"] {{ background: {BG}; }}

  /* --- Custom card utility -------------------------------------------- */
  .pulse-card {{
    background: {BG_MUTED};
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 18px;
    margin-bottom: 12px;
  }}
  .pulse-card-muted {{
    background: {BG_SUBTLE};
  }}

  /* --- Pill / tag utility --------------------------------------------- */
  .pulse-pill {{
    display: inline-block;
    padding: 3px 12px;
    border-radius: 999px;
    background: {BG_MUTED};
    color: {TEXT_MUTED};
    font-size: 0.72rem;
    font-weight: 500;
    border: 1px solid {BORDER};
    margin-right: 4px;
    font-family: 'JetBrains Mono', ui-monospace, monospace;
    letter-spacing: 0.02em;
  }}
  .pulse-pill-accent {{
    background: {ACCENT}1F;
    color: {ACCENT_DEEP};
    border-color: {ACCENT}66;
  }}
  .pulse-pill-critical {{
    background: {CRITICAL}1F;
    color: {CRITICAL};
    border-color: {CRITICAL}55;
  }}

  /* --- Code blocks ----------------------------------------------------- */
  code, pre, [data-testid="stCodeBlock"] {{
    font-family: 'JetBrains Mono', ui-monospace, monospace !important;
    background: {BG_MUTED} !important;
    color: {TEXT} !important;
    border-radius: 8px;
    border: 1px solid {BORDER};
  }}

  /* --- Caption ---------------------------------------------------------*/
  .stCaption, [data-testid="stCaptionContainer"] {{
    color: {TEXT_MUTED} !important;
  }}

  /* --- Alerts (st.info / st.warning / st.error) ----------------------- */
  div[data-baseweb="notification"] {{
    background: {BG_MUTED} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 12px !important;
    color: {TEXT} !important;
  }}
  div[data-baseweb="notification"] * {{
    color: {TEXT} !important;
  }}
</style>
"""


def inject_global_css() -> None:
    """Call once at the top of every page."""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# pydeck helpers - dark CARTO basemap
# --------------------------------------------------------------------------- #
def map_kwargs() -> dict:
    """Shared pydeck Deck() kwargs for a dark CARTO basemap.

    No Mapbox token required; pydeck's "carto" provider serves the
    dark-matter tile set for free.
    """
    return {
        "map_provider": "carto",
        "map_style":    "dark",
    }
