# Catastrophe Monitor — Two-Mission Roadmap

Prepared 2026-09-10 after reviewing: v0.2 app, Sean's feedback and screenshots, the seven Hiscox USA
moratorium bulletins (Gold Mountain, Bench/Beachcomb, Bug, Hawk, Lala, Edouard, Lowell), Justin's June and
September workbooks (incl. the Cottonwood investigation sheet with WatchDuty map, zip-codes.com ZIP map and
damage-assessment panel), and the Teams monitoring threads (Cram fire, Fausto, Karina/Lowell).

**Mission 1 — Soon.** A demonstrable Hiscox CAT dashboard: map-first, urgency-led, with moratorium status,
real population, ZIP features and a bulletin wizard. Accuracy caveats are stated on screen, not hidden.
**Mission 2 — Scale.** Feed it authoritative data automatically so it holds up nationally and daily, then
extend to tropical weather and internal exposure.

---

## What the review changed in our thinking

| Observation | Consequence |
|---|---|
| Screening-flag list (71 fires) shows facts with no verdict | Replace with a 1–3 **urgency level** and a **recommended status change**, each flagged for human review; flags become the evidence line. |
| "Not verified" on new fires' change columns | Bug: shows "n/a (new)" now. Containment/description gaps are real WFIGS gaps (no ICS-209 for small fires) and are now explained in the caption. |
| Justin's actual visuals: WatchDuty perimeter on satellite with towns boxed; zip-codes.com ZIP boundaries; damage-assessment tiles | The detail view must be a **map**: perimeter, 1/5/10-mile rings, ZCTA boundaries with labels, moratorium ZIPs shaded, nearest towns with population. Damage counts stay human-entered (no public API) with WatchDuty/InciWeb links pre-filled. |
| Bulletins follow one fixed template; wildfire uses ZIP lists, tropical uses counties/parishes/states; one bulletin has a copy error ("due to the Iron Fire" in the Bench/Beachcomb bulletin) | A **bulletin wizard** from a template removes copy errors and pre-fills facts and ZIPs. Output DOCX (python-docx already installed). Human proofreads and sends. |
| Bulletins are the only structured record of moratoriums | Build a **moratorium register** (fire/storm, type, effective, expiry, ZIPs or counties, lines, contacts, status). Seed it from the seven PDFs. Expiry drives "expiring soon" and "expired but fire still active" alerts. |
| Population: Justin uses zip-codes.com ZIP population and town population | Census 2020 decennial gives both **ZCTA population** and **place population** via the API (free key). Justin's 9-9 sheet already has an empty Population column waiting for this. |
| Team use: Kate, Justin, David, Sean all read and edit | Move analyst store to **SQLite** with `updated_by`, keep JSON export; simple "Your name" field in the sidebar; per-record history already exists. |
| WFIGS times are UTC | Label as UTC and show local time alongside. |
| Noon CSV added | Intraday snapshots already work (noon file: 201 fires, 4 new, 2 dropped vs 09:00). With live perimeter fetch, no GeoJSON download is needed per snapshot. |
| pydeck, python-docx, sqlite3 already installed | Map, DOCX wizard and multi-user store need **no new packages**. Phase 2 geometry still needs shapely/pyproj/geopandas/pyogrio. |

---

## Mission 1 — Demo-ready dashboard (target: 3 working sessions)

### Session A — Map + urgency (the "wow" screen)
1. **Geometry layer (Phase 2b, approved memo):** install shapely/pyproj/geopandas/pyogrio; `geo/perimeters.py` (NIFC FeatureServer by IRWIN, historical service fallback, snapshot GeoJSON fallback), `geo/zcta.py` and `geo/places.py` (Census TIGERweb live, cached per snapshot, TLS workaround isolated), `geo/spatial.py` (UTM projection, edge distances, 1/5/10-mile bands, nearest places). Results saved as `spatial.json` per fire per snapshot with method, CRS and timestamps.
2. **Hiscox CAT Map (pydeck):**
   - *Topline map* on the Dashboard: all tracked fires as perimeter polygons coloured by status, untracked urgency-3 fires as outlined polygons, filter chips (status, state, urgency), hover card (name, acres, containment, urgency, nearest town + population). Click → detail.
   - *Detail map:* perimeter (satellite or terrain basemap), 1/5/10-mile rings, ZCTA boundaries with ZIP labels, ZCTAs in an active moratorium shaded purple, nearest places labelled with 2020 population, origin point marker, north-up scale. Legend states geometry vintage and perimeter date.
   - *Default selection rule:* highest urgency fire whose candidate ZIPs are not already all under moratorium; if none, the largest fire the underwriter last set to Monitor or higher. Rule shown under the map.
