"""
In-app analyst reviews - the active operational store (handoff sections 12 and 13).

This is a NEW, CLEAN store, separate from data/analyst_status.json. The Excel-derived
records in that older file are an archived backup: they are never read here, never
displayed, and never used as a comparison baseline (Locked Decision: Day 1 Fresh
Baseline).

The operational baseline consists only of reviews saved inside CAT Monitor. A fire
with no entry here has no baseline and shows Initial Review.

Storage: data/reviews.json
  { "<IRWIN ID>": [ <review entry>, <review entry>, ... ] }   newest last

Every saved Ignore or Monitor decision appends an entry. Entries are never edited
or removed; a later review appends a new entry beside the earlier one.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REVIEW_FILE = DATA_DIR / "reviews.json"
MAP_DIR = DATA_DIR / "review_maps"

# Only these dispositions are saved. "Create Moratorium" opens the builder entry
# point and never records a disposition (handoff 10.3).
IGNORE = "Ignore"
MONITOR = "Monitor"
DISPOSITIONS = (IGNORE, MONITOR)

# Evidence captured at review time (handoff section 12). Missing stays missing.
EVIDENCE_KEYS = (
    "state", "source_system", "acres", "containment", "wfigs_distance",
    "wfigs_location", "nearest_place", "population", "population_year",
    "perimeter_distance", "nearby_zctas", "perimeter_id", "perimeter_timestamp",
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _norm(irwin_id: str) -> str:
    return (irwin_id or "").strip().upper()


def load() -> dict[str, list[dict[str, Any]]]:
    """The active review store. Empty dict before Day 1."""
    if not REVIEW_FILE.exists():
        return {}
    try:
        data = json.loads(REVIEW_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # Never silently lose reviews; keep a copy and start clean.
        REVIEW_FILE.rename(REVIEW_FILE.with_suffix(".corrupt.json"))
        return {}
    return {_norm(k): list(v or []) for k, v in data.items()}


def save(store: dict[str, list[dict[str, Any]]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = REVIEW_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(store, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(REVIEW_FILE)


def history(store: dict[str, list[dict[str, Any]]], irwin_id: str) -> list[dict[str, Any]]:
    """All reviews for a fire, newest first (handoff: review history display)."""
    return list(reversed(store.get(_norm(irwin_id), [])))


def latest(store: dict[str, list[dict[str, Any]]], irwin_id: str) -> dict[str, Any] | None:
    """The newest saved review, which is this fire's operational baseline.

    None means never reviewed in-app: Initial Review.
    """
    entries = store.get(_norm(irwin_id), [])
    return entries[-1] if entries else None


def disposition(store: dict[str, list[dict[str, Any]]], irwin_id: str) -> str | None:
    r = latest(store, irwin_id)
    return r.get("disposition") if r else None


def add_review(store: dict[str, list[dict[str, Any]]], irwin_id: str, fire_name: str | None, *,
               disposition: str, reviewer: str | None, rationale: str = "",
               snapshot_id: str | None = None, evidence: dict[str, Any] | None = None,
               map_image: str | None = None, review_id: str | None = None,
               area_bucket: str | None = None) -> dict[str, Any]:
    """Append one review entry. Returns the stored entry.

    `rationale` is preserved exactly, including line breaks, and is optional.
    `evidence` records only what the reviewer could actually see; absent facts stay
    absent and are never backfilled later.
    `area_bucket` is the reviewer-confirmed or reviewer-changed Area Bucket, if any -
    a separate quick-look dimension from `disposition`, not a screening fact, so it
    is not filtered through EVIDENCE_KEYS.
    """
    if disposition not in DISPOSITIONS:
        raise ValueError(f"disposition must be one of {DISPOSITIONS}, got {disposition!r}")
    iid = _norm(irwin_id)
    ev = {k: (evidence or {}).get(k) for k in EVIDENCE_KEYS if (evidence or {}).get(k) is not None}
    entry = {
        "review_id": review_id or uuid.uuid4().hex,
        "irwin_id": iid,
        "fire_name": fire_name,
        "reviewer": reviewer,
        "timestamp": _now(),
        "disposition": disposition,
        "rationale": rationale or "",
        "snapshot_id": snapshot_id,
        "evidence": ev,
        "map_image": map_image,
        "area_bucket": area_bucket,
    }
    store.setdefault(iid, []).append(entry)
    return entry


def has_review_id(store: dict[str, list[dict[str, Any]]], irwin_id: str, review_id: str) -> bool:
    """Guard against duplicate entries from a Streamlit rerun (handoff section 16)."""
    return any(e.get("review_id") == review_id for e in store.get(_norm(irwin_id), []))


# --------------------------------------------------------------------------- #
# Changes since the last saved in-app review
# --------------------------------------------------------------------------- #
def changes_since(review: dict[str, Any] | None, current: dict[str, Any]) -> list[dict[str, Any]]:
    """Supported comparisons only, against the saved review's own evidence.

    Compares a field only when the saved review actually recorded it, so nothing is
    invented for reviews that predate a field. Returns
    [{"label", "was", "now"}] for size and containment (handoff 9.2).
    """
    if not review:
        return []
    ev = review.get("evidence") or {}
    out: list[dict[str, Any]] = []

    was, now = ev.get("acres"), current.get("acres")
    if was is not None and now is not None and abs(float(now) - float(was)) >= 1:
        out.append({"label": "Size", "was": f"{float(was):,.0f}", "now": f"{float(now):,.0f} acres"})

    was, now = ev.get("containment"), current.get("containment")
    if was is not None and now is not None and float(now) != float(was):
        out.append({"label": "Containment", "was": f"{float(was):.0f}%", "now": f"{float(now):.0f}%"})

    return out


def map_path(review: dict[str, Any] | None) -> Path | None:
    """Filesystem path of a review's saved map, only when it exists on disk."""
    if not review or not review.get("map_image"):
        return None
    p = MAP_DIR / review["map_image"]
    return p if p.exists() else None
