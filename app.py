"""
Catastrophe Monitor - Version 0.3 (U.S. Wildfire)  -  "Hiscox CAT Map"

Map-first underwriting dashboard: WFIGS national fire list -> deterministic
urgency 1-3 with a human review queue -> actual perimeter geometry with
ZCTA / place distances -> analyst decisions preserved across downloads.

Run:  streamlit run app.py

UI Redesign: 2026-09-10 - Simplified dashboard with top 5 fires view
"""
# CAT_MONITOR_BUILD: REV_1_3_1_VERIFIED

from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import analyst
import attention
import baseline
import dashboard
import dashboard_map
import maps
import reviews
import screening
import snapshots
import urgency
import wfigs
from geo import analysis, census, spatial

NV = wfigs.NOT_VERIFIED
BASE_DIR = Path(__file__).resolve().parent
PAGES = ["Dashboard", "Fire Table", "Fire Detail"]
STATUS_ORDER = {"Existing Moratorium": 0, "Investigate": 1, "Monitor": 2, "No Action": 3}
STATUS_ICON = {"No Action": "⚪", "Monitor": "🟡", "Investigate": "🔴", "Existing Moratorium": "🟣"}
STATUS_LABEL = {s: f"{STATUS_ICON[s]} {s}" for s in analyst.STATUS_OPTIONS}
LABEL_STATUS = {v: k for k, v in STATUS_LABEL.items()}
LEVEL_ICON = {1: "🔵", 2: "🟠", 3: "🔴"}
SORT_PRESETS = {
    "Urgency, then Justin order": (["urgency_level", "origin_miles", "acres"], [False, True, False]),
    "Justin order (WFIGS reference miles, nearest first)": (["origin_miles", "acres"], [True, False]),
    "Tracked first": (["_status_order", "urgency_level", "origin_miles"], [True, False, True]),
    "Lowest containment": (["pct_contained", "acres"], [True, False]),
    "Largest": (["acres"], [False]),
    "Biggest growth since prior": (["acres_change"], [False]),
    "Closest to a place (perimeter)": (["perim_place_miles", "origin_miles"], [True, True]),
}

st.set_page_config(page_title="Catastrophe Monitor", page_icon="🔥", layout="wide")


# --------------------------------------------------------------------------- #
# Formatting helpers - every missing value renders as "Not verified"
# --------------------------------------------------------------------------- #
def _missing(v) -> bool:
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(v, str) and v.strip() == ""


def fmt_num(v, decimals: int = 0, suffix: str = "") -> str:
    return NV if _missing(v) else f"{v:,.{decimals}f}{suffix}"


def fmt_signed(v, decimals: int = 0, suffix: str = "") -> str:
    return NV if _missing(v) else f"{v:+,.{decimals}f}{suffix}"


def fmt_dt(v, utc: bool = True) -> str:
    if _missing(v):
        return NV
    ts = pd.Timestamp(v)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts.strftime("%Y-%m-%d %H:%M") + (" UTC" if utc else "")


def fmt_text(v) -> str:
    return NV if _missing(v) else str(v)


def clean_text(v) -> str:
    """Free text as a plain string: missing -> "", numbers -> their digits.

    Analyst fields reach the frame as None (stored json null), as float NaN (pandas
    turns None into NaN in a string-dtype column), or as a number the analyst typed.
    Every string method in the app must go through this, and a missing value must
    never surface as the literal text "nan".
    """
    if _missing(v):
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))          # 2500.0 typed as population -> "2500"
    return str(v).strip()


def origin_desc(row) -> str:
    if _missing(row.get("origin_miles")):
        return NV
    return (f"{row['origin_miles']:g} mi {row['origin_direction']} of "
            f"{row['origin_place']}, {row['origin_place_state']}")


def when(meta: dict | None) -> str:
    if not meta:
        return NV
    return fmt_dt(meta.get("data_current_through") or meta["retrieved_at"])


def when_dt(meta: dict | None) -> datetime | None:
    if not meta:
        return None
    return pd.Timestamp(meta.get("data_current_through") or meta["retrieved_at"]).to_pydatetime()


def snapshot_label(meta: dict) -> str:
    return f"data thru {when(meta)}  |  {meta['csv_filename']}  |  {meta['row_count']} fires"


def badge(status: str, unconfirmed: bool = False) -> str:
    colour = analyst.STATUS_COLOURS.get(status, "#9aa0a6")
    extra = (" <span style='background:#fff3cd;color:#7a5a00;border:1px solid #e0a100;border-radius:6px;"
             "padding:1px 6px;font-size:0.8em'>unconfirmed baseline</span>" if unconfirmed else "")
    return (f"<span style='background:{colour};color:white;border-radius:6px;padding:2px 10px;font-weight:600'>"
            f"{status}</span>{extra}")


def level_chip(level: int, label: str, provisional: bool = False) -> str:
    colour = urgency.LEVEL_COLOUR.get(level, "#6c8ebf")
    prov = " <span style='color:#7a5a00;font-size:0.8em'>(provisional: origin-point only)</span>" if provisional else ""
    return (f"<span style='background:{colour};color:white;border-radius:6px;padding:2px 10px;font-weight:600'>"
            f"Urgency {level} · {label}</span>{prov}")


def _kv(label: str, value: str) -> None:
    st.markdown(f"<span style='color:grey'>{label}:</span> {value}", unsafe_allow_html=True)


def parse_zips(text: str | None) -> set[str]:
    return set(re.findall(r"\b\d{5}\b", text or ""))


# --------------------------------------------------------------------------- #
# Data access
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def _load(snapshot_id: str):
    return snapshots.load_snapshot(snapshot_id)


@st.cache_data(show_spinner=False)
def _compare(current_id: str, prior_id: str | None):
    cur, _ = _load(current_id)
    prior = _load(prior_id)[0] if prior_id else None
    return snapshots.compare(cur, prior)


def _spatial_version(snapshot_id: str) -> str:
    folder = snapshots.SNAP_DIR / snapshot_id / "spatial"
    if not folder.exists():
        return "0"
    files = list(folder.glob("*.json"))
    return f"{len(files)}:{max((f.stat().st_mtime for f in files), default=0)}"


@st.cache_data(show_spinner=False)
def _spatial_all(snapshot_id: str, version: str) -> dict:
    return {iid: analysis.load(snapshot_id, iid) for iid in analysis.list_calculated(snapshot_id)}


@st.cache_data(show_spinner=False)
def _load_inputs_cached(snapshot_id: str, irwin_id: str, version: str):
    """Cached wrapper around analysis.load_inputs - avoids re-reading the full
    perimeter/ZCTA/place geometry JSON from disk on every rerun (sort, filter,
    fire selection, review-form open). `version` ties the cache to the same
    per-snapshot spatial-file signature used by _spatial_all."""
    return analysis.load_inputs(snapshot_id, irwin_id)



def _records() -> dict:
    if "analyst_records" not in st.session_state:
        st.session_state["analyst_records"] = analyst.load()
    return st.session_state["analyst_records"]


def _save_records() -> None:
    analyst.save(st.session_state["analyst_records"])


def _editor() -> str | None:
    return (st.session_state.get("editor_name") or "").strip() or None


def _status_of(iid: str) -> str:
    return analyst.get(_records(), iid).get("status", analyst.DEFAULT_STATUS)


