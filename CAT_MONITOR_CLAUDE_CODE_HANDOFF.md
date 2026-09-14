# CAT Monitor: Claude Code Implementation Handoff

## Purpose

This is the authoritative implementation handoff for CAT Monitor.

The only stakeholders in scope are Sean and Justin. This work is exclusively for wildfire tracking. Do not introduce requirements, terminology, flags, logic, or references from any other project.

The goal is to improve Justin's current manual WFIGS review process without replacing underwriting judgment.

CAT Monitor should help the reviewer:

1. Sort and optionally filter the fires already surfaced by the application.
2. See the facts Justin uses in the current manual process.
3. Understand whether a person has reviewed a fire and what has changed since that review.
4. Decide to Ignore, Monitor, or Create Moratorium.
5. Record optional Review Rationale with Ignore or Monitor.
6. Optionally save the current map image with a review.
7. Apply the saved review correctly after later data uploads.

---

# Locked Decision: Day 1 Fresh Baseline

The redesigned CAT Monitor will begin with a clean Day 1 operational baseline created inside the app by Sean and Justin.

Previous Excel workbooks are historical reference only. Do not import old Excel-derived notes, statuses, review watermarks, distance references, or moratorium records into the new Day 1 baseline.

During Day 1, Sean and Justin will review the current fires and save new Ignore or Monitor decisions. Those saved reviews become the baseline for future uploads.

A fire without a saved Day 1 review has not yet been reviewed in the new operational baseline.

## Existing analyst-status data

The repository currently contains Excel-derived analyst reviews and review watermarks seeded from Justin's prior workbook. These must not populate or control the new Day 1 baseline.

Required handling:

1. **Preserve the existing analyst-status data as an archived backup.** Retain it in full, unmodified, outside the active review store.
2. **Create a clean active analyst-review store for Day 1.** The redesigned app reads and writes only this store.
3. **Do not import or display old Excel-derived reviews, notes, statuses, watermarks, distance references, or moratorium records in the new operational baseline.** They are not shown in the dashboard, the selected-fire panel, review states, review history, or change comparisons.
4. **Sean and Justin's new in-app Ignore and Monitor reviews create the Day 1 baseline.** No other source establishes an operational baseline.
5. **Do not modify application code yet.** This decision is recorded for the implementation that follows; no code changes are authorized by this section.
6. **Do not delete any existing data.** Archiving is a move or copy, never a deletion.

Before Day 1, every fire therefore has no operational baseline and shows Initial Review, regardless of any archived Excel-derived record that may exist for it.

---

# Locked Decision: Census and Geography

The clean Day 1 baseline applies only to analyst reviews and review history.

Preserve the existing Census integration, Census API key configuration, cached Census data, populated-place calculations, 2020 population data, and perimeter-distance calculations.

Do not delete, reset, expose, or replace the Census API key.

When verified population is available, display it as already specified in the handoff.

---

# 1. Implementation Boundaries

## 1.1 Preserve current queue behavior

Preserve the existing logic that determines which non-Alaska fires initially qualify for the dashboard and which previously reviewed fires resurface.

The approved Alaska rule in Section 3 is the only exception: Alaska fires are automatically ignored and hidden from the main dashboard.

For all other fires, add only the sorting, optional filtering, display, and review workflow described here. Do not broaden or narrow the existing initial-review population.

Do not create or change material-change thresholds in this build. Continue using the application's existing review and change logic.

## 1.2 Preserve existing records as archived backup

Use additive changes where possible.

Do not delete or destructively alter the existing Excel-derived analyst-status data. Preserve it in full as an archived backup.

The archived data is **not active** in the redesigned app. It does not populate the Day 1 baseline, does not appear in the dashboard or review history, and is never used as a comparison baseline. See *Locked Decision: Day 1 Fresh Baseline*.

Reviews saved inside CAT Monitor from Day 1 onward are the only active review records. Once such reviews exist, do not overwrite, reseed, or destructively migrate them; they remain valid even when earlier in-app records do not contain the new Review Rationale or saved-map fields.

