"""Command-line entry point: collect -> rank -> detect changes -> summarise -> verify -> render.

    python -m ceemea_brief.pipeline                 # live run (LLM if GITHUB_TOKEN is set)
    python -m ceemea_brief.pipeline --no-llm        # live data, extractive summaries only
    python -m ceemea_brief.pipeline --replay data/raw/2026-10-20.json   # rerun on saved inputs
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from . import changes as changes_mod
from . import llm, relevance, render, summarise, verify
from .config import ROOT, load_config
from .models import Article, CountryBrief
from .sources import bis, fx, imf, news


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {msg}", flush=True)


# ---------------------------------------------------------------- collect
def collect(cfg: dict, now: datetime) -> dict:
    """Fetch every source. A failing source is recorded, never fatal."""
    countries = cfg["countries"]
    years = [now.year, now.year + 1]
    raw = {"generated": now.isoformat(), "years": years, "news": {}, "imf": {}, "bis": {}, "fx": {}, "status": {}}

    ok = 0
    for c in countries:
        try:
            arts = news.fetch(c, now=now, lookback_hours=cfg["news"]["lookback_hours"])
            raw["news"][c.iso3] = [asdict(a) for a in arts]
            ok += 1
        except Exception as exc:   # noqa: BLE001
            raw["news"][c.iso3] = []
            raw["status"][f"news:{c.iso3}"] = f"failed: {exc}"[:200]
        time.sleep(0.5)            # be polite to the feed
    raw["status"]["news"] = f"{ok}/{len(countries)} feeds"

    try:
        data = imf.fetch(list(cfg["imf_indicators"]), [c.iso3 for c in countries], years)
        raw["imf"] = {ind: {iso: {str(y): v for y, v in s.items()} for iso, s in d.items()} for ind, d in data.items()}
        raw["status"]["imf"] = "ok"
    except Exception as exc:   # noqa: BLE001
        raw["status"]["imf"] = f"failed: {exc}"[:200]

    try:
        raw["bis"] = bis.fetch([c.bis for c in countries])
        raw["status"]["bis"] = f"ok ({len(raw['bis'])} rates)"
    except Exception as exc:   # noqa: BLE001
        raw["status"]["bis"] = f"failed: {exc}"[:200]

    try:
        raw["fx"] = fx.fetch([c.ccy for c in countries])
        raw["status"]["fx"] = "ok"
    except Exception as exc:   # noqa: BLE001
        raw["status"]["fx"] = f"failed: {exc}"[:200]
    return raw


# ---------------------------------------------------------------- history
def country_snapshot(c, raw: dict) -> dict:
    return {
        "imf": {ind: (raw["imf"].get(ind, {}).get(c.iso3) or {}) for ind in raw["imf"]},
        "policy_rate": raw["bis"].get(c.bis) if c.bis else None,
        "fx": (raw["fx"].get("rates") or {}).get(c.ccy),
        "articles": [news.article_hash(a["title"]) for a in raw["news"].get(c.iso3, [])],
    }


def previous_snapshot(history_dir: Path, run_date: str) -> tuple[str | None, dict]:
    files = sorted(p for p in history_dir.glob("*.json") if p.stem < run_date)
    if not files:
        return None, {}
    return files[-1].stem, json.loads(files[-1].read_text())


# ---------------------------------------------------------------- per-country
def data_lines(c, snap: dict, raw: dict, labels: dict) -> list[str]:
    lines = []
    for ind, meta in labels.items():
        for y, v in sorted((snap["imf"].get(ind) or {}).items()):
            lines.append(f"{meta['label']} {y} (IMF WEO forecast): {v:.1f}{meta['unit'].replace('% GDP', '% of GDP')}")
    pr = snap["policy_rate"]
    if pr:
        lines.append(f"Policy rate (BIS, {pr['period']}): {pr['rate']:.2f}%")
    else:
        lines.append("Policy rate: not published by BIS for this country")
    if snap["fx"]:
        lines.append(f"{c.ccy} per USD (open.er-api.com, {raw['fx'].get('as_of', '')[:16]}): {snap['fx']:.4g}")
    return lines


def build_country(c, raw, prev_snap, cfg, *, now, use_llm, client=None) -> tuple[CountryBrief, dict]:
    labels = cfg["imf_indicators"]
    snap = country_snapshot(c, raw)
    prev = prev_snap.get(c.iso3) if prev_snap else None
    seen = set(prev.get("articles", [])) if prev else set()

    arts = [Article(**a) for a in raw["news"].get(c.iso3, [])]
    ranked = relevance.rank(arts, c.iso3, now=now, seen=seen, max_items=cfg["news"]["max_items"],
                            keyfn=news.article_hash)
    chg = changes_mod.detect(c, snap, prev, labels)
    lines = data_lines(c, snap, raw, labels)

    brief = summarise.summarise(c, ranked, lines, chg, use_llm=use_llm, client=client)
    brief.articles, brief.changes = ranked, chg
    brief.macro = {"snapshot": snap, "lines": lines}
    verify.verify(brief, "\n".join(lines + [x.text for x in chg]))
    return brief, snap


# ---------------------------------------------------------------- main
def run(*, run_date: str, raw: dict, cfg: dict, use_llm: bool, out_dir: Path, history_dir: Path,
        client=None, label: str = "") -> list[CountryBrief]:
    now = datetime.fromisoformat(raw["generated"])
    prev_date, prev_snap = previous_snapshot(history_dir, run_date)
    briefs, snaps = [], {}
    for c in cfg["countries"]:
        log(f"{c.name}: {len(raw['news'].get(c.iso3, []))} headlines")
        b, snaps[c.iso3] = build_country(c, raw, prev_snap, cfg, now=now, use_llm=use_llm, client=client)
        briefs.append(b)

    history_dir.mkdir(parents=True, exist_ok=True)
    (history_dir / f"{run_date}.json").write_text(json.dumps(snaps, indent=1, default=str))

    report = {
        "run_date": run_date, "generated": raw["generated"], "previous": prev_date,
        "status": raw["status"], "years": raw["years"], "label": label,
        "method": next((b.method for b in briefs if b.method.startswith("llm")), "extractive"),
        "bullets": sum(len(b.bullets) for b in briefs),
        "flags": sum(b.flag_count for b in briefs),
        "fallbacks": [b.country.name for b in briefs if b.note.startswith("LLM step failed")],
    }
    render.write_site(briefs, report, cfg, out_dir)
    log(f"done: {report['bullets']} bullets, {report['flags']} flags, method {report['method']}")
    return briefs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the CEEMEA daily macro brief.")
    ap.add_argument("--date", default=date.today().isoformat(), help="run date, YYYY-MM-DD")
    ap.add_argument("--replay", type=Path, help="rerun on a saved raw-input file instead of fetching")
    ap.add_argument("--no-llm", action="store_true", help="extractive summaries only")
    ap.add_argument("--out", type=Path, default=ROOT / "docs")
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--label", default="", help="banner text, e.g. 'TEST DATA'")
    args = ap.parse_args(argv)

    cfg = load_config()
    if args.replay:
        raw = json.loads(args.replay.read_text())
    else:
        raw = collect(cfg, datetime.now(timezone.utc))
        (args.data / "raw").mkdir(parents=True, exist_ok=True)
        (args.data / "raw" / f"{args.date}.json").write_text(json.dumps(raw, indent=1))
    use_llm = not args.no_llm and llm.available()
    if not args.no_llm and not use_llm:
        log("GITHUB_TOKEN not set: using extractive summaries")
    client = llm.GitHubModels() if use_llm else None   # one client, so calls are paced
    run(run_date=args.date, raw=raw, cfg=cfg, use_llm=use_llm, out_dir=args.out,
        history_dir=args.data / "history", label=args.label, client=client)
    return 0


if __name__ == "__main__":
    sys.exit(main())
