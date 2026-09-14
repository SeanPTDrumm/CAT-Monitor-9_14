# Catastrophe Monitor — Current State

## Purpose

A local Streamlit app for commercial BOP wildfire catastrophe monitoring at Hiscox. It cuts
the manual research burden in Justin's wildfire workflow while preserving human underwriting
judgment, source transparency and an audit trail. First hazard is U.S. wildfire; tropical
weather comes later. Justin remains the decision-maker — the app never imposes or lifts a
moratorium.

## What currently works

- **WFIGS ingestion** (`wfigs.py`) — parses the official NIFC perimeter CSV export, normalises
  columns, deterministically parses the origin-point description. Missing values stay missing.
- **Snapshots and comparison** (`snapshots.py`) — stores each upload under
  `data/snapshots/<id>/` with raw CSV, normalised CSV, `perimeters.geojson` and `meta.json`.
  `compare()` joins on IRWIN ID and calculates acreage/containment/perimeter deltas and
  `is_new`.
- **Perimeter geometry** — every fire in the current snapshot already has its polygon stored
  locally (201 of 201). Nothing needs fetching for geometry.
- **Spatial engine** (`geo/spatial.py`, `geo/analysis.py`, `geo/census.py`,
  `geo/perimeters.py`) — projects to the perimeter's UTM zone and measures true edge-to-edge
  distance from the **actual perimeter** to Census ZCTA and populated-place polygons, with
  1/5/10-mile bands, 2020 population, and raw inputs cached so every number is reproducible.
  Verified working on real data.
- **Analyst records** (`analyst.py`) — keyed on IRWIN ID, so a new download never overwrites a
  decision. Append-only status history, urgency decisions, and a **review watermark**
  (`record_review`) recording the facts as they stood at the last review.
- **Justin's baseline as starting state** (`baseline.py`) — his workbook sheets are full WFIGS
  exports, so the acreage/containment/perimeter date he reviewed are read directly from them.
  Sheet `9-9` is the last completed review pass (194 fires, zero notes = position unchanged);
  sheet `9-8` carries his written conclusions. 209 records are stamped with that watermark.
- **Attention screening** (`attention.py`) — deterministic, no Streamlit dependency, no score.
  Decides whether a fire needs attention and returns the named evidence.
- **Dashboard** (`dashboard.py`, `dashboard_map.py`) — three summary states, Changed/New and
  Currently Monitoring lists, central map, selected-fire quick facts, explicit loading and
  error states.
- **Fire Table** (`app.py:page_table`) — filterable editable table of all fires.
- **Fire Detail** (`app.py:page_detail`) — verified facts, change vs prior snapshot, candidate
  ZIP screening, analyst form, sources.

Current data state: 3 snapshots, newest `2026-09-11_160449` (197 fires, data through
2026-09-11 18:08 UTC). Geography computed for all 197 fires; 122 fires have nearest population
center with 2020 Census population value; 122 fires have verified perimeter distance. Analyst
records reset to baseline-only state. Dashboard loads successfully. Latest CSV and GeoJSON
upload succeeded.

## Architecture

**Engine (no Streamlit, safe to call from tests or scripts)**
- `wfigs.py` — source parsing
- `snapshots.py` — persistence + snapshot comparison
- `analyst.py` — analyst record schema, status history, review watermark
- `baseline.py` — Justin's workbook: notes import, reviewed facts, watermark seeding
- `attention.py` — dashboard screening: buckets, evidence, flags
- `urgency.py` / `screening.py` — older deterministic urgency 1-3 rules (still used by Fire
  Table and the rule-recommendation queue)
- `geo/` — perimeters, Census geometry/population, spatial maths, ZIP master

**Presentation**
- `app.py` — sidebar, `build_frame()`, router, Fire Table, Fire Detail, dashboard adapter
  (`_dashboard_context`) and secondary tabs
- `dashboard.py` — all dashboard layout; receives read-only accessors via a context dict
- `dashboard_map.py` — dashboard cartography and camera; independent of `maps.fire_deck`
- `maps.py` — Fire Detail and national map decks (unchanged)

`build_frame()` in `app.py` is the join point: it assembles source facts + deltas + analyst
record + urgency + geography + `attention.assess()` into one row per fire.

## Locked product decisions

- Dynamic "requiring attention" queue. No fixed Top 5.
- Exactly three summary states: Requiring Attention, Currently Monitoring, Reviewed / No
  Material Change.
