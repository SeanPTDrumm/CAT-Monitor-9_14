"""
Deterministic spatial maths: perimeter vs ZCTA / place polygons.

Method (version 1):
  * All geometry arrives as GeoJSON in EPSG:4326.
  * Everything is projected to the UTM zone of the perimeter centroid
    (metres) so distances are true ground distances, not degrees.
  * Distance is shapely edge-to-edge between polygons; 0 means intersects.
  * Bands: intersects -> VERIFY; <= 5 mi -> REVIEW; <= 10 mi -> NEARBY.
    The 1-mile band is reported as well ("within_1mi").
Nothing here reads a LLM or estimates; every number is reproducible from
the inputs stored alongside the result.
"""
from __future__ import annotations

import math
from typing import Any

from pyproj import CRS, Transformer
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform
from shapely.validation import make_valid

METHOD_VERSION = "spatial-v1 (UTM edge-to-edge, shapely 2 / pyproj 3)"
METRES_PER_MILE = 1609.344
SQM_PER_ACRE = 4046.8564224
BANDS_MILES = (1.0, 5.0, 10.0)


def utm_crs_for(lon: float, lat: float) -> CRS:
    zone = int((lon + 180) // 6) + 1
    zone = min(max(zone, 1), 60)
    epsg = (32600 if lat >= 0 else 32700) + zone
    return CRS.from_epsg(epsg)


def _to_geom(geojson_geom: dict[str, Any]) -> BaseGeometry:
    g = shape(geojson_geom)
    if not g.is_valid:
        g = make_valid(g)
    return g


def band_for(distance_miles: float | None, intersects: bool) -> str | None:
    if intersects:
        return "intersects"
    if distance_miles is None:
        return None
    for b in BANDS_MILES:
        if distance_miles <= b:
            return f"within_{int(b)}mi"
    return None


def review_state(band: str | None) -> str:
    return {"intersects": "VERIFY", "within_1mi": "REVIEW", "within_5mi": "REVIEW",
            "within_10mi": "NEARBY"}.get(band or "", "BEYOND")


def compass(dx: float, dy: float) -> str:
    ang = (math.degrees(math.atan2(dx, dy)) + 360) % 360
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[int((ang + 22.5) // 45) % 8]


def analyze(perimeter_geojson: dict[str, Any], zcta_features: list[dict[str, Any]],
            place_features: list[dict[str, Any]], max_miles: float = 10.0) -> dict[str, Any]:
    """Return candidates within `max_miles` of the perimeter edge, sorted by distance."""
    perim_ll = _to_geom(perimeter_geojson)
    c = perim_ll.centroid
    crs = utm_crs_for(c.x, c.y)
    fwd = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
    perim = transform(fwd, perim_ll)
    pcent = perim.centroid

    def measure(feat: dict[str, Any]) -> dict[str, Any] | None:
        geom_ll = feat.get("geometry")
        if not geom_ll:
            return None
        g = transform(fwd, _to_geom(geom_ll))
        inter = perim.intersects(g)
        d_m = 0.0 if inter else perim.distance(g)
        d_mi = d_m / METRES_PER_MILE
        if d_mi > max_miles:
            return None
        gc = g.centroid
        out = {
            "distance_miles": round(d_mi, 2),
            "intersects": bool(inter),
            "band": band_for(d_mi, inter),
            "direction_from_fire": compass(gc.x - pcent.x, gc.y - pcent.y),
        }
        if inter:
            out["overlap_acres"] = round(perim.intersection(g).area / SQM_PER_ACRE, 1)
        return out

    zctas = []
    for f in zcta_features:
        m = measure(f)
        if m is None:
            continue
        p = f.get("properties") or {}
        zctas.append({"zcta": p.get("ZCTA5") or p.get("GEOID"), **m,
                      "review_state": review_state(m["band"]),
                      "land_area_sqmi": round((p.get("AREALAND") or 0) / 2_589_988.11, 1) if p.get("AREALAND") else None})
    zctas.sort(key=lambda r: (r["distance_miles"], r["zcta"]))

    places = []
    for f in place_features:
        m = measure(f)
        if m is None:
            continue
        p = f.get("properties") or {}
        places.append({"name": p.get("BASENAME") or p.get("NAME"), "full_name": p.get("NAME"),
                       "geoid": p.get("GEOID"), "kind": p.get("place_kind"), "state_fips": p.get("STATE"), **m})
    places.sort(key=lambda r: (r["distance_miles"], r["name"] or ""))

    minx, miny, maxx, maxy = perim_ll.bounds
    return {
        "method": METHOD_VERSION,
        "crs_used": crs.to_string(),
        "perimeter": {
            "area_acres_calculated": round(perim.area / SQM_PER_ACRE, 1),
            "geometry_type": perim_ll.geom_type,
            "parts": len(getattr(perim_ll, "geoms", [perim_ll])),
            "centroid_lon": round(c.x, 5), "centroid_lat": round(c.y, 5),
            "bbox": [round(minx, 5), round(miny, 5), round(maxx, 5), round(maxy, 5)],
        },
        "zctas": zctas,
        "places": places,
        "bands_miles": list(BANDS_MILES),
        "max_miles": max_miles,
    }


def rings_geojson(perimeter_geojson: dict[str, Any], miles: tuple[float, ...] = BANDS_MILES) -> list[dict[str, Any]]:
    """Buffer rings around the perimeter for map display, back in EPSG:4326."""
    perim_ll = _to_geom(perimeter_geojson)
    c = perim_ll.centroid
    crs = utm_crs_for(c.x, c.y)
    fwd = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
    back = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform
    perim = transform(fwd, perim_ll)
    out = []
    for m in miles:
        ring = perim.buffer(m * METRES_PER_MILE).simplify(25)
        out.append({"type": "Feature", "properties": {"miles": m},
                    "geometry": mapping(transform(back, ring))})
    return out


def simplify_for_map(geojson_geom: dict[str, Any], tolerance_deg: float = 0.0002) -> dict[str, Any]:
    g = _to_geom(geojson_geom).simplify(tolerance_deg, preserve_topology=True)
    return mapping(g)
