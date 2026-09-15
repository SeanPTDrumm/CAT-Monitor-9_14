"""
Hiscox CAT Map layers (pydeck / deck.gl, Carto basemap, no API key needed).

Two views:
  national_deck : all fires as points (origin lat/lon, WFIGS) sized by acres and
                  coloured by urgency, plus real perimeter polygons where geography
                  has been calculated.
  fire_deck     : one fire - perimeter, 1/5/10-mile rings, ZCTA boundaries with
                  community labels (moratorium ZCTAs shaded), places with population,
                  origin point.
Everything drawn comes from stored source geometry; nothing is sketched.
"""
from __future__ import annotations

import math
from typing import Any

import pydeck as pdk

CARTO_VOYAGER = "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json"
CARTO_POSITRON = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"

STATUS_RGB = {"No Action": [154, 160, 166], "Monitor": [224, 161, 0],
              "Investigate": [217, 48, 37], "Existing Moratorium": [123, 63, 191],
              "Moratorium": [123, 63, 191]}
LEVEL_RGB = {1: [108, 142, 191], 2: [224, 161, 0], 3: [217, 48, 37]}
FIRE_FILL = [200, 30, 30, 110]
FIRE_LINE = [180, 0, 0, 255]
RING_LINE = {1.0: [200, 60, 60, 200], 5.0: [230, 140, 30, 180], 10.0: [60, 100, 200, 160]}
ZCTA_LINE = [40, 80, 160, 200]
ZCTA_FILL = [40, 80, 160, 18]
ZCTA_VERIFY_FILL = [217, 48, 37, 55]
ZCTA_REVIEW_FILL = [224, 161, 0, 45]
MORATORIUM_FILL = [123, 63, 191, 90]
PLACE_RGB = [20, 20, 20]


def fit_view(bbox: list[float] | tuple[float, float, float, float], pad: float = 1.9,
             min_zoom: float = 6.5, max_zoom: float = 12.5) -> pdk.ViewState:
    minx, miny, maxx, maxy = bbox
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    span = max((maxx - minx) * math.cos(math.radians(cy)), maxy - miny, 0.01) * pad
    zoom = max(min(math.log2(360.0 / span) - 1.0, max_zoom), min_zoom)
    return pdk.ViewState(latitude=cy, longitude=cx, zoom=zoom, pitch=0, bearing=0)


def national_view() -> pdk.ViewState:
    return pdk.ViewState(latitude=39.5, longitude=-105.0, zoom=3.6, pitch=0)


# --------------------------------------------------------------------------- #
def national_deck(points: list[dict[str, Any]], perimeters: list[dict[str, Any]],
                  view: pdk.ViewState | None = None) -> pdk.Deck:
    """points: dicts with lon, lat, name, status, level, acres, containment, nearest, tooltip fields.
    perimeters: GeoJSON Features with properties {name, status, level, tooltip...}."""
    layers = []
    if perimeters:
        layers.append(pdk.Layer(
            "GeoJsonLayer", data={"type": "FeatureCollection", "features": perimeters},
            stroked=True, filled=True, get_fill_color="properties.fill", get_line_color="properties.line",
            line_width_min_pixels=1.5, pickable=True, auto_highlight=True))
    if points:
        layers.append(pdk.Layer(
            "ScatterplotLayer", data=points, get_position="[lon, lat]", get_fill_color="color",
            get_line_color=[255, 255, 255, 200], line_width_min_pixels=1, stroked=True,
            get_radius="radius", radius_min_pixels=4, radius_max_pixels=28, pickable=True, auto_highlight=True))
    tooltip = {"html": "<b>{name}</b> ({state})<br/>Status: {status} &nbsp;·&nbsp; Urgency: {level_label}"
                       "<br/>{acres_txt} · {contain_txt}<br/>{nearest}<br/><i>{why}</i>",
               "style": {"backgroundColor": "#1e1e1e", "color": "white", "fontSize": "12px"}}
    return pdk.Deck(layers=layers, initial_view_state=view or national_view(), map_style=CARTO_POSITRON, tooltip=tooltip)