Use a stable fire identifier, preferably IRWIN ID. Do not merge fires by name.

## 1.3 Repeated-filename snapshot deduplication

WFIGS may provide updated files using the same filename as an earlier download.

- Same filename + different contents = allow import and create a new snapshot.
- Same filename + identical contents = do not create a duplicate snapshot.

Use file-content comparison (e.g., content hash) to identify duplicates. Do not use filename alone.

Previously saved snapshots remain unchanged.

## 1.4 Do not invent information or workflow

Do not infer or create:

- Population values
- Evacuation information
- Structures-threatened information
- Natural-barrier logic
- Material-change thresholds
- Risk scores
- Additional state rules
- New flags or review states
- Final bulletin ZIP codes from ZCTAs

Except for the Alaska rule below, screening evidence must not automatically choose Ignore, Monitor, or Create Moratorium.

---

# 2. Data Inputs

The app will receive:

- The most recent available WFIGS CSV
- The most recent available perimeter GeoJSON

The CSV may be newer than the GeoJSON because perimeter geometry is not generated as frequently.

Use the application's existing ingestion and normalized fields. Do not create a second raw-CSV parser in the dashboard.

Justin's working spreadsheet retains WFIGS fields including:

```text
poly_IncidentName
attr_CreatedBySystem
attr_IncidentSize
attr_PercentContained
Distance
WFIGS location-description field
```

Claude Code must inspect the current CSV and existing normalization to confirm the exact raw names for Distance and location description. Do not guess column names.

Readable UI labels:

```text
Fire name       ← poly_IncidentName
Source          ← attr_CreatedBySystem
Current size    ← attr_IncidentSize
Containment     ← attr_PercentContained
```

Justin's spreadsheet also has a manually maintained Notes column. Those notes are reviewer judgment, not assumed WFIGS source data. CAT Monitor captures that judgment as Review Rationale.

## CSV and GeoJSON freshness

Use current CSV values for current tabular facts.

Use the latest available matching GeoJSON for perimeter display and existing perimeter-based calculations.

Do not imply that older geometry is from the latest CSV upload. Preserve and display existing source dates or timestamps where the current architecture makes them available.

A missing or older perimeter must not be interpreted as containment, closure, reduced risk, or disappearance.

---

# 3. Alaska

For any fire where the current WFIGS state is `AK`:

```text
Disposition          Ignore
Review Rationale     No coverage in AK
Main dashboard       Hidden
```

Retain the underlying source record.

No additional Alaska workflow, alert, badge, screen, reviewer action, or special handling is required for this build.

---

# 4. Screening Standards

These standards control sorting, optional filtering, and visual presentation. They do not change the existing queue logic.

## 4.1 Distance

Distance is Justin's main organizing consideration.

WFIGS Distance supports Justin's familiar primary sorting and the initial `Within 5 miles` filter.

Perimeter Distance is a separate, more precise exposure measurement shown and sortable when the existing geography calculation is available.

```text
WFIGS Distance of 5 miles or less     Main manual-review priority
WFIGS Distance over 5 miles           Lower priority, but still reviewable
```

Do not describe the WFIGS five-mile result as verified fire-perimeter proximity. A fire beyond five WFIGS miles may still deserve review because of size, containment, calculated Perimeter Distance, or reviewer-observed context.

## 4.2 Size

```text
500 acres and above     Higher review priority
Under 500 acres         Lower review priority
```

A fire under 500 acres is not automatically hidden or ignored.

Use only this size breakpoint. Do not invent additional acreage tiers or color bands.

The numeric acreage must always remain visible.

## 4.3 Containment colors

Always show the numeric containment percentage and apply these exact bands:

```text
100%          Green
90–99%        Yellow
80–89%        Orange-yellow
70–79%        Orange
40–69%        Bright orange / reddish orange
Under 40%     Red
Unavailable   Neutral grey
```

Boundary checks:

