"""
Deterministic screening flags ("Why it surfaces").

These are NOT a risk score and NEVER change a fire's status. They restate
observable WFIGS facts against fixed, visible thresholds so the analyst can
see at a glance why a fire deserves a look. Thresholds are shown in the UI
and can be adjusted there.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

DEFAULT_THRESHOLDS: dict[str, float] = {
    "containment_below_pct": 50,     # containment strictly below this %
    "acres_at_least": 10_000,        # incident size at or above
    "origin_miles_within": 5,        # WFIGS origin-point description miles at or below
    "growth_acres_at_least": 1_000,  # acres added since prior snapshot at or above
    "contained_at_least_pct": 95,    # at or above this containment the fire does not surface
}

THRESHOLD_LABELS: dict[str, str] = {
    "containment_below_pct": "Containment below (%)",
    "acres_at_least": "Acres at least",
    "origin_miles_within": "WFIGS reference within (miles)",
    "growth_acres_at_least": "Growth since prior at least (acres)",
    "contained_at_least_pct": "Do not surface when contained at least (%)",
}


def _na(v: Any) -> bool:
    try:
        return v is None or pd.isna(v)
    except (TypeError, ValueError):
        return False


def screen_row(r: pd.Series | dict, t: dict[str, float] | None = None) -> tuple[bool, list[str], list[str]]:
    """Return (surfaces, reasons, data_gaps) for one normalised fire row."""
    t = {**DEFAULT_THRESHOLDS, **(t or {})}
    reasons: list[str] = []
    gaps: list[str] = []
    g = r.get if hasattr(r, "get") else (lambda k, d=None: r[k] if k in r else d)

    pct = g("pct_contained")
    if _na(pct):
        gaps.append("containment not reported")
    elif pct == 0:
        reasons.append("Zero containment")
    elif pct < t["containment_below_pct"]:
        reasons.append(f"Containment {pct:.0f}% (below {t['containment_below_pct']:.0f}%)")

    acres = g("acres")
    if _na(acres):
        gaps.append("acres not reported")
    elif acres >= t["acres_at_least"]:
        reasons.append(f"Large: {acres:,.0f} ac")

    miles = g("origin_miles")
    if _na(miles):
        gaps.append("no WFIGS location description")
    elif miles <= t["origin_miles_within"]:
        place = g("origin_place")
        reasons.append(f"WFIGS ref {miles:g} mi from {place}" if place else f"WFIGS ref {miles:g} mi")

    growth = g("acres_change")
    if not _na(growth) and growth >= t["growth_acres_at_least"]:
        reasons.append(f"Grew {growth:+,.0f} ac since prior")

    if bool(g("is_new", False)):
        reasons.append("New in this snapshot")

    # Near-full containment suppresses surfacing (Justin's "Contained" = no action),
    # but the factual reasons stay visible with the containment stated first.
    if not _na(pct) and pct >= t["contained_at_least_pct"] and reasons:
        return False, [f"Contained {pct:.0f}%"] + reasons, gaps
    return bool(reasons), reasons, gaps


def apply(df: pd.DataFrame, thresholds: dict[str, float] | None = None) -> pd.DataFrame:
    """Add screen_surfaces / screen_reasons / screen_gaps columns (copy)."""
    out = df.copy()
    res = [screen_row(r, thresholds) for _, r in out.iterrows()]
    out["screen_surfaces"] = [s for s, _, _ in res]
    out["screen_reasons"] = ["; ".join(rs) for _, rs, _ in res]
    out["screen_gaps"] = ["; ".join(gs) for _, _, gs in res]
    return out


def describe(thresholds: dict[str, float] | None = None) -> str:
    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    return (f"Flags: containment below {t['containment_below_pct']:.0f}% or zero; acres at least "
            f"{t['acres_at_least']:,.0f}; WFIGS origin reference within {t['origin_miles_within']:g} miles; "
            f"growth of at least {t['growth_acres_at_least']:,.0f} acres since prior; new in snapshot. "
            f"Fires contained at least {t['contained_at_least_pct']:.0f}% do not surface. "
            "Deterministic restatement of WFIGS facts, not a score. Flags never change status.")
