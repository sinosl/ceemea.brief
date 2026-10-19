"""IMF World Economic Outlook series via the DataMapper API.

The API returns every country for an indicator, so we fetch once per
indicator and filter locally.
"""
from __future__ import annotations

from . import http

URL = "https://www.imf.org/external/datamapper/api/v1/{indicator}"


def parse(payload: dict, indicator: str, iso3s: list[str], years: list[int]) -> dict[str, dict[int, float]]:
    """Return {iso3: {year: value}} for the requested countries and years."""
    series = payload.get("values", {}).get(indicator, {})
    out: dict[str, dict[int, float]] = {}
    for iso in iso3s:
        row = series.get(iso, {})
        out[iso] = {y: float(row[str(y)]) for y in years if row.get(str(y)) is not None}
    return out


def fetch(indicators: list[str], iso3s: list[str], years: list[int]) -> dict[str, dict[str, dict[int, float]]]:
    """Return {indicator: {iso3: {year: value}}}. Missing indicators raise, so the caller can log them."""
    result = {}
    for ind in indicators:
        payload = http.get(URL.format(indicator=ind), timeout=60).json()
        result[ind] = parse(payload, ind, iso3s, years)
    return result