```text
39%  → Red
40%  → Bright orange / reddish orange
69%  → Bright orange / reddish orange
70%  → Orange
79%  → Orange
80%  → Orange-yellow
89%  → Orange-yellow
90%  → Yellow
99%  → Yellow
100% → Green
```

Requirements:

- Do not treat blank containment as 0%.
- Color is a visual aid, not a disposition.
- Color must not be the only way the value is communicated.
- Apply color to the value, indicator, or cell. Do not flood the entire selected-fire panel.
- Keep styling scoped to the dashboard.

---

# 5. Distance Fields and Sorting

There are two different distance concepts. Never combine them in one field.

## 5.1 WFIGS Distance

WFIGS provides a distance and location description used in Justin's current manual workflow.

Example source values:

```text
Distance                    15
Location description        N from Ronald, WA
```

Readable display:

```text
WFIGS location
15 miles north of Ronald, WA
```

## 5.2 Perimeter Distance

When existing geography calculations provide it:

```text
Nearest population center
[Place]

Distance from fire perimeter
[Verified edge-to-edge distance]
```

Do not substitute WFIGS Distance for missing Perimeter Distance.

## 5.3 What the reviewer sees

Use one ordinary sort dropdown above the fire list:

```text
SORT BY
[ WFIGS Distance ▼ ]
```

Choices:

```text
WFIGS Distance
Perimeter Distance
Fire Size
Containment
```

Rules:

- WFIGS Distance is the default sort, nearest first.
- Perimeter Distance is a separate optional sort.
- Perimeter Distance sorting uses only verified calculated values.
- Fires without verified Perimeter Distance appear after verified values and display `Not verified`.
- Do not fill their missing Perimeter Distance with WFIGS Distance.
- When values in the selected sort are equal, use lower containment first, then larger size.

## 5.4 What a fire row shows

When sorted by WFIGS Distance:

```text
GOAT • WA
809 acres | 3% contained
15 mi north of Ronald
```

When sorted by Perimeter Distance:

```text
GOAT • WA
809 acres | 3% contained
6.2 mi from perimeter to Ronald
```

When sorted by Fire Size or Containment, keep the default WFIGS location display in the compact row.

Do not show both distances in the compact row. Both may appear in the selected-fire panel.

---

# 6. Optional Filters

Place filters above the fire list next to the sort control:

```text
SORT BY
[ WFIGS Distance ▼ ]

FILTERS
☐ 500+ acres
☐ Within 5 miles

Showing [visible count] of [current dashboard count] fires
```

Both filters are unchecked by default.

Therefore, opening the dashboard preserves the fires already surfaced by the current application. Filters only narrow the visible list temporarily.

## Filter behavior

### 500+ acres

When checked, show only fires with current size of at least 500 acres.

### Within 5 miles

The `Within 5 miles` filter always uses WFIGS Distance, regardless of the selected Sort By option.

- Include records with WFIGS Distance of 5 miles or less.
- Exclude records over 5 WFIGS miles.
- Missing WFIGS Distance values do not pass this filter.
- Do not use Perimeter Distance for this filter in the first implementation.

Perimeter Distance remains a separate optional sort and selected-fire-panel value.

### Both filters

When both are checked, a fire must satisfy both conditions.

Filtering does not record a decision, Ignore a fire, or alter the underlying queue.

Preserve sort and filter selections during the current application session and after saving a review.

If no fires match:

```text
No fires match the current view.
Adjust the filters to view additional fires.
```

---

# 7. Main Fire List

Each compact row should show:

- Fire name
- State
- Current size
- Numeric containment with its approved color treatment
- The distance selected in Sort By
- Associated place or WFIGS location description
- Current human disposition when one exists

Do not show:

- Evacuation warnings
- Structures Threatened
- Population warnings
- Hidden risk scores
- New flags

Selecting a row updates the selected fire, map, and details panel. It does not save a review decision.

If saving Ignore removes the selected fire from the main list:

1. Select the next visible fire.
2. Update the map and details together.
3. If no fire remains, show the empty state above.

---

