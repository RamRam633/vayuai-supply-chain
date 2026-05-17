"""
Central configuration: regions, commodity universe, risk-engine weights, cache TTLs.

All tunables live here so non-engineers (or Claude) can adjust without touching code.
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
CACHE_DB_PATH = os.getenv("CACHE_DB_PATH", str(DATA_DIR / "cache.sqlite"))

# --------------------------------------------------------------------------- #
# API keys (loaded from .env)
# --------------------------------------------------------------------------- #
AISSTREAM_API_KEY = os.getenv("AISSTREAM_API_KEY", "")
FRED_API_KEY = os.getenv("FRED_API_KEY", "")
NOAA_USER_AGENT = os.getenv("NOAA_USER_AGENT", "SupplyChainPulse/0.1")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ENABLE_CLAUDE_SUMMARY = os.getenv("ENABLE_CLAUDE_SUMMARY", "false").lower() == "true"

# OpenSky Network - free, but the anonymous /states/all endpoint is rate-
# limited on shared cloud IPs. Setting a (free) account here bumps the
# daily quota and usually fixes "0 aircraft" on Render.
# Register: https://opensky-network.org/index.php?option=com_users&view=registration
OPENSKY_USERNAME = os.getenv("OPENSKY_USERNAME", "")
OPENSKY_PASSWORD = os.getenv("OPENSKY_PASSWORD", "")

REFRESH_INTERVAL_MINUTES = int(os.getenv("REFRESH_INTERVAL_MINUTES", "15"))

# --------------------------------------------------------------------------- #
# Regions - used for risk-score rollups and map filtering.
# Bounding boxes are (min_lon, min_lat, max_lon, max_lat).
# --------------------------------------------------------------------------- #
REGIONS = {
    "North America":   {"bbox": (-170, 15,  -50, 72),  "center": (-100,  40)},
    "South America":   {"bbox": ( -90, -56, -30,  13), "center": ( -60, -15)},
    "Europe":          {"bbox": ( -25, 35,   45, 71),  "center": (  15,  50)},
    "Middle East":     {"bbox": (  25, 12,   65, 42),  "center": (  45,  27)},
    "Africa":          {"bbox": ( -20, -35,  55, 38),  "center": (  20,   0)},
    "South Asia":      {"bbox": (  60,  5,   95, 38),  "center": (  78,  22)},
    "East Asia":       {"bbox": (  95, 18,  150, 55),  "center": ( 120,  35)},
    "Southeast Asia":  {"bbox": (  92, -11, 142, 23),  "center": ( 115,   5)},
    "Oceania":         {"bbox": ( 110, -50, 180, -10), "center": ( 140, -25)},
}

# --------------------------------------------------------------------------- #
# Critical chokepoints - these get special highlight on the map.
# Coordinates approximate, used for proximity-based event tagging.
# --------------------------------------------------------------------------- #
CHOKEPOINTS = [
    {"name": "Suez Canal",          "lat": 30.5,  "lon": 32.3,   "radius_km": 150},
    {"name": "Panama Canal",        "lat": 9.08,  "lon": -79.68, "radius_km": 150},
    {"name": "Strait of Hormuz",    "lat": 26.57, "lon": 56.25,  "radius_km": 150},
    {"name": "Strait of Malacca",   "lat": 2.5,   "lon": 101.3,  "radius_km": 200},
    {"name": "Bab el-Mandeb",       "lat": 12.58, "lon": 43.33,  "radius_km": 120},
    {"name": "Bosphorus",           "lat": 41.1,  "lon": 29.1,   "radius_km": 50},
    {"name": "Taiwan Strait",       "lat": 24.5,  "lon": 119.5,  "radius_km": 250},
    {"name": "English Channel",     "lat": 50.5,  "lon": 1.0,    "radius_km": 100},
]

# --------------------------------------------------------------------------- #
# Major cargo airports - used by the flights pipeline for proximity counts.
# Coordinates are airport reference points; cargo_rank ~= 2024 global ranking.
# --------------------------------------------------------------------------- #
MAJOR_AIRPORTS = [
    {"name": "Hong Kong (HKG)",      "iata": "HKG", "lat": 22.308, "lon": 113.918,  "cargo_rank": 1},
    {"name": "Memphis (MEM)",        "iata": "MEM", "lat": 35.042, "lon":  -89.977, "cargo_rank": 2},
    {"name": "Shanghai Pudong",      "iata": "PVG", "lat": 31.143, "lon": 121.805,  "cargo_rank": 3},
    {"name": "Anchorage (ANC)",      "iata": "ANC", "lat": 61.174, "lon": -149.998, "cargo_rank": 4},
    {"name": "Incheon (ICN)",        "iata": "ICN", "lat": 37.463, "lon": 126.440,  "cargo_rank": 5},
    {"name": "Louisville (SDF)",     "iata": "SDF", "lat": 38.174, "lon":  -85.736, "cargo_rank": 6},
    {"name": "Taipei (TPE)",         "iata": "TPE", "lat": 25.077, "lon": 121.233,  "cargo_rank": 7},
    {"name": "Doha (DOH)",           "iata": "DOH", "lat": 25.273, "lon":  51.608,  "cargo_rank": 8},
    {"name": "Frankfurt (FRA)",      "iata": "FRA", "lat": 50.033, "lon":   8.570,  "cargo_rank": 9},
    {"name": "Tokyo Narita (NRT)",   "iata": "NRT", "lat": 35.765, "lon": 140.386,  "cargo_rank": 10},
    {"name": "Los Angeles (LAX)",    "iata": "LAX", "lat": 33.942, "lon": -118.408, "cargo_rank": 11},
    {"name": "Singapore Changi",     "iata": "SIN", "lat":  1.360, "lon": 103.989,  "cargo_rank": 12},
    {"name": "Paris CDG",            "iata": "CDG", "lat": 49.010, "lon":   2.548,  "cargo_rank": 13},
    {"name": "Miami (MIA)",          "iata": "MIA", "lat": 25.793, "lon":  -80.291, "cargo_rank": 14},
    {"name": "Dubai (DXB)",          "iata": "DXB", "lat": 25.253, "lon":  55.365,  "cargo_rank": 15},
    {"name": "Chicago O'Hare",       "iata": "ORD", "lat": 41.978, "lon":  -87.905, "cargo_rank": 16},
    {"name": "Liege (LGG)",          "iata": "LGG", "lat": 50.638, "lon":   5.443,  "cargo_rank": 17},
    {"name": "Guangzhou Baiyun",     "iata": "CAN", "lat": 23.392, "lon": 113.299,  "cargo_rank": 18},
    {"name": "Amsterdam Schiphol",   "iata": "AMS", "lat": 52.309, "lon":   4.764,  "cargo_rank": 19},
    {"name": "Beijing Capital",      "iata": "PEK", "lat": 40.080, "lon": 116.585,  "cargo_rank": 20},
    {"name": "London Heathrow",      "iata": "LHR", "lat": 51.470, "lon":  -0.454,  "cargo_rank": 21},
    {"name": "Bangkok Suvarnabhumi", "iata": "BKK", "lat": 13.690, "lon": 100.750,  "cargo_rank": 22},
    {"name": "Mumbai (BOM)",         "iata": "BOM", "lat": 19.089, "lon":  72.866,  "cargo_rank": 23},
    {"name": "Sao Paulo Guarulhos",  "iata": "GRU", "lat": -23.43, "lon":  -46.479, "cargo_rank": 24},
    {"name": "Sydney (SYD)",         "iata": "SYD", "lat": -33.94, "lon": 151.175,  "cargo_rank": 25},
]


# --------------------------------------------------------------------------- #
# Major ports - used for activity feed and congestion proxy.
# --------------------------------------------------------------------------- #
MAJOR_PORTS = [
    {"name": "Shanghai",        "country": "CN", "lat": 31.23,  "lon": 121.47},
    {"name": "Singapore",       "country": "SG", "lat": 1.27,   "lon": 103.85},
    {"name": "Ningbo-Zhoushan", "country": "CN", "lat": 29.87,  "lon": 121.55},
    {"name": "Shenzhen",        "country": "CN", "lat": 22.54,  "lon": 114.06},
    {"name": "Busan",           "country": "KR", "lat": 35.10,  "lon": 129.04},
    {"name": "Rotterdam",       "country": "NL", "lat": 51.95,  "lon":   4.14},
    {"name": "Hamburg",         "country": "DE", "lat": 53.55,  "lon":   9.99},
    {"name": "Antwerp",         "country": "BE", "lat": 51.22,  "lon":   4.40},
    {"name": "Los Angeles",     "country": "US", "lat": 33.74,  "lon": -118.27},
    {"name": "Long Beach",      "country": "US", "lat": 33.77,  "lon": -118.20},
    {"name": "New York/NJ",     "country": "US", "lat": 40.67,  "lon":  -74.05},
    {"name": "Dubai (Jebel Ali)","country":"AE", "lat": 25.01,  "lon":  55.06},
    {"name": "Mumbai (JNPT)",   "country": "IN", "lat": 18.95,  "lon":  72.95},
    {"name": "Santos",          "country": "BR", "lat": -23.97, "lon": -46.33},
    {"name": "Durban",          "country": "ZA", "lat": -29.87, "lon":  31.04},
]

# --------------------------------------------------------------------------- #
# Cargo airline operators - ICAO airline designator (first three chars of
# the callsign) mapped to display name + brand color. Used by the Logistics
# page to filter the live flights snapshot down to cargo aircraft and to
# build per-carrier maps and leaderboards.
# Source: ICAO airline designators + each carrier's public IFR call signs.
# --------------------------------------------------------------------------- #
CARGO_OPERATORS = {
    "FDX": {"name": "FedEx Express",       "color": "#4d148c"},
    "UPS": {"name": "UPS Airlines",        "color": "#8b6914"},
    "GTI": {"name": "Atlas Air",           "color": "#1f4068"},  # also Amazon Air
    "ABX": {"name": "ABX Air",             "color": "#1976d2"},  # ATSG / Amazon Air
    "ATN": {"name": "Air Transport Intl",  "color": "#0288d1"},  # ATSG / Amazon Air
    "PAC": {"name": "Polar Air Cargo",     "color": "#3f51b5"},
    "CLX": {"name": "Cargolux",            "color": "#d32f2f"},
    "CKS": {"name": "Kalitta Air",         "color": "#7b1fa2"},
    "DHK": {"name": "DHL Air UK",          "color": "#ffc107"},
    "BCS": {"name": "DHL Air Belgium",     "color": "#ffb300"},
    "DAE": {"name": "DHL Aviation",        "color": "#fdd835"},
    "BOX": {"name": "AeroLogic",           "color": "#f57c00"},  # DHL/Lufthansa JV
    "GEC": {"name": "Lufthansa Cargo",     "color": "#ef6c00"},
    "CKK": {"name": "China Cargo",         "color": "#c62828"},
    "ABR": {"name": "ASL Airlines",        "color": "#00838f"},
    "WGN": {"name": "Western Global",      "color": "#388e3c"},
    "SQC": {"name": "Singapore Cargo",     "color": "#0277bd"},
    "KZR": {"name": "Air Astana Cargo",    "color": "#009688"},
    "ANX": {"name": "Air China Cargo",     "color": "#b71c1c"},
    "BIE": {"name": "BIA / Cargojet",      "color": "#5d4037"},
    "CJT": {"name": "Cargojet",            "color": "#5d4037"},
}


# --------------------------------------------------------------------------- #
# Commodity universe. Values are legacy yfinance tickers kept for reference;
# the live fetch in pipelines/commodities.py uses FRED IDs from its own map.
# --------------------------------------------------------------------------- #
COMMODITIES = {
    # Energy
    "Crude Oil (WTI)":     "CL=F",
    "Brent Crude":         "BZ=F",
    "Natural Gas":         "NG=F",
    # Precious metals
    "Gold":                "GC=F",
    "Silver":              "SI=F",
    # Industrial metals
    "Copper":              "HG=F",
    "Aluminum":            "ALI=F",
    "Nickel":              "FRED:PNICKUSDM",
    "Zinc":                "FRED:PZINCUSDM",
    "Iron Ore":            "FRED:PIORECRUSDM",
    "Uranium":             "FRED:PURANUSDM",
    # Grains
    "Wheat":               "ZW=F",
    "Corn":                "ZC=F",
    "Soybeans":            "ZS=F",
    # Soft agriculture
    "Coffee":              "FRED:PCOFFOTMUSDM",
    "Sugar":               "FRED:PSUGAISAUSDM",
    "Cocoa":               "FRED:PCOCOUSDM",
    "Cotton":              "FRED:PCOTTINDUSDM",
}

# Per-commodity category, used to colour-group the rebased chart and
# performance leaderboard.
COMMODITY_CATEGORY = {
    "Crude Oil (WTI)":  "Energy",
    "Brent Crude":      "Energy",
    "Natural Gas":      "Energy",
    "Gold":             "Precious metals",
    "Silver":           "Precious metals",
    "Copper":           "Industrial metals",
    "Aluminum":         "Industrial metals",
    "Nickel":           "Industrial metals",
    "Zinc":             "Industrial metals",
    "Iron Ore":         "Industrial metals",
    "Uranium":          "Industrial metals",
    "Wheat":            "Grains",
    "Corn":             "Grains",
    "Soybeans":         "Grains",
    "Coffee":           "Softs",
    "Sugar":            "Softs",
    "Cocoa":            "Softs",
    "Cotton":           "Softs",
}

# FRED series IDs we'll pull for the macro/freight panel.
FRED_SERIES = {
    "WTI Crude (USD/bbl)":         "DCOILWTICO",
    "Brent Crude (USD/bbl)":       "DCOILBRENTEU",
    "Natural Gas (Henry Hub)":     "DHHNGSP",
    "Global Supply Chain Pressure Index (GSCPI proxy)": "STLFSI4",  # proxy if GSCPI not in FRED
    "USD Trade-Weighted Index":    "DTWEXBGS",
    "10Y Treasury Yield":          "DGS10",
}

# --------------------------------------------------------------------------- #
# Risk-engine weights (sum doesn't need to == 1; normalized internally).
# Tune these against real disruption events.
# --------------------------------------------------------------------------- #
RISK_WEIGHTS = {
    "geopolitical_intensity":   0.25,  # GDELT negative-tone event density
    "weather_alerts":           0.18,  # NOAA + storm/typhoon proximity + EONET storms
    "seismic_activity":         0.10,  # USGS M5+ in last 7d + EONET earthquakes/volcanoes
    "commodity_volatility":     0.17,  # commodity z-score + macro shocks
    "port_congestion_proxy":    0.15,  # AIS vessel density near major ports
    "aviation_disruption":      0.10,  # OpenSky-derived airport congestion
    "natural_disasters":        0.05,  # EONET wildfires/floods/drought/landslides
}

# --------------------------------------------------------------------------- #
# Cache TTLs in seconds - per-source so volatile feeds refresh faster.
# --------------------------------------------------------------------------- #
CACHE_TTL = {
    "ais_snapshot":     5 * 60,      # 5 min - vessels move
    "flight_snapshot":  60,          # 1 min - aircraft move fast
    "gdelt":            10 * 60,     # 10 min - event firehose
    "gdacs":            30 * 60,     # 30 min - GDACS event list
    "usgs_quakes":      10 * 60,
    "eonet":            15 * 60,     # 15 min - natural events update slowly
    "nhc":              10 * 60,     # 10 min - NHC advisories every few hours
    "noaa_alerts":      10 * 60,
    "open_meteo":       60 * 60,     # 1 h - weather changes slowly at country scale
    "yfinance":         15 * 60,     # 15 min during market hours
    "fred":             6 * 60 * 60, # 6 h - macro series update slowly
    "news":             15 * 60,     # 15 min - RSS feeds (Google News, Reddit)
    "world_bank":       24 * 60 * 60,
    "claude_summary":   30 * 60,     # don't burn tokens
}
