# Next task: screening vocabulary and flags from Justin's notes

## Goal

Make the dashboard's flags and parameters speak Justin's actual decision language instead of
generic ones, and add the two screening levers his notes prove he uses but the app lacks: the
**state book exclusion** and the **natural barrier**.

Derived from his 41 workbook notes (in `data/analyst_status.json`, prefixed
`[Justin workbook 9-8]`) and the Hiscox bulletin PDFs in the project root. Do not invent
flags — every one must trace to his wording or to source data.

### The vocabulary to implement

| Flag | Trigger (all deterministic) |
|---|---|
| `NO BOP IN <STATE>` | Fire's state is in the book-exclusion list. Seed the list with **AK** and **WA** (the two he states), editable by the analyst, attributed to his 9-8 notes. A fire in an excluded state must never reach the attention bucket. |
| `NATURAL BARRIER` | `analyst.ANALYST_FIELDS["barriers"]` is non-empty. Show his text verbatim (e.g. "Body of water separation"). Counts as a quieting reason, never an elevation. |
| `CONTAINED` / `NEARLY CONTAINED` | `pct_contained` ≥95 / ≥75. His most common dismissal. |
| `SMALL` | Acres below the 300 ac guideline. |
| `LOW POPULATION` | Nearest place population below `THRESHOLDS["population_min"]`. Must state the number, matching his `<place> ~<population>` format. **Blocked without a Census API key — see below.** |
| `NO STRUCTURES THREATENED` / `STRUCTURES THREATENED` | From the analyst `structures_evac` field only. Blank stays "not verified". |
| `MORATORIUM UNTIL <date>` | Replaces the current generic moratorium label, using his phrasing. |

Keep the existing evacuation and change flags; only relabel to his wording.

**Open decision, defaulted:** use Justin's wording (not normalised labels). He was asked and
did not answer, so proceed with his wording and flag it for confirmation — it is a
string-constant change if he disagrees.

### Blocker to raise first: no population data

There is no Census API key, so **every** place population is currently `None` (0 of 32
measured places have one). `LOW POPULATION` therefore cannot be implemented as specified.

Do this at the start of the task:

```bash
python -c "from geo import census; print(census.population_status())"
```

- If it reports no key: tell Sean a free key from
  https://api.census.gov/data/key_signup.html written to `data/census_api_key.txt` unblocks it,
  then re-run geography for the queue. Until then, implement `LOW POPULATION` so it renders
  `POPULATION NOT VERIFIED` rather than treating unknown population as low. **Do not infer
  population from acreage, place name, or anything else.**
- If a key is present: implement the flag fully and state the number.

Everything else in this task works without the key.

## Files and functions likely involved

- `attention.py`
  - `THRESHOLDS` — add `excluded_states` handling and a population floor for `LOW POPULATION`
  - `assess()` — add the state-exclusion short-circuit before any elevation logic; add the
    barrier quieting reason
  - `_FLAG_LABELS` / `_flags()` — relabel to his vocabulary, add the new flags
  - `describe()` — keep it truthful about the new rules
- `analyst.py` — additive only: where the editable excluded-state list is stored (a module
  constant plus an analyst-editable override is fine; do not restructure the record schema)
- `dashboard.py` — `_right()` flag rendering and `_fire_rows()` evidence line, so a barrier or
  excluded state reads clearly
- `app.py` — `_dashboard_secondary()` "Rules" tab caption picks up `attention.describe()`
  automatically; check nothing else needs touching

## Must stay untouched

- `geo/` — the spatial engine. No changes to distance or ZIP calculation.
- `maps.py`, `app.py:page_detail()`, `app.py:page_table()`.
- `wfigs.py`, `snapshots.py`, `baseline.py` seeding behaviour, and the existing review
  watermarks in `data/analyst_status.json` (209 of them — do not re-seed or overwrite).
- `urgency.py` / `screening.py` thresholds — the Fire Table and rule-recommendation queue
  depend on them.
- Dashboard CSS scoping; no global theme.

## Acceptance criteria

1. Mukluk (AK) and Sinlahekin (WA) show `NO BOP IN AK` / `NO BOP IN WA`. Both are already
   quiet today (bucket `reviewed`), so the real test is that they **cannot** be pulled into
   attention: temporarily drop `excluded_states`, confirm Sinlahekin (166,021 ac) surfaces,
   restore the list, confirm it goes quiet again with the flag.
2. The excluded-state list is visible and editable in the app, not hard-coded out of reach.
3. A fire with text in `barriers` shows `NATURAL BARRIER` with that text; it lowers relevance
   and never raises it. No record currently populates `barriers`, so test by adding text to
   one fire via Fire Detail, or by passing a stub record to `attention.assess()` directly.
4. Flag labels read in Justin's wording. `LOW POPULATION` shows the actual population number
   if a Census key is present, or `POPULATION NOT VERIFIED` if not — never an inferred value.
5. Regression, unchanged from today's baseline: buckets stay
   **1 attention / 1 monitoring / 177 reviewed / 22 background**. MEERS (914 ac, OK, no
   geography) is the one attention item, provisional. Miners (147 ac) and Skull (68 ac) stay
   quiet. Timber (CA) stays in Currently Monitoring.
6. `attention.describe()` accurately states every rule now in force.
7. Fire Detail and Fire Table render exactly as before, in their original light styling.

## How to test

**Deterministic, no browser** — buckets and evidence straight from the engine:

```bash
python -c "
from datetime import date
import pandas as pd, snapshots, analyst, attention
from geo import analysis
cur, pri = '2026-09-10_120600', '2026-09-10_090007'
c,_ = snapshots.load_snapshot(cur); p,_ = snapshots.load_snapshot(pri)
merged,_ = snapshots.compare(c, p); recs = analyst.load()
spc = {i: analysis.load(cur,i) for i in analysis.list_calculated(cur)}
spp = {i: analysis.load(pri,i) for i in analysis.list_calculated(pri)}
rows = []
for _, r in merged.iterrows():
    rec = analyst.get(recs, r['irwin_id'], r['fire_name'])
    sp = spc.get(r['irwin_id'])
    gch = analysis.compare(sp, spp.get(r['irwin_id'])) if sp and spp.get(r['irwin_id']) else {}
    a = attention.assess(r, sp, gch, rec, today=date(2026,9,10))
    rows.append(dict(fire=r['fire_name'], state=r['state'], acres=r['acres'],
                     bucket=a['bucket'], flags=','.join(f['label'] for f in a['flags']),
                     why=' | '.join(a['reasons'][:2])))
d = pd.DataFrame(rows)
print(d.bucket.value_counts().to_dict())
print(d[d.bucket=='attention'].to_string(index=False))
for n in ['Mukluk','Sinlahekin','Miners','Skull','MEERS','Timber']:
    q = d[d.fire.str.lower()==n.lower()]
    if not q.empty: print(n, '->', q.iloc[0].bucket, '|', q.iloc[0].flags)
"
```

**In the app** — restart the server (Streamlit does not reliably reload imported modules):

```bash
python -m streamlit run app.py
```

Then: confirm the three counts; select a fire and check its flags read in Justin's wording;
switch to Fire Table and Fire Detail and confirm they are unchanged and still light-styled.
