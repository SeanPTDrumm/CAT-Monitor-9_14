# CAT Monitor Windows local build — audit

Build date: 2026-09-15. Target: Windows x64, CPython 3.12. Tested on Sean's Windows computer, Python **3.12.14**, Streamlit **1.63.0**, with a fresh isolated virtual environment.

## Result

**PASS for the local packaging checks listed below.** The application installed from the included offline wheels, ran through the supplied Windows launcher, served localhost, rendered in a browser, and passed empty/populated Streamlit tests. This certifies the tested package behavior, not the work computer's permissions or every live external data service.

No Census dataset, API key, prior operational snapshot, or prior review record is shipped. The package contains ordinary source plus offline dependency wheels; **Python itself is a prerequisite, not bundled**.

## Source frozen before modification

- Repository: `https://github.com/SeanPTDrumm/CAT-Monitor-9_14.git`
- Branch: `main`
- Commit: `c9b51e8cccaacaf2b26bef789f82aaa6ceabf70b`
- Remote main was checked live and a new clean clone was made. The older local checkout had uncommitted maps.py changes; it was not used as the package base.
- `provenance/source-snapshot.zip` is the unmodified Git archive of that commit.
- `source-files.json` records SHA-256 for every tracked source file; branch, commit, repository, clean status, and freeze time are separate files.
- `packaging.patch` records the app changes; `package-files.json` records delivered file hashes, excluding its own recursive hash. `folder-tree.txt` lists the complete shipping tree.
- No commit or push was made to the remote repository.

## Changes made for packaging

Added one shared path module; redirected snapshots, geography results/cache, reviews, review maps, legacy analyst status, reference workbooks, ZIP master, key configuration, and staged imports outside app code. Added minimal missing-reference captions and corrected displayed path text. Added setup, launcher, pinned requirements, dependency wheels, documentation, and repeatable checks. Dashboard styling, fire screening, review decisions, and map logic were preserved.

## Evidence and checks

| Requested check | Result and evidence |
|---|---|
| Complete folder tree inspected | PASS. Every shipping file listed in `provenance/folder-tree.txt`; no `.venv`, `__pycache__`, API key, or real runtime records included. Data folders contain text placeholders only. |
| Syntax-check every Python file | PASS. **26 files** compiled, including entrypoint, all app modules and all three package scripts. See `automated-checks.json` and `final-checks.log`. |
| All imports resolve | PASS. **52 static import targets**, every non-entry app module, and all nine original direct dependency imports loaded; entrypoint executed by AppTest and live Streamlit. Native geospatial dependencies imported successfully. |
| Requirements complete | PASS. **45 exact pinned versions** checked against the installed environment. `pip check`: **No broken requirements found**. All original direct dependencies retained. |
| Launcher app path | PASS. Actual CMD launcher executed from a different working directory; it launched package `app/app.py`, with loopback binding and port 8501. See launcher process/log evidence. |
| Setup virtual environment | PASS. Actual Setup.cmd created `.venv` in a fresh folder containing spaces and installed all dependencies with `--no-index --find-links=wheelhouse`. `include-system-site-packages=false`; interpreter and Streamlit module paths verified under that `.venv`. Explicit `CAT_MONITOR_PYTHON` branch was used. Existing-venv rerun also passed. |
| Local Streamlit test | PASS. AppTest empty startup and real-data dashboard both completed without exceptions. Then the actual launcher started the HTTP server. |
| Opens on localhost | PASS. `http://localhost:8501/` returned **200**; `/_stcore/health` returned **200 / ok**. Browser rendered **Catastrophe Monitor**, the empty-state upload controls and both missing-reference captions. Listener verified on **127.0.0.1:8501**. |
| Writable persistent operational paths | PASS. All **9 writable folder targets** tested. Shared snapshot paths verified between ingestion and geography. Review saved and reloaded in a new AppTest session. Code replacement plus new-process initialization preserved **20 data-file SHA-256 hashes**. See `persistence-check.json`. |
| Missing Census/reference files | PASS. No ZIP master, baseline workbook, local Census dataset or real key supplied. Missing references returned empty/unverified values without crashing; browser captions gave expected paths. Simulated Census API failure returned unverified values; simulated blocked TIGERweb produced and persisted an explicit unavailable result. |
| Real populated workflow | PASS. Imported actual previous WFIGS raw.csv and matching perimeter GeoJSON into isolated test storage; dashboard loaded; **Mark Reviewed** saved; a new session retained it; identical import was rejected without replacing the snapshot. Input CSV SHA-256: `092047c39786ccf29d25aa22411878fe76a5b3816b8104de905d96bd470d49bb`. Test records are excluded from the ZIP. |
| Review map storage | PASS. Existing map builder serialized an actual perimeter into non-empty HTML in the separate review_maps folder, and initialization preserved it. Census feature lists were explicitly empty for this isolated serialization test; no population counts or Census polygons were synthesized. This was a serializer/storage test, not certification of live map tiles. |
| ZIP contents and integrity | Final packaging process reopens the ZIP, checks CRCs and every manifest hash, verifies source snapshot hashes, and syntax-checks Python bytes from the archive. External audit copy includes the resulting ZIP SHA-256 and final verification result. |

