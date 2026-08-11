"""Load the Nifty 500 universe and map symbols to Fyers' NSE cash-equity format."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_UNIVERSE_CSV = ROOT / "data" / "nifty500.csv"


def load_universe(path: Path = DEFAULT_UNIVERSE_CSV, series: str = "EQ") -> list[dict]:
    """Read data/nifty500.csv, keeping only rows for the given series (EQ by default)."""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = [row for row in csv.DictReader(f) if row.get("Series", "").strip() == series]
    if not rows:
        raise ValueError(f"No '{series}'-series rows found in {path}")
    return rows


def to_fyers_symbol(nse_symbol: str, exchange: str = "NSE") -> str:
    """e.g. 'RELIANCE' -> 'NSE:RELIANCE-EQ'."""
    return f"{exchange}:{nse_symbol.strip()}-EQ"


def load_fyers_symbols(path: Path = DEFAULT_UNIVERSE_CSV, exchange: str = "NSE") -> list[str]:
    return [to_fyers_symbol(row["Symbol"], exchange) for row in load_universe(path)]


def load_sector_map(path: Path = DEFAULT_UNIVERSE_CSV, series: str = "EQ") -> dict[str, str]:
    """Symbol -> Industry, e.g. {'HDFCBANK': 'Financial Services', ...}."""
    return {row["Symbol"]: row["Industry"] for row in load_universe(path, series)}
