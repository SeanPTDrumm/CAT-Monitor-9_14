"""
Does this fire require the analyst's attention right now, and on what evidence?

This is the dashboard's screening layer. It answers one question - "what changed
since the last completed review?" - and it answers it with named evidence, never
a score.

Design rules (from CLAUDE.md):
  * The ~300 acre / ~5 mile figures are SCREENING GUIDELINES, not gates. Any
    elevation signal (evacuation, structures, rapid growth, perimeter movement,
    moratorium context, analyst Investigate) surfaces a fire regardless of its
    size or distance.
  * "New in this snapshot" NEVER qualifies a fire on its own. It only routes the
    fire into the first-look path, which requires its own evidence.
  * A fire the analyst already reviewed stays quiet until a fact moves past a
    threshold measured against the REVIEW WATERMARK (analyst.record_review).
  * Nothing is inferred. A fact that was not captured at review time produces no
    delta claim, and a distance without perimeter geometry is reported as
    provisional, never as a perimeter distance.

Wraps urgency.assess(); it does not replace it.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

import analyst

THRESHOLDS: dict[str, float] = {
    # screening guidelines (deliberately soft - see module docstring)
    "guideline_acres": 300,          # "normally relevant" size
    "guideline_miles": 5.0,          # "normally relevant" distance to populated/ZIP geography
    "context_miles": 10.0,           # beyond this, geography stops being a concern by itself
    "close_miles": 1.0,              # very close: relevant even for a small fire
    # material change vs the review watermark
    "growth_acres": 1000,            # absolute growth that is material on its own
    "growth_pct": 25,                # relative growth that is material
    "growth_pct_min_acres": 100,     # ...provided the absolute growth is at least this
    "containment_loss_pts": 10,      # containment going backwards
    "approach_miles": 0.5,           # perimeter closing on a populated place
    # de-escalation
    "contained_pct": 95,             # at/above this a fire is quiet unless elevated
    "very_active_pct": 25,           # low containment that keeps a farther fire relevant
    # moratorium
    "moratorium_soon_days": 14,
}

BUCKET_ATTENTION = "attention"
BUCKET_MONITORING = "monitoring"
BUCKET_REVIEWED = "reviewed"
BUCKET_BACKGROUND = "background"

_EVAC_ORDER_WORDS = ("evacuation order", "evac order", "mandatory evacuation", "under order")
_EVAC_WARNING_WORDS = ("evacuation warning", "evac warning", "advisory", "be ready", "set")


def _na(v: Any) -> bool:
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(v, str) and v.strip() == ""


def _f(v: Any) -> float | None:
    if _na(v):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_date(v: Any) -> date | None:
    """ISO dates, M/D/YYYY, timestamps. None when unparseable - never guessed."""
    if _na(v):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return pd.Timestamp(v).date()
    except (ValueError, TypeError, OverflowError):
        return None


# --------------------------------------------------------------------------- #
# Perimeter-based proximity
# --------------------------------------------------------------------------- #
def proximity(spatial: dict[str, Any] | None, row: Any) -> dict[str, Any]:
    """Nearest populated place / relevant ZCTA, measured from the actual perimeter.

    `verified` is False when no perimeter geometry exists; in that case `miles` is
    None (never the origin-point distance) and `origin_miles` carries the WFIGS
    origin-point reference separately, clearly labelled.
    """
    g = row.get if hasattr(row, "get") else (lambda k, d=None: row[k] if k in row else d)
    out: dict[str, Any] = {
        "verified": False, "miles": None, "what": None, "place": None, "place_miles": None,
        "population": None, "zcta_miles": None, "intersects_zcta": False,
        "verify_review_zctas": [], "origin_miles": _f(g("origin_miles")),
        "origin_place": g("origin_place"),
    }
    if not spatial or spatial.get("status") != "calculated":
        return out
    sp = spatial.get("spatial") or {}
    out["verified"] = True

    places = sp.get("places") or []
    if places:
        p0 = places[0]
        out["place"] = p0.get("name")
        out["place_miles"] = _f(p0.get("distance_miles"))
        out["population"] = p0.get("population_2020")
        out["place_direction"] = p0.get("direction_from_fire")

    zctas = sp.get("zctas") or []
    relevant = [z for z in zctas if z.get("review_state") in ("VERIFY", "REVIEW")]
    out["verify_review_zctas"] = sorted(z["zcta"] for z in relevant if z.get("zcta"))
    out["intersects_zcta"] = any(z.get("intersects") for z in zctas)
    if zctas:
        z0 = zctas[0]
        out["zcta_miles"] = _f(z0.get("distance_miles"))
        out["zcta"] = z0.get("zcta")
        out["zcta_city"] = z0.get("zip_city")

    # Evidence names the actual place / ZIP area, so a reader can check it.
    if out["place_miles"] is not None:
        pop = out["population"]
        out["place_label"] = (f"{out['place']} {out['place_miles']:.1f} mi from the perimeter"
                              + (f" (pop {pop:,})" if pop is not None else ""))
    if out["zcta_miles"] is not None:
        z = out["zcta"] + (f" {out['zcta_city']}" if out.get("zcta_city") else "")
        out["zcta_label"] = (f"perimeter intersects ZIP area {z}" if out["zcta_miles"] == 0
                             else f"ZIP area {z} {out['zcta_miles']:.1f} mi from the perimeter")

    candidates = [(m, w, lbl) for m, w, lbl in (
        (out["place_miles"], "populated place", out.get("place_label")),
        (out["zcta_miles"], "ZIP area", out.get("zcta_label"))) if m is not None]
    if candidates:
        out["miles"], out["what"], out["nearest_label"] = min(candidates, key=lambda c: c[0])
    return out


# --------------------------------------------------------------------------- #
# Evidence from analyst research (free text; never inferred from WFIGS)
# --------------------------------------------------------------------------- #
def evacuation_state(rec: dict[str, Any]) -> tuple[str, str | None]:
    """('orders' | 'warning' | 'none_found' | 'not_verified', supporting text).

    WFIGS publishes no evacuation field, so this reads only what the analyst
    researched into structures_evac. Blank means NOT VERIFIED, never "none".
    """
    text = (rec.get("structures_evac") or "").strip()
    if not text:
        return "not_verified", None
    low = text.lower()
    if any(w in low for w in _EVAC_ORDER_WORDS):
        return "orders", text
    if any(w in low for w in _EVAC_WARNING_WORDS):
        return "warning", text
    if "no evacuation" in low or "none" in low:
        return "none_found", text
    return "not_verified", text


def structures_threatened(rec: dict[str, Any]) -> str | None:
    text = (rec.get("structures_evac") or "").strip()
    if not text:
        return None
    return text if "structure" in text.lower() else None


def moratorium_state(rec: dict[str, Any], today: date | None = None,
                     thresholds: dict[str, float] | None = None) -> dict[str, Any]:
    """Moratorium standing. Flags only - the app never imposes or lifts one."""
    t = {**THRESHOLDS, **(thresholds or {})}
    today = today or date.today()
    out: dict[str, Any] = {"in_force": False, "expires": None, "days_left": None,
                           "state": "none", "source": rec.get("moratorium_expiry_source")}
    if rec.get("status") != "Existing Moratorium":
        return out
    out["in_force"] = True
    exp = _parse_date(rec.get("moratorium_expires"))
    if exp is None:
        out["state"] = "expiry_not_recorded"
        return out
    out["expires"] = exp.isoformat()
    out["days_left"] = (exp - today).days
    if out["days_left"] < 0:
        out["state"] = "expired"
    elif out["days_left"] <= t["moratorium_soon_days"]:
        out["state"] = "expiring_soon"
    else:
        out["state"] = "in_force"
    return out


# --------------------------------------------------------------------------- #
# Change since the review watermark
# --------------------------------------------------------------------------- #
def review_delta(row: Any, rec: dict[str, Any],
                 review: dict[str, Any] | None = None) -> dict[str, Any]:
    """Facts now vs facts as reviewed. Only where the fact was captured at review.

    `review` is the latest saved IN-APP review (reviews.latest). That is the only
    operational baseline: archived Excel-derived watermarks are never used here
    (Locked Decision: Day 1 Fresh Baseline). With no in-app review, a fire has no
    baseline and reports reviewed=False, which the UI shows as Initial Review.
    """
    g = row.get if hasattr(row, "get") else (lambda k, d=None: row[k] if k in row else d)
    if review:
        ev = review.get("evidence") or {}
        r = {"acres": ev.get("acres"), "pct_contained": ev.get("containment"),
             "perimeter_date_current": ev.get("perimeter_timestamp"),
             "review_label": f"review of {str(review.get('timestamp') or '')[:16].replace('T', ' ')}",
             "facts_source": f"in-app review by {review.get('reviewer') or 'unknown reviewer'}"}
    else:
        r = None
    out: dict[str, Any] = {"reviewed": bool(r), "label": (r or {}).get("review_label"),
                           "facts_source": (r or {}).get("facts_source"),
                           "acres_delta": None, "acres_delta_pct": None,
                           "containment_delta": None, "perimeter_is_newer": None}
    if not r:
        return out

    acres_now, acres_then = _f(g("acres")), _f(r.get("acres"))
    if acres_now is not None and acres_then is not None:
        out["acres_delta"] = acres_now - acres_then
        if acres_then > 0:
            out["acres_delta_pct"] = out["acres_delta"] / acres_then * 100.0

    pct_now, pct_then = _f(g("pct_contained")), _f(r.get("pct_contained"))
    if pct_now is not None and pct_then is not None:
        out["containment_delta"] = pct_now - pct_then

    pd_now, pd_then = _parse_date(g("perimeter_date_current")), _parse_date(r.get("perimeter_date_current"))
    if pd_now and pd_then:
        out["perimeter_is_newer"] = pd_now > pd_then
    return out


# --------------------------------------------------------------------------- #
# Change since the prior SNAPSHOT
#
# Independent of review_delta above, and of any saved review. This reads only the
# delta columns snapshots.compare() already calculates from the IRWIN-ID join, so
# every fire has a change story from the moment a second snapshot exists - a fire
# nobody has ever reviewed included.
#
# Deliberately free of thresholds. This function states what changed; whether a
# change is MATERIAL stays with assess() and THRESHOLDS, so nothing here can
# quietly invent a new standard.
# --------------------------------------------------------------------------- #
def snapshot_delta(row: Any) -> dict[str, Any]:
    """Facts now vs the prior snapshot. All-None / False when there is no prior.

    Keys:
      has_prior          prior snapshot carried this IRWIN ID
      is_new             absent from the prior snapshot
      acres_delta        signed acres, acres_delta_pct signed percent
      containment        now, containment_prior then, containment_delta signed points
      perimeter_changed  tri-state: True / False / None (unknown)
      exposure_changed   ZIP areas entered/tightened, or a place distance moved
      closer_miles       largest approach in miles, when a place got closer
      name_changed       same IRWIN ID, different fire name (NOT a dropped fire)
      name_prior         the previous name when it changed
    """
    g = row.get if hasattr(row, "get") else (lambda k, d=None: row[k] if k in row else d)

    acres_delta = _f(g("acres_change"))
    cont_delta = _f(g("pct_contained_change"))
    perim = g("perimeter_updated")
    out: dict[str, Any] = {
        "has_prior": bool(g("has_prior")),
        "is_new": bool(g("is_new")),
        "acres": _f(g("acres")),
        "acres_prior": _f(g("acres_prior")),
        "acres_delta": acres_delta,
        "acres_delta_pct": _f(g("acres_change_pct")),
        "containment": _f(g("pct_contained")),
        "containment_prior": _f(g("pct_contained_prior")),
        "containment_delta": cont_delta,
        # perimeter_updated is object-dtype tri-state; None means "cannot say",
        # which must not be reported as "did not change".
        "perimeter_changed": True if perim is True else (False if perim is False else None),
        "exposure_changed": False,
        "closer_miles": None,
        "zips_entered": [],
        "name_changed": False,
        "name_prior": None,
    }

    prior_name = g("fire_name_prior")
    now_name = g("fire_name")
    if (prior_name is not None and now_name is not None
            and str(prior_name).strip() and str(prior_name).strip() != str(now_name).strip()):
        out["name_changed"] = True
        out["name_prior"] = str(prior_name).strip()

    # Exposure / distance change, only where the geography comparison actually ran.
    gch = g("geo_change") or {}
    if isinstance(gch, dict) and gch.get("comparable"):
        entered = [z.get("zcta") for z in (gch.get("zctas_entered_10mi") or [])
                   if z.get("review_state") in ("VERIFY", "REVIEW")]
        tightened = gch.get("zctas_band_tightened") or []
        moves = gch.get("place_distance_changes") or []
        approach = moves[0] if moves and moves[0].get("delta_miles", 0) < 0 else None
        out["zips_entered"] = [z for z in entered if z]
        if approach:
            out["closer_miles"] = abs(float(approach["delta_miles"]))
        out["exposure_changed"] = bool(entered or tightened or approach)
    return out


# --------------------------------------------------------------------------- #
# The assessment
# --------------------------------------------------------------------------- #
ALASKA_STATE = "AK"
ALASKA_RATIONALE = "No coverage in AK"


def is_alaska(row: Any) -> bool:
    """Alaska fires are automatically ignored and hidden (handoff section 3).

    The source record is retained; only dashboard visibility is affected.
    """
    g = row.get if hasattr(row, "get") else (lambda k, d=None: row[k] if k in row else d)
    return str(g("state") or "").strip().upper() == ALASKA_STATE


def assess(row: Any, spatial: dict[str, Any] | None, geo_change: dict[str, Any] | None,
           rec: dict[str, Any], *, review: dict[str, Any] | None = None,
           today: date | None = None,
           thresholds: dict[str, float] | None = None) -> dict[str, Any]:
    """Bucket + evidence for one fire. Deterministic; safe to call outside Streamlit.

    `review` is the latest saved in-app review (reviews.latest) and is the only
    operational baseline used for change detection.
    """
    t = {**THRESHOLDS, **(thresholds or {})}
    g = row.get if hasattr(row, "get") else (lambda k, d=None: row[k] if k in row else d)
    status = rec.get("status") or analyst.DEFAULT_STATUS

    if is_alaska(row):
        # Hidden from the main dashboard, disposition Ignore, fixed rationale.
        # No other Alaska handling exists.
        return {
            "bucket": BUCKET_BACKGROUND, "requires_attention": False, "alaska": True,
            "elevation": [], "guideline": [],
            "quiet": [{"code": "no_coverage_ak", "text": ALASKA_RATIONALE}],
            "reasons": [ALASKA_RATIONALE], "reason_codes": [],
            "proximity": proximity(spatial, row), "delta": review_delta(row, rec, review),
            "moratorium": moratorium_state(rec, today, t),
            "evacuation": {"state": "not_verified", "text": None}, "structures": None,
            "flags": [], "provisional": False,
        }

    prox = proximity(spatial, row)
    delta = review_delta(row, rec, review)
    mora = moratorium_state(rec, today, t)
    evac_state, evac_text = evacuation_state(rec)
    structures = structures_threatened(rec)

    acres = _f(g("acres"))
    pct = _f(g("pct_contained"))
    contained = pct is not None and pct >= t["contained_pct"]

    # Distance to a POPULATED PLACE and distance to a ZIP area are different facts.
    # A fire can intersect a large rural ZCTA with no settlement anywhere near it, so
    # ZIP-area proximity alone never carries a sub-guideline fire.
    big = acres is not None and acres >= t["guideline_acres"]
    place_miles = prox.get("place_miles")
    place_close = place_miles is not None and place_miles <= t["close_miles"]
    place_near = place_miles is not None and place_miles <= t["guideline_miles"]
    zip_near = prox.get("zcta_miles") is not None and prox["zcta_miles"] <= t["guideline_miles"]
    in_context = prox["miles"] is not None and prox["miles"] <= t["context_miles"]

    # Change on its own is only worth an interruption once the fire is materially
    # sized, or a settlement is genuinely close. A 45 -> 147 acre fire with no place
    # within 10 miles is growth without consequence.
    material = big or place_close

    elevation: list[dict[str, str]] = []
    guideline: list[dict[str, str]] = []
    quiet: list[dict[str, str]] = []

    def add(bucket: list, code: str, text: str) -> None:
        bucket.append({"code": code, "text": text})

    # ---- elevation signals: these override the size / distance guidelines ----
    if evac_state == "orders":
        add(elevation, "evacuation_orders", "Evacuation orders reported (analyst research)")
    elif evac_state == "warning":
        add(elevation, "evacuation_warning", "Evacuation warning reported (analyst research)")
    if structures:
        add(elevation, "structures_threatened", "Structures reported threatened (analyst research)")

    d_ac, d_pct = delta["acres_delta"], delta["acres_delta_pct"]
    if material and d_ac is not None and d_ac >= t["growth_acres"]:
        add(elevation, "rapid_growth",
            f"Acres {d_ac:+,.0f} since the {delta['label']} review")
    elif (material and d_ac is not None and d_pct is not None and d_pct >= t["growth_pct"]
          and d_ac >= t["growth_pct_min_acres"]):
        add(elevation, "rapid_growth",
            f"Acres {d_ac:+,.0f} ({d_pct:+.0f}%) since the {delta['label']} review")

    d_cont = delta["containment_delta"]
    if material and d_cont is not None and d_cont <= -t["containment_loss_pts"]:
        add(elevation, "containment_lost",
            f"Containment {d_cont:+.0f} pts since the {delta['label']} review")

    gch = geo_change or {}
    if gch.get("comparable"):
        moves = gch.get("place_distance_changes") or []
        if moves and moves[0]["delta_miles"] <= -t["approach_miles"]:
            m = moves[0]
            add(elevation, "perimeter_movement",
                f"Perimeter moved {abs(m['delta_miles']):.1f} mi toward {m['name']} "
                f"(now {m['now_miles']:.1f} mi)")
        entered = [z for z in (gch.get("zctas_entered_10mi") or [])
                   if z.get("review_state") in ("VERIFY", "REVIEW")]
        tightened = gch.get("zctas_band_tightened") or []
        if entered:
            add(elevation, "new_zip_threat",
                "ZIP area(s) newly within concern range: "
                + ", ".join(z["zcta"] for z in entered[:4]))
        elif tightened:
            add(elevation, "new_zip_threat",
                "ZIP area(s) moved into a closer band: "
                + ", ".join(c[0]["zcta"] for c in tightened[:4]))

    if mora["state"] == "expiring_soon":
        add(elevation, "moratorium_expiring",
            f"Moratorium expires {mora['expires']} ({mora['days_left']} days)")
    elif mora["state"] == "expired":
        add(elevation, "moratorium_expired",
            f"Moratorium expiry {mora['expires']} has passed - confirm before lifting")
    elif mora["state"] == "expiry_not_recorded":
        add(elevation, "moratorium_expiry_unknown",
            "Moratorium in force with no expiry date recorded")
    elif mora["state"] == "in_force":
        add(elevation, "moratorium_in_force", f"Moratorium in force to {mora['expires']}")

    if status == "Investigate":
        add(elevation, "analyst_investigate", "Analyst has this fire at Investigate")

    # ---- screening guidelines: only consulted when nothing above fired ----
    if not delta["reviewed"] and not contained:
        # A fire the analyst has never looked at. "New in this snapshot" is NOT a
        # reason on its own - each branch below carries its own evidence.
        label = prox.get("nearest_label")
        if big and (place_near or zip_near):
            add(guideline, "meets_guidelines", f"{acres:,.0f} ac, {label}")
        elif big and in_context and pct is not None and pct < t["very_active_pct"]:
            add(guideline, "large_active_just_outside",
                f"{acres:,.0f} ac at {pct:.0f}% contained, {label}")
        elif place_close and (pct is None or pct < 50):
            # Below the size guideline, but a settlement is within a mile.
            add(guideline, "small_but_close",
                (f"{prox.get('place_label')}"
                 + (f", {acres:,.0f} ac" if acres is not None else "")
                 + (f", {pct:.0f}% contained" if pct is not None else "")))
        elif not prox["verified"] and big:
            om = prox["origin_miles"]
            if om is not None and om <= t["guideline_miles"]:
                add(guideline, "provisional_first_look",
                    f"{acres:,.0f} ac; WFIGS origin reference {om:g} mi from "
                    f"{prox['origin_place']} - perimeter distance not yet calculated")

    # ---- why a fire stays quiet ----
    if contained:
        add(quiet, "contained", f"Contained {pct:.0f}%")
    if delta["reviewed"] and not elevation:
        add(quiet, "no_material_change",
            f"No material change since the {delta['label']} review")
    if prox["miles"] is not None and prox["miles"] > t["context_miles"]:
        add(quiet, "distant", f"Nearest {prox['what']} beyond {t['context_miles']:g} mi")
    elif prox.get("nearest_label"):
        add(quiet, "proximity", prox["nearest_label"][0].upper() + prox["nearest_label"][1:])
    if not prox["verified"]:
        add(quiet, "geography_pending", "Perimeter geography not yet calculated")

    requires = bool(elevation) or bool(guideline)
    if requires:
        bucket = BUCKET_ATTENTION
    elif status in ("Monitor", "Investigate", "Existing Moratorium"):
        bucket = BUCKET_MONITORING
    elif delta["reviewed"]:
        bucket = BUCKET_REVIEWED
    else:
        bucket = BUCKET_BACKGROUND

    return {
        "bucket": bucket, "alaska": False,
        "requires_attention": requires,
        "elevation": elevation,
        "guideline": guideline,
        "quiet": quiet,
        "reasons": [r["text"] for r in (elevation + guideline)] or [r["text"] for r in quiet],
        "reason_codes": [r["code"] for r in (elevation + guideline)],
        "proximity": prox,
        "delta": delta,
        "moratorium": mora,
        "evacuation": {"state": evac_state, "text": evac_text},
        "structures": structures,
        "flags": _flags(elevation, evac_state, mora, prox),
        "provisional": not prox["verified"],
    }


_FLAG_LABELS = {
    "evacuation_orders": ("EVACUATION ORDERS IN EFFECT", "alert"),
    "evacuation_warning": ("EVACUATION WARNING", "warn"),
    "structures_threatened": ("STRUCTURES THREATENED", "alert"),
    "rapid_growth": ("SIGNIFICANT SIZE INCREASE", "warn"),
    "containment_lost": ("CONTAINMENT LOST", "warn"),
    "perimeter_movement": ("NEW PERIMETER MOVEMENT", "warn"),
    "new_zip_threat": ("NEW ZIP / POPULATED AREA THREAT", "alert"),
    "moratorium_in_force": ("EXISTING MORATORIUM", "info"),
    "moratorium_expiring": ("MORATORIUM EXPIRING SOON", "warn"),
    "moratorium_expired": ("MORATORIUM EXPIRED - CONFIRM", "alert"),
    "moratorium_expiry_unknown": ("MORATORIUM EXPIRY NOT RECORDED", "warn"),
}


def _flags(elevation: list[dict[str, str]], evac_state: str, mora: dict[str, Any],
           prox: dict[str, Any]) -> list[dict[str, str]]:
    """Only the flags relevant to this fire, in severity order."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for r in elevation:
        label = _FLAG_LABELS.get(r["code"])
        if label and r["code"] not in seen:
            out.append({"label": label[0], "tone": label[1], "detail": r["text"]})
            seen.add(r["code"])
    if evac_state == "not_verified":
        out.append({"label": "EVACUATION STATUS NOT VERIFIED", "tone": "muted",
                    "detail": "WFIGS publishes no evacuation field; not yet researched"})
    elif evac_state == "none_found":
        out.append({"label": "NO EVACUATION ORDERS FOUND", "tone": "muted",
                    "detail": "Per analyst research"})
    if not prox["verified"]:
        out.append({"label": "PERIMETER DISTANCE NOT VERIFIED", "tone": "muted",
                    "detail": "Perimeter geography not yet calculated for this fire"})
    order = {"alert": 0, "warn": 1, "info": 2, "muted": 3}
    return sorted(out, key=lambda f: order.get(f["tone"], 9))


