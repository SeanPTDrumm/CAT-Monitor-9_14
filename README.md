# CAT Monitor — Windows local build

If Claude previously ran this app on the same work computer, its Python installation may be reusable, but this build specifically requires 64-bit Python 3.12. Setup will check that requirement.

Frozen source: `SeanPTDrumm/CAT-Monitor-9_14`, branch `main`, commit `c9b51e8cccaacaf2b26bef789f82aaa6ceabf70b`.

The existing CAT Monitor dashboard and review workflow run on your computer. No Streamlit Cloud account, deployment, or hosting is required. This is a local Python application, not a standalone EXE: **64-bit Python 3.12 is required**. This condensed ZIP excludes dependency wheels. Setup downloads the 45 pinned packages and their dependencies from PyPI; internet access to pypi.org and files.pythonhosted.org is required. Live geography and map backgrounds still need internet access.

## First-time setup

1. Have 64-bit Python 3.12 installed with its Windows `py` launcher. If your employer manages software, ask IT to install it. This ZIP does not install Python or bypass computer policy.
2. Right-click the ZIP → **Extract All**. Put the resulting `CAT-Monitor` folder in a permanent, writable local location, for example `C:\Users\YOURNAME\Documents\CAT-Monitor`. Do not run inside the ZIP, Program Files, or a read-only folder. Allow about 2 GB free for extraction and the virtual environment.
3. Double-click **Setup.cmd**. Wait for **Setup complete**. It creates `.venv` inside this folder and installs the pinned requirements from PyPI into that environment. It then checks dependency compatibility and tests write access to each data folder. No administrator rights are requested.
4. Double-click **Launch CAT Monitor.cmd**. Keep its console window open. The browser should open at **http://localhost:8501**; if it does not, enter that address yourself.
5. In the app's existing data controls, upload an official WFIGS CSV and its matching perimeter GeoJSON, then save the snapshot. An empty dashboard before the first import is expected. See `DATA_GUIDE.md` for optional references and API configuration.

If Python has no `py` launcher, open Command Prompt in this folder and run:

```bat
set "CAT_MONITOR_PYTHON=C:\full\path\to\python.exe"
Setup.cmd
```

That executable must be 64-bit Python 3.12. If setup fails, keep the error text; do not assume installation finished. Rerunning Setup.cmd reuses `.venv` and preserves data. If you move the package after setup, rename `.venv` to `.venv-old` and rerun setup at the new location; virtual environments are not portable.

## Daily use

1. Double-click **Launch CAT Monitor.cmd**.
2. Open http://localhost:8501 if needed. Import new official files using the existing workflow, select the snapshot, review fires, and save decisions with **Mark Reviewed** or **Log Review**.
3. Use the geography refresh controls when needed. Missing population stays **Not verified**; it is not zero. Live services and background maps may be blocked by a work network.
4. To stop, focus the launcher console and press **Ctrl+C**. Closing the browser alone does not stop Streamlit.

Run only one local instance per data folder. If port 8501 is already occupied, stop the earlier CAT Monitor console first. Startup failures are written under `data/logs/streamlit-*.log`.

## Folder structure

```text
CAT-Monitor/
  app/                         Replaceable application code, assets, original docs
  data/
    reference/census/          Reserved for genuine future Census reference files
    reference/baseline/        Optional baseline workbooks
    operational_snapshots/     Imported CSVs, perimeters, metadata, spatial results
    review_history/            Saved in-app reviews and separate legacy analyst store
    review_maps/               Saved HTML review maps
    logs/                      Timestamped local server logs
    cache/                     API population cache
    imports/                   Optional staging for CSV/GeoJSON imports
    config/                    Optional local Census API key
  scripts/                     Initialization, launcher, repeatable build checks
  provenance/                  Source ZIP, hashes, patch, tree, test evidence
  .venv/                       Created on THIS computer by setup; not shipped
  Setup.cmd
  Launch CAT Monitor.cmd
  requirements.txt            Exact dependency versions
  DATA_GUIDE.md
  BUILD_AUDIT.md
```

## Updates and backups — preserve your work

Stop the app and back up the entire `data` folder before updating. Extract a new build into a separate staging folder. Copy only `app`, `scripts`, `.streamlit/config.toml`, the root CMD scripts, `requirements.txt`, and documentation/provenance into your existing installation; then rerun Setup.cmd. **Do not replace or delete your existing `data` folder, and do not replace it with the new build's empty placeholders.** Updating only app code cannot overwrite sibling data paths. Do not copy an old `app` directory over this build: the local path changes are necessary.

For a separate data location, set a persistent Windows user environment variable `CAT_MONITOR_DATA_DIR` to an **absolute** writable directory before setup/launch. Keep it unchanged across updates. All data subfolders then live there. The app resolves paths independently of the launcher's working directory.

Prior local records are not automatically migrated. To migrate, with both apps stopped and a backup made, copy old `data/snapshots` contents to `data/operational_snapshots`; old `data/reviews.json` and `data/analyst_status.json` to `data/review_history`; old `data/review_maps` contents to `data/review_maps`; old `data/geography/population_cache.json` to `data/cache`; old `data/geography/zip_master.csv` to `data/reference`; and any approved baseline workbooks to `data/reference/baseline`. Do not merge two reviews.json files by overwriting one. No previous test reviews are included in this ZIP.

## GitHub and developer use

This windows-local branch publishes the condensed local package; main is unchanged. On the work computer select windows-local, choose Code > Download ZIP, extract it to a permanent writable folder, and run Setup.cmd. Track source, scripts, requirements and documentation. Root `.gitignore` excludes local data, secrets and virtual environments. The wheelhouse is already omitted from this condensed package.

Run from the package root after setup:

```bat
.venv\Scripts\python.exe -m streamlit run app\app.py --server.address=127.0.0.1
.venv\Scripts\python.exe scripts\check_build.py
```

The repeatable check uses temporary test storage; the optional real-file populated test requires `CAT_MONITOR_AUDIT_CSV` and `CAT_MONITOR_AUDIT_GEOJSON`. It does not alter your reviews. The original source docs inside `app` describe the upstream version and may mention old paths; this README and DATA_GUIDE govern this local package.

## What this build does not certify

Read `BUILD_AUDIT.md` for evidence. Testing on this Windows machine does not prove that a work computer's policy permits Python or that its network permits Census/NIFC/map services. No live keyed Census population result is certified by this build. The inherited active ZCTA population query uses the PL endpoint; ZCTA population may remain unverified. `data/reference/census` is a reserved location, not an implemented bulk-Census importer. Saved review maps are HTML with external map assets, not fully offline screenshots.