def moratorium_zip_set(recs: dict) -> set[str]:
    zips: set[str] = set()
    for r in recs.values():
        if r.get("status") == "Existing Moratorium":
            zips |= parse_zips(r.get("moratorium_zips"))
    return zips


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
def data_controls(c, include_upload: bool = True) -> None:
    """Load / import widgets. Rendered into the sidebar on the legacy pages, and into
    the dashboard's own "Data" popover so the dashboard carries no admin sidebar."""
    if include_upload:
        with c.expander("Upload files", expanded=False):
            csv_up = st.file_uploader("WFIGS perimeter CSV", type=["csv"], key="csv_up")
            geo_up = st.file_uploader("Matching GeoJSON (optional; fetched live if omitted)", type=["geojson", "json"], key="geo_up")
            if st.button("Save snapshot from upload", disabled=csv_up is None, use_container_width=True):
                with st.spinner("Saving snapshot and fetching live perimeters…"):
                    try:
                        sid = snapshots.save_snapshot(
                            csv_up.getvalue(), csv_up.name,
                            geojson_bytes=geo_up.getvalue() if geo_up else None,
                            geojson_filename=geo_up.name if geo_up else None,
                            fetch_perimeters_if_missing=True)
                        st.cache_data.clear()
                        st.session_state["current_id"] = sid
                        st.session_state.pop(f"prior_pick_{sid}", None)
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

    with c.expander("Import from project folder", expanded=False):
        already = {m["csv_filename"] for m in snapshots.list_snapshots()}
        folder_csvs = sorted(p.name for p in BASE_DIR.glob("*.csv") if p.name not in already)
        folder_geo = ["(fetch live)"] + sorted(p.name for p in BASE_DIR.glob("*.geojson"))
        if not folder_csvs:
            st.caption("No un-imported CSV files in the project folder.")
        else:
            pick = st.selectbox("CSV file", folder_csvs, key="folder_csv")
            geo_pick = st.selectbox("GeoJSON", folder_geo, key="folder_geo")
            if st.button("Import selected", use_container_width=True):
                p = BASE_DIR / pick
                g = BASE_DIR / geo_pick if not geo_pick.startswith("(") else None
                with st.spinner("Importing…"):
                    try:
                        sid = snapshots.save_snapshot(
                            p.read_bytes(), p.name,
                            geojson_bytes=g.read_bytes() if g else None, geojson_filename=g.name if g else None,
                            retrieved_at=datetime.fromtimestamp(p.stat().st_mtime), fetch_perimeters_if_missing=True)
                        st.cache_data.clear()
                        st.session_state["current_id"] = sid
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

    with c.expander("Import Justin's baseline notes", expanded=False):
        books = baseline.find_workbooks()
        if not books:
            st.caption("Put the tracking workbook in reference/ to enable this.")
        else:
            wb = st.selectbox("Workbook", books, format_func=lambda p: p.name, key="bl_wb")
            sheets = baseline.sheet_names(wb)
            sheet = st.selectbox("Sheet (day)", sheets,
                                 index=sheets.index(baseline.DEFAULT_SHEET) if baseline.DEFAULT_SHEET in sheets else 0,
                                 key="bl_sheet")
            if st.button("Import baseline notes", use_container_width=True):
                try:
                    summary = baseline.import_baseline(_records(), wb, sheet)
                    _save_records()
                    st.session_state["baseline_summary"] = summary
                    st.rerun()
                except (ValueError, KeyError) as e:
                    st.error(f"Import failed: {e}")
            if "baseline_summary" in st.session_state:
                s = st.session_state["baseline_summary"]
                st.success(f"Sheet {s['sheet']}: {s['imported']} imported, {s['skipped_existing']} skipped.")

            st.divider()
            st.caption("**Set the review baseline.** The chosen sheet is treated as the last "
                       "completed review: every fire on it is stamped with the acreage, "
                       "containment and perimeter date Justin was looking at, so a fire he "
                       "dismissed stays quiet until those facts move.")
            rev_sheet = st.selectbox("Last reviewed sheet", sheets,
                                     index=sheets.index(baseline.REVIEW_SHEET)
                                     if baseline.REVIEW_SHEET in sheets else len(sheets) - 1,
                                     key="bl_review_sheet")
            if st.button("Set review baseline from this sheet", use_container_width=True,
                         key="bl_seed"):
                try:
                    summary = baseline.seed_review_watermarks(
                        _records(), wb, review_sheet=rev_sheet,
                        fallback_sheets=tuple(s for s in reversed(sheets) if s != rev_sheet),
                        by=_editor())
                    _save_records()
                    st.session_state["review_seed_summary"] = summary
                    st.cache_data.clear()
                    st.rerun()
                except (ValueError, KeyError) as e:
                    st.error(f"Could not set the review baseline: {e}")
            if "review_seed_summary" in st.session_state:
                s = st.session_state["review_seed_summary"]
                st.success(f"Review baseline {s['review_sheet']}: {s['seeded']} fires stamped, "
                           f"{s['seeded_from_fallback']} from an earlier sheet, "
                           f"{s['skipped_existing']} already had one.")
                for m in s.get("moratorium_expiry_filled", []):
                    st.caption(f"Moratorium expiry read from the analyst note: "
                               f"{m['fire']} → {m['expires']}")


def snapshot_controls(c, metas: list[dict]) -> None:
    """Current / prior snapshot selectors. Writes session state; reads happen in
    resolve_snapshots() so the dashboard can render these late, inside a popover."""
    ids = [m["snapshot_id"] for m in metas]
    labels = {m["snapshot_id"]: snapshot_label(m) for m in metas}
    current_id, _ = resolve_snapshots(metas)
    c.selectbox("Current snapshot", ids, index=ids.index(current_id),
                format_func=lambda i: labels[i], key="current_id")
    prior_choices = ["(none)"] + [i for i in ids if i != current_id]
    c.selectbox("Compare with prior snapshot", prior_choices,
                format_func=lambda i: "(none)" if i == "(none)" else labels[i],
                key=f"prior_pick_{current_id}")


def housekeeping_controls(c, metas: list[dict]) -> None:
    ids = [m["snapshot_id"] for m in metas]
    labels = {m["snapshot_id"]: snapshot_label(m) for m in metas}
    with c.expander("Rules (screening and urgency)", expanded=False):
        st.caption(attention.describe())
        st.caption(urgency.describe())
        st.caption(screening.describe())
        st.caption(census.population_status())
    with c.expander("Snapshot housekeeping", expanded=False):
        st.caption(f"{len(metas)} snapshot(s) stored under data/snapshots/")
        del_pick = st.selectbox("Delete a snapshot", ["(select)"] + ids, key="hk_del",
                                format_func=lambda i: i if i == "(select)" else labels[i])
        confirm = st.checkbox("I understand this removes the stored copy of that download.",
                              key="hk_confirm")
        if st.button("Delete", disabled=(del_pick == "(select)" or not confirm), key="hk_go"):
            snapshots.delete_snapshot(del_pick)
            st.cache_data.clear()
            st.session_state.pop("current_id", None)
            st.rerun()


def resolve_snapshots(metas: list[dict]) -> tuple[str | None, str | None]:
    """Which snapshots are in play, from session state alone - no widgets drawn.

    Lets main() know the current/prior ids before the page body renders, so the
    dashboard can keep its data controls out of the way.
    """
    ids = [m["snapshot_id"] for m in metas]
    if not ids:
        return None, None
    current_id = st.session_state.get("current_id")
    if current_id not in ids:
        current_id = ids[0]
        st.session_state["current_id"] = current_id
    # Seed the prior-snapshot choice before its widget exists, so the automatic
    # "immediately preceding download" default survives into the widget.
    key = f"prior_pick_{current_id}"
    if key not in st.session_state:
        auto_prior = snapshots.prior_snapshot_id(current_id)
        st.session_state[key] = auto_prior or "(none)"
    pick = st.session_state[key]
    prior_id = None if pick in (None, "(none)") or pick not in ids else pick
    return current_id, prior_id


def sidebar(minimal: bool = False) -> tuple[str | None, str | None, str]:
    """Navigation and data controls.

    `minimal=True` (dashboard): skip sidebar entirely. The dashboard is its own
    layout and does not share the sidebar navigation model. Analyst name and
    resolved snapshots are returned only.

    `minimal=False` (legacy pages): full sidebar with navigation, data controls,
    and snapshot management.
    """
    if minimal:
        # Dashboard: no sidebar at all. Store analyst name in session only.
        st.session_state.setdefault("editor_name", "")
        metas = snapshots.list_snapshots()
        return (*resolve_snapshots(metas), "Dashboard")

    st.sidebar.title("Catastrophe Monitor")
    st.sidebar.caption("v0.6 - U.S. Wildfire")
    page = st.sidebar.radio("Page", PAGES, key="page")
    st.sidebar.text_input("Your name (recorded on edits)", key="editor_name", placeholder="e.g. Justin")

    metas = snapshots.list_snapshots()
    st.sidebar.divider()
    st.sidebar.subheader("Load a new WFIGS download")
    data_controls(st.sidebar)
    st.sidebar.divider()
    st.sidebar.subheader("Snapshots")
    if not metas:
        st.sidebar.info("No snapshots yet. Load a WFIGS CSV above.")
        return None, None, page
    snapshot_controls(st.sidebar, metas)
    housekeeping_controls(st.sidebar, metas)
    return (*resolve_snapshots(metas), page)


# --------------------------------------------------------------------------- #
# Frame: facts + change + analyst + screening + geography + urgency
# --------------------------------------------------------------------------- #
def auto_description(r: pd.Series) -> str:
    bits = []
    if not _missing(r.get("acres")):
        bits.append(f"{r['acres']:,.0f} acres")
    bits.append(f"{r['pct_contained']:.0f}% contained" if not _missing(r.get("pct_contained")) else "containment not reported")
    if not _missing(r.get("acres_change")) and abs(r["acres_change"]) >= 1:
        bits.append(f"{r['acres_change']:+,.0f} acres since prior snapshot")
    s1 = ", ".join(bits) + "."
    s2 = ""
    if r.get("geo_status") == "calculated":
        if r.get("nearest_place"):
            s2 = f" Nearest place: {r['nearest_place']}."
        if r.get("zcta_verify"):
            s2 += f" Perimeter intersects ZCTA(s) {r['zcta_verify']}."
    elif not _missing(r.get("origin_miles")):
        s2 = f" WFIGS locates the origin {origin_desc(r)} (perimeter distance not yet calculated)."
    return (s1 + s2).strip()


