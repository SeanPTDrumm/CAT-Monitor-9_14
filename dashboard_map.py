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
  * labels only on ZIPs intersecting the perimeter or within 5 miles, with
    collision suppression and a hard cap so the map stays readable
  * surrounding available ZIPs remain hoverable as a quiet exploration layer
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
PERIM_FILL = [255, 111, 55, 54]      # translucent orange wash
PERIM_LINE = [255, 82, 36, 255]         # dominant fire outline
PERIM_LINE_WIDTH = 3.6

ZCTA_LINE = theme.MAP_ZIP_LINE
ZCTA_RELEVANT_LINE = theme.MAP_ZIP_NEAR_LINE
MORATORIUM_LINE = theme.MAP_MORATORIUM_LINE
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


def label_point(perim_geom: Any, feature_geom: dict[str, Any],
                intersects: bool = False) -> tuple[float, float] | None:
    """Return a readable label anchor inside the ZIP area near the fire.

    Intersecting ZIPs use a representative point inside the actual
    fire/ZIP overlap, so the label is visibly associated with the overlap.
    Nearby ZIPs start at the ZIP edge closest to the fire and are nudged
    inward toward a guaranteed interior point. This avoids labels sitting
    exactly on borders or disappearing far away in a huge rural ZCTA.
    """
    try:
        g = shape(feature_geom)
        if g.is_empty:
            return None

        if intersects:
            overlap = g.intersection(perim_geom)
            if not overlap.is_empty:
                p = overlap.representative_point()
                return float(p.x), float(p.y)

        near = nearest_points(perim_geom, g)[1]
        inside = g.representative_point()

        dx = float(inside.x - near.x)
        dy = float(inside.y - near.y)
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            return float(inside.x), float(inside.y)

        # Roughly <= 0.8 mile inward. Enough to get off the border without
        # dragging the label deep into a very large rural ZIP.
        step = min(length * 0.20, 0.012)
        x = float(near.x + dx / length * step)
        y = float(near.y + dy / length * step)

        p = Point(x, y)
        if g.covers(p):
            return x, y

        # Safety fallback: always inside the ZIP.
        return float(inside.x), float(inside.y)

    except (AttributeError, TypeError, ValueError):
        return None