# 8. Selected-Fire Panel

Use this order:

```text
[FIRE NAME]                                             [STATE]

[REVIEW STATE]
[Last human review when available]

[CHANGES SINCE LAST REVIEW when applicable]

FIRE
Current size
Containment
WFIGS location

EXPOSURE
Nearest population center
Distance from fire perimeter
Nearby ZIP areas

EVACUATION STATUS

[REVIEW RATIONALE when one exists]

REVIEW DECISION
[Ignore] [Monitor] [Create Moratorium]

[Open Details →]
```

Do not add a second Screening Factors block that duplicates size, containment, and distance. Put the screening meaning beneath the relevant fact when useful.

Example:

```text
Current size
809 acres
Meets 500-acre review threshold

Containment
3%
Under 40%

Distance from fire perimeter
6.0 miles
Outside main 5-mile review distance
```

## 8.1 Population

When verified population is available:

```text
Nearest population center
Lawtonka Acres (pop. 2,500)*

*2020 U.S. Census population.
```

When population is unavailable:

```text
Nearest population center
Lawtonka Acres
```

Do not show a separate Population row or missing-population badge.

## 8.2 Nearby ZIP areas

```text
Nearby ZIP areas
73015, 73062, 73507

Census ZIP Code Tabulation Areas within 5 miles of the
fire perimeter, sorted by distance.
```

These are not final bulletin ZIP codes.

## 8.3 Structures Threatened

Do not display Structures Threatened.

## 8.4 Evacuation Status

For now:

```text
EVACUATION STATUS
Unavailable
```

Do not show an evacuation warning at the top. Do not add evacuation entry or ingestion behavior in this build.

## 8.5 Open Details

Keep the existing:

```text
Open Details →
```

Opening details does not record a review.

---

# 9. Review States

Use only these states. Do not create additional flags or states.

## 9.1 Initial review

When no saved in-app Ignore or Monitor review exists:

```text
REVIEW REQUIRED
No reviewer has assessed this fire yet.
```

A fire without a saved Day 1 review has not yet been reviewed in the operational baseline.

## 9.2 Material change

Use only when the existing application logic resurfaces a previously reviewed fire:

```text
REVIEW REQUIRED
Material changes detected since the last review.

Last reviewed by [Reviewer] on [Date and time].
```

Show only supported comparisons against the newest saved in-app Ignore or Monitor review baseline.

Examples of supported comparisons:

```text
CHANGES SINCE LAST REVIEW
Size             450 → 914 acres
Containment       82% → 75%
```

Do not create or revise material-change thresholds.

## 9.3 Monitoring

When the last human disposition is Monitor:

```text
MONITORING
Last reviewed by [Reviewer] on [Date and time].
```

Keep the fire visible after later uploads and show supported changes from the last saved human review baseline.

If no comparable facts changed:

```text
No changes since the last review.
```

Uploading data does not advance the human review baseline.

## 9.4 Ignored

Ignored fires remain off the main dashboard unless existing material-change logic resurfaces them.

If opened through an existing secondary route:

```text
IGNORED
Last reviewed by [Reviewer] on [Date and time].
```

Do not build a new ignored-fire archive or special screen.

---

# 10. Review Decisions

Use only:

```text
Ignore
Monitor
Create Moratorium
```

Remove the old `Reviewed - No Action` control.

## 10.1 Ignore

Clicking Ignore opens the Review Fire form. It does not save immediately.

Saving Ignore:

- Records the reviewer and timestamp.
- Stores the compatible Ignore disposition.
- Stores optional Review Rationale.
- Stores the current evidence baseline.
- Optionally stores a map image when requested.
- Removes the fire from the main list unless existing change logic later resurfaces it.

## 10.2 Monitor

Clicking Monitor opens the same Review Fire form with Monitor selected.

Saving Monitor:

- Records the same review information.
- Sets the current facts as the new human review baseline.
- Keeps the fire visible after later uploads.

When reviewing a monitored fire again, the reviewer clicks Monitor again. Do not introduce Continue Monitoring, Acknowledge Changes, or Log Review.

