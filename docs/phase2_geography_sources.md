# Phase 2a — Wildfire Geography: Proposed Sources, Method, Limitations, Validation

**Status:** proposal for approval. No spatial code has been written. Prepared 2026-09-10.
**Decision needed from Sean:** approve the sources and method below (or amend) before Phase 2b implementation begins.

Everything marked *verified* was checked live from this machine on 2026-09-10.

---

## 1. What Phase 2 must deliver (from CLAUDE.md and the mockup)

Deterministically, for each tracked fire and on demand for any fire:

1. ZIP-like areas (ZCTAs) that **intersect** the current fire perimeter → review state **VERIFY**
2. ZCTAs within **1, 5 and 10 miles** of the perimeter edge → **REVIEW** (≤ 5 mi) / **NEARBY** (≤ 10 mi)
3. **Nearest populated places** with population, distance measured perimeter edge → place boundary
4. **Change** in all of the above between snapshots
5. Every number labelled with source, geometry vintage, CRS and timestamps; failures shown as *Not calculated*, never silently replaced by the origin-point description

No LLM estimates any distance or boundary. Distance is always from the **actual perimeter polygon**, never the point of origin.

---

## 2. Proposed data sources

| Need | Primary source (recommended) | Fallback | Verified today |
|---|---|---|---|
| Fire perimeter polygon | NIFC **WFIGS Current Interagency Fire Perimeters** ArcGIS FeatureServer, layer 0 `…/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_Current/FeatureServer/0`. Query `where=attr_IrwinID='{GUID}'`, `f=geojson`, EPSG:4326. | The GeoJSON already saved with each snapshot (`data/snapshots/<id>/perimeters.geojson`), same fields. For fires that have left the current feed: NIFC **WFIGS Interagency Fire Perimeters** (historical, no fall-off) `…/WFIGS_Interagency_Perimeters/FeatureServer/0`, same IRWIN field. | Yes. Layer supports Query, GeoJSON, `supportsQueryWithDistance`, maxRecordCount 2000, WKID 4326. Live count 201 perimeters. Timber query by IRWIN returned 25,435.5 ac / 27 %. Hawk found in the historical service (15,083 ac, 100 % contained). |
| ZIP-like polygons | Census **TIGERweb** REST, `TIGERweb/PUMA_TAD_TAZ_UGA_ZCTA/MapServer/1` = *2020 Census ZIP Code Tabulation Areas*, full-resolution TIGER geometry, queried per fire by perimeter bounding box + 10-mile buffer. Keyless. | Census cartographic boundary file `cb_2020_us_zcta520_500k.zip` (**64 MB**, generalised 1:500k) cached in `data/geography/` for offline use; results from it are labelled *generalised geometry*. The full TIGER/Line file `tl_2020_us_zcta520.zip` (**504 MB**) is not recommended for this app. | Yes. 17 ZCTAs returned within 10 mi of Hawk's origin in 0.1 s, incl. 89508 and Reno ZCTAs; GeoJSON payload 1.5 MB with geometry. |
| Populated places (boundaries) | TIGERweb `TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/4` (*Incorporated Places*) and `/5` (*Census Designated Places*), 2020 vintage. Keyless. | `cb_2020_us_place_500k.zip` (**23 MB**) cached locally, labelled generalised. | Yes. Within 10 mi of Hawk origin: Reno city; CDPs Mogul, Verdi, Golden Valley, Cold Springs, Lemmon Valley, Sun Valley. |
| Population | Census Data API, 2020 Decennial PL 94-171, variable `P1_001N` by place: `https://api.census.gov/data/2020/dec/pl?get=NAME,P1_001N&for=place:*&in=state:XX&key=…`. Join on 7-digit GEOID (state + place). **Requires a free API key** (Sean or Justin registers once; stored locally, not in code). Cached per state. | Census Population Estimates CSV `sub-est2023.csv` (keyless) — incorporated places only. CDPs (most of the small communities Justin names, e.g. Sun Valley NV) would then show *Not verified*. | API reachable; key-required message confirmed. |
| ZIP ≠ ZCTA verification | USPS lookup / analyst, recorded per ZIP in the Candidate ZIP table ("USPS confirmed" checkbox + source). | — | n/a (human step) |

Reference pages: NIFC dataset listing (data-nifc.opendata.arcgis.com, *WFIGS Current Interagency Fire Perimeters*); Census ZCTA guidance (census.gov/programs-surveys/geography/guidance/geo-areas/zctas.html); Census cartographic boundary files 2020 (GENZ2020); TIGERweb REST (tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb).

---

## 3. Matching method

