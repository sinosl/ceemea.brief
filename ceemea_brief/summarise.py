"""Turn ranked headlines and data into a short country brief.

Two back-ends:
  * LLM (GitHub Models, free; see llm.py) when GITHUB_TOKEN is available.
  * Extractive fallback otherwise, or if the model's answer can't be used:
    top headlines verbatim plus the computed changes. No model involved.

The model only sees the numbered sources and the data table, and must
cite a source id for every bullet. verify.py then checks it did.
"""
from __future__ import annotations

import json
import re

from . import llm
from .models import Article, Bullet, Change, Country, CountryBrief

DEFAULT_MODEL = llm.MODEL

SYSTEM = """You are a research associate on an emerging-markets sovereign debt team.
You write the morning brief a portfolio manager reads in two minutes.

Rules:
- Use ONLY the numbered sources and the DATA block provided. No outside knowledge, no guesses.
- Every bullet must cite at least one source id in "sources" (e.g. ["KEN-2"]) or "DATA".
- Copy numbers exactly as they appear in the sources or DATA. Do not compute new figures.
- Headlines are often vague; if a source only hints at something, say so ("reports suggest").
- Prefer what moves hard-currency bonds: IMF programmes, ratings, financing, fiscal slippage,
  FX and reserves, policy rates, politics that threatens any of these.
- If nothing material happened, say so plainly. Do not pad.
Return JSON only, no prose before or after."""

SCHEMA = """{
  "headline": "one line, <= 15 words, the single most important point today",
  "bullets": [
    {"text": "one sentence, <= 35 words", "sources": ["ISO-1"]}
  ],
  "bond_angle": "one or two sentences: why this matters (or doesn't) for the sovereign's bonds",
  "bond_angle_sources": ["ISO-1", "DATA"]
}
Give 2 to 4 bullets."""


def build_prompt(country: Country, articles: list[Article], data_lines: list[str], changes: list[Change]) -> str:
    src = "\n".join(
        f"[{a.id}] {a.title} ({a.publisher}, {a.published[:10]})" + (f"\n    {a.snippet}" if a.snippet and a.snippet not in a.title else "")
        for a in articles) or "(no relevant headlines in the last 36 hours)"
    chg = "\n".join(f"- {c.text}" for c in changes) or "- none"
    data = "\n".join(f"- {line}" for line in data_lines) or "- none"
    return (f"COUNTRY: {country.name} ({country.region})\n\n"
            f"SOURCES:\n{src}\n\n"
            f"DATA (id DATA):\n{data}\n\n"
            f"CHANGES SINCE LAST BRIEF (computed, id DATA):\n{chg}\n\n"
            f"Write the brief as JSON in this shape:\n{SCHEMA}")


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply (tolerates ``` fences)."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start:end + 1])


def from_llm_json(obj: dict, country: Country, model: str) -> CountryBrief:
    bullets = [Bullet(text=str(b["text"]).strip(), sources=[str(s) for s in b.get("sources", [])])
               for b in obj.get("bullets", []) if str(b.get("text", "")).strip()]
    if not bullets:
        raise ValueError("model returned no bullets")
    brief = CountryBrief(country=country, headline=str(obj.get("headline", "")).strip(), bullets=bullets[:4],
                         bond_angle=str(obj.get("bond_angle", "")).strip(), method=f"llm:{model}")
    brief.angle_sources = [str(s) for s in obj.get("bond_angle_sources", [])]
    return brief


def llm_brief(country, articles, data_lines, changes, *, client=None, model: str = DEFAULT_MODEL) -> CountryBrief:
    """client: any object with complete(system, user) -> str (llm.GitHubModels, or a fake in tests)."""
    client = client or llm.ChatClient(model=model)
    text = client.complete(SYSTEM, build_prompt(country, articles, data_lines, changes))
    return from_llm_json(extract_json(text), country, getattr(client, "model", model))


def extractive_brief(country: Country, articles: list[Article], changes: list[Change]) -> CountryBrief:
    """No-model fallback: computed changes first, then the top headlines verbatim."""
    bullets = [Bullet(text=c.text, sources=["DATA"]) for c in changes]
    bullets += [Bullet(text=f"{a.title} ({a.publisher}).", sources=[a.id]) for a in articles[: max(0, 4 - len(bullets))]]
    if not bullets:
        bullets = [Bullet(text="No bond-relevant headlines and no data changes since the last brief.", sources=["DATA"])]
    headline = changes[0].text if changes else (articles[0].title if articles else "Quiet day")
    return CountryBrief(country=country, headline=headline, bullets=bullets,
                        bond_angle="", method="extractive")


def summarise(country, articles, data_lines, changes, *, use_llm: bool, client=None, model: str = DEFAULT_MODEL) -> CountryBrief:
    if use_llm:
        try:
            return llm_brief(country, articles, data_lines, changes, client=client, model=model)
        except Exception as exc:   # noqa: BLE001 - never lose the country because one call failed
            brief = extractive_brief(country, articles, changes)
            brief.note = f"LLM step failed ({type(exc).__name__}: {str(exc)[:120]}); fell back to extractive."
            return brief
    return extractive_brief(country, articles, changes)
