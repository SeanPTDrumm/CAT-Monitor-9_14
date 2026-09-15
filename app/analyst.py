"""
Analyst (human) annotations, persisted separately from source snapshots.

Keyed on IRWIN ID so a new WFIGS download never overwrites Justin's
Monitor / Investigate decisions, ZIP research, or notes.
Everything here is ANALYST INTERPRETATION or OUTSIDE RESEARCH, never
source fact. Status changes are logged in an append-only history.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
from local_paths import REVIEW_DIR as DATA_DIR
STATUS_FILE = DATA_DIR / "analyst_status.json"

STATUS_OPTIONS = ["No Action", "Monitor", "Investigate", "Existing Moratorium"]
DEFAULT_STATUS = "No Action"

# Colour treatment for statuses (used by the UI; kept here so every page agrees).
STATUS_COLOURS = {
    "No Action": "#9aa0a6",            # grey
    "Monitor": "#e0a100",              # amber
    "Investigate": "#d93025",          # red
    "Existing Moratorium": "#7b3fbf",  # purple
}

# Source of the current status value.
SOURCE_ANALYST = "analyst"
SOURCE_BASELINE_PREFIX = "baseline"   # e.g. "baseline 9-8 (unconfirmed)"

# field key -> (label, help text). Order = display order.
ANALYST_FIELDS: dict[str, tuple[str, str]] = {
    "status": ("Status", "Analyst triage decision."),
    "nearest_population_center": (
        "Nearest Population Center",
        "Town/city closest to the current perimeter (outside research)."),
    "population": (
        "Population",
        "Population of that place, with source (outside research)."),
    "structures_evac": (
        "Structures / Evacuation",
        "Structures threatened/destroyed and evacuation status, with source and date."),
    "zips": ("ZIPs", "Candidate ZIP codes affected or threatened (outside research)."),
    "moratorium_zips": (
        "Moratorium ZIPs",
        "ZIPs under an existing underwriting moratorium, with end date."),
    "moratorium_effective": (
        "Moratorium effective date",
        "Date the binding restriction took effect (YYYY-MM-DD or M/D/YYYY), from the bulletin."),
    "moratorium_expires": (
        "Moratorium expiry date",
        "Date/time the restriction ends (YYYY-MM-DD or M/D/YYYY), from the bulletin. "
        "Used only to flag 'expiring soon' / 'expired - confirm'; the app never lifts a moratorium."),
    "barriers": (
        "Natural / Geographic Barriers",
        "Rivers, lakes, ridgelines, burn scars etc. between fire and exposure."),
    "posture_triggers": (
        "What Would Change the Posture",
        "Conditions that would move this fire up or down: perimeter movement toward "
        "population, structure threat, evacuations, new ZIPs in buffer, containment stalling."),
    "description": ("Description (1-3 sentences)",
                    "Plain-language summary for the team. Leave blank to show an auto-summary built only from verified facts."),
    "notes": ("Notes", "Analyst interpretation and reasoning (current posture)."),
}
TEXT_FIELDS = [k for k in ANALYST_FIELDS if k != "status"]

# Review checklist from the mockup's audit-trail panel. key -> label
CHECKLIST_ITEMS: dict[str, str] = {
    "national_screened": "National fire list ingested and screened",
    "prior_compared": "Prior monitored fires compared day over day",
    "containment_acreage_checked": "Containment and acreage checked",
    "pop_structure_evac_reviewed": "Population / structure / evacuation evidence reviewed",
    "perimeter_zip_done_or_pending": "Perimeter-to-ZIP analysis completed or explicitly marked pending",
    "interpretation_separated": "Underwriting interpretation separated from sourced facts",
    "human_approved": "Human analyst approved any moratorium recommendation",
}

# Structured ZIP entries: list of {"zip": str, "source": str, "note": str}
ZIP_ENTRY_COLUMNS = ["zip", "source", "note"]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load() -> dict[str, dict[str, Any]]:
    if not STATUS_FILE.exists():
        return {}
    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # Never silently lose the file; keep a copy and start fresh.
        STATUS_FILE.rename(STATUS_FILE.with_suffix(".corrupt.json"))
        return {}
    return {k.upper(): v for k, v in data.items()}


def save(records: dict[str, dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATUS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(records, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(STATUS_FILE)


def blank_record(irwin_id: str, fire_name: str | None = None) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "irwin_id": irwin_id,
        "fire_name": fire_name,
        "status": DEFAULT_STATUS,
        "status_source": SOURCE_ANALYST,
        "status_history": [],
        "baseline_reference": "",
        "checklist": {k: False for k in CHECKLIST_ITEMS},
        "zip_entries": [],
        "updated_at": None,
        "updated_by": None,
        "urgency_human": None,       # analyst's own 1-3 level, for calibration
        "urgency_decisions": [],     # append-only log of accept / keep / override decisions
        "review": None,              # last completed review watermark (see record_review)
        "review_history": [],        # append-only log of prior watermarks
    }
    for k in TEXT_FIELDS:
        rec[k] = ""
    return rec


def get(records: dict[str, dict[str, Any]], irwin_id: str,
        fire_name: str | None = None) -> dict[str, Any]:
    """Record for a fire with every field present (defaults filled for older records)."""
    rec = blank_record(irwin_id, fire_name)
    stored = records.get(irwin_id.upper(), {})
    rec.update(stored)
    # A stored null must not defeat the blank_record default: json null arrives as
    # None, and .get(k, "") cannot help because the key exists. Left as None these
    # become float NaN once put in a DataFrame column (pandas string dtype), which
    # then breaks any .strip() on the value.
    for k in TEXT_FIELDS:
        if rec.get(k) is None:
            rec[k] = ""
    if not rec.get("status"):
        rec["status"] = DEFAULT_STATUS
    # older records may lack nested defaults
    cl = dict(blank_record(irwin_id)["checklist"])
    cl.update(stored.get("checklist") or {})
    rec["checklist"] = cl
    rec["status_history"] = list(stored.get("status_history") or [])
    rec["zip_entries"] = list(stored.get("zip_entries") or [])
    rec["urgency_decisions"] = list(stored.get("urgency_decisions") or [])
    rec["review_history"] = list(stored.get("review_history") or [])
    if fire_name and not rec.get("fire_name"):
        rec["fire_name"] = fire_name
    return rec


def is_unconfirmed(rec: dict[str, Any]) -> bool:
    return str(rec.get("status_source", "")).startswith(SOURCE_BASELINE_PREFIX)


def update(records: dict[str, dict[str, Any]], irwin_id: str, fire_name: str | None,
           *, source: str = SOURCE_ANALYST, by: str | None = None, **fields: Any) -> bool:
    """Apply changed fields to one record in-place. Returns True if anything changed.

    `source` describes who made the change ("analyst" or "baseline ..."). Any status
    change is appended to status_history. A save by the analyst also confirms a status
    that was suggested from the baseline import.
    """
    iid = irwin_id.upper()
    current = get(records, iid, fire_name)
    changed = False

    for k, v in fields.items():
        if k == "checklist":
            new_cl = dict(current["checklist"])
            for ck, cv in (v or {}).items():
                if ck in CHECKLIST_ITEMS:
                    new_cl[ck] = bool(cv)
            if new_cl != current["checklist"]:
                current["checklist"] = new_cl
                changed = True
            continue
        if k == "zip_entries":
            new_z = [{c: str(e.get(c, "") or "").strip() for c in ZIP_ENTRY_COLUMNS}
                     for e in (v or []) if any(str(e.get(c, "") or "").strip() for c in ZIP_ENTRY_COLUMNS)]
            if new_z != current["zip_entries"]:
                current["zip_entries"] = new_z
                changed = True
            continue
        if k == "baseline_reference":
            v = (v or "").strip()
            if current.get("baseline_reference", "") != v:
                current["baseline_reference"] = v
                changed = True
            continue
        if k not in ANALYST_FIELDS:
            continue
        if v is None:
            v = ""
        if isinstance(v, str):
            v = v.strip()
        if k == "status":
            v = v if v in STATUS_OPTIONS else DEFAULT_STATUS
            if v != current["status"]:
                current["status_history"].append(
                    {"at": _now(), "from": current["status"], "to": v, "source": source, "by": by})
                current["status"] = v
                current["status_source"] = source
                changed = True
            continue
        if (current.get(k) or "") != v:
            current[k] = v
            changed = True

    # An analyst save confirms any baseline-suggested status.
    if source == SOURCE_ANALYST and is_unconfirmed(current):
        current["status_history"].append(
            {"at": _now(), "from": current["status"], "to": current["status"],
             "source": "confirmed by analyst", "by": by})
        current["status_source"] = SOURCE_ANALYST
        changed = True

    if changed:
        current["fire_name"] = fire_name or current.get("fire_name")
        current["updated_at"] = _now()
        current["updated_by"] = by or current.get("updated_by")
        records[iid] = current
    return changed


def confirm(records: dict[str, dict[str, Any]], irwin_id: str, fire_name: str | None = None,
            by: str | None = None) -> bool:
    """Analyst confirms a baseline-suggested status without other edits."""
    return update(records, irwin_id, fire_name, source=SOURCE_ANALYST, by=by)


def record_urgency_decision(records: dict[str, dict[str, Any]], irwin_id: str, fire_name: str | None, *,
                            app_level: int, app_recommended: str, action: str,
                            human_level: int | None = None, status_after: str | None = None,
                            by: str | None = None) -> None:
    """Log what the analyst did with an urgency recommendation (accepted / kept / overrode)."""
    iid = irwin_id.upper()
    rec = get(records, iid, fire_name)
    rec["urgency_decisions"].append({
        "at": _now(), "by": by, "app_level": app_level, "app_recommended": app_recommended,
        "human_level": human_level, "action": action, "status_after": status_after or rec["status"]})
    if human_level is not None:
        rec["urgency_human"] = int(human_level)
    if action == "kept_current":
        rec["urgency_kept"] = {"level": int(app_level), "recommended": app_recommended, "at": _now(), "by": by}
    elif action == "accepted":
        rec.pop("urgency_kept", None)
    rec["updated_at"] = _now()
    rec["updated_by"] = by or rec.get("updated_by")
    records[iid] = rec


# --------------------------------------------------------------------------- #
# Review watermark - "the state of this fire when the analyst last reviewed it"
# --------------------------------------------------------------------------- #
# The watermark is what makes "nothing material has changed since my last review"
# answerable. It stores the FACTS AS THEY STOOD at the review, each with its own
# provenance, so a later comparison is a real comparison and not a guess. Facts
# that were not captured at review time stay absent; they are never back-filled
# from a later snapshot and presented as though they had been reviewed.
REVIEW_FACT_KEYS = ("acres", "pct_contained", "perimeter_date_current",
                    "verify_review_zctas", "nearest_place", "nearest_place_miles")


def record_review(records: dict[str, dict[str, Any]], irwin_id: str, fire_name: str | None, *,
                  facts: dict[str, Any], review_label: str, facts_source: str,
                  by: str | None = None, at: str | None = None) -> None:
    """Stamp 'reviewed at this state'. Only keys in REVIEW_FACT_KEYS are kept.

    `review_label` names the review to a human ("Justin workbook 9-9", "2026-09-10 review").
    `facts_source` records WHERE each fact came from, so the UI can say "since the 9-9
    review" only when that is literally true.
    """
    iid = irwin_id.upper()
    rec = get(records, iid, fire_name)
    if rec.get("review"):
        rec["review_history"].append(rec["review"])
    rec["review"] = {
        "at": at or _now(),
        "by": by,
        "review_label": review_label,
        "facts_source": facts_source,
        **{k: facts.get(k) for k in REVIEW_FACT_KEYS if facts.get(k) is not None},
    }
    rec["updated_at"] = _now()
    rec["updated_by"] = by or rec.get("updated_by")
    records[iid] = rec


def review_of(rec: dict[str, Any]) -> dict[str, Any] | None:
    """The review watermark, or None when this fire has never been reviewed."""
    r = rec.get("review")
    return r if isinstance(r, dict) and r else None


def has_reviewed_fact(rec: dict[str, Any], key: str) -> bool:
    """True when `key` was actually captured at review time (so a delta is meaningful)."""
    r = review_of(rec)
    return bool(r) and r.get(key) is not None


def is_blank_record(rec: dict[str, Any]) -> bool:
    return rec.get("status", DEFAULT_STATUS) == DEFAULT_STATUS and \
        not any((rec.get(k) or "").strip() for k in TEXT_FIELDS) and \
        not rec.get("zip_entries")


def count_by_status(records: dict[str, dict[str, Any]],
                    irwin_ids: set[str] | None = None) -> dict[str, int]:
    """Counts per status. If irwin_ids given, only fires in that set are counted."""
    counts = {s: 0 for s in STATUS_OPTIONS}
    for iid, rec in records.items():
        if irwin_ids is not None and iid not in irwin_ids:
            continue
        s = rec.get("status", DEFAULT_STATUS)
        counts[s] = counts.get(s, 0) + 1
    return counts


def status_at(rec: dict[str, Any], when: datetime) -> str | None:
    """Status in force at `when`, from the history log. None if no history reaches back that far."""
    hist = rec.get("status_history") or []
    if not hist:
        return None
    ts = when.isoformat(timespec="seconds")
    if ts < hist[0]["at"]:
        return None  # the app has no record of the status before its first log entry
    status = None
    for h in hist:
        if h["at"] <= ts:
            status = h["to"]
        else:
            break
    return status
