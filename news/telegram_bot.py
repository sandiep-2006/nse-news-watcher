"""Sends alerts to a personal Telegram chat via the Bot API.

Needs a bot token + chat id, from either of two places (checked in this
order):
  1. Environment variables TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID - used when
     running under GitHub Actions (set as repo secrets, no file involved).
  2. config/telegram_credentials.json (gitignored - copy
     config/telegram_credentials.example.json to get started) - used for a
     local run.
Until one of those is filled in, send_message() just logs a warning and
returns False - the rest of the watcher (fetch/match/score) still runs and
logs normally, so the pipeline is fully testable before Telegram is set up.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CREDENTIALS_FILE = ROOT / "config" / "telegram_credentials.json"

DRY_RUN = False  # when True, send_message logs what it WOULD send instead of calling the API - set via scripts/run_news_watcher.py --dry-run for safe testing


def load_credentials(path: Path = DEFAULT_CREDENTIALS_FILE) -> dict | None:
    env_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    env_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if env_token and env_chat_id:
        return {"bot_token": env_token, "chat_id": env_chat_id}

    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        creds = json.load(f)
    if not creds.get("bot_token") or not creds.get("chat_id"):
        return None
    return creds


def send_message(text: str, creds: dict | None = None, timeout: int = 10) -> bool:
    if DRY_RUN:
        logger.info("[DRY RUN] Would send Telegram message: %s", text.splitlines()[0][:80] if text else "")
        return True

    creds = creds if creds is not None else load_credentials()
    if creds is None:
        logger.warning(
            "Telegram not configured (fill in config/telegram_credentials.json) "
            "- skipping send: %s",
            text.splitlines()[0][:80] if text else "",
        )
        return False

    url = f"https://api.telegram.org/bot{creds['bot_token']}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={
                "chat_id": creds["chat_id"],
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=timeout,
        )
    except requests.RequestException as e:
        logger.error("Telegram send failed (network error): %s", e)
        return False

    if resp.status_code != 200:
        logger.error("Telegram send failed (%s): %s", resp.status_code, resp.text[:300])
        return False
    return True
