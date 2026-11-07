"""US Treasury daily par yield curve (CSV, no key): the daily 10-year yield.

This is the benchmark emerging-market dollar bonds are priced against, so it
is worth having daily rather than as a monthly average.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime

from . import http

URL = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
       "daily-treasury-rates.csv/{year}/all")


def parse(text: str) -> list[tuple[str, float]]:
    """[(ISO date, 10-year yield), ...] sorted oldest first."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    cols = {(name or "").strip().strip('"'): name for name in (reader.fieldnames or [])}
    if "Date" not in cols or "10 Yr" not in cols:
        raise ValueError(f"unexpected Treasury columns: {reader.fieldnames}")
    out = []
    for row in reader:
        raw_date, raw_val = (row[cols["Date"]] or "").strip(), (row[cols["10 Yr"]] or "").strip()
        if not raw_val:
            continue
        out.append((datetime.strptime(raw_date, "%m/%d/%Y").date().isoformat(), float(raw_val)))
    return sorted(out)


def fetch(today: date) -> dict:
    """{"value", "date", "prev", "prev_date", "source", "freq"} for the latest two trading days."""
    obs = []
    for year in (today.year, today.year - 1):
        resp = http.get(URL.format(year=year), params={"type": "daily_treasury_yield_curve",
                                                       "field_tdr_date_value": year, "page": "", "_format": "csv"})
        obs = parse(resp.text) + obs
        if len(obs) >= 2:
            break
    if not obs:
        raise ValueError("no Treasury yield observations")
    last, prev = obs[-1], (obs[-2] if len(obs) > 1 else (None, None))
    return {"value": last[1], "date": last[0], "prev": prev[1], "prev_date": prev[0],
            "source": "US Treasury", "freq": "daily"}
