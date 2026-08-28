---
phase: quick-260828-l3l
plan: 01
subsystem: gui-canvas-tools
tags: [canvas, tools, restore, undo, inpaint-correction]
requires:
  - D-06 baseline slot (canvas._original_image_numpy, quick-260826-u9m)
  - bbox-patch image-undo stack (history.push_image_action / pop_image_undo)
  - strip exclusive tool group (09-01/09-02 tools_strip)
provides:
  - ToolMode.RESTORE (7th tool) with O shortcut, green cursor, strip button
  - canvas.restore_committed payload contract {x, y, w, h, pre_patch}
  - MainWindow._on_restore_committed per-stroke write-back
affects: [inpaint correction workflow, tools strip, tool shortcuts]
tech-stack:
  added: []
  patterns: [numpy boolean-mask disc stamping, per-move full-frame numpy->QImage refresh (accepted T-l3l-03)]
key-files:
  created:
    - manga_ai_studio/gui/assets/icons/restore.svg
  modified:
    - manga_ai_studio/core/mask_editor.py
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/tools_strip.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_gui_canvas.py
    - tests/test_gui_tools_strip.py
    - tests/test_history.py
    - tests/test_gui_crop_tool.py
    - tests/test_gui_boxes.py
    - tests/test_mask_editor/test_mask_editor.py
decisions:
  - P-preview suppression over force-exit: a press during Show Original is a silent no-op (plan-documented decision)
  - per-move display refresh builds the QImage straight from the working array, never through set_image_from_numpy (protects the P-preview claim mid-stroke)
  - page-open gating for Restore (NOT baseline-gated) — a missing baseline is a canvas-level safe no-op
  - restore stroke emits no mask_modified — zero mask-undo entries (pure pixel work)
metrics:
  duration: 33 min
  completed: 2026-08-28
actuals:
  tokens: 72000
  tasks: 2
  commits: 2
status: complete
---

# Quick Task 260828-l3l: Restore Eraser Tool — Paint Original Pixel Summary

**One-liner:** 7th canvas tool "Restore" (O) — a green-circled brush that paints the Show Original baseline pixels back over mangled inpaint results, with one bbox-patch undo entry per stroke, current_image sync, session-dirty marking, and zero baseline rebaselining (D-14).

## Tasks Completed

| Task | Name | Commit | Result |
| ---- | ---- | ------ | ------ |
| 1 | Canvas Restore core (enum, pixel-stamp stroke, green cursor, restore_committed) | 1856c44 | 6 new canvas tests pass |
| 2 | Strip button + O shortcut + main_window write-back (+ tests) | d367169 | 4 new tests pass (strip x3, history x1) |

## What Was Built