def describe(thresholds: dict[str, float] | None = None) -> str:
    t = {**THRESHOLDS, **(thresholds or {})}
    return (
        f"A reviewed fire stays quiet until a fact moves past a threshold measured against the "
        f"review watermark: acres {t['growth_acres']:,.0f}+ or {t['growth_pct']:.0f}%+, containment "
        f"down {t['containment_loss_pts']:.0f}+ pts, perimeter {t['approach_miles']:g}+ mi closer to a "
        f"place, or a ZIP area newly within concern range. Growth and containment loss count only "
        f"once the fire is at least {t['guideline_acres']:,.0f} acres or a populated place is within "
        f"{t['close_miles']:g} mi - growth on a small fire with nothing near it is not an "
        f"interruption. Evacuations, structures threatened, moratorium context and an Investigate "
        f"status surface a fire regardless of its size or distance. For a fire never reviewed, the "
        f"guidelines are about {t['guideline_acres']:,.0f}+ acres within about {t['guideline_miles']:g} "
        f"mi of populated / ZIP geography - guidelines, not gates: a large active fire out to "
        f"{t['context_miles']:g} mi, or any fire with a populated place within {t['close_miles']:g} mi, "
        f"also surfaces. Intersecting a large rural ZIP area is not by itself nearness to people. "
        f"Being new in the snapshot is never a reason on its own. Contained {t['contained_pct']:.0f}%+ "
        "is quiet unless elevated. All distances are from the actual perimeter; without perimeter "
        "geometry the fire is marked provisional and no perimeter distance is claimed."
    )