def build_frame(merged: pd.DataFrame, snapshot_id: str, prior_id: str | None) -> pd.DataFrame:
    recs = _records()
    df = merged.copy()
    recs_rows = [analyst.get(recs, iid, nm) for iid, nm in zip(df["irwin_id"], df["fire_name"])]
    # Analyst text lands in the frame as clean strings, so no downstream string
    # method can meet a None or a NaN. Status keeps its own default.
    for k in analyst.ANALYST_FIELDS:
        if k == "status":
            df[k] = [r.get(k) or analyst.DEFAULT_STATUS for r in recs_rows]
        else:
            df[k] = [clean_text(r.get(k)) for r in recs_rows]
    df["unconfirmed"] = [analyst.is_unconfirmed(r) for r in recs_rows]
    df["baseline_reference"] = [clean_text(r.get("baseline_reference")) for r in recs_rows]
    df["urgency_human"] = [r.get("urgency_human") for r in recs_rows]
    df["_kept"] = [r.get("urgency_kept") or {} for r in recs_rows]
    df["_status_order"] = df["status"].map(STATUS_ORDER).fillna(9)
    df["origin_ref"] = [origin_desc(r) for _, r in df.iterrows()]
    df = screening.apply(df)

    sp_all = _spatial_all(snapshot_id, _spatial_version(snapshot_id))
    sp_prior = _spatial_all(prior_id, _spatial_version(prior_id)) if prior_id else {}
    mora_zips = set()  # moratorium_zip_set(recs)  # Temporarily disabled

    cols = {k: [] for k in ("geo_status", "geo_reason", "perim_place_miles", "nearest_place", "zcta_verify",
                            "zcta_review_n", "zcta_in_moratorium", "urgency_level", "urgency_label", "urgency_reason",
                            "urgency_nearest", "urgency_rec", "urgency_change", "urgency_note", "urgency_provisional",
                            "geo_change", "attention")}
    for (_, row), rec in zip(df.iterrows(), recs_rows):
        sp = sp_all.get(row["irwin_id"])
        spp = sp_prior.get(row["irwin_id"]) if sp_prior else None
        gch = analysis.compare(sp, spp) if sp and spp else {}
        if sp and sp.get("status") == "calculated":
            s = sp["spatial"]
            cols["geo_status"].append("calculated"); cols["geo_reason"].append("")
            p0 = s["places"][0] if s["places"] else None
            cols["perim_place_miles"].append(p0["distance_miles"] if p0 else None)
            cols["nearest_place"].append(
                (f"{p0['name']} {p0['distance_miles']:.1f} mi {p0['direction_from_fire']}"
                 + (f" (pop {p0['population_2020']:,})" if p0.get("population_2020") is not None else "")) if p0 else "")
            ver = [z["zcta"] for z in s["zctas"] if z["intersects"]]
            cols["zcta_verify"].append(", ".join(ver))
            cols["zcta_review_n"].append(sum(1 for z in s["zctas"] if z["review_state"] in ("VERIFY", "REVIEW")))
            cols["zcta_in_moratorium"].append(", ".join(z["zcta"] for z in s["zctas"]
                                                        if z["review_state"] in ("VERIFY", "REVIEW") and z["zcta"] in mora_zips))
        else:
            cols["geo_status"].append("not_calculated" if sp else "pending")
            cols["geo_reason"].append((sp or {}).get("reason", ""))
            cols["perim_place_miles"].append(None)
            for k in ("nearest_place", "zcta_verify", "zcta_in_moratorium"):
                cols[k].append("")
            cols["zcta_review_n"].append(None)
        u = urgency.assess(row, sp, gch, rec["status"])
        cols["urgency_level"].append(u["level"]); cols["urgency_label"].append(u["label"])
        cols["urgency_reason"].append(u["reason_text"]); cols["urgency_nearest"].append(u["nearest"] or "")
        cols["urgency_rec"].append(u["recommended_status"]); cols["urgency_change"].append(u["change_recommended"])
        cols["urgency_note"].append(u["note"]); cols["urgency_provisional"].append(u["provisional"])
        cols["geo_change"].append(gch)
        # Dashboard screening: "has anything material changed since the last review?"
        # Same row / spatial / change / record already in hand - no second pass.
        cols["attention"].append(
            attention.assess(row, sp, gch, rec,
                             review=reviews.latest(_review_store(), row["irwin_id"])))
    for k, v in cols.items():
        df[k] = v
    # a recommendation the analyst already chose to keep, at this level, is not re-queued
    df["urgency_kept_match"] = [bool(k) and k.get("level") == lv and k.get("recommended") == rc
                                for k, lv, rc in zip(df["_kept"], df["urgency_level"], df["urgency_rec"])]
    df["description_auto"] = [auto_description(r) for _, r in df.iterrows()]
    # Analyst text may arrive as None, NaN or a number; normalise before any string
    # method, and never let a missing value render as the literal text "nan".
    df["description_shown"] = [clean_text(d) or a
                               for d, a in zip(df["description"], df["description_auto"])]
    return df


def sort_frame(df: pd.DataFrame, preset: str) -> pd.DataFrame:
    cols, asc = SORT_PRESETS[preset]
    return df.sort_values(cols, ascending=asc, na_position="last")


def default_detail_fire(df: pd.DataFrame) -> str | None:
    """Highest urgency fire whose VERIFY/REVIEW ZCTAs are not all already under moratorium;
    else the largest fire the underwriter has at Monitor or higher."""
    if df.empty:
        return None
    cand = df[(df["status"] != "Existing Moratorium")].copy()
    n_review = cand["zcta_review_n"].fillna(0)
    n_mora = cand["zcta_in_moratorium"].apply(lambda s: len([z for z in str(s).split(",") if z.strip()]))
    cand = cand[~((n_review > 0) & (n_mora >= n_review))]
    cand = cand[cand["urgency_level"] >= 2]
    if not cand.empty:
        cand = cand.sort_values(["urgency_level", "geo_status", "acres"], ascending=[False, True, False])
        return cand.iloc[0]["irwin_id"]
    tracked = df[df["status"] != analyst.DEFAULT_STATUS].sort_values("acres", ascending=False)
    if not tracked.empty:
        return tracked.iloc[0]["irwin_id"]
    return df.sort_values("urgency_level", ascending=False).iloc[0]["irwin_id"]


def geo_candidates(df: pd.DataFrame) -> list[tuple[str, str]]:
    sel = df[(df["status"] != analyst.DEFAULT_STATUS) | (df["urgency_level"] >= 2)]
    sel = sel[sel["geo_status"] == "pending"]
    return [(r.irwin_id, r.fire_name) for r in sel.itertuples()]


def run_geography(snapshot_id: str, fires: list[tuple[str, str]], force: bool = False) -> None:
    if not fires:
        return
    bar = st.progress(0.0, text="Computing geography…")

    def prog(i, n, name):
        bar.progress(i / n, text=f"Geography {i}/{n}: {name}")

    analysis.run_many(snapshot_id, fires, force=force, progress=prog)
    bar.empty()
    st.cache_data.clear()


# --------------------------------------------------------------------------- #
# Shared widgets
# --------------------------------------------------------------------------- #
def review_queue(df: pd.DataFrame, key: str, limit: int | None = None) -> None:
    q = df[df["urgency_change"] & ~df["urgency_kept_match"]
           & ((df["urgency_level"] >= 2) | (df["status"] != analyst.DEFAULT_STATUS))]
    q = q.sort_values(["urgency_level", "acres"], ascending=[False, False])
    if limit:
        q = q.head(limit)
    if q.empty:
        st.success("No status changes recommended under the current rules.")
        return
    st.caption("Each row is a deterministic recommendation. Nothing changes until you press Accept or Keep. "
               "Keep records your decision and hides the item until the fire's level or recommendation changes. "
               "Your own 1-3 level is recorded for calibration.")
    recs = _records()
    for r in q.itertuples():
        c1, c2, c3, c4, c5 = st.columns([3.2, 2.2, 1.2, 1, 1])
        with c1:
            # Fix #4: Add context badge (NEW or CHANGED)
            is_new = r.is_new if hasattr(r, 'is_new') else False
            badge_text = "🆕 NEW" if is_new else "🔄 CHANGED"
            st.markdown(f"{badge_text} {LEVEL_ICON[r.urgency_level]} **{r.fire_name}** ({r.state}) · "
                        f"{STATUS_LABEL[r.status]} → **{STATUS_LABEL[r.urgency_rec]}**"
                        + (" · *provisional*" if r.urgency_provisional else ""))
            st.caption(f"{r.urgency_reason} · {r.urgency_nearest}")
        with c2:
            st.caption(r.description_shown[:160] + ("…" if len(r.description_shown) > 160 else ""))
        with c3:
            human = st.selectbox("Your level", [1, 2, 3], index=r.urgency_level - 1, key=f"{key}_hl_{r.irwin_id}",
                                 label_visibility="collapsed")
        with c4:
            if st.button("Accept", key=f"{key}_acc_{r.irwin_id}", type="primary", use_container_width=True):
                analyst.update(recs, r.irwin_id, r.fire_name, by=_editor(), status=r.urgency_rec)
                analyst.record_urgency_decision(recs, r.irwin_id, r.fire_name, app_level=r.urgency_level,
                                                app_recommended=r.urgency_rec, action="accepted",
                                                human_level=human, status_after=r.urgency_rec, by=_editor())
                _save_records(); st.rerun()
        with c5:
            if st.button("Keep", key=f"{key}_keep_{r.irwin_id}", use_container_width=True):
                analyst.record_urgency_decision(recs, r.irwin_id, r.fire_name, app_level=r.urgency_level,
                                                app_recommended=r.urgency_rec, action="kept_current",
                                                human_level=human, status_after=r.status, by=_editor())
                _save_records(); st.toast(f"Kept {r.status} for {r.fire_name}"); st.rerun()


