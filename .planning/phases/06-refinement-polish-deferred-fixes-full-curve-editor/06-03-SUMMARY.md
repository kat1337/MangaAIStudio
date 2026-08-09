---
phase: 06-refinement-polish-deferred-fixes-full-curve-editor
plan: 03
subsystem: gui
tags: [qt, pyside6, qactiongroup, typography, toolbar, dialogs, tdd]

# Dependency graph
requires:
  - phase: 05
    provides: ToolsPanel exclusive QActionGroup (tools_panel.py:105-106), the 6th Crop tool action wiring, set_active_tool sync entry points
provides:
  - Checkable+grouped window tool actions — toolbar buttons highlight the active tool in sync with the dock on every entry path (programmatic/shortcut/menu)
  - 14px Body base font (QFont.setPixelSize(14)) on CropDialog, ResizeDialog, LoadTranslationsDialog
  - RED-gate regression test for toolbar checked-state tracking; typography regression tests for all three dialogs
affects: [06-04 (Curves dialog ships at 14px from birth), end-of-phase UAT visual verification, verify-work]

# Actuals (#2632) — pairs with the plan's estimate (24000 tokens) to calibrate future estimates.
actuals:
  tokens: 7600    # chars/4 over the realized diff (~30.4K chars)
  tasks: 2        # tasks completed
  commits: 3      # commits made

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "QToolButton mirrors its default action's checkable state — making the BUTTON checkable alone is a no-op (Pitfall 2); the ACTION must be checkable + in the exclusive QActionGroup"
    - "Exclusive QActionGroup membership shared between window actions and panel actions keeps dock + toolbar in sync (set_active_tool btn.setChecked(True) becomes functional)"
    - "Dialog typography via QFont().setPixelSize(14) on the dialog itself — children inherit; QFontInfo(font).pixelSize() == 14 is the assertion (NOT pointSize)"

key-files:
  created: []
  modified:
    - manga_ai_studio/gui/main_window.py — six window tool actions setCheckable(True) + tools_panel.tool_group.addAction; corrected _make_tool_toolbar_button comment
    - manga_ai_studio/gui/crop_dialog.py — 14px Body base font in __init__
    - manga_ai_studio/gui/resize_dialog.py — 14px Body base font in __init__
    - manga_ai_studio/gui/load_translations_dialog.py — 14px Body base font in __init__ (Consolas 10 paste_edit exception preserved)
    - tests/test_gui_crop_tool.py — test_toolbar_buttons_track_active_tool (RED gate), test_crop_dialog_font_14px
    - tests/test_gui_image_dialogs.py — test_resize_dialog_font_14px
    - tests/test_gui_boxes.py — test_load_translations_dialog_font_14px

key-decisions:
  - "D-10 fix follows RESEARCH Option 1: make the six window tool actions checkable + members of tools_panel.tool_group (no new button-side logic, no toggled connects on window actions — Pitfall 1 prohibition honored)"
  - "D-12 implemented via QFont().setPixelSize(14) (Assumption A4) — not point size; QFontInfo(...).pixelSize() == 14 is the test contract"
  - "Accepted UI-SPEC surface 31 side effect: Tools-menu tool items now render a checkmark on the active tool"

patterns-established:
  - "Toolbar/dock tool sync = actions in ONE exclusive group; buttons are pure mirrors of their default actions"

requirements-completed: [D-10, D-12]

# Coverage metadata (#1602) — one entry per shipped deliverable.
coverage:
  - id: D1
    description: "Toolbar tool buttons highlight the active tool in sync with the dock across all entry paths (programmatic set_active_tool, V/B/R/L/E/G shortcuts, Tools-menu triggers); six window tool actions are checkable members of the exclusive QActionGroup"
    requirement: D-10
    verification:
      - kind: unit
        ref: "tests/test_gui_crop_tool.py#test_toolbar_buttons_track_active_tool"
        status: pass
    human_judgment: false
  - id: D2
    description: "CropDialog, ResizeDialog and LoadTranslationsDialog field values and labels render at 14px Body (QFontInfo pixelSize == 14); LoadTranslations paste area keeps its Consolas 10 mono exception"
    requirement: D-12
    verification:
      - kind: unit
        ref: "tests/test_gui_crop_tool.py#test_crop_dialog_font_14px"
        status: pass
      - kind: unit
        ref: "tests/test_gui_image_dialogs.py#test_resize_dialog_font_14px"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_load_translations_dialog_font_14px"
        status: pass
    human_judgment: false

# Metrics
duration: 6min
completed: 2026-08-09
status: complete
---

# Phase 6 Plan 3: Toolbar Active-Tool Highlight Sync + 14px Dialog Typography Summary

