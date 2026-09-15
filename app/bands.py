"""
Population Bands and provisional Area Buckets.

Both are derived ONLY from spatial data already cached to disk in
data/snapshots/<id>/spatial/*.json (geo/analysis.py). Nothing here makes a
network call, invents a value, or recomputes geography. A fire whose
geography has not been computed yet, or that carries no population/ZCTA
signal at all, is "Not available" / "Needs review" - never guessed.

Every function here is pure: it takes an already-loaded spatial dict (or one
fire's or one ZCTA's slice of it) and returns a label plus the factors that
produced it. None of them read a file or make a request themselves - the
caller is responsible for loading spatial data once (already cached via
app.py's `_spatial_all`/`_bands_all`, both `st.cache_data`-backed) and passing
it in.

Area Bucket is a quick-look sorting/filtering aid, not a screening decision.
It is deliberately separate from Ignore / Monitor / Create Moratorium,
review state, containment band, and population band. A reviewer may confirm
or change it; that confirmation is stored with the review, not here.
"""
from __future__ import annotations

from typing import Any

POPULATION_BANDS = ["Under 1,000", "1,000-4,999", "5,000-24,999", "25,000+", "Not available"]
AREA_BUCKETS = ["Rural", "Residential", "Commercial", "Uninhabited", "Low exposure", "Needs review"]

# Sort order for the "Population Band" and "Area Bucket" sort choices - smallest/
# least-exposed first, "Not available" / "Needs review" always last.
_POP_ORDER = {b: i for i, b in enumerate(POPULATION_BANDS)}
_BUCKET_ORDER = {b: i for i, b in enumerate(AREA_BUCKETS)}

FAR_MILES = 8.0            # beyond this with a small population, exposure is low
LOW_POP_THRESHOLD = 1000
COMMERCIAL_POP_THRESHOLD = 25_000
RESIDENTIAL_POP_THRESHOLD = 1_000


def population_band(pop: float | None) -> str:
    """One of POPULATION_BANDS. `pop` is the nearest place's 2020 Census value."""
    if pop is None:
        return "Not available"
    if pop < 1_000:
        return "Under 1,000"
    if pop < 5_000:
        return "1,000-4,999"
    if pop < 25_000:
        return "5,000-24,999"
    return "25,000+"


def population_band_sort_key(band: str) -> int:
    return _POP_ORDER.get(band, 99)


def area_bucket_sort_key(bucket: str) -> int:
    return _BUCKET_ORDER.get(bucket, 99)


def area_bucket(sp: dict[str, Any] | None) -> tuple[str, list[str]]:
    """Provisional Area Bucket + the quick-look factors that produced it.

    Uses only the measurements already stored in the per-fire spatial result
    (nearest place population/distance, ZCTA review-range count). Rule-based
    and deliberately simple; rename/merge/replace freely (see module docstring).
    """
    if not sp or sp.get("status") != "calculated":
        return "Needs review", ["Geography has not been computed for this fire yet."]

    s = sp.get("spatial") or {}
    places = s.get("places") or []
    zctas = s.get("zctas") or []
    relevant = [z for z in zctas if z.get("review_state") in ("VERIFY", "REVIEW")]
    n_relevant = len(relevant)

    if not places and not zctas:
        return "Uninhabited", ["No populated place or ZIP area found within 10 miles of the current perimeter."]

    nearest = places[0] if places else None
    pop = nearest.get("population_2020") if nearest else None
    dist = nearest.get("distance_miles") if nearest else None

    factors: list[str] = []
    if nearest:
        factors.append(
            f"Nearest place: {nearest.get('name')} ({dist:.1f} mi, pop {pop:,})" if pop is not None
            else f"Nearest place: {nearest.get('name')} ({dist:.1f} mi, population not verified)")
    else:
        factors.append("No populated place identified within 10 miles.")
    factors.append(f"{n_relevant} ZIP area(s) within 5 miles of the perimeter"
                    if n_relevant else "No ZIP areas within 5 miles of the perimeter")

    if pop is None and n_relevant == 0 and not places:
        return "Needs review", factors + ["No population or ZIP signal available to classify this fire."]

    if not places and n_relevant == 0:
        return "Uninhabited", factors

    if dist is not None and dist > FAR_MILES and (pop or 0) < LOW_POP_THRESHOLD and n_relevant == 0:
        return "Low exposure", factors

    if pop is not None and pop >= COMMERCIAL_POP_THRESHOLD:
        return "Commercial", factors
    if pop is not None and pop >= RESIDENTIAL_POP_THRESHOLD:
        return "Residential", factors
    if (pop is not None and pop < RESIDENTIAL_POP_THRESHOLD) or n_relevant > 0:
        return "Rural", factors

    return "Needs review", factors + ["Available population and ZIP data did not support a confident bucket."]


# --------------------------------------------------------------------------- #
# Per-ZCTA variants (map hover) - same taxonomy, evaluated against one ZCTA's
# own cached fields rather than a fire's nearest place.
# --------------------------------------------------------------------------- #
RURAL_LAND_AREA_SQMI = 100.0   # large land area with no population signal reads as rural/sparse
DENSE_PER_SQMI = 1000.0
RESIDENTIAL_PER_SQMI = 100.0


def zcta_area_bucket(z: dict[str, Any]) -> tuple[str, list[str]]:
    """Provisional Area Bucket for a single ZCTA, from its own cached fields
    (population_2020, land_area_sqmi, zip_city, distance_miles, intersects).

    ZCTA-level Census population is frequently unavailable even when the
    fire's nearest-PLACE population resolves fine - that is expected, not a
    bug. When population is missing, land area (a rural/sparse proxy) and a
    known ZIP city name (a residential/rural signal) are used instead of
    defaulting straight to "Needs review".
    """
    pop = z.get("population_2020")
    land = z.get("land_area_sqmi")
    city = z.get("zip_city")
    factors: list[str] = []

    if pop is not None:
        factors.append(f"Population {pop:,}")
    if land is not None:
        factors.append(f"Land area {land:,.1f} sq mi")
    if city:
        factors.append(f"Known ZIP community: {city}")

    if pop is not None and land:
        density = pop / land
        factors.append(f"~{density:,.0f} people/sq mi")
        if density <= 0:
            return "Uninhabited", factors
        if density >= DENSE_PER_SQMI:
            return "Commercial", factors
        if density >= RESIDENTIAL_PER_SQMI:
            return "Residential", factors
        return "Rural", factors

    if pop is not None and pop == 0:
        return "Uninhabited", factors

    if land is not None and land >= RURAL_LAND_AREA_SQMI:
        return "Rural", factors + ["Large land area with no population signal suggests rural/sparse land."]

    if city:
        return "Rural", factors + ["Known ZIP community with no population or land-area signal."]

    return "Needs review", factors + ["No population, land-area, or named-community signal available."]


def zcta_distance_label(z: dict[str, Any]) -> str:
    """Presentation-only relationship to the fire perimeter, for map hover.

    Independent of the VERIFY/REVIEW `review_state` screening band already
    used elsewhere - this is display banding over the same cached
    `distance_miles`/`intersects` fields, not a new calculation.
    """
    if z.get("intersects"):
        return "Area within fire perimeter"
    mi = z.get("distance_miles")
    if mi is None:
        return "Not verified"
    if mi <= 1:
        return "0-1 mi"
    if mi <= 3:
        return "1-3 mi"
    if mi <= 6:
        return "3-6 mi"
    if mi <= 10:
        return "6-10 mi"
    return "10+ mi"