- **ToolMode.RESTORE** (`mask_editor.py:77`) — the 7th exclusive tool; joins `PAINT_TOOLS` so box interaction is Alt-gated under it (D-15) and the brush-circle cursor shows. `_effective_eraser` untouched (Restore is never an eraser).
- **Restore stroke state machine** (`canvas.py`): press gate (baseline present + not `_showing_original` + dims match, else silent no-op without arming `_is_painting`), numpy disc stamps via boolean-mask assignment (radius `brush_size/2`, clipped to image dims, bbox accumulator), interpolated advance at `max(1.0, brush_size/4)` scene px with endpoint stamp (RoundCap-coverage mirror), per-move display refresh straight from the working array (`.copy()`-detached; never routed through `set_image_from_numpy` mid-stroke).
- **`restore_committed` signal** — emitted exactly once per stroke with `{x, y, w, h, pre_patch}`; `pre_patch` is the pre-stroke snapshot sliced to the clamped (≥1x1) bbox and `.copy()`-detached (payload-aliasing discipline, T-l3l-02). A click (press+release, no move) commits the dot.
- **Green cursor** — pen `QColor(95,208,104,200)` / brush `QColor(95,208,104,60)` (#5fd068, the inpaint palette), branched before the eraser/paint color pick.
- **Strip + window wiring** — `restore.svg` (24x24, #e8e8ea stroke, module-relative resolution per T-l3l-01), `action_restore` placed after Eraser / before Crop, exclusive group holds exactly 7 actions, `action_tool_restore` (checkable + Tools menu + page-open gating in both gating tuples), `(O, ToolMode.RESTORE)` QShortcut, `set_active_tool` sync tuple.
- **`_on_restore_committed`** — mirrors `_on_inpaint_finished`'s order: bbox display refresh via `set_image_from_numpy(composite, bbox)` (capture-gated, so the baseline is never overwritten — D-14 with no extra code) → `image_files[idx].current_image` write-back → `_set_session_dirty()` → `history.push_image_action(x, y, pre_patch)`. Existing Ctrl+Z reverts the whole stroke with zero new history code.

## Test Results

- Task 1 verify: `tests/test_gui_canvas.py` — 46 passed (40 pre-existing + 6 new: stamps-original-pixels, click-dot, no-baseline no-op, P-preview suppression, green cursor, single emission w/ detached payload).
- Task 2 verify: `test_gui_canvas.py + test_gui_tools_strip.py + test_history.py` — 91 passed (3 new strip tests: action/mode + order/tooltip, toggled-path emission + WR-02 silence, page-open gating; 1 new history end-to-end: one undo entry, pop patch == pre-stroke slice, apply restores, current_image sync, dirty title, no mask entries, D-14 baseline-unchanged guard).
- Full suite (pinned interpreter `C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe -m pytest -q`): **1214 passed, 1 failed** in 4m04s. The single failure is `tests/test_gui_boxes.py::test_no_ghost_after_undo_and_scroll` — see Known Issues below.

## Deviations from Plan

**[Rule 3 - Blocking] Four exhaustive-enumeration tests broke when the 7th tool was added** (the plan's `files_modified` did not include them):

1. `tests/test_mask_editor/test_mask_editor.py::test_tool_mode_has_six_members` → renamed to `test_tool_mode_has_seven_members`, expected set + RESTORE.
2. `tests/test_gui_crop_tool.py::test_crop_is_sixth_exclusive_tool` — exact strip-order list → RESTORE inserted after Eraser, before Crop.
3. `tests/test_gui_tools_strip.py` — membership counts 6→7 actions, 8→9 buttons, divider row 6→7, `_ICON_NAMES` + "restore" (also activates the pre-existing icon art-direction test for the new SVG).
4. `tests/test_gui_boxes.py::test_cursor_hidden_for_move_and_crop_visible_for_paint_tools` — iterates ALL ToolModes; RESTORE added to the expected cursor-visible set.

All four are assertion-count updates only; no production behavior changed to accommodate them.

**Test-contract correction (no deviation in production code):** the plan's strip test spec said "`set_active_tool(ToolMode.RESTORE)` ... emits tool_changed" — in this codebase `set_active_tool` deliberately emits NOTHING (WR-02; signals blocked, the single emission path is the strip action's toggled). The test was written to the established contract: user toggled path emits exactly once, programmatic sync emits zero.

## Known Issues (pre-existing, out of scope)

- `tests/test_gui_boxes.py::test_no_ghost_after_undo_and_scroll` fails in the full suite AND in true isolation. Verified pre-existing: it fails identically on pristine pre-task master (119c13a) in a throwaway worktree — it is an environment-level rendering issue (viewport grab reads a partially-tinted frame: expected red-overlay green < 200, got 206), not inter-test state and not caused by this task. Per the task constraints it was documented, not fixed. `test_run_ocr_selected_dispatches_worker_not_inline` (the other named flake) passed in this run's full suite.
- Plan-time full-suite baseline was 1205 passed; this run is 1215 collected (1214 pass + the pre-existing failure above).

## Threat Model Compliance

- T-l3l-01 (icon path): `restore.svg` loads through the existing `_icon()` module-relative resolution (`Path(__file__).parent / "assets" / "icons"`); covered by the strip icon path-containment test.
- T-l3l-02 (ndarray payload): `pre_patch` `.copy()`-detached in `_finish_restore_stroke` before emission; asserted in `test_restore_emits_once_per_stroke` (mutating the payload leaves the canvas intact).
- T-l3l-03 (per-move full-frame refresh): accepted cost documented in `_refresh_restore_display`'s docstring.

## Self-Check: PASSED

- `manga_ai_studio/gui/assets/icons/restore.svg` exists; `ToolMode.RESTORE` present in mask_editor.py, canvas.py PAINT_TOOLS, tools_strip.py, main_window.py (action creation :1089, Tools menu :1171, gating :1374, `_on_restore_committed` :1790, connect :3659, O shortcut :3681, sync :5145).
- Commits verified in `git log`: 1856c44, d367169.
