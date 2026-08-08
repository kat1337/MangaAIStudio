---
phase: 05-project-persistence-image-ops-export
plan: 07
subsystem: ui
tags: [pyqt, image-ops, crop, canvas-gesture, dim-out, dialog]

# Dependency graph
requires:
  - phase: 05-02
    provides: core/image_ops.crop_page_with_boxes (exact slices + D-16 drop/clip seam)
  - phase: 05-04
    provides: push_geometry_state stamp-shared undo record (ONE entry per op)
  - phase: 05-06
    provides: _apply_geometry_op orchestration (gate -> flush -> pre-capture -> transform -> write-back -> one undo -> rebaseline -> dirty -> flash)
provides:
  - The 6th exclusive tool: ToolMode.CROP, ToolsPanel button (after Eraser), Tools-menu action, window-level G QShortcut (D-11)
  - Canvas Crop-tool armed-rect state machine: drag defines the rect (CrossCursor, clamped to the page), release ARMS it (drag-then-decide), Enter applies / Esc cancels, 8x8 scene-px minimum no-op
  - Dim-out overlay: 4 composited rects at rgba(0,0,0,0.45), z=880, 1px moat inset, page-clamped
  - crop_committed(QRectF) signal -> _apply_crop -> _apply_geometry_op: exact image+mask slices, D-16 drop/clip with count flash, ONE geometry undo entry, one-press restore, geometry_altered (D-22)
  - CropDialog (Edit menu, surface 24b): X/Y/W/H spinboxes at full page bounds, W−x/H−y live recompute, apply-time re-validation stays-open correction
affects: [05-08 exporter geometry_altered consumers, end-of-phase UAT visual gate (armed-rect feel)]

# Actuals (#2632) — pairs with the plan's `estimate` (30000 tokens) on the SAME scale.
actuals:
  tokens: 16730    # chars/4 over the realized diff (66923 chars, 8 files, 1235 insertions)
  tasks: 3
  commits: 4       # 3 task commits + the docs metadata commit

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "crop apply reuses _apply_geometry_op with the 4-tuple core seam — dropped count captured via a closure dict, single status flash after the op"
    - "armed-rect gesture state machine (drag defines, release arms, Enter/Esc decides) — no commit-on-release, tool stays active"
    - "dim-out overlay as 4 page-clamped composited rects with a 1px moat (z=880 below the preview border z=900)"
    - "crop tests run at zoom_reset() — the 05-09 truncation lesson applied as prevention (exact scene<->viewport round trip)"
    - "programmatic exclusivity must explicitly uncheck: blockSignals swallows QActionGroup unchecking (Qt behavior)"

key-files:
  created:
    - manga_ai_studio/gui/crop_dialog.py
    - tests/test_gui_crop_tool.py
  modified:
    - manga_ai_studio/core/mask_editor.py
    - manga_ai_studio/gui/tools_panel.py
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_gui_canvas.py
    - tests/test_mask_editor/test_mask_editor.py

key-decisions:
  - "G is a window-level QShortcut (the V/B/R/L/E pattern), NOT an action-level setShortcut — a duplicate setShortcut would trigger Qt's 'Ambiguous shortcut overload' (CR-14)"
  - "ToolsPanel.set_active_tool explicitly unchecks the other actions — blockSignals around setChecked swallows the QActionGroup's exclusive unchecking (Qt behavior), leaving the previous tool checked and active_tool() wrong (exposed by the 6th action)"
  - "The dim-out 1px inset is a MOAT: dim rects cover the page minus the crop inflated 1px each side, then are clamped to the page (a crop hugging an edge must not dim outside the page)"
  - "Crop geometry tests run at zoom_reset() so scene<->viewport mapping is exact — the 05-09 truncation lesson applied as prevention instead of tolerance bands"
  - "CropDialog stores result_values (the 05-06 precedent — 'result' shadows QDialog.result()); apply-time re-validation compares against the PAGE bounds, not the spinbox ranges (which tests may widen programmatically)"

patterns-established:
  - "Pattern 1: canvas gesture -> crop_committed(scene QRectF) -> _on_crop_committed (math.floor + clamp) -> _apply_crop -> _apply_geometry_op"
  - "Pattern 2: the 4-tuple core seam's dropped count rides a closure dict into the flash decision (single flash, correct copy)"
  - "Pattern 3: crop armed state is cleared on tool switch / page switch / image replacement (_clear_crop_state)"

requirements-completed: [PROJ-04]

