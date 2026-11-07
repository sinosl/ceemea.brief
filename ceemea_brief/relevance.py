"""Rank headlines by how likely they are to matter for sovereign bonds.

A transparent keyword model, not an LLM, so ranking is reproducible and
cheap. Weights are deliberately simple and easy to argue with.
"""
from __future__ import annotations

import re
from datetime import datetime

from .models import Article

# term -> weight. Matched as whole words / phrases, case-insensitive.
WEIGHTS: dict[str, float] = {
    # official sector and ratings
    "imf": 3.0, "world bank": 2.0, "programme": 1.5, "program": 1.5, "review": 1.0,
    "moody's": 3.0, "fitch": 3.0, "s&p": 3.0, "rating": 2.5, "downgrade": 3.0, "upgrade": 3.0, "outlook": 1.0,
    # debt and markets
    "eurobond": 3.5, "bond": 2.0, "bonds": 2.0, "yield": 2.0, "yields": 2.0, "spread": 2.0, "default": 3.0,
    "restructuring": 3.0, "debt": 2.0, "refinancing": 2.5, "issuance": 2.0, "buyback": 2.5, "sukuk": 2.5,
    # monetary
    "central bank": 2.5, "interest rate": 2.5, "rate cut": 3.0, "rate hike": 3.0, "inflation": 2.0,
    "devaluation": 3.0, "currency": 1.5, "reserves": 2.0,
    # fiscal and growth
    "budget": 2.0, "deficit": 2.5, "fiscal": 2.0, "tax": 1.0, "gdp": 2.0, "growth": 1.0, "recession": 2.5,
    "current account": 2.0, "remittances": 1.5, "oil": 1.0, "opec": 1.5,
    # politics
    "election": 2.0, "sanctions": 2.5, "protest": 1.5, "minister": 1.0, "finance minister": 2.5, "coup": 3.0,
}
NOISE = ["football", "match", "celebrity", "film", "tourism tips", "recipe", "concert", "olympic", "fifa"]

_PATTERNS = {t: re.compile(r"(?<![a-z])" + re.escape(t) + r"(?![a-z])", re.I) for t in WEIGHTS}
_NOISE = [re.compile(r"(?<![a-z])" + re.escape(t) + r"(?![a-z])", re.I) for t in NOISE]


def score(article: Article, *, now: datetime | None = None, seen: set[str] | None = None,
          key: str | None = None) -> float:
    text = f"{article.title} {article.snippet}"
    s = sum(w for t, w in WEIGHTS.items() if _PATTERNS[t].search(text))
    s -= 4.0 * sum(1 for p in _NOISE if p.search(text))
    if now and article.published:
        try:
            age_h = (now - datetime.fromisoformat(article.published)).total_seconds() / 3600
            s += max(0.0, 1.0 - age_h / 36)   # up to +1 for very fresh news
        except ValueError:
            pass
    if seen is not None and key in seen:
        s -= 2.0                               # already in yesterday's brief
    return round(s, 2)


def rank(articles: list[Article], iso3: str, *, now: datetime | None, seen: set[str],
         max_items: int, keyfn) -> list[Article]:
    for a in articles:
        a.score = score(a, now=now, seen=seen, key=keyfn(a.title))
    kept = sorted((a for a in articles if a.score > 0), key=lambda a: a.score, reverse=True)[:max_items]
    for i, a in enumerate(kept, 1):
        a.id = f"{iso3}-{i}"
    return kept