Clicking Monitor again reopens the same Review Fire form and saves a new review baseline when submitted.

## 10.3 Create Moratorium

Clicking Create Moratorium opens the Moratorium Builder entry point with available selected-fire facts.

The click alone must not:

- Create a moratorium
- Save a bulletin
- Generate a PDF
- Change Ignore or Monitor

---

# 11. Review Fire Form

```text
REVIEW FIRE: MEERS

Disposition
(•) Ignore
( ) Monitor

Review Rationale
┌──────────────────────────────────────────────────────┐
│                                                      │
│                                                      │
│                                                      │
│                                                      │
│                                                      │
│                                                      │
│                                                      │
│                                                      │
└──────────────────────────────────────────────────────┘

☐ Save current map image with this review

SYSTEM SNAPSHOT AT REVIEW
914 acres | 75% contained
WFIGS location: 1 mile south of White Swan, WA
Nearest population center: Lawtonka Acres
Distance from fire perimeter: 8.7 miles
Nearby ZIP areas: 73015, 73062, 73507

[Cancel]                                      [Save Review]
```

## 11.1 Review Rationale

- Label exactly: **Review Rationale**
- Approximately eight visible lines
- Free text
- Optional for Ignore and Monitor
- Do not block saving when empty
- Preserve exact text and line breaks
- Do not auto-write or suggest rationale
- Attribute entered rationale to reviewer and timestamp
- Never overwrite an earlier rationale

Examples of human rationale, not application rules:

```text
Fire below threshold size.
```

```text
Containment over 80%.
```

```text
Containment low but natural barriers exist between the
perimeter and the population center.
```

```text
May need a moratorium if acreage continues to grow.
```

## 11.2 Optional map image

The checkbox label is exactly:

```text
Save current map image with this review
```

The checkbox is unchecked by default.

When selected:

- Save an actual image of the currently displayed app map.
- Associate it with that specific review-history entry.
- The image should contain the selected fire and visible map overlays shown to the reviewer.

When not selected:

- Save the review normally without a map image.
- Do not show a missing-map warning.

If map capture fails:

- Save the underlying review.
- Show: `Review saved. The map image could not be saved.`
- Do not create a blank or invalid image record.

Do not capture credentials, API keys, unrelated browser content, or anything outside the app's map view.

---

# 12. Review Record and History

Every saved Ignore or Monitor decision creates an append-only review entry.

Store at minimum:

```text
review ID
stable fire ID / IRWIN ID
fire name
reviewer
timestamp
disposition
Review Rationale
source CSV/snapshot identifier
saved map-image reference, if requested and successfully created
```

Store available evidence at review time:

```text
state
source system
acres
containment
WFIGS distance
WFIGS location description
nearest population-center name, if available
verified population and source year, if available
calculated perimeter distance, if available
nearby ZCTA candidates and distances, if available
perimeter/GeoJSON identifier and timestamp, if available
```

Missing historical evidence remains missing. Do not backfill what the reviewer saw.

## Review history display

Newest first:

```text
REVIEW HISTORY

September 11, 2026 at 10:42 AM
Justin • Monitor

May need a moratorium if acreage continues to grow.

[View saved map]
```

Show `View saved map` only when a valid map image exists for that review.

Opening the saved map must not overwrite the current map or current data.

---

# 13. Effects of Later Uploads

All comparisons use the latest saved in-app human review baseline, not merely the immediately preceding upload.

The operational baseline consists only of reviews saved within CAT Monitor. A fire without a saved in-app review has no operational baseline and shows Initial Review.

## Never reviewed

Show Review Required using existing queue behavior.

## Ignored

Keep off the main dashboard when existing change logic does not require renewed review.

If existing logic resurfaces it, show supported changes and the prior Review Rationale.

## Monitoring

Keep on the main dashboard after each upload.

Show supported changes from the last saved human review baseline.

The reviewer clicks Monitor again to record a new review baseline.

