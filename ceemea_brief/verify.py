"""Check the summary against its sources before anyone reads it.

For every bullet (and the bond angle):
  1. it must cite at least one source, and every cited id must exist;
  2. every number in the text must appear in a cited source
     (headline/snippet text, or the DATA block for "DATA").
Anything that fails is flagged on the page, not silently dropped:
the reader decides, but knows which figures to double-check.
"""
from __future__ import annotations

import re

from .models import Article, CountryBrief

# numbers like 4, -3.5, 1,200, 27.5 - but not inside words or codes (Q3, G20, KEN-2)
NUM = re.compile(r"(?<![\w.\-])[-+−]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.\-])[-+−]?\d+(?:\.\d+)?")
YEAR = re.compile(r"^(19|20)\d{2}$")


def numbers(text: str) -> list[str]:
    """Numbers in a string, normalised (no thousands commas, ASCII minus, no sign)."""
    out = []
    for m in NUM.findall(text):
        n = m.replace(",", "").replace("−", "-").lstrip("+-")
        if n and not YEAR.match(n):
            out.append(n)
    return out


def _matches(n: str, pool: set[str]) -> bool:
    """True if n appears in pool, allowing the summary to round a sourced figure."""
    if n in pool:
        return True
    try:
        x = float(n)
    except ValueError:
        return False
    decimals = len(n.split(".")[1]) if "." in n else 0
    for p in pool:
        try:
            if round(float(p), decimals) == x:
                return True
        except ValueError:
            continue
    return False


def evidence_pools(articles: list[Article], data_text: str) -> dict[str, set[str]]:
    pools = {a.id: set(numbers(f"{a.title} {a.snippet}")) for a in articles}
    pools["DATA"] = set(numbers(data_text))
    return pools


def check_text(text: str, cited: list[str], pools: dict[str, set[str]]) -> list[str]:
    flags = []
    if not cited:
        flags.append("No source cited.")
    unknown = [c for c in cited if c not in pools]
    if unknown:
        flags.append(f"Cites unknown source {', '.join(unknown)}.")
    cited_pool = set().union(*(pools[c] for c in cited if c in pools)) if cited else set()
    all_pool = set().union(*pools.values()) if pools else set()
    for n in numbers(text):
        if _matches(n, cited_pool):
            continue
        if _matches(n, all_pool):
            flags.append(f"Figure {n} is in a source, but not the one cited.")
        else:
            flags.append(f"Figure {n} not found in any source; check before use.")
    return flags


def verify(brief: CountryBrief, data_text: str) -> CountryBrief:
    pools = evidence_pools(brief.articles, data_text)
    for b in brief.bullets:
        b.flags = check_text(b.text, b.sources, pools)
    if brief.bond_angle and brief.method.startswith("llm"):
        brief.angle_flags = check_text(brief.bond_angle, brief.angle_sources, pools)
    return brief
