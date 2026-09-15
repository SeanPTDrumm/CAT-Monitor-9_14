"""
Per-fire, per-snapshot geography run and cache.

Result file: data/snapshots/<snapshot_id>/spatial/<IRWIN>.json
Raw inputs : data/snapshots/<snapshot_id>/spatial/<IRWIN>.inputs.json
             (perimeter + ZCTA + place GeoJSON exactly as fetched, so every
              number can be reproduced)

status in the result is one of:
  "calculated"      - full result present
  "not_calculated"  - no perimeter geometry or a service failure; `reason` says why
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from geo import census, net, perimeters, spatial, zipmaster

BASE_DIR = Path(__file__).resolve().parent.parent
from local_paths import SNAP_DIR
MAX_MILES = 10.0


def _norm(iid: str) -> str:
    iid = iid.strip().upper()
    return iid if iid.startswith("{") else "{" + iid + "}"


def _paths(snapshot_id: str, irwin_id: str) -> tuple[Path, Path]:
    folder = SNAP_DIR / snapshot_id / "spatial"
    key = _norm(irwin_id).strip("{}")
    return folder / f"{key}.json", folder / f"{key}.inputs.json"


def load(snapshot_id: str, irwin_id: str) -> dict[str, Any] | None:
    p, _ = _paths(snapshot_id, irwin_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def load_inputs(snapshot_id: str, irwin_id: str) -> dict[str, Any] | None:
    _, p = _paths(snapshot_id, irwin_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def list_calculated(snapshot_id: str) -> set[str]:
    folder = SNAP_DIR / snapshot_id / "spatial"
    if not folder.exists():
        return set()
    return {"{" + p.stem + "}" for p in folder.glob("*.json") if not p.name.endswith(".inputs.json")}


def run(snapshot_id: str, irwin_id: str, fire_name: str | None = None, *,
        force: bool = False, prefer_live: bool = False) -> dict[str, Any]:
    """Compute (or return cached) geography for one fire in one snapshot."""
    if not force:
        cached = load(snapshot_id, irwin_id)
        if cached:
            return cached

    res_path, in_path = _paths(snapshot_id, irwin_id)
    res_path.parent.mkdir(parents=True, exist_ok=True)
    snap_geo = SNAP_DIR / snapshot_id / "perimeters.geojson"
    now = datetime.now().isoformat(timespec="seconds")
    result: dict[str, Any] = {"irwin_id": _norm(irwin_id), "fire_name": fire_name,
                              "snapshot_id": snapshot_id, "calculated_at": now, "status": "not_calculated"}

    perim = perimeters.get_perimeter(irwin_id, snap_geo if snap_geo.exists() else None, prefer_live=prefer_live)
    result["perimeter_source"] = {k: perim.get(k) for k in
                                  ("source", "source_name", "source_url", "retrieved_at", "perimeter_date_current",
                                   "polygon_datetime", "map_method", "gis_acres", "pct_contained")}
    if not perim.get("geometry"):
        result["reason"] = f"No perimeter polygon: {perim.get('reason')}"
        res_path.write_text(json.dumps(result, indent=1), encoding="utf-8")
        return result

    try:
        from shapely.geometry import shape
        bbox = shape(perim["geometry"]).bounds
        env = census.envelope_around(bbox, MAX_MILES + 0.5)
        z = census.fetch_zctas(env)
        pl = census.fetch_places(env)
    except net.NetError as e:
        result["reason"] = f"Census TIGERweb unavailable: {e}"
        res_path.write_text(json.dumps(result, indent=1), encoding="utf-8")
        return result

    in_path.write_text(json.dumps({"perimeter": perim, "zctas": z, "places": pl}), encoding="utf-8")

    sp = spatial.analyze(perim["geometry"], z["features"], pl["features"], MAX_MILES)

    # population (optional key); never invented
    zpop = census.population_for_zctas(r["zcta"] for r in sp["zctas"])
    ppop = census.population_for_places(r["geoid"] for r in sp["places"] if r.get("geoid"))
    for r in sp["zctas"]:
        r["population_2020"] = zpop.get(r["zcta"])
        zm = zipmaster.lookup(r["zcta"])
        r["zip_city"] = zm["city"] if zm else None
        r["zip_state"] = zm["state"] if zm else None
        r["zip_county"] = zm["county"] if zm else None
    for r in sp["places"]:
        r["population_2020"] = ppop.get(r.get("geoid"))

    result.update({
        "status": "calculated",
        "spatial": sp,
        "sources": {
            "perimeter": result["perimeter_source"],
            "zcta_geometry": {k: z[k] for k in ("source_name", "source_url", "retrieved_at", "crs", "truncated")},
            "place_geometry": {k: pl[k] for k in ("source_name", "source_url", "retrieved_at", "crs")},
            "population": {"source_name": census.SOURCE_POPULATION, "status": census.population_status()},
        },
        "caveats": [
            "ZCTAs are Census statistical areas, not USPS delivery ZIP codes; confirm ZIPs with USPS before use.",
            "Distances are from the perimeter polygon as of its poly_DateCurrent timestamp; fire may have moved since.",
            "Place boundaries are 2020 legal/statistical boundaries; population is the 2020 decennial count.",
        ],
    })
    res_path.write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def compare(current: dict[str, Any] | None, prior: dict[str, Any] | None) -> dict[str, Any]:
    """Change in geography between two results. Empty dict if either side is missing."""
    if not current or not prior or current.get("status") != "calculated" or prior.get("status") != "calculated":
        return {}
    cur_date = current["perimeter_source"].get("perimeter_date_current")
    pri_date = prior["perimeter_source"].get("perimeter_date_current")
    if prior["perimeter_source"].get("source") != "snapshot_geojson" or (cur_date and cur_date == pri_date):
        # The prior snapshot has no perimeter of record (or the same polygon answered both), so
        # any "movement" would be an artefact. Say so rather than compute it.
        return {"comparable": False,
                "reason": "prior snapshot has no saved perimeter; live geometry answered both dates"
                if prior["perimeter_source"].get("source") != "snapshot_geojson" else
                "same perimeter date on both snapshots (no new perimeter published)"}
    cz = {r["zcta"]: r for r in current["spatial"]["zctas"]}
    pz = {r["zcta"]: r for r in prior["spatial"]["zctas"]}
    entered = [cz[z] for z in cz if z not in pz]
    left = [pz[z] for z in pz if z not in cz]
    tightened = [(cz[z], pz[z]) for z in cz if z in pz and (cz[z]["band"] != pz[z]["band"]) and
                 cz[z]["distance_miles"] < pz[z]["distance_miles"]]
    cp = {r["geoid"]: r for r in current["spatial"]["places"] if r.get("geoid")}
    pp = {r["geoid"]: r for r in prior["spatial"]["places"] if r.get("geoid")}
    approach = []
    for g, r in cp.items():
        if g in pp:
            delta = round(r["distance_miles"] - pp[g]["distance_miles"], 2)
            if delta != 0:
                approach.append({"name": r["name"], "kind": r["kind"], "now_miles": r["distance_miles"],
                                 "prior_miles": pp[g]["distance_miles"], "delta_miles": delta})
    approach.sort(key=lambda a: a["delta_miles"])
    return {
        "comparable": True,
        "zctas_entered_10mi": entered, "zctas_left_10mi": left, "zctas_band_tightened": tightened,
        "place_distance_changes": approach,
        "nearest_place_now": current["spatial"]["places"][0] if current["spatial"]["places"] else None,
        "nearest_place_prior": prior["spatial"]["places"][0] if prior["spatial"]["places"] else None,
        "acres_calculated_delta": round(current["spatial"]["perimeter"]["area_acres_calculated"]
                                        - prior["spatial"]["perimeter"]["area_acres_calculated"], 1),
        "perimeter_dates": (prior["perimeter_source"].get("perimeter_date_current"),
                            current["perimeter_source"].get("perimeter_date_current")),
    }


def run_many(snapshot_id: str, fires: list[tuple[str, str | None]], *, force: bool = False,
             progress: Callable[[int, int, str], None] | None = None) -> dict[str, dict[str, Any]]:
    out = {}
    for i, (iid, name) in enumerate(fires, 1):
        if progress:
            progress(i, len(fires), name or iid)
        try:
            out[_norm(iid)] = run(snapshot_id, iid, name, force=force)
        except Exception as e:  # never let one fire break the batch
            out[_norm(iid)] = {"irwin_id": _norm(iid), "fire_name": name, "status": "not_calculated",
                               "reason": f"Unexpected error: {type(e).__name__}: {e}"}
    return out