- Three columns: fire lists | Hiscox map | selected-fire quick facts. The map is the visual
  centre.
- First click selects and loads the map; it does not navigate. "View detailed review →" opens
  Fire Detail.
- The dashboard shows **no admin sidebar** — navigation and analyst name only. Data controls
  live in the header "Data" popover.
- Dark navy dashboard styling is injected by `dashboard.render()` only. **No global
  `.streamlit/config.toml`** — Fire Detail and Fire Table keep their original appearance.
- Justin's baseline is the authoritative starting state. Fires he reviewed and dismissed stay
  quiet until facts move.
- Distance always means distance from the **actual current perimeter**. Without perimeter
  geometry, show "Not verified" — never substitute the origin-point distance.
- Never fabricate acreage, ZIPs, population, structures, evacuations, distances or citations.
  Unverifiable = "Not verified".
- The app never imposes or lifts a moratorium; it only flags.

## Wildfire screening rules (`attention.py`)

Buckets: `attention` / `monitoring` / `reviewed` / `background`.

**Elevation signals — surface a fire at any size or distance:**
evacuation orders or warnings; structures threatened; perimeter moved ≥0.5 mi toward a place;
a ZIP area newly in concern range or moving to a closer band; moratorium in force, expiring
within 14 days, expired, or expiry unrecorded; analyst status Investigate.

**Change signals — require materiality first:**
acreage +1,000 or +25% (min 100 ac absolute), or containment down ≥10 pts, measured against
the review watermark — **and only if the fire is ≥300 acres or a populated place is within
1 mile**. Growth on a small fire with nothing near it is not an interruption.

**First look (never-reviewed fires only):**
≥300 ac with a place or ZIP area within 5 mi; or ≥300 ac within 10 mi at <25% contained; or
any size with a populated **place** within 1 mi at <50% contained; or ≥300 ac with no
geography yet and a WFIGS origin reference within 5 mi (marked provisional).

**Quieting:** containment ≥95%; watermark present with no delta past threshold; nearest
geography beyond 10 mi.

**Hard rules:**
- `is_new` alone NEVER qualifies a fire. A new fire must carry its own evidence.
- Intersecting a large rural ZCTA is not nearness to people. Sub-300-acre exceptions require a
  populated **place**, not a ZIP area.
- 300 ac / 5 mi are guidelines, not gates.
- Thresholds live in `attention.THRESHOLDS` and are described by `attention.describe()`.

## Map behaviour we want

- Fire perimeter **dominant**: strong orange outline, light fill, drawn last so nothing covers
  it.
- ZCTA boundaries **outline-only, no fill**. Single exception: a ZCTA under an existing
  moratorium gets a subtle low-alpha purple fill and heavier outline.
- ZIP labels only on VERIFY/REVIEW areas, placed at each area's **nearest point to the fire**
  (`shapely.nearest_points`) — never a centroid, which for a rural ZCTA can sit 30 miles away.
- Nearest populated place highlighted; others plain.
- Proximity rings omitted on the dashboard; the calculated distance is stated in quick facts.
- **Camera**: scales with the fire (`MAX_SPAN_MULTIPLE=3`), floored at `MIN_CONTEXT_MILES=2.5`
  so a small fire still shows adjacent ZIP boundaries, ceilinged at `MAX_CONTEXT_MILES=6` so a
  wide rural ZCTA cannot shrink the fire. Measured: a 0.8-mile fire gets a 5-mile view; an
  18-mile fire gets 25 miles.
- Loading shows "Loading fire perimeter and ZIP geography…". Failure shows an explicit reason
  plus a compute action — never a silent failure or a stale map.
- Map and quick-facts panel must name the same ZIPs and places.

## Must not be broken

- `app.py:page_detail()` and `app.py:page_table()` — behaviour and original light styling.
- `maps.py` — `fire_deck`, `national_deck`, `zcta_feature`, `place_point` and colour
  constants. Fire Detail depends on `fire_deck` exactly as it is. Dashboard cartography lives
  in `dashboard_map.py` instead.
- `geo/` — the spatial engine. Any change to distance or ZIP output invalidates prior analyst
  conclusions.
