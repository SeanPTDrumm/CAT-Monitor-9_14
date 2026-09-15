"""Persistent paths, independent of current directory and app updates."""
import os
from pathlib import Path
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.environ.get("CAT_MONITOR_DATA_DIR", str(PACKAGE_ROOT / "data"))).expanduser().resolve()
REFERENCE_DIR = DATA_ROOT / "reference"
CENSUS_DIR = REFERENCE_DIR / "census"
BASELINE_DIR = REFERENCE_DIR / "baseline"
SNAP_DIR = DATA_ROOT / "operational_snapshots"
REVIEW_DIR = DATA_ROOT / "review_history"
MAP_DIR = DATA_ROOT / "review_maps"
LOG_DIR = DATA_ROOT / "logs"
CACHE_DIR = DATA_ROOT / "cache"
IMPORT_DIR = DATA_ROOT / "imports"
CONFIG_DIR = DATA_ROOT / "config"
DIRECTORIES = (CENSUS_DIR, BASELINE_DIR, SNAP_DIR, REVIEW_DIR, MAP_DIR, LOG_DIR, CACHE_DIR, IMPORT_DIR, CONFIG_DIR)
def ensure_directories():
    for folder in DIRECTORIES:
        folder.mkdir(parents=True, exist_ok=True)
