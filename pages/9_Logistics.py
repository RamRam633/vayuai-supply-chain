"""
Logistics page - live cargo airline operations.

Filters the global flights snapshot down to known cargo operators by
ICAO callsign prefix (FDX = FedEx, UPS = UPS Airlines, GTI = Atlas Air
and Amazon Air, CLX = Cargolux, CKS = Kalitta, BCS / DHK / DAE / BOX
= DHL ecosystem, and a few more in config.CARGO_OPERATORS).

What you get on this page:
    KPIs        - total cargo flights in the air, top operator, biggest
                  hub by cargo flights nearby, average altitude
    Carrier
    leaderboard - count per operator, brand color
    Map         - cargo-only positions, color-coded by carrier
    Hub mix     - cargo flights within 250km of each major cargo airport
    Roster      - sortable table of every cargo flight currently tracked

No new external API. Reuses the flights_snapshot.sqlite that the
bootstrap thread maintains via OpenSky / ADSB.lol.
"""

from __future__ import annotations

import math
from collections import Counter

import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st

import config
from pipelines.flights import (
    read_snapshot as read_flights, snapshot_source, AIRPORT_RADIUS_KM,
)
from components import (
    render_filters_sidebar, inject_global_css, apply_light, map_kwargs,
    render_api_status, render_cold_start_banner_if_needed,
    render_brand_header, render_brand_footer, LOGO_PATH,
    TEXT, TEXT_MUTED, BORDER, BG, BG_MUTED, ACCENT, ACCENT_DEEP, CRITICAL,
)
from pipelines import bootstrap


st.set_page_config(
    page_title="Logistics - Supply Chain Pulse",
    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else None,
    layout="wide",
)
inject_global_css()
bootstrap.ensure_bootstrap()
render_brand_header()

st.markdown("## Cargo airline operations")
st.markdown(
    f"<div style='color:{TEXT_MUTED};font-size:0.95rem;margin-bottom:14px;"
    f"max-width:780px;line-height:1.5'>"
    "Live positions of every cargo aircraft we can identify, filtered "
    "from the global flights snapshot by ICAO callsign prefix. Includes "
    "FedEx (FDX), UPS, Atlas Air / Amazon Air (GTI, ABX, ATN), the DHL "
    "family (DHK, BCS, DAE, BOX), Cargolux, Kalitta, Lufthansa Cargo, "
    "and others."
    "</div>",
    unsafe_allow_html=True,
)
render_cold_start_banner_if_needed()

# Filters are intentionally subordinate here. Render them so the sidebar
# stays consistent across pages, but Logistics doesn't currently apply them
# (the page is dedicated to cargo carriers).
_ = render_filters_sidebar()


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
flights = read_flights()


def _classify(callsign: str) -> str | None:
    """Return ICAO airline designator if the callsign matches a cargo operator."""
    if not callsign:
        return None
    cs = callsign.strip().upper()
    if len(cs) < 3:
        return None
    prefix = cs[:3]
    return prefix if prefix in config.CARGO_OPERATORS else None


# Tag every aircraft with its cargo carrier (or None)
tagged = []
for f in flights:
    op = _classify(f.get("callsign", ""))
    if op:
        rec = dict(f)
        rec["operator"] = op
        rec["operator_name"] = config.CARGO_OPERATORS[op]["name"]
        rec["operator_color"] = config.CARGO_OPERATORS[op]["color"]
        tagged.append(rec)

if not flights:
    st.info(
        "Live flights snapshot is empty. The bootstrap thread will populate "
        "it within a minute of the container booting; "
        "click **Refresh data now** in the sidebar to force a fetch sooner. "
        "If the snapshot stays empty in production, set OPENSKY_USERNAME and "
        "OPENSKY_PASSWORD in Render's Environment tab - that bypasses the "
        "anonymous quota that OpenSky enforces on shared cloud IPs. "
        "Free registration at https://opensky-network.org/."
    )
    render_api_status()
render_brand_footer()
    st.stop()


airborne = [f for f in tagged if not f.get("on_ground")]
src_label = snapshot_source() or "snapshot"


# --------------------------------------------------------------------------- #
# KPIs
# --------------------------------------------------------------------------- #
carrier_counts = Counter(f["operator"] for f in tagged)
top_op_code, top_op_n = (carrier_counts.most_common(1) + [(None, 0)])[0]
top_op_name = (
    config.CARGO_OPERATORS[top_op_code]["name"] if top_op_code else "-"
)

