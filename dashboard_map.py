"""
The dashboard's Hiscox map: the fire is the subject.

Separate from maps.fire_deck() on purpose. Fire Detail's map is a full analytical
view (rings, ZCTA fills, origin point, layer toggles) and must keep working exactly
as it does. This module renders the same source geometry with dashboard cartography:

  * fire perimeter dominant - strong outline, light fill, drawn last
  * ZCTA boundaries OUTLINE-ONLY, no fill, so they cannot overpower the perimeter.
    One deliberate exception: a ZCTA under an existing moratorium gets a subtle
    low-alpha fill and a heavier outline, because "already restricted" is a fact
    the analyst must see without hunting for it.
  * labels only on ZIP areas actually in concern range, placed at each area's
    nearest point to the fire (not its centroid - a rural ZCTA's centroid can sit
    30 miles away and label the wrong ground)
  * proximity rings omitted; the calculated distance is stated in quick facts
  * camera fitted to the perimeter plus only nearby relevant geography, with a
    hard cap on how far it may zoom out

Every number and outline comes from the stored source geometry. Nothing is sketched.
"""
from __future__ import annotations

import math
from typing import Any

import pydeck as pdk
from shapely.geometry import Point, shape
from shapely.ops import nearest_points

import maps
import theme

# Dashboard palette. Every overlay colour comes from theme.py so the map and the
# interface cannot drift apart. Blue and purple are both gone: the ZIP outline
# used to be blue, and "under moratorium" used to be a purple fill. Moratorium is
# a DATA state, not branding, so it is now a heavier neutral outline and is
# stated explicitly in the panel rather than being a colour to decode.
#
# The fire perimeter keeps its own strong orange - it is a data colour, it is the
# subject of the map, and it must stay dominant over every neutral around it.
PERIM_FILL = [255, 92, 40, 60]      # light: the outline carries the shape
PERIM_LINE = [255, 92, 40, 255]     # dominant

ZCTA_LINE = theme.MAP_ZIP_LINE
ZCTA_RELEVANT_LINE = theme.MAP_ZIP_NEAR_LINE
MORATORIUM_LINE = theme.MAP_MORATORIUM_LINE
MORATORIUM_FILL = theme.MAP_MORATORIUM_FILL
PLACE_RGB = theme.MAP_PLACE[:3]
PLACE_NEAREST_RGB = theme.MAP_PLACE_NEAREST[:3]

# Outlined text (dark fill, light halo) instead of a background box: readable
# against the light CARTO_POSITRON basemap and against coloured fills alike,
# and has no "background renders, glyph does not" failure mode since there is
# no separate background quad to desync from the text.
LABEL_TEXT_DARK = theme.MAP_LABEL_TEXT
LABEL_OUTLINE = theme.MAP_LABEL_OUTLINE

# deck.gl will not draw a text outline unless the font atlas is an SDF one. Without
# this it logs "fontSettings.sdf is required to render outline" and drops the halo,
# which is what made ZIP labels unreadable against the basemap.
LABEL_FONT_SETTINGS = {"sdf": True}

# Stable layer id: Streamlit keys chart selections by layer id, and pydeck
# otherwise mints a fresh UUID on every rerun.
ZIP_LAYER_ID = "cm-zips"

# Distance-ring choices. Off by default so rings do not occupy every review.
RING_OFF = "Off"
RING_REVIEW = "1 / 3 / 5 miles"
RING_CHOICES = [RING_OFF, RING_REVIEW, "1 mile", "3 miles", "5 miles", "10 miles", "All"]
_RING_MILES = {RING_REVIEW: (1.0, 3.0, 5.0),
               "1 mile": (1.0,), "3 miles": (3.0,), "5 miles": (5.0,),
               "10 miles": (10.0,), "All": (1.0, 3.0, 5.0, 10.0)}

MILES_PER_DEG_LAT = 69.0

# Camera policy (correction: a large rural ZCTA must never shrink the fire again).
MAX_CONTEXT_MILES = 6.0     # relevant geography beyond this does not pull the camera
MAX_SPAN_MULTIPLE = 3.0     # the view scales with the fire, not with a rural ZCTA
MIN_CONTEXT_MILES = 2.5     # ...but a small fire still shows its immediate surroundings,
                            #    so an adjacent ZIP boundary is not cropped out
