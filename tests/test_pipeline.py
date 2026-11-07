"""Tests for every pipeline stage, using fictional fixture data (no network)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ceemea_brief import changes, pipeline, relevance, summarise, verify
from ceemea_brief.config import load_config
from ceemea_brief.models import Article, Bullet, Country, CountryBrief
from ceemea_brief.sources import bis, fx, imf, news

import sys
sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
import make_fixtures as fx_data  # noqa: E402
from fake_llm import FakeClient  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 20, 6, tzinfo=timezone.utc)
NTH = Country("Northland", "CEE", "NTH", "NT", "NTD", "Northland economy")


@pytest.fixture(scope="session")
def cfg(tmp_path_factory):
    p = tmp_path_factory.mktemp("cfg") / "c.yaml"
    p.write_text(fx_data.COUNTRIES)
    return load_config(p)


# ------------------------------------------------------------------ sources
def test_news_parse_drops_old_and_duplicate_items():
    arts = news.parse_feed(fx_data.RSS, NTH, now=NOW, lookback_hours=36)
    titles = [a.title for a in arts]
    assert "Northland central bank cuts interest rate by 50bp to 5.25%" in titles
    assert len([t for t in titles if "cuts interest rate" in t]) == 1     # duplicate dropped
    assert not any("Old Northland" in t for t in titles)                   # too old
    assert arts[0].publisher == "Test Wire"
    assert "4.1%" in arts[0].snippet


def test_split_title_handles_publishers():
    assert news.split_title("A - B - Reuters", "Reuters") == ("A - B", "Reuters")
    assert news.split_title("Plain title", "") == ("Plain title", "")


def test_imf_parse_filters_countries_and_years():
    payload = {"values": {"NGDP_RPCH": {"KEN": {"2025": 4.8, "2026": 5.0, "2027": 5.1}, "USA": {"2026": 2.0}}}}
    out = imf.parse(payload, "NGDP_RPCH", ["KEN", "NGA"], [2026, 2027])
    assert out == {"KEN": {2026: 5.0, 2027: 5.1}, "NGA": {}}


def test_bis_parse_api_and_bulk_column_styles():
    api = "FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE\nM,PL,2026-08,5.0\nM,PL,2026-09,4.75\nM,TR,2026-09,40.5\nM,US,2026-09,4.0\n"
    bulk = ('"FREQ:Frequency","REF_AREA:Reference area","TIME_PERIOD:Time period","OBS_VALUE:Value"\n'
            '"D:Daily","PL:Poland","2026-09-30","4.75"\n"M:Monthly","PL:Poland","2026-09","4.75"\n')
    a = bis.latest(bis.parse_csv(api, ["PL", "TR"]))
    assert a["PL"] == {"period": "2026-09", "rate": 4.75, "change_bp": -25}
    assert a["TR"]["change_bp"] is None
    b = bis.parse_csv(bulk, ["PL"])
    assert b["PL"] == [("2026-09", 4.75)]          # daily row ignored


def test_bis_rejects_unknown_format():
    with pytest.raises(ValueError):
        bis.parse_csv("a,b\n1,2\n", ["PL"])


def test_fx_parse():
    out = fx.parse({"result": "success", "time_last_update_utc": "x", "rates": {"KES": 129.1, "USD": 1}}, ["KES", "NGN"])
    assert out["rates"] == {"KES": 129.1}
    with pytest.raises(ValueError):
        fx.parse({"result": "error"}, ["KES"])


# ------------------------------------------------------------------ ranking and changes
def test_relevance_prefers_bond_news_and_penalises_noise():
    bond = Article("", "Fitch downgrades Kenya; eurobond yields jump", "W", "", "")
    sport = Article("", "Kenya football match result", "W", "", "")
    assert relevance.score(bond) > 5 > relevance.score(sport)


def test_rank_assigns_ids_and_penalises_seen():
    arts = [Article("", "IMF review agreed", "W", "", ""), Article("", "Budget deficit widens", "W", "", "")]
    seen = {news.article_hash("IMF review agreed")}
    ranked = relevance.rank(arts, "KEN", now=None, seen=seen, max_items=5, keyfn=news.article_hash)
    assert [a.id for a in ranked] == ["KEN-1", "KEN-2"]
    assert ranked[0].title == "Budget deficit widens"


def test_changes_detects_rate_fx_and_imf_revision():
    today = {"policy_rate": {"period": "2026-10", "rate": 5.25, "change_bp": -50}, "fx": 4.10,
             "imf": {"NGDP_RPCH": {"2026": 3.2}}}
    prev = {"policy_rate": {"period": "2026-09", "rate": 5.75}, "fx": 4.00, "imf": {"NGDP_RPCH": {"2026": 3.4}}}
    out = changes.detect(NTH, today, prev, {"NGDP_RPCH": {"label": "Real GDP growth", "unit": "%"}})
    kinds = {c.metric for c in out}
    assert kinds == {"policy_rate", "fx", "imf:NGDP_RPCH:2026"}
    assert any("cut 50bp" in c.text for c in out)
    assert any("weakened 2.4%" in c.text for c in out)


def test_changes_first_run_uses_bis_change_and_small_fx_moves_ignored():
    today = {"policy_rate": {"period": "2026-10", "rate": 5.25, "change_bp": -50}, "fx": 4.0, "imf": {}}
    out = changes.detect(NTH, today, None, {})
    assert [c.metric for c in out] == ["policy_rate"] and "cut 50bp" in out[0].text
    assert changes.fx_move(4.0, 4.02) == -0.5


# ------------------------------------------------------------------ verification
def test_verify_flags_unsourced_and_miscited_numbers():
    arts = [Article("KEN-1", "Inflation at 4.1% in September", "W", "", ""), Article("KEN-2", "Budget gap of 5.9%", "W", "", "")]
    brief = CountryBrief(NTH, "h", [
        Bullet("Inflation was 4.1%.", ["KEN-1"]),
        Bullet("Inflation was 4.1%.", ["KEN-2"]),
        Bullet("Growth will hit 7.2%.", ["KEN-1"]),
        Bullet("Debt is 70.0% of GDP in 2026.", ["DATA"]),
        Bullet("No citation here.", []),
        Bullet("Bad id.", ["KEN-9"]),
    ], "", "llm:test", articles=arts)
    verify.verify(brief, "Govt debt 2026: 70.0% of GDP")
    flags = [b.flags for b in brief.bullets]
    assert flags[0] == [] and flags[3] == []                 # 2026 treated as a year, not a figure
    assert "not the one cited" in flags[1][0]
    assert "not found in any source" in flags[2][0]
    assert flags[4] == ["No source cited."]
    assert "unknown source KEN-9" in flags[5][0]


def test_numbers_allows_rounding_and_ignores_codes():
    assert verify.numbers("Q3 GDP grew 1,200 or −3.5 per G20 KEN-2") == ["1200", "3.5"]
    assert verify._matches("4.1", {"4.13"}) and not verify._matches("4.2", {"4.13"})


# ------------------------------------------------------------------ summarising
def test_extract_json_tolerates_fences():
    assert summarise.extract_json('Sure:\n```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(ValueError):
        summarise.extract_json("no json")


def test_prompt_contains_numbered_sources_and_rules():
    arts = [Article("NTH-1", "Rate cut", "W", "", "2026-10-20T04:00:00")]
    p = summarise.build_prompt(NTH, arts, ["Policy rate: 5.25%"], [])
    assert "[NTH-1] Rate cut (W, 2026-10-20)" in p and "Policy rate: 5.25%" in p
    assert "ONLY the numbered sources" in summarise.SYSTEM


def test_llm_failure_falls_back_to_extractive():
    class Broken:
        def complete(self, *a, **k):
            raise RuntimeError("HTTP 500")
    b = summarise.summarise(NTH, [Article("NTH-1", "Rate cut", "W", "", "")], [], [], use_llm=True, client=Broken())
    assert b.method == "extractive" and b.note.startswith("LLM step failed")


# ------------------------------------------------------------------ end to end
def test_full_run_with_fake_llm(tmp_path, cfg):
    hist = tmp_path / "history"
    hist.mkdir()
    (hist / "2026-10-19.json").write_text(json.dumps(fx_data.PREVIOUS))
    client = FakeClient()
    briefs = pipeline.run(run_date="2026-10-20", raw=fx_data.raw_inputs(), cfg=cfg, use_llm=True,
                          out_dir=tmp_path / "docs", history_dir=hist, client=client, label="TEST")
    by = {b.country.iso3: b for b in briefs}

    # Northland: sports story ranked out; the invented 75bp is flagged, sourced figures pass
    assert all("football" not in a.title for a in by["NTH"].articles)
    nth_flags = [f for b in by["NTH"].bullets for f in b.flags]
    assert nth_flags == ["Figure 75 not found in any source; check before use."]
    assert any(c.metric == "policy_rate" for c in by["NTH"].changes)
    assert any(c.metric.startswith("imf:NGDP_RPCH") for c in by["NTH"].changes)

    # Eastovia: FX move computed (49.6 -> 51.2 = 3.1% weaker) and cited correctly via DATA
    assert any("weakened 3.1%" in c.text for c in by["EST"].changes)
    assert by["EST"].flag_count == 0

    # Southmark: unusable model reply -> extractive fallback, recorded on the page
    assert by["STH"].method == "extractive" and "fell back" in by["STH"].note

    html = (tmp_path / "docs" / "index.html").read_text()
    assert "Northland" in html and "⚑" in html and "TEST" in html
    assert (tmp_path / "docs" / "archive" / "2026-10-20.html").exists()
    assert json.loads((tmp_path / "docs" / "latest.json").read_text())["report"]["flags"] == 1
    assert (hist / "2026-10-20.json").exists()


def test_github_models_client_sends_openai_format(monkeypatch):
    from ceemea_brief import llm
    sent = {}

    class Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": '{"ok": 1}'}}]}

    def fake_post(url, headers, json, timeout):
        sent.update(url=url, headers=headers, body=json)
        return Resp()

    monkeypatch.setattr(llm.requests, "post", fake_post)
    monkeypatch.setattr(llm, "PAUSE_SECONDS", 0)
    c = llm.ChatClient(token="t", model="gemini-3.8-flash")
    assert c.complete("sys", "user") == '{"ok": 1}'
    assert sent["url"].startswith("https://generativelanguage.googleapis.com/")
    assert sent["headers"]["Authorization"] == "Bearer t"
    assert [m["role"] for m in sent["body"]["messages"]] == ["system", "user"]


# ------------------------------------------------------------------ global drivers and deep dives
def test_oecd_cpi_keeps_most_recent_dataset_per_country():
    from ceemea_brief.sources import oecd
    old = ('"REF_AREA:Reference area","FREQ:Frequency","MEASURE:Measure","EXPENDITURE:Expenditure","TIME_PERIOD:Time period","OBS_VALUE:Value"\n'
           '"USA:United States","M:Monthly","CPI:Consumer price index","_T:Total","2026-08","2.9"\n'
           '"USA:United States","M:Monthly","CPI:Consumer price index","_T:Total","2026-09","3.0"\n'
           '"DEU:Germany","M:Monthly","CPI:Consumer price index","_T:Total","2026-06","2.0"\n'
           '"DEU:Germany","M:Monthly","CPI:Consumer price index","CP045:Electricity","2026-06","9.9"\n')
    new = ("REF_AREA,FREQ,MEASURE,EXPENDITURE,TIME_PERIOD,OBS_VALUE\n"
           "DEU,M,CPI,_T,2026-09,2.3\nDEU,M,CPI,_TXCP01_NRG,2026-09,2.7\nUSA,M,CPI,_T,2026-07,2.8\n")
    out = oecd.parse_cpi([("OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0", oecd._rows(new)),
                          ("OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0", oecd._rows(old))])
    assert out["DEU"]["headline"]["value"] == 2.3 and out["DEU"]["headline"]["flow"] == "COICOP 2018"
    assert out["DEU"]["core"]["value"] == 2.7
    assert out["USA"]["headline"]["period"] == "2026-09"          # old dataset is more recent for the US
    assert "CP045" not in str(out["DEU"])                          # categories outside the four are ignored


def test_oecd_yields_and_start_period():
    from datetime import date
    from ceemea_brief.sources import oecd
    rows = oecd._rows("REF_AREA,FREQ,MEASURE,TIME_PERIOD,OBS_VALUE\nGBR,M,IRLT,2026-08,4.5\nGBR,M,IRLT,2026-09,4.62\nGBR,M,IRST,2026-09,4.0\n")
    y = oecd.parse_yields(rows)["GBR"]
    assert (y["value"], y["date"], y["prev"]) == (4.62, "2026-09", 4.5)
    assert oecd.start_period(date(2026, 2, 10), 4) == "2025-10"


def test_worldbank_takes_latest_non_empty_year():
    from ceemea_brief.sources import worldbank
    payload = [{"page": 1}, [
        {"countryiso3code": "KEN", "date": "2025", "value": None},
        {"countryiso3code": "KEN", "date": "2024", "value": 21.2},
        {"countryiso3code": "KEN", "date": "2023", "value": 21.9},
        {"countryiso3code": "XXX", "date": "2025", "value": 1.0}]]
    assert worldbank.parse(payload, ["KEN", "POL"]) == {"KEN": {"value": 21.2, "year": 2024}}
    with pytest.raises(ValueError):
        worldbank.parse([{"message": [{"value": "Invalid value"}]}], ["KEN"])


def test_treasury_csv_parse():
    from ceemea_brief.sources import treasury
    text = '﻿Date,"1 Mo","10 Yr","30 Yr"\n10/17/2026,4.1,4.33,4.8\n10/16/2026,4.1,4.29,4.7\n10/15/2026,4.1,,4.7\n'
    assert treasury.parse(text) == [("2026-10-16", 4.29), ("2026-10-17", 4.33)]


def test_yield_change_detected_and_small_moves_ignored():
    today = {"yield": {"value": 4.41, "date": "2026-10-19", "source": "US Treasury", "freq": "daily"}, "imf": {}}
    big = changes.detect(NTH, today, {"yield": {"value": 4.29, "date": "2026-10-16"}}, {})
    small = changes.detect(NTH, today, {"yield": {"value": 4.39, "date": "2026-10-16"}}, {})
    assert [c.metric for c in big] == ["yield"] and "rose 12bp to 4.41%" in big[0].text
    assert small == []


def test_peer_averages_and_highlights(cfg):
    from ceemea_brief import deepdive
    wb = fx_data.raw_inputs()["worldbank"]
    avgs = deepdive.peer_averages(wb, cfg)
    assert avgs["SL.UEM.TOTL.ZS"]["ceemea"] == round((3.0 + 7.1 + 5.6) / 3, 2)   # Westland excluded
    assert avgs["SL.UEM.TOTL.ZS"]["developed"] == 4.2
    est = next(c for c in cfg["countries"] if c.iso3 == "EST")
    lines = deepdive.highlights(est, wb, avgs, cfg)
    assert len(lines) == 3 and any(l.startswith("Remittances received is 6.1% of GDP (2024), well above") for l in lines)
    assert deepdive.sparkline([["a", 1.0], ["b", 3.0]]) == "0.0,26.0 120.0,2.0"
    assert deepdive.sparkline([["a", 1.0]]) == ""


def test_prompt_marks_global_drivers(cfg):
    west = next(c for c in cfg["countries"] if c.iso3 == "WST")
    p = summarise.build_prompt(west, [], ["Policy rate: 3.75%"], [])
    assert "GLOBAL DRIVER" in p and "emerging-market borrowers" in p
    assert "CEEMEA SOVEREIGN" in summarise.build_prompt(NTH, [], [], [])


def test_full_run_writes_global_section_and_deep_dives(tmp_path, cfg):
    hist = tmp_path / "history"
    hist.mkdir()
    (hist / "2026-10-19.json").write_text(json.dumps(fx_data.PREVIOUS))
    briefs = pipeline.run(run_date="2026-10-20", raw=fx_data.raw_inputs(), cfg=cfg, use_llm=True,
                          out_dir=tmp_path / "docs", history_dir=hist, client=FakeClient())
    west = next(b for b in briefs if b.country.iso3 == "WST")
    assert any(c.metric == "yield" for c in west.changes) and west.flag_count == 0
    assert any("10-year government bond yield (Test Treasury, daily, 2026-10-19): 4.41%" in l for l in west.macro["lines"])
    html = (tmp_path / "docs" / "index.html").read_text()
    assert "Global drivers" in html and "Why it matters for EM" in html and 'href="country/WST.html"' in html
    arch = (tmp_path / "docs" / "archive" / "2026-10-20.html").read_text()
    assert 'href="../country/NTH.html"' in arch
    page = (tmp_path / "docs" / "country" / "NTH.html").read_text()
    assert "Inflation by component" in page and "7.3" in page and "What stands out" in page
    assert "Figure 75 not found" in page                     # flags carry through to the deep dive
    assert "does not publish a monthly inflation breakdown" in (tmp_path / "docs" / "country" / "EST.html").read_text()
    assert "Westland" in (tmp_path / "docs" / "country" / "index.html").read_text()