coverage:
  - id: D1
    description: "The 6th exclusive tool — ToolMode.CROP in the enum, ToolsPanel text button after Eraser (exclusive QActionGroup, accent highlight), Tools-menu action, toolbar button, window-level G shortcut; activating it deactivates Brush and vice versa"
    requirement: PROJ-04
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_crop_tool.py#test_crop_is_sixth_exclusive_tool"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_crop_tool.py#test_crop_action_in_tools_menu"
        status: pass
    human_judgment: false
  - id: D2
    description: "Crop-tool armed-rect state machine — drag defines the rect (CrossCursor, clamped to the page), release ARMS it (dim + preview persist), Enter applies (crop_committed) / Esc cancels, tool stays active; <8x8 drags are no-ops; box press/move unchanged while Crop is active; armed state cleared on tool switch"
    requirement: PROJ-04
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_crop_tool.py#test_drag_arms_rect_enter_applies_esc_cancels"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_crop_tool.py#test_small_drag_noop"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_crop_tool.py#test_box_press_still_selects"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_crop_tool.py#test_clamp_to_page"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_crop_tool.py#test_tool_switch_clears_armed_crop"
        status: pass
    human_judgment: false
  - id: D3
    description: "Dim-out overlay — 4 composited rects at rgba(0,0,0,0.45) z=880, 1px moat inset so the cyan dashed border renders unobscured, union == page minus the inflated crop exactly, pairwise non-overlapping, page-clamped"
    requirement: PROJ-04
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_crop_tool.py#test_dim_outlayers_geometry"
        status: pass
    human_judgment: false
  - id: D4
    description: "Crop apply — exact image+mask slices, inside box translated / fully-outside dropped / partial clipped (bbox), dropped-count flash per §Copywriting, ONE geometry undo entry, one Ctrl+Z restores all three incl. the dropped box, geometry_altered True (D-16/D-18/D-22); degenerate calls are silent no-ops (T-05-17)"
    requirement: PROJ-04
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_crop_tool.py#test_crop_apply_drop_clip_count"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_crop_tool.py#test_crop_degenerate_noop"
        status: pass
    human_judgment: false
  - id: D5
    description: "Numeric Crop… dialog (Edit menu, surface 24b) — opens at the FULL page bounds (never empty), Width 1..W−x recomputed when X changes (Height analog), apply-time re-validation corrects out-of-range values in place and keeps the dialog open; dialog Apply runs the same crop semantics as the tool path"
    requirement: PROJ-04
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_crop_tool.py#test_crop_dialog_contract"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_crop_tool.py#test_crop_dialog_apply_end_to_end"
        status: pass
    human_judgment: false

# Metrics
duration: 28min
completed: 2026-08-08
status: complete
---

# Phase 05 Plan 07: Canvas Crop tool — armed-rect state machine with dim-out overlay, D-16 drop/clip apply, and the numeric Crop… dialog

**The phase's only canvas-gesture image op: the 6th exclusive tool (ToolMode.CROP, G shortcut) with a drag-arms/Enter-applies/Esc-cancels state machine, a 4-rect rgba(0,0,0,0.45) dim-out overlay at z=880 with a 1px moat, and an apply path that slices image+mask exactly, drops/clips boxes with the count flash, pushes ONE geometry undo entry (one Ctrl+Z restores everything incl. dropped boxes), and marks geometry_altered — plus the Edit-menu CropDialog (full-bounds spinboxes, W−x/H−y recompute, stays-open re-validation). Both entry points funnel through the plan 05-06 _apply_geometry_op seam with core/image_ops.crop_page_with_boxes.**

## Performance

