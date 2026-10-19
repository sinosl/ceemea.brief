"""Load the country list and settings from config/countries.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml

from .models import Country

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "countries.yaml"


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    raw["countries"] = [Country(**{k: str(v or "") for k, v in c.items()}) for c in raw["countries"]]
    return raw
