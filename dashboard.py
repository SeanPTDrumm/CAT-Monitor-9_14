"""
CAT Monitor dashboard and review workflow (presentation only).

Implements CAT_MONITOR_CLAUDE_CODE_HANDOFF.md sections 4-12. This module lays out
and formats; it computes no facts. Queue membership comes from the application's
existing logic (attention.py); geometry from dashboard_map; the review baseline and
history from reviews.py.

Scope rules honoured here:
  * The operational baseline is only reviews saved in-app. Archived Excel-derived
    records are never read or shown.
  * WFIGS Distance and Perimeter Distance are never combined in one field.
  * Reviewer dispositions are No Action, Monitor, Moratorium.
  * Nothing is inferred - no population, evacuation, structures, barriers, scores.
  * Styling stays scoped to this page.
"""
# CAT_MONITOR_BUILD: REV_1_3_1_VERIFIED

from __future__ import annotations

from pathlib import Path
from string import Template
from typing import Any, Callable

import pandas as pd
import streamlit as st

import attention
import dashboard_map
import reviews
import theme

# Sort choices (handoff 5.3). WFIGS Distance is the default, nearest first.
SORT_QUEUE = "Review Queue"
SORT_WFIGS = "WFIGS Distance"
SORT_PERIMETER = "Perimeter Distance"
SORT_SIZE = "Fire Size"
SORT_CONTAINMENT = "Containment"
SORT_CHOICES = [SORT_QUEUE, SORT_WFIGS, SORT_SIZE, SORT_CONTAINMENT]

SIZE_BREAKPOINT = 500.0        # handoff 4.2 - the only size breakpoint
WFIGS_NEAR_MILES = 5.0         # handoff 4.1 / 6

QUICK_REASON_OPTIONAL = "— Optional —"
QUICK_REASON_INVESTIGATE = "Needs further investigation"
QUICK_REASONS = [
    QUICK_REASON_OPTIONAL,
    "Low risk / limited exposure",
    "Containment good / improving",
    "No material change",
    QUICK_REASON_INVESTIGATE,
    "Other",
]

# Containment bands (handoff 4.3). Exact, and always shown with the number.
CONTAINMENT_UNAVAILABLE = "#8a9099"


def containment_colour(pct: float | None) -> str:
    """Exact bands from handoff 4.3. Blank is neutral grey, never treated as 0%."""
    if pct is None:
        return CONTAINMENT_UNAVAILABLE
    if pct >= 100:
        return "#2e9e4f"       # green
    if pct >= 90:
        return "#d9c223"       # yellow
    if pct >= 80:
        return "#dba52a"       # orange-yellow
    if pct >= 70:
        return "#e8842c"       # orange
    if pct >= 40:
        return "#f0602a"       # bright / reddish orange
    return "#d93025"           # red


# Review-state accents come from the Hiscox visual system. Kept as a dict under the
# original name so existing callers keep working; the glyph and label that travel
# with each state (so state is never carried by colour alone) live in
# theme.REVIEW_STATE.
TONE = {k: v["accent"] for k, v in theme.REVIEW_STATE.items()}

# Fire-row geometry. One number, used by both the row markup and the CSS that
# pulls the transparent click target over it - they must not disagree.
ROW_H = 78

