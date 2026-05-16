#!/usr/bin/env bash
# Global Supply Chain Pulse — local run helper.
# Usage:
#   ./run.sh setup     # one-time: create venv, install deps, copy .env
#   ./run.sh refresh   # pull fresh data from all free APIs (run anytime)
#   ./run.sh ais       # collect ~60s of AIS vessel positions (needs key)
#   ./run.sh app       # launch the Streamlit dashboard
#   ./run.sh test      # run smoke tests
#   ./run.sh deploy-render  # push to Render via blueprint (needs git remote)
#   ./run.sh deploy-vercel  # push the landing page to Vercel
#
# First-time path:  ./run.sh setup  →  edit .env  →  ./run.sh refresh  →  ./run.sh app

set -euo pipefail

cd "$(dirname "$0")"
VENV=".venv"

cmd="${1:-help}"

case "$cmd" in
  setup)
    echo "[setup] creating venv at $VENV"
    python3 -m venv "$VENV"
    # shellcheck source=/dev/null
    source "$VENV/bin/activate"
    pip install --upgrade pip
    pip install -r requirements.txt
    if [ ! -f .env ]; then
      cp .env.example .env
      echo "[setup] copied .env.example -> .env"
      echo "[setup] EDIT .env and add at minimum:"
      echo "          FRED_API_KEY        (free, https://fredaccount.stlouisfed.org/apikeys)"
      echo "          AISSTREAM_API_KEY   (free, https://aisstream.io/authenticate)"
      echo "          ANTHROPIC_API_KEY   (optional, for Claude exec summary)"
    fi
    mkdir -p data
    echo "[setup] done. Next: edit .env, then ./run.sh refresh && ./run.sh app"
    ;;

  refresh)
    # shellcheck source=/dev/null
    source "$VENV/bin/activate"
    python scripts/refresh_data.py
    ;;

  ais)
    # shellcheck source=/dev/null
    source "$VENV/bin/activate"
    python scripts/refresh_ais.py
    ;;

  app)
    # shellcheck source=/dev/null
    source "$VENV/bin/activate"
    streamlit run app.py
    ;;

  test)
    # shellcheck source=/dev/null
    source "$VENV/bin/activate"
    pytest -q
    ;;

  deploy-render)
    echo "[deploy-render] this assumes the repo is pushed to GitHub."
    echo "[deploy-render] in Render dashboard:"
    echo "   1. New -> Blueprint -> connect this repo"
    echo "   2. Render reads render.yaml and provisions:"
    echo "        - web service (Streamlit)"
    echo "        - cron job (refresh_data.py every 15 min)"
    echo "        - 1GB persistent disk"
    echo "   3. Set secrets in Render: AISSTREAM_API_KEY, FRED_API_KEY, NOAA_USER_AGENT, ANTHROPIC_API_KEY"
    ;;

  deploy-vercel)
    if ! command -v vercel >/dev/null 2>&1; then
      echo "Install Vercel CLI first: npm i -g vercel"
      exit 1
    fi
    cd landing
    echo "[deploy-vercel] remember to edit landing/index.html iframe src to your Render URL"
    vercel --prod
    ;;

  help|*)
    grep -E '^#( |   )' "$0" | sed 's/^# \?//'
    ;;
esac
