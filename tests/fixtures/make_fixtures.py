"""Build synthetic test inputs.

All countries and headlines here are FICTIONAL, so test output can never
be mistaken for real news. Run:  python tests/fixtures/make_fixtures.py
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
NOW = "2026-10-20T06:00:00+00:00"

COUNTRIES = """countries:
  - {name: Northland, region: CEE,         iso3: NTH, bis: NT, ccy: NTD, query: 'Northland economy'}
  - {name: Eastovia,  region: Middle East, iso3: EST, bis: '', ccy: EVP, query: 'Eastovia economy'}
  - {name: Southmark, region: Africa,      iso3: STH, bis: SM, ccy: SMR, query: 'Southmark economy'}
imf_indicators:
  NGDP_RPCH:   {label: Real GDP growth, unit: '%'}
  PCPIPCH:     {label: Inflation, unit: '%'}
  GGXWDG_NGDP: {label: Govt debt, unit: '% GDP'}
  GGXCNL_NGDP: {label: Fiscal balance, unit: '% GDP'}
  BCA_NGDPD:   {label: Current account, unit: '% GDP'}
news: {max_items: 6, lookback_hours: 36}
"""

RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>test</title>
<item><title>Northland central bank cuts interest rate by 50bp to 5.25% - Test Wire</title><link>https://example.org/1</link>
<pubDate>Mon, 20 Oct 2026 04:00:00 GMT</pubDate><source url="https://example.org">Test Wire</source><description>Inflation slowed to 4.1% in September.</description></item>
<item><title>Northland central bank cuts interest rate by 50bp to 5.25% - Other Wire</title><link>https://example.org/1b</link>
<pubDate>Mon, 20 Oct 2026 04:30:00 GMT</pubDate><source url="https://example.org">Other Wire</source></item>
<item><title>Northland football team wins match - Sports Daily</title><link>https://example.org/2</link>
<pubDate>Mon, 20 Oct 2026 03:00:00 GMT</pubDate><source url="https://example.org">Sports Daily</source></item>
<item><title>Old Northland budget story - Test Wire</title><link>https://example.org/3</link>
<pubDate>Wed, 01 Oct 2026 03:00:00 GMT</pubDate><source url="https://example.org">Test Wire</source></item>
</channel></rss>"""


def raw_inputs() -> dict:
    a = lambda i, t, p, h, s="": {"id": "", "title": t, "publisher": p, "url": f"https://example.org/{i}",  # noqa: E731
                                  "published": f"2026-10-20T0{h}:00:00+00:00", "snippet": s, "score": 0.0}
    return {
        "generated": NOW, "years": [2026, 2027],
        "news": {
            "NTH": [a(1, "Northland central bank cuts interest rate by 50bp to 5.25%", "Test Wire", 4, "Inflation slowed to 4.1% in September."),
                    a(2, "Northland finance minister presents 2027 budget with deficit target of 3.0% of GDP", "Test Wire", 3),
                    a(3, "Northland football team wins match", "Sports Daily", 2)],
            "EST": [a(4, "IMF staff reach agreement with Eastovia on $1.2 billion programme review", "Test Wire", 5),
                    a(5, "Eastovia currency falls as reserves drop to 3.1 months of imports", "Test Wire", 4)],
            "STH": [a(6, "Fitch affirms Southmark at B with stable outlook", "Test Wire", 1)],
        },
        "imf": {
            "NGDP_RPCH": {"NTH": {"2026": 3.2, "2027": 3.0}, "EST": {"2026": 4.1, "2027": 4.4}, "STH": {"2026": 1.1, "2027": 1.4}},
            "PCPIPCH": {"NTH": {"2026": 4.0, "2027": 3.1}, "EST": {"2026": 18.5, "2027": 12.0}, "STH": {"2026": 4.6, "2027": 4.5}},
            "GGXWDG_NGDP": {"NTH": {"2026": 58.0, "2027": 60.1}, "EST": {"2026": 88.4, "2027": 84.0}, "STH": {"2026": 77.2, "2027": 78.0}},
            "GGXCNL_NGDP": {"NTH": {"2026": -5.4, "2027": -4.9}, "EST": {"2026": -7.1, "2027": -6.5}, "STH": {"2026": -5.0, "2027": -4.6}},
            "BCA_NGDPD": {"NTH": {"2026": -0.8, "2027": -1.0}, "EST": {"2026": -4.2, "2027": -3.6}, "STH": {"2026": -1.4, "2027": -1.6}},
        },
        "bis": {"NT": {"period": "2026-10", "rate": 5.25, "change_bp": -50}, "SM": {"period": "2026-10", "rate": 7.0, "change_bp": 0}},
        "fx": {"as_of": "Mon, 20 Oct 2026 00:02:31 +0000", "rates": {"NTD": 3.98, "EVP": 51.2, "SMR": 17.9}},
        "status": {"news": "3/3 feeds", "imf": "ok", "bis": "ok (2 rates)", "fx": "ok"},
    }


PREVIOUS = {"NTH": {"imf": {"NGDP_RPCH": {"2026": 3.4, "2027": 3.0}}, "policy_rate": {"period": "2026-09", "rate": 5.75, "change_bp": 0},
                    "fx": 3.99, "articles": []},
            "EST": {"imf": {}, "policy_rate": None, "fx": 49.6, "articles": []},
            "STH": {"imf": {}, "policy_rate": {"period": "2026-10", "rate": 7.0, "change_bp": 0}, "fx": 17.95, "articles": []}}

LLM_REPLY = {
    "NTH": {"headline": "Rate cut and a tighter 2027 budget", "bullets": [
        {"text": "The central bank cut its policy rate by 50bp to 5.25% as inflation slowed to 4.1%.", "sources": ["NTH-2"]},
        {"text": "The 2027 budget targets a deficit of 3.0% of GDP, against an IMF forecast of -5.4% for 2026.", "sources": ["NTH-1", "DATA"]},
        {"text": "Analysts expect a further 75bp of cuts.", "sources": ["NTH-2"]}],
        "bond_angle": "Easing plus consolidation is supportive for local bonds if the deficit target is credible.", "bond_angle_sources": ["NTH-1", "NTH-2"]},
    "EST": {"headline": "IMF review agreed; reserves still thin", "bullets": [
        {"text": "IMF staff agreed the programme review, unlocking $1.2 billion.", "sources": ["EST-1"]},
        {"text": "Reserves fell to 3.1 months of imports and the currency weakened 3.1% against the dollar.", "sources": ["EST-2", "DATA"]}],
        "bond_angle": "The review lowers near-term financing risk; reserves remain the constraint.", "bond_angle_sources": ["EST-1", "EST-2"]},
    "STH": "not json at all",
}

if __name__ == "__main__":
    (HERE / "countries_test.yaml").write_text(COUNTRIES)
    (HERE / "feed.xml").write_text(RSS)
    (HERE / "raw.json").write_text(json.dumps(raw_inputs(), indent=1))
    print("fixtures written")
