"""Economics concepts: tag each country brief, store it, and build the topic archive.

Tagging is a transparent keyword match (no model), so the same story is always
filed under the same concepts.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

CONCEPTS = {
    "monetary-policy": {"name": "Monetary policy",
                        "terms": ["central bank", "policy rate", "interest rate", "rate cut", "rate hike", "cut its", "raised",
                                  "basis points", "bp", "monetary", "fed", "ecb", "bank of england", "bank of japan"]},
    "inflation": {"name": "Inflation",
                  "terms": ["inflation", "consumer prices", "cpi", "price growth", "deflation"]},
    "exchange-rates": {"name": "Exchange rates",
                       "terms": ["currency", "exchange rate", "devaluation", "depreciat", "appreciat", "weakened",
                                 "strengthened", "against usd", "against the dollar", "lira", "naira", "rand", "shilling",
                                 "pound", "tenge", "forint", "zloty", "yen", "yuan"]},
    "fiscal-policy": {"name": "Fiscal policy and public debt",
                      "terms": ["budget", "deficit", "fiscal", "public debt", "government debt", "tax", "spending",
                                "borrowing"]},
    "growth": {"name": "Economic growth",
               "terms": ["gdp", "growth", "recession", "output", "contraction", "expansion"]},
    "trade": {"name": "Trade and the balance of payments",
              "terms": ["export", "import", "current account", "trade", "tariff", "remittance"]},
    "development": {"name": "Development, the IMF and World Bank",
                    "terms": ["imf", "world bank", "programme", "program", "aid", "poverty"]},
    "financial-markets": {"name": "Bonds, yields and financial markets",
                          "terms": ["bond", "yield", "eurobond", "sukuk", "rating", "moody", "fitch", "s&p", "spread",
                                    "default", "investor"]},
    "labour": {"name": "Labour market",
               "terms": ["unemployment", "jobs", "employment", "wages", "payrolls", "labour", "labor"]},
    "commodities": {"name": "Commodities and energy",
                    "terms": ["oil", "gas", "opec", "gold", "wheat", "commodity", "copper", "energy"]},
}

_PATTERNS = {k: [re.compile(r"(?<![a-z])" + re.escape(t)) for t in v["terms"]] for k, v in CONCEPTS.items()}


def tag(text: str, min_hits: int = 1) -> list[str]:
    """Concept slugs whose terms appear in the text, strongest match first."""
    low = text.lower()
    hits = [(sum(1 for p in pats if p.search(low)), k) for k, pats in _PATTERNS.items()]
    return [k for n, k in sorted(hits, key=lambda t: -t[0]) if n >= min_hits]


def brief_record(b, run_date: str) -> dict:
    """Compact, storable version of one country's brief, with its concept tags."""
    text = " ".join([b.headline] + [x.text for x in b.bullets] + [c.text for c in b.changes] + [b.bond_angle])
    return {
        "date": run_date, "iso3": b.country.iso3, "country": b.country.name, "group": b.country.group,
        "headline": b.headline, "method": b.method,
        "bullets": [{"text": x.text, "sources": x.sources, "flags": x.flags} for x in b.bullets],
        "bond_angle": b.bond_angle,
        "changes": [c.text for c in b.changes],
        "articles": [{"id": a.id, "title": a.title, "publisher": a.publisher, "url": a.url, "score": a.score}
                     for a in b.articles],
        "lines": b.macro.get("lines", []),
        "tags": tag(text)[:3],                       # the three strongest concepts only
    }


def save_day(briefs, run_date: str, data_dir: Path) -> Path:
    folder = data_dir / "briefs"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{run_date}.json"
    path.write_text(json.dumps([brief_record(b, run_date) for b in briefs], indent=1), encoding="utf-8")
    return path


def load_days(data_dir: Path, start: str | None = None, end: str | None = None) -> list[dict]:
    """All stored country records between two ISO dates (inclusive), oldest first."""
    out = []
    for p in sorted((data_dir / "briefs").glob("20*.json")):
        if (start and p.stem < start) or (end and p.stem > end):
            continue
        out += json.loads(p.read_text(encoding="utf-8"))
    return out


def write_archive(data_dir: Path, out_dir: Path, weekly_items: list[dict] | None = None) -> dict:
    """docs/topics/index.html and one page per concept. Returns {slug: count}."""
    from .render import env, long_date
    records = load_days(data_dir)
    by_topic: dict = {k: [] for k in CONCEPTS}
    for r in reversed(records):                       # newest first
        for t in r.get("tags", []):
            by_topic.setdefault(t, []).append(r)
    folder = out_dir / "topics"
    folder.mkdir(parents=True, exist_ok=True)
    page = env.get_template("topics.html.j2")
    for slug, meta in CONCEPTS.items():
        (folder / f"{slug}.html").write_text(page.render(mode="topic", slug=slug, meta=meta, items=by_topic[slug],
                                                         concepts=CONCEPTS, long_date=long_date,
                                                         weekly=[w for w in (weekly_items or []) if w.get("concept") == slug]),
                                             encoding="utf-8")
    counts = {k: len(v) for k, v in by_topic.items()}
    (folder / "index.html").write_text(page.render(mode="index", concepts=CONCEPTS, counts=counts,
                                                   latest={k: (v[0]["date"] if v else None) for k, v in by_topic.items()},
                                                   long_date=long_date), encoding="utf-8")
    return counts
