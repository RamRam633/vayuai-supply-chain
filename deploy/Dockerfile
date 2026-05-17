# Dockerfile for Global Supply Chain Pulse — Streamlit app.
# Used by Render, Railway, Fly, or any container host.

FROM python:3.11-slim

WORKDIR /app

# System deps for pyarrow (parquet), pydeck, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps first for layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Patch Streamlit's shell index.html so social-bot crawlers (LinkedIn,
# Twitter, Slack, iMessage) see a real <title> and OG meta tags. By default
# the shell title is hardcoded "Streamlit" and JS-set page titles don't
# reach crawlers since they don't execute JS.
RUN python -c "import streamlit, pathlib; \
idx = pathlib.Path(streamlit.__file__).parent / 'static' / 'index.html'; \
html = idx.read_text(); \
inject = ('<title>Global Supply Chain Pulse | VayuAI</title>' \
'<meta name=\"description\" content=\"Real-time view of global trade. Fifteen public feeds across nine regions and eight strategic chokepoints, refreshed continuously.\"/>' \
'<meta property=\"og:title\" content=\"Global Supply Chain Pulse | VayuAI\"/>' \
'<meta property=\"og:description\" content=\"Real-time view of global trade. Fifteen public feeds across nine regions and eight strategic chokepoints, refreshed continuously.\"/>' \
'<meta property=\"og:url\" content=\"https://supplychain.vayuai.ai\"/>' \
'<meta property=\"og:type\" content=\"website\"/>' \
'<meta property=\"og:site_name\" content=\"VayuAI\"/>' \
'<meta name=\"twitter:card\" content=\"summary\"/>' \
'<meta name=\"twitter:title\" content=\"Global Supply Chain Pulse | VayuAI\"/>' \
'<meta name=\"twitter:description\" content=\"Real-time view of global trade. Fifteen public feeds across nine regions and eight strategic chokepoints, refreshed continuously.\"/>'); \
patched = html.replace('<title>Streamlit</title>', inject); \
assert patched != html, 'Streamlit title pattern not found - check Streamlit version'; \
idx.write_text(patched); \
print(f'Patched OG meta into {idx}')"

# App source.
COPY . .

# Render injects $PORT; default to 8501 for local.
ENV PORT=8501
EXPOSE 8501

# Streamlit needs --server.address=0.0.0.0 to bind in container.
CMD streamlit run app.py \
    --server.address=0.0.0.0 \
    --server.port=${PORT} \
    --server.headless=true \
    --browser.gatherUsageStats=false