3. **Urgency level 1–3 (deterministic baseline, human-reviewed):**
   - Inputs: containment, acres and growth since prior, perimeter distance to nearest place and its population, ZCTA population within 5 mi, perimeter movement toward population vs prior snapshot, existing moratorium coverage, whether the fire is new.
   - Output: level 1 (watch), 2 (elevated), 3 (act), a one-line reason, and a **recommended status** (No Action / Monitor / Investigate / Existing Moratorium). Where the recommendation differs from the analyst's current status the fire is placed in a **Review queue** with "Accept / Keep current / Set other" buttons. Nothing changes without a click.
   - Calibration: every human decision stores the analyst's own level ("what would you have scored"), so the next iteration can be tuned from real overrides. Thresholds live in one file and are shown in the UI.
4. **Dashboard restructure:** header + five cards (fires reviewed, Monitor, Investigate, Existing Moratorium, review queue size) → CAT Map → Review queue → Tracked fires (filterable, with 1–3 sentence description) → Moratoriums & status → Changes (new/dropped). The old screening-flags panel is removed.

### Session B — Moratorium register, population, descriptions, multi-user
5. **Moratorium register** (`moratoria.py`, SQLite table): fields per bulletin; status Active / Expiring ≤ 7 days / Expired / Lifted; link to IRWIN ID (wildfire) or storm name (tropical); ZIP list drives map shading and the "ZIPs not already in moratorium" logic. Seed from the seven bulletins (parsed automatically, human-confirmed). Dashboard panel: active moratoriums with days remaining; alerts when a moratorium expires while its fire is still active or when a tracked fire's candidate ZIPs include ZIPs under another moratorium.
6. **Real population:** Census API key stored locally; ZCTA population (`for=zip code tabulation area`) and place population (`for=place`) cached in `data/geography/`; shown in the ZIP table and on the map; source line "U.S. Census 2020 PL 94-171". Justin's zip-codes.com stays as a manual cross-check link.
7. **Descriptions:** each tracked fire gets a 1–3 sentence description: *human field* first; if empty, a deterministic **auto-summary** composed only from verified facts ("25,407 ac, 27% contained, 4 mi SE of Big Sur (pop 1,700); perimeter moved 0.3 mi toward Big Sur since 9/9") labelled *auto-generated from source facts*. No adjectives, no inference.
8. **Multi-user store:** SQLite (`data/catmonitor.db`) replacing the JSON, with `updated_by` from a sidebar "Your name" box, full history, and a one-click JSON export. Works from a shared OneDrive/SharePoint folder for a small team; document the caveat that simultaneous edits within the same second can collide.