**Six window tool actions made checkable members of the ToolsPanel exclusive QActionGroup (D-10, toolbar buttons now highlight the active tool on every entry path) + 14px Body base fonts on the three existing dialogs via QFont.setPixelSize(14) (D-12)**

## Performance

- **Duration:** 6 min
- **Started:** 2026-08-09T23:10:00Z (approx; first commit 18:11:20 -0500)
- **Completed:** 2026-08-09T23:14:24Z (last commit 18:14:24 -0500)
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- D-10: the six window tool actions (`action_tool_move/brush/rectangle/lasso/eraser/crop`) are now `setCheckable(True)` + members of `tools_panel.tool_group` — `set_active_tool`'s `btn.setChecked(True)` is functional (was a no-op), the exclusive group unchecks the previous tool, and the toolbar + dock always show the same active tool
- RED-gate regression test `test_toolbar_buttons_track_active_tool` covers all five contracts: group membership (Test 4), programmatic path (Test 1), V-shortcut path (Test 2), Tools-menu path (Test 3), dock↔toolbar sync (Test 5) — it FAILED on pre-fix code (`actionGroup() is None`) and passes post-fix
- Corrected the false group-membership comment at `_make_tool_toolbar_button` — the docstring now states the actual mechanism (buttons mirror their checkable default actions; the group's exclusivity unchecks the previous tool)
- D-12: 14px Body base font (`QFont(); f.setPixelSize(14); self.setFont(f)`) right after `super().__init__(parent)` in CropDialog, ResizeDialog, and LoadTranslationsDialog; the Consolas 10 mono exception on the LoadTranslations paste area is untouched
- Typography regression tests asserting `QFontInfo(dialog.font()).pixelSize() == 14` for all three dialogs
- Full suite green: 569 passed (superset of the 552 Phase-5-close baseline)

## Task Commits

Each task was committed atomically:

1. **Task 1: D-10 — window tool actions checkable + in the exclusive group (RED-GREEN)** - `a3c94e8` (test), `e59e88f` (feat)
2. **Task 2: D-12 — dialog field values/labels at 14px Body** - `355bb3d` (feat)

**Plan metadata:** pending final commit

## Files Created/Modified

- `manga_ai_studio/gui/main_window.py` - six window tool actions checkable + added to `tools_panel.tool_group` in `_build_tools_menu`; corrected `_make_tool_toolbar_button` docstring
- `manga_ai_studio/gui/crop_dialog.py` - 14px Body base font in `__init__` (+ `QFont` import)
- `manga_ai_studio/gui/resize_dialog.py` - 14px Body base font in `__init__` (+ `QFont` import)
- `manga_ai_studio/gui/load_translations_dialog.py` - 14px Body base font in `__init__`; Consolas 10 paste_edit preserved
- `tests/test_gui_crop_tool.py` - `test_toolbar_buttons_track_active_tool` (RED gate) + `test_crop_dialog_font_14px`
- `tests/test_gui_image_dialogs.py` - `test_resize_dialog_font_14px`
- `tests/test_gui_boxes.py` - `test_load_translations_dialog_font_14px`

## Decisions Made

- **D-10 implementation** follows RESEARCH Open Question 1 / Option 1: checkable actions in the exclusive group. No `toggled` connects added on window actions (RESEARCH Pitfall 1 — the panel already connects toggled; double connections would double-emit). Verified the QToolButton mirror contract empirically: the button's checkability tracks its default action, so making the ACTION checkable (not the button) is the load-bearing change.
- **D-12 implementation** via `QFont.setPixelSize(14)` per RESEARCH Assumption A4 — exact pixel contract; tests assert `QFontInfo(...).pixelSize() == 14`, never pointSize.
- **Accepted side effect** (UI-SPEC surface 31): the Tools-menu tool items render a checkmark on the active tool.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Toolbar active-tool highlight deferral (deferred-items.md, Phase 1 plan 04 era) closed via RED-GREEN regression
- 05-UI-REVIEW Pillar 3 typography flag (dialog field values/labels at 14px) closed on the three existing dialogs
- The new Curves dialog (plan 06-04) ships at 14px from birth — the D-12 contract extends to it; levels_dialog.py untouched by this plan (per plan scope)
- Full suite at 569 passed, 0 failed

---
*Phase: 06-refinement-polish-deferred-fixes-full-curve-editor*
*Completed: 2026-08-09*

## Self-Check: PASSED

- FOUND: `.planning/phases/06-refinement-polish-deferred-fixes-full-curve-editor/06-03-SUMMARY.md`
- FOUND: `a3c94e8` (test RED), `e59e88f` (feat GREEN Task 1), `355bb3d` (feat Task 2)
- Full suite: 569 passed, 0 failed

