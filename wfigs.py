"""
WFIGS loading and normalisation for Catastrophe Monitor.

Everything in this module is either:
  * a SOURCE-PROVIDED fact copied from the WFIGS export, or
  * a DETERMINISTIC parse of a source field (the short-description text).
Nothing here is inferred or estimated. Missing values stay missing (None/NaN)
and are rendered as "Not verified" by the UI layer.
"""
from __future__ import annotations

import json
import re
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

import pandas as pd

SOURCE_NAME = "NIFC / WFIGS Current Interagency Fire Perimeters"
SOURCE_URL = (
    "https://data-nifc.opendata.arcgis.com/datasets/"
    "nifc::wfigs-current-interagency-fire-perimeters"
)
NOT_VERIFIED = "Not verified"

# Values WFIGS uses for "no data".
_MISSING = {"", "null", "Null", "NULL", "None", "nan", "NaN"}

# "14 Miles SE from Mitchell, OR"  /  "30 Miles E from Miles City, MT"
# Anchored on the *last* ", XX" state token so place names containing
# commas or the word "Miles" parse correctly.
_DESC_RE = re.compile(
    r"^\s*(?P<miles>\d+(?:\.\d+)?)\s+Miles?\s+(?P<dir>[NSEW]{1,3})\s+from\s+"
    r"(?P<place>.+?),\s*(?P<state>[A-Z]{2})\s*$"
)

# Source column -> normalised column. Order here is the order kept in output.
SOURCE_COLUMNS: dict[str, str] = {
    "attr_IrwinID": "irwin_id",
    "attr_UniqueFireIdentifier": "unique_fire_id",
    "attr_IncidentName": "fire_name",
    "poly_IncidentName": "perimeter_name",
    "attr_CreatedBySystem": "source_system",   # UI label "Source"
    "attr_POOState": "state_raw",
    "attr_POOCounty": "county",
    "attr_POOFips": "county_fips",
    "attr_POOCity": "poo_city",
    "poly_GISAcres": "acres_gis",
    "attr_IncidentSize": "incident_size",
    "attr_PercentContained": "pct_contained",
    "attr_IncidentShortDescription": "short_description",
    "attr_FireBehaviorGeneral": "fire_behavior",
    "attr_TotalIncidentPersonnel": "personnel",
    "attr_IncidentComplexityLevel": "complexity",
    "attr_IncidentManagementOrg": "management_org",
    "attr_IsCpxChild": "is_cpx_child",
    "attr_CpxName": "cpx_name",
    "attr_IncidentTypeCategory": "incident_type",
    "attr_FireDiscoveryDateTime": "discovery_datetime",
    "attr_ICS209ReportDateTime": "ics209_datetime",
    "attr_ModifiedOnDateTime_dt": "incident_modified",
    "poly_PolygonDateTime": "perimeter_datetime",
    "poly_DateCurrent": "perimeter_date_current",
    "poly_MapMethod": "map_method",
    "attr_InitialLatitude": "origin_lat",
    "attr_InitialLongitude": "origin_lon",
    "attr_FireCause": "fire_cause",
    "OBJECTID": "objectid",
}

NUMERIC_COLUMNS = [
    "acres_gis", "incident_size", "pct_contained", "personnel",
    "origin_lat", "origin_lon", "is_cpx_child",
]
DATETIME_COLUMNS = [
    "discovery_datetime", "ics209_datetime", "incident_modified",
    "perimeter_datetime", "perimeter_date_current",
]
REQUIRED_SOURCE_COLUMNS = ["attr_IrwinID", "attr_IncidentName", "poly_GISAcres"]


def parse_short_description(text: Any) -> dict[str, Any]:
    """Deterministically split the WFIGS origin-point description.

    Returns origin_miles/origin_direction/origin_place/origin_place_state,
    all None when the text is missing or does not match the WFIGS pattern.
    NOTE: this is distance from the *point of origin*, not the perimeter.
    """
    out = {"origin_miles": None, "origin_direction": None,
           "origin_place": None, "origin_place_state": None}
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return out
    s = str(text).strip()
    if s in _MISSING or s.lower().startswith("null "):
        return out
    m = _DESC_RE.match(s)
    if not m:
        return out
    out["origin_miles"] = float(m.group("miles"))
    out["origin_direction"] = m.group("dir")
    out["origin_place"] = m.group("place").strip()
    out["origin_place_state"] = m.group("state")
    return out