# Biggest hub for cargo right now
def _hav(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


HUB_RADIUS_KM = 250
hub_rows = []
for ap in config.MAJOR_AIRPORTS:
    n_near = sum(
        1 for f in airborne
        if _hav(ap["lat"], ap["lon"], f["lat"], f["lon"]) <= HUB_RADIUS_KM
    )
    hub_rows.append({
        "airport":     ap["name"],
        "iata":        ap.get("iata", ""),
        "cargo_rank":  ap.get("cargo_rank"),
        "lat":         ap["lat"],
        "lon":         ap["lon"],
        "cargo_near":  n_near,
    })
hub_df = pd.DataFrame(hub_rows).sort_values("cargo_near", ascending=False)
top_hub = hub_df.iloc[0]["airport"] if not hub_df.empty and hub_df.iloc[0]["cargo_near"] > 0 else "-"

avg_alt_m = (
    sum(f.get("baro_alt_m", 0) for f in airborne) / max(1, len(airborne))
)
avg_alt_ft = avg_alt_m / 0.3048

k1, k2, k3, k4 = st.columns(4)
k1.metric("Cargo flights tracked", f"{len(tagged):,}",
          help=f"Sourced from {src_label}.")
k2.metric("Top carrier", top_op_name, f"{top_op_n} aircraft")
k3.metric("Busiest hub", top_hub,
          help=f"Cargo flights within {HUB_RADIUS_KM} km.")
k4.metric("Avg cruise altitude", f"{avg_alt_ft/1000:.1f}k ft")


# --------------------------------------------------------------------------- #
# Carrier leaderboard
# --------------------------------------------------------------------------- #
st.markdown("### Carrier leaderboard")
st.caption(
    "Aircraft per operator currently in the snapshot. Atlas Air (GTI) "
    "also flies the Amazon Air fleet; ABX and ATN are the ATSG "
    "subsidiaries that fly the rest of Amazon Air."
)

leader = (
    pd.DataFrame(
        [{"code": c, "name": config.CARGO_OPERATORS[c]["name"],
          "aircraft": n,
          "color": config.CARGO_OPERATORS[c]["color"]}
         for c, n in carrier_counts.most_common()]
    )
)
if not leader.empty:
    fig_l = px.bar(
        leader.sort_values("aircraft", ascending=True),
        x="aircraft", y="name", orientation="h",
        color="name",
        color_discrete_map=dict(zip(leader["name"], leader["color"])),
    )
    apply_light(fig_l, height=380, showlegend=False,
                margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_l, use_container_width=True)


# --------------------------------------------------------------------------- #
# Map - cargo flights color-coded by carrier
# --------------------------------------------------------------------------- #
st.markdown("### Live cargo positions")
st.caption(
    "Dots color-coded by carrier. Concentric circles mark the major cargo "
    "airports - hovering shows how many tagged aircraft are within "
    f"{HUB_RADIUS_KM} km."
)


def _hex_to_rgba(hex_color: str, alpha: int = 220) -> list[int]:
    h = hex_color.lstrip("#")
    return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha]


ac_df = pd.DataFrame(airborne)
if not ac_df.empty:
    ac_df["color"] = ac_df["operator_color"].apply(_hex_to_rgba)

hub_layer = pdk.Layer(
    "ScatterplotLayer",
    data=hub_df.assign(radius=HUB_RADIUS_KM * 1000),
    get_position="[lon, lat]",
    get_radius="radius",
    get_fill_color=[212, 175, 55, 30],
    stroked=True,
    get_line_color=[212, 175, 55, 180],
    line_width_min_pixels=1,
    pickable=True,
)
ac_layer = pdk.Layer(
    "ScatterplotLayer",
    data=ac_df if not ac_df.empty else pd.DataFrame(columns=["lat", "lon"]),
    get_position="[lon, lat]",
    get_radius=14000,
    get_fill_color="color",
    opacity=0.85,
    pickable=True,
)
deck = pdk.Deck(
    initial_view_state=pdk.ViewState(latitude=30, longitude=10, zoom=1.4),
    layers=[hub_layer, ac_layer],
    tooltip={"text": "{operator_name} {callsign}\n{airport}"},
    **map_kwargs(),
)
st.pydeck_chart(deck, use_container_width=True)


