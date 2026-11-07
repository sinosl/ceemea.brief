"""World Bank World Development Indicators (API v2, no key).

Annual series for the deep-dive pages. One request per indicator covers all
countries; the latest non-empty year is kept for each country.
"""
from __future__ import annotations

from . import http

URL = "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"


def parse(payload, iso3s: list[str]) -> dict[str, dict]:
    """{iso3: {"value", "year"}} using the most recent non-null observation."""
    if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
        msg = payload[0].get("message") if isinstance(payload, list) and payload and isinstance(payload[0], dict) else payload
        raise ValueError(f"World Bank returned no data: {str(msg)[:120]}")
    out: dict[str, dict] = {}
    for rec in payload[1]:
        iso, val, year = rec.get("countryiso3code"), rec.get("value"), rec.get("date")
        if iso not in iso3s or val is None or not str(year).isdigit():
            continue
        if iso not in out or int(year) > out[iso]["year"]:
            out[iso] = {"value": round(float(val), 2), "year": int(year)}
    return out


def fetch(indicators: list[str], iso3s: list[str], first_year: int, last_year: int) -> tuple[dict, dict]:
    """Returns ({indicator: {iso3: {...}}}, {indicator: error}) - one failed indicator doesn't stop the rest."""
    data, errors = {}, {}
    for ind in indicators:
        try:
            payload = http.get(URL.format(countries=";".join(iso3s), indicator=ind),
                               params={"format": "json", "date": f"{first_year}:{last_year}", "per_page": 1000},
                               timeout=60).json()
            data[ind] = parse(payload, iso3s)
        except Exception as exc:   # noqa: BLE001
            errors[ind] = str(exc)[:150]
    return data, errors
