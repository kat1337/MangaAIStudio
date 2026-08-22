---
phase: 09-ui-rework
plan: 03
subsystem: gui
tags: [pyside6, edit-section, default-action, menu-slimming, ui-05, d-08, d-09]
requires:
  - SidePanel/CollapsibleSection API (09-02) — add_section accepts the fourth section; the sidePanel/editExpanded key mechanism was left generic and ready
  - The six live image-op QActions in main_window.py (action_curves, action_crop_dialog, action_resize, action_rotate_cw/ccw/180) with _refresh_action_states gating
provides:
  - manga_ai_studio/gui/side_panel.py EditSection — 2-column QGridLayout of six text QToolButtons bound via setDefaultAction to the LIVE window actions
  - MainWindow._build_edit_section — appends the panel's fourth CollapsibleSection ("Edit", settings_key sidePanel/editExpanded) after _build_menus
  - Slimmed menus per D-09 — Tools menu carries no Rotate ▸ / Curves… / Resize…; Edit menu carries no Crop…; all six QActions stay ALIVE as state/gating holders
  - tests/test_gui_edit_section.py — structure, default-action identity, trigger parity, gating parity, membership negatives, shortcut audit
affects:
  - End-of-phase UAT gate — visual pass over strip accent + panel feel incl. the completed four-section layout
tech-stack:
  added: [] # zero new packages
  patterns:
    - setDefaultAction binding over lambda buttons — enablement/tooltip/status-tip inheritance from the live QActions for free
    - dedicated post-menu build step for a section whose body binds menu-created actions (construction-order constraint)
    - membership-removal-only menu slimming with NOTE comments citing the state-holder precedent
key-files:
  created:
    - tests/test_gui_edit_section.py
  modified:
    - manga_ai_studio/gui/side_panel.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_gui_curves_dialog.py
    - tests/test_gui_crop_tool.py
decisions:
  - Edit section assembly lives in a dedicated MainWindow._build_edit_section() called AFTER _build_menus instead of inside _build_docks' assembly — the six image-op actions do not exist until the menus are built (docks build first); the section self-seeds its editExpanded restore with the same tolerant parse
  - D-08 button order is dialogs-first (Curves… | Crop… / Resize… | Rotate CW) then rotates — UI-SPEC §40's listing order mapped row-major onto the 2-column grid
  - Menu slimming keeps the six QAction constructions and their triggered wiring byte-identical; only addAction/menu lines were removed, each site carrying a NOTE comment citing D-09 and the action_detect_boxes_mode precedent
metrics:
  duration: 14 min
  completed: 2026-08-21
  status: complete
actuals:
  tokens: 6400 # chars/4 over the realized diff (547 insertions / 26 deletions across 5 files)
  tasks: 2
  commits: 2
---

# Phase 9 Plan 03: Edit Section + Menu Slimming Summary

The panel's fourth "Edit" section — a 2-column grid of six text buttons bound via `setDefaultAction` to the live Curves/Crop-dialog/Resize/rotate QActions — plus the D-09 menu slim-down that removes those entry points from the Tools/Edit menus while keeping every QAction alive as a state holder, with zero new op logic and zero keyboard loss.

## What Was Built

- **`EditSection`** (`side_panel.py`): constructor receives the six LIVE window actions; each `QToolButton` gets `ToolButtonTextOnly` + `setDefaultAction(act)` — labels/tooltips/status-tips and `_refresh_action_states` enablement inherited free. Secondary chrome (flat #2d2d33, 1px #3a3a42 border, hover #34343c) + sm (8px) grid gaps per §40. No lambda wiring anywhere.
- **`MainWindow._build_edit_section`** (new step between `_build_menus` and `_build_central_widget`): builds the body, wraps it as CollapsibleSection("Edit", settings_key="sidePanel/editExpanded", provider=self._settings), appends via `side_panel.add_section`, and seeds the restored collapse state through `restore_expanded` (blockSignals — no write-back). D-02 workflow order now complete: Detection settings → Brush → Typesetting → Edit.
- **Menu slimming (D-09)**: `_build_tools_menu` no longer adds the Rotate submenu, Curves…, or Resize…; `_build_edit_menu` no longer adds Crop…. Membership removal ONLY — every QAction construction, tooltip, triggered wiring, and enabled seed is untouched, with NOTE comments citing D-09 at both sites. These actions carry NO shortcuts (before or after); V/B/R/L/E/G window-level QShortcuts and D/C action shortcuts verified intact by test.
- **Tests**: new `tests/test_gui_edit_section.py` (11 tests: workflow-order/persistence key, 2-column×6-button structure, default-action identity, crop TOOL-vs-dialog distinction, `_on_curves`/`_on_crop_dialog` spy parity, real rotate dims-swap, disabled→enabled gating parity, Tools/Edit menu membership negatives, zero-shortcut audit). `test_gui_curves_dialog.py` retargeted to the Edit-section binding contract; `test_gui_crop_tool.py` extended with the D-08 two-distinct-buttons assertion.

## Tasks Completed

| Task | Name | Commit |
| ---- | ---- | ------ |
| 1 | EditSection body — six default-action buttons as the panel's fourth section | a1b3fc8 |
| 2 | Menu slimming (D-09) — remove Image-section and Crop… entries, keep actions alive, verify shortcuts | 38f2fe5 |

## Verification

- Task 1 RED confirmed before implementation (Edit section absent → titles assertion failed); verify green after: 18 passed (edit_section + side_panel files).
- Task 2 quick command green: 72 passed (edit_section + curves + crop_tool + detection_settings); explicit shortcut audit run: tools_strip/canvas/detection_boxes/image_dialogs = 80 passed unchanged.
- Full suite at plan close: **1018 passed, 0 failed** (pinned 3.14.2 interpreter) — strict superset of the 1007 at 09-02 close (+11 new Edit-section/menu-slimming tests).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Edit-section assembly moved to a dedicated post-menu build step**
- **Found during:** Task 1
- **Issue:** The plan placed the section append "in MainWindow panel assembly" (_build_docks), but `_build_docks()` runs BEFORE `_build_menus()` (main_window __init__ order) — the six image-op QActions do not exist yet and binding them would raise AttributeError.
- **Fix:** New `_build_edit_section()` invoked immediately after `_build_menus()`, completing the same D-02 ordering and seeding its own persistence state; documented with a construction-order NOTE in both call sites.
- **Files modified:** manga_ai_studio/gui/main_window.py
- **Commit:** a1b3fc8

### Notes

- Two plan-time assumptions about test targets were corrected on the test side only (no production impact): the strip's tool buttons bind STRIP-OWNED actions (not `window.action_tool_crop` identity — the 09-01 icon-on-strip-actions decision), and V/B/R/L/E/G are window-level QShortcuts rather than action-level setShortcut calls — so the shortcut audit asserts the QShortcut set plus the D/C action shortcuts.
- Task 1 followed RED-first discipline (tests written and observed failing before implementation), committed atomically as one task commit.

## Known Stubs

None — all six Edit buttons are fully wired to production QActions; no placeholder data paths.

## Threat Flags

None — no new trust boundary introduced (button labels/tooltips inherited verbatim from existing plain-text actions, T-09c-01 accept). T-09c-02 mitigation (keyboard-reachability) implemented as the zero-shortcut audit test + the no-setShortcut-touch prohibition honored.

## Self-Check: PASSED

- side_panel.py and tests/test_gui_edit_section.py exist on disk (FOUND).
- Commits a1b3fc8, 38f2fe5 present in git log (FOUND).
- Full suite green post-plan (1018 passed).
