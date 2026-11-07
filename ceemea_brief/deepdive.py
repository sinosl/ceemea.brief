"""Country deep-dive pages: a structural and microeconomic breakdown of each economy.

Everything here is computed from the data, with no language model involved:
inflation by component (OECD, monthly), labour market, economic structure,
trade and external position (World Bank, annual), with each figure compared
against the CEEMEA and developed-economy averages.
"""
from __future__ import annotations

from pathlib import Path

from .models import CountryBrief

CPI_LABELS = {"headline": "All items", "food": "Food", "energy": "Energy", "core": "Core (excl. food and energy)"}
SECTIONS = {"overview": "Income", "structure": "Economic structure", "labour": "Labour market and prices",
            "external": "Trade, remittances and credit"}


def peer_averages(wb: dict, cfg: dict) -> dict:
    """{indicator: {"ceemea": avg, "developed": avg}} over countries with data."""
    groups = {"ceemea": [c.iso3 for c in cfg["countries"] if c.group != "global"],
              "developed": [c.iso3 for c in cfg["countries"] if c.developed]}
    out = {}
    for ind in cfg["worldbank_indicators"]:
        vals = wb.get(ind, {})
        out[ind] = {}
        for g, isos in groups.items():
            xs = [vals[i]["value"] for i in isos if i in vals]
            out[ind][g] = round(sum(xs) / len(xs), 2) if xs else None
    return out


def peer_group(c) -> tuple[str, str]:
    return ("developed", "developed-economy") if c.group == "global" else ("ceemea", "CEEMEA")


def fmt_num(v, digits=1):
    if v is None:
        return "–"
    return f"{v:,.0f}" if digits == 0 else f"{v:,.{digits}f}"


def highlights(c, wb: dict, avgs: dict, cfg: dict, n: int = 3) -> list[str]:
    """The n indicators where the country differs most from its peer average (computed, not written by a model)."""
    key, name = peer_group(c)
    scored = []
    for ind, meta in cfg["worldbank_indicators"].items():
        obs, avg = wb.get(ind, {}).get(c.iso3), avgs.get(ind, {}).get(key)
        if not obs or avg is None:
            continue
        gap = (obs["value"] - avg) / max(abs(avg), 1.0)
        scored.append((abs(gap), ind, meta, obs, avg))
    scored.sort(key=lambda t: t[0], reverse=True)
    out = []
    for size, ind, meta, obs, avg in scored[:n]:
        d = int(meta.get("digits", 1))
        unit = meta["unit"]
        pre, post = ("US$", "") if unit == "US$" else ("", unit if unit.startswith("%") else f" {unit}")
        direction = ("well " if size >= 0.5 else "") + ("above" if obs["value"] > avg else "below")
        out.append(f"{meta['label']} is {pre}{fmt_num(obs['value'], d)}{post} ({obs['year']}), {direction} "
                   f"the {name} average of {pre}{fmt_num(avg, d)}{post}.")
    return out


def sparkline(series: list, width: int = 120, height: int = 28) -> str:
    """SVG polyline points for a short series of [period, value] pairs."""
    vals = [v for _, v in series]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    step = width / (len(vals) - 1)
    return " ".join(f"{i * step:.1f},{height - 2 - (v - lo) / span * (height - 4):.1f}" for i, v in enumerate(vals))


def country_context(c, brief: CountryBrief, raw: dict, cfg: dict, avgs: dict) -> dict:
    wb = raw.get("worldbank") or {}
    key, peer_name = peer_group(c)
    sections: dict = {s: [] for s in SECTIONS}
    for ind, meta in cfg["worldbank_indicators"].items():
        obs = wb.get(ind, {}).get(c.iso3)
        sections.setdefault(meta.get("section", "overview"), []).append({
            "label": meta["label"], "unit": meta["unit"], "digits": int(meta.get("digits", 1)),
            "value": obs["value"] if obs else None, "year": obs["year"] if obs else None,
            "ceemea": avgs[ind]["ceemea"], "developed": avgs[ind]["developed"], "ind": ind})
    structure = {row["ind"]: row["value"] for row in sections["structure"]}
    cpi = (raw.get("cpi") or {}).get(c.iso3) or {}
    cpi_rows = [dict(label=CPI_LABELS[k], points=sparkline(v["series"]), **v) for k, v in cpi.items() if k in CPI_LABELS]
    cpi_rows.sort(key=lambda r: list(CPI_LABELS.values()).index(r["label"]))
    snap = brief.macro.get("snapshot", {})
    return {"c": c, "brief": brief, "sections": sections, "section_names": SECTIONS, "structure": structure,
            "cpi_rows": cpi_rows, "yld": snap.get("yield"), "rate": snap.get("policy_rate"), "fx": snap.get("fx"),
            "imf": snap.get("imf", {}), "peer_name": peer_name, "peer_key": key,
            "highlights": highlights(c, wb, avgs, cfg)}


def write_pages(briefs: list[CountryBrief], raw: dict, cfg: dict, report: dict, out_dir: Path) -> None:
    from .render import env, long_date   # shared Jinja environment and filters
    folder = out_dir / "country"
    folder.mkdir(parents=True, exist_ok=True)
    avgs = peer_averages(raw.get("worldbank") or {}, cfg)
    page = env.get_template("country.html.j2")
    year = report["years"][0]
    contexts = []
    for b in briefs:
        ctx = country_context(b.country, b, raw, cfg, avgs)
        contexts.append(ctx)
        (folder / f"{b.country.iso3}.html").write_text(
            page.render(report=report, cfg=cfg, year=year, when=long_date(report["run_date"]), fmt_num=fmt_num, **ctx),
            encoding="utf-8")
    (folder / "index.html").write_text(env.get_template("countries.html.j2").render(
        contexts=contexts, report=report, when=long_date(report["run_date"])), encoding="utf-8")