- **Duration:** 28 min
- **Started:** 2026-08-08T17:28:11Z
- **Completed:** 2026-08-08T17:56:28Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments
- **6th tool (TRACER-ready surface):** `ToolMode.CROP` (the first enum extension — Phase 3's "no 6th tool" stance superseded by D-11), ToolsPanel button after Eraser in the exclusive QActionGroup, Tools-menu action, toolbar button, and a window-level `G` QShortcut (the established V/B/R/L/E pattern). The `set_active_tool` exclusivity fix: `blockSignals` around `setChecked` swallows the group's exclusive unchecking (Qt behavior), so the programmatic path now explicitly unchecks the other actions — `active_tool()` reports the true tool.
- **Armed-rect state machine (TRACER):** drag defines the crop rect (CrossCursor, anchor + cursor clamped to the page), release ARMS it — dim + preview persist (drag-then-decide; no commit-on-release); Enter emits `crop_committed(scene QRectF)` and clears the armed state, Esc cancels, the tool stays active either way; <8x8 scene-px drags are silent no-ops; a press on a box still selects/moves it (crop drags start only on empty canvas); armed state removed on tool switch / page switch / image replacement.
- **Dim-out overlay:** 4 composited rects covering the outside-of-crop region at `rgba(0,0,0,0.45)` z=880 — below the reused cyan dashed preview border (z=900), above the box layer; a 1px moat inset (page minus crop inflated 1px each side) keeps the border unobscured; rects are clamped to the page so a crop hugging an edge dims nothing outside it; constant item count (T-05-18).
- **Apply path:** `_on_crop_committed` int-converts (math.floor) + clamps the scene rect; `_apply_crop` reuses `_apply_geometry_op("crop", geometry=True)` with `crop_page_with_boxes` — exact image+mask slices (D-18), D-16 drop/clip with the dropped count captured from the core seam and flashed per §Copywriting, ONE geometry undo entry, one-press restore of all three stores (incl. the dropped box), `geometry_altered` via the shared path, Show Original re-baseline (D-14). Degenerate calls (w<1 / out-of-bounds) are silent no-ops (T-05-17).
- **Crop… dialog (surface 24b):** X/Y/Width/Height spinboxes initialized to the FULL page bounds (never empty), Width 1..W−x recomputed live when X changes (Height analog), [Cancel][Apply] per the `_DIALOG_QSS` pattern; apply-time re-validation corrects out-of-range values in place and keeps the dialog open (guards programmatic edges only).
- **Suite:** 537 passed / 0 failed at completion (12 new crop tests; the two 5-tool contract tests updated to the 6-tool contract per D-11).

## Task Commits

Each task was committed atomically:

1. **Task 1: ToolMode.CROP + 6th tool button + G shortcut + Tools-menu action** - `15274e1` (feat)
2. **Task 2: Crop-tool armed-rect state machine + dim-out overlay (TRACER)** - `7ed5d20` (feat)
3. **Task 3: Crop apply (drop/clip + count flash + one undo) + numeric Crop… dialog** - `e124b40` (feat)

**Plan metadata:** (final docs commit)

## Files Created/Modified
- `manga_ai_studio/core/mask_editor.py` (MOD) - `ToolMode.CROP` added (the 6th tool, D-11); enum docstring "5 exclusive" -> "6 exclusive"
- `manga_ai_studio/gui/tools_panel.py` (MOD) - Crop button after Eraser in the exclusive group, `_action_to_tool` entry, docstrings; `set_active_tool` explicit-uncheck fix
- `manga_ai_studio/gui/canvas.py` (MOD) - `crop_committed` signal, armed-rect state + `_begin/_advance/_end_crop_drag`, `_show/_clear_crop_dim` (4 rects, z=880, 1px moat, page-clamped), `_apply_armed_crop`/`_cancel_armed_crop`/`_clear_crop_state`, Enter/Esc key dispatch, crop dispatch branch (after box hit-test, before mask tools), cleanup hooks in `set_tool`/`set_image`/`clear`/`_set_image_from_numpy`
- `manga_ai_studio/gui/main_window.py` (MOD) - Tools-menu Crop action + toolbar button + G QShortcut + gating; `_on_crop_committed`, `_apply_crop`, `_on_crop_dialog`, Edit-menu `Crop…` action; `crop_committed` connection in `_wire_tool_actions`
- `manga_ai_studio/gui/crop_dialog.py` (NEW) - `CropDialog`: full-bounds spinboxes, W−x/H−y recompute, apply-time re-validation, `result_values` collector
- `tests/test_gui_crop_tool.py` (NEW) - 12 pytest-qt tests (tool surface, armed-rect contract, dim geometry, box interaction, clamp, tool-switch cleanup, drop/clip/count + one-press undo, dialog contract + end-to-end, degenerate no-op)
- `tests/test_gui_canvas.py`, `tests/test_mask_editor/test_mask_editor.py` (MOD) - 5-tool contract tests updated to the 6-tool contract (D-11)

## Decisions Made
- **`G` is a window-level `QShortcut`, not an action-level `setShortcut`** — the V/B/R/L/E pattern; a duplicate action-level shortcut would trigger Qt's "Ambiguous shortcut overload" (CR-14).
- **`ToolsPanel.set_active_tool` explicitly unchecks the other actions** — `blockSignals` around `setChecked` swallows the QActionGroup's exclusive unchecking (probe-confirmed Qt behavior), leaving the previous tool checked and `active_tool()` wrong. Exposed by the 6th action's dict position; a pre-existing latent defect for the 5 original tools.
- **The dim 1px inset is a moat, and dim rects are page-clamped** — the dim covers the page minus the crop inflated 1px on each side (the 2px dashed border renders unobscured); rects extending past the page (crop hugging an edge) are clamped so nothing dims outside the page.
- **Crop geometry tests run at `zoom_reset()`** — the canvas auto-fits at page load (fractional zoom), and QTest's int viewport delivery drifts the delivered scene rect (the 05-09 artifact). 100% zoom makes the scene<->viewport round trip exact, so the geometry assertions are exact — the 05-09 lesson applied as prevention.
- **`CropDialog` stores `result_values`** (the 05-06 precedent — `result` shadows `QDialog.result()`) and its apply-time re-validation compares against the PAGE bounds, not the spinbox ranges (which a test may widen programmatically).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `set_active_tool` left the previous tool checked (broken exclusivity)**
- **Found during:** Task 1 (`test_crop_action_in_tools_menu` — the menu-action assertion `tools_panel.active_tool() == CROP`)
- **Issue:** `blockSignals(True)` around `act.setChecked(True)` suppresses the QActionGroup's exclusive unchecking (Qt reacts to the action event, which blocked signals swallow) — both the new and the old tool stayed checked, and `active_tool()` (first-checked in dict order) reported the WRONG tool. Latent for the original 5 tools (never exercised through this path); the 6th action's dict position exposed it.
- **Fix:** `ToolsPanel.set_active_tool` explicitly unchecks every other checked action (still signal-blocked — no `tool_changed` re-emission).
- **Files modified:** `manga_ai_studio/gui/tools_panel.py`
- **Verification:** menu-action trigger + G shortcut both leave exactly one checked action; `active_tool()` == the active tool; full suite green
- **Committed in:** 15274e1 (Task 1 commit)

**2. [Rule 1 - Bug] Dim rects extended past the page when the crop hugged an edge**
- **Found during:** Task 2 (`test_clamp_to_page` — union-area assertion)
- **Issue:** the moat's left/right rects span `y-1 .. y+h+1`; with a crop at the bottom page edge the rect extended 1px BELOW the page (union area included 1px outside the page).
- **Fix:** each dim rect is intersected with the page rect before being added (nothing may dim outside the page).
- **Files modified:** `manga_ai_studio/gui/canvas.py` (`_show_crop_dim`)
- **Verification:** `test_dim_outlayers_geometry` + `test_clamp_to_page` union-area assertions pass
- **Committed in:** 7ed5d20 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both fixes are correctness requirements of the plan's own contracts (exclusive-group behavior; exact dim coverage). No scope creep.

## Issues Encountered
- **Toolbar tool-button highlight never worked** (pre-existing since plan 04, out of scope): the window's tool actions are not checkable and not in the panel's group, so `QToolButton.setChecked` is a no-op — probe-verified after Task 1's toolbar-sync assertion failed. The accent-highlight contract lives on the ToolsPanel (works, tested); the toolbar quirk is logged to `deferred-items.md` for the plan that owns the toolbar wiring.
- **Test viewport drift at the fit zoom:** QTest delivers int viewport coords at the fractional auto-fit scale, drifting the delivered scene rect by up to ~3.6px (the documented 05-09 artifact). Solved by running crop tests at `zoom_reset()` (exact round trip) instead of tolerance bands.
- **Multi-line git commit message broke PowerShell quoting** (Task 3 commit) — the message was split at newlines into pathspecs; retried with `-m` per line (message content unchanged).

## User Setup Required

None - no external service configuration required.

## Known Stubs

None - no placeholder values, empty data sources, or un-wired components in the plan's files.

## Self-Check: PASSED

- Files verified on disk: crop_dialog.py, test_gui_crop_tool.py, canvas.py, main_window.py, tools_panel.py, mask_editor.py
- Commits verified in git log: 15274e1 (Task 1), 7ed5d20 (Task 2), e124b40 (Task 3)
- Full suite at completion: 537 passed / 0 failed

## Next Phase Readiness
- `_apply_crop` completes the plan 05-06 `_apply_geometry_op` family (rotate/levels/resize/crop) — every geometry op now sets `geometry_altered` per page, which plan 05-08's exporter reads for the D-22 `_ocr.json` location rule.
- The armed-rect gesture pattern (drag-arms/Enter-decides) is the reference for any future canvas gestures.
- End-of-phase UAT gate: the crop gesture feel (dim opacity, moat, Enter/Esc responsiveness) is the visual judgment item deferred to the phase's end-of-phase verify mode.

---
*Phase: 05-project-persistence-image-ops-export*
*Completed: 2026-08-08*