def point_record(row: dict[str, Any]) -> dict[str, Any] | None:
    """Build a national-map point from a frame row (dict). None if no origin coordinates."""
    lat, lon = row.get("origin_lat"), row.get("origin_lon")
    if lat is None or lon is None or lat != lat or lon != lon:
        return None
    level = int(row.get("urgency_level") or 1)
    acres = row.get("acres") or 0
    acres = 0 if acres != acres else acres
    status = row.get("status") or "No Action"
    colour = list(STATUS_RGB.get(status, [154, 160, 166])) if status != "No Action" else list(LEVEL_RGB[level])
    alpha = 230 if status != "No Action" or level >= 2 else 120
    return {
        "lon": float(lon), "lat": float(lat), "name": row.get("fire_name"), "state": row.get("state") or "",
        "status": status, "level": level, "level_label": f"{level} - {row.get('urgency_label', '')}",
        "acres_txt": f"{acres:,.0f} ac" if acres else "acres Not verified",
        "contain_txt": (f"{row['pct_contained']:.0f}% contained" if row.get("pct_contained") == row.get("pct_contained")
                        and row.get("pct_contained") is not None else "containment Not verified"),
        "nearest": row.get("urgency_nearest") or "", "why": row.get("urgency_reason") or "",
        "color": colour + [alpha],
        "radius": 3000 + 60 * math.sqrt(max(acres, 1)),
    }


def perimeter_feature(geom: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    status = row.get("status") or "No Action"
    level = int(row.get("urgency_level") or 1)
    rgb = STATUS_RGB.get(status, STATUS_RGB["No Action"]) if status != "No Action" else LEVEL_RGB[level]
    p = point_record(row) or {}
    return {"type": "Feature", "geometry": geom,
            "properties": {**{k: v for k, v in p.items() if k not in ("lon", "lat", "color", "radius")},
                           "name": row.get("fire_name"), "state": row.get("state") or "", "status": status,
                           "fill": list(rgb) + [120], "line": list(rgb) + [255]}}


# --------------------------------------------------------------------------- #
def fire_deck(perimeter_geom: dict[str, Any], rings: list[dict[str, Any]], zcta_feats: list[dict[str, Any]],
              places: list[dict[str, Any]], origin: tuple[float, float] | None, bbox: list[float],
              fire_name: str, show_zctas: bool = True, show_places: bool = True, satellite_hint: bool = False) -> pdk.Deck:
    """zcta_feats: GeoJSON features with properties {zcta, label, review_state, in_moratorium, distance_miles,
    population, cx, cy}. places: dicts {name, kind, distance_miles, population, lon, lat}."""
    layers = []
    # rings (outermost first so inner ones draw on top)
    for ring in sorted(rings, key=lambda r: -r["properties"]["miles"]):
        m = ring["properties"]["miles"]
        layers.append(pdk.Layer("GeoJsonLayer", data={"type": "FeatureCollection", "features": [ring]},
                                stroked=True, filled=False, get_line_color=RING_LINE.get(m, [90, 90, 90, 160]),
                                line_width_min_pixels=1.5))
    if show_zctas and zcta_feats:
        layers.append(pdk.Layer("GeoJsonLayer", data={"type": "FeatureCollection", "features": zcta_feats},
                                stroked=True, filled=True, get_fill_color="properties.fill",
                                get_line_color=ZCTA_LINE, line_width_min_pixels=1, pickable=True, auto_highlight=True))
        labels = [{"position": [f["properties"]["cx"], f["properties"]["cy"]],
                   "text": f["properties"]["label"], "size": 13} for f in zcta_feats if f["properties"].get("cx")]
        layers.append(pdk.Layer("TextLayer", data=labels, get_position="position", get_text="text",
                                get_size="size", get_color=[30, 50, 120, 255], get_angle=0,
                                get_text_anchor=pdk.types.String("middle"), get_alignment_baseline=pdk.types.String("center"),
                                font_family="Arial", font_weight=600, background=True, get_background_color=[255, 255, 255, 170],
                                background_padding=[3, 2]))
    # perimeter
    layers.append(pdk.Layer("GeoJsonLayer",
                            data={"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": perimeter_geom,
                                                                             "properties": {"name": fire_name, "kind": "Fire perimeter"}}]},
                            stroked=True, filled=True, get_fill_color=FIRE_FILL, get_line_color=FIRE_LINE,
                            line_width_min_pixels=2, pickable=True))
    if show_places and places:
        pts = [p for p in places if p.get("lon") is not None]
        layers.append(pdk.Layer("ScatterplotLayer", data=pts, get_position="[lon, lat]", get_fill_color=PLACE_RGB + [220],
                                get_radius=120, radius_min_pixels=4, radius_max_pixels=8, pickable=True))
        layers.append(pdk.Layer("TextLayer", data=[{**p, "text": p["label"], "position": [p["lon"], p["lat"]]} for p in pts],
                                get_position="position", get_text="text", get_size=13, get_color=[20, 20, 20, 255],
                                get_pixel_offset=[0, -14], get_text_anchor=pdk.types.String("middle"),
                                get_alignment_baseline=pdk.types.String("bottom"), font_family="Arial", font_weight=700,
                                background=True, get_background_color=[255, 255, 255, 200], background_padding=[3, 2]))
    if origin:
        layers.append(pdk.Layer("ScatterplotLayer", data=[{"lon": origin[1], "lat": origin[0], "name": "WFIGS point of origin"}],
                                get_position="[lon, lat]", get_fill_color=[255, 230, 0, 255], get_line_color=[0, 0, 0, 255],
                                stroked=True, line_width_min_pixels=1.5, get_radius=80, radius_min_pixels=5,
                                radius_max_pixels=9, pickable=True))
    tooltip = {"html": "<b>{label}</b>{name}<br/>{kind}<br/>{detail}",
               "style": {"backgroundColor": "#1e1e1e", "color": "white", "fontSize": "12px"}}
    return pdk.Deck(layers=[l for l in layers if l is not None], initial_view_state=fit_view(bbox),
                    map_style=CARTO_VOYAGER, tooltip=tooltip)