MIN_PAD_MILES = 1.25        # always this much clear ground around the perimeter
MIN_ZOOM = 8.0
MAX_ZOOM = 14.0


def _deg_per_mile(lat: float) -> tuple[float, float]:
    """(lon_deg_per_mile, lat_deg_per_mile) at this latitude."""
    lat_deg = 1.0 / MILES_PER_DEG_LAT
    lon_deg = 1.0 / max(MILES_PER_DEG_LAT * math.cos(math.radians(lat)), 1e-6)
    return lon_deg, lat_deg


def label_point(perim_geom: Any, feature_geom: dict[str, Any]) -> tuple[float, float] | None:
    """Point on `feature_geom` closest to the fire - a representative label anchor.

    Deterministic (shapely nearest_points), and always inside/on the ZIP area it
    labels, so a 40-mile-wide rural ZCTA labels next to the fire rather than at a
    centroid tens of miles away.
    """
    try:
        g = shape(feature_geom)
        if g.is_empty:
            return None
        p = nearest_points(perim_geom, g)[1]
        return float(p.x), float(p.y)
    except (AttributeError, TypeError, ValueError):
        return None


def fit_view(perim_bbox: list[float], context_points: list[tuple[float, float]]) -> pdk.ViewState:
    """Camera fitted to the fire, extended only by nearby context, then capped.

    Guarantees: the perimeter always fits with at least MIN_PAD_MILES of margin, and
    the view never spans more than MAX_SPAN_MULTIPLE times the perimeter itself.
    """
    minx, miny, maxx, maxy = perim_bbox
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    lon_pm, lat_pm = _deg_per_mile(cy)

    # Half-span of the fire itself, in degrees.
    fire_hx, fire_hy = max((maxx - minx) / 2, 1e-5), max((maxy - miny) / 2, 1e-5)
    pad_x, pad_y = MIN_PAD_MILES * lon_pm, MIN_PAD_MILES * lat_pm
    need_x, need_y = fire_hx + pad_x, fire_hy + pad_y

    # Extend toward nearby context only.
    max_x = MAX_CONTEXT_MILES * lon_pm
    max_y = MAX_CONTEXT_MILES * lat_pm
    for px, py in context_points:
        dx, dy = abs(px - cx), abs(py - cy)
        if dx <= fire_hx + max_x and dy <= fire_hy + max_y:
            need_x, need_y = max(need_x, dx * 1.08), max(need_y, dy * 1.08)

    # Cap: the view scales with the fire, floored so a small fire still shows its
    # immediate surroundings and ceilinged so a wide rural ZCTA cannot shrink the fire.
    cap_x = min(max(fire_hx * MAX_SPAN_MULTIPLE, MIN_CONTEXT_MILES * lon_pm, pad_x),
                MAX_CONTEXT_MILES * lon_pm + fire_hx)
    cap_y = min(max(fire_hy * MAX_SPAN_MULTIPLE, MIN_CONTEXT_MILES * lat_pm, pad_y),
                MAX_CONTEXT_MILES * lat_pm + fire_hy)
    half_x, half_y = min(need_x, cap_x), min(need_y, cap_y)

    span = max(half_x * 2 * math.cos(math.radians(cy)), half_y * 2, 1e-4)
    zoom = max(min(math.log2(360.0 / span) - 1.0, MAX_ZOOM), MIN_ZOOM)
    return pdk.ViewState(latitude=cy, longitude=cx, zoom=zoom, pitch=0, bearing=0)


