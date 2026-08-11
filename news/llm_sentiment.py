"""LLM-based bullish/bearish scorer for a news headline+summary, using the
free tier of Google's Gemini API (gemini-2.5-flash).

Needs an API key from either of two places (checked in this order):
  1. Environment variable GEMINI_API_KEY - used when running under GitHub
     Actions (set as a repo secret, no file involved).
  2. config/gemini_credentials.json (gitignored) - copy
     config/gemini_credentials.example.json and paste in a free key from
     https://aistudio.google.com/apikey (no card needed - the Flash free
     tier covers up to 1,000 requests/day, far more than this watcher
     needs) - used for a local run.
Until one of those is filled in, is_configured() returns False and
news.watcher falls back to news.sentiment's keyword scorer instead.

Unlike the keyword scorer (pure phrase counting), this actually reads the
sentence - it correctly handles cases like "shares fall despite profit
surge" (the price move is what matters, not the profit line mentioned in
passing), which is a known failure mode of the keyword approach.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CREDENTIALS_FILE = ROOT / "config" / "gemini_credentials.json"
MODEL = "gemini-2.5-flash"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "direction": {"type": "STRING", "enum": ["bullish", "bearish", "neutral"]},
        "confidence": {"type": "NUMBER", "description": "0.0 to 1.0"},
        "reason": {"type": "STRING", "description": "One short plain-language sentence"},
    },
    "required": ["direction", "confidence", "reason"],
}

_PROMPT_TEMPLATE = """You are screening a single Indian stock-market news headline for its likely SHORT-TERM effect on {company} ({symbol})'s own share price.

Headline: {title}
Summary: {summary}

Judge only the likely effect on {symbol}'s SHARE PRICE itself, not on other metrics mentioned in passing. If the headline reports a mix (e.g. price fell despite a profit rise, or an analyst kept a "Buy" rating even as results disappointed), the actual reported price move takes priority over other numbers or ratings. If there is no clear likely price effect, say neutral. Give your best-effort judgment; do not refuse."""


def load_credentials(path: Path = DEFAULT_CREDENTIALS_FILE) -> dict | None:
    env_key = os.environ.get("GEMINI_API_KEY")
    if env_key:
        return {"api_key": env_key}

    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        creds = json.load(f)
    if not creds.get("api_key"):
        return None
    return creds


def is_configured(path: Path = DEFAULT_CREDENTIALS_FILE) -> bool:
    return load_credentials(path) is not None


def score_text_llm(
    title: str,
    summary: str,
    symbol: str,
    company: str,
    creds: dict | None = None,
    timeout: int = 15,
) -> dict | None:
    """Same return shape as news.sentiment.score_text() (direction/confidence/
    reason/engine), or None if not configured or the call failed - callers
    must treat None as "fall back to the keyword scorer", NOT as neutral."""
    creds = creds if creds is not None else load_credentials()
    if creds is None:
        return None

    prompt = _PROMPT_TEMPLATE.format(
        company=company, symbol=symbol, title=title, summary=summary or "(none)"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _RESPONSE_SCHEMA,
            "temperature": 0.1,
        },
    }

    try:
        resp = requests.post(API_URL, params={"key": creds["api_key"]}, json=payload, timeout=timeout)
    except requests.RequestException as e:
        logger.warning("Gemini request failed (network error): %s - falling back to keyword scorer", e)
        return None

    if resp.status_code == 429:
        logger.warning("Gemini rate-limited (429) - falling back to keyword scorer for this item")
        return None
    if resp.status_code != 200:
        logger.warning(
            "Gemini request failed (%s): %s - falling back to keyword scorer",
            resp.status_code,
            resp.text[:300],
        )
        return None

    try:
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        direction = parsed["direction"]
        confidence = float(parsed["confidence"])
        reason = parsed.get("reason", "")
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as e:
        logger.warning("Could not parse Gemini response (%s) - falling back to keyword scorer", e)
        return None

    if direction not in ("bullish", "bearish", "neutral"):
        direction = "neutral"
    confidence = max(0.0, min(1.0, confidence))

    return {
        "direction": direction,
        "confidence": round(confidence, 3),
        "reason": reason,
        "engine": "gemini",
        "matched_positive": [],
        "matched_negative": [],
    }
