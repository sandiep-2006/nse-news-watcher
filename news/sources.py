"""Free Indian financial news RSS sources.

All feeds are public, no API key needed. URLs verified live (2026-08-10) to
return real, current articles - if a site changes its RSS path later, that
one feed just logs a warning and returns nothing, it won't break the others.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import feedparser
import requests

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_TAG_RE = re.compile(r"<[^<]+?>")

RSS_FEEDS: dict[str, str] = {
    "moneycontrol_buzzing": "https://www.moneycontrol.com/rss/buzzingstocks.xml",
    "moneycontrol_results": "https://www.moneycontrol.com/rss/results.xml",
    "moneycontrol_business": "https://www.moneycontrol.com/rss/business.xml",
    "et_markets_stocks": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    "business_standard_markets": "https://www.business-standard.com/rss/markets-106.rss",
    "livemint_markets": "https://www.livemint.com/rss/markets",
    "livemint_companies": "https://www.livemint.com/rss/companies",
}


@dataclass
class NewsItem:
    source: str
    title: str
    summary: str
    link: str
    published: str  # raw string from the feed, best-effort, not parsed

    @property
    def uid(self) -> str:
        """Stable id for dedup - the article link, falling back to source+title."""
        return self.link or f"{self.source}:{self.title}"


def _clean(text: str) -> str:
    return _TAG_RE.sub("", text or "").strip()


def fetch_feed(name: str, url: str, timeout: int = 10) -> list[NewsItem]:
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Fetch failed for %s (%s): %s", name, url, e)
        return []

    parsed = feedparser.parse(resp.content)
    items = []
    for entry in parsed.entries:
        items.append(
            NewsItem(
                source=name,
                title=_clean(entry.get("title", "")),
                summary=_clean(entry.get("summary", "")),
                link=entry.get("link", "").strip(),
                published=entry.get("published", entry.get("updated", "")),
            )
        )
    return items


def fetch_all(feeds: dict[str, str] = RSS_FEEDS) -> list[NewsItem]:
    """Fetch every configured feed, logging a per-feed count. One feed failing
    (site down, blocked, URL changed) never aborts the others."""
    all_items: list[NewsItem] = []
    for name, url in feeds.items():
        items = fetch_feed(name, url)
        logger.info("%s: %d items", name, len(items))
        all_items.extend(items)
    return all_items
