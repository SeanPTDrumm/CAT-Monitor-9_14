# Local data guide

All paths below are relative to `data` (or your absolute `CAT_MONITOR_DATA_DIR`). Setup creates folders but does not fabricate records. PLACEHOLDER.txt files are explanatory text, not datasets.

| Folder or file | How it populates | Action needed |
|---|---|---|
| `operational_snapshots/` | App creates timestamped folders after you import and save official data; includes raw.csv, normalized.csv, meta.json, optional perimeters.geojson and spatial results | Obtain and upload current official WFIGS CSV and matching perimeter GeoJSON. There is no scheduled CSV feed. Optional live perimeter retrieval needs network access. |
| `review_history/reviews.json` | Created when an in-app decision is saved; subsequent decisions retain earlier history | Review and save in the app. Empty at delivery. |
| `review_history/analyst_status.json` | Legacy analyst/baseline controls write this separate store | Optional; never substitute it for active in-app review history. |
| `review_maps/` | App saves HTML when Log Review includes an available map | Compute/display geography first. Without a map, the review can save and report that map capture failed. HTML backgrounds/assets still need internet. |
| `logs/` | Each launcher run creates a timestamped Streamlit log | No manual input; retain logs for troubleshooting. |
| `cache/population_cache.json` | Census API population lookups cache returned values | Optional API key and network access needed for new values. Not a complete Census reference dataset. |
| `config/census_api_key.txt` | Never created with a key by setup | Optional: put only your real Census key in this UTF-8 text file, or set `CENSUS_API_KEY`. Environment value takes precedence. Never commit or share a populated key file. |
| `reference/zip_master.csv` | Not downloaded | Optional genuine internal ZIP reference. UTF-8 CSV headers: `zip,city,state,county`. Preserve five-digit ZIPs as text, including leading zeros. Restart after adding it. It is not Census population data. |
| `reference/baseline/` | Not downloaded | Optional genuine Excel baseline workbooks. The existing default is `2026-09 Fire Tracking.xlsx`; source baseline import expects `attr_IrwinID` and `Notes` columns. Use existing baseline controls if needed; active reviews remain separate. |
| `reference/census/` | Intentionally empty and reserved | Add only real, provenance-documented Census files later. No generic CSV/shapefile auto-loader is implemented. Adding arbitrary files does not make the application consume them; an explicit adapter will be needed. |
| `imports/` | Optional staging folder; existing folder-import selector scans it | Put official CSV and GeoJSON files here if using folder import, or upload from anywhere through the app. |

## Missing references

Missing ZIP master means community labels are unavailable; a visible message gives its expected path. Missing API key means populations show **Not verified**. Missing baseline files simply leave the optional workbook list empty. Missing bulk Census reference files do not crash the app: it continues using its existing live TIGERweb/Census API approach. An unavailable TIGERweb service produces an explicit geography-unavailable result.

Census support is retained, not replaced with invented local counts. The inherited ZCTA population endpoint limitation remains documented in BUILD_AUDIT.md. A valid key does not guarantee every population value will be returned. Previously saved spatial results may require **Compute / refresh geography** to retry after a key or service becomes available.

## Network dependencies

Setup downloads dependencies from PyPI (pypi.org and files.pythonhosted.org). It does not require Streamlit Cloud. Runtime live geometry uses Census TIGERweb and NIFC ArcGIS services; optional population uses api.census.gov. Map styling uses external tiles/assets. Obtain work-network access through your normal IT process if these services are blocked. Stored snapshots/reviews remain local and persistent even when external services are unavailable.
