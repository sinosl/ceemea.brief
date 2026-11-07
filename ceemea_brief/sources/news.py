"""Headlines from Google News RSS, one search per country."""
from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import feedparser

from ..models import Article, Country
from . import http

FEED = "https://news.google.com/rss/search?q={q}+when:2d&hl=en-GB&gl=GB&ceid=GB:en"
_TAG = re.compile(r"<[^>]+>")


def feed_url(country: Country) -> str:
    return FEED.format(q=quote_plus(country.query))


def parse_feed(xml: str | bytes, country: Country, *, now: datetime, lookback_hours: int) -> list[Article]:
    """Turn RSS XML into Articles, dropping old items and duplicate headlines."""
    feed = feedparser.parse(xml)
    cutoff = now - timedelta(hours=lookback_hours)
    seen: set[str] = set()
    out: list[Article] = []
    for entry in feed.entries:
        published = _entry_time(entry)
        if published and published < cutoff:
            continue
        title, publisher = split_title(entry.get("title", ""), entry.get("source", {}).get("title", ""))
        key = normalise(title)
        if not title or key in seen:
            continue
        seen.add(key)
        out.append(Article(
            id="",   # assigned after ranking
            title=title,
            publisher=publisher,
            url=entry.get("link", ""),
            published=published.isoformat() if published else "",
            snippet=_clean(entry.get("summary", ""))[:400],
        ))
    return out


def fetch(country: Country, *, now: datetime, lookback_hours: int) -> list[Article]:
    resp = http.get(feed_url(country))
    return parse_feed(resp.content, country, now=now, lookback_hours=lookback_hours)


def split_title(title: str, publisher: str) -> tuple[str, str]:
    """Google News titles end with ' - Publisher'; split that off."""
    title = html.unescape(title).strip()
    if publisher and title.endswith(" - " + publisher):
        return title[: -len(publisher) - 3].strip(), publisher
    if " - " in title:
        head, tail = title.rsplit(" - ", 1)
        if len(tail) <= 40:
            return head.strip(), publisher or tail.strip()
    return title, publisher


def normalise(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


def article_hash(title: str) -> str:
    return hashlib.sha1(normalise(title).encode()).hexdigest()[:12]


def _entry_time(entry) -> datetime | None:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime(*t[:6], tzinfo=timezone.utc) if t else None


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", text))).strip()