def _label_sep_miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Approximate separation between two lon/lat label anchors in miles."""
    lat = (a[1] + b[1]) / 2.0
    dx = (a[0] - b[0]) * MILES_PER_DEG_LAT * math.cos(math.radians(lat))
    dy = (a[1] - b[1]) * MILES_PER_DEG_LAT
    return math.hypot(dx, dy)


def _declutter_labels(labels: list[dict[str, Any]], max_labels: int = 6) -> list[dict[str, Any]]:
    """Keep the most decision-useful ZIP labels without turning the map into soup.

    Priority:
      1) perimeter-intersecting ZIPs
      2) nearest ZIPs within 5 miles

    Labels that would land almost on top of an already-kept label are suppressed.
    The complete ZIP list still remains available in the right panel and via hover.
    """
    labels = sorted(
        labels,
        key=lambda x: (
            not bool(x.get("intersects")),
            x.get("distance_miles") is None,
            float(x.get("distance_miles") or 0.0),
            str(x.get("text") or ""),
        ),
    )

    kept: list[dict[str, Any]] = []
    for cand in labels:
        pos = cand.get("position")
        if not pos or len(pos) != 2:
            continue

        # Allow intersecting ZIP labels to sit a little closer together because
        # they are the most important; otherwise keep roughly 0.9 mi separation.
        min_sep = 0.55 if cand.get("intersects") else 0.90
        if any(_label_sep_miles(tuple(pos), tuple(k["position"])) < min_sep for k in kept):
            continue

        kept.append(cand)
        if len(kept) >= max_labels:
            break

    return kept


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
        if not z:
            continue

        m = measured.get(z)
        in_mora = z in mora
        is_sel = selected_zip is not None and z == selected_zip

        inside = bool(m.get("intersects")) if m else False
        distance = m.get("distance_miles") if m else None
        try:
            within_five = distance is not None and float(distance) <= 5.0
        except (TypeError, ValueError):
            within_five = False

        # This is the underwriting review layer: intersecting ZIPs + ZIPs within
        # five miles of the perimeter. Selected/moratorium ZIPs can still be shown
        # distinctly, but they do not cause extra labels outside the review zone.
        review_relevant = inside or within_five

        if is_sel:
            line, width = theme.MAP_ZIP_SEL_LINE, theme.MAP_ZIP_SEL_WIDTH
            context_fill, context_kind = theme.MAP_ZIP_SELECTED_FILL, "selected"
        elif in_mora:
            line, width = theme.MAP_MORATORIUM_LINE, theme.MAP_MORATORIUM_WIDTH
            context_fill, context_kind = theme.MAP_MORATORIUM_FILL, "moratorium"
        elif inside:
            line, width = theme.MAP_ZIP_INSIDE_LINE, theme.MAP_ZIP_INSIDE_WIDTH
            context_fill, context_kind = theme.MAP_ZIP_INTERSECT_FILL, "intersects"
        elif within_five:
            line, width = theme.MAP_ZIP_NEAR_LINE, theme.MAP_ZIP_NEAR_WIDTH
            context_fill, context_kind = theme.MAP_ZIP_CONTEXT_FILL, "within-5"
        else:
            line, width = theme.MAP_ZIP_LINE, theme.MAP_ZIP_WIDTH
            context_fill, context_kind = None, "exploration"

        # The exploration layer includes every available input ZCTA so the analyst
        # can zoom outward and hover surrounding ZIPs. Unmeasured ZIPs stay visually
        # quiet and are never mislabeled as being within the review area.
        if m:
            detail = _zcta_detail(m, in_mora)
        else:
            detail = f"ZIP {z} · Outside calculated review area"

        zfeats.append({
            "type": "Feature", "geometry": f.get("geometry"),
            "properties": {
                "zcta": z,
                "label": f"ZIP {z}",
                "name": "", "kind": "",
                "detail": detail,
                "fill": theme.MAP_ZIP_PICK_FILL,
                "line": line,
                "width": width,
                "context_fill": context_fill,
                "context_kind": context_kind,
            },
        })

        # Visible labels are intentionally limited to the underwriting review
        # geography. The right panel remains the complete textual source of truth.
        if m and review_relevant:
            pt = label_point(perim_shape, f.get("geometry"), intersects=inside)
            if pt:
                labels.append({
                    "position": list(pt),
                    "text": z,
                    "distance_miles": distance,
                    "intersects": inside,
                    "detail": (
                        "Perimeter intersects"
                        if inside
                        else f"{float(distance):.1f} mi"
                    ),
                    "label_color": (
                        theme.MAP_ZIP_LABEL_INTERSECT
                        if inside
                        else theme.MAP_ZIP_LABEL_TEXT
                    ),
                    "label_size": (
                        theme.MAP_ZIP_LABEL_INTERSECT_SIZE
                        if inside
                        else theme.MAP_ZIP_LABEL_SIZE
                    ),
                })
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

    # Keep map annotation intentionally sparse. Intersections win, then nearest
    # <=5-mile ZIPs, with collision suppression. The right panel carries the full list.
    labels = _declutter_labels(labels, max_labels=6)

    return {"ok": True, "perimeter": perim_geom, "zctas": zfeats, "labels": labels,
            "places": places, "view": fit_view(list(bbox), context),
            "rings": _ring_features(perim_geom, rings),
            "selected_zip": (
                selected_zip
                if selected_zip is not None
                and any(
                    (f.get("properties") or {}).get("zcta") == selected_zip
                    for f in zfeats
                )
                else None
            ),
            "relevant_zips": sorted(
                z
                for z, rec in measured.items()
                if bool(rec.get("intersects"))
                or (
                    rec.get("distance_miles") is not None
                    and float(rec["distance_miles"]) <= 5.0
                )
            ),
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
    """Build the dashboard map with a strict visual hierarchy.

    Fire > relevant ZIP boundaries > rings > basemap.

    ZIPs are split into three layers:
      * pale, non-interactive context fills for relevant ZIPs only;
      * crisp outline-only boundaries for every ZIP in range;
      * a transparent pick layer whose only visible effect is a pale hover wash.

    Splitting the layers prevents deck.gl selection/highlight behaviour from
    turning whole ZIP polygons into opaque red, grey, blue, or purple blocks.
    """
    from geo import spatial as geo_spatial

    layers: list[pdk.Layer] = []

    # 1) Distance rings: context only, drawn below geography and fire.
    if prepared.get("rings"):
        layers.append(pdk.Layer(
            "GeoJsonLayer", id="cm-rings",
            data={"type": "FeatureCollection", "features": prepared["rings"]},
            stroked=True, filled=False,
            get_line_color="properties.line",
            get_line_width=theme.MAP_RING_WIDTH,
            line_width_units=pdk.types.String("pixels"),
            line_width_min_pixels=1,
            pickable=False,
        ))

    zctas = prepared.get("zctas") or []

    # 2) Very pale fills only for ZIPs that matter to the current review.
    context_features = [
        f for f in zctas
        if (f.get("properties") or {}).get("context_fill") is not None
    ]
    if context_features:
        layers.append(pdk.Layer(
            "GeoJsonLayer", id="cm-zip-context",
            data={"type": "FeatureCollection", "features": context_features},
            stroked=False, filled=True,
            get_fill_color="properties.context_fill",
            opacity=0.13,
            pickable=False,
        ))

    # 3) ZIP boundaries. Outline-only: these are geography, not a heat map.
    if zctas:
        layers.append(pdk.Layer(
            "GeoJsonLayer", id="cm-zip-outlines",
            data={"type": "FeatureCollection", "features": zctas},
            stroked=True, filled=False,
            get_line_color="properties.line",
            get_line_width="properties.width",
            line_width_units=pdk.types.String("pixels"),
            line_width_min_pixels=1,
            pickable=False,
        ))

        # 4) Transparent interaction surface across EVERY available ZCTA polygon.
        # Hover gets a pale cream wash. This is the only ZIP layer that receives
        # mouse events; visible fills/outlines and the fire perimeter are non-pickable,
        # so they cannot block ZIP hover/click selection.
        layers.append(pdk.Layer(
            "GeoJsonLayer", id=ZIP_LAYER_ID,
            data={"type": "FeatureCollection", "features": zctas},
            stroked=False, filled=True,
            get_fill_color="properties.fill",
            opacity=0.01,
            pickable=True,
            auto_highlight=True,
            highlight_color=theme.MAP_ZIP_HOVER_FILL,
        ))

    # 5) Population places / labels.
    if prepared["places"]:
        layers.append(pdk.Layer(
            "ScatterplotLayer", id="cm-places",
            data=prepared["places"],
            get_position="[lon, lat]",
            get_fill_color="color",
            get_line_color=[255, 255, 255, 225],
            stroked=True,
            line_width_min_pixels=1,
            get_radius="radius",
            radius_units=pdk.types.String("pixels"),
            radius_min_pixels=4,
            radius_max_pixels=10,
            pickable=True,
        ))
        layers.append(pdk.Layer(
            "TextLayer", id="cm-place-labels",
            data=[{**p, "text": p["label"], "position": [p["lon"], p["lat"]]}
                  for p in prepared["places"] if p.get("nearest")],
            get_position="position",
            get_text="text",
            get_size=13,
            get_color=LABEL_TEXT_DARK,
            get_pixel_offset=[0, -14],
            get_text_anchor=pdk.types.String("middle"),
            get_alignment_baseline=pdk.types.String("bottom"),
            font_family="Arial, Helvetica, sans-serif",
            font_weight=700,
            outline_width=6,
            get_outline_color=LABEL_OUTLINE,
            font_settings=LABEL_FONT_SETTINGS,
        ))

    # 6) Fire perimeter is deliberately drawn last among polygon layers so no
    # ZIP fill, hover state, or ring can visually cover it.
    layers.append(pdk.Layer(
        "GeoJsonLayer", id="cm-perimeter",
        data={"type": "FeatureCollection", "features": [{
            "type": "Feature",
            "geometry": geo_spatial.simplify_for_map(prepared["perimeter"], simplify),
            "properties": {
                "label": fire_name,
                "name": "",
                "kind": "Current fire perimeter",
                "detail": "",
            },
        }]},
        stroked=True,
        filled=True,
        get_fill_color=PERIM_FILL,
        get_line_color=PERIM_LINE,
        line_width_units=pdk.types.String("pixels"),
        get_line_width=PERIM_LINE_WIDTH,
        line_width_min_pixels=3,
        # Visual layer only. The transparent ZIP interaction layer underneath
        # must receive hover/click events even when the fire overlaps a ZIP.
        pickable=False,
        auto_highlight=False,
    ))

    # ZIP text labels are intentionally omitted from the working map.
    # The review panel remains the authoritative ZIP list, while every available
    # ZIP polygon stays hoverable/selectable through the transparent interaction
    # layer. This keeps the map readable and avoids cartographic clutter.


    tooltip = {
        "html": "<b>{label}</b><br/>{detail}",
        "style": {
            "backgroundColor": theme.SURFACE,
            "color": theme.TEXT,
            "border": f"1px solid {theme.BORDER}",
            "fontSize": "12px",
            "fontFamily": theme.FONT,
        },
    }

    return pdk.Deck(
        layers=layers,
        initial_view_state=prepared["view"],
        map_style=maps.CARTO_POSITRON,
        tooltip=tooltip,
    )


def caption(prepared: dict[str, Any]) -> str:
    """Source attribution, one line, nothing else.

    The old version appended a "Purple shading: existing moratorium (...)"
    legend. The purple is gone, and a moratorium is now stated in the
    selected-fire panel rather than needing a colour legend under the map.
    """
    return theme.ATTRIBUTION
