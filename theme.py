"""
Hiscox visual system tokens for the CAT Monitor dashboard.

Single source of palette truth, imported by `dashboard.py` (CSS) and
`dashboard_map.py` (pydeck layer colours), so the interface and the map cannot
drift apart.

Provenance - every value here is either taken from an approved Hiscox artifact
already in this project or is a neutral chosen to sit with them. Nothing is a
guess at a brand colour:

  RED     #CF241E  weighted centroid of the 23,200 red pixels in the logo
                   embedded identically in all seven "Internal - Hiscox USA
                   Bulletin" PDFs in the project root.
  BLACK   #000000  the bulletins' own letterhead band, and the logo asset's
                   background, so `assets/hiscox-logo.png` composites onto the
                   header with no visible tile edge.
  BORDER  #55564E  the warm neutral grey present in every bulletin.

Deliberately NOT defined here:
  * Containment colours. They live in `dashboard.containment_colour()` and mean
    containment only - they are never adjusted to match the brand, and are not
    re-stated here so there is no second copy to drift.
  * The fire perimeter orange. It is a data colour owned by `dashboard_map`.

Scope: these tokens are injected by `dashboard.render()` only. Fire Table and
Fire Detail keep their original light appearance (locked decision - there is no
global .streamlit/config.toml).
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
# Surfaces and text
# --------------------------------------------------------------------------- #
BLACK = "#000000"           # brand band: header strip, behind the logo
BG = "#121212"              # application background
SURFACE = "#1A1A1A"         # panels, fire rows
SURFACE_RAISED = "#232323"  # hover / selected row
SURFACE_SUNKEN = "#0E0E0E"  # toolbar well, insets

TEXT = "#F5F3F0"            # warm white, primary
TEXT_DIM = "#C9C7C1"        # secondary emphasis
TEXT_MUTED = "#9A9A94"      # secondary / captions
TEXT_FAINT = "#6E6E68"      # tertiary, de-emphasised

BORDER = "#55564E"          # from the bulletins
BORDER_SOFT = "#333330"     # hairline dividers inside panels

RED = "#CF241E"             # brand, selection, active, primary action, focus
RED_DIM = "#8E1914"         # pressed / low-emphasis brand edge
RED_WASH = "rgba(207,36,30,0.10)"   # selected-row tint
RED_WASH_STRONG = "rgba(207,36,30,0.18)"

FONT = "Arial, Helvetica, sans-serif"   # Arial is what the bulletins use

# --------------------------------------------------------------------------- #
# Review state - never colour alone (glyph + label always travel with it)
# --------------------------------------------------------------------------- #
# Keys match dashboard.review_state()["tone"].
REVIEW_STATE: dict[str, dict[str, str]] = {
    "required":   {"accent": RED,        "glyph": "◆", "label": "NOT REVIEWED"},
    "monitoring": {"accent": TEXT,       "glyph": "◉", "label": "MONITOR"},
    "no_action":  {"accent": TEXT_FAINT, "glyph": "○", "label": "NO ACTION"},
    "moratorium": {"accent": RED,        "glyph": "■", "label": "MORATORIUM"},
}


# --------------------------------------------------------------------------- #
# Colour helpers for pydeck (which wants [r, g, b, a] 0-255)
# --------------------------------------------------------------------------- #
def rgb(hex_colour: str, alpha: int = 255) -> list[int]:
    """'#CF241E' -> [207, 36, 30, alpha]. Accepts values with or without '#'."""
    h = hex_colour.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"expected a 6-digit hex colour, got {hex_colour!r}")
    return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha]


# --------------------------------------------------------------------------- #
# Map palette — REWORK MAP 1.5
#
# Visual hierarchy is explicit:
#   1. Fire perimeter
#   2. Relevant ZIP/ZCTA boundaries
#   3. Distance rings
#   4. Basemap
#
# ZIP polygons are no longer risk-colour blocks. Normal ZIPs are outline-only.
# Relevant/intersecting ZIPs receive only a very pale warm wash on a separate
# non-interactive layer. The interactive ZIP layer itself is effectively
# transparent and exists only to provide hover/click affordance.
# --------------------------------------------------------------------------- #

# Neutral ZIP outlines.
MAP_ZIP_LINE = [118, 118, 112, 150]
MAP_ZIP_NEAR_LINE = [105, 105, 100, 205]
MAP_ZIP_INSIDE_LINE = [86, 86, 82, 235]
MAP_ZIP_SEL_LINE = [65, 65, 62, 255]
MAP_MORATORIUM_LINE = [45, 45, 42, 245]

# Pale contextual washes. These are deliberately light and are rendered on a
# separate layer with an additional layer opacity cap in dashboard_map.py.
MAP_ZIP_CONTEXT_FILL = [232, 219, 196, 255]     # nearby/relevant
MAP_ZIP_INTERSECT_FILL = [248, 208, 154, 255]   # perimeter intersection
MAP_ZIP_SELECTED_FILL = [255, 235, 196, 255]    # selected ZIP
MAP_MORATORIUM_FILL = [225, 218, 206, 255]

# Interactive ZIP polygons themselves are transparent. Hover alone supplies
# the pale temporary fill. This prevents opaque red/grey blocks.
MAP_ZIP_PICK_FILL = [255, 255, 255, 0]
MAP_ZIP_HOVER_FILL = [255, 249, 229, 105]       # pale cream hover, never purple

MAP_ZIP_WIDTH = 0.8
MAP_ZIP_NEAR_WIDTH = 1.15
MAP_ZIP_INSIDE_WIDTH = 1.55
MAP_ZIP_SEL_WIDTH = 2.2
MAP_MORATORIUM_WIDTH = 1.8

# Distance rings are visible reference lines but must remain subordinate to the
# fire. They use progressively lighter neutral strokes.
MAP_RING_LINE = {
    1: [90, 90, 86, 185],
    3: [105, 105, 100, 155],
    5: [120, 120, 115, 130],
    10: [135, 135, 130, 100],
}
MAP_RING_FILL = [0, 0, 0, 0]
MAP_RING_WIDTH = 1.25

MAP_PLACE = [72, 78, 86, 225]
MAP_PLACE_NEAREST = [207, 36, 30, 255]

# Label treatment: dark glyph with a light halo, readable on the pale basemap.
MAP_LABEL_TEXT = [22, 26, 32, 255]
MAP_LABEL_OUTLINE = [255, 255, 255, 235]

ATTRIBUTION = "NIFC | Census 2020 ZCTA | CARTO / OpenStreetMap"
