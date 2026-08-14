"""Match free-text news articles to Nifty 500 stock symbols by company name.

Heuristic, not NLP: strips the corporate-form suffix off each company's legal
name (e.g. "Reliance Industries Ltd." -> "Reliance Industries") and looks for
that phrase, plus a small hand-picked list of common press shorthand (e.g.
"RIL", "TCS", "HUL"), as a whole-word/phrase match in the article text. A
handful of genuinely ambiguous short names (e.g. bare "Reliance", which could
mean Reliance Industries OR Reliance Power; bare "Mahindra", which matches
four different Nifty 500 companies) are deliberately left OUT of the manual
alias list rather than guessed at - better to miss a mention than mis-tag it.
"""
from __future__ import annotations

import re
from pathlib import Path

from utils.symbols import load_universe

ROOT = Path(__file__).resolve().parent.parent

_SUFFIX_RE = re.compile(
    r"\s*(private\s+limited|pvt\.?\s*ltd\.?|ltd\.?|limited)\s*\.?\s*$",
    re.IGNORECASE,
)

# Unambiguous common shorthand seen in real headlines that the auto-cleaned
# legal name wouldn't catch on its own. Deliberately conservative - omits
# anything that collides with another Nifty 500 name.
_MANUAL_ALIASES: dict[str, str] = {
    "ril": "RELIANCE",
    "tcs": "TCS",
    "infosys": "INFY",
    "hdfc bank": "HDFCBANK",
    "icici bank": "ICICIBANK",
    "sbi": "SBIN",
    "state bank of india": "SBIN",
    "l&t": "LT",
    "larsen & toubro": "LT",
    "larsen and toubro": "LT",
    "m&m": "M&M",
    "mahindra & mahindra": "M&M",
    "hul": "HINDUNILVR",
    "hindustan unilever": "HINDUNILVR",
    "kotak bank": "KOTAKBANK",
    "kotak mahindra bank": "KOTAKBANK",
    "axis bank": "AXISBANK",
    "bharti airtel": "BHARTIARTL",
    "airtel": "BHARTIARTL",
    "adani enterprises": "ADANIENT",
    "adani ports": "ADANIPORTS",
    "ultratech cement": "ULTRACEMCO",
    "asian paints": "ASIANPAINT",
    "nestle india": "NESTLEIND",
    "power grid": "POWERGRID",
    "dr reddy": "DRREDDY",
    "dr. reddy's": "DRREDDY",
    "divi's lab": "DIVISLAB",
    "eicher motors": "EICHERMOT",
    "hero motocorp": "HEROMOTOCO",
    "bajaj auto": "BAJAJ-AUTO",
    "jsw steel": "JSWSTEEL",
    "coal india": "COALINDIA",
    "indian oil": "IOC",
    "tech mahindra": "TECHM",
    "indusind bank": "INDUSINDBK",
    "sbi life": "SBILIFE",
    "hdfc life": "HDFCLIFE",
    "maruti suzuki": "MARUTI",
    "sun pharma": "SUNPHARMA",
    "tata motors": "TATAMOTORS",
    "tata steel": "TATASTEEL",
    "tata consultancy": "TCS",
}

_MIN_ALIAS_LEN = 4  # skip cleaned names shorter than this - too generic/risky

# These NSE-listed companies' names double as commonly-cited Indian brokerage/
# research houses - "according to Motilal Oswal", "JM Financial maintains a
# Buy", etc. - almost always about a DIFFERENT stock, not the company itself.
# A body-text mention is essentially always a citation; the article is only
# actually ABOUT one of these when the name appears in the headline. Caught
# live: an HAL-earnings article citing "JM Financial" as one of several
# brokerages got mis-tagged as JM Financial news (2026-08-14).
_TITLE_ONLY_SYMBOLS = {"JMFINANCIL", "MOTILALOFS", "IIFL", "ANGELONE", "NUVAMA"}


def _clean_company_name(name: str) -> str:
    return _SUFFIX_RE.sub("", name).strip().strip(".").strip()


class SymbolMatcher:
    """Builds an alias -> (symbol, company) index once, then matches article
    text against it. Each alias is matched as a whole phrase (word-boundary
    delimited) so e.g. "ITC" won't match inside "bitcoin"."""

    def __init__(self, universe_csv: Path | None = None):
        self._patterns: list[tuple[re.Pattern, str, str, bool]] = []
        self._build(universe_csv)

    def _build(self, universe_csv: Path | None) -> None:
        rows = load_universe(universe_csv) if universe_csv else load_universe()
        seen_aliases: set[str] = set()

        for row in rows:
            symbol = row["Symbol"].strip()
            company = row["Company Name"].strip()
            title_only = symbol in _TITLE_ONLY_SYMBOLS
            cleaned = _clean_company_name(company)
            if len(cleaned) >= _MIN_ALIAS_LEN:
                self._add(cleaned, symbol, company, seen_aliases, title_only=title_only)
            # also match the bare ticker itself when it's distinctive enough
            # (case-sensitive - avoids matching lowercase common words)
            if len(symbol) >= 3 and symbol.isalpha():
                self._add(symbol, symbol, company, seen_aliases, case_sensitive=True, title_only=title_only)

        for alias, symbol in _MANUAL_ALIASES.items():
            company = next((r["Company Name"] for r in rows if r["Symbol"] == symbol), symbol)
            self._add(alias, symbol, company, seen_aliases, title_only=symbol in _TITLE_ONLY_SYMBOLS)

    def _add(
        self,
        alias: str,
        symbol: str,
        company: str,
        seen: set[str],
        *,
        case_sensitive: bool = False,
        title_only: bool = False,
    ) -> None:
        key = (alias, case_sensitive)
        if key in seen:
            return
        seen.add(key)
        flags = 0 if case_sensitive else re.IGNORECASE
        pattern = re.compile(r"\b" + re.escape(alias) + r"\b", flags)
        self._patterns.append((pattern, symbol, company, title_only))

    def match(self, title: str, summary: str = "") -> list[tuple[str, str]]:
        """Returns unique (symbol, company) pairs found in `title`+`summary`.
        A handful of symbols (see _TITLE_ONLY_SYMBOLS) only match against the
        title - a body-only mention for those is almost always a citation of
        that firm's opinion on some other stock, not the article's subject."""
        full_text = f"{title} {summary}"
        if not full_text.strip():
            return []
        found: dict[str, str] = {}
        for pattern, symbol, company, title_only in self._patterns:
            if symbol in found:
                continue
            text = title if title_only else full_text
            if pattern.search(text):
                found[symbol] = company
        return list(found.items())