def fire_picker_table(frame: pd.DataFrame, key: str, display_cols: list[str]) -> None:
    shown = frame[display_cols].copy()
    if "Status" in shown.columns:
        shown["Status"] = [STATUS_LABEL.get(s, s) for s in shown["Status"]]
    if "Urgency" in shown.columns:
        shown["Urgency"] = [f"{LEVEL_ICON.get(int(v), '')} {int(v)}" if not _missing(v) else "" for v in shown["Urgency"]]
    for c, fn in {"Acres": lambda v: fmt_num(v, 0), "Acres change": lambda v: fmt_signed(v, 0),
                  "Containment %": lambda v: fmt_num(v, 0, "%"), "Containment change": lambda v: fmt_signed(v, 0, " pts"),
                  "Perimeter → place (mi)": lambda v: fmt_num(v, 1)}.items():
        if c in shown.columns:
            shown[c] = [fn(v) for v in shown[c]]
    if "Why flagged" in shown.columns:
        is_new = shown["Why flagged"].astype(str).str.contains("New in this snapshot", regex=False)
        for c in ("Acres change", "Containment change"):
            if c in shown.columns:
                shown.loc[is_new, c] = "n/a (new)"
    event = st.dataframe(shown, hide_index=True, use_container_width=True, on_select="rerun",
                         selection_mode="single-row", key=key)
    rows = event.selection.rows if event and event.selection else []
    if rows:
        iid = frame.iloc[rows[0]]["irwin_id"]
        if st.button(f"Open detail for {frame.iloc[rows[0]]['Fire']}", key=f"{key}_open"):
            _goto_detail(iid)


# --------------------------------------------------------------------------- #
# Page: Dashboard
# --------------------------------------------------------------------------- #
def _goto_detail(irwin_id: str) -> None:
    """Navigate to Fire Detail for this fire.

    Records the intent rather than writing "page" directly: the page radio owns that
    key, and assigning to a widget's key after the widget exists in the current run
    does not take effect. main() applies pending_page before the radio is created.
    """
    st.session_state["selected_irwin"] = irwin_id
    st.session_state["pending_page"] = "Fire Detail"
    st.rerun()


def _iso(v) -> str | None:
    """Timestamp as ISO text for storage, or None. Never a guess."""
    if _missing(v):
        return None
    try:
        return pd.Timestamp(v).isoformat(timespec="seconds")
    except (ValueError, TypeError):
        return None