# --------------------------------------------------------------------------- #
# Hub mix
# --------------------------------------------------------------------------- #
st.markdown("### Cargo flights near each major hub")
st.caption(
    f"Number of identified cargo aircraft within {HUB_RADIUS_KM} km of "
    "each major cargo airport. FedEx's Memphis (MEM) Superhub and UPS's "
    "Louisville (SDF) Worldport typically dominate."
)

hub_show = hub_df[hub_df["cargo_near"] > 0].head(25)
if hub_show.empty:
    st.info("No cargo aircraft near any monitored hub right now.")
else:
    fig_h = px.bar(
        hub_show.sort_values("cargo_near", ascending=True),
        x="cargo_near", y="airport", orientation="h",
        color="cargo_near",
        color_continuous_scale=[[0, "#3a3530"], [0.5, "#d4af37"], [1, "#e07a35"]],
    )
    apply_light(fig_h, height=460, coloraxis_showscale=False,
                margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_h, use_container_width=True)


# --------------------------------------------------------------------------- #
# Per-carrier cards
# --------------------------------------------------------------------------- #
st.markdown("### Per-carrier detail")

if not carrier_counts:
    st.info("No identified cargo carrier aircraft in the current snapshot.")
else:
    by_op: dict[str, list[dict]] = {}
    for f in tagged:
        by_op.setdefault(f["operator"], []).append(f)

    operators_sorted = [c for c, _ in carrier_counts.most_common()]
    cols_per_row = 3
    for i in range(0, len(operators_sorted), cols_per_row):
        chunk = operators_sorted[i:i + cols_per_row]
        cs = st.columns(cols_per_row)
        for c, op_code in zip(cs, chunk):
            op = config.CARGO_OPERATORS[op_code]
            flights_for_op = by_op.get(op_code, [])
            airborne_n = sum(1 for f in flights_for_op if not f.get("on_ground"))
            ground_n   = len(flights_for_op) - airborne_n
            avg_alt_op = (
                sum(f.get("baro_alt_m", 0) for f in flights_for_op if not f.get("on_ground"))
                / max(1, airborne_n)
            )
            avg_alt_op_ft = avg_alt_op / 0.3048
            c.markdown(
                f"""
                <div style='border:1px solid {BORDER};border-left:4px solid {op["color"]};
                            background:{BG_MUTED};border-radius:12px;padding:14px 16px;
                            margin-bottom:8px'>
                  <div style='font-size:0.7rem;color:{TEXT_MUTED};
                              text-transform:uppercase;letter-spacing:0.07em;
                              font-family:JetBrains Mono,monospace;
                              margin-bottom:4px'>
                    {op_code}
                  </div>
                  <div style='font-size:1.05rem;color:{TEXT};font-weight:600;
                              font-family:Fraunces,serif;margin-bottom:8px'>
                    {op["name"]}
                  </div>
                  <div style='font-size:0.84rem;color:{TEXT_MUTED};
                              line-height:1.5'>
                    <b style='color:{TEXT}'>{len(flights_for_op)}</b> total &nbsp;&middot;&nbsp;
                    <b style='color:{TEXT}'>{airborne_n}</b> in air &nbsp;&middot;&nbsp;
                    <b style='color:{TEXT}'>{ground_n}</b> ground<br>
                    avg altitude {avg_alt_op_ft/1000:.1f}k ft
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# --------------------------------------------------------------------------- #
# Roster table
# --------------------------------------------------------------------------- #
with st.expander("Full cargo aircraft roster"):
    if not tagged:
        st.info("No tagged aircraft.")
    else:
        roster = pd.DataFrame(tagged)
        roster = roster[[
            "operator", "operator_name", "callsign", "icao24",
            "lat", "lon", "baro_alt_m", "velocity_ms", "on_ground", "ts_utc",
        ]].copy()
        roster["altitude_ft"] = (roster["baro_alt_m"] / 0.3048).round(0)
        roster["speed_kt"]    = (roster["velocity_ms"] / 0.514444).round(0)
        roster = roster.drop(columns=["baro_alt_m", "velocity_ms"])
        roster.columns = [
            "Op", "Operator", "Callsign", "ICAO24",
            "Lat", "Lon", "On ground", "Snapshot",
            "Altitude (ft)", "Speed (kt)",
        ]
        st.dataframe(
            roster.sort_values(["Operator", "Callsign"]),
            use_container_width=True, hide_index=True,
        )


# --------------------------------------------------------------------------- #
# API health footer
# --------------------------------------------------------------------------- #
render_api_status()
render_brand_footer()
