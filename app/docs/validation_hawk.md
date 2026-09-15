# Validation — Hawk Fire (NV), app ZCTA screening vs. Hiscox bulletin ZIPs

Prepared 2026-09-10. Status: **first pass, awaiting Justin's measured distances and sign-off.**

## Inputs

- Perimeter: NIFC WFIGS Interagency Fire Perimeters (historical, live), IRWIN `{D11B03E5-0A65-4618-B493-56BABF82A834}`, perimeter current 2026-08-31T12:32:01+00:00, 15,083 GIS acres, map method IR Image Interpretation, containment 100% at retrieval. The fire has left the current WFIGS feed (contained), so the historical service supplied the polygon.
- ZCTA and place geometry: U.S. Census Bureau TIGERweb (2020 TIGER/Line geometry, live), retrieved 2026-09-10T12:58:32.
- Method: spatial-v1 (UTM edge-to-edge, shapely 2 / pyproj 3), CRS EPSG:32611; calculated perimeter area 15,094.5 ac vs WFIGS 15,083.1 (difference +11.4 ac, projection/rounding).
- Bulletin: *Hawk Fire – CA and NV – Quoting and Binding Restrictions*, dated August 24, 2026, effective through 11:59 PM September 21, 2026. Ten ZIPs listed.

## Bulletin ZIPs vs app result (10-mile screen)

| Bulletin ZIP | ZIP master community | App review state | Distance from perimeter (mi) | Note |
|---|---|---|---|---|
| 89506 | Reno, NV | VERIFY | 0.00 | intersects perimeter |
| 89439 | Verdi, NV | VERIFY | 0.00 | intersects perimeter |
| 89508 | Reno, NV | REVIEW | 0.06 | within_1mi |
| 89523 | Reno, NV | VERIFY | 0.00 | intersects perimeter |
| 89533 | Reno, NV | — | — | no ZCTA within 10 mi of perimeter; check whether PO-box/unique ZIP or beyond screen radius |
| 89503 | Reno, NV | REVIEW | 1.58 | within_5mi |
| 84939 | **not a valid ZIP in ZIP master** | — | — | not a valid ZIP; likely typo (Utah range) |
| 89507 | Reno, NV | — | — | no ZCTA within 10 mi of perimeter; check whether PO-box/unique ZIP or beyond screen radius |
| 89512 | Reno, NV | REVIEW | 2.47 | within_5mi |
| 89557 | Reno, NV | REVIEW | 3.29 | within_5mi |

**Agreement:** 7 of 10 bulletin ZIPs fall inside the app's VERIFY/REVIEW/NEARBY screen; 3 VERIFY (perimeter intersects), 4 REVIEW (within 5 mi).

## App candidates not in the bulletin (VERIFY / REVIEW only)

| ZCTA | Community | Review state | Distance (mi) |
|---|---|---|---|
| 96105 | Chilcoot, CA | REVIEW | 1.12 |
| 96118 | Loyalton, CA | REVIEW | 2.81 |
| 89433 | Sun Valley, NV | REVIEW | 2.95 |
| 89519 | Reno, NV | REVIEW | 3.02 |
| 89511 | Reno, NV | REVIEW | 3.13 |
| 89509 | Reno, NV | REVIEW | 3.54 |
| 89501 | Reno, NV | REVIEW | 4.03 |
| 89436 | Sparks, NV | REVIEW | 4.11 |
| 89502 | Reno, NV | REVIEW | 4.75 |
| 89431 | Sparks, NV | REVIEW | 4.94 |

These are candidates for the underwriter to consider or dismiss (some are Reno core ZIPs a few miles from the perimeter; 96105/96118 are Sierra County, CA communities across the state line).

## Nearest Census places

| Place | Kind | Distance (mi) | Direction | Population 2020 |
|---|---|---|---|---|
| Reno | Incorporated Place | 0.00 | SE | Not verified (no Census API key yet) |
| Verdi | Census Designated Place | 0.75 | SW | Not verified (no Census API key yet) |
| Golden Valley | Census Designated Place | 0.96 | E | Not verified (no Census API key yet) |
| Mogul | Census Designated Place | 1.42 | S | Not verified (no Census API key yet) |
| Verdi | Census Designated Place | 1.45 | SW | Not verified (no Census API key yet) |
| Lemmon Valley | Census Designated Place | 1.80 | NE | Not verified (no Census API key yet) |
| Cold Springs | Census Designated Place | 1.95 | N | Not verified (no Census API key yet) |
| Sun Valley | Census Designated Place | 2.95 | E | Not verified (no Census API key yet) |

## Discrepancies to resolve with Justin

1. **84939** is not a valid ZIP in the ZIP master (Utah 849xx range). Probable typo in the bulletin; the wizard's ZIP validation would have flagged it. Ask which Reno-area ZIP was intended (89439 Verdi is already listed; 89509? 89519?).
2. **89533** and **89507** (both Reno) have no ZCTA within 10 mi of the perimeter. Both are likely PO-box or unique ZIPs without a Census ZCTA. Confirm via USPS lookup; if so, they are legitimately outside ZCTA screening and must be handled by the ZIP-master/USPS step, not by geometry.
3. The app proposes additional Reno-side ZCTAs within 5 mi (89433 Sun Valley, 89509, 89519, 89511, 89501, 89502, 89431, 89436 Sparks) and two California ZCTAs (96105 Chilcoot, 96118 Loyalton). Justin's list excluded them: was that judgement (barriers, wind, low exposure) or measurement? Record the reasoning as a rule candidate.
4. Distances: Justin's measured distances (WFIGS map + Google Maps) are needed to compare against the perimeter edge distances above (tolerance ±0.5 mi at band edges).

## Gate

Do not scale ZCTA screening to automatic bulletin drafting until items 1-4 are answered and Sean signs off. Second validation case: **Bug Fire** (ten ZIPs in its bulletin, perimeter from the historical service).