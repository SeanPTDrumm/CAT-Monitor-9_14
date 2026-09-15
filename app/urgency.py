"""
Urgency level 1-3 and recommended status - deterministic baseline for human review.

  1 = watch      : active fire, no population signal within the rules
  2 = elevated   : low containment or growth AND (a place within 10 mi or a
                   ZCTA within 5 mi), or very large fire not yet mostly
                   contained, or perimeter moved toward the nearest place
  3 = act        : low containment or growth AND a Census place within 5 mi
                   of the perimeter (or a ZCTA/place there with population
                   >= threshold when population is known)

Rules are fixed and visible. The output is a *recommendation*; the analyst's
status only changes when they accept it in the app. Every human decision is
stored with the analyst's own level so thresholds can be calibrated later.

When no perimeter geometry is available the rules fall back to the WFIGS
origin-point description and say so ("provisional").
"""
from __future__ import annotations

from typing import Any

import pandas as pd

LEVEL_LABEL = {1: "Watch", 2: "Elevated", 3: "Act"}
LEVEL_COLOUR = {1: "#6c8ebf", 2: "#e0a100", 3: "#d93025"}

THRESHOLDS: dict[str, float] = {
    "low_containment_pct": 50,       # "active" when containment is below this (or unknown & new)
    "growth_acres": 1000,            # growth since prior counted as active
    "large_acres": 10000,
    "mostly_contained_pct": 75,
    "near_miles": 5.0,               # populated place / ZCTA within this -> level 3 candidate
    "far_miles": 10.0,               # within this -> level 2 candidate
    "population_min": 1000,          # place or ZCTA population considered material
    "approach_miles": 0.5,           # perimeter moved this much closer to nearest place since prior
    "contained_pct": 95,             # at/above: recommend closing Monitor items
}


def _na(v: Any) -> bool:
    try:
        return v is None or pd.isna(v)
    except (TypeError, ValueError):
        return False


def _pop_ok(p: Any, t: dict[str, float]) -> bool | None:
    """True/False if population known, None if not verified."""
    if p is None:
        return None
    return p >= t["population_min"]