# --------------------------------------------------------------------------- #
def prepare(spatial: dict[str, Any] | None, inputs: dict[str, Any] | None,
            moratorium_zips: set[str] | None = None,
            selected_zip: str | None = None,
            rings: str = RING_OFF) -> dict[str, Any]:
    """Turn stored geometry + measurements into dashboard map layers.

    Returns {"ok": True, ...} or {"ok": False, "reason": <explicit reason>}.
    The reason is shown to the user; this never fails silently or leaves a stale map.
    """
    mora = moratorium_zips or set()
    if not spatial or spatial.get("status") != "calculated":
        return {"ok": False, "reason": (spatial or {}).get("reason")
                or "Perimeter geography has not been calculated for this fire yet."}
    if not inputs:
        return {"ok": False, "reason": "Stored geometry for this fire is missing "
                                       "(data/snapshots/<id>/spatial/*.inputs.json)."}
    perim_geom = (inputs.get("perimeter") or {}).get("geometry")
    if not perim_geom:
        return {"ok": False, "reason": "No perimeter polygon is stored for this fire."}

    s = spatial["spatial"]
    try:
        perim_shape = shape(perim_geom)
    except (AttributeError, TypeError, ValueError) as e:
        return {"ok": False, "reason": f"Perimeter geometry could not be read: {e}"}

    measured = {z["zcta"]: z for z in s.get("zctas", [])}
    zfeats: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    context: list[tuple[float, float]] = []

    for f in (inputs.get("zctas") or {}).get("features", []):
        props = f.get("properties") or {}
        z = props.get("ZCTA5")
        m = measured.get(z)
        if not m:
            continue                      # beyond 10 mi: not this fire's geography
        relevant = m.get("review_state") in ("VERIFY", "REVIEW")
        in_mora = z in mora
        inside = bool(m.get("intersects"))
        is_sel = selected_zip is not None and z == selected_zip

        # Four states, most specific first. Every fill is transparent or very
        # low-opacity so the basemap - roads, place names, terrain - stays
        # readable underneath, and none of them can mask the perimeter.
        if is_sel:
            fill, line, width = (theme.MAP_ZIP_SEL_FILL, theme.MAP_ZIP_SEL_LINE,
                                 theme.MAP_ZIP_SEL_WIDTH)
        elif in_mora:
            fill, line, width = (theme.MAP_MORATORIUM_FILL, theme.MAP_MORATORIUM_LINE,
                                 theme.MAP_MORATORIUM_WIDTH)
        elif inside:
            fill, line, width = (theme.MAP_ZIP_INSIDE_FILL, theme.MAP_ZIP_INSIDE_LINE,
                                 theme.MAP_ZIP_INSIDE_WIDTH)
        elif relevant:
            fill, line, width = (theme.MAP_ZIP_NEAR_FILL, theme.MAP_ZIP_NEAR_LINE,
                                 theme.MAP_ZIP_NEAR_WIDTH)
        else:
            fill, line, width = (theme.MAP_ZIP_FILL, theme.MAP_ZIP_LINE,
                                 theme.MAP_ZIP_WIDTH)

        zfeats.append({
            "type": "Feature", "geometry": f.get("geometry"),
            "properties": {
                "zcta": z,
                "label": f"ZIP {z}",
                "name": "", "kind": "",
                "detail": _zcta_detail(m, in_mora),
                "fill": fill, "line": line, "width": width,
            },
        })
        if relevant or in_mora:
            pt = label_point(perim_shape, f.get("geometry"))
            if pt:
                # Single-line ZIP code only - a two-line label (code + city) rendered
                # as a solid background box with no visible text in pydeck's TextLayer.
                # The city name is still available on hover via _zcta_detail().
                labels.append({"position": list(pt), "text": z,
                               "distance_miles": m.get("distance_miles"),
                               "intersects": bool(m.get("intersects")),
                               "detail": (f"{float(m['distance_miles']):.1f} mi"
                                          if m.get("distance_miles") is not None else "Distance not verified")})
                context.append(pt)

    places: list[dict[str, Any]] = []
    pmeas = {p["geoid"]: p for p in s.get("places", []) if p.get("geoid")}
    nearest_geoid = (s.get("places") or [{}])[0].get("geoid") if s.get("places") else None
    for f in (inputs.get("places") or {}).get("features", []):
        props = f.get("properties") or {}
        m = pmeas.get(props.get("GEOID"))
        if not m:
            continue
        try:
            lon, lat = float(props["CENTLON"]), float(props["CENTLAT"])
        except (KeyError, TypeError, ValueError):
            continue
        is_nearest = props.get("GEOID") == nearest_geoid
        pop = m.get("population_2020")
        places.append({
            "lon": lon, "lat": lat, "name": "",
            "label": m["name"] + (f" ({pop:,})" if pop is not None else ""),
            "kind": m.get("kind") or "Census place",
            "detail": (f"{m['distance_miles']} mi {m['direction_from_fire']} of the perimeter · "
                       + (f"pop {pop:,} (Census 2020)" if pop is not None else "pop Not verified")),
            "color": (PLACE_NEAREST_RGB if is_nearest else PLACE_RGB) + [235],
            "radius": 9 if is_nearest else 6,
            "nearest": is_nearest,
        })
        if is_nearest or (m.get("distance_miles") or 99) <= MAX_CONTEXT_MILES:
            context.append((lon, lat))

    bbox = s.get("perimeter", {}).get("bbox")
    if not bbox or len(bbox) != 4:
        minx, miny, maxx, maxy = perim_shape.bounds
        bbox = [minx, miny, maxx, maxy]

    # Map labels are deliberately selective: perimeter-intersecting ZIPs first,
    # then the nearest remaining ZIPs. The right panel carries the fuller list.
    labels.sort(key=lambda x: (not x.get("intersects"),
                               x.get("distance_miles") is None,
                               x.get("distance_miles") if x.get("distance_miles") is not None else 999))
    labels = labels[:8]

    return {"ok": True, "perimeter": perim_geom, "zctas": zfeats, "labels": labels,
            "places": places, "view": fit_view(list(bbox), context),
            "rings": _ring_features(perim_geom, rings),
            "selected_zip": selected_zip if selected_zip in measured else None,
            "relevant_zips": sorted(measured[z]["zcta"] for z in measured
                                    if measured[z].get("review_state") in ("VERIFY", "REVIEW")),
            "moratorium_zips_shown": sorted(z for z in measured if z in mora)}