def _clean_missing(df: pd.DataFrame) -> pd.DataFrame:
    return df.replace({v: None for v in _MISSING}).infer_objects(copy=False)


def _read_csv(source: str | Path | bytes | BytesIO) -> pd.DataFrame:
    if isinstance(source, (bytes, bytearray)):
        source = BytesIO(source)
    return pd.read_csv(source, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def load_wfigs_csv(source: str | Path | bytes | BytesIO) -> pd.DataFrame:
    """Read a WFIGS CSV export and return a normalised DataFrame.

    Raises ValueError if required identifier columns are absent.
    """
    raw = _read_csv(source)
    missing = [c for c in REQUIRED_SOURCE_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"Not a WFIGS perimeter export; missing columns: {missing}")

    present = {src: dst for src, dst in SOURCE_COLUMNS.items() if src in raw.columns}
    df = raw[list(present)].rename(columns=present)
    df = _clean_missing(df)

    for c in NUMERIC_COLUMNS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in DATETIME_COLUMNS:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], format="%m/%d/%Y %I:%M:%S %p", errors="coerce")

    # Identity clean-up: IRWIN GUIDs are braces + upper-case in WFIGS.
    df["irwin_id"] = df["irwin_id"].astype("string").str.strip().str.upper()
    df = df[df["irwin_id"].notna() & (df["irwin_id"] != "")].copy()
    df = df.drop_duplicates(subset="irwin_id", keep="first")

    # "US-OR" -> "OR"
    if "state_raw" in df.columns:
        df["state"] = df["state_raw"].astype("string").str.replace("US-", "", regex=False)
    else:
        df["state"] = None

    # Acres: prefer the perimeter GIS acres; fall back to reported incident size.
    df["acres"] = df["acres_gis"]
    if "incident_size" in df.columns:
        df["acres"] = df["acres"].fillna(df["incident_size"])
    df["acres_source"] = df.apply(
        lambda r: "poly_GISAcres" if pd.notna(r.get("acres_gis"))
        else ("attr_IncidentSize" if pd.notna(r.get("acres")) else None), axis=1)

    parsed = df["short_description"].apply(parse_short_description) \
        if "short_description" in df.columns else pd.Series([{}] * len(df), index=df.index)
    parsed_df = pd.DataFrame(list(parsed), index=df.index)
    for c in ["origin_miles", "origin_direction", "origin_place", "origin_place_state"]:
        df[c] = parsed_df[c] if c in parsed_df.columns else None
    df["origin_miles"] = pd.to_numeric(df["origin_miles"], errors="coerce")

    return df.reset_index(drop=True)


def load_geojson_summary(source: str | Path | bytes) -> dict[str, Any]:
    """Read a WFIGS GeoJSON and return a light summary (no spatial maths in 0.1)."""
    if isinstance(source, (bytes, bytearray)):
        data = json.loads(source.decode("utf-8"))
    else:
        with open(source, encoding="utf-8") as fh:
            data = json.load(fh)
    feats = data.get("features", [])
    ids = set()
    geom_types: dict[str, int] = {}
    for f in feats:
        p = f.get("properties") or {}
        iid = (p.get("attr_IrwinID") or p.get("poly_IRWINID") or "").strip().upper()
        if iid:
            ids.add(iid)
        g = f.get("geometry") or {}
        gt = g.get("type", "None")
        geom_types[gt] = geom_types.get(gt, 0) + 1
    crs = (data.get("crs") or {}).get("properties", {}).get("name")
    return {"feature_count": len(feats), "irwin_ids": sorted(ids),
            "geometry_types": geom_types, "crs": crs}


def data_current_through(df: pd.DataFrame) -> pd.Timestamp | None:
    """Latest source timestamp in the file (perimeter or incident update)."""
    stamps = []
    for c in ["perimeter_date_current", "incident_modified"]:
        if c in df.columns and df[c].notna().any():
            stamps.append(df[c].max())
    return max(stamps) if stamps else None
