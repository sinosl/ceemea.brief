"""OECD Data Explorer (SDMX REST API, no key): monthly CPI breakdown and 10-year yields.

* CPI: the OECD is moving from its COICOP 1999 dataset to a COICOP 2018 one,
  and some countries stopped updating in the old one. Both are queried and the
  most recent series for each country and category is kept.
* Long-term (10-year) government bond yields: monthly averages from the
  short-term economic statistics "financial market" dataset.

Requests name only the countries flagged `oecd: true`. If a batch request is
refused, countries are retried one at a time so one bad code can't sink the rest.
"""
from __future__ import annotations

import csv
import io
import time
from datetime import date

from . import http

BASE = "https://sdmx.oecd.org/public/rest/data"
CPI_FLOWS = [
    "OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0",
    "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0",
]
YIELD_FLOW = "OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0"

# CPI categories shown on deep-dive pages: label -> codes tried in order
CPI_CATEGORIES = {
    "headline": ["_T"],
    "food": ["CP01"],
    "energy": ["NRG"],
    "core": ["_TXCP01_NRG"],
}


def _rows(text: str) -> list[dict]:
    """SDMX-CSV rows with column names reduced to their codes ('REF_AREA:Reference area' -> 'REF_AREA')."""
    reader = csv.DictReader(io.StringIO(text))
    cols = {name: name.split(":")[0].strip().upper() for name in (reader.fieldnames or [])}
    if "OBS_VALUE" not in cols.values() or "REF_AREA" not in cols.values():
        raise ValueError(f"unexpected OECD columns: {reader.fieldnames}")
    out = []
    for row in reader:
        r = {cols[k]: (v or "").split(":")[0].strip() for k, v in row.items() if k in cols}
        if r.get("OBS_VALUE") not in ("", "NaN", "NAN"):
            out.append(r)
    return out


def start_period(today: date, months_back: int) -> str:
    y, m = today.year, today.month - months_back
    while m <= 0:
        y, m = y - 1, m + 12
    return f"{y:04d}-{m:02d}"


def _get(flow: str, key: str, start: str) -> str:
    return http.get(f"{BASE}/{flow}/{key}", params={"startPeriod": start, "format": "csvfile"}, timeout=90).text


def _batched(flow: str, areas: list[str], key_tail: str, start: str) -> list[dict]:
    """One request for all areas; on failure, one request per area (best effort)."""
    try:
        return _rows(_get(flow, "+".join(areas) + key_tail, start))
    except Exception:   # noqa: BLE001
        rows = []
        for a in areas:
            try:
                rows += _rows(_get(flow, a + key_tail, start))
            except Exception:   # noqa: BLE001 - country not covered by this dataset
                pass
            time.sleep(1.0)
        return rows


def parse_cpi(rows_by_flow: list[tuple[str, list[dict]]]) -> dict:
    """{iso3: {category: {"period", "value", "year_ago", "series": [[period, value], ...], "flow"}}}"""
    best: dict = {}
    for flow, rows in rows_by_flow:
        series: dict = {}
        for r in rows:
            if r.get("FREQ", "M") != "M" or r.get("MEASURE", "CPI") != "CPI":
                continue
            series.setdefault((r["REF_AREA"], r.get("EXPENDITURE", "_T")), []).append(
                (r["TIME_PERIOD"], float(r["OBS_VALUE"])))
        for (area, code), obs in series.items():
            cat = next((c for c, codes in CPI_CATEGORIES.items() if code in codes), None)
            if not cat:
                continue
            obs.sort()
            current = best.get(area, {}).get(cat)
            if current and current["period"] >= obs[-1][0]:
                continue   # the other dataset is at least as recent
            best.setdefault(area, {})[cat] = {
                "period": obs[-1][0], "value": round(obs[-1][1], 2),
                "year_ago": round(obs[-13][1], 2) if len(obs) >= 13 else None,
                "series": [[p, round(v, 2)] for p, v in obs[-13:]],
                "flow": "COICOP 2018" if "C2018" in flow else "COICOP 1999",
            }
    return best


def fetch_cpi(areas: list[str], today: date) -> dict:
    start = start_period(today, 15)
    collected = []
    for flow in CPI_FLOWS:
        collected.append((flow, _batched(flow, areas, ".M.N.CPI.PA..N.GY", start)))
    return parse_cpi(collected)


def parse_yields(rows: list[dict]) -> dict:
    """{iso3: {"value", "date", "prev", "prev_date", "source", "freq"}} from monthly IRLT rows."""
    series: dict = {}
    for r in rows:
        if r.get("MEASURE") == "IRLT" and r.get("FREQ", "M") == "M":
            series.setdefault(r["REF_AREA"], []).append((r["TIME_PERIOD"], float(r["OBS_VALUE"])))
    out = {}
    for area, obs in series.items():
        obs.sort()
        out[area] = {"value": round(obs[-1][1], 2), "date": obs[-1][0],
                     "prev": round(obs[-2][1], 2) if len(obs) > 1 else None,
                     "prev_date": obs[-2][0] if len(obs) > 1 else None,
                     "source": "OECD", "freq": "monthly average"}
    return out


def fetch_yields(areas: list[str], today: date) -> dict:
    return parse_yields(_batched(YIELD_FLOW, areas, ".M.IRLT.PA.....", start_period(today, 4)))