def assess(row: pd.Series | dict, spatial: dict[str, Any] | None = None, geo_change: dict[str, Any] | None = None,
           current_status: str = "No Action", thresholds: dict[str, float] | None = None) -> dict[str, Any]:
    t = {**THRESHOLDS, **(thresholds or {})}
    g = row.get if hasattr(row, "get") else (lambda k, d=None: row[k] if k in row else d)
    reasons: list[str] = []
    provisional = False

    pct = g("pct_contained"); acres = g("acres"); growth = g("acres_change"); is_new = bool(g("is_new", False))
    active = False
    if not _na(pct) and pct < t["low_containment_pct"]:
        active = True; reasons.append(f"containment {pct:.0f}%")
    if not _na(growth) and growth >= t["growth_acres"]:
        active = True; reasons.append(f"grew {growth:+,.0f} ac since prior")
    if _na(pct) and is_new:
        active = True; reasons.append("new fire, containment not reported")

    # population proximity from spatial result, else fall back to WFIGS origin text
    near_pop = False          # populated (>= threshold) place or ZCTA within near_miles - strongest signal
    near_place_unknown = False  # a Census place (settlement) within near_miles, population not verified
    zcta_signal = False       # ZCTA intersected / within near_miles but population unknown or small
    far_pop = False           # any place within far_miles
    intersects_zcta = False
    nearest_txt = None
    if spatial and spatial.get("status") == "calculated":
        sp = spatial["spatial"]
        for pl in sp["places"]:
            ok = _pop_ok(pl.get("population_2020"), t)
            if pl["distance_miles"] <= t["near_miles"]:
                if ok:
                    near_pop = True
                elif ok is None:
                    near_place_unknown = True
            if pl["distance_miles"] <= t["far_miles"] and ok is not False:
                far_pop = True
        for z in sp["zctas"]:
            ok = _pop_ok(z.get("population_2020"), t)
            if z["intersects"]:
                intersects_zcta = True
            if z["distance_miles"] <= t["near_miles"]:
                if ok:
                    near_pop = True
                else:
                    zcta_signal = True
        if sp["places"]:
            p0 = sp["places"][0]
            pop = p0.get("population_2020")
            nearest_txt = (f"{p0['name']} {p0['distance_miles']:.1f} mi {p0['direction_from_fire']} of perimeter"
                           + (f", pop {pop:,}" if pop is not None else ", pop Not verified"))
    else:
        provisional = True
        om = g("origin_miles")
        if not _na(om):
            if om <= t["far_miles"]:
                far_pop = True   # origin-point text names a place; without geometry this caps at level 2
            nearest_txt = f"WFIGS origin ref {om:g} mi from {g('origin_place')} (origin point, provisional)"
        else:
            nearest_txt = "no location reference available"

    approach = None
    if geo_change and geo_change.get("place_distance_changes"):
        closest = geo_change["place_distance_changes"][0]
        if closest["delta_miles"] <= -t["approach_miles"]:
            approach = closest
            reasons.append(f"perimeter moved {abs(closest['delta_miles']):.1f} mi toward {closest['name']}")

    level = 1
    if active and (near_pop or near_place_unknown):
        level = 3
    elif active and (far_pop or zcta_signal):
        level = 2
    elif (not _na(acres) and acres >= t["large_acres"] and (_na(pct) or pct < t["mostly_contained_pct"])):
        level = 2
        reasons.append(f"large fire {acres:,.0f} ac under {t['mostly_contained_pct']:.0f}% contained"
                       + (f" ({pct:.0f}%)" if not _na(pct) else " (containment not reported)"))
    elif approach:
        level = 2

    if near_pop:
        reasons.append(f"populated place/ZCTA within {t['near_miles']:g} mi of perimeter")
    elif near_place_unknown:
        reasons.append(f"Census place within {t['near_miles']:g} mi of perimeter (population Not verified)")
    elif zcta_signal and not far_pop:
        reasons.append(f"ZCTA within {t['near_miles']:g} mi (population Not verified); no Census place within {t['far_miles']:g} mi")
    elif far_pop:
        reasons.append(f"place within {t['far_miles']:g} mi" + (" (WFIGS origin text, provisional)" if provisional else ""))
    if intersects_zcta:
        reasons.append("perimeter intersects a ZCTA")

    contained = not _na(pct) and pct >= t["contained_pct"]
    if contained:
        level = 1
        reasons = [f"contained {pct:.0f}%"] + [r for r in reasons if not r.startswith("containment")]

    # recommended status
    if current_status == "Existing Moratorium":
        rec = "Existing Moratorium"
        note = "Moratorium in force; review at expiry" + (" (fire now contained)" if contained else "")
    elif level == 3:
        rec, note = "Investigate", "Level 3: population signal with active fire; investigate ZIPs and moratorium need"
    elif level == 2:
        rec, note = "Monitor", "Level 2: keep on daily watch"
    else:
        if contained and current_status in ("Monitor", "Investigate"):
            rec, note = "No Action", "Contained; consider closing the item"
        elif current_status in ("Monitor", "Investigate"):
            rec, note = current_status, "Level 1: no new signal; keep current status"
        else:
            rec, note = "No Action", "Level 1: no population signal under the rules"

    return {
        "level": level, "label": LEVEL_LABEL[level], "reasons": reasons, "reason_text": "; ".join(reasons) or "no signal",
        "nearest": nearest_txt, "provisional": provisional, "recommended_status": rec, "note": note,
        "change_recommended": rec != current_status,
    }


def describe(thresholds: dict[str, float] | None = None) -> str:
    t = {**THRESHOLDS, **(thresholds or {})}
    return (f"Active = containment below {t['low_containment_pct']:.0f}% or growth of {t['growth_acres']:,.0f}+ acres. "
            f"Level 3 = active and a Census place (or a ZCTA with population {t['population_min']:,}+) within "
            f"{t['near_miles']:g} mi of the perimeter. Level 2 = active and a place within {t['far_miles']:g} mi or a ZCTA within "
            f"{t['near_miles']:g} mi, "
            f"or {t['large_acres']:,}+ acres under {t['mostly_contained_pct']:.0f}% contained, or perimeter moved "
            f"{t['approach_miles']:g}+ mi toward a place since prior. Level 1 otherwise; contained {t['contained_pct']:.0f}%+ "
            "is always level 1. Without perimeter geometry the WFIGS origin-point text is used and marked provisional. "
            "Recommendations never change a status without the analyst accepting them.")