### Session C — Bulletin wizard + polish
9. **Bulletin wizard** (`bulletins.py` + page): pick fire (or storm), type (Emergency Moratorium; later Lift/Extension), lines of business, contacts, effective and expiry dates, impacted ZIPs (pre-filled from VERIFY/REVIEW candidates and the analyst's confirmed list; editable), one-paragraph situation statement (pre-filled from verified facts; editable). Produces a DOCX matching the Hiscox template (Retail Traded / Digital Traded sections, quoted broker communications, diary period) saved to `reports/` for proofreading. On "Issued", the register gets a new Active moratorium. Tropical variant uses counties/parishes/states.
10. **Polish for demo:** status colours on the map legend, UTC/local time labels, Fire Table gains Perimeter distance and Urgency columns, detail §3 becomes the mockup's Candidate ZIP table (ZCTA, distance, band, review state, population, moratorium?, USPS-confirmed), export of the tracked-fire table to Excel in Justin's column order.

### Validation inside Mission 1
- **Hawk** (approved): app candidate ZIPs vs the ten ZIPs in the Hawk bulletin (89506 89439 89508 89523 89533 89503 84939 89507 89512 89557; note 84939 looks like a typo for a Utah ZIP and is itself a good test of the wizard's ZIP validation).
- **Bug Fire** as second case: ten ZIPs across CA/NV in its bulletin, perimeter from the historical service.
- Document both in `docs/validation_hawk.md` and `docs/validation_bug.md`. Demo language: "ZCTA-based screening agrees with the underwriter's list on N of 10; differences are explained by ZIP-vs-ZCTA boundaries; USPS confirmation remains the human step."

### Demo script (what we can honestly say)
"Every morning the app pulls the national fire list, draws every monitored fire's actual perimeter on the Hiscox CAT Map with the ZIPs and towns around it, ranks urgency 1–3 from fixed rules, and queues any recommended status change for an underwriter. Moratoriums are tracked to expiry. A bulletin drafts itself from verified facts for proofreading. ZIP accuracy is Census-ZCTA today, validated against two past moratoriums; USPS confirmation is the human step, and we will refine boundaries as we scale."

---

## Mission 2 — Empower it at scale (after the demo)

| Track | Work | Source / dependency |
|---|---|---|
| **Automatic ingestion** | Scheduled pull of the WFIGS perimeter and incident-location services (no manual CSV); intraday snapshots; diff against the last run; email/Teams digest only when permitted | NIFC FeatureServers (verified live) |
| **Geometry accuracy** | Compare TIGERweb ZCTA vs full TIGER ZCTA on validation fires; ZIP↔ZCTA crosswalk for PO-box/unique ZIPs; USPS ZIP lookup link per ZIP; county/parish polygons for tropical bulletins | Census TIGER, HUD USPS ZIP–ZCTA crosswalk (to be evaluated) |
| **Structures / evacuations** | Evaluate InciWeb incident API and state evacuation feeds (e.g. Genasys/CAL FIRE) for an authoritative structures/evacuation feed; until then human entry with WatchDuty/InciWeb deep links | InciWeb, state feeds (to be researched) |
| **Urgency calibration** | Use stored human overrides to tune thresholds; publish the rule table each iteration; never a black-box score | Internal history |
| **Tropical weather module** | NHC GIS: active-storm cone/track/wind-radii shapefiles and 7-day outlook areas; snapshots and change detection; Hawaii/Atlantic/E-Pacific views; county/parish exposure; bulletin wizard variant (Lala/Edouard/Lowell patterns) | NHC GIS services (to be verified as in Phase 2a) |
| **Internal exposure layer** | If Hiscox policy permits: ~300 insured locations kept in `data/internal/`, joined to perimeter bands and storm cones; separate page and permissions | Internal file |
| **Reporting & distribution** | Leadership PDF/HTML report from the mockup layout; bulletin "Lift" and "Extension" variants; optional Teams post of the daily digest (only on explicit request) | python-docx (present); reportlab or HTML print |
| **Operations** | Shared-folder deployment guide; backup of `data/`; access list; run-book for the daily routine | — |

---

## What the additional workbooks and the bulletin generator add (reviewed 2026-09-10, later)

**Wildfire moratorium workbooks (Palisades, Hurst, Kenneth, Lidia, Sunset — Jan 2025 CA; Monroe Canyon, Pickett Canyon, Cottonwood 2025–26).** One sheet per day, identical layout: County · "Moratoriums" · source link (Cal Fire incident page or WatchDuty) · ZIP list · "Additional zip codes" added on later days · "Combined List" · "Moratorium plan – N days (date)" · "Moratorium Expiration" · "No Updates" · "Expired/Lifted" · "Zip Code Resources" links (unitedstateszipcodes.org, zipmap.net, zip-codes.com, maptive) · embedded map screenshots (2–15 per workbook).
→ This *is* the moratorium register data model: a moratorium has a fire, a county, a source link, a dated ZIP list that **grows over days**, a planned duration, an expiration date and a lifted flag. The register must keep ZIP-list history by day, not just the current list. Palisades went from 7 ZIPs (1/8) to 15+ (1/13) — the "additional ZIPs" event is exactly what the perimeter-to-ZCTA change detection should surface automatically.

**Tropical workbooks (Erin, Imelda, Kiko).** NHC Public Advisory text pasted (watches/warnings, "changes with this advisory"), cone image, per-state county lists (NC/VA for Erin; HI for Kiko), a County Maps sheet, and a large reference county list.
→ Tropical module = advisory text + cone + **county** lists, matching the Lowell/Edouard/Lala bulletins (counties/parishes/state), not ZIPs. Sources to verify in Phase 4: NHC GIS cone/track/watch-warning layers and Census county polygons.

**Southern Coastal County Zips (10-2024).** Justin's coastal-county strategy list (state, county, tier, 2024 implementation), a **41,700-row ZIP master** (ZIP → city, county, state, metro) and an RMS ZIP→county table.
→ A ready-made **ZIP validation and ZIP→county crosswalk** for the wizard and register (would have caught "84939" in the Hawk bulletin) and the county→ZIP expansion tropical bulletins need. Load into `data/geography/zip_master.parquet` (internal reference; not public data, keep in the repo's data folder, not in any bulletin).

**County Liability Concerns – Judicial Hotspots.** Liability limits by county; unrelated to catastrophe monitoring. Not used.

**Bulletin generator (`bulletin_files.zip`: generate_hiscox_bulletin.js, hiscox_header.jpeg, HOW_TO).** A tested Node/docx-js generator with the real header banner, repeating header/footer, grey-bar sections and a metadata table. House rule: never recreate the banner; edit only `BULLETIN_DATA`.
→ The moratorium bulletin wizard should **reuse this generator and asset**: either call `node generate_hiscox_bulletin.js` with a moratorium-specific `BULLETIN_DATA` (sections become "Impacted area", "Retail Traded", "Digital Traded", "Who does this impact?"), or, if Node is not available on the work machine, port the same layout to python-docx using the same `hiscox_header.jpeg`. **Checked 2026-09-10: Node is not installed on this machine, so the wizard will use python-docx (installed) with the extracted banner asset.** Content rules from the seven moratorium PDFs: fixed broker communications quoted verbatim, diary period (1 week / 2 weeks / 21 days), lines of business, contacts Justin Cardullo and David Seaman, "INTERNAL USE ONLY".

## Progress log

- **2026-09-10 — Session A delivered (v0.3).** Geometry layer live (NIFC current + historical perimeters by IRWIN, Census TIGERweb ZCTAs/places per fire, UTM edge distances, 1/5/10-mile bands, results cached per snapshot); Hiscox CAT Map national and per-fire views (pydeck, CARTO basemap); urgency 1–3 with review queue (Accept / Keep, analyst level recorded, Keep suppresses re-queueing until the level changes); default fire selection rule; editor name on every edit; description field with auto-summary fallback; live perimeter download when a snapshot has no GeoJSON; ZIP master loaded for community names and ZIP validation; Hawk validation first pass in `docs/validation_hawk.md` (7 of 10 bulletin ZIPs in VERIFY/REVIEW; 84939 invalid ZIP; 89533/89507 likely no-ZCTA ZIPs). Census API key still needed for population.

## Decisions (Sean, 2026-09-10)
1. Urgency scale: **1 = watch, 2 = elevated, 3 = act.**
2. Bulletin wizard: **demo-grade Word (DOCX) output** using the installed python-docx; no PDF dependency for now.
3. Team storage: **keep the JSON file, add editor name** (`updated_by`); SQLite deferred. Concurrent-edit caveat documented.
4. Build order: **Session A first (map + urgency)**, then B, then C.