def _dashboard_data_controls(metas: list[dict]) -> None:
    """Daily WFIGS update: two files in, then update and compare."""
    current_id, prior_id = resolve_snapshots(metas) if metas else (None, None)
    meta_by_id = {m["snapshot_id"]: m for m in metas}

    cur_meta = meta_by_id.get(current_id) if current_id else None
    prior_meta = meta_by_id.get(prior_id) if prior_id else None

    if cur_meta:
        c1, c2 = st.columns(2)
        c1.metric("Current", when(cur_meta))
        c2.metric("Compared with", when(prior_meta) if prior_meta else "None")
    else:
        st.info("No current snapshot. Load the newest WFIGS CSV and matching GeoJSON.")

    st.caption("Daily update — use the CSV and GeoJSON from the same WFIGS download.")
    c1, c2 = st.columns(2)
    with c1:
        csv_up = st.file_uploader("WFIGS CSV", type=["csv"], key="daily_csv_up")
    with c2:
        geo_up = st.file_uploader("Matching GeoJSON", type=["geojson", "json"],
                                  key="daily_geo_up")

    ready = csv_up is not None and geo_up is not None
    if ready:
        st.caption(f"Ready: {csv_up.name} + {geo_up.name}")
    else:
        st.caption("Choose both files to continue.")

    if st.button("Update & Compare", type="primary", disabled=not ready,
                 use_container_width=True, key="daily_save_compare"):
        with st.spinner("Loading WFIGS data and preparing the comparison…"):
            try:
                sid = snapshots.save_snapshot(
                    csv_up.getvalue(), csv_up.name,
                    geojson_bytes=geo_up.getvalue(),
                    geojson_filename=geo_up.name,
                    fetch_perimeters_if_missing=False,
                )
                st.cache_data.clear()
                st.session_state["current_id"] = sid
                st.session_state.pop(f"prior_pick_{sid}", None)
                st.toast("New snapshot loaded and comparison prepared.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))

    with st.expander("Advanced / Admin", expanded=False):
        st.text_input("Reviewer name", key="editor_name", placeholder="e.g. Justin")
        data_controls(st, include_upload=False)
        refreshed = snapshots.list_snapshots()
        if refreshed:
            st.divider()
            snapshot_controls(st, refreshed)
            housekeeping_controls(st, refreshed)


def _compare_label(meta: dict, prior_meta: dict | None) -> str | None:
    """'Sep 10 15:43 → Sep 11 18:08' - which two snapshots are being compared."""
    if not prior_meta:
        return None

    def short(m: dict) -> str:
        v = m.get("data_current_through")
        try:
            return pd.Timestamp(v).strftime("%b %d %H:%M")
        except (ValueError, TypeError):
            return str(v or "unknown")

    return f"{short(prior_meta)} → {short(meta)}"


def _perimeter_note(meta: dict, prior_meta: dict | None) -> str | None:
    """A transparent, read-only note when perimeter provenance is not comparable.

    Reports what the stored metadata actually says; repairs nothing and writes
    nothing. Two real cases in the current data: a snapshot whose perimeter was
    fetched live at save time (so it is not one of the downloaded GeoJSON files),
    and a snapshot with no perimeter of record at all. In both cases a perimeter
    comparison against that snapshot cannot be made truthfully, so we say so
    rather than implying the perimeter did or did not move.
    """
    if not prior_meta:
        return None
    problems = []
    for label, m in (("current", meta), ("prior", prior_meta)):
        gj = m.get("geojson")
        if not gj:
            problems.append(f"the {label} snapshot has no perimeter of record")
        else:
            fn = str(gj.get("filename") or "")
            if not fn.lower().endswith(".geojson"):
                problems.append(f"the {label} snapshot's perimeter was fetched live "
                                f"at save time, not from a downloaded file")
    if not problems:
        return None
    return ("Perimeter comparison unavailable: " + "; ".join(problems)
            + ". Fire-record changes below are unaffected.")


def _dashboard_context(df: pd.DataFrame, meta: dict, metas: list[dict],
                       dropped: pd.DataFrame | None = None,
                       prior_meta: dict | None = None) -> dict:
    """Read-only accessors handed to the presentation layer.

    Keeps dashboard.py free of Streamlit caching, file paths and analyst I/O, and
    keeps app.py free of layout.
    """
    recs = _records()
    sid = meta["snapshot_id"]
    store = _review_store()
    compare_label = _compare_label(meta, prior_meta)
    perimeter_note = _perimeter_note(meta, prior_meta)

    def save_review(row: pd.Series, disposition: str, rationale: str,
                    quick_reason: str | None, logged: bool, save_map: bool) -> None:
        """Persist a quick review or an intentional logged review.

        Disposition is not treated as changed until persistence succeeds, and a
        per-submission review id makes a Streamlit rerun unable to append twice.
        """
        iid = row["irwin_id"]
        review_id = st.session_state.get("cm_review_id")
        if not review_id:
            review_id = uuid.uuid4().hex
            st.session_state["cm_review_id"] = review_id
        if reviews.has_review_id(store, iid, review_id):
            st.session_state.pop("cm_form", None)
            st.session_state.pop("cm_review_id", None)
            st.rerun()

        map_name, map_failed = None, False
        if logged and save_map:
            map_name, map_failed = _save_review_map(review_id, row)

        try:
            reviews.add_review(
                store, iid, row["fire_name"], disposition=disposition,
                reviewer=_editor(), rationale=rationale, quick_reason=quick_reason,
                snapshot_id=sid, evidence=dashboard.evidence_for(row, meta), map_image=map_name,
                review_id=review_id, logged=logged)
            reviews.save(store)
        except (OSError, ValueError) as e:
            st.error(f"The review could not be saved: {e}. Nothing was changed.")
            return

        st.session_state.pop("cm_review_id", None)
        label = "Logged review" if logged else "Review"
        st.toast(f"{label} saved; map freeze failed."
                 if map_failed else f"{row['fire_name']}: {disposition} saved.")
        st.rerun()

    def moratorium_entry(row: pd.Series) -> None:
        """Entry point only: passes the available facts through and creates nothing."""
        att = row.get("attention") or {}
        prox = att.get("proximity") or {}
        st.subheader(f"Moratorium builder — {row['fire_name']}")
        st.caption("Entry point only. Nothing has been created, saved or generated. "
                   "Suggested ZIP areas are Census ZCTA candidates, not confirmed "
                   "bulletin ZIP codes.")
        _kv("Fire name", fmt_text(row["fire_name"]))
        _kv("State", fmt_text(row.get("state")))
        _kv("Current size", fmt_num(dashboard.current_size(row), 0, " acres"))
        _kv("Containment", fmt_num(row.get("pct_contained"), 0, "%"))
        _kv("Nearest population center", fmt_text(prox.get("place")))
        _kv("Suggested ZIP candidates",
            ", ".join(prox.get("verify_review_zctas") or []) or NV)
        if st.button("Close", key=f"cm_mora_close_{row['irwin_id']}"):
            st.session_state.pop("cm_moratorium", None)
            st.rerun()

    return {
        "fmt": {"num": fmt_num, "signed": fmt_signed, "text": fmt_text, "dt": fmt_dt, "when": when},
        "not_verified": NV,
        "state": lambda r: fmt_text(r.get("state")),
        "record": lambda iid: analyst.get(recs, iid),
        "review_store": store,
        "snapshot_id": sid,
        "spatial_all": lambda s: _spatial_all(s, _spatial_version(s)),
        "load_inputs": lambda s, iid: _load_inputs_cached(s, iid, _spatial_version(s)),
        "run_geography": lambda fires: run_geography(sid, fires),
        "goto_detail": _goto_detail,
        "save_review": save_review,
        "moratorium_entry": moratorium_entry,
        "data_controls": lambda: _dashboard_data_controls(metas),
        # Snapshot-comparison context. `dropped` is the frame snapshots.compare()
        # already returns (prior IRWIN IDs absent from the current snapshot);
        # `records` lets the dropped view name an analyst status without app.py
        # having to lay anything out.
        "dropped": dropped,
        "records": recs,
        "compare_label": compare_label,
        "perimeter_note": perimeter_note,
    }


def _review_store() -> dict:
    """The active in-app review store, cached for this session."""
    if "cm_review_store" not in st.session_state:
        st.session_state["cm_review_store"] = reviews.load()
    return st.session_state["cm_review_store"]


def _save_review_map(review_id: str, row: pd.Series) -> tuple[str | None, bool]:
    """Save an image of the map currently shown for this fire.

    Returns (filename, failed). Only the app's own map view is written; no
    credentials, keys or unrelated content. A failure never blocks the review and
    never leaves a blank or invalid record behind.
    """
    prepared = st.session_state.get("cm_last_deck")
    if (not prepared or not prepared.get("ok")
            or prepared.get("irwin_id") != row["irwin_id"]):
        return None, True     # no map of THIS fire was on screen; record nothing
    try:
        reviews.MAP_DIR.mkdir(parents=True, exist_ok=True)
        name = f"{review_id}.html"
        path = reviews.MAP_DIR / name
        dashboard_map.deck(prepared, str(row["fire_name"])).to_html(
            str(path), open_browser=False, notebook_display=False)
        if not path.exists() or path.stat().st_size == 0:
            path.unlink(missing_ok=True)
            return None, True
        return name, False
    except Exception:            # noqa: BLE001 - capture must never lose the review
        return None, True


def page_dashboard(df: pd.DataFrame, dropped: pd.DataFrame, meta: dict,
                   prior_meta: dict | None) -> None:
    recs = _records()
    ctx = _dashboard_context(df, meta, snapshots.list_snapshots(),
                             dropped=dropped, prior_meta=prior_meta)

    def secondary() -> None:
        _dashboard_secondary(df, dropped, meta, prior_meta, recs)

    dashboard.render(df, meta, ctx, secondary)


def _dashboard_secondary(df: pd.DataFrame, dropped: pd.DataFrame, meta: dict,
                         prior_meta: dict | None, recs: dict) -> None:
    """Everything the analyst may want, but should not have to look at first."""
    in_file = set(df["irwin_id"])
    tabs = st.tabs(["Snapshot & geography", "National view",
                    "Changes vs prior snapshot", "New fires", "Dropped from feed"])
    with tabs[0]:
        csv_fn = meta.get("csv_filename", "unknown")
        st.caption(f"WFIGS data current through **{when(meta)}** · {csv_fn} · loaded "
                   f"{fmt_dt(meta.get('retrieved_at'), utc=False)}"
                   + (f" · compared with **{when(prior_meta)}**" if prior_meta
                      else " · *no prior snapshot selected*"))
        # Counts come from in-app reviews only. Archived Excel-derived statuses are
        # not surfaced anywhere on the dashboard (Locked Decision: Day 1 Fresh Baseline).
        store = _review_store()
        dispositions = [reviews.disposition(store, i) for i in df["irwin_id"]]
        c1, c2, c3 = st.columns(3)
        c1.metric("Fires in file", meta.get("row_count", 0))
        c2.metric("Monitor", sum(1 for d in dispositions if d == reviews.MONITOR))
        c3.metric("No Action", sum(1 for d in dispositions if d == reviews.NO_ACTION))
        if not any(dispositions):
            st.caption("No in-app reviews saved yet. Day 1 begins with the first fire marked "
                       "No Action, Monitor, or Moratorium.")

        pending = geo_candidates(df)
        calc_n = int((df["geo_status"] == "calculated").sum())
        st.caption(f"Perimeter geography: {calc_n} computed · {len(pending)} pending")
        if pending and st.button(f"Compute geography ({len(pending)})", type="primary",
                                 key="sec_geo"):
            run_geography(meta["snapshot_id"], pending)
            st.rerun()

    with tabs[1]:
        f1, f2, f3 = st.columns(3)
        lv = f1.multiselect("Urgency", [3, 2, 1], default=[3, 2],
                            format_func=lambda v: f"{LEVEL_ICON[v]} {v} {urgency.LEVEL_LABEL[v]}",
                            key="nat_urg")
        states = sorted(s for s in df["state"].dropna().unique())
        sf = f2.multiselect("State", states, default=[], placeholder="All states", key="nat_state")
        show_all = f3.checkbox("Include level-1 fires", value=False, key="nat_show_all")
        view = df.copy()
        if not show_all:
            view = view[view["urgency_level"].isin(lv)]
        if sf:
            view = view[view["state"].isin(sf)]
        pts, perims = [], []
        sp_all = _spatial_all(meta["snapshot_id"], _spatial_version(meta["snapshot_id"]))
        for r in view.to_dict("records"):
            # In-app disposition only; archived statuses never colour the dashboard.
            r["status"] = reviews.disposition(_review_store(), r["irwin_id"]) or "No Action"
            sp = sp_all.get(r["irwin_id"])
            if sp and sp.get("status") == "calculated":
                inputs = analysis.load_inputs(meta["snapshot_id"], r["irwin_id"])
                geom = (inputs or {}).get("perimeter", {}).get("geometry")
                if geom:
                    perims.append(maps.perimeter_feature(spatial.simplify_for_map(geom, 0.0005), r))
            p = maps.point_record(r)
            if p:
                pts.append(p)
        st.pydeck_chart(maps.national_deck(pts, perims), use_container_width=True, height=420)
        st.caption(f"{len(view)} fires shown. Points are WFIGS origin coordinates sized by acres; "
                   "coloured by urgency (no in-app review changes a colour until saved). "
                   "Solid polygons are "
                   "actual NIFC perimeters where geography has been calculated. "
                   "Basemap © CARTO / OpenStreetMap.")

    with tabs[2]:
        # Real analyst records, not {}. With an empty dict every fire read as
        # "No Action", so material_changes() treated nothing as tracked and its
        # tracked-only reasons - including "dropped from feed" - were unreachable.
        mc = snapshots.material_changes(df, dropped, recs) if prior_meta else None
        if mc is None:
            st.info("Select a prior snapshot in the Data panel to see snapshot-over-snapshot "
                    "changes.")
        elif mc.empty:
            st.success("No material changes between these two snapshots.")
        else:
            fire_picker_table(mc, key="mc_table",
                              display_cols=["Fire", "State", "Acres", "Acres change",
                                            "Containment %", "Containment change", "Why flagged"])

    with tabs[3]:
        new = df[df["is_new"]].sort_values("acres", ascending=False)
        st.caption("New to this snapshot. Being new is not by itself a reason for attention - "
                   "a new fire surfaces only on its own evidence.")
        if new.empty:
            st.info("No new fires in this snapshot.")
        else:
            st.dataframe(pd.DataFrame({
                "Fire": new["fire_name"].values, "State": new["state"].values,
                "County": [fmt_text(v) for v in new["county"]],
                "Acres": [fmt_num(v, 0) for v in new["acres"]],
                "Containment %": [fmt_num(v, 0, "%") for v in new["pct_contained"]],
                "Urgency": new["urgency_level"].values,
                "WFIGS ref. (origin)": new["origin_ref"].values}),
                hide_index=True, use_container_width=True)

    with tabs[4]:
        if dropped.empty:
            st.info("No fires were dropped from the feed.")
        else:
            st.dataframe(pd.DataFrame({
                "Fire": dropped["fire_name"].values, "State": dropped["state"].values,
                "Acres (prior)": [fmt_num(v, 0) for v in dropped["acres"]],
                "Containment % (prior)": [fmt_num(v, 0, "%") for v in dropped["pct_contained"]]}),
                hide_index=True, use_container_width=True)


# --------------------------------------------------------------------------- #
# Page: Fire Table
# --------------------------------------------------------------------------- #
def page_table(df: pd.DataFrame, meta: dict, prior_meta: dict | None) -> None:
    st.title("Fire Table")
    st.caption("Source columns are WFIGS facts (read-only; blank numeric cells = Not verified). Urgency and "
               "recommendation are deterministic rules. Analyst columns are editable and saved with your name. "
               "**Miles (origin)** is the WFIGS point-of-origin description; **Perimeter→place** is calculated "
               "from the actual perimeter where geography has been computed.")
    f1, f2, f3, f4, f5, f6 = st.columns([1.5, 1.5, 1.5, 1.5, 2, 2])
    status_f = f1.multiselect("Status", analyst.STATUS_OPTIONS, default=[], placeholder="All statuses",
                              format_func=lambda s: STATUS_LABEL[s])
    states = sorted(s for s in df["state"].dropna().unique())
    state_f = f2.multiselect("State", states, default=[], placeholder="All states")
    preset = f3.selectbox("Sort", list(SORT_PRESETS), index=0)
    only = f4.selectbox("Show", ["All fires", "Urgency 2-3 only", "Recommended changes only", "Changed / new only", "Tracked only"])
    show_all_fires = f5.checkbox("Show all fires", value=False, help="Default: tracked/monitored only")
    search = f6.text_input("Search fire / county / place / notes", "")

    view = df
    if not show_all_fires:
        view = view[view["status"] != analyst.DEFAULT_STATUS]
    if status_f:
        view = view[view["status"].isin(status_f)]
    if state_f:
        view = view[view["state"].isin(state_f)]
    if only == "Urgency 2-3 only":
        view = view[view["urgency_level"] >= 2]
    elif only == "Recommended changes only":
        view = view[view["urgency_change"]]
    elif only == "Changed / new only":
        view = view[(view["acres_change"].fillna(0) != 0) | (view["pct_contained_change"].fillna(0) != 0)
                    | view["is_new"] | (view["perimeter_updated"] == True)]  # noqa: E712
    elif only == "Tracked only":
        view = view[view["status"] != analyst.DEFAULT_STATUS]
    if search.strip():
        s = search.strip().lower()
        hay = (view["fire_name"].fillna("").str.lower() + " " + view["county"].fillna("").str.lower() + " "
               + view["origin_ref"].fillna("").str.lower() + " " + view["notes"].fillna("").str.lower() + " "
               + view["nearest_place"].fillna("").str.lower())
        view = view[hay.str.contains(s, regex=False)]
    view = sort_frame(view, preset)

    table = pd.DataFrame({
        "irwin_id": view["irwin_id"].values,
        "Status": [STATUS_LABEL[s] for s in view["status"]],
        "Urg": [f"{LEVEL_ICON[int(v)]} {int(v)}" for v in view["urgency_level"]],
        "Recommended": [f"→ {r}" if c else "" for r, c in zip(view["urgency_rec"], view["urgency_change"])],
        "Fire": view["fire_name"].values, "State": view["state"].values,
        "Acres": view["acres"].values,
        "Change": [None if _missing(v) else (0.0 if abs(v) < 0.5 else round(v)) for v in view["acres_change"]],
        "Containment": [fmt_num(v, 0, "%") for v in view["pct_contained"]],
        "Perimeter→place mi": view["perim_place_miles"].values,
        "Nearest place (calc.)": view["nearest_place"].values,
        "Miles (origin)": view["origin_miles"].values,
        "WFIGS ref. place": [(f"{r['origin_direction']} of {r['origin_place']}, {r['origin_place_state']}"
                              if not _missing(r["origin_miles"]) else NV) for _, r in view.iterrows()],
        "Why (rules)": view["urgency_reason"].values,
        "VERIFY ZCTAs": view["zcta_verify"].values,
        "New": view["is_new"].astype(bool).values,
        "Nearest Population Center": view["nearest_population_center"].values,
        "Population": view["population"].values,
        "Structures / Evacuation": view["structures_evac"].values,
        "ZIPs": view["zips"].values, "Moratorium ZIPs": view["moratorium_zips"].values,
        "Description": view["description"].values, "Notes": view["notes"].values,
    })
    editable = ["Status", "Nearest Population Center", "Population", "Structures / Evacuation", "ZIPs",
                "Moratorium ZIPs", "Description", "Notes"]
    disabled = [c for c in table.columns if c not in editable]
    col_cfg = {
        "irwin_id": None,
        "Status": st.column_config.SelectboxColumn(options=list(STATUS_LABEL.values()), required=True, width="medium"),
        "Urg": st.column_config.TextColumn("Urg", width="small", help=urgency.describe()),
        "Recommended": st.column_config.TextColumn(width="small", help="Rule recommendation differing from current status"),
        "Fire": st.column_config.TextColumn(width="medium"), "State": st.column_config.TextColumn(width="small"),
        "Acres": st.column_config.NumberColumn(format="%.0f"), "Change": st.column_config.NumberColumn(format="%+.0f"),
        "Containment": st.column_config.TextColumn(width="small"),
        "Perimeter→place mi": st.column_config.NumberColumn(format="%.1f", help="Calculated edge distance from the NIFC perimeter to the nearest Census place"),
        "Nearest place (calc.)": st.column_config.TextColumn(width="medium"),
        "Miles (origin)": st.column_config.NumberColumn(format="%.0f", help="WFIGS origin-point description, NOT perimeter"),
        "WFIGS ref. place": st.column_config.TextColumn(width="medium"),
        "Why (rules)": st.column_config.TextColumn(width="large"),
        "VERIFY ZCTAs": st.column_config.TextColumn(width="medium", help="ZCTAs the perimeter intersects (Census ZCTA, not USPS)"),
        "New": st.column_config.CheckboxColumn(),
        "Nearest Population Center": st.column_config.TextColumn(width="medium", help="Analyst / outside research"),
        "Population": st.column_config.TextColumn(width="small"),
        "Structures / Evacuation": st.column_config.TextColumn(width="medium"),
        "ZIPs": st.column_config.TextColumn(width="medium"), "Moratorium ZIPs": st.column_config.TextColumn(width="medium"),
        "Description": st.column_config.TextColumn(width="large"), "Notes": st.column_config.TextColumn(width="large"),
    }
    st.caption(f"{len(table)} of {len(df)} fires shown · sort: {preset}.")
    edited = st.data_editor(table, hide_index=True, use_container_width=True, disabled=disabled, column_config=col_cfg,
                            num_rows="fixed",
                            key=f"editor_{meta['snapshot_id']}_{preset}_{len(table)}_{hash(tuple(table['irwin_id']))}",
                            height=min(38 * (len(table) + 1) + 4, 900))
    field_map = {"Status": "status", "Nearest Population Center": "nearest_population_center", "Population": "population",
                 "Structures / Evacuation": "structures_evac", "ZIPs": "zips", "Moratorium ZIPs": "moratorium_zips",
                 "Description": "description", "Notes": "notes"}
    recs = _records()
    changed_any = False
    for (_, orig), (_, new) in zip(table.iterrows(), edited.iterrows()):
        fields = {}
        for col, key in field_map.items():
            o = "" if _missing(orig[col]) else str(orig[col])
            n = "" if _missing(new[col]) else str(new[col])
            if o != n:
                fields[key] = LABEL_STATUS.get(n, n) if key == "status" else n
        if fields:
            changed_any |= analyst.update(recs, orig["irwin_id"], orig["Fire"], by=_editor(), **fields)
    if changed_any:
        _save_records(); st.toast("Analyst edits saved."); st.rerun()

    st.divider()
    names = dict(zip(table["irwin_id"], table["Fire"] + " (" + table["State"].fillna("") + ")"))
    pick = st.selectbox("Open Fire Detail for", ["(select a fire)"] + list(table["irwin_id"]),
                        format_func=lambda i: names.get(i, i))
    if not pick.startswith("(") and st.button("Open detail"):
        _goto_detail(pick)


# --------------------------------------------------------------------------- #
# Page: Fire Detail
# --------------------------------------------------------------------------- #
def page_detail(df: pd.DataFrame, meta: dict, prior_meta: dict | None) -> None:
    st.title("Fire Detail")
    if df.empty:
        st.info("No fires in this snapshot.")
        return
    order = df.sort_values(["urgency_level", "_status_order", "acres"], ascending=[False, True, False])
    ids = list(order["irwin_id"])
    labels = {r["irwin_id"]: f"{LEVEL_ICON[int(r['urgency_level'])]} {STATUS_ICON[r['status']]} {r['fire_name']} ({r['state']})"
              for _, r in order.iterrows()}
    default = st.session_state.get("selected_irwin") or default_detail_fire(df) or ids[0]
    if default not in ids:
        default = ids[0]
    iid = st.selectbox("Fire", ids, index=ids.index(default), format_func=lambda i: labels[i])
    if "selected_irwin" not in st.session_state:
        st.caption("Default selection: highest-urgency fire whose candidate ZIPs are not already under moratorium; "
                   "otherwise the largest fire the underwriter has at Monitor or above.")
    st.session_state["selected_irwin"] = iid
    r = df[df["irwin_id"] == iid].iloc[0]
    recs = _records()
    rec = analyst.get(recs, iid, r["fire_name"])
    sp = analysis.load(meta["snapshot_id"], iid)
    inputs = analysis.load_inputs(meta["snapshot_id"], iid) if sp and sp.get("status") == "calculated" else None
    mora_zips = set()  # moratorium_zip_set(recs)  # Temporarily disabled

    h1, h2 = st.columns([4, 1.3])
    with h1:
        st.markdown(f"<h2 style='margin-bottom:0'>{r['fire_name']} &nbsp;<span style='color:grey;font-weight:400'>"
                    f"{fmt_text(r['state'])}</span> &nbsp; {badge(rec['status'], analyst.is_unconfirmed(rec))} &nbsp; "
                    f"{level_chip(int(r['urgency_level']), r['urgency_label'], bool(r['urgency_provisional']))}</h2>",
                    unsafe_allow_html=True)
        st.markdown(f"*{r['description_shown']}*"
                    + ("" if (rec.get("description") or "").strip()
                       else "  <span style='color:grey'>(auto-summary from verified facts)</span>"),
                    unsafe_allow_html=True)
    with h2:
        if analyst.is_unconfirmed(rec) and st.button("Confirm status", type="primary", use_container_width=True):
            analyst.confirm(recs, iid, r["fire_name"], by=_editor()); _save_records(); st.rerun()
        if st.button("Compute / refresh geography", use_container_width=True):
            run_geography(meta["snapshot_id"], [(iid, r["fire_name"])], force=True); st.rerun()

    with st.container(border=True):
        u1, u2 = st.columns([3, 2])
        with u1:
            st.markdown(f"**Why urgency {int(r['urgency_level'])}:** {r['urgency_reason']}")
            st.markdown(f"**Nearest population:** {r['urgency_nearest'] or NV}")
            st.markdown(f"**Recommendation:** {STATUS_LABEL[r['urgency_rec']]} — {r['urgency_note']}"
                        + ("  ⚠️ *differs from current status*" if r["urgency_change"] else ""))
        with u2:
            human = st.selectbox("Your urgency level (for calibration)", [1, 2, 3],
                                 index=(int(rec["urgency_human"]) - 1) if rec.get("urgency_human") else int(r["urgency_level"]) - 1,
                                 key=f"hl_{iid}")
            b1, b2 = st.columns(2)
            if r["urgency_change"] and b1.button("Accept recommendation", type="primary", use_container_width=True, key=f"acc_{iid}"):
                analyst.update(recs, iid, r["fire_name"], by=_editor(), status=r["urgency_rec"])
                analyst.record_urgency_decision(recs, iid, r["fire_name"], app_level=int(r["urgency_level"]),
                                                app_recommended=r["urgency_rec"], action="accepted", human_level=human,
                                                status_after=r["urgency_rec"], by=_editor())
                _save_records(); st.rerun()
            if b2.button("Record my level", use_container_width=True, key=f"keep_{iid}"):
                analyst.record_urgency_decision(recs, iid, r["fire_name"], app_level=int(r["urgency_level"]),
                                                app_recommended=r["urgency_rec"],
                                                action="kept_current" if r["urgency_change"] else "agreed",
                                                human_level=human, by=_editor())
                _save_records(); st.toast("Recorded."); st.rerun()

    # ---- map
    st.subheader("Hiscox CAT Map")
    if inputs and sp and sp.get("status") == "calculated":
        s = sp["spatial"]
        perim_geom = inputs["perimeter"]["geometry"]
        rings = spatial.rings_geojson(perim_geom)
        zmeas = {z["zcta"]: z for z in s["zctas"]}
        zfeats = [maps.zcta_feature(f, zmeas[(f.get("properties") or {}).get("ZCTA5")],
                                    (f.get("properties") or {}).get("ZCTA5") in mora_zips)
                  for f in inputs["zctas"]["features"] if (f.get("properties") or {}).get("ZCTA5") in zmeas]
        pmeas = {p["geoid"]: p for p in s["places"] if p.get("geoid")}
        places = [pp for pp in (maps.place_point(f.get("properties") or {}, pmeas[(f.get("properties") or {}).get("GEOID")])
                                for f in inputs["places"]["features"] if (f.get("properties") or {}).get("GEOID") in pmeas) if pp]
        origin = (r["origin_lat"], r["origin_lon"]) if not _missing(r.get("origin_lat")) else None
        bbox = census.envelope_around(tuple(s["perimeter"]["bbox"]), 10.5)
        m1, m2, _ = st.columns([1, 1, 4])
        show_z = m1.checkbox("ZCTAs", value=True, key=f"mz_{iid}")
        show_p = m2.checkbox("Places", value=True, key=f"mp_{iid}")
        st.pydeck_chart(maps.fire_deck(spatial.simplify_for_map(perim_geom, 0.0001), rings, zfeats, places, origin,
                                       list(bbox), r["fire_name"], show_z, show_p), use_container_width=True, height=620)
        ps = sp["perimeter_source"]
        st.caption(f"Perimeter: {ps['source_name']}, current {fmt_dt(ps['perimeter_date_current'])}, "
                   f"{ps.get('map_method') or NV}. Rings at 1 / 5 / 10 miles from the perimeter edge (calculated). "
                   "ZCTA boundaries: Census 2020 TIGER (not USPS ZIP boundaries); red = intersects, amber = within 5 mi, "
                   "purple = under an existing moratorium. Places: Census incorporated places and CDPs with 2020 population "
                   "where available. Yellow dot = WFIGS point of origin. Basemap © CARTO / OpenStreetMap.")
    elif sp and sp.get("status") == "not_calculated":
        st.error(f"Geography not calculated: {sp.get('reason')}")
    else:
        st.info("Geography not yet computed for this fire. Press **Compute / refresh geography** (about 3 seconds).")

    # ---- candidate ZIP table
    st.subheader("Candidate ZIPs (ZCTA screening)")
    if sp and sp.get("status") == "calculated":
        s = sp["spatial"]
        analyst_zips = {e["zip"]: e for e in rec["zip_entries"]}
        zt = pd.DataFrame([{
            "ZCTA": z["zcta"],
            "Community (ZIP master)": (f"{z['zip_city']}, {z['zip_state']}" if z.get("zip_city") else NV),
            "Distance (mi)": z["distance_miles"], "Band": z["band"], "Review state": z["review_state"],
            "Population 2020": f"{z['population_2020']:,}" if z.get("population_2020") is not None else NV,
            "Overlap (ac)": f"{z['overlap_acres']:,.0f}" if z.get("overlap_acres") is not None else "",
            "Under moratorium": "Yes" if z["zcta"] in mora_zips else "",
            "Analyst entry": ((analyst_zips[z["zcta"]]["source"] + " " + analyst_zips[z["zcta"]]["note"]).strip()
                              if z["zcta"] in analyst_zips else ""),
        } for z in s["zctas"]])
        st.dataframe(zt, hide_index=True, use_container_width=True,
                     column_config={"Distance (mi)": st.column_config.NumberColumn(format="%.2f"),
                                    "Population 2020": st.column_config.NumberColumn(format="%d"),
                                    "Overlap (ac)": st.column_config.NumberColumn(format="%.0f")})
        extra = [e for e in rec["zip_entries"] if e["zip"] not in {z["zcta"] for z in s["zctas"]}]
        if extra:
            st.caption("Analyst ZIPs with no ZCTA within 10 mi (PO-box / unique ZIPs, typos, or beyond range): "
                       + ", ".join(f"{e['zip']} ({e['source'] or 'no source'})" for e in extra))
        st.caption("VERIFY = perimeter intersects the ZCTA; REVIEW = within 5 mi; NEARBY = within 10 mi. ZCTAs approximate "
                   "USPS ZIP areas; confirm with USPS before use in a bulletin. " + census.population_status())
    else:
        st.caption("Compute geography to populate this table from the actual perimeter.")

    # ---- verified facts
    st.subheader("1. Verified Facts")
    st.caption(f"Source-provided values from {meta['source_name']} ({meta['csv_filename']}), data current through "
               f"{when(meta)}, loaded {fmt_dt(meta['retrieved_at'], utc=False)}. Nothing here is inferred.")
    a, b, c = st.columns(3)
    with a:
        st.markdown("**Incident**")
        _kv("Incident name", fmt_text(r["fire_name"])); _kv("IRWIN ID", fmt_text(r["irwin_id"]))
        _kv("Unique fire ID", fmt_text(r.get("unique_fire_id"))); _kv("Incident type", fmt_text(r.get("incident_type")))
        _kv("Complex", fmt_text(r.get("cpx_name")) if r.get("is_cpx_child") == 1 else "No")
        _kv("Discovered", fmt_dt(r.get("discovery_datetime"))); _kv("Fire cause", fmt_text(r.get("fire_cause")))
    with b:
        st.markdown("**Size and containment**")
        _kv("Acres", fmt_num(r["acres"], 1) + (f"  ({r['acres_source']})" if not _missing(r.get("acres_source")) else ""))
        _kv("Reported incident size (acres)", fmt_num(r.get("incident_size"), 0))
        _kv("Percent contained", fmt_num(r.get("pct_contained"), 0, "%"))
        _kv("Fire behavior (general)", fmt_text(r.get("fire_behavior"))); _kv("Total personnel", fmt_num(r.get("personnel"), 0))
        _kv("Incident complexity", fmt_text(r.get("complexity"))); _kv("Management org", fmt_text(r.get("management_org")))
    with c:
        st.markdown("**Location and currency**")
        _kv("Point-of-origin state / county", f"{fmt_text(r['state'])} / {fmt_text(r.get('county'))}")
        _kv("Point-of-origin city (WFIGS)", fmt_text(r.get("poo_city")))
        _kv("Origin-point description (WFIGS)", fmt_text(r.get("short_description")))
        _kv("Origin lat / lon", f"{fmt_num(r.get('origin_lat'), 5)}, {fmt_num(r.get('origin_lon'), 5)}")
        _kv("Perimeter polygon date", fmt_dt(r.get("perimeter_datetime")))
        _kv("Perimeter last current", fmt_dt(r.get("perimeter_date_current")))
        _kv("Perimeter map method", fmt_text(r.get("map_method")))
        _kv("Incident record modified", fmt_dt(r.get("incident_modified")))
        _kv("Last ICS-209 report", fmt_dt(r.get("ics209_datetime")))
    st.info("WFIGS does not publish structures threatened, evacuations, population or ZIP codes. Population and ZCTAs come "
            "from the Census; structures and evacuations are analyst research (WatchDuty / InciWeb / Cal Fire) entered below.")

    # ---- change
    st.subheader("2. Change Since Prior Snapshot")
    if prior_meta is None:
        st.info("No prior snapshot selected in the sidebar.")
    elif bool(r["is_new"]):
        st.warning(f"New: this IRWIN ID was not in the prior snapshot (data current through {when(prior_meta)}).")
    else:
        prior_status = analyst.status_at(rec, when_dt(prior_meta))
        rows = [
            ["Acres", fmt_num(r.get("acres_prior"), 1), fmt_num(r["acres"], 1),
             fmt_signed(r.get("acres_change"), 1) + (f" ({fmt_signed(r.get('acres_change_pct'), 1, '%')})"
                                                     if not _missing(r.get("acres_change_pct")) else "")],
            ["Percent contained", fmt_num(r.get("pct_contained_prior"), 0, "%"), fmt_num(r.get("pct_contained"), 0, "%"),
             fmt_signed(r.get("pct_contained_change"), 0, " pts")],
            ["Perimeter last current", fmt_dt(r.get("perimeter_date_current_prior")), fmt_dt(r.get("perimeter_date_current")),
             "Updated" if r.get("perimeter_updated") is True else ("Unchanged" if r.get("perimeter_updated") is False else NV)],
            ["Analyst status", prior_status or "Not recorded", rec["status"],
             ("Stable" if prior_status == rec["status"] else ("Changed" if prior_status else ""))],
        ]
        gch = r["geo_change"] or {}
        if gch.get("comparable"):
            npn, npp = gch.get("nearest_place_now"), gch.get("nearest_place_prior")
            pdc = gch.get("place_distance_changes") or []
            rows.append(["Nearest place distance (perimeter)",
                         f"{npp['name']} {npp['distance_miles']:.2f} mi" if npp else NV,
                         f"{npn['name']} {npn['distance_miles']:.2f} mi" if npn else NV,
                         f"{pdc[0]['delta_miles']:+.2f} mi ({pdc[0]['name']})" if pdc else "no change"])
            rows.append(["ZCTAs within 10 mi", "", "",
                         f"entered {len(gch['zctas_entered_10mi'])}, left {len(gch['zctas_left_10mi'])}, "
                         f"band tightened {len(gch['zctas_band_tightened'])}"])
            rows.append(["Perimeter area (calculated)", "", "", fmt_signed(gch.get("acres_calculated_delta"), 1, " ac")])
        elif gch:
            rows.append(["Perimeter geography change", "", "", f"Not comparable: {gch.get('reason')}"])
        st.table(pd.DataFrame(rows, columns=["Measure", "Prior", "Current", "Change (calculated)"]).set_index("Measure"))
    if rec["status_history"]:
        with st.expander(f"Status history ({len(rec['status_history'])})"):
            st.dataframe(pd.DataFrame(rec["status_history"]), hide_index=True, use_container_width=True)
    if rec["urgency_decisions"]:
        with st.expander(f"Urgency decisions ({len(rec['urgency_decisions'])})"):
            st.dataframe(pd.DataFrame(rec["urgency_decisions"]), hide_index=True, use_container_width=True)

    # ---- analyst form
    st.subheader("3. Underwriting Interpretation (analyst)")
    with st.form(key=f"form_{iid}"):
        status_label = st.selectbox("Status", list(STATUS_LABEL.values()), index=analyst.STATUS_OPTIONS.index(rec["status"]))
        cA, cB = st.columns(2)
        vals = {}
        long_fields = {"posture_triggers", "notes", "description"}
        for i, k in enumerate([k for k in analyst.TEXT_FIELDS if k not in long_fields]):
            label, help_ = analyst.ANALYST_FIELDS[k]
            vals[k] = (cA if i % 2 == 0 else cB).text_input(label, value=rec.get(k, ""), help=help_)
        vals["description"] = st.text_area(analyst.ANALYST_FIELDS["description"][0], value=rec.get("description", ""),
                                           help=analyst.ANALYST_FIELDS["description"][1], height=80,
                                           placeholder=r["description_auto"])
        vals["notes"] = st.text_area("Current posture / Notes", value=rec.get("notes", ""), height=100)
        vals["posture_triggers"] = st.text_area(analyst.ANALYST_FIELDS["posture_triggers"][0],
                                                value=rec.get("posture_triggers", ""), height=80)
        st.markdown("**Analyst ZIP entries** (USPS-confirmed ZIPs, moratorium list, sources)")
        zip_df = pd.DataFrame(rec["zip_entries"] or [{"zip": "", "source": "", "note": ""}], columns=analyst.ZIP_ENTRY_COLUMNS)
        zip_edit = st.data_editor(zip_df, num_rows="dynamic", hide_index=True, use_container_width=True, key=f"zips_{iid}",
                                  column_config={"zip": st.column_config.TextColumn("ZIP", width="small"),
                                                 "source": st.column_config.TextColumn("Source", width="medium"),
                                                 "note": st.column_config.TextColumn("Note", width="large")})
        st.markdown("**Review checklist**")
        cl_vals = {}
        cc1, cc2 = st.columns(2)
        for i, (ck, cl_label) in enumerate(analyst.CHECKLIST_ITEMS.items()):
            cl_vals[ck] = (cc1 if i % 2 == 0 else cc2).checkbox(cl_label, value=rec["checklist"].get(ck, False), key=f"cl_{iid}_{ck}")
        if st.form_submit_button("Save analyst record", type="primary"):
            entries = zip_edit[analyst.ZIP_ENTRY_COLUMNS].fillna("").to_dict("records")
            if analyst.update(recs, iid, r["fire_name"], by=_editor(), status=LABEL_STATUS[status_label],
                              checklist=cl_vals, zip_entries=entries, **vals):
                _save_records(); st.success("Saved."); st.rerun()
            else:
                st.info("No changes to save.")
    _kv("Analyst record last updated", f"{fmt_text(rec.get('updated_at'))} by {fmt_text(rec.get('updated_by'))}")

    # ---- sources
    st.subheader("4. Sources / Verification")
    rows = [
        ["Fire facts", meta["source_name"], meta["source_url"], meta["csv_filename"], f"data thru {when(meta)}"],
        ["Change columns", "Calculated in this app (IRWIN ID join)", "",
         prior_meta["csv_filename"] if prior_meta else "No prior", when(prior_meta) if prior_meta else ""],
        ["Urgency / screening", "Calculated in this app (fixed rules, see sidebar)", "", "urgency.py / screening.py", "deterministic"],
        ["Baseline note", "Justin tracking workbook", "", rec.get("baseline_reference") or "Not imported", "verbatim"],
        ["Analyst fields", f"Analyst outside research ({rec.get('updated_by') or 'unknown editor'})", "",
         "data/analyst_status.json", rec.get("updated_at") or NV],
    ]
    if sp and sp.get("status") == "calculated":
        src = sp["sources"]
        rows += [
            ["Perimeter geometry", src["perimeter"]["source_name"], src["perimeter"].get("source_url") or "", "",
             fmt_dt(src["perimeter"].get("perimeter_date_current"))],
            ["ZCTA geometry", src["zcta_geometry"]["source_name"], src["zcta_geometry"]["source_url"], "", src["zcta_geometry"]["retrieved_at"]],
            ["Place geometry", src["place_geometry"]["source_name"], src["place_geometry"]["source_url"], "", src["place_geometry"]["retrieved_at"]],
            ["Population", src["population"]["source_name"], "https://api.census.gov/data/2020/dec/pl", "", src["population"]["status"]],
            ["ZIP community names", "Hiscox ZIP master (10-2024)", "", "data/geography/zip_master.csv", "internal reference"],
            ["Distance method", sp["spatial"]["method"], "", sp["spatial"]["crs_used"], sp["calculated_at"]],
        ]
    else:
        rows.append(["Perimeter-to-ZIP geography", "Not calculated for this fire yet", "", "", "Pending"])
    st.dataframe(pd.DataFrame(rows, columns=["Item", "Source", "URL", "File / field", "As of / note"]),
                 hide_index=True, use_container_width=True)
    done = sum(1 for v in rec["checklist"].values() if v)
    st.markdown(f"**Review checklist:** {done} of {len(analyst.CHECKLIST_ITEMS)} · **Status source:** "
                f"{rec.get('status_source')} · **Moratorium decision:** human analyst only")


# --------------------------------------------------------------------------- #
def main() -> None:
    # Apply any pending navigation before the page radio is created, so the widget
    # picks it up (see _goto_detail).
    pending = st.session_state.pop("pending_page", None)
    if pending in PAGES:
        st.session_state["page"] = pending

    # The dashboard gets navigation only; its data controls live in its own header
    # popover so the analyst is not fronted by an admin panel.
    on_dashboard = st.session_state.get("page", PAGES[0]) == "Dashboard"
    current_id, prior_id, page = sidebar(minimal=on_dashboard)
    if (page == "Dashboard") != on_dashboard:
        st.rerun()          # navigation changed; redraw with the right sidebar
    if current_id is None:
        st.title("Catastrophe Monitor")
        st.markdown("No snapshots loaded yet. Download the current **WFIGS Interagency Fire "
                    "Perimeters** CSV, then load it below.")
        if on_dashboard:
            data_controls(st)   # the minimal sidebar has none, so offer them here
        else:
            st.caption("Use **Upload files** or **Import from project folder** in the sidebar.")
        return
    merged, dropped = _compare(current_id, prior_id)
    _, meta = _load(current_id)
    prior_meta = _load(prior_id)[1] if prior_id else None
    df = build_frame(merged, current_id, prior_id)
    if page == "Dashboard":
        page_dashboard(df, dropped, meta, prior_meta)
    elif page == "Fire Table":
        page_table(df, meta, prior_meta)
    else:
        page_detail(df, meta, prior_meta)


main()