"""Plain data containers passed between pipeline stages."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Country:
    name: str
    region: str
    iso3: str
    bis: str
    ccy: str
    query: str


@dataclass
class Article:
    id: str              # short citation id, e.g. "KEN-3"
    title: str
    publisher: str
    url: str
    published: str       # ISO timestamp
    snippet: str = ""
    score: float = 0.0   # bond-relevance score


@dataclass
class Change:
    """A data-driven change since the previous run (no LLM involved)."""
    metric: str
    before: Optional[float]
    after: Optional[float]
    text: str


@dataclass
class Bullet:
    text: str
    sources: list[str]
    flags: list[str] = field(default_factory=list)   # filled by verify.py


@dataclass
class CountryBrief:
    country: Country
    headline: str
    bullets: list[Bullet]
    bond_angle: str
    method: str                       # "llm:<model>" or "extractive"
    articles: list[Article] = field(default_factory=list)
    macro: dict = field(default_factory=dict)
    changes: list[Change] = field(default_factory=list)
    angle_sources: list[str] = field(default_factory=list)
    angle_flags: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def flag_count(self) -> int:
        return sum(len(b.flags) for b in self.bullets) + len(self.angle_flags)

    def to_dict(self) -> dict:
        return asdict(self)
