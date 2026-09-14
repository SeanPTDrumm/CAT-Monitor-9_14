"""
ZIP master lookup (ZIP -> city, state, county), from the internal ZIP master
sheet in Justin's "Southern Coastal County Zips (10-2024)" workbook, exported
to data/geography/zip_master.csv.

Used for: naming a ZCTA by its post-office community ("93920 Big Sur"),
validating ZIPs typed into bulletins, and ZIP -> county for tropical work.
This is an internal reference table dated 10-2024; it is not Census data.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ZIP_MASTER = BASE_DIR / "data" / "geography" / "zip_master.csv"
SOURCE_NAME = "Hiscox ZIP master (Southern Coastal County Zips workbook, 10-2024)"


@lru_cache(maxsize=1)
def _table() -> dict[str, dict[str, str]]:
    if not ZIP_MASTER.exists():
        return {}
    with open(ZIP_MASTER, newline="", encoding="utf-8") as fh:
        return {r["zip"]: r for r in csv.DictReader(fh)}


def available() -> bool:
    return bool(_table())


def lookup(zip_code: str | None) -> dict[str, str] | None:
    if not zip_code:
        return None
    return _table().get(str(zip_code).strip().zfill(5))


def label(zip_code: str) -> str:
    """'93920 (Big Sur, CA)' or just the code if unknown."""
    r = lookup(zip_code)
    return f"{zip_code} ({r['city']}, {r['state']})" if r else str(zip_code)


def is_valid(zip_code: str) -> bool:
    return lookup(zip_code) is not None


def zips_in_county(state: str, county: str) -> list[str]:
    s, c = state.strip().upper(), county.strip().lower()
    return sorted(z for z, r in _table().items() if r["state"].upper() == s and r["county"].lower() == c)