def _ring_features(perim_geom: dict[str, Any], rings: str) -> list[dict[str, Any]]:
    """Distance rings for display, or [] when the control is Off.

    Reuses geo.spatial.rings_geojson - the same deterministic buffer of the same
    cached perimeter polygon the distances are already measured from. Local
    geometry only: no network call, no geography recomputation, and nothing here
    feeds a measurement or a decision.
    """
    if rings == RING_OFF:
        return []
    miles = _RING_MILES.get(rings)
    if not miles:
        return []
    try:
        from geo import spatial as geo_spatial
        feats = geo_spatial.rings_geojson(perim_geom, miles)
    except Exception:       # a ring is decoration; never break the map for one
        return []
    for f in feats:
        m = f["properties"]["miles"]
        f["properties"].update({
            "label": f"{m:g} mi", "name": "", "kind": "",
            "detail": f"{m:g} mile from the fire perimeter",
            "line": theme.MAP_RING_LINE.get(int(m), theme.MAP_RING_LINE[10]),
            "fill": theme.MAP_RING_FILL,
        })
    return feats


def _zcta_detail(m: dict[str, Any], in_moratorium: bool) -> str:
    """Hover detail for a ZIP/ZCTA: raw known facts only, no exposure buckets."""
    bits: list[str] = []
    city = m.get("zip_city")
    bits.append(f"ZIP {m['zcta']}" + (f" ({city})" if city else ""))

    if m.get("intersects"):
        bits.append("Perimeter intersects ZIP area")
    else:
        mi = m.get("distance_miles")
        if mi is not None:
            bits.append(f"{float(mi):.1f} mi from perimeter")

    pop = m.get("population_2020")
    if pop is not None:
        bits.append(f"Population {int(pop):,} (Census 2020)")

    if in_moratorium:
        bits.append("Under existing moratorium")
    return " · ".join(bits)


