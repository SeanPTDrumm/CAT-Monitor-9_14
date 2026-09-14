"""
Snapshot persistence and day-over-day comparison.

A snapshot = one WFIGS CSV download (optionally with its GeoJSON), stored
under data/snapshots/<snapshot_id>/ with the raw file(s), a normalised CSV,
and meta.json. Comparison between snapshots is a deterministic join on
IRWIN ID. All "change" values here are CALCULATED, not source-provided.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

import wfigs

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SNAP_DIR = DATA_DIR / "snapshots"

_ID_FMT = "%Y-%m-%d_%H%M%S"


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stored_csv_hash(snapshot_id: str) -> str | None:
    """Hash of a stored snapshot's raw CSV, from meta when present else computed.

    Snapshots saved before hashing was added carry no hash in meta, so it is derived
    from the stored raw.csv. Stored snapshots are never modified by this.
    """
    folder = SNAP_DIR / snapshot_id
    mf, raw = folder / "meta.json", folder / "raw.csv"
    if mf.exists():
        try:
            h = json.loads(mf.read_text(encoding="utf-8")).get("csv_sha256")
            if h:
                return h
        except json.JSONDecodeError:
            pass
    return content_hash(raw.read_bytes()) if raw.exists() else None


def find_duplicate_snapshot(csv_bytes: bytes) -> str | None:
    """Snapshot id whose raw CSV is byte-identical to `csv_bytes`, else None.

    Identity is decided by content, never by filename (handoff 1.3): WFIGS reissues
    updated files under the same name, and those must import as new snapshots.
    """
    incoming = content_hash(csv_bytes)
    for m in list_snapshots():
        if _stored_csv_hash(m["snapshot_id"]) == incoming:
            return m["snapshot_id"]
    return None


def _ensure_dirs() -> None:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)


def save_snapshot(
    csv_bytes: bytes,
    csv_filename: str,
    *,
    geojson_bytes: bytes | None = None,
    geojson_filename: str | None = None,
    retrieved_at: datetime | None = None,
    fetch_perimeters_if_missing: bool = False,
) -> str:
    """Validate, normalise and store a WFIGS download. Returns the snapshot id.

    If no GeoJSON is supplied and `fetch_perimeters_if_missing` is set, the current
    NIFC perimeter layer is downloaded so the snapshot has a perimeter of record.
    Failure to fetch is recorded in meta, never raised.

    Raises ValueError when the CSV content is byte-identical to a stored snapshot.
    The same filename with different content is a legitimate new snapshot."""
    df = wfigs.load_wfigs_csv(csv_bytes)  # raises ValueError on bad schema
    dup = find_duplicate_snapshot(csv_bytes)
    if dup is not None:
        raise ValueError(
            f"This file's contents are identical to snapshot {dup}; no new snapshot "
            "was created. Re-uploading the same filename is fine once the contents differ.")
    perimeter_fetch_note = None
    if geojson_bytes is None and fetch_perimeters_if_missing:
        try:
            from geo import perimeters as _perims
            geojson_bytes = _perims.download_current_geojson()
            geojson_filename = "NIFC current perimeters (live at save time)"
        except Exception as e:  # noqa: BLE001 - recorded, not fatal
            perimeter_fetch_note = f"Live perimeter download failed: {e}"
    _ensure_dirs()
    retrieved_at = retrieved_at or datetime.now()
    snapshot_id = retrieved_at.strftime(_ID_FMT)
    folder = SNAP_DIR / snapshot_id
    if folder.exists():  # same second twice; make unique
        snapshot_id = datetime.now().strftime(_ID_FMT + "_%f")
        folder = SNAP_DIR / snapshot_id
    folder.mkdir(parents=True)

    (folder / "raw.csv").write_bytes(csv_bytes)
    df.to_csv(folder / "normalized.csv", index=False)

    geo_meta: dict[str, Any] | None = None
    if geojson_bytes:
        (folder / "perimeters.geojson").write_bytes(geojson_bytes)
        summary = wfigs.load_geojson_summary(geojson_bytes)
        ids_in_csv = set(df["irwin_id"])
        geo_meta = {
            "filename": geojson_filename,
            "feature_count": summary["feature_count"],
            "geometry_types": summary["geometry_types"],
            "crs": summary["crs"],
            "irwin_match_count": len(ids_in_csv & set(summary["irwin_ids"])),
        }

    current_through = wfigs.data_current_through(df)
    meta = {
        "snapshot_id": snapshot_id,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "retrieved_at": retrieved_at.isoformat(timespec="seconds"),
        "csv_filename": csv_filename,
        "csv_sha256": content_hash(csv_bytes),
        "row_count": int(len(df)),
        "data_current_through": current_through.isoformat(timespec="seconds")
        if current_through is not None else None,
        "source_name": wfigs.SOURCE_NAME,
        "source_url": wfigs.SOURCE_URL,
        "geojson": geo_meta,
        "perimeter_fetch_note": perimeter_fetch_note,
    }
    (folder / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return snapshot_id


def list_snapshots() -> list[dict[str, Any]]:
    """All snapshot meta dicts, newest first."""
    _ensure_dirs()
    out = []
    for folder in SNAP_DIR.iterdir():
        mf = folder / "meta.json"
        if folder.is_dir() and mf.exists():
            try:
                out.append(json.loads(mf.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
    # Order by the source's own currency timestamp (most reliable; file modified
    # times are unreliable on synced drives), then by retrieval time.
    out.sort(key=lambda m: (m.get("data_current_through") or "", m.get("retrieved_at") or ""),
             reverse=True)
    return out


def load_snapshot(snapshot_id: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    folder = SNAP_DIR / snapshot_id
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    df = pd.read_csv(
        folder / "normalized.csv",
        dtype={"irwin_id": str, "county_fips": str, "objectid": str, "unique_fire_id": str},
        keep_default_na=True,
    )
    for c in wfigs.DATETIME_COLUMNS:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df, meta


def delete_snapshot(snapshot_id: str) -> None:
    folder = SNAP_DIR / snapshot_id
    if folder.exists() and folder.parent == SNAP_DIR:
        shutil.rmtree(folder)


def prior_snapshot_id(current_id: str) -> str | None:
    """The snapshot immediately before `current_id` by retrieval time, if any."""
    ids = [m["snapshot_id"] for m in list_snapshots()]  # newest first
    if current_id not in ids:
        return None
    i = ids.index(current_id)
    return ids[i + 1] if i + 1 < len(ids) else None


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #
COMPARE_COLUMNS = ["acres", "pct_contained", "perimeter_datetime", "perimeter_date_current",
                   "incident_modified", "origin_miles", "fire_name"]
CHANGE_COLUMNS = ["acres_prior", "acres_change", "acres_change_pct",
                  "pct_contained_prior", "pct_contained_change"]


def compare(current: pd.DataFrame, prior: pd.DataFrame | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Join current to prior on irwin_id.

    Returns (merged, dropped):
      merged  - current rows plus calculated change columns
      dropped - prior rows whose irwin_id is absent from current
    """
    cur = current.copy()
    if prior is None or prior.empty:
        cur["has_prior"] = False
        cur["is_new"] = False  # cannot say "new" without a prior snapshot
        for c in CHANGE_COLUMNS:
            cur[c] = float("nan")
        cur["perimeter_updated"] = None
        empty = prior.iloc[0:0] if prior is not None else pd.DataFrame(columns=cur.columns)
        return cur, empty

    p = prior.set_index("irwin_id")[[c for c in COMPARE_COLUMNS if c in prior.columns]]
    p = p.rename(columns={c: f"{c}_prior" for c in p.columns})
    merged = cur.merge(p, left_on="irwin_id", right_index=True, how="left", indicator=True)
    merged["has_prior"] = merged["_merge"] == "both"
    merged["is_new"] = ~merged["has_prior"]
    merged = merged.drop(columns="_merge")

    merged["acres_change"] = merged["acres"] - merged["acres_prior"]
    prior_pos = merged["acres_prior"].gt(0)
    merged["acres_change_pct"] = float("nan")
    merged.loc[prior_pos, "acres_change_pct"] = (
        merged.loc[prior_pos, "acres_change"] / merged.loc[prior_pos, "acres_prior"] * 100.0)
    merged["pct_contained_change"] = merged["pct_contained"] - merged["pct_contained_prior"]

    both = merged["perimeter_date_current"].notna() & merged["perimeter_date_current_prior"].notna()
    merged["perimeter_updated"] = None
    merged.loc[both, "perimeter_updated"] = (
        merged.loc[both, "perimeter_date_current"] > merged.loc[both, "perimeter_date_current_prior"])
    merged["perimeter_updated"] = merged["perimeter_updated"].astype(object)

    dropped = prior[~prior["irwin_id"].isin(set(cur["irwin_id"]))].copy()
    return merged, dropped