- **Fire identity:** `attr_IrwinID` (GUID). Verified unique per day and stable across days (190/199 matched 9/9→9/10). Perimeters are harvested into WFIGS only when they carry a valid IRWIN ID.
- **Complexes:** `attr_IsCpxChild = 1` fires are analysed under their **own** IRWIN ID (NWCG rule: never the complex's ID). The complex name is displayed for context only.
- **Perimeter of record per snapshot:** the polygon saved with the snapshot (frozen, reproducible). A "Refresh perimeter now" action can pull the live polygon and is stored as a separate, timestamped result so today's figures are never overwritten silently.
- **Fires no longer in the current feed:** pull from the historical service by IRWIN ID and label the result *from historical perimeter service; fire declared contained/out*.

---

## 4. Distance and buffer method (deterministic)

1. Load perimeter (Polygon/MultiPolygon, EPSG:4326). Build a 10-mile envelope around it.
2. Query TIGERweb ZCTA layer and both Places layers with that envelope (`esriGeometryEnvelope`, `returnGeometry=true`, `f=geojson`). Cache raw responses in the snapshot folder with retrieval time.
3. Project perimeter and candidates to the **UTM zone of the perimeter centroid** (pyproj, metres). Distances in a projected CRS avoid the degree-distortion of raw lat/lon.
4. For each ZCTA / place polygon: `intersects` test, then `shapely.distance` (edge-to-edge, metres → miles). Distance 0 = intersects.
5. Bands: intersects → VERIFY; 0 < d ≤ 1 mi and ≤ 5 mi → REVIEW; ≤ 10 mi → NEARBY. Band thresholds displayed and fixed in code (1 / 5 / 10 mi per CLAUDE.md).
6. Nearest places: three closest place polygons by edge distance, with 2020 population from the API cache; also the incorporated place nearest.
7. Persist `spatial.json` per fire per snapshot: method version, CRS used, perimeter date (`poly_DateCurrent`), TIGERweb layer ids and retrieval time, every candidate with distance, band, population and source. UI reads only this file → every figure traceable.
8. **Change since prior snapshot:** ZCTAs entering/leaving each band, nearest-place distance delta (perimeter movement toward population), and perimeter area delta.

Dependencies to install (approved in principle; sizes are wheel downloads): `shapely 2.1.2`, `pyproj 3.8.0`, `geopandas 1.1.4`, `pyogrio 0.13.0` (PyPI reachable from this machine). `requests` already present.

---

## 5. Limitations (to be shown in the app, not buried)

1. **ZCTA ≠ USPS ZIP.** ZCTAs are Census block aggregations approximating ZIP delivery areas. Roughly 8,000 USPS ZIPs (PO-box, unique/organisational, military) have no ZCTA; boundaries differ (about 11 % of ZCTAs share under half their area with the ZIP). ZCTAs are 2020 vintage and fixed until the next census; USPS changes ZIPs at any time. Therefore: the app produces **candidate ZIPs for USPS/manual confirmation**, and the Candidate ZIP table carries an analyst "USPS confirmed" state.
2. **Perimeter currency.** Perimeters lag the fire (IR flights, mapping method). Distance is as of `poly_DateCurrent`, shown beside every figure. Fires < 100 ac may drop from the current feed after 3–8 days without update; contained fires drop too (Hawk).
3. **Multipolygon and complex fires.** Distances use the whole multipolygon. Only the most recently edited part of a multi-part perimeter is captured by WFIGS if the source was drawn as separate polygons.
4. **TIGERweb dependency.** Live Census service; if unavailable the app uses the cached 64 MB generalised file and labels results *generalised geometry (≈ up to a few hundred metres error)*, or shows *Not calculated*.
5. **census.gov TLS quirk on this machine.** Python 3.13's default strict certificate check rejects census.gov's chain (`Basic Constraints of CA cert not marked critical`). NIFC and PyPI are unaffected. The fix is to clear `VERIFY_X509_STRICT` on the SSL context for census.gov requests only; certificates are still verified against the CA store. This will be isolated in one function and documented.
6. **Population.** 2020 decennial counts carry differential-privacy noise (small for towns, irrelevant at the scale used). CDP boundaries are statistical, not legal. Requires an API key; without it CDP populations show *Not verified*.
7. **Not a moratorium decision.** Bands and candidate ZIPs are screening geometry. The analyst decides.

---

## 6. Validation plan — Hawk fire (NV, N of Reno), agreed 2026-09-10

**Inputs needed from Justin:** his moratorium ZIP list for Hawk, the distances/“miles from perimeter” he measured, the tools used (WFIGS map + USPS ZIP lookup + Google Maps), and the date of his analysis (perimeter date matters).

**Steps**
1. Retrieve Hawk's perimeter by IRWIN `{D11B03E5-0A65-4618-B493-56BABF82A834}` from the historical service (current feed no longer carries it). Record `poly_DateCurrent` (2026-08-31 12:32 as of the 9/9 snapshot).
2. Run the §4 method. Expected candidates within 10 mi include ZCTAs 89508, 89506/89523/89503 area, Cold Springs, Lemmon Valley, Golden Valley, Sun Valley CDPs and Reno city (from today's probe).
3. Produce `docs/validation_hawk.md`: side-by-side table (Justin ZIP, in app? band, app distance, Justin distance, difference, explanation).
4. **Acceptance:** every ZIP on Justin's moratorium list appears in VERIFY or REVIEW; no app VERIFY ZIP is absent from his list without an explained reason (ZIP-without-ZCTA, PO-box ZIP, perimeter date difference, generalisation). Distance agreement within ±0.5 mi for band-edge cases; larger gaps must be explained by perimeter date or measurement method before proceeding.
5. **Gate:** no nationwide run until Sean signs off on the Hawk comparison. If discrepancies cannot be explained, stop and diagnose (compare against the full 504 MB TIGER ZCTA file as a second opinion).

---

## 7. What approval unlocks (Phase 2b, one to two sessions)

- `pip install shapely pyproj geopandas pyogrio`
- New modules `geo/perimeters.py`, `geo/zcta.py`, `geo/places.py`, `geo/spatial.py`; `data/geography/` cache; `spatial.json` per fire per snapshot
- Fire Detail §3 becomes the mockup's Candidate ZIP table (ZCTA, distance, band, review state, USPS-confirmed) plus nearest places with Census population; Fire Table gains a **Perimeter distance** column beside the existing origin-point Miles
- Dashboard material changes gain "ZCTA entered 5-mile band" and "perimeter moved toward <place>"
- Census API key: Sean/Justin registers at api.census.gov/data/key_signup.html; key kept in `data/census_api_key.txt` (git-ignored, not in code)
