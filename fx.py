"""Spot FX against USD from the free open.er-api.com endpoint (daily update)."""
from __future__ import annotations

from . import http

URL = "https://open.er-api.com/v6/latest/USD"


def parse(payload: dict, currencies: list[str]) -> dict:
    if payload.get("result") != "success":
        raise ValueError(f"FX API returned {payload.get('result')}")
    rates = payload.get("rates", {})
    return {"as_of": payload.get("time_last_update_utc", ""),
            "rates": {c: float(rates[c]) for c in currencies if c in rates}}


def fetch(currencies: list[str]) -> dict:
    return parse(http.get(URL).json(), currencies)
