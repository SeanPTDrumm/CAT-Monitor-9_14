# Catastrophe Monitor · Hiscox CAT Map (v0.3 - U.S. Wildfire)

Map-first underwriting dashboard for BOP catastrophe monitoring. It loads the national
WFIGS fire list, ranks every fire with fixed urgency rules (1 watch · 2 elevated · 3 act),
queues recommended status changes for a human decision, draws each monitored fire's
actual NIFC perimeter with the Census ZCTAs and places around it, and keeps every
analyst decision across downloads. Underwriting decisions remain with the analyst.

## Run

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

Browser: http://localhost:8501. Enter your name in the sidebar so edits are attributed.

## Daily routine

1. Download the current **WFIGS Interagency Fire Perimeters** CSV
   (https://data-nifc.opendata.arcgis.com/datasets/nifc::wfigs-current-interagency-fire-perimeters).
   The GeoJSON is optional: the app fetches live perimeters from NIFC when it is omitted.
2. Sidebar → **Upload files** (or drop the CSV in this folder → **Import from project folder**).
3. Dashboard → **Compute geography** for tracked and elevated fires (about 3 s per fire).
4. Work the **Review queue**: Accept or Keep each recommendation; set your own 1-3 level.
5. Open **Fire Detail** for anything at urgency 3: map, candidate ZIPs, analyst record.

## What the numbers are

| Item | Source / method | Label in app |
|---|---|---|
| Fire facts (acres, containment, dates) | WFIGS CSV, read-only | Verified Facts; missing = **Not verified** |
| Change columns | IRWIN-ID join between two snapshots | calculated |
| Urgency 1-3, recommendation | Fixed rules in `urgency.py` (shown in sidebar) | deterministic; never changes status by itself |
| Perimeter polygon | NIFC WFIGS FeatureServer (current, then historical) or the snapshot GeoJSON | source + perimeter date shown |
| ZCTA and place polygons | Census TIGERweb 2020 TIGER, fetched per fire, cached with snapshot | ZCTA ≠ USPS ZIP; confirm with USPS |
| Distances | UTM projection, shapely edge-to-edge (`geo/spatial.py`) | VERIFY (intersects) / REVIEW (≤5 mi) / NEARBY (≤10 mi) |
| Population | Census 2020 PL 94-171 via API; needs a free key in `data/census_api_key.txt` | Not verified until a key is present |
| ZIP community names | Hiscox ZIP master (10-2024) `data/geography/zip_master.csv` | internal reference |
| Population centre, structures, evacuations, moratorium ZIPs, notes | Analyst research (WatchDuty, InciWeb, Cal Fire, USPS) | analyst |

**Miles (origin)** in the Fire Table is the WFIGS point-of-origin description Justin sorted by;
**Perimeter → place** is the calculated edge distance and supersedes it wherever geography has run.

## Files

| Path | Purpose |
|---|---|
| `app.py` | Streamlit UI: Dashboard (CAT Map, review queue), Fire Table, Fire Detail (fire map, candidate ZIPs) |
| `wfigs.py` | WFIGS CSV/GeoJSON loading and parsing |
| `snapshots.py` | Snapshot storage under `data/snapshots/`, comparison, material-change rules, live perimeter fetch on save |
| `analyst.py` | Analyst records (status, notes, ZIP entries, checklist, history, urgency decisions) in `data/analyst_status.json` |
| `urgency.py` | Urgency 1-3 rules and recommendations |
| `screening.py` | "Why it surfaces" evidence flags |
| `maps.py` | pydeck layers for the national and per-fire maps |
| `geo/` | `net.py` (HTTP with the corporate-TLS workaround), `perimeters.py` (NIFC), `census.py` (TIGERweb, population), `spatial.py` (maths), `analysis.py` (per-fire run and cache), `zipmaster.py` |
| `baseline.py` | One-time import of Justin's workbook notes from `reference/` |
| `CURRENT.md` | **Start here: what is true now** — what works, architecture, locked decisions, screening rules, what must not break, known issues |
| `NEXT_TASK.md` | The single next task, with acceptance criteria and how to test it |
| `docs/` | `validation_hawk.md` (ZIP screening vs the Hawk bulletin, 4 open questions), `phase2_geography_sources.md` (sources and method behind the spatial engine), `roadmap_missions.md` |
| `data/` | Snapshots (with `spatial/` results per fire), analyst decisions, geography cache. **Back this up.** |

## Known limits (v0.3)

- No Census API key yet → populations read Not verified and urgency 3 relies on "a Census place within 5 mi".
- Structures threatened and evacuations have no public API; they are analyst-entered.
- Analyst records are a shared JSON file; two people saving in the same second can collide.
- Moratorium register, bulletin wizard and tropical weather are the next build sessions (see `docs/roadmap_missions.md`).
