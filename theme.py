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
# Map palette - neutral greys and the brand red only.
#
# Blue and purple are both gone: the old ZCTA_LINE was blue and the moratorium
# treatment was purple. Moratorium is a DATA state, not branding, so it now
# reads as a heavier neutral outline and is stated explicitly in the panel
# rather than being a colour the reviewer has to decode.
# --------------------------------------------------------------------------- #
MAP_ZIP_LINE = rgb(BORDER, 170)             # normal ZIP: thin, muted
MAP_ZIP_FILL = [0, 0, 0, 0]                 # normal ZIP: no fill at all
MAP_ZIP_NEAR_LINE = rgb(TEXT_MUTED, 215)    # near the fire: brighter outline
MAP_ZIP_NEAR_FILL = rgb(TEXT_MUTED, 14)     # ...and a very low-opacity wash
MAP_ZIP_SEL_LINE = rgb(RED, 255)            # selected: contrasting outline
MAP_ZIP_SEL_FILL = rgb(RED, 30)             # selected: subtle translucent fill
MAP_ZIP_INSIDE_LINE = rgb(TEXT, 240)        # intersects the perimeter
MAP_ZIP_INSIDE_FILL = rgb(TEXT, 16)         # ...kept light so it cannot mask the fire
MAP_MORATORIUM_LINE = rgb(TEXT, 250)        # data state: heavier neutral, no purple
MAP_MORATORIUM_FILL = rgb(TEXT, 20)

MAP_ZIP_WIDTH = 0.9
MAP_ZIP_NEAR_WIDTH = 1.6
MAP_ZIP_SEL_WIDTH = 2.8
MAP_ZIP_INSIDE_WIDTH = 2.2
MAP_MORATORIUM_WIDTH = 2.4

# Distance rings: intentionally visible on the pale CARTO basemap.
# These are underwriting reference distances, not decoration.
MAP_RING_LINE = {
    1: rgb(BORDER, 235),
    3: rgb(BORDER, 205),
    5: rgb(BORDER, 175),
    10: rgb(BORDER, 120),
}
MAP_RING_FILL = [0, 0, 0, 0]        # never filled
MAP_RING_WIDTH = 1.9

MAP_PLACE = rgb(TEXT, 235)
MAP_PLACE_NEAREST = rgb(RED, 255)   # the nearest place is the one that matters

# Label treatment: dark glyph with a light halo. Readable on the pale
# CARTO_POSITRON basemap and over any fill, with no separate background quad
# that could render while the glyph does not.
MAP_LABEL_TEXT = [12, 18, 30, 255]
MAP_LABEL_OUTLINE = [255, 255, 255, 235]

ATTRIBUTION = "NIFC | Census 2020 ZCTA | CARTO / OpenStreetMap"