_CSS_TEMPLATE = Template("""
<style>
  /* ---------------------------------------------------------------- shell */
  /* Set the face on the root ONLY and let it inherit. Enumerating
     span/div/p here out-specifies Streamlit's own icon-font rule, and the
     Material ligatures then render as their literal text ("expand_more",
     "arrow_right") all over the UI. */
  /* Streamlit's default body colour is dark-on-light (#31333F); set the warm
     white here so labels and widget text inherit it instead. */
  .stApp { background: $BG; font-family: $FONT; color: $TEXT; }
  .stApp [data-testid="stWidgetLabel"], .stApp [data-testid="stWidgetLabel"] p,
  .stApp label, .stApp label p { color: $TEXT_DIM !important; }
  /* ...and make the icon faces immune regardless.
     letter-spacing must be reset here too: Streamlit's icons are ligatures, and
     ANY inherited letter-spacing disables ligature substitution, so the glyph
     name ("expand_more", "keyboard_arrow_right") renders as literal text. The
     compact toolbar sets letter-spacing on buttons, which the icon spans inside
     them inherit - hence this reset. */
  .stApp [data-testid="stIconMaterial"], .stApp .material-icons,
  .stApp .material-icons-outlined, .stApp span[class*="material-icons"],
  .stApp [class*="stIconMaterial"] {
      font-family: "Material Symbols Rounded", "Material Icons",
                   "Material Icons Outlined" !important;
      letter-spacing: normal !important;
      font-variant-ligatures: normal !important;
      font-feature-settings: "liga" !important; }
  .block-container { padding-top: .9rem !important; padding-bottom: 1rem !important;
                     max-width: 100% !important; }

  /* Streamlit chrome: drop the decoration bar and Deploy, keep the main menu
     reachable so Rerun and settings are not lost. */
  [data-testid="stDecoration"] { display: none !important; }
  [data-testid="stAppDeployButton"] { display: none !important; }
  header[data-testid="stHeader"] { background: rgba(0,0,0,0) !important; }

  /* --------------------------------------------------------------- header */
  .cm-head { background: $BLACK; border: 1px solid $BORDER_SOFT; border-radius: 3px;
             padding: 10px 16px; margin-bottom: 12px;
             display: flex; align-items: center; gap: 18px; }
  .cm-head-logo { height: 44px; display: block; }
  .cm-head-rule { width: 1px; height: 34px; background: $BORDER; opacity: .7; }
  .cm-head-txt { display: flex; flex-direction: column; gap: 1px; }
  .cm-head-title { font-size: 1.12rem; font-weight: 700; color: $TEXT;
                   letter-spacing: .14em; line-height: 1.1; }
  .cm-head-title b { color: $RED; font-weight: 700; }
  .cm-head-sub { font-size: .72rem; color: $TEXT_MUTED; letter-spacing: .05em; }
  .cm-head-right { margin-left: auto; text-align: right; }
  .cm-head-stamp-l { font-size: .62rem; text-transform: uppercase; letter-spacing: .13em;
                     color: $TEXT_FAINT; }
  .cm-head-stamp-v { font-size: .86rem; color: $TEXT; font-weight: 700; }

  /* -------------------------------------------------------------- panels */
  .cm-panel { background: $SURFACE; border: 1px solid $BORDER_SOFT; border-radius: 3px;
              padding: 10px 12px; margin-bottom: 10px; }
  .cm-sec { font-size: .64rem; text-transform: uppercase; letter-spacing: .15em;
            color: $TEXT_FAINT; font-weight: 700; margin: 0 0 7px 0;
            padding-bottom: 5px; border-bottom: 1px solid $BORDER_SOFT; }
  .cm-sec-i { font-size: .64rem; text-transform: uppercase; letter-spacing: .15em;
              color: $TEXT_FAINT; font-weight: 700; margin: 12px 0 5px 0; }
  .cm-sub { color: $TEXT_MUTED; font-size: .78rem; }
  .cm-nv { color: $TEXT_FAINT; font-weight: 400; font-style: italic; }

  /* ------------------------------------------------- snapshot intelligence */
  .cm-si-head { display: flex; align-items: baseline; gap: 10px; margin: 0 0 6px 0; }
  .cm-si-title { font-size: .64rem; text-transform: uppercase; letter-spacing: .15em;
                 color: $TEXT_FAINT; font-weight: 700; }
  .cm-si-pair { font-size: .68rem; color: $TEXT_MUTED; margin-left: auto;
                font-variant-numeric: tabular-nums; }
  .cm-si-none { font-size: .72rem; color: $TEXT_FAINT; font-style: italic; }
  .cm-note { font-size: .68rem; color: $TEXT_MUTED; border-left: 2px solid $BORDER;
             padding: 3px 0 3px 8px; margin: 2px 0 8px 0; }

  /* Change-category chips are real buttons (they filter), styled compactly. */
  div[class*="st-key-cm_chg_"] { margin: 0 !important; }
  div[class*="st-key-cm_chg_"] button {
      background: $SURFACE_SUNKEN !important; border: 1px solid $BORDER_SOFT !important;
      color: $TEXT_DIM !important; border-radius: 2px !important;
      padding: 2px 7px !important; min-height: 25px !important; height: 25px !important;
      font-size: .66rem !important; font-weight: 700 !important;
      letter-spacing: .07em !important; width: 100% !important; }
  div[class*="st-key-cm_chg_"] button:hover {
      border-color: $BORDER !important; color: $TEXT !important;
      background: $SURFACE_RAISED !important; }
  div[class*="st-key-cm_chg_"] button[kind="primary"] {
      background: $RED_WASH_STRONG !important; border-color: $RED !important;
      color: $TEXT !important; }

  /* ------------------------------------------------------------- toolbar */
  .cm-tools { background: $SURFACE_SUNKEN; border: 1px solid $BORDER_SOFT;
              border-radius: 3px; padding: 7px 10px 3px 10px; margin-bottom: 9px; }
  .cm-tool-l { font-size: .6rem; text-transform: uppercase; letter-spacing: .13em;
               color: $TEXT_FAINT; font-weight: 700; margin: 0 0 2px 0; }
  .cm-count { font-size: .7rem; color: $TEXT_MUTED; font-variant-numeric: tabular-nums; }
  .cm-count b { color: $TEXT; }
  .cm-q-head { font-size: .60rem; text-transform: uppercase; letter-spacing: .14em;
                color: $TEXT_FAINT; font-weight: 700; padding: 9px 8px 4px 8px;
                border-bottom: 1px solid $BORDER_SOFT; background: $SURFACE_SUNKEN; }
  .cm-q-head:first-child { padding-top: 5px; }

  /* Widgets: one compact dark treatment, no default white blocks.
     This Streamlit build renders selects/multiselects as react-aria
     (.react-aria-ComboBox with an inner div[role="group"]), NOT as BaseWeb, so
     the data-baseweb selectors below are only a fallback for other builds.
     Without the react-aria rules the controls stay Streamlit's light grey
     (#F0F2F6 on #31333F) and dominate the dark interface. */
  .react-aria-ComboBox div[role="group"],
  .react-aria-ComboBox > div:not([role="group"]),
  div[data-baseweb="select"] > div {
      background: $SURFACE !important; border: 1px solid $BORDER_SOFT !important;
      border-radius: 2px !important; min-height: 29px !important;
      font-size: .76rem !important; color: $TEXT !important; }
  .react-aria-ComboBox div[role="group"]:hover,
  div[data-baseweb="select"] > div:hover { border-color: $BORDER !important; }
  .react-aria-ComboBox div[role="group"]:focus-within {
      border-color: $RED !important; }
  .react-aria-ComboBox input,
  .react-aria-ComboBox [role="combobox"] {
      background: transparent !important; color: $TEXT !important;
      font-size: .76rem !important; }
  .react-aria-ComboBox input::placeholder { color: $TEXT_FAINT !important; }
  .react-aria-ComboBox button { background: transparent !important;
      border: none !important; min-height: 0 !important; padding: 0 4px !important; }
  .react-aria-ComboBox svg, div[data-baseweb="select"] svg {
      fill: $TEXT_MUTED !important; color: $TEXT_MUTED !important; }
  /* Dropdown list */
  .react-aria-Popover, .react-aria-ListBox, [role="listbox"] {
      background: $SURFACE !important; border: 1px solid $BORDER !important;
      border-radius: 2px !important; }
  .react-aria-ListBox [role="option"], [role="listbox"] [role="option"],
  div[data-baseweb="popover"] li {
      background: transparent !important; color: $TEXT_DIM !important;
      font-size: .76rem !important; }
  .react-aria-ListBox [role="option"][data-focused],
  .react-aria-ListBox [role="option"]:hover,
  [role="listbox"] [role="option"]:hover {
      background: $SURFACE_RAISED !important; color: $TEXT !important; }
  .react-aria-ListBox [role="option"][data-selected],
  .react-aria-ListBox [role="option"][aria-selected="true"] {
      background: $RED_WASH_STRONG !important; color: $TEXT !important; }
  /* Multiselect chips */
  .react-aria-TagGroup .react-aria-Tag, .react-aria-Tag,
  [data-testid="stMultiSelect"] span[data-baseweb="tag"] {
      background: $RED_DIM !important; color: $TEXT !important;
      border: none !important; font-size: .68rem !important;
      border-radius: 2px !important; }
  [data-testid="stCheckbox"] { min-height: 29px; display: flex; align-items: center; }
  [data-testid="stCheckbox"] label { font-size: .74rem !important; color: $TEXT_DIM !important; }
  [data-testid="stCheckbox"] label span[aria-hidden="true"] {
      background: $SURFACE !important; border-color: $BORDER !important;
      border-radius: 2px !important; }
  [data-testid="stCheckbox"] label input:checked + span[aria-hidden="true"],
  [data-testid="stCheckbox"] label span[data-checked="true"] {
      background: $RED !important; border-color: $RED !important; }

  /* Generic buttons (Show All, review actions, popover trigger). */
  .stButton > button, [data-testid="stPopover"] button {
      background: $SURFACE !important; border: 1px solid $BORDER_SOFT !important;
      color: $TEXT_DIM !important; border-radius: 2px !important;
      font-size: .73rem !important; font-weight: 700 !important;
      letter-spacing: .04em !important; min-height: 29px !important;
      padding: 3px 10px !important; }
  .stButton > button:hover, [data-testid="stPopover"] button:hover {
      border-color: $BORDER !important; color: $TEXT !important;
      background: $SURFACE_RAISED !important; }
  .stButton > button[kind="primary"] {
      background: $RED !important; border-color: $RED !important; color: #fff !important; }
  .stButton > button[kind="primary"]:hover {
      background: $RED_DIM !important; border-color: $RED_DIM !important; }
  .stButton > button:focus-visible { outline: 2px solid $RED !important; outline-offset: 1px; }

  /* --------------------------------------------------------- fire rows
     Dense list. Each fire is ONE markdown block; the click target is a
     transparent button of exactly the same height rendered immediately BEFORE
     it, which the row is then pulled up over with a negative margin. The row
     is pointer-events:none, so clicks fall through to the button while the
     button's :hover styles the row via the sibling selector. This is what
     gets the per-fire pitch down to ${ROW_H}px - four stacked Streamlit blocks
     per fire could not. */
  /* The st-key-* class lands ON the vertical block, not on an ancestor, so this
     has to match the element itself - as a descendant selector it silently does
     nothing and Streamlit's 16px flex gap survives on both elements per fire
     (i.e. +32px of pitch). */
  .st-key-cm_list { gap: 0 !important; }
  .st-key-cm_list [data-testid="stVerticalBlock"] { gap: 0 !important; }
  .st-key-cm_list [data-testid="stElementContainer"] { margin: 0 !important; }
  .st-key-cm_list div[class*="st-key-cm_pick_"] {
      height: ${ROW_H}px !important; margin: 0 !important; }
  .st-key-cm_list div[class*="st-key-cm_pick_"] button {
      height: ${ROW_H}px !important; min-height: ${ROW_H}px !important;
      width: 100% !important; opacity: 0 !important; padding: 0 !important;
      margin: 0 !important; background: transparent !important;
      border: none !important; box-shadow: none !important; cursor: pointer; }
  .st-key-cm_list div[class*="st-key-cm_pick_"] + [data-testid="stElementContainer"] {
      margin-top: -${ROW_H}px !important; height: ${ROW_H}px !important;
      pointer-events: none; position: relative; }
  .st-key-cm_list div[class*="st-key-cm_pick_"]:hover
      + [data-testid="stElementContainer"] .cm-fr { background: $SURFACE_RAISED; }

  .cm-fr { height: ${ROW_H}px; box-sizing: border-box; background: $SURFACE;
           border-bottom: 1px solid $BORDER_SOFT; display: flex; align-items: stretch;
           overflow: hidden; }
  .cm-fr.sel { background: $RED_WASH; border-bottom-color: $BORDER; }
  .cm-fr-bar { width: 3px; flex: 0 0 3px; }
  .cm-fr-body { flex: 1; min-width: 0; padding: 8px 11px 7px 10px;
                display: flex; flex-direction: column; justify-content: center; gap: 4px; }
  .cm-fr-l1, .cm-fr-l2, .cm-fr-l3 { display: flex; align-items: center; gap: 8px;
                          white-space: nowrap; min-width: 0; }
  .cm-fr-name { font-size: .92rem; font-weight: 700; color: $TEXT;
                letter-spacing: .02em; overflow: hidden; text-overflow: ellipsis;
                max-width: 46%; }
  .cm-fr.sel .cm-fr-name { color: #fff; }
  .cm-fr-st { font-size: .6rem; font-weight: 700; color: $TEXT_MUTED;
              border: 1px solid $BORDER_SOFT; border-radius: 2px; padding: 0 3px;
              letter-spacing: .06em; }
  .cm-fr-chg { font-size: .64rem; font-weight: 700; letter-spacing: .04em;
               padding: 1px 5px; border-radius: 2px; overflow: hidden;
               text-overflow: ellipsis; }
  .cm-fr-chg.up { color: $RED; background: $RED_WASH_STRONG; }
  .cm-fr-chg.neu { color: $TEXT_DIM; background: rgba(245,243,240,0.07); }
  .cm-fr-rs { font-size: .6rem; font-weight: 700; letter-spacing: .09em;
              margin-left: auto; flex: 0 0 auto; }
  .cm-fr-rec { font-size: .58rem; color: $TEXT_FAINT; letter-spacing: .04em;
               flex: 0 0 auto; }
  .cm-fr-l2 { font-size: .74rem; color: $TEXT_DIM;
              font-variant-numeric: tabular-nums; }
  .cm-fr-l3 { font-size: .68rem; color: $TEXT_MUTED;
              font-variant-numeric: tabular-nums; }
  .cm-fr-ac { font-weight: 700; color: $TEXT_DIM; flex: 0 0 auto; }
  .cm-fr-ct { font-weight: 700; flex: 0 0 auto; }
  .cm-fr-loc { color: $TEXT_MUTED; overflow: hidden; text-overflow: ellipsis;
               min-width: 0; flex: 1 1 auto; }
  .cm-fr-pop { color: $TEXT_FAINT; flex: 0 0 auto; }

  /* ---------------------------------------------------- selected-fire panel */
  .cm-name { font-size: 1.18rem; font-weight: 700; color: $TEXT;
             letter-spacing: .035em; margin: 0; }
  .cm-review-help { font-size: .68rem; line-height: 1.35; color: $TEXT_MUTED;
                    margin: 4px 0 8px 0; }
  .cm-review-split { border-top: 1px solid $BORDER_SOFT; margin: 10px 0 8px 0; padding-top: 8px; }
  .cm-zipline { font-size: .72rem; color: $TEXT_DIM; line-height: 1.45; margin: 2px 0; }
  .cm-zipline b { color: $TEXT; }
  .cm-state { display: inline-block; border-radius: 2px; padding: 2px 7px;
              font-size: .63rem; font-weight: 700; letter-spacing: .1em; }
  .cm-f { display: flex; justify-content: space-between; align-items: baseline;
          gap: 10px; padding: 3px 0; border-bottom: 1px solid rgba(85,86,78,0.16); }
  .cm-f:last-child { border-bottom: none; }
  .cm-f-l { font-size: .64rem; text-transform: uppercase; letter-spacing: .1em;
            color: $TEXT_FAINT; flex: 0 0 auto; }
  .cm-f-v { font-size: .8rem; color: $TEXT; font-weight: 700; text-align: right;
            font-variant-numeric: tabular-nums; }
  .cm-f-n { font-size: .64rem; color: $TEXT_FAINT; text-align: right; font-weight: 400; }
  .cm-chg { color: $TEXT; font-size: .76rem; font-variant-numeric: tabular-nums;
            padding: 2px 0; }
  .cm-chg b { color: $RED; }
  .cm-rat { color: $TEXT_DIM; font-size: .76rem; white-space: pre-wrap;
            border-left: 2px solid $BORDER; padding-left: 8px; }
  .cm-badge { display: inline-block; background: $SURFACE_SUNKEN; color: $TEXT_MUTED;
              border: 1px solid $BORDER_SOFT; border-radius: 2px; padding: 1px 6px;
              font-size: .64rem; font-weight: 700; margin: 1px 4px 3px 0; }

  /* ----------------------------------------------------------- map shell */
  .cm-map-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 5px; }
  .cm-map-cap { font-size: .62rem; color: $TEXT_FAINT; letter-spacing: .05em;
                margin-top: 4px; }
  div[class*="st-key-cm_mapmode"] [data-testid="stWidgetLabel"] { display: none; }
  div[class*="st-key-cm_mapmode"] button {
      background: $SURFACE !important; border: 1px solid $BORDER_SOFT !important;
      color: $TEXT_MUTED !important; font-size: .66rem !important;
      font-weight: 700 !important; letter-spacing: .07em !important;
      min-height: 26px !important; padding: 2px 9px !important; border-radius: 2px !important; }
  div[class*="st-key-cm_mapmode"] button[aria-checked="true"],
  div[class*="st-key-cm_mapmode"] button[aria-pressed="true"] {
      background: $RED_WASH_STRONG !important; border-color: $RED !important;
      color: $TEXT !important; }

  /* Containers Streamlit draws with its own surface colour. */
  div[data-testid="stVerticalBlockBorderWrapper"] { background: $SURFACE;
      border-color: $BORDER_SOFT; }
  hr { border-color: $BORDER_SOFT !important; }
  [data-testid="stExpander"] details { background: $SURFACE !important;
      border: 1px solid $BORDER_SOFT !important; border-radius: 3px !important; }
  [data-testid="stExpander"] summary { font-size: .74rem !important; color: $TEXT_DIM !important; }
</style>
""")