Evidence files live in `provenance/`. The self-test script uses temporary storage and supports optional real WFIGS fixture paths. Full build checks ran using the freshly installed verification environment, not just the original developer environment.

The final populated browser view was also inspected: 176 fires displayed, Camp Creek selected, and review controls visible. Missing-reference messages were verified under **UPDATE DATA → Advanced / Admin**. `browser-observations.txt` records this check.

## Failures, warnings, and test boundaries

- **No unresolved failure in the required local packaging checks.** Initial Streamlit skill discovery ran before pip finished and reported that Streamlit was not installed; repeating after installation succeeded. This was an installation timing issue.
- An intermediate placement of missing-reference captions opened a sidebar and narrowed the dashboard. Browser QA caught this; captions were moved into existing data controls. The final full-width layout was inspected and all automated checks rerun successfully.
- Existing Streamlit `use_container_width` deprecation messages and AppTest's missing-script-context/cache warnings occurred. They did not prevent tests or browser rendering. Existing UI code was preserved rather than redesigned during packaging.
- Browser content-export tooling was unavailable; browser state and screenshot were inspected directly, and observations are recorded in this report rather than claiming a saved screenshot artifact.
- **Live keyed Census population retrieval was not tested.** No real key was copied into the build. The upstream active ZCTA query still uses `2020/dec/pl`; it may leave ZCTA populations unverified. Packaging does not certify that lookup. Place API support and existing failure handling remain intact.
- `reference/census/` is a reserved future-data directory. There is no bulk local Census loader in the starting product; arbitrary files dropped there are not automatically consumed. No Census data was invented to fill this gap.
- Fresh setup was tested with the documented explicit-interpreter option. This host's registered `py` launcher has Python 3.13, not 3.12; the default `py -3.12` installation branch was not exercised successfully here. On the work computer, install/register Python 3.12 or use `CAT_MONITOR_PYTHON` as documented.
- Runtime Census/NIFC requests and map tiles depend on internet access. Offline wheel installation does not make live-data retrieval or external map assets offline. Work-network proxy/firewall behavior remains untested.
- The browser opening at localhost was verified by direct navigation after launching. Automatic opening of a default browser on the work computer is not guaranteed; manually entering the address is supported.
- Old operational-data migration, multi-user concurrent writes, every secondary export, and work-computer deployment were not tested. Use one instance per data folder. Review-map HTML storage was tested; full offline replay of external map tiles was not.

## Remaining work on the work computer

1. Install or obtain IT-provided **64-bit Python 3.12**.
2. Extract the ZIP to a permanent writable folder; run **Setup.cmd**, then **Launch CAT Monitor.cmd**.
3. Supply official WFIGS CSV/perimeters; optionally supply a genuine ZIP master and Census API key. Reference folders are intentionally empty.
4. Verify the work network permits needed live sources/maps. Keep unavailable population as **Not verified**.
5. Back up the persistent `data` folder; preserve it during updates using the README instructions. Migrate older real records only if needed, with a backup first.

Do not treat the successful local build as evidence that live Census results or work-network access have already been validated.
