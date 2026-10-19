"""Central bank policy rates from the BIS (dataset WS_CBPOL).

Tries the SDMX API first (small, monthly series) and falls back to the
bulk flat CSV if the API is unavailable. BIS does not cover every
country; those are simply left out and shown as "not in BIS".
"""
from __future__ import annotations

import csv
import io
import zipfile

from . import http

API = "https://stats.bis.org/api/v1/data/WS_CBPOL/M.{areas}/all"
BULK = "https://data.bis.org/static/bulk/WS_CBPOL_csv_flat.zip"


def parse_csv(text: str, areas: list[str]) -> dict[str, list[tuple[str, float]]]:
    """Parse SDMX-CSV (API or bulk) into {area: [(period, rate), ...]} sorted by period.

    Column names differ slightly between the API and bulk files, so match
    them by suffix (e.g. 'REF_AREA' and 'REF_AREA:Reference area').
    """
    reader = csv.DictReader(io.StringIO(text))
    cols = {name.split(":")[0].strip().upper(): name for name in (reader.fieldnames or [])}
    need = ("REF_AREA", "TIME_PERIOD", "OBS_VALUE")
    if not all(c in cols for c in need):
        raise ValueError(f"unexpected BIS columns: {reader.fieldnames}")
    freq_col = cols.get("FREQ")
    out: dict[str, list[tuple[str, float]]] = {a: [] for a in areas}
    for row in reader:
        area = row[cols["REF_AREA"]].split(":")[0].strip()
        if area not in out:
            continue
        if freq_col and row[freq_col].split(":")[0].strip() not in ("M", ""):
            continue
        val = row[cols["OBS_VALUE"]].strip()
        if not val or val.upper() == "NAN":
            continue
        out[area].append((row[cols["TIME_PERIOD"]].strip(), float(val)))
    for a in out:
        out[a].sort()
    return out


def latest(series: dict[str, list[tuple[str, float]]]) -> dict[str, dict]:
    """Latest rate and the change from the previous month, per area."""
    res = {}
    for area, obs in series.items():
        if not obs:
            continue
        period, rate = obs[-1]
        prev = obs[-2][1] if len(obs) > 1 else None
        res[area] = {"period": period, "rate": rate,
                     "change_bp": None if prev is None else round((rate - prev) * 100)}
    return res


def fetch(areas: list[str]) -> dict[str, dict]:
    areas = [a for a in areas if a]
    try:
        resp = http.get(API.format(areas="+".join(areas)),
                        params={"lastNObservations": 3, "format": "csv"}, timeout=60)
        return latest(parse_csv(resp.text, areas))
    except Exception:   # noqa: BLE001 - fall back to the bulk file
        resp = http.get(BULK, timeout=120)
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            name = next(n for n in zf.namelist() if n.endswith(".csv"))
            text = zf.read(name).decode("utf-8-sig")
        return latest(parse_csv(text, areas))
