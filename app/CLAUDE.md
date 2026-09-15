# Catastrophe Monitor — Claude Code Project Instructions

## Purpose

Build and refine a local Streamlit application called **Catastrophe Monitor** for commercial BOP underwriting.

The app is intended to reduce the manual time required to monitor catastrophic events while preserving human underwriting judgment, source transparency, and a clear audit trail.

The first hazard is **U.S. wildfire**. Tropical weather can be added later.

---

## Important: Preserve Working Backend Logic

The application already has significant data ingestion, mapping, and historical-log functionality.

Do **not** refactor, replace, or redesign working backend systems unless a change is genuinely required to support the agreed user experience.

The current problem is primarily:

- too much information on the main screen,
- weak prioritization,
- poor visual hierarchy,
- too many visible controls,
- an unattractive and confusing UI,
- uncertainty about whether map/geospatial processing is working.

The goal is **simplification**, not another large redesign.

---

## Justin's Baseline Is the Authoritative Starting State

Justin's existing wildfire workbook/log is **not merely a formatting example**.

It represents the current analyst-reviewed state of the wildfire universe as of the latest completed review.

Treat it as the application's starting memory/state.

This means:

- Fires Justin marked **Monitor** should begin in Monitor status.
- Fires he reviewed and dismissed should remain dismissed unless new data materially changes the situation.
- Existing notes and prior analyst conclusions should persist.
- Existing moratorium information should persist.
- Relevant prior geographic conclusions should persist.
- New uploaded data should be evaluated **against Justin's prior reviewed state**, not treated as a fresh national review every time.
- Previously dismissed fires should not clutter the dashboard merely because they still exist in the national dataset.
- A dismissed fire should become prominent again only when something material changes.

The application should continue Justin's work from the last review rather than restart it.

---

## Current Refresh Model

For now, do **not** assume the app automatically downloads WFIGS/NIFC data.

The user uploads the newest official data files.

Uploading new data triggers a new catastrophe review.

At the top of the dashboard show:

- **Developments as of:** timestamp/date represented by the newest uploaded data
- **Previous review/log:** timestamp of the last saved analyst review

When new data is uploaded:

1. ingest the new official data,
2. compare it with the previous logged state,
3. update monitored fires,
4. identify new or materially changed fires,
5. surface only those items that require attention.

---

## Wildfire Screening Logic

Do not use a fixed "Top 5" concept.

Use a dynamic **Fires Requiring Attention** queue.

The number of fires shown should be based on relevance.

### General screening concern

A fire is normally more relevant when it is:

- approximately **300+ acres**, and
- within about **5 miles of a populated area / relevant ZIP geography**.

These are screening guidelines, **not rigid exclusion rules**.

### Factors that may downgrade relevance

- high containment,
- small or stable acreage,
- substantial distance from populated areas,
- prior analyst review concluding that geography/barriers materially reduce concern,
- no material change since the last review.

### Factors that may elevate relevance

- evacuation orders,
- rapid acreage growth,
- major perimeter movement,
- movement toward populated areas,
- structures threatened,
- new ZIP areas entering concern range,
- an existing moratorium,
- a moratorium approaching expiration,
- meaningful deterioration since the previous review.

Do **not** invent an opaque numerical risk score.

Show the evidence that caused a fire to rise or fall in relevance.

---

## Critical Definition: Distance

Whenever the application displays a fire's distance to a population center or ZIP area, the distance should mean distance from the **actual current fire perimeter**, not the incident origin point.

If perimeter-based distance is not available, display **Not verified** rather than substituting the incident-point distance without explanation.

---

## Dashboard Purpose

The first screen should answer:

1. **What changed since my last review?**
2. **What fires am I already monitoring, and how have they changed?**
3. **Is there anything new that deserves my attention?**

The dashboard should **not** display everything the system knows.

Use progressive disclosure:

- answer first,
- supporting evidence second,
- raw/source detail only when the analyst drills in.

---

## Agreed Dashboard Layout

### Header

Show:

- **Catastrophe Monitor**
- **Developments as of**
- **Previous review**

Keep the header clean.

### Three summary states only

Use only three compact summary cards:

1. **Requiring Attention**
2. **Currently Monitoring**
3. **Previously Reviewed / No Material Change**

Do not add additional KPI cards unless specifically requested later.

### Main working area

The main work area should contain:

- a compact list of **Changed / New Since Last Review**,
- a compact list/tab of **Currently Monitoring**,
- the **Hiscox Map** as the central visual,
- a compact selected-fire quick-facts panel.

The Hiscox Map means the map already built in this project showing wildfire perimeter and ZIP geography.

