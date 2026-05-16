"""
World map: ports, chokepoints, airports, events, plus optional live flight
and vessel overlays. Light CARTO Positron basemap, light-theme palette.
"""

from __future__ import annotations

import pandas as pd
import pydeck as pdk
import streamlit as st

import config
from .theme import (
    CATEGORY_COLOR_RGBA, BORDER, TEXT_MUTED, TEXT, map_kwargs,
)


def _airports_layer() -> pdk.Layer:
    ap = pd.DataFrame(getattr(config, "MAJOR_AIRPORTS", []))
    if ap.empty:
        ap = pd.DataFrame(columns=["lat", "lon", "name", "iata"])
    return pdk.Layer(
        "ScatterplotLayer",
        data=ap,
        get_position="[lon, lat]",
        get_radius=22000,
        get_fill_color=[14, 116, 144, 220],
        pickable=True,
        stroked=True,
        get_line_color=[255, 255, 255, 230],
        line_width_min_pixels=1,
    )


def _flights_layer(flights: list[dict]) -> pdk.Layer:
    df = pd.DataFrame(flights) if flights else pd.DataFrame(columns=["lat", "lon"])
    return pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position="[lon, lat]",
        get_radius=7000,
        get_fill_color=[14, 116, 144, 150],
        opacity=0.55,
    )


def _vessels_layer(vessels: list[dict]) -> pdk.Layer:
    df = pd.DataFrame(vessels) if vessels else pd.DataFrame(columns=["lat", "lon"])
    return pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position="[lon, lat]",
        get_radius=10000,
        get_fill_color=[8, 145, 178, 130],
        opacity=0.55,
    )


def render_world_map(
    signals: list[dict],
    flights: list[dict] | None = None,
    vessels: list[dict] | None = None,
    show_airports: bool = True,
) -> None:
    """Render the headline map. Optional overlays for flights / vessels."""

    port_df = pd.DataFrame(config.MAJOR_PORTS)
    chokes  = pd.DataFrame(config.CHOKEPOINTS)

    geo_signals = [
        s for s in signals
        if s.get("lat") is not None and s.get("lon") is not None
    ]
    if geo_signals:
        ev_df = pd.DataFrame(geo_signals)
        ev_df["color"] = ev_df["category"].map(
            lambda c: CATEGORY_COLOR_RGBA.get(c, [156, 163, 175, 180])
        )
        ev_df["radius"] = (ev_df["severity"].astype(float) * 80_000 + 22_000).astype(int)
    else:
        ev_df = pd.DataFrame(columns=["lat", "lon", "color", "radius", "title", "category"])

    port_layer = pdk.Layer(
        "ScatterplotLayer",
        data=port_df,
        get_position="[lon, lat]",
        get_radius=32000,
        get_fill_color=[245, 158, 11, 200],
        pickable=True,
        stroked=True,
        get_line_color=[255, 255, 255, 230],
        line_width_min_pixels=1,
    )
    choke_layer = pdk.Layer(
        "ScatterplotLayer",
        data=chokes,
        get_position="[lon, lat]",
        get_radius=78000,
        get_fill_color=[234, 88, 12, 60],
        pickable=True,
        stroked=True,
        get_line_color=[234, 88, 12, 200],
        line_width_min_pixels=2,
    )
    event_layer = pdk.Layer(
        "ScatterplotLayer",
        data=ev_df,
        get_position="[lon, lat]",
        get_radius="radius",
        get_fill_color="color",
        pickable=True,
        opacity=0.55,
    )

    layers: list = [choke_layer]
    if vessels:
        layers.append(_vessels_layer(vessels))
    if flights:
        layers.append(_flights_layer(flights))
    layers.append(port_layer)
    if show_airports:
        layers.append(_airports_layer())
    layers.append(event_layer)

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(latitude=20, longitude=20, zoom=1.2),
        tooltip={"text": "{title}\n{name}\n{category}"},
        **map_kwargs(),
    )
    st.pydeck_chart(deck, use_container_width=True)

    # Legend
    legend = [
        ("Ports",          "#F59E0B"),
        ("Airports",       "#0E7490"),
        ("Chokepoints",    "#EA580C"),
        ("Geopolitical",   "#DC2626"),
        ("Weather",        "#2563EB"),
        ("Tropical",       "#DB2777"),
        ("Seismic",        "#D97706"),
        ("Volcanic",       "#EA580C"),
        ("Natural",        "#16A34A"),
        ("Commodity",      "#7C3AED"),
        ("Flights",        "#0E7490"),
        ("Vessels",        "#0891B2"),
    ]
    cols = st.columns(len(legend))
    for col, (label, color) in zip(cols, legend):
        col.markdown(
            f"<div style='display:flex;align-items:center;gap:6px'>"
            f"<span style='width:9px;height:9px;border-radius:50%;"
            f"background:{color};display:inline-block;"
            f"border:1px solid {BORDER}'></span>"
            f"<span style='font-size:0.74em;color:{TEXT_MUTED}'>{label}</span></div>",
            unsafe_allow_html=True,
        )