# --------------------------------------------------------------------------- #
# Dropped fires
#
# A fire is DROPPED only when its stable IRWIN ID was present in the prior
# snapshot and is absent from the current one. A changed fire_name under the
# SAME IRWIN ID is not a dropped fire - that is a name change on the joined
# record, reported by snapshot_delta()["name_changed"].
#
# A dropped fire is not automatically closed, contained, ignored, or removed
# from historical context. It is simply no longer in the current feed.
# --------------------------------------------------------------------------- #
DROPPED_NOT_REPORTED = "No longer reported by WFIGS"


def assess_dropped(prior_row: Any, rec: dict[str, Any] | None = None) -> dict[str, Any]:
    """Prior-snapshot facts for a fire that left the feed, plus a supported reason.

    The explanation is drawn ONLY from what the prior record actually says, in
    priority order:

      1. it was 100% contained in the prior snapshot
      2. the prior record explicitly marks it a child of a complex
         (is_cpx_child / cpx_name, from attr_IsCpxChild / attr_CpxName)
      3. otherwise the neutral "No longer reported by WFIGS"

    A rename is NEVER inferred for an absent IRWIN ID: with the ID gone there is
    nothing to match a new name against, so guessing would be fabrication.
    """
    g = prior_row.get if hasattr(prior_row, "get") else (
        lambda k, d=None: prior_row[k] if k in prior_row else d)
    rec = rec or {}

    acres = _f(g("acres"))
    pct = _f(g("pct_contained"))

    # NaN must go through _na(): pandas turns a blank cell into float("nan"), and
    # str(nan) is the truthy string "nan" - which would claim "part of complex nan"
    # for a fire whose record says nothing about a complex at all.
    child = g("is_cpx_child")
    child_yes = (not _na(child)
                 and str(child).strip().lower() in ("1", "1.0", "true", "yes", "y"))
    cpx = g("cpx_name")
    cpx_name = str(cpx).strip() if not _na(cpx) else None

    if pct is not None and pct >= 100:
        reason, code = "Was 100% contained in the prior snapshot", "contained"
    elif child_yes or cpx_name:
        reason = ("Prior record marks it part of complex " + cpx_name) if cpx_name else \
                 "Prior record marks it a child of a complex"
        code = "complex"
    else:
        reason, code = DROPPED_NOT_REPORTED, "not_reported"

    status = rec.get("status") or analyst.DEFAULT_STATUS
    return {
        "dropped": True,
        "irwin_id": g("irwin_id"),
        "fire_name": g("fire_name"),
        "state": g("state"),
        "acres_prior": acres,
        "containment_prior": pct,
        "reason": reason,
        "reason_code": code,
        "status": status,
        "tracked": status != analyst.DEFAULT_STATUS,
    }