The map should be the visual center of the experience.

---

## Fire Selection Behavior

Use a two-stage interaction.

### First click / selection

Selecting a fire should **not immediately navigate away**.

Instead:

- highlight the selected fire in the list,
- load the fire on the Hiscox Map,
- zoom appropriately,
- display the current perimeter,
- display relevant ZIP geography,
- show the most important flags,
- show a concise quick-facts panel.

### Important flags

Surface clear, prominent indicators such as:

- **EVACUATION ORDERS IN EFFECT**
- **NO EVACUATION ORDERS FOUND**
- **EVACUATION STATUS NOT VERIFIED**
- **SIGNIFICANT SIZE INCREASE**
- **NEW PERIMETER MOVEMENT**
- **NEW POPULATED AREA / ZIP THREAT**
- **EXISTING MORATORIUM**
- **MORATORIUM EXPIRING SOON**

Do not show every available flag at all times. Only show the flags relevant to the selected fire.

### Selected-fire quick facts

Show only the core underwriting facts:

- current acreage,
- acreage change since previous review,
- containment,
- containment change,
- nearest relevant population center,
- population,
- distance from current perimeter,
- relevant/threatened ZIPs,
- structures threatened if available,
- evacuation status,
- current analyst disposition.

This should be enough to determine whether deeper review is needed.

---

## Fire Detail View

If the user clicks **View Detailed Review** (or intentionally drills deeper), open a dedicated incident view.

The detail view should narrow entirely to the selected fire.

Include:

1. **Verified Facts**
2. **Change Since Prior Snapshot**
3. **Geographic / ZIP Analysis**
4. **Evacuation / Structure Information**
5. **Moratorium Information**
6. **Prior Analyst Conclusions**
7. **Free-Text Notes**
8. **Saved Historical Map Views** when supported
9. **Sources / Verification**
10. **Underwriting Interpretation**

### Moratorium fields

If a moratorium exists, surface:

- status,
- effective date,
- expiration date,
- relevant ZIPs,
- whether it is expiring soon.

Do not create or remove a moratorium automatically.

---

## Map Loading Behavior

The app must make processing state obvious.

When loading perimeter or ZIP geography, show:

**Loading fire perimeter and ZIP geography…**

Use a spinner or progress state if practical.

During loading:

- prevent accidental interaction that would interrupt the process where practical,
- avoid silently leaving an old map in place.

On success:

- clearly show that the map updated.

On failure:

- show an explicit error.

The user should never have to wonder whether the app is working or broken.

---

## Visual Design

The app should feel like a **premium internal underwriting product**.

The current preferred direction is:

- dark navy / charcoal theme,
- restrained color,
- strong spacing,
- clear hierarchy,
- calm, modern, high-contrast presentation,
- central map,
- compact fire lists,
- clear alert badges,
- minimal visible controls.

Avoid:

- giant raw-data tables,
- excessive cards,
- excessive buttons,
- debug information,
- giant walls of text,
- chart clutter,
- exposing every available field,
- developer-tool appearance.

Think:

**executive underwriting catastrophe monitor**

not:

**generic Streamlit/data-science dashboard**

---

## Reliability Rules

This application concerns real catastrophic events and underwriting decisions.

Always follow these rules:

- Never fabricate fire statistics.
- Never fabricate ZIPs.
- Never fabricate population.
- Never fabricate structure counts.
- Never fabricate evacuation status.
- Never fabricate distances.
- Never fabricate source citations.
- If a value cannot be verified, display **Not verified**.
- Clearly separate source facts from deterministic calculations and analyst interpretation.
- Preserve source names, source URLs/services, and timestamps where available.
- Do not visually guess geography with an LLM.
- Do not automatically make final underwriting or moratorium decisions.

Justin / the human analyst remains the final decision-maker.

---

## Future Enhancements

Do not prioritize these until the wildfire dashboard is stable.

### Tropical weather

Later add:

- Atlantic,
- Eastern Pacific,
- Central Pacific / Hawaii,
- National Hurricane Center 5–7 day outlook,
- active systems,
- day-over-day track/cone changes,
- catastrophe relevance,
- ZIP/exposure geography when appropriate.

### Internal exposure layer

Only if permitted by company policy, the app may later support a separate internal layer for insured building locations.

Keep internal exposure data logically separated from public catastrophe data.

---

## Development Behavior

When working on this project:

- inspect current files before changing them,
- preserve working logic,
- prefer the smallest useful change,
- do not rewrite unrelated parts of the app,
- explain any new dependency before installing it,
- keep the app usable by a non-developer,
- optimize for clarity and underwriting usefulness,
- do not over-engineer.