def deck(prepared: dict[str, Any], fire_name: str, simplify: float = 0.0001) -> pdk.Deck:
    """Build the dashboard deck. Perimeter is dominant; ZIPs stay readable/clickable."""
    from geo import spatial as geo_spatial

    layers: list[pdk.Layer] = []
    # Rings first, underneath everything: they are context, not the subject.
    if prepared.get("rings"):
        layers.append(pdk.Layer(
            "GeoJsonLayer", id="cm-rings",
            data={"type": "FeatureCollection", "features": prepared["rings"]},
            stroked=True, filled=False, get_fill_color="properties.fill",
            get_line_color="properties.line", get_line_width=theme.MAP_RING_WIDTH,
            line_width_units=pdk.types.String("pixels"), line_width_min_pixels=1,
            pickable=False))

    if prepared["zctas"]:
        layers.append(pdk.Layer(
            "GeoJsonLayer", id=ZIP_LAYER_ID,
            data={"type": "FeatureCollection", "features": prepared["zctas"]},
            stroked=True, filled=True, get_fill_color="properties.fill",
            get_line_color="properties.line", get_line_width="properties.width",
            line_width_units=pdk.types.String("pixels"),
            line_width_min_pixels=1,
            pickable=True, auto_highlight=True,
            highlight_color=theme.MAP_ZIP_HOVER_FILL))

    if prepared["places"]:
        layers.append(pdk.Layer(
            "ScatterplotLayer", id="cm-places", data=prepared["places"], get_position="[lon, lat]",
            get_fill_color="color", get_line_color=[10, 15, 25, 220], stroked=True,
            line_width_min_pixels=1, get_radius="radius", radius_units=pdk.types.String("pixels"),
            radius_min_pixels=4, radius_max_pixels=10, pickable=True))
        layers.append(pdk.Layer(
            "TextLayer", id="cm-place-labels",
            data=[{**p, "text": p["label"], "position": [p["lon"], p["lat"]]}
                  for p in prepared["places"] if p.get("nearest")],
            get_position="position", get_text="text", get_size=13, get_color=LABEL_TEXT_DARK,
            get_pixel_offset=[0, -14], get_text_anchor=pdk.types.String("middle"),
            get_alignment_baseline=pdk.types.String("bottom"), font_family="Arial, Helvetica, sans-serif",
            font_weight=700, outline_width=6, get_outline_color=LABEL_OUTLINE,
            font_settings=LABEL_FONT_SETTINGS))

    # Perimeter last so nothing draws over the fire.
    layers.append(pdk.Layer(
        "GeoJsonLayer", id="cm-perimeter",
        data={"type": "FeatureCollection", "features": [{
            "type": "Feature", "geometry": geo_spatial.simplify_for_map(prepared["perimeter"], simplify),
            "properties": {"label": fire_name, "name": "", "kind": "Current fire perimeter",
                           "detail": ""}}]},
        stroked=True, filled=True, get_fill_color=PERIM_FILL, get_line_color=PERIM_LINE,
        line_width_min_pixels=3, pickable=True))

    if prepared["labels"]:
        layers.append(pdk.Layer(
            "TextLayer", id="cm-zip-labels", data=prepared["labels"],
            get_position="position", get_text="text",
            get_size=13, get_color=LABEL_TEXT_DARK, get_text_anchor=pdk.types.String("middle"),
            get_alignment_baseline=pdk.types.String("center"), font_family="Arial, Helvetica, sans-serif",
            font_weight=700, outline_width=6, get_outline_color=LABEL_OUTLINE,
            font_settings=LABEL_FONT_SETTINGS))

    tooltip = {"html": "<b>{label}</b><br/>{detail}",
               "style": {"backgroundColor": theme.SURFACE, "color": theme.TEXT,
                         "border": f"1px solid {theme.BORDER}", "fontSize": "12px",
                         "fontFamily": theme.FONT}}
    return pdk.Deck(layers=layers, initial_view_state=prepared["view"],
                    map_style=maps.CARTO_POSITRON, tooltip=tooltip)


def caption(prepared: dict[str, Any]) -> str:
    """Source attribution, one line, nothing else.

    The old version appended a "Purple shading: existing moratorium (...)"
    legend. The purple is gone, and a moratorium is now stated in the
    selected-fire panel rather than needing a colour legend under the map.
    """
    return theme.ATTRIBUTION
