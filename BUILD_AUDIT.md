# Condensed CAT Monitor — build audit

## Result

PASS: condensed packaging and fresh-environment setup checks. This build removes the bundled dependency wheels; app Python files are byte-identical to the previously tested local build from frozen source commit c9b51e8cccaacaf2b26bef789f82aaa6ceabf70b.

## Changes

- Removed wheelhouse (approximately 121 MB uncompressed).
- Setup.cmd now installs pinned requirements using https://pypi.org/simple.
- Updated README and data guide to explain online setup.
- Preserved source snapshot, persistent data-folder layout, launcher, requirements, and prior test evidence.

## Tests actually performed for this condensed build

- Executed the revised Setup.cmd in a fresh .venv with 64-bit Python 3.12.14, using the documented CAT_MONITOR_PYTHON option. Installation completed; pip check reported no broken requirements; all nine data-folder write checks passed.
- Pip used its local download cache during this test. The PyPI configuration was exercised, but this is not a cold-download test and does not establish work-network access.
- Reran scripts/check_build.py in that fresh environment: all 26 Python files compile, static imports and original direct dependencies import, all 45 pinned versions match, persistent directories are writable, missing references/key and simulated API failures are handled, and the empty Streamlit app renders with no exceptions.
- Compared every app Python file with the earlier tested build: no app changes.
- Inspected the shipping tree and excluded .venv, caches and runtime records. Reopened the final ZIP, checked CRCs and each package-manifest hash, and checked size is below 25,000,000 bytes.
- The earlier build's actual localhost browser launch, real WFIGS import/review workflow, map serialization and code-update persistence tests remain applicable to the unchanged app and launcher. Those tests were not repeated for this dependency-packaging-only change. See provenance/ORIGINAL_FULL_BUILD_AUDIT.md and the retained evidence.

## Limitations and remaining steps

1. The work computer still needs 64-bit Python 3.12. Previous localhost use suggests Python may exist, but its version is not confirmed. No Python runtime is bundled.
2. Extract the ZIP to a writable permanent folder and double-click Setup.cmd, then Launch CAT Monitor.cmd. Setup needs access to pypi.org and files.pythonhosted.org. If it fails, retain the displayed error.
3. Supply official WFIGS files and optional real ZIP reference/API key. No Census datasets or operational records are bundled.
4. The inherited ZCTA population limitation and unverified live keyed Census retrieval remain unchanged. This condensed build does not fix or certify Census population retrieval.
5. Preserve and back up data during updates. Dependencies still consume disk space after setup; only the transfer ZIP is smaller.

The original full-build audit describes its offline wheelhouse variant. This report and the root README govern the condensed variant. Updated package-files.json and folder-tree.txt describe this ZIP, not the older full build.

## GitHub branch publication

Published as windows-local, separately from main. App and launcher code are unchanged from the condensed package. README now includes GitHub download instructions. .gitattributes preserves package file bytes in Git archives; the package manifest and tree were regenerated for this branch. Earlier evidence records the tested builds and their original source commit.
