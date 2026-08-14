"""Polls free Indian financial news RSS feeds, matches each article to Nifty
500 symbols, scores likely direction with news.sentiment, and pushes new,
non-neutral hits to Telegram.

Advisory only - this does not place trades or feed the backtest engine.
See SESSION_STATUS.md's news-watcher section for how this fits into the
rest of the project.
"""
from __future__ import annotations

import csv
import json
import logging
import time
from datetime import date, datetime
from datetime import time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from news import llm_sentiment, sentiment, sources, telegram_bot
from news.symbol_matcher import SymbolMatcher

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
SEEN_STATE_FILE = ROOT / "data" / "news_watcher_seen.json"
ALERTS_LOG_FILE = ROOT / "data" / "alerts_log.csv"
IST = ZoneInfo("Asia/Kolkata")
MAX_SEEN_KEEP = 5000
LLM_CALL_DELAY_SEC = 0.5  # spacing between Gemini calls within one poll, safety margin under the free tier's per-minute rate limit

_LOG_FIELDS = [
    "date_ist",
    "time_ist",
    "symbol",
    "company",
    "direction",
    "confidence",
    "engine",
    "reason",
    "headline",
    "source",
    "link",
]


def log_alert(
    symbol: str,
    company: str,
    result: dict,
    item: sources.NewsItem,
    path: Path = ALERTS_LOG_FILE,
) -> None:
    """Appends one row per alert to a CSV, kept under version control (see
    .github/workflows/news_watcher.yml's commit step) so the history of
    every call made survives past any single GitHub Actions run - lets
    accuracy be checked later by reading this file instead of screenshotting
    Telegram."""
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    now = datetime.now(IST)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_LOG_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(
            {
                "date_ist": now.strftime("%Y-%m-%d"),
                "time_ist": now.strftime("%H:%M:%S"),
                "symbol": symbol,
                "company": company,
                "direction": result["direction"],
                "confidence": result["confidence"],
                "engine": result.get("engine", ""),
                "reason": result.get("reason", ""),
                "headline": item.title,
                "source": item.source,
                "link": item.link,
            }
        )


def load_seen(path: Path = SEEN_STATE_FILE) -> set[str]:
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read %s (%s) - starting with empty dedup state", path, e)
        return set()


def save_seen(seen: set[str], path: Path = SEEN_STATE_FILE, max_keep: int = MAX_SEEN_KEEP) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # sets have no stable order - trimming isn't "oldest-first" here, just a
    # cap so the file can't grow unbounded over a long-running session.
    trimmed = list(seen)[-max_keep:]
    path.write_text(json.dumps(trimmed), encoding="utf-8")


def in_market_hours(now: datetime, start: dtime, end: dtime) -> bool:
    if now.weekday() >= 5:  # Saturday/Sunday
        return False
    return start <= now.time() <= end


_ENGINE_LABEL = {"gemini": "AI", "keyword": "keyword heuristic"}


def format_alert(item: sources.NewsItem, symbol: str, company: str, result: dict) -> str:
    emoji = "\U0001F4C8" if result["direction"] == "bullish" else "\U0001F4C9"
    engine_label = _ENGINE_LABEL.get(result.get("engine"), result.get("engine", "?"))
    reason = result.get("reason") or "n/a"
    return (
        f"{emoji} <b>{symbol}</b> ({company})\n"
        f"{result['direction'].upper()} — confidence {result['confidence']:.0%} "
        f"[{engine_label}, unvalidated]\n"
        f"Why: {reason}\n"
        f"{item.title}\n"
        f'<a href="{item.link}">{item.source}</a>'
    )


def _score(item: sources.NewsItem, symbol: str, company: str, use_llm: bool) -> dict:
    """Scores one (article, symbol) pair. Tries Gemini first when configured;
    any failure (network, rate limit, bad response) transparently falls back
    to the free keyword scorer instead of dropping the alert."""
    if use_llm:
        result = llm_sentiment.score_text_llm(item.title, item.summary, symbol, company)
        time.sleep(LLM_CALL_DELAY_SEC)
        if result is not None:
            return result
    return sentiment.score_text(item.title, item.summary)


def run_once(matcher: SymbolMatcher, seen: set[str], use_llm: bool | None = None) -> tuple[set[str], int]:
    """Fetches all sources once, alerts on new+relevant items, returns the
    updated seen-set and how many alerts were sent."""
    if use_llm is None:
        use_llm = llm_sentiment.is_configured()

    items = sources.fetch_all()
    new_seen = set(seen)
    n_alerts = 0

    for item in items:
        if item.uid in seen:
            continue
        new_seen.add(item.uid)

        matches = matcher.match(item.title, item.summary)
        if not matches:
            continue

        for symbol, company in matches:
            result = _score(item, symbol, company, use_llm)
            if result["direction"] == "neutral":
                continue

            text = format_alert(item, symbol, company, result)
            logger.info(
                "ALERT %s %s conf=%.0f%% [%s] :: %s",
                symbol,
                result["direction"],
                result["confidence"] * 100,
                result.get("engine"),
                item.title,
            )
            telegram_bot.send_message(text)
            log_alert(symbol, company, result, item)
            n_alerts += 1

    return new_seen, n_alerts


def main_loop(
    poll_seconds: int = 150,
    market_hours_only: bool = True,
    market_start: dtime = dtime(9, 0),
    market_end: dtime = dtime(15, 35),
) -> None:
    matcher = SymbolMatcher()
    seen = load_seen()
    logger.info(
        "News watcher started. poll_seconds=%d market_hours_only=%s (%s-%s IST) scorer=%s",
        poll_seconds,
        market_hours_only,
        market_start,
        market_end,
        "gemini (falls back to keyword on any error)" if llm_sentiment.is_configured() else "keyword heuristic only",
    )

    last_log_date: date | None = None
    while True:
        now = datetime.now(IST)
        if market_hours_only and not in_market_hours(now, market_start, market_end):
            if last_log_date != now.date():
                logger.info("Outside market hours (%s IST) - sleeping until next check.", now.strftime("%H:%M"))
                last_log_date = now.date()
            time.sleep(poll_seconds)
            continue

        try:
            seen, n_alerts = run_once(matcher, seen)
            save_seen(seen)
            if n_alerts:
                logger.info("Poll complete: %d alert(s) sent.", n_alerts)
        except Exception:
            logger.exception("run_once failed - continuing to next poll instead of crashing")

        time.sleep(poll_seconds)