def material_changes(
    merged: pd.DataFrame,
    dropped: pd.DataFrame,
    statuses: dict[str, dict[str, Any]],
    *,
    acres_threshold: float = 1000.0,
    pct_threshold: float = 10.0,
    min_abs_for_pct: float = 100.0,
) -> pd.DataFrame:
    """Rows worth a human look. Deterministic rules, no scoring.

    Tracked = analyst status other than "No Action".
    Flags:
      tracked fire: any acres change, any containment change, perimeter updated
      any fire:     acres growth >= acres_threshold, OR >= pct_threshold % when the
                    absolute growth is at least min_abs_for_pct acres
      any fire:     new in this snapshot
      tracked fire: dropped from feed
    """
    rows = []

    def status_of(iid: str) -> str:
        return (statuses.get(iid) or {}).get("status") or "No Action"

    for _, r in merged.iterrows():
        st = status_of(r["irwin_id"])
        tracked = st != "No Action"
        reasons = []
        ac = r.get("acres_change")
        pc = r.get("pct_contained_change")
        acp = r.get("acres_change_pct")
        if bool(r.get("is_new")):
            reasons.append("New in this snapshot")
        if pd.notna(ac) and ac != 0:
            if tracked:
                reasons.append(f"Acres {ac:+,.0f}")
            elif ac >= acres_threshold or (pd.notna(acp) and acp >= pct_threshold and ac >= min_abs_for_pct):
                reasons.append(f"Acres {ac:+,.0f} ({acp:+.0f}%)" if pd.notna(acp) else f"Acres {ac:+,.0f}")
        if tracked and pd.notna(pc) and pc != 0:
            reasons.append(f"Containment {pc:+.0f} pts")
        if tracked and r.get("perimeter_updated") is True:
            reasons.append("Perimeter updated")
        if reasons:
            rows.append({
                "Status": st, "Fire": r.get("fire_name"), "State": r.get("state"),
                "Acres": r.get("acres"), "Acres change": ac,
                "Containment %": r.get("pct_contained"), "Containment change": pc,
                "Why flagged": "; ".join(reasons), "irwin_id": r["irwin_id"],
            })

    for _, r in dropped.iterrows():
        st = status_of(r["irwin_id"])
        if st != "No Action":
            rows.append({
                "Status": st, "Fire": r.get("fire_name"), "State": r.get("state"),
                "Acres": r.get("acres"), "Acres change": float("nan"),
                "Containment %": r.get("pct_contained"), "Containment change": float("nan"),
                "Why flagged": "Dropped from WFIGS feed (tracked fire)", "irwin_id": r["irwin_id"],
            })

    cols = ["Status", "Fire", "State", "Acres", "Acres change", "Containment %",
            "Containment change", "Why flagged", "irwin_id"]
    out = pd.DataFrame(rows, columns=cols)
    for c in ["Acres", "Acres change", "Containment %", "Containment change"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    order = {"Existing Moratorium": 0, "Investigate": 1, "Monitor": 2, "No Action": 3}
    if not out.empty:
        out["_o"] = out["Status"].map(order).fillna(9)
        out = out.sort_values(["_o", "Acres change"], ascending=[True, False], na_position="last")
        out = out.drop(columns="_o").reset_index(drop=True)
    return out
