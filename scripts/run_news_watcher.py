"""Entry point for the live news watcher - polls free Indian financial news,
matches to Nifty 500 symbols, scores likely direction, alerts via Telegram.

Advisory only: nothing here places trades. See news/watcher.py and
config/news.yaml. Telegram delivery needs config/telegram_credentials.json
filled in (copy config/telegram_credentials.example.json) - until then,
alerts just get logged, not sent.

Usage:
    python scripts/run_news_watcher.py                    # run continuously
    python scripts/run_news_watcher.py --once              # single poll pass, then exit (testing)
    python scripts/run_news_watcher.py --all-hours          # ignore market-hours gating (testing)
    python scripts/run_news_watcher.py --once --dry-run      # test without sending real Telegram messages
"""
from __future__ import annotations

import argparse
import sys
from datetime import time as dtime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from news import telegram_bot
from news.symbol_matcher import SymbolMatcher
from news.watcher import load_seen, main_loop, run_once, save_seen
from utils.config import load_settings
from utils.logging_config import setup_logging

ROOT = Path(__file__).resolve().parent.parent
NEWS_CONFIG_FILE = ROOT / "config" / "news.yaml"


def _parse_hhmm(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Run a single poll pass and exit")
    parser.add_argument("--all-hours", action="store_true", help="Ignore market-hours gating")
    parser.add_argument("--dry-run", action="store_true", help="Log alerts instead of sending them to Telegram")
    args = parser.parse_args()

    setup_logging()
    if args.dry_run:
        telegram_bot.DRY_RUN = True

    cfg = load_settings(NEWS_CONFIG_FILE) if NEWS_CONFIG_FILE.exists() else {}
    poll_seconds = int(cfg.get("poll_seconds", 150))
    market_hours_only = bool(cfg.get("market_hours_only", True)) and not args.all_hours
    market_start = _parse_hhmm(cfg.get("market_start", "09:00"))
    market_end = _parse_hhmm(cfg.get("market_end", "15:35"))

    if args.once:
        matcher = SymbolMatcher()
        seen = load_seen()
        seen, n_alerts = run_once(matcher, seen)
        save_seen(seen)
        print(f"Single poll pass complete: {n_alerts} alert(s) sent.")
    else:
        main_loop(
            poll_seconds=poll_seconds,
            market_hours_only=market_hours_only,
            market_start=market_start,
            market_end=market_end,
        )


if __name__ == "__main__":
    main()