- `wfigs.py`, `snapshots.py` — source parsing and snapshot comparison.
- `analyst.py` schema — additive changes only. Records are the analyst's audit trail; never
  drop or rewrite fields. `record_review` appends the previous watermark to `review_history`.
- Dashboard CSS must stay scoped to `dashboard.render()`. Do not add a global theme.
- Navigation must route through `st.session_state["pending_page"]`, applied in `main()` before
  the sidebar radio is created. Assigning `session_state["page"]` after the radio exists does
  not take effect.
- Writes to analyst records must be `on_click` callbacks with a stable widget key, never an
  inline `if st.button(...)` body in a list that re-orders. A misfiring per-row button
  silently overwrote two watermarks during development.

## Known issues

- **Dashboard polish is unfinished.** All four areas need work: the map, the fire list rows,
  the quick-facts panel, and overall density/type/spacing.
- **Black rectangles on the map.** ZIP/ZCTA labels appear as black rectangles and are unreadable.
  Require investigation into `dashboard_map.py` label rendering.
- **Flags and parameters do not yet use Justin's vocabulary.** His 41 notes contain the real
  decision language — "Contained", "Small, nearly contained", "No structures threatened",
  "Body of water separation" / "River separation", "low population", "No BOP in AK/WA",
  "Moratorium until 9/21" — always formatted `<condition>; <place> ~<population>`. This is
  tomorrow's task; see NEXT_TASK.md.
- **No state book exclusion.** Justin dismisses whole states ("No BOP in AK", "No BOP in WA").
  The app has no concept of where Hiscox writes BOP, so Mukluk (AK) and Sinlahekin (WA) are
  screened as if they mattered.
- **Natural barriers never surface.** `analyst.ANALYST_FIELDS["barriers"]` exists but nothing
  reads or flags it, though it is one of Justin's recurring dismissal reasons.
- **Feed dropouts are not handled per Justin's rule.** A tracked fire that leaves the WFIGS
  feed should resurface only if its moratorium expires within 2 days, and should then explain
  why it left (merged into a complex — check `attr_IsCpxChild` / `attr_CpxName` — or reached
  100% containment).
- **Moratorium data is free text.** The bulletin PDFs state effective date, expiry to 11:59 PM,
  and an impacted ZIP list in a consistent format; the app stores this as prose.
  `baseline.expiry_from_note` parses only "Moratorium until M/D" from an analyst note.
- **Hawk validation done but not signed off** — see `docs/validation_hawk.md`. The app's ZCTA
  screening matched **7 of the 10** ZIPs in the Hawk bulletin (3 VERIFY / 4 REVIEW). Four
  questions are open for Justin, and `CLAUDE.md`'s gate says do not scale to automatic
  bulletin drafting until they are answered:
  1. Bulletin ZIP `84939` is not a valid ZIP (Utah range) — probable typo.
  2. `89533` and `89507` have no ZCTA within 10 mi — likely PO-box/unique ZIPs that must be
     handled by the USPS/ZIP-master step, not by geometry.
  3. The app proposes 10 extra ZCTAs within 5 mi that Justin's list excluded (Reno-side plus
     two California ones) — was that judgment or measurement? His answer is a rule candidate.
  4. His measured distances are still needed to compare against the perimeter-edge distances
     (tolerance ±0.5 mi at band edges).
  Second validation case should be the Bug Fire.
- `use_container_width` is deprecated in Streamlit 1.63 (removal after 2025-12-31); used
  throughout. Cosmetic warning only.
- Streamlit does not reliably hot-reload edits to imported modules; restart the server to pick
  up changes to `attention.py` / `dashboard_map.py`.

## Recently fixed

- **Population data now available** — Census API key installed and verified. All 122 fires with
  nearest population centers now display 2020 Decennial Census population values. Perimeter
  distance calculated for all 122 measured places.
- **Geography computation completed** — all 197 fires in latest snapshot have spatial analysis
  computed. Perimeter geometry, ZCTA/place proximity, and distance measurements are complete
  with zero failures.
- **Repeated-filename content-hash handling** — WFIGS may provide updated files with identical
  names; the app now identifies duplicates by content hash and only creates new snapshots when
  contents differ.
- **Float/NaN description parsing crash** — fixed underlying data handling to prevent crashes on
  malformed or missing WFIGS description fields.

## Running it

```bash
python -m streamlit run app.py
```

Or the configured launch profile `cat-monitor` (`.claude/launch.json`, port 8501).
