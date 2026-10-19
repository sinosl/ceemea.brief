"""Render the brief as static HTML for GitHub Pages (docs/)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import ROOT
from .models import CountryBrief

env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]),
                  trim_blocks=True, lstrip_blocks=True)


def fmt(v, digits=1, suffix=""):
    return "–" if v is None else f"{v:.{digits}f}{suffix}"


env.filters["fmt"] = fmt


def overview_rows(briefs: list[CountryBrief], cfg: dict, year: int) -> list[dict]:
    rows = []
    for b in briefs:
        snap = b.macro["snapshot"]
        imf = {ind: (snap["imf"].get(ind) or {}).get(str(year)) for ind in cfg["imf_indicators"]}
        fx_chg = next((c for c in b.changes if c.metric == "fx"), None)
        rows.append({"name": b.country.name, "region": b.country.region, "iso3": b.country.iso3,
                     "imf": imf, "rate": snap["policy_rate"], "fx": snap["fx"], "ccy": b.country.ccy,
                     "fx_alert": fx_chg.text if fx_chg else "", "flags": b.flag_count,
                     "headline": b.headline})
    return rows


def long_date(d: str) -> str:
    x = date.fromisoformat(d)
    return f"{x.strftime('%A')} {x.day} {x.strftime('%B %Y')}"


def write_site(briefs: list[CountryBrief], report: dict, cfg: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    arch = out_dir / "archive"
    arch.mkdir(exist_ok=True)
    year = report["years"][0]
    ctx = dict(briefs=briefs, report=report, cfg=cfg, year=year, rows=overview_rows(briefs, cfg, year),
               when=long_date(report["run_date"]),
               all_changes=[(b.country.name, c) for b in briefs for c in b.changes])
    page = env.get_template("brief.html.j2")
    (out_dir / "index.html").write_text(page.render(base="", **ctx), encoding="utf-8")
    (arch / f"{report['run_date']}.html").write_text(page.render(base="../", **ctx), encoding="utf-8")
    (out_dir / "latest.json").write_text(json.dumps(
        {"report": report, "briefs": [b.to_dict() for b in briefs]}, indent=1, default=str), encoding="utf-8")

    dates = sorted((p.stem for p in arch.glob("20*.html")), reverse=True)
    (arch / "index.html").write_text(env.get_template("archive.html.j2").render(dates=dates, long_date=long_date),
                                     encoding="utf-8")
    (out_dir / ".nojekyll").write_text("")
