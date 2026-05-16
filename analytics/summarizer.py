"""
Executive summary generation.

Two modes:
  1. Local rule-based summary (always on) — composes a deterministic narrative
     from the top regional risks and most-severe recent signals.
  2. Claude API summary (off by default; ENABLE_CLAUDE_SUMMARY=true to enable)
     — takes the same structured brief and asks Claude for a sharper exec-style
     narrative, cached for CACHE_TTL['claude_summary'] seconds.

The Claude prompt is intentionally constrained to reduce hallucination: it
must cite signal IDs from the brief and stay within a bounded structure.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config
from analytics.risk_score import (
    compute_regional_risk,
    load_signals,
    top_risks,
)

SUMMARY_CACHE = Path(config.DATA_DIR) / "claude_summary.json"


def build_brief() -> dict[str, Any]:
    """Assemble a structured brief Claude can chew on.

    Designed so the same dict can be rendered locally or sent to Claude.
    """
    blob = load_signals()
    signals = blob.get("signals", [])
    regional = compute_regional_risk(signals)
    leaders = top_risks(regional, n=3)

    # Pick top severity signals per top region (last 24h).
    region_to_signals: dict[str, list[dict]] = {r: [] for r, _ in leaders}
    for sig in signals:
        for r in (
            [sig["region"]] if sig.get("region") else []
        ) + _placeholder_regions(sig):
            if r in region_to_signals:
                region_to_signals[r].append(sig)
    for r, sigs in region_to_signals.items():
        region_to_signals[r] = sorted(
            sigs, key=lambda s: s.get("severity", 0), reverse=True
        )[:5]

    # Commodity / macro callouts (always global).
    commodity_signals = [s for s in signals if s.get("category") == "commodity"]
    macro_signals = [s for s in signals if s.get("category") == "macro"]

    brief = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_freshness": blob.get("generated_at"),
        "regional_scores": regional,
        "top_regions": [{"region": r, "score": s} for r, s in leaders],
        "highlights_by_region": region_to_signals,
        "commodity_moves": commodity_signals[:5],
        "macro_moves": macro_signals[:5],
        "total_signals": len(signals),
    }
    return brief


def _placeholder_regions(sig: dict) -> list[str]:
    """Tag commodity/macro to all top regions for inclusion (UI affordance)."""
    return []


def local_summary(brief: dict[str, Any]) -> str:
    """Deterministic narrative — fallback when Claude is disabled."""
    lines = []
    top = brief.get("top_regions", [])
    if not top:
        return "Global supply-chain pressure is muted across all monitored regions. No significant signals in the lookback window."

    lead = top[0]
    others = ", ".join(f"{t['region']} ({t['score']})" for t in top[1:])
    suffix = f", followed by {others}" if others else ""
    lines.append(
        f"Supply-chain pressure is concentrated in **{lead['region']}** "
        f"(risk score {lead['score']}/100){suffix}."
    )

    for r, sigs in brief.get("highlights_by_region", {}).items():
        if not sigs:
            continue
        bits = "; ".join(s["title"] for s in sigs[:3])
        lines.append(f"**{r}** drivers: {bits}.")

    com = brief.get("commodity_moves", [])
    if com:
        lines.append(
            "Commodity moves of note: " + "; ".join(s["title"] for s in com[:3]) + "."
        )
    macro = brief.get("macro_moves", [])
    if macro:
        lines.append(
            "Macro shifts: " + "; ".join(s["title"] for s in macro[:3]) + "."
        )

    return "\n\n".join(lines)


# --------------------------------------------------------------------------- #
# Claude integration. Off by default.
# --------------------------------------------------------------------------- #
CLAUDE_SYSTEM = """You are an expert global supply-chain analyst writing for C-suite readers.

You will receive a structured JSON brief of current risk signals. Produce a tight
executive summary in markdown with this exact structure:

1. **Headline (one sentence)** — where pressure is building and why it matters now.
2. **Top three regional pressures** — each as a bullet citing 1-2 specific signals from the brief.
3. **Commodity/macro watch** — 2-3 sentences on the most consequential price/macro moves.
4. **What to watch in the next 24-48h** — one bullet per item, max 3 items.

Rules:
- Use only facts present in the brief; never invent events or numbers.
- Be specific (cite signal titles), but compress.
- No hedging filler ("it is worth noting that...").
- Max ~250 words total."""


def claude_executive_summary(brief: dict[str, Any]) -> str:
    """Call Claude with the brief. Returns local_summary() on any failure."""
    if not config.ENABLE_CLAUDE_SUMMARY or not config.ANTHROPIC_API_KEY:
        return local_summary(brief)

    # Cache check.
    if SUMMARY_CACHE.exists():
        try:
            cached = json.loads(SUMMARY_CACHE.read_text())
            age = time.time() - cached.get("written_at", 0)
            if age < config.CACHE_TTL["claude_summary"]:
                return cached["text"]
        except Exception:
            pass

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=900,
            system=CLAUDE_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": "Brief JSON:\n```json\n" + json.dumps(brief, default=str)[:18000] + "\n```",
                }
            ],
        )
        text = msg.content[0].text if msg.content else local_summary(brief)
    except Exception as e:
        print(f"[claude] summary failed: {e}")
        return local_summary(brief)

    try:
        SUMMARY_CACHE.write_text(json.dumps({"written_at": time.time(), "text": text}))
    except Exception as e:
        print(f"[claude] cache write failed: {e}")

    return text