## Older or missing GeoJSON

Continue showing current CSV facts.

Use the latest available matching perimeter geometry when present and do not imply that it is as current as the CSV.

Do not interpret a missing perimeter update as reduced risk or closure.

## Archived Excel-derived reviews

Archived Excel-derived reviews are never used as a comparison baseline and are never displayed. A fire whose only record is archived Excel-derived data shows Initial Review.

## Earlier in-app reviews

For reviews saved inside CAT Monitor, compare only fields contained in that saved review baseline. Do not invent historical rationale, population, ZIP areas, perimeter distance, or map images.

---

# 14. Moratorium Builder Boundary

For this first implementation, Create Moratorium only needs to open or establish the builder entry point and pass the available selected-fire facts. Clicking it must not create, save, or generate anything.

The detailed builder behavior below documents the intended later workflow. It is not part of the first implementation unless the application already supports it.

Intended later builder behavior:

- Prefill fire name.
- Prefill available suggested ZIP candidates.
- Prefill standard boilerplate when supplied to the app.
- Suggest an expiration date 21 days after the effective date.
- Allow every field to be changed before preview.
- Preview without saving.
- Save and log only after user approval.
- Create the PDF only from saved, user-approved content.

Nearby ZCTAs are suggestions, not confirmed bulletin ZIP codes.

Do not decide whether saving a moratorium changes Ignore or Monitor. Keep an active moratorium record separate from the review disposition until that behavior is explicitly defined.

---

# 15. Items to Remove or Avoid

Do not show or add:

- Reviewed - No Action
- OK - No Action as the main header
- New Since Last Review for a never-reviewed fire
- Missing-population header badges
- Missing-evacuation header badges
- Structures Threatened
- Separate Population row
- Duplicate Screening Factors block
- Hidden risk or priority score
- Natural-barrier automation
- Evacuation entry or ingestion
- New flags or states
- Additional state rules
- Separate monitor acknowledgment buttons

Keep:

- Ignore
- Monitor
- Create Moratorium
- Open Details
- Review Required
- Monitoring
- Ignored when accessed outside the main list
- Review Rationale
- Optional Save current map image with this review

---

# 16. Save and Regression Safety

- Use stable widget and callback keys.
- Prevent duplicate review entries from Streamlit reruns.
- Do not change the visible disposition until persistence succeeds.
- Show a clear error if review persistence fails.
- Rerender from persisted data after save.
- Review history is append-only.
- Do not expose credentials.
- Keep dashboard CSS locally scoped.
- Preserve existing Fire Table and Fire Detail behavior except for agreed integration.
- Do not create a second data-ingestion path.
- Do not change spatial calculations solely for UI work.

---

# 17. Acceptance Tests

## Alaska

1. Load an AK fire.
2. Confirm the source record remains.
3. Confirm disposition is Ignore.
4. Confirm rationale is `No coverage in AK`.
5. Confirm it is absent from the main dashboard.

## Default dashboard

1. Confirm the existing non-Alaska dashboard population appears before optional filters are applied.
2. Confirm Alaska is the only approved exception to preserving the existing dashboard population.
3. Confirm both filters are unchecked.
4. Confirm WFIGS Distance is the default sort.

## Sort dropdown

1. Confirm choices are WFIGS Distance, Perimeter Distance, Fire Size, and Containment.
2. Confirm WFIGS and Perimeter distances are not combined.
3. Confirm Perimeter Distance missing values show Not verified and sort after verified values.
4. Confirm the compact row shows Perimeter Distance only when Perimeter Distance is selected.
5. Confirm the compact row keeps the WFIGS location display when Fire Size or Containment is selected.

## Filters

1. Confirm 500+ acres includes 500 and excludes 499.
2. Confirm Within 5 miles includes WFIGS Distance 5.0 and excludes WFIGS values above 5.
3. Confirm Within 5 miles always uses WFIGS Distance, regardless of the Sort By selection.
4. Confirm missing WFIGS Distance does not pass the filter.
5. Confirm both filters together require both conditions.
6. Confirm filtering records no disposition.
7. Confirm the visible count is shown.

