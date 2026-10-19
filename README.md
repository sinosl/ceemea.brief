# CEEMEA Morning Brief

An automated daily macro brief for ten emerging-market sovereigns in Central and Eastern Europe, Central Asia, the Middle East and Africa. It is written for a debt portfolio manager who has two minutes before the open.

**Live brief:** `https://<your-username>.github.io/ceemea-brief/` *(published by GitHub Actions every weekday morning)*

Countries: Poland, Hungary, Romania, Türkiye, Kazakhstan, Egypt, Saudi Arabia, Nigeria, Kenya, South Africa (edit `config/countries.yaml` to change).

---

## What it does

```
 Google News RSS ─┐
 IMF WEO (API) ───┤   collect      rank           detect          summarise        verify          render
 BIS policy rates ┼──► raw JSON ──► headlines ──► changes vs ───► LLM, cites ───► every figure ──► HTML site
 FX (open API) ───┘   (saved)      by bond        last brief     numbered        checked          + archive
                                    relevance      (no LLM)       sources only    against source   + JSON
```

1. **Collect.** For each country the pipeline pulls:
   - recent headlines from a news search tuned to bond-moving topics;
   - IMF World Economic Outlook forecasts for growth, inflation, government debt, fiscal balance and current account;
   - the central bank policy rate from the BIS;
   - spot FX against the dollar.

   Raw inputs are saved to `data/raw/` so any day can be re-run exactly. A source that fails is logged on the page, and the rest of the brief is still built.
2. **Rank.** Headlines are scored by a transparent keyword model in `relevance.py`. IMF programmes, ratings, eurobonds, deficits and rate decisions score up; sport and celebrity stories score down; stories already in yesterday's brief are pushed down. The ranking is deliberately not an LLM, so it is reproducible and cheap, and the weights are easy to argue with.
3. **Detect changes.** Policy-rate moves, FX moves over 1% and IMF forecast revisions are computed directly from today's data against the previous run's. The "What changed" section is never written by the model.
4. **Summarise.** A language model (GPT-4.1 mini through [GitHub Models](https://github.com/marketplace/models), free and authenticated with the workflow's built-in token, so there is no API key) writes a headline, two to four bullets and a "bond angle" for each country. It sees only the numbered sources and the data block, and must cite a source id such as `[KEN-2]` or `DATA` for every bullet. If no model is available, or its reply can't be used, that country falls back to an extractive summary (computed changes plus top headlines verbatim), and the page says so.
5. **Verify.** Before publishing, `verify.py` checks every bullet:
   - it cites a source, and every cited id exists;
   - every number in the text appears in the cited source, allowing for rounding.

   Anything that fails is shown with a ⚑ flag, not deleted, so the reader knows which figures to check. The flag count appears at the top of the page.
6. **Render.** The pipeline produces a static HTML page with a dashboard table, the list of changes and a card for each country, with a link to every source. Past briefs are kept in `docs/archive/`, and a machine-readable copy is written to `docs/latest.json`.

## Why it is built this way

| Design choice | Reason |
|---|---|
| The model only sees numbered sources | Its job is to summarise, not recall. Out-of-date "knowledge" is the main way a macro summary goes wrong. |
| Numbers are checked against sources, not trusted | Language models can be fluent and wrong at the same time. Flagging an unsupported figure is cheaper than a PM acting on it. |
| Changes are computed, not generated | "The central bank cut 50bp" is a fact in the data, so there is no reason to let a model write it. |
| Keyword ranking instead of LLM ranking | It is reproducible, auditable and free. The weights in `relevance.py` sit in one dictionary. |
| A failure in one stage never blocks the brief | A partial brief at 06:30 is worth more than a perfect one at 09:00. Failures are reported on the page. |
| Raw inputs are saved daily | `--replay` rebuilds any day's brief from what was actually fetched. |

## Project layout

```
ceemea_brief/
  sources/      news.py · imf.py · bis.py · fx.py · http.py   (one module per data source)
  relevance.py  headline scoring
  changes.py    data changes since the previous brief
  summarise.py  prompt, JSON parsing, extractive fallback
  llm.py        model client (GitHub Models, OpenAI-compatible format)
  verify.py     citation and figure checks
  render.py     HTML output (Jinja2 templates in templates/)
  pipeline.py   command-line entry point that runs the stages above
config/countries.yaml          countries, search queries, indicators
tests/                         17 tests on fictional fixture data; no network or API key needed
.github/workflows/daily-brief.yml   weekday 05:17 UTC run: test, build, commit, publish
docs/                          the published site (GitHub Pages)
data/raw/, data/history/       saved inputs and daily snapshots used for change detection
```

## Running it

```bash
pip install -r requirements.txt
python -m pytest -q                                   # 17 tests, offline
python tests/fixtures/demo.py /tmp/demo               # demo page from fictional data
python -m ceemea_brief.pipeline --no-llm              # live data, extractive summaries
GITHUB_TOKEN=<token with models:read> python -m ceemea_brief.pipeline   # live data, LLM summaries
python -m ceemea_brief.pipeline --replay data/raw/2026-10-20.json --date 2026-10-20
```

**Cost:** nothing. GitHub Actions, GitHub Pages and GitHub Models are free for a public repository on a personal account. The brief makes about 10 model calls a day, spaced five seconds apart to stay inside the free-tier rate limits. The model is set in one place (`CEEMEA_MODEL`), and the client uses the standard chat-completions format, so moving to another provider changes only `llm.py`.

## Limitations and next steps

- **News coverage.** Headlines come from a news aggregator, so stories behind paywalls appear as headlines only. Adding a Bloomberg or Reuters feed would be the obvious upgrade.
- **Policy-rate coverage.** The BIS does not publish policy rates for Egypt, Kazakhstan, Kenya or Nigeria. The next step is to parse those central banks' own releases.
- **IMF data frequency.** IMF forecasts change only twice a year (April and October), so revisions show up around those dates.
- **Bond pricing.** Adding sovereign eurobond spreads (for example, from an index provider) would let the "bond angle" refer to actual pricing.
- **Verification limits.** The check catches unsupported numbers, not wrong wording around correct numbers. Review of the text is still needed.

*Research tool only; not investment advice.*