def zcta_feature(feat: dict[str, Any], measured: dict[str, Any], in_moratorium: bool) -> dict[str, Any]:
    """Merge a TIGERweb ZCTA feature with its measured result into a map feature."""
    p = feat.get("properties") or {}
    z = measured["zcta"]
    community = measured.get("zip_city")
    label = f"{z} {community}" if community else z
    if in_moratorium:
        fill = MORATORIUM_FILL
    elif measured["review_state"] == "VERIFY":
        fill = ZCTA_VERIFY_FILL
    elif measured["review_state"] == "REVIEW":
        fill = ZCTA_REVIEW_FILL
    else:
        fill = ZCTA_FILL
    pop = measured.get("population_2020")
    detail = (f"{measured['distance_miles']} mi from perimeter · {measured['review_state']}"
              + (f" · pop {pop:,}" if pop is not None else " · pop Not verified")
              + (" · UNDER MORATORIUM" if in_moratorium else ""))
    try:
        cx, cy = float(p.get("CENTLON")), float(p.get("CENTLAT"))
    except (TypeError, ValueError):
        cx = cy = None
    return {"type": "Feature", "geometry": feat.get("geometry"),
            "properties": {"zcta": z, "label": label, "name": "", "kind": "ZCTA (Census; not a USPS boundary)",
                           "detail": detail, "review_state": measured["review_state"], "in_moratorium": in_moratorium,
                           "fill": fill, "cx": cx, "cy": cy}}


def place_point(feat_props: dict[str, Any], measured: dict[str, Any]) -> dict[str, Any] | None:
    try:
        lon, lat = float(feat_props.get("CENTLON")), float(feat_props.get("CENTLAT"))
    except (TypeError, ValueError):
        return None
    pop = measured.get("population_2020")
    return {"lon": lon, "lat": lat, "name": "", "label": measured["name"] + (f" ({pop:,})" if pop is not None else ""),
            "kind": measured["kind"],
            "detail": f"{measured['distance_miles']} mi {measured['direction_from_fire']} of perimeter · "
                      + (f"pop {pop:,} (Census 2020)" if pop is not None else "pop Not verified")}
