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
