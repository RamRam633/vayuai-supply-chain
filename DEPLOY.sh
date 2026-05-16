#!/usr/bin/env bash
# Global Supply Chain Pulse — deploy walkthrough.
#
# Run blocks one at a time. Each block is independent. Read the comments first.
#
#   bash DEPLOY.sh                  # prints this menu
#   bash DEPLOY.sh local            # run the app locally first to sanity-check
#   bash DEPLOY.sh keys             # paste your free API keys into .env
#   bash DEPLOY.sh git              # init repo + push to GitHub
#   bash DEPLOY.sh render           # what to click in the Render dashboard
#   bash DEPLOY.sh vercel           # deploy the landing page
#
# Prereqs (one-time):
#   - GitHub CLI:   brew install gh   &&  gh auth login
#   - Vercel CLI:   npm i -g vercel   &&  vercel login
#   - A Render account at https://render.com (free tier is fine)

set -euo pipefail
cd "$(dirname "$0")"

cmd="${1:-help}"

case "$cmd" in

# --------------------------------------------------------------------------- #
local)
  # Smoke-test before you ship. Opens http://localhost:8501
  source .venv/bin/activate
  streamlit run app.py
  ;;

# --------------------------------------------------------------------------- #
keys)
  cat <<'EOF'

Open .env in an editor and paste your keys. All free, ~2 min each:

  FRED_API_KEY=        https://fredaccount.stlouisfed.org/apikeys
                       (makes macro charts real instead of synthetic)

  AISSTREAM_API_KEY=   https://aisstream.io/authenticate
                       (makes vessel positions real instead of synthetic)

  NOAA_USER_AGENT=     SupplyChainPulse/1.0 (your-real-email@example.com)
                       (NOAA requires a contact in the User-Agent string)

  ANTHROPIC_API_KEY=   https://console.anthropic.com   (optional)
                       (only needed if you flip ENABLE_CLAUDE_SUMMARY=true)

After editing, verify everything still works:
  PYTHONPATH=. .venv/bin/python scripts/check_apis.py

EOF
  ;;

# --------------------------------------------------------------------------- #
git)
  # Initialize the repo and push to GitHub. Requires `gh` CLI authenticated.
  # If you already created the repo on github.com, replace this block with:
  #   git init && git add . && git commit -m "initial"
  #   git remote add origin git@github.com:<you>/<repo>.git
  #   git branch -M main && git push -u origin main

  if [ -d .git ]; then
    echo "[git] repo already initialized — pushing latest changes"
    git add -A
    git commit -m "deploy: update" || echo "nothing to commit"
    git push
    exit 0
  fi

  echo "[git] initializing new repo"
  git init
  git add .
  git commit -m "initial: global supply chain pulse"

  # Make sure .env is NOT committed (it's already in .gitignore but double-check)
  if git ls-files --error-unmatch .env >/dev/null 2>&1; then
    echo "ERROR: .env is staged. Aborting — remove secrets first."
    exit 1
  fi

  echo "[git] creating GitHub repo (private by default; pass --public to make it public)"
  gh repo create global-supply-chain-pulse --private --source=. --remote=origin --push
  echo "[git] done. Repo URL:"
  gh repo view --json url -q .url
  ;;

# --------------------------------------------------------------------------- #
render)
  cat <<'EOF'

Render deploys the Streamlit app + the 15-min cron job from render.yaml.

  1. Go to https://dashboard.render.com/blueprints
  2. Click "New Blueprint Instance"
  3. Connect this GitHub repo
  4. Render reads render.yaml and shows two services:
       - supply-chain-pulse  (web, Docker, free tier)
       - pulse-refresh       (cron, every 15 min)
     plus a 1GB persistent disk shared by both.
  5. Render will prompt for the secrets it can't sync:
        AISSTREAM_API_KEY
        FRED_API_KEY
        NOAA_USER_AGENT      (e.g. "SupplyChainPulse/1.0 (you@example.com)")
        ANTHROPIC_API_KEY    (leave blank if you're not using Claude summary)
  6. Click "Apply". First build takes ~5 min.
  7. When the web service is green, copy its URL — looks like:
        https://supply-chain-pulse.onrender.com

Note: the free tier sleeps after 15 min idle. Upgrade to Starter ($7/mo) if
you want it always-on.

EOF
  ;;

# --------------------------------------------------------------------------- #
vercel)
  # Vercel hosts the marketing landing page that iframes the Render URL.
  if ! command -v vercel >/dev/null 2>&1; then
    echo "Vercel CLI missing. Install with:  npm i -g vercel"
    exit 1
  fi

  echo "[vercel] Make sure landing/index.html points at your Render URL."
  echo "         Look for the <iframe src=\"...\"> tag and replace the placeholder."
  echo
  read -r -p "Press Enter when the iframe src is updated..."

  cd landing
  vercel --prod
  ;;

# --------------------------------------------------------------------------- #
help|*)
  grep -E '^# ' "$0" | head -20 | sed 's/^# \?//'
  echo
  echo "Subcommands: local | keys | git | render | vercel"
  ;;

esac
