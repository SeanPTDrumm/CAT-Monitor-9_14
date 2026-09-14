"""
Fire perimeter geometry by IRWIN ID.

Order of preference (each result records which source answered):
  1. the GeoJSON saved with the snapshot (frozen, reproducible)
  2. NIFC WFIGS *Current* Interagency Fire Perimeters FeatureServer (live)
  3. NIFC WFIGS Interagency Fire Perimeters (historical, no fall-off) for
     fires that have left the current feed (contained / out)
Nothing is estimated: if no source has a polygon, the result is None with
the reason recorded.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from geo import net

NIFC_BASE = "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services"
CURRENT_LAYER = f"{NIFC_BASE}/WFIGS_Interagency_Perimeters_Current/FeatureServer/0"
HISTORICAL_LAYER = f"{NIFC_BASE}/WFIGS_Interagency_Perimeters/FeatureServer/0"
SOURCE_NAMES = {
    "snapshot_geojson": "WFIGS GeoJSON saved with snapshot",
    "nifc_current": "NIFC WFIGS Current Interagency Fire Perimeters (live)",
    "nifc_historical": "NIFC WFIGS Interagency Fire Perimeters (historical, live)",
}
OUT_FIELDS = ("attr_IrwinID,attr_IncidentName,poly_IncidentName,poly_GISAcres,poly_DateCurrent,"
              "poly_PolygonDateTime,poly_MapMethod,attr_PercentContained,attr_IncidentSize,"
              "attr_ModifiedOnDateTime_dt,attr_FireOutDateTime,attr_ContainmentDateTime")


def _norm(iid: str) -> str:
    iid = iid.strip().upper()
    return iid if iid.startswith("{") else "{" + iid + "}"


def _norm_dt(v: Any) -> str | None:
    """Epoch ms, RFC-2822 ("Wed, 09 Sep 2026 23:56:20 GMT") or ISO -> ISO-8601 UTC string."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        try:
            return datetime.fromtimestamp(int(v) / 1000, tz=timezone.utc).isoformat(timespec="seconds")
        except (ValueError, OSError):
            return None
    s = str(v).strip()
    try:
        return parsedate_to_datetime(s).astimezone(timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        pass
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).isoformat(timespec="seconds")
    except ValueError:
        return s


def _feature_result(feature: dict[str, Any], source: str) -> dict[str, Any]:
    props = feature.get("properties") or feature.get("attributes") or {}
    geom = feature.get("geometry")
    return {
        "irwin_id": (props.get("attr_IrwinID") or props.get("poly_IRWINID") or "").upper(),
        "incident_name": props.get("attr_IncidentName") or props.get("poly_IncidentName"),
        "geometry": geom,  # GeoJSON geometry, EPSG:4326
        "gis_acres": props.get("poly_GISAcres"),
        "perimeter_date_current": _norm_dt(props.get("poly_DateCurrent")),
        "polygon_datetime": _norm_dt(props.get("poly_PolygonDateTime")),
        "map_method": props.get("poly_MapMethod"),
        "pct_contained": props.get("attr_PercentContained"),
        "source": source,
        "source_name": SOURCE_NAMES[source],
        "source_url": {"nifc_current": CURRENT_LAYER, "nifc_historical": HISTORICAL_LAYER}.get(source, ""),
        "retrieved_at": datetime.now().isoformat(timespec="seconds"),
        "crs": "EPSG:4326",
    }


def from_snapshot_geojson(path: Path, irwin_id: str) -> dict[str, Any] | None:
    """Look a fire up in a saved WFIGS GeoJSON file. Streams the file once."""
    if not path.exists():
        return None
    want = _norm(irwin_id)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    for f in data.get("features", []):
        p = f.get("properties") or {}
        iid = (p.get("attr_IrwinID") or p.get("poly_IRWINID") or "").strip().upper()
        if iid == want and f.get("geometry"):
            res = _feature_result(f, "snapshot_geojson")
            res["source_url"] = str(path)
            return res
    return None


def _query_layer(layer_url: str, irwin_id: str, source: str) -> dict[str, Any] | None:
    params = {
        "where": f"attr_IrwinID='{_norm(irwin_id)}'",
        "outFields": OUT_FIELDS, "returnGeometry": "true", "outSR": "4326", "f": "geojson",
    }
    data = net.get_json(f"{layer_url}/query", params)
    feats = data.get("features") or []
    feats = [f for f in feats if f.get("geometry")]
    if not feats:
        return None
    # If several perimeters share the IRWIN (rare), take the most recently current.
    feats.sort(key=lambda f: (f.get("properties") or {}).get("poly_DateCurrent") or 0, reverse=True)
    return _feature_result(feats[0], source)


def fetch_live(irwin_id: str) -> dict[str, Any] | None:
    """Current service first, then historical. Raises NetError only if both fail to respond."""
    errors = []
    for layer, source in ((CURRENT_LAYER, "nifc_current"), (HISTORICAL_LAYER, "nifc_historical")):
        try:
            res = _query_layer(layer, irwin_id, source)
            if res:
                return res
        except net.NetError as e:
            errors.append(str(e))
    if len(errors) == 2:
        raise net.NetError(" / ".join(errors))
    return None


def get_perimeter(irwin_id: str, snapshot_geojson: Path | None = None, *, prefer_live: bool = False) -> dict[str, Any]:
    """Resolve a perimeter. Always returns a dict; `geometry` is None when nothing was found,
    with `reason` explaining why. Never estimates."""
    attempts = []
    order = ["live", "snapshot"] if prefer_live else ["snapshot", "live"]
    for step in order:
        if step == "snapshot" and snapshot_geojson is not None:
            res = from_snapshot_geojson(snapshot_geojson, irwin_id)
            if res:
                return res
            attempts.append("not in snapshot GeoJSON")
        elif step == "live":
            try:
                res = fetch_live(irwin_id)
                if res:
                    return res
                attempts.append("no polygon in NIFC current or historical services")
            except net.NetError as e:
                attempts.append(f"NIFC unreachable: {e}")
    return {"irwin_id": _norm(irwin_id), "geometry": None, "source": None, "source_name": None,
            "reason": "; ".join(attempts) or "no geometry source available",
            "retrieved_at": datetime.now().isoformat(timespec="seconds")}


def live_feed_count() -> int:
    data = net.get_json(f"{CURRENT_LAYER}/query", {"where": "1=1", "returnCountOnly": "true", "f": "json"})
    return int(data.get("count", 0))


def download_current_geojson() -> bytes:
    """Whole current-perimeter layer as GeoJSON bytes (all fields, all features), paged.
    Used to give a snapshot a perimeter of record when the user did not download one."""
    step = 1000
    offset = 0
    features: list[dict[str, Any]] = []
    while True:
        data = net.get_json(f"{CURRENT_LAYER}/query", {
            "where": "1=1", "outFields": "*", "returnGeometry": "true", "outSR": "4326",
            "f": "geojson", "resultOffset": offset, "resultRecordCount": step}, timeout=180)
        feats = data.get("features") or []
        features.extend(feats)
        more = data.get("properties", {}).get("exceededTransferLimit") or data.get("exceededTransferLimit")
        if len(feats) < step or not more:
            break
        offset += step
    out = {"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
           "features": features,
           "properties": {"source": SOURCE_NAMES["nifc_current"], "source_url": CURRENT_LAYER,
                          "retrieved_at": datetime.now().isoformat(timespec="seconds")}}
    return json.dumps(out).encode("utf-8")
