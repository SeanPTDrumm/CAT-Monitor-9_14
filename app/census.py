"""
Census geography and population.

  * ZCTA polygons  : Census TIGERweb, layer "2020 Census ZIP Code Tabulation Areas"
  * Place polygons : Census TIGERweb, Incorporated Places + Census Designated Places
  * Population     : Census Data API, 2020 Decennial PL 94-171, P1_001N
                     (needs a free API key in data/census_api_key.txt; without it
                      population is "Not verified")

All geometry is full-resolution TIGER, EPSG:4326, fetched per fire by envelope
and cached with the snapshot. ZCTAs are NOT USPS ZIP codes; see docs.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from geo import net

TIGERWEB = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb"
ZCTA_LAYER = f"{TIGERWEB}/PUMA_TAD_TAZ_UGA_ZCTA/MapServer/1"          # 2020 Census ZCTAs
INC_PLACE_LAYER = f"{TIGERWEB}/Places_CouSub_ConCity_SubMCD/MapServer/4"  # Incorporated Places
CDP_LAYER = f"{TIGERWEB}/Places_CouSub_ConCity_SubMCD/MapServer/5"        # Census Designated Places
CENSUS_API = "https://api.census.gov/data/2020/dec/pl"
SOURCE_GEOMETRY = "U.S. Census Bureau TIGERweb (2020 TIGER/Line geometry, live)"
SOURCE_POPULATION = "U.S. Census Bureau 2020 Decennial Census, PL 94-171 (P1_001N)"

BASE_DIR = Path(__file__).resolve().parent.parent
from local_paths import DATA_ROOT as DATA_DIR, CACHE_DIR as GEO_DIR, CONFIG_DIR
KEY_FILE = CONFIG_DIR / "census_api_key.txt"
POP_CACHE = GEO_DIR / "population_cache.json"

MILES_PER_DEG_LAT = 69.0


def envelope_around(bbox: tuple[float, float, float, float], miles: float) -> tuple[float, float, float, float]:
    """Expand a lon/lat bbox by `miles` on every side (approximate, generous)."""
    minx, miny, maxx, maxy = bbox
    dlat = miles / MILES_PER_DEG_LAT
    lat = max(abs(miny), abs(maxy), 1.0)
    dlon = miles / (MILES_PER_DEG_LAT * max(math.cos(math.radians(lat)), 0.2))
    return (minx - dlon, miny - dlat, maxx + dlon, maxy + dlat)


def _query_envelope(layer: str, bbox: tuple[float, float, float, float], out_fields: str) -> list[dict[str, Any]]:
    minx, miny, maxx, maxy = bbox
    params = {
        "geometry": json.dumps({"xmin": minx, "ymin": miny, "xmax": maxx, "ymax": maxy,
                                "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryEnvelope", "inSR": "4326", "spatialRel": "esriSpatialRelIntersects",
        "outFields": out_fields, "returnGeometry": "true", "outSR": "4326", "f": "geojson", "where": "1=1",
    }
    data = net.get_json(f"{layer}/query", params, timeout=120)
    feats = data.get("features") or []
    if data.get("exceededTransferLimit") or data.get("properties", {}).get("exceededTransferLimit"):
        # Envelope too large for one page; caller should shrink or page. Flag it.
        for f in feats:
            f.setdefault("properties", {})["_truncated"] = True
    return feats


def fetch_zctas(bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    feats = _query_envelope(ZCTA_LAYER, bbox, "ZCTA5,GEOID,NAME,AREALAND,CENTLAT,CENTLON")
    return {"features": feats, "source_name": SOURCE_GEOMETRY, "source_url": ZCTA_LAYER,
            "retrieved_at": datetime.now().isoformat(timespec="seconds"), "crs": "EPSG:4326",
            "truncated": any(f.get("properties", {}).get("_truncated") for f in feats)}


def fetch_places(bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    fields = "NAME,BASENAME,GEOID,STATE,PLACE,LSADC,FUNCSTAT,AREALAND,CENTLAT,CENTLON"
    feats = []
    for layer, kind in ((INC_PLACE_LAYER, "Incorporated Place"), (CDP_LAYER, "Census Designated Place")):
        for f in _query_envelope(layer, bbox, fields):
            f.setdefault("properties", {})["place_kind"] = kind
            feats.append(f)
    return {"features": feats, "source_name": SOURCE_GEOMETRY,
            "source_url": f"{INC_PLACE_LAYER} ; {CDP_LAYER}",
            "retrieved_at": datetime.now().isoformat(timespec="seconds"), "crs": "EPSG:4326"}


# --------------------------------------------------------------------------- #
# Population (Census Data API; optional key)
# --------------------------------------------------------------------------- #
def api_key() -> str | None:
    # Streamlit exposes root-level Secrets as environment variables.
    k = os.environ.get("CENSUS_API_KEY", "").strip()
    if k:
        return k
    if KEY_FILE.exists():
        k = KEY_FILE.read_text(encoding="utf-8").strip()
        return k or None
    return None


def _load_cache() -> dict[str, Any]:
    if POP_CACHE.exists():
        try:
            return json.loads(POP_CACHE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_cache(c: dict[str, Any]) -> None:
    GEO_DIR.mkdir(parents=True, exist_ok=True)
    POP_CACHE.write_text(json.dumps(c, indent=1, sort_keys=True), encoding="utf-8")


def population_for_zctas(zctas: Iterable[str]) -> dict[str, int | None]:
    """{zcta: population or None}. None = not available (no key, or ZCTA absent from API)."""
    norm_zctas: set[str] = set()
    for z in zctas:
        if z is None:
            continue
        s = str(z).strip()
        if s.endswith(".0") and s[:-2].isdigit():
            s = s[:-2]
        if s.isdigit() and len(s) <= 5:
            s = s.zfill(5)
        if len(s) == 5 and s.isdigit():
            norm_zctas.add(s)
    zctas = sorted(norm_zctas)
    cache = _load_cache()
    out: dict[str, int | None] = {}
    missing = []
    for z in zctas:
        key = f"zcta:{z}"
        # A cached null may be left over from an earlier failed/no-key lookup.
        # Treat only a real numeric population as a cache hit; retry nulls now
        # that the Census API is available.
        if key in cache and cache[key] is not None:
            out[z] = cache[key]
        else:
            missing.append(z)
    k = api_key()
    if missing and k:
        # Census API geography predicates do not accept a comma-separated list of
        # ZCTAs in one `for=` value. Query each requested ZCTA individually so one
        # invalid/missing geography cannot blank the whole batch.
        for z in missing:
            try:
                rows = net.get_json(
                    CENSUS_API,
                    {"get": "NAME,P1_001N",
                     "for": f"zip code tabulation area:{z}",
                     "key": k},
                )
                hdr = rows[0]
                zi, pi = hdr.index("zip code tabulation area"), hdr.index("P1_001N")
                for r in rows[1:]:
                    out[r[zi]] = int(r[pi])
                    cache[f"zcta:{r[zi]}"] = int(r[pi])
            except (net.NetError, ValueError, IndexError):
                pass
        _save_cache(cache)
    for z in missing:
        out.setdefault(z, None)
    return out


def population_for_places(geoids: Iterable[str]) -> dict[str, int | None]:
    """{7-digit place GEOID: population or None}. Queries one state at a time.

    TIGERweb can surface GEOID values as numbers/number-like strings. For states
    with a leading-zero FIPS code (for example California = 06), that can turn a
    7-digit place GEOID such as 06xxxxx into a 6-digit value. Normalize to exactly
    7 digits before querying the Census API.
    """
    norm_geoids: set[str] = set()
    for g in geoids:
        if g is None:
            continue
        s = str(g).strip()
        # Handle values that arrived through JSON/pandas as "611390.0".
        if s.endswith(".0") and s[:-2].isdigit():
            s = s[:-2]
        if s.isdigit() and len(s) <= 7:
            s = s.zfill(7)
        if len(s) == 7 and s.isdigit():
            norm_geoids.add(s)
    geoids = sorted(norm_geoids)
    cache = _load_cache()
    out: dict[str, int | None] = {}
    by_state: dict[str, list[str]] = {}
    for g in geoids:
        key = f"place:{g}"
        # Do not let a stale cached null permanently suppress a fresh lookup.
        # This matters after enabling/fixing the Census API on an existing app.
        if key in cache and cache[key] is not None:
            out[g] = cache[key]
        else:
            by_state.setdefault(g[:2], []).append(g)
    k = api_key()
    if by_state and k:
        for st, gs in by_state.items():
            # The Census API accepts one concrete place code (or a wildcard), not
            # a comma-separated list such as "place:12345,67890". The old batching
            # therefore worked only when a state happened to have one requested
            # place, and silently returned no population for fires near several
            # Census places. Query each GEOID independently.
            for geoid in gs:
                try:
                    rows = net.get_json(
                        CENSUS_API,
                        {"get": "NAME,P1_001N",
                         "for": f"place:{geoid[2:]}",
                         "in": f"state:{st}",
                         "key": k},
                    )
                    hdr = rows[0]
                    si, pi_, vi = hdr.index("state"), hdr.index("place"), hdr.index("P1_001N")
                    for r in rows[1:]:
                        g = r[si] + r[pi_]
                        out[g] = int(r[vi])
                        cache[f"place:{g}"] = int(r[vi])
                except (net.NetError, ValueError, IndexError):
                    pass
        _save_cache(cache)
    for gs in by_state.values():
        for g in gs:
            out.setdefault(g, None)
    return out


def population_status() -> str:
    return ("Census API key present" if api_key() else
            "No Census API key (CENSUS_API_KEY or data/config/census_api_key.txt): populations show Not verified. "
            "Free key: https://api.census.gov/data/key_signup.html")
