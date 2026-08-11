"""Load config/settings.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SETTINGS_FILE = ROOT / "config" / "settings.yaml"


def load_settings(path: Path = DEFAULT_SETTINGS_FILE) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
