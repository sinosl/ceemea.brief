"""Detect what changed in the data since the previous run.

These lines are computed, not written by the model, so the 'what
changed' section can always be trusted.
"""
from __future__ import annotations

from .models import Change

FX_ALERT_PCT = 1.0          # flag FX moves larger than this
WEO_REVISION_MIN = 0.1      # ignore IMF revisions smaller than this


def fx_move(prev_rate: float | None, rate: float | None) -> float | None:
    """% change in the local currency against USD (positive = local currency stronger)."""
    if not prev_rate or not rate:
        return None
    return round((prev_rate / rate - 1) * 100, 2)


def detect(country, today: dict, previous: dict | None, labels: dict[str, dict]) -> list[Change]:
    """Compare today's snapshot for one country with the previous run's."""
    out: list[Change] = []
    prev = previous or {}

    pr, pr_prev = today.get("policy_rate"), prev.get("policy_rate")
    # First run: report BIS's own month-on-month change. Later runs: only report a
    # change against the previous brief, so one decision isn't repeated all month.
    if pr and not previous and pr.get("change_bp"):
        verb = "raised" if pr["change_bp"] > 0 else "cut"
        out.append(Change("policy_rate", pr["rate"] - pr["change_bp"] / 100, pr["rate"],
                          f"Policy rate {verb} {abs(pr['change_bp'])}bp to {pr['rate']:.2f}% ({pr['period']}, BIS)."))
    elif pr and pr_prev and pr_prev.get("rate") is not None and abs(pr["rate"] - pr_prev["rate"]) > 1e-9:
        bp = round((pr["rate"] - pr_prev["rate"]) * 100)
        verb = "raised" if bp > 0 else "cut"
        out.append(Change("policy_rate", pr_prev["rate"], pr["rate"],
                          f"Policy rate {verb} {abs(bp)}bp to {pr['rate']:.2f}% since the last brief (BIS)."))

    move = fx_move(prev.get("fx"), today.get("fx"))
    if move is not None and abs(move) >= FX_ALERT_PCT:
        direction = "strengthened" if move > 0 else "weakened"
        out.append(Change("fx", prev.get("fx"), today.get("fx"),
                          f"{country.ccy} {direction} {abs(move):.1f}% against USD since the last brief "
                          f"({prev['fx']:.4g} to {today['fx']:.4g} per USD)."))

    for ind, meta in labels.items():
        for year, val in (today.get("imf", {}).get(ind) or {}).items():
            old = ((prev.get("imf") or {}).get(ind) or {}).get(str(year), ((prev.get("imf") or {}).get(ind) or {}).get(year))
            if old is not None and abs(val - old) >= WEO_REVISION_MIN:
                out.append(Change(f"imf:{ind}:{year}", old, val,
                                  f"IMF revised its {year} forecast for {meta['label'][0].lower() + meta['label'][1:]} from {old:.1f} to {val:.1f}{meta['unit'].replace('% GDP', '% of GDP')}."))
    return out