## Containment

Confirm every boundary in Section 4.3 and confirm blank is neutral grey, not 0%.

## Initial review

Confirm Review Required wording and the four actions: Ignore, Monitor, Create Moratorium, and Open Details.

## Ignore

1. Click Ignore.
2. Confirm Review Fire opens before save.
3. Save with or without Review Rationale.
4. Confirm reviewer, timestamp, disposition, evidence baseline, and rationale if entered are appended.
5. Confirm the map image is saved only if requested and capture succeeds.
6. Confirm the fire leaves the main list.
7. Confirm the next visible fire or empty state appears.

## Monitor

1. Click Monitor.
2. Confirm the same Review Fire form opens.
3. Save with or without rationale.
4. Confirm the fire remains visible after later uploads.
5. Click Monitor again.
6. Confirm the same form reopens and a new baseline is saved.
7. Confirm no separate acknowledgment button exists.

## Optional map image

1. Save a review with the checkbox clear and confirm no map button or warning appears in history.
2. Save a review with the checkbox selected and confirm a valid image is associated with that review.
3. Simulate capture failure and confirm the review still saves with the specified message.
4. Confirm no blank image record is created.

## Day 1 clean baseline

1. Confirm the existing Excel-derived analyst-status data is retained in full as an archived backup and nothing is deleted.
2. Confirm the active review store is empty at Day 1 start.
3. Confirm no Excel-derived review, note, status, watermark, distance reference, or moratorium record appears in the dashboard, selected-fire panel, review state, review history, or change comparison.
4. Confirm every fire shows Initial Review before any in-app review is saved, including fires that have an archived Excel-derived record.
5. Confirm a saved in-app Ignore or Monitor review establishes the baseline, and that subsequent comparisons use it.
6. Confirm reviews saved in-app remain valid afterward and missing historical fields are not fabricated.

## Selected-fire panel

Confirm no separate Population row, no missing-data badges, no Structures Threatened, and Evacuation Status appears only as Unavailable.

## Save safety

Confirm failed persistence does not change the disposition, reruns do not duplicate entries, and history remains append-only.

---

# 18. Definition of Done

The first implementation is complete when:

- The existing non-Alaska dashboard population is preserved, with Alaska as the only approved exception.
- WFIGS Distance is the default sort in one clear dropdown.
- Perimeter Distance, Fire Size, and Containment are separate sort choices.
- The two optional filters are visible and unchecked by default; `Within 5 miles` uses WFIGS Distance only and both filters affect only the current view.
- The 500-acre breakpoint and containment bands work exactly as specified.
- Alaska is ignored and hidden as specified.
- The selected-fire panel is clear and does not repeat facts or promote missing data as warnings.
- Ignore and Monitor open the Review Fire form.
- Review Rationale is optional, large, and saved when entered.
- Map-image saving is optional and cannot block the review save.
- Monitor remains visible after later uploads.
- Ignore remains hidden unless existing change logic resurfaces it.
- The existing Excel-derived analyst-status data is retained as an archived backup, nothing is deleted, and none of it is active in the redesigned app.
- The active review store starts clean, and the Day 1 baseline is created solely by Sean and Justin's in-app Ignore and Monitor reviews.
- Create Moratorium opens an entry point without creating anything immediately.
- No new flags, scores, thresholds, unsupported data, or unrelated workflow have been introduced.

---

# Final Instruction to Claude Code

Implement only this handoff. Preserve existing behavior where this document does not explicitly authorize a change. If current code cannot support a requirement without changing screening thresholds, source interpretation, spatial logic, or in-app review data, identify that conflict rather than inventing a solution. Do not add a new rule, flag, field, score, state, workflow, or data source unless it is explicitly described here.

Archiving the existing Excel-derived analyst-status data and starting the active review store clean is explicitly authorized by *Locked Decision: Day 1 Fresh Baseline*, and is not a conflict. Deleting that data is never authorized.