_CSS = _CSS_TEMPLATE.substitute(
    BG=theme.BG, BLACK=theme.BLACK, SURFACE=theme.SURFACE,
    SURFACE_RAISED=theme.SURFACE_RAISED, SURFACE_SUNKEN=theme.SURFACE_SUNKEN,
    TEXT=theme.TEXT, TEXT_DIM=theme.TEXT_DIM, TEXT_MUTED=theme.TEXT_MUTED,
    TEXT_FAINT=theme.TEXT_FAINT, BORDER=theme.BORDER, BORDER_SOFT=theme.BORDER_SOFT,
    RED=theme.RED, RED_DIM=theme.RED_DIM, RED_WASH=theme.RED_WASH,
    RED_WASH_STRONG=theme.RED_WASH_STRONG, FONT=theme.FONT, ROW_H=ROW_H,
)



def _inject_css() -> None:
    """Dashboard only, so Fire Table and Fire Detail keep their existing look."""
    st.markdown(_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Fact accessors - read the existing normalised fields, never re-parse the CSV
# --------------------------------------------------------------------------- #
def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def current_size(row: Any) -> float | None:
    """Current size <- attr_IncidentSize (handoff 2), falling back to acres."""
    v = _num(row.get("incident_size"))
    return v if v is not None else _num(row.get("acres"))


def containment(row: Any) -> float | None:
    return _num(row.get("pct_contained"))


def wfigs_distance(row: Any) -> float | None:
    """WFIGS Distance - the miles in the WFIGS location description (handoff 5.1)."""
    return _num(row.get("origin_miles"))


_COMPASS = {"N": "north", "NE": "northeast", "E": "east", "SE": "southeast",
            "S": "south", "SW": "southwest", "W": "west", "NW": "northwest",
            "NNE": "north-northeast", "ENE": "east-northeast", "ESE": "east-southeast",
            "SSE": "south-southeast", "SSW": "south-southwest", "WSW": "west-southwest",
            "WNW": "west-northwest", "NNW": "north-northwest"}


def wfigs_location(row: Any) -> str | None:
    """Readable WFIGS location, e.g. '15 miles north of Ronald, WA' (handoff 5.1)."""
    mi = wfigs_distance(row)
    place, state = row.get("origin_place"), row.get("origin_place_state")
    if mi is None or not place:
        return None
    direction = _COMPASS.get(str(row.get("origin_direction") or "").upper().strip())
    where = f"{place}, {state}" if state else str(place)
    unit = "mile" if mi == 1 else "miles"
    return (f"{mi:g} {unit} {direction} of {where}" if direction
            else f"{mi:g} {unit} from {where}")


def wfigs_location_reported(row: Any, att: dict[str, Any]) -> str | None:
    """Compact-row wording, WFIGS-first: 'Reported N miles DIR from Place, ST (pop. N)'.

    Underwriters scan by WFIGS distance/direction/place first, so the compact
    row leads with that (handoff 5.1), never with calculated perimeter distance.
    Population is the exact cached value for that same place when the fire's
    nearest-place spatial result names it; otherwise the population band -
    never fabricated, never omitted outright.
    """
    mi = wfigs_distance(row)
    place, state = row.get("origin_place"), row.get("origin_place_state")
    if mi is None or not place:
        return None
    direction = str(row.get("origin_direction") or "").upper().strip()
    where = f"{place}, {state}" if state else str(place)
    unit = "mile" if mi == 1 else "miles"
    base = (f"Reported {mi:g} {unit} {direction} from {where}" if direction
            else f"Reported {mi:g} {unit} from {where}")

    prox = att.get("proximity") or {}
    prox_place, prox_pop = prox.get("place"), prox.get("population")
    if prox_pop is not None and prox_place and str(place).strip().lower() in str(prox_place).strip().lower():
        return f"{base} (pop. {prox_pop:,})"
    band = row.get("population_band")
    if band and band != "Not available":
        return f"{base} (pop. {band})"
    return base


def perimeter_distance(att: dict[str, Any]) -> float | None:
    """Verified edge-to-edge distance to the nearest populated place (handoff 5.2)."""
    return (att.get("proximity") or {}).get("place_miles")


def nearest_place(att: dict[str, Any]) -> str | None:
    return (att.get("proximity") or {}).get("place")


def nearby_zctas(att: dict[str, Any]) -> list[str]:
    return (att.get("proximity") or {}).get("verify_review_zctas") or []


def _att(row: Any) -> dict[str, Any]:
    a = row.get("attention") if hasattr(row, "get") else None
    return a if isinstance(a, dict) else {}


# --------------------------------------------------------------------------- #
# Sorting and filtering (handoff 5.3 and 6)
# --------------------------------------------------------------------------- #
def _queue_group(row: Any, store: dict, snapshot_id: str | None) -> int:
    """0 = needs review, 1 = tracked, 2 = reviewed/no action for this snapshot."""
    latest = reviews.latest(store, row["irwin_id"])
    att = _att(row)
    if latest is None:
        return 0

    disp = reviews.disposition(store, row["irwin_id"])
    same_snapshot = bool(snapshot_id and latest.get("snapshot_id") == snapshot_id)
    if latest.get("quick_reason") == QUICK_REASON_INVESTIGATE:
        return 0

    if disp in (reviews.MONITOR, reviews.MORATORIUM):
        return 1
    if disp == reviews.NO_ACTION:
        # A No Action decision stays at the bottom for the snapshot in which it was
        # completed. On a later upload it resurfaces as work only if the screening
        # layer says the fire again requires attention.
        if same_snapshot:
            return 2
        return 0 if att.get("requires_attention") else 2
    return 0


def sort_fires(frame: pd.DataFrame, choice: str, store: dict | None = None,
               snapshot_id: str | None = None) -> pd.DataFrame:
    """Reviewer queue first; alternate factual sorts remain available.

    Review Queue contains no hidden score. Within each review-state group it uses
    visible facts: ZIP intersection, 500+ acre breakpoint, containment, acreage,
    perimeter-to-place distance, and verified population.
    """
    f = frame.copy()
    f["_wfigs"] = [wfigs_distance(r) for _, r in f.iterrows()]
    f["_perim"] = [perimeter_distance(_att(r)) for _, r in f.iterrows()]
    f["_size"] = [current_size(r) for _, r in f.iterrows()]
    f["_cont"] = [containment(r) for _, r in f.iterrows()]
    f["_cont_tie"] = f["_cont"].fillna(10_000)
    f["_size_tie"] = -f["_size"].fillna(-1)

    if choice == SORT_QUEUE and store is not None:
        f["_q_group"] = [_queue_group(r, store, snapshot_id) for _, r in f.iterrows()]
        f["_zip_intersect"] = [
            0 if ((_att(r).get("proximity") or {}).get("intersects_zcta")) else 1
            for _, r in f.iterrows()
        ]
        f["_near5"] = [
            0 if (perimeter_distance(_att(r)) is not None
                  and perimeter_distance(_att(r)) <= WFIGS_NEAR_MILES) else 1
            for _, r in f.iterrows()
        ]
        f["_size500"] = [0 if (current_size(r) or -1) >= SIZE_BREAKPOINT else 1
                         for _, r in f.iterrows()]
        f["_pop"] = [
            -float(((_att(r).get("proximity") or {}).get("population")))
            if ((_att(r).get("proximity") or {}).get("population")) is not None else 1e18
            for _, r in f.iterrows()
        ]
        keys = ["_q_group", "_zip_intersect", "_near5", "_size500", "_cont_tie",
                "_size_tie", "_perim", "_pop"]
        asc = [True, True, True, True, True, True, True, True]
    elif choice == SORT_PERIMETER:
        keys, asc = ["_perim", "_cont_tie", "_size_tie"], [True, True, True]
    elif choice == SORT_SIZE:
        keys, asc = ["_size", "_cont_tie", "_size_tie"], [False, True, True]
    elif choice == SORT_CONTAINMENT:
        keys, asc = ["_cont", "_size_tie"], [True, True]
    else:
        keys, asc = ["_wfigs", "_cont_tie", "_size_tie"], [True, True, True]

    helper_cols = [c for c in (
        "_wfigs", "_perim", "_size", "_cont", "_cont_tie", "_size_tie",
        "_q_group", "_zip_intersect", "_near5", "_size500", "_pop"
    ) if c in f.columns]
    return f.sort_values(keys, ascending=asc, na_position="last").drop(columns=helper_cols)


def apply_filters(frame: pd.DataFrame, big_only: bool, near_only: bool) -> pd.DataFrame:
    """Optional size/distance filters only. They narrow the view and record no decision."""
    f = frame
    if big_only:
        f = f[[(current_size(r) or -1) >= SIZE_BREAKPOINT for _, r in f.iterrows()]]
    if near_only:
        f = f[[(wfigs_distance(r) is not None and wfigs_distance(r) <= WFIGS_NEAR_MILES)
               for _, r in f.iterrows()]]
    return f


def dashboard_fires(df: pd.DataFrame, store: dict,
                    snapshot_id: str | None = None) -> pd.DataFrame:
    """Build the day's work queue.

    * Unreviewed fires surface from the existing attention/screening logic.
    * Monitor and Moratorium remain tracked.
    * No Action remains visible at the bottom for the snapshot in which it was
      reviewed, then stays quiet on later uploads unless the fire resurfaces.
    """
    keep: list[bool] = []
    for _, r in df.iterrows():
        att = _att(r)
        latest = reviews.latest(store, r["irwin_id"])
        disp = reviews.disposition(store, r["irwin_id"])

        if att.get("alaska"):
            keep.append(False)
        elif latest is None:
            # Day 1 baseline: every non-Alaska fire gets a human look. The queue
            # ordering puts the consequential fires first so obvious low-concern
            # fires can be cleared rapidly.
            keep.append(True)
        elif latest and snapshot_id and latest.get("snapshot_id") == snapshot_id:
            keep.append(True)       # completed today: stays visible, but moves down
        elif disp in (reviews.MONITOR, reviews.MORATORIUM):
            keep.append(True)       # intentionally tracked across uploads
        elif disp == reviews.NO_ACTION:
            keep.append(bool(att.get("requires_attention")))  # resurfaced only
        else:
            keep.append(att.get("bucket") in (attention.BUCKET_ATTENTION,
                                              attention.BUCKET_MONITORING))
    return df[pd.Series(keep, index=df.index)]


# --------------------------------------------------------------------------- #
# Review state (handoff 9)
# --------------------------------------------------------------------------- #
def review_state(row: Any, store: dict, snapshot_id: str | None = None) -> dict[str, Any]:
    """Human review state plus change context."""
    latest = reviews.latest(store, row["irwin_id"])
    att = _att(row)
    when = None
    if latest:
        ts = str(latest.get("timestamp") or "")
        when = f"Last reviewed by {latest.get('reviewer') or 'unknown'} on {_pretty(ts)}."

    if latest is None:
        return {"label": "NOT REVIEWED", "tone": "required", "accent": TONE["required"],
                "detail": "Not previously reviewed.", "review": None,
                "changes": [], "when": None}

    current = {"acres": current_size(row), "containment": containment(row)}
    changes = reviews.changes_since(latest, current)
    disp = reviews.disposition(store, row["irwin_id"])
    same_snapshot = bool(snapshot_id and latest.get("snapshot_id") == snapshot_id)

    if latest.get("quick_reason") == QUICK_REASON_INVESTIGATE:
        return {"label": "INVESTIGATE", "tone": "required", "accent": TONE["required"],
                "when": when, "detail": "Marked for further investigation.",
                "review": latest, "changes": changes}

    # A prior No Action fire that resurfaces is work again; do not leave a stale
    # NO ACTION badge on a fire the current screening logic says needs attention.
    if disp == reviews.NO_ACTION and not same_snapshot and att.get("requires_attention"):
        return {"label": "REVIEW NEEDED", "tone": "required", "accent": TONE["required"],
                "when": when, "detail": "Changed since the prior review.",
                "review": latest, "changes": changes}

    if disp == reviews.MONITOR:
        tone, label = "monitoring", "MONITOR"
    elif disp == reviews.MORATORIUM:
        tone, label = "moratorium", "MORATORIUM"
    else:
        tone, label = "no_action", "NO ACTION"

    if att.get("requires_attention") and changes:
        detail = "Changed since the last review."
    elif changes:
        detail = "Updated since the last review."
    else:
        detail = "No acreage or containment change since the last review."

    return {"label": label, "tone": tone, "accent": TONE[tone],
            "when": when, "detail": detail, "review": latest, "changes": changes}


def _pretty(iso: str) -> str:
    try:
        return pd.Timestamp(iso).strftime("%B %-d, %Y at %-I:%M %p")
    except (ValueError, TypeError):
        try:
            return pd.Timestamp(iso).strftime("%B %d, %Y at %I:%M %p").replace(" 0", " ")
        except (ValueError, TypeError):
            return str(iso)


def review_recency(row: Any, store: dict) -> str:
    """Compact review recency for a fire row: 'Never reviewed', 'Reviewed today',
    'Reviewed yesterday', 'Reviewed Sep 11'.

    Day-of-month is formatted without a platform-specific strftime flag - "%-d" is
    a glibc extension and raises on Windows, which is where this app runs.
    """
    latest = reviews.latest(store, row["irwin_id"])
    if latest is None:
        return "Never reviewed"
    try:
        ts = pd.Timestamp(str(latest.get("timestamp") or ""))
    except (ValueError, TypeError):
        return "Reviewed"
    if pd.isna(ts):
        return "Reviewed"
    now = pd.Timestamp.now()
    if ts.date() == now.date():
        return "Reviewed today"
    if (now.normalize() - ts.normalize()).days == 1:
        return "Reviewed yesterday"
    return f"Reviewed {ts.strftime('%b')} {ts.day}"


# --------------------------------------------------------------------------- #
# Snapshot intelligence - "Since Last Update"
#
# Purely snapshot-to-snapshot: current CSV vs the prior CSV. Requires no saved
# review, and never calls anything "material" - these are plain facts. The
# materiality judgement stays where it already lives, in attention.py.
# --------------------------------------------------------------------------- #
CHANGE_CATEGORIES = [
    ("new", "NEW"),
    ("acreage", "ACREAGE"),
    ("containment", "CONTAINMENT"),
    ("perimeter", "PERIMETER"),
    ("exposure", "EXPOSURE"),
    ("name", "NAME"),
    ("dropped", "DROPPED"),
]


def _since_last_update(frame: pd.DataFrame,
                       dropped: pd.DataFrame | None = None) -> dict[str, list[str]]:
    """Fire ids per factual change category, from the existing snapshot join.

    Only categories with at least one fire are returned, so the summary never
    shows a category the data cannot support.
    """
    out: dict[str, list[str]] = {k: [] for k, _ in CHANGE_CATEGORIES}
    for _, r in frame.iterrows():
        d = attention.snapshot_delta(r)
        iid = r["irwin_id"]
        if d["is_new"]:
            out["new"].append(iid)
            continue            # a new fire has no prior values to have changed
        if d["acres_delta"] is not None and d["acres_delta"] != 0:
            out["acreage"].append(iid)
        if d["containment_delta"] is not None and d["containment_delta"] != 0:
            out["containment"].append(iid)
        if d["perimeter_changed"] is True:
            out["perimeter"].append(iid)
        if d["exposure_changed"]:
            out["exposure"].append(iid)
        if d["name_changed"]:
            out["name"].append(iid)
    if dropped is not None and not dropped.empty:
        out["dropped"] = list(dropped["irwin_id"])
    return {k: v for k, v in out.items() if v}


def _snapshot_summary(frame: pd.DataFrame, dropped: pd.DataFrame | None,
                       pair_label: str | None, note: str | None = None) -> None:
    """Simple non-interactive snapshot heading.

    Change details belong on each fire row and in the selected-fire panel.
    There are intentionally no acreage/containment/perimeter/dropped filter buttons.
    """
    # Clear any stale category filter left from an older app version/session.
    st.session_state["cm_change_filter"] = None

    st.markdown(
        "<div class='cm-si-head'><span class='cm-si-title'>Changes since prior update</span>"
        + (f"<span class='cm-si-pair'>{pair_label}</span>" if pair_label else "")
        + "</div>", unsafe_allow_html=True)

    if note:
        st.markdown(f"<div class='cm-note'>{note}</div>", unsafe_allow_html=True)

    # If there is no prior snapshot, say so plainly. Otherwise the fire rows and
    # selected-fire panel carry the actual change information.
    if not pair_label:
        st.markdown(
            "<div class='cm-si-none'>No comparable prior snapshot is selected.</div>",
            unsafe_allow_html=True,
        )


def filter_by_change(pool: pd.DataFrame, dropped: pd.DataFrame | None) -> pd.DataFrame | None:
    """Fires in the selected change category, or None when no category is active.

    Selects from the FULL dashboard pool, deliberately ignoring the 500+ acre and
    within-5-mile narrowing. The counts on the chips are counted over the pool, so
    filtering inside the already-narrowed view could show "ACREAGE 2" and then an
    empty list. A change category is a different lens, not an extra filter.

    View only; records nothing.
    """
    active = st.session_state.get("cm_change_filter")
    if not active or active == "dropped":
        return None
    cats = _since_last_update(pool, dropped)
    keep = set(cats.get(active, []))
    return pool[pool["irwin_id"].isin(keep)] if keep else pool.iloc[0:0]


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
_LOGO = Path(__file__).resolve().parent / "assets" / "hiscox-logo.png"


@st.cache_data(show_spinner=False)
def _logo_data_uri(path_str: str, mtime: float) -> str | None:
    """The header logo as a data URI, or None if the asset is absent.

    `mtime` is part of the cache key so replacing the asset invalidates it.
    The mark is the approved Hiscox lockup extracted verbatim from the bulletin
    letterhead already in this project - it is never redrawn or recoloured.
    """
    import base64
    p = Path(path_str)
    if not p.exists():
        return None
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode("ascii")


def _header(meta: dict, ctx: dict) -> None:
    """Compact branded header plus a clear data-update workflow."""
    uri = _logo_data_uri(str(_LOGO), _LOGO.stat().st_mtime if _LOGO.exists() else 0.0)

    logo = (f"<img class='cm-head-logo' src='{uri}' alt='Hiscox'/>"
            "<div class='cm-head-rule'></div>") if uri else ""

    st.markdown(
        "<div class='cm-head'>" + logo
        + "<div class='cm-head-txt'>"
          "<div class='cm-head-title'>CAT MONITOR</div>"
          "<div class='cm-head-sub'>Wildfire monitoring</div></div>"
          "<div class='cm-head-right'>"
          "<div class='cm-head-stamp-l'>Data current</div>"
          f"<div class='cm-head-stamp-v'>{ctx['fmt']['when'](meta)}</div></div>"
          "</div>",
        unsafe_allow_html=True,
    )

    pair_label = ctx.get("compare_label")
    if pair_label:
        st.markdown(
            f"<div class='cm-note'><b>Comparing:</b> {pair_label}</div>",
            unsafe_allow_html=True,
        )

    with st.expander("UPDATE DATA — load a new WFIGS CSV + GeoJSON", expanded=False):
        st.caption(
            "Upload the newest WFIGS perimeter CSV and its matching GeoJSON. "
            "After saving, CAT Monitor will make it current and automatically "
            "compare it with the immediately preceding snapshot."
        )
        ctx["data_controls"]()


# --------------------------------------------------------------------------- #
# Controls - one compact toolbar
# --------------------------------------------------------------------------- #
_FILTER_KEYS = ("cm_f_big", "cm_f_near")


def _clear_filters() -> None:
    """Back to the opening view: the 500+ acre and within-5-mile defaults on,
    optional filters off, and no change-category narrowing."""
    st.session_state["cm_f_big"] = True
    st.session_state["cm_f_near"] = True
    st.session_state["cm_change_filter"] = None


def _controls() -> str:
    """Primary work-queue ordering, with alternate factual sorts available."""
    with st.container(key="cm_tools"):
        st.markdown("<div class='cm-tool-l'>Queue order</div>", unsafe_allow_html=True)
        choice = st.selectbox("Queue order", SORT_CHOICES, key="cm_sort_v12",
                              label_visibility="collapsed")
    return choice


# --------------------------------------------------------------------------- #
# Main fire list - dense two-line rows
# --------------------------------------------------------------------------- #
def _change_indicator(row: Any) -> tuple[str, str] | None:
    """The single most relevant factual change for the row, as (text, css class).

    Raw snapshot deltas, stated verbatim. No thresholds are applied or invented
    here: a fire appears with whatever its comparison actually says. Priority is
    fixed so the same fire always shows the same indicator.
    """
    d = attention.snapshot_delta(row)
    if d["is_new"]:
        return "NEW", "up"
    ac = d["acres_delta"]
    if ac is not None and ac != 0:
        return f"{ac:+,.0f} ac", "up" if ac > 0 else "neu"
    ct, was, now = d["containment_delta"], d["containment_prior"], d["containment"]
    if ct is not None and ct != 0 and was is not None and now is not None:
        return f"{was:.0f}% → {now:.0f}%", "up" if ct < 0 else "neu"
    if d["perimeter_changed"] is True:
        return "Perimeter changed", "neu"
    if d["exposure_changed"]:
        closer = d["closer_miles"]
        if closer is not None:
            return f"{closer:.1f} mi closer", "up"
        return "Exposure changed", "neu"
    if d["name_changed"]:
        return "Name changed", "neu"
    return None


def _row_population(row: Any, att: dict[str, Any]) -> str:
    """Show only an exact verified Census population; never substitute a bucket."""
    prox = att.get("proximity") or {}
    pop = prox.get("population")
    return f"pop. {pop:,}" if pop is not None else "pop. not verified"


def _row_location(row: Any) -> str:
    """'2 mi N of Ouray, CO' - WFIGS distance, direction and place, always visible."""
    mi = wfigs_distance(row)
    place, state = row.get("origin_place"), row.get("origin_place_state")
    if mi is None or not place:
        return "location not verified"
    direction = str(row.get("origin_direction") or "").upper().strip()
    where = f"{place}, {state}" if state else str(place)
    return f"{mi:g} mi {direction} of {where}" if direction else f"{mi:g} mi from {where}"


def _fire_list(frame: pd.DataFrame, selected: str | None, sort_choice: str,
               store: dict, ctx: dict) -> str | None:
    """Dense two-line rows.

    Each fire is one transparent full-height button followed by one markdown
    block pulled up over it (see the .st-key-cm_list rules). The button carries
    the click; the row carries the pixels. Four stacked Streamlit blocks per fire
    could not reach this density.
    """
    picked = None
    last_section = None
    section_names = {0: "TO REVIEW", 1: "TRACKING", 2: "REVIEWED — NO ACTION"}
    with st.container(key="cm_list"):
        for _, r in frame.iterrows():
            qg = _queue_group(r, store, ctx.get("snapshot_id"))
            section = section_names.get(qg, "TO REVIEW")
            if section != last_section:
                st.markdown(f"<div class='cm-q-head'>{section}</div>", unsafe_allow_html=True)
                last_section = section
            iid = r["irwin_id"]
            att = _att(r)
            size, cont = current_size(r), containment(r)
            state = review_state(r, store, ctx.get("snapshot_id"))
            rs = theme.REVIEW_STATE[state["tone"]]
            chg = _change_indicator(r)

            # Click target first, so the row below can be pulled over it and the
            # button's :hover can style the row through the sibling selector.
            if st.button("", key=f"cm_pick_{iid}", use_container_width=True):
                picked = iid

            # Exactly one distance in the compact row. WFIGS-first is what the
            # reviewer scans by; Perimeter Distance only when sorted on it.
            if sort_choice == SORT_PERIMETER:
                pd_mi = perimeter_distance(att)
                loc = (f"{pd_mi:.1f} mi from perimeter to {nearest_place(att)}"
                       if pd_mi is not None and nearest_place(att)
                       else f"{pd_mi:.1f} mi from perimeter" if pd_mi is not None
                       else "perimeter distance not verified")
            else:
                loc = _row_location(r)

            st.markdown(
                f"<div class='cm-fr{' sel' if iid == selected else ''}'>"
                f"<span class='cm-fr-bar' style='background:{rs['accent']}'></span>"
                "<div class='cm-fr-body'>"
                "<div class='cm-fr-l1'>"
                f"<span class='cm-fr-name'>{r['fire_name']}</span>"
                f"<span class='cm-fr-st'>{ctx['fmt']['text'](r.get('state'))}</span>"
                + f"<span class='cm-fr-rs' style='color:{rs['accent']}'>"
                  f"{rs['glyph']} {state['label']}</span>"
                  "</div>"
                  "<div class='cm-fr-l2'>"
                f"<span class='cm-fr-ac'>{f'{size:,.0f} ac' if size is not None else 'size n/v'}</span>"
                f"<span class='cm-fr-ct' style='color:{containment_colour(cont)}'>"
                f"{f'{cont:.0f}% contained' if cont is not None else 'containment n/v'}</span>"
                + ("<span class='cm-fr-chg up'>ZIP INTERSECT</span>"
                   if ((att.get("proximity") or {}).get("intersects_zcta")) else "")
                + (f"<span class='cm-fr-chg {chg[1]}'>{chg[0]}</span>" if chg else "")
                + "</div>"
                  "<div class='cm-fr-l3'>"
                f"<span class='cm-fr-loc'>{(nearest_place(att) or loc)}"
                f"{f' · {perimeter_distance(att):.1f} mi' if perimeter_distance(att) is not None else ''}</span>"
                f"<span class='cm-fr-pop'>{_row_population(r, att)}</span>"
                f"<span class='cm-fr-rec'>{review_recency(r, store)}</span>"
                "</div></div></div>", unsafe_allow_html=True)
    return picked


def _dropped_list(dropped: pd.DataFrame | None, ctx: dict) -> None:
    """Fires whose IRWIN ID was in the prior snapshot and is absent from this one.

    Shown from prior-snapshot facts, because that is the last thing the source
    actually said about them. Not selectable: there is no current record to put
    on the map, and a dropped fire is not treated as closed or contained.
    """
    if dropped is None or dropped.empty:
        st.markdown("<div class='cm-si-none'>No fires left the feed.</div>",
                    unsafe_allow_html=True)
        return
    recs = ctx.get("records") or {}
    rows = [attention.assess_dropped(r, recs.get(r["irwin_id"]))
            for _, r in dropped.iterrows()]
    rows.sort(key=lambda d: (not d["tracked"], -(d["acres_prior"] or 0)))
    for d in rows:
        size = f"{d['acres_prior']:,.0f} ac" if d["acres_prior"] is not None else "size n/v"
        cont = (f"{d['containment_prior']:.0f}%" if d["containment_prior"] is not None
                else "n/v")
        st.markdown(
            "<div class='cm-fr' style='height:auto'>"
            f"<span class='cm-fr-bar' style='background:{theme.TEXT_FAINT}'></span>"
            "<div class='cm-fr-body'>"
            "<div class='cm-fr-l1'>"
            f"<span class='cm-fr-name'>{d['fire_name']}</span>"
            f"<span class='cm-fr-st'>{ctx['fmt']['text'](d['state'])}</span>"
            "<span class='cm-fr-rs' style='color:"
            f"{theme.TEXT_FAINT}'>DROPPED</span></div>"
            "<div class='cm-fr-l2'>"
            f"<span class='cm-fr-ac'>{size}</span>"
            f"<span class='cm-fr-ct' style='color:{containment_colour(d['containment_prior'])}'>"
            f"{cont}</span>"
            f"<span class='cm-fr-loc'>{d['reason']}</span>"
            "</div></div></div>", unsafe_allow_html=True)
    st.markdown("<div class='cm-note'>Prior-snapshot values. A fire leaving the feed is "
                "not by itself a closure, a containment, or a review decision.</div>",
                unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Selected-fire panel (handoff 8)
# --------------------------------------------------------------------------- #
def _fact(label: str, value: str | None, note: str | None = None) -> None:
    """One compact label/value row. Missing values always read "Not verified"."""
    shown = value if value else "<span class='cm-nv'>Not verified</span>"
    st.markdown(f"<div class='cm-f'><span class='cm-f-l'>{label}</span>"
                f"<span class='cm-f-v'>{shown}"
                + (f"<div class='cm-f-n'>{note}</div>" if note else "")
                + "</span></div>", unsafe_allow_html=True)


def _panel(row: pd.Series | None, store: dict, ctx: dict) -> None:
    """Selected fire: current -> change -> exposure -> prior review -> today's review."""
    if row is None:
        st.markdown("<div class='cm-si-none'>Select a fire to see its details.</div>",
                    unsafe_allow_html=True)
        return

    att = _att(row)
    state = review_state(row, store, ctx.get("snapshot_id"))
    rs = theme.REVIEW_STATE[state["tone"]]
    size, cont = current_size(row), containment(row)
    iid = row["irwin_id"]
    d = attention.snapshot_delta(row)

    st.markdown(
        f"<div class='cm-name'>{row['fire_name']}"
        f"<span class='cm-fr-st' style='margin-left:8px'>{ctx['fmt']['text'](row.get('state'))}</span></div>"
        f"<div style='margin:5px 0 2px 0'><span class='cm-state' "
        f"style='background:{rs['accent']}22;color:{rs['accent']};"
        f"border:1px solid {rs['accent']}66'>{rs['glyph']} {state['label']}</span></div>",
        unsafe_allow_html=True)

    # REVIEW FIRST — the normal path should take only a few seconds.
    st.markdown("<div class='cm-sec-i'>Review</div>", unsafe_allow_html=True)
    current_disp = reviews.disposition(store, iid)
    options = list(reviews.DISPOSITIONS)
    default_idx = options.index(current_disp) if current_disp in options else 0

    chosen = st.radio("Status", options, index=default_idx, horizontal=True,
                      key=f"cm_disp_v13_{iid}")

    quick_reason = st.selectbox(
        "Quick reason",
        QUICK_REASONS,
        index=0,
        key=f"cm_reason_v13_{iid}",
        help="Optional. Leave blank for a one-click review."
    )
    quick_reason_value = None if quick_reason == QUICK_REASON_OPTIONAL else quick_reason

    rationale = st.text_area("Notes / rationale", value="", height=72,
                             placeholder="Optional note…",
                             key=f"cm_note_v13_{iid}")

    st.markdown(
        "<div class='cm-review-help'><b>Mark Reviewed</b> requires nothing else. "
        "It records the status and current fire facts as the baseline for the next update. "
        "If marked for further investigation, the fire stays in To Review.</div>",
        unsafe_allow_html=True)
    if st.button("Mark Reviewed", type="primary", use_container_width=True,
                 key=f"cm_mark_v13_{iid}"):
        st.session_state["cm_advance_after_review"] = iid
        ctx["save_review"](row, chosen, rationale, quick_reason_value, False, False)

    with st.expander("Log Review — formal record", expanded=False):
        st.caption("Use this when you want a fuller evidence record you can revisit or explain later.")
        freeze_map = st.checkbox("Include map snapshot", value=True,
                                 key=f"cm_freeze_v13_{iid}")
        if st.button("Log Review", use_container_width=True, key=f"cm_log_v13_{iid}"):
            st.session_state["cm_advance_after_review"] = iid
            ctx["save_review"](row, chosen, rationale, quick_reason_value, True, freeze_map)

    # CURRENT
    st.markdown("<div class='cm-sec-i'>Current</div>", unsafe_allow_html=True)
    _fact("Acreage", f"{size:,.0f}" if size is not None else None)
    _fact("Containment",
          f"<span style='color:{containment_colour(cont)}'>{cont:.0f}%</span>"
          if cont is not None else None)
    _fact("WFIGS location", wfigs_location(row))

    # CHANGE
    st.markdown("<div class='cm-sec-i'>Since prior update</div>", unsafe_allow_html=True)
    lines: list[str] = []
    if d["is_new"]:
        lines.append("<b>New in this snapshot</b>")
    else:
        if d["acres_delta"] is not None and d["acres_delta"] != 0:
            lines.append(f"Acreage <b>{d['acres_delta']:+,.0f}</b>")
        if (d["containment_delta"] is not None and d["containment_delta"] != 0
                and d["containment_prior"] is not None and d["containment"] is not None):
            lines.append(f"Containment {d['containment_prior']:.0f}% → "
                         f"{d['containment']:.0f}% (<b>{d['containment_delta']:+.0f} pts</b>)")
        if d["perimeter_changed"] is True:
            lines.append("Perimeter changed")
        if d["closer_miles"] is not None:
            lines.append(f"Nearest place <b>{d['closer_miles']:.1f} mi closer</b>")
        if d["zips_entered"]:
            lines.append("ZIPs newly in range: " + ", ".join(d["zips_entered"][:4]))
    if lines:
        for line in lines:
            st.markdown(f"<div class='cm-chg'>{line}</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='cm-sub'>No reported change in the comparable fields.</div>",
                    unsafe_allow_html=True)

    # EXPOSURE
    st.markdown("<div class='cm-sec-i'>Exposure</div>", unsafe_allow_html=True)
    prox = att.get("proximity") or {}
    place, pop = prox.get("place"), prox.get("population")
    _fact("Nearest population center", place)
    _fact("Population", f"{pop:,}" if pop is not None else None,
          "2020 U.S. Census" if pop is not None else None)
    pd_mi = perimeter_distance(att)
    _fact("Distance from perimeter", f"{pd_mi:.1f} mi" if pd_mi is not None else None)

    sid = ctx.get("snapshot_id")
    sp = (ctx["spatial_all"](sid).get(iid) if sid else None) or {}
    zrows = [z for z in ((sp.get("spatial") or {}).get("zctas") or [])
             if z.get("review_state") in ("VERIFY", "REVIEW")]
    zrows.sort(key=lambda z: (z.get("distance_miles") is None,
                              z.get("distance_miles") if z.get("distance_miles") is not None else 999))
    if zrows:
        intersects = [z for z in zrows if z.get("intersects")]
        nearby = [z for z in zrows if not z.get("intersects")]

        st.markdown("<div class='cm-f-l' style='margin-top:6px'>Relevant ZIP areas</div>",
                    unsafe_allow_html=True)

        if intersects:
            codes = ", ".join(str(z.get("zcta")) for z in intersects[:6])
            more = f" +{len(intersects)-6} more" if len(intersects) > 6 else ""
            st.markdown(f"<div class='cm-zipline'><b>Perimeter intersects:</b> {codes}{more}</div>",
                        unsafe_allow_html=True)

        if nearby:
            parts = []
            for z in nearby[:5]:
                code = str(z.get("zcta"))
                city = f" {z.get('zip_city')}" if z.get("zip_city") else ""
                mi = z.get("distance_miles")
                parts.append(f"{code}{city} ({float(mi):.1f} mi)" if mi is not None
                             else f"{code}{city}")
            more = f" +{len(nearby)-5} more" if len(nearby) > 5 else ""
            st.markdown(f"<div class='cm-zipline'><b>Nearby:</b> "
                        + " · ".join(parts) + more + "</div>",
                        unsafe_allow_html=True)
    else:
        st.markdown("<div class='cm-sub'>No ZIP areas currently in the review range.</div>",
                    unsafe_allow_html=True)

    # PRIOR REVIEW
    st.markdown("<div class='cm-sec-i'>Prior review</div>", unsafe_allow_html=True)
    latest = state["review"]
    if latest:
        logged = " · Logged review" if latest.get("logged") else ""
        st.markdown(
            f"<div class='cm-sub'><b>{reviews.disposition(store, iid)}</b> · "
            f"{_pretty(str(latest.get('timestamp') or ''))}{logged}</div>",
            unsafe_allow_html=True)
        if latest.get("quick_reason"):
            st.markdown(f"<div class='cm-sub'>Reason: {latest['quick_reason']}</div>",
                        unsafe_allow_html=True)
        if (latest.get("rationale") or "").strip():
            st.markdown(f"<div class='cm-rat'>{latest['rationale']}</div>",
                        unsafe_allow_html=True)
    else:
        st.markdown("<div class='cm-sub'>Not previously reviewed.</div>",
                    unsafe_allow_html=True)


    _history(row, store, ctx)


def _containment_note(cont: float | None) -> str | None:
    if cont is None:
        return None
    if cont >= 100:
        return "100%"
    if cont >= 90:
        return "90-99%"
    if cont >= 80:
        return "80-89%"
    if cont >= 70:
        return "70-79%"
    if cont >= 40:
        return "40-69%"
    return "Under 40%"


def _distance_note(mi: float | None) -> str | None:
    if mi is None:
        return None
    return ("Within main 5-mile review distance" if mi <= WFIGS_NEAR_MILES
            else "Outside main 5-mile review distance")


def _history(row: pd.Series, store: dict, ctx: dict) -> None:
    entries = reviews.history(store, row["irwin_id"])
    if not entries:
        return
    with st.expander(f"Review history ({len(entries)})", expanded=False):
        for e in entries:
            kind = " • Logged review" if e.get("logged") else ""
            disp = reviews.NO_ACTION if e.get("disposition") == reviews.LEGACY_IGNORE else e.get("disposition")
            st.markdown(f"**{_pretty(str(e.get('timestamp') or ''))}**  \n"
                        f"{e.get('reviewer') or 'unknown'} • {disp}{kind}")
            if (e.get("rationale") or "").strip():
                st.markdown(f"<div class='cm-rat'>{e['rationale']}</div>",
                            unsafe_allow_html=True)
            # Shown only when a valid saved map exists for that review.
            if reviews.map_path(e) is not None:
                if st.button("View saved map", key=f"cm_vm_{e['review_id']}"):
                    _show_saved_map(e)
            st.divider()


@st.dialog("Saved map", width="large")
def _show_saved_map(entry: dict[str, Any]) -> None:
    """Open a review's saved map without disturbing the current map or data."""
    path = reviews.map_path(entry)
    if path is None:
        st.error("The saved map for this review is no longer available.")
        return
    st.caption(f"Map saved with the {entry.get('disposition')} review by "
               f"{entry.get('reviewer') or 'unknown'} on "
               f"{_pretty(str(entry.get('timestamp') or ''))}.")
    st.components.v1.html(path.read_text(encoding="utf-8"), height=520, scrolling=False)


# --------------------------------------------------------------------------- #
# Review Fire form (handoff 11)
# --------------------------------------------------------------------------- #
def evidence_for(row: pd.Series, meta: dict) -> dict[str, Any]:
    """Facts available to the reviewer at review time (handoff 12).

    Absent facts are omitted rather than filled in.
    """
    att = _att(row)
    prox = att.get("proximity") or {}
    return {
        "state": row.get("state"),
        "source_system": row.get("source_system"),
        "acres": current_size(row),
        "containment": containment(row),
        "wfigs_distance": wfigs_distance(row),
        "wfigs_location": wfigs_location(row),
        "nearest_place": prox.get("place"),
        "population": prox.get("population"),
        "population_year": 2020 if prox.get("population") is not None else None,
        "perimeter_distance": prox.get("place_miles"),
        "nearby_zctas": nearby_zctas(att) or None,
        "perimeter_timestamp": _iso_or_none(row.get("perimeter_date_current")),
        "perimeter_id": (meta.get("geojson") or {}).get("filename"),
    }


def _iso_or_none(v: Any) -> str | None:
    try:
        return None if pd.isna(v) else pd.Timestamp(v).isoformat(timespec="seconds")
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------------- #
# Centre column - the map
# --------------------------------------------------------------------------- #
def _map_toolbar() -> str:
    """One underwriting-oriented distance overlay: 1, 3 and 5 miles together."""
    c1, c2 = st.columns([0.58, 0.42], gap="small", vertical_alignment="center")
    with c1:
        st.markdown("<div class='cm-sub'>Fire perimeter and relevant ZIP areas</div>",
                    unsafe_allow_html=True)
    with c2:
        show_rings = st.checkbox("Show 1 / 3 / 5 mile rings", value=False,
                                 key="cm_show_review_rings")
    return dashboard_map.RING_REVIEW if show_rings else dashboard_map.RING_OFF


def _map(row: pd.Series | None, meta: dict, ctx: dict) -> None:
    if row is None:
        st.markdown("<div class='cm-si-none'>Select a fire to view perimeter and "
                    "geography.</div>", unsafe_allow_html=True)
        return

    rings = _map_toolbar()
    sid = meta["snapshot_id"]
    iid = row["irwin_id"]

    # Everything below is read from the per-snapshot spatial cache. Selecting a
    # ZIP, switching mode or toggling rings re-reads that cache and re-buffers
    # local geometry only - no external request on any of those paths.
    sp = ctx["spatial_all"](sid).get(iid)
    inputs = ctx["load_inputs"](sid, iid) if sp else None
    selected_zip = (st.session_state.get("cm_sel_zip") or {}).get(iid)
    prepared = dashboard_map.prepare(sp, inputs, set(), selected_zip=selected_zip,
                                     rings=rings)

    if not prepared["ok"]:
        st.error(f"**Map not available for {row['fire_name']}.** {prepared['reason']}")
        if st.button("Compute geography for this fire", type="primary",
                     use_container_width=True, key=f"cm_geo_{iid}"):
            ctx["run_geography"]([(iid, row["fire_name"])])
            st.rerun()
        return

    # Remember what was actually on screen, tagged with the fire it belongs to, so a
    # "save map with this review" can never store another fire's map.
    st.session_state["cm_last_deck"] = {**prepared, "irwin_id": iid}

    built = dashboard_map.deck(prepared, row["fire_name"])

    # The deck paints an empty canvas on the FIRST render of a session: it mounts
    # before the column it lives in has been measured, and nothing afterwards
    # tells it to resize. Re-rendering with the same key is not enough - React
    # keeps the already-broken instance - so the key carries a "primed" bit and
    # the second pass mounts a fresh component into an already-measured column.
    # One extra rerun per session, everything downstream cached.
    primed = bool(st.session_state.get("cm_map_primed"))
    deck_key = f"cm_deck_{iid}_{1 if primed else 0}"

    # ONE chart call for every mode, always keyed and always registering
    # selection, so switching mode cannot change how the chart mounts.
    event = None
    try:
        event = st.pydeck_chart(
            built, use_container_width=True, height=548,
            selection_mode="single-object", on_select="rerun", key=deck_key)
    except Exception:
        # Selection support differs across Streamlit builds. Showing the map is
        # what matters; losing click-to-select is acceptable, a blank map is not.
        st.pydeck_chart(built, use_container_width=True, height=548,
                        key=f"plain_{deck_key}")

    if not primed:
        st.session_state["cm_map_primed"] = True
        st.rerun()

    # Clicking a ZIP only highlights it; it never records a review decision.
    picked = _picked_zip(event)
    if picked is not None and picked != selected_zip:
        st.session_state.setdefault("cm_sel_zip", {})[iid] = picked
        st.rerun()

    bar = [dashboard_map.caption(prepared)]
    if prepared.get("selected_zip"):
        bar.append(f"ZIP {prepared['selected_zip']} selected")
    st.markdown(f"<div class='cm-map-cap'>{'  |  '.join(bar)}</div>",
                unsafe_allow_html=True)


def _picked_zip(event: Any) -> str | None:
    """The ZIP code the reviewer clicked, or None.

    Streamlit's pydeck selection payload has shifted shape between versions, so
    this reads defensively and returns None rather than raising if the running
    build reports selections differently.
    """
    try:
        objs = (event.selection or {}).get("objects") or {}
    except (AttributeError, TypeError):
        return None
    for feats in objs.values():
        for f in feats or []:
            z = (f.get("zcta") if isinstance(f, dict) else None) or \
                ((f.get("properties") or {}).get("zcta") if isinstance(f, dict) else None)
            if z:
                return str(z)
    return None


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def render(df: pd.DataFrame, meta: dict, ctx: dict, secondary: Callable[[], None]) -> None:
    _inject_css()
    _header(meta, ctx)
    store = ctx["review_store"]
    dropped = ctx.get("dropped")
    pair_label = ctx.get("compare_label")
    note = ctx.get("perimeter_note")

    pool = dashboard_fires(df, store, meta.get("snapshot_id"))
    sort_choice = _controls()

    # The left side is always the fire list. Change information is shown on each
    # fire row and expanded in the selected-fire panel, rather than through
    # separate change-category buttons.
    view = sort_fires(
        pool,
        sort_choice,
        store=store,
        snapshot_id=meta.get("snapshot_id"),
    )

    # After a review is saved, advance immediately to the next fire still needing
    # work. The reviewed card remains in the queue but moves into Tracking or
    # Reviewed — No Action.
    advance_from = st.session_state.pop("cm_advance_after_review", None)
    if advance_from and not view.empty:
        work_ids = [
            r["irwin_id"] for _, r in view.iterrows()
            if _queue_group(r, store, meta.get("snapshot_id")) == 0
            and r["irwin_id"] != advance_from
        ]
        if work_ids:
            st.session_state["selected_irwin"] = work_ids[0]
        else:
            st.session_state["selected_irwin"] = view.iloc[0]["irwin_id"]


    # Three columns: list | map | selected fire. The map is the visual centre.
    col_l, col_c, col_r = st.columns([0.35, 0.40, 0.25], gap="medium")

    with col_l:
        _snapshot_summary(pool, dropped, pair_label, note)
        st.markdown(f"<div class='cm-count'>Showing <b>{len(view)}</b> of "
                    f"<b>{len(pool)}</b> fires</div>", unsafe_allow_html=True)
        picked = None
        if view.empty:
            st.markdown("<div class='cm-si-none'>No fires match the current filters.</div>", unsafe_allow_html=True)
        else:
            picked = _fire_list(view, st.session_state.get("selected_irwin"),
                                sort_choice, store, ctx)
    if picked and picked != st.session_state.get("selected_irwin"):
        st.session_state["selected_irwin"] = picked
        st.rerun()

    # The selected fire stays put while a change filter narrows the list, so
    # filtering never silently moves the map onto a different fire.
    selected = st.session_state.get("selected_irwin")
    if selected not in set(pool["irwin_id"]):
        selected = view.iloc[0]["irwin_id"] if not view.empty else (
            pool.iloc[0]["irwin_id"] if not pool.empty else None)
        st.session_state["selected_irwin"] = selected

    row = pool[pool["irwin_id"] == selected].iloc[0] if selected is not None else None
    with col_c:
        _map(row, meta, ctx)
    with col_r:
        _panel(row, store, ctx)

    if selected is not None and st.session_state.get("cm_moratorium") == selected:
        st.divider()
        ctx["moratorium_entry"](row)

    st.divider()
    with st.expander("Additional information", expanded=False):
        secondary()