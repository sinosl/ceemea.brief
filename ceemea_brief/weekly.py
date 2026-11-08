"""Weekly "Economics in the news": three stories of the week explained with A-level concepts.

Runs on Fridays (or with --weekly). Inputs are the week's stored country
briefs (data/briefs). The model picks three stories, names the economic
concept each illustrates and explains the mechanism. As with the daily brief,
it sees only the numbered items, every figure it writes is checked against the
item it cites, and if the model is unavailable a computed fallback is
published instead.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from . import summarise, topics, verify

SYSTEM = """You write a weekly 'Economics in the news' page for readers learning economics.
From the numbered items (each is one country's news on one day), pick the THREE stories that best
illustrate core macroeconomic concepts. Use three different countries where possible.

Rules:
- Use ONLY the information in the items. No outside knowledge.
- Copy numbers exactly as they appear in the item you cite. Do not compute new figures.
- Explain the economics clearly: name the mechanism, not just the event.
- "concept" must be one of the concept keys given.
Return JSON only."""

SCHEMA = """{"stories": [
  {"item": "W3",
   "title": "<= 10 words",
   "what_happened": "two sentences describing the news, citing figures from the item",
   "concept": "<concept key>",
   "explanation": "two or three sentences linking the event to economic theory"}
]}"""


def week_id(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_range(d: date) -> tuple[str, str]:
    monday = d - timedelta(days=d.weekday())
    return monday.isoformat(), (monday + timedelta(days=6)).isoformat()


def candidates(records: list[dict]) -> list[dict]:
    """Number the week's country-day records W1..Wn, most newsworthy first (computed score)."""
    scored = []
    for r in records:
        top = sorted((a.get("score", 0) for a in r.get("articles", [])), reverse=True)[:3]
        scored.append((sum(top) + 3 * len(r.get("changes", [])), r))
    scored.sort(key=lambda t: -t[0])
    out = []
    for i, (score, r) in enumerate(scored[:30], 1):
        out.append(dict(r, wid=f"W{i}", score=round(score, 1)))
    return out


def item_text(c: dict) -> str:
    return " ".join([c["headline"]] + [b["text"] for b in c["bullets"]] + c.get("changes", [])
                    + [a["title"] for a in c.get("articles", [])] + c.get("lines", []))


def build_prompt(cands: list[dict]) -> str:
    items = []
    for c in cands:
        body = "; ".join([b["text"] for b in c["bullets"]] + c.get("changes", []))
        items.append(f"[{c['wid']}] {c['country']} ({c['date']}): {c['headline']}. {body}")
    concepts = ", ".join(f"{k} ({v['name']})" for k, v in topics.CONCEPTS.items())
    return (f"ITEMS:\n" + "\n".join(items) + f"\n\nCONCEPT KEYS: {concepts}\n\n"
            f"Return JSON in this shape, with exactly three stories:\n{SCHEMA}")


def clean_story(s: dict, by_id: dict) -> dict | None:
    c = by_id.get(str(s.get("item", "")))
    if not c:
        return None
    concept = s.get("concept") if s.get("concept") in topics.CONCEPTS else (c["tags"][0] if c.get("tags") else "growth")
    story = {"item": c["wid"], "country": c["country"], "iso3": c["iso3"], "date": c["date"],
             "title": str(s.get("title", c["headline"])).strip(), "what_happened": str(s.get("what_happened", "")).strip(),
             "concept": concept, "explanation": str(s.get("explanation", "")).strip(),
             "sources": c.get("articles", [])[:3], "method": "llm"}
    pools = {c["wid"]: set(verify.numbers(item_text(c)))}
    story["flags"] = (verify.check_text(story["what_happened"], [c["wid"]], pools)
                      + verify.check_text(story["explanation"], [c["wid"]], pools))
    return story


def fallback(cands: list[dict]) -> list[dict]:
    """No model: the three highest-scoring stories from different countries, with their computed concept tags."""
    out, seen = [], set()
    for c in cands:
        if c["iso3"] in seen:
            continue
        seen.add(c["iso3"])
        out.append({"item": c["wid"], "country": c["country"], "iso3": c["iso3"], "date": c["date"],
                    "title": c["headline"], "what_happened": " ".join(b["text"] for b in c["bullets"][:2]),
                    "concept": c["tags"][0] if c.get("tags") else "growth", "explanation": "", "sources": c.get("articles", [])[:3],
                    "flags": [f for b in c["bullets"][:2] for f in b.get("flags", [])], "method": "extractive"})
        if len(out) == 3:
            break
    return out


def build(run_date: str, data_dir: Path, out_dir: Path, *, use_llm: bool, client=None) -> dict:
    d = date.fromisoformat(run_date)
    start, end = week_range(d)
    cands = candidates(topics.load_days(data_dir, start, min(end, run_date)))
    stories, note = [], ""
    if cands and use_llm and client is not None:
        try:
            reply = summarise.extract_json(client.complete(SYSTEM, build_prompt(cands), max_tokens=6000))
            by_id = {c["wid"]: c for c in cands}
            stories = [s for s in (clean_story(x, by_id) for x in reply.get("stories", [])[:3]) if s]
            if not stories:
                raise ValueError("no usable stories in reply")
        except Exception as exc:   # noqa: BLE001
            note = f"Model step failed ({type(exc).__name__}: {str(exc)[:100]}); showing computed selection."
            stories = []
    if not stories and cands:
        stories = fallback(cands)
    digest = {"week": week_id(d), "start": start, "end": end, "run_date": run_date, "stories": stories,
              "note": note, "count": len(cands)}
    folder = data_dir / "weekly"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{digest['week']}.json").write_text(json.dumps(digest, indent=1), encoding="utf-8")
    return digest


def load_all(data_dir: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((data_dir / "weekly").glob("*-W*.json"), reverse=True)]


def write_pages(data_dir: Path, out_dir: Path) -> list[dict]:
    """docs/weekly/<week>.html for every stored digest, and docs/weekly/index.html showing the latest."""
    from .render import env, long_date
    digests = load_all(data_dir)
    folder = out_dir / "weekly"
    folder.mkdir(parents=True, exist_ok=True)
    page = env.get_template("weekly.html.j2")
    ctx = dict(concepts=topics.CONCEPTS, long_date=long_date, all_weeks=digests)
    for dg in digests:
        (folder / f"{dg['week']}.html").write_text(page.render(dg=dg, is_index=False, **ctx), encoding="utf-8")
    (folder / "index.html").write_text(page.render(dg=digests[0] if digests else None, is_index=True, **ctx),
                                       encoding="utf-8")
    return [dict(s, week=dg["week"]) for dg in digests for s in dg["stories"]]
