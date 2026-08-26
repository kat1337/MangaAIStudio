---
phase: quick-260825-wfy
plan: 01
subsystem: gui
tags: [rotation, qt-graphics, boundingrect, inspector, spinbox, tdd]
requires: [quick-260824-viq rotation_deg style field + RotationHandle, quick-260825-uzv handle press dispatch]
provides:
  - delta-based rotation preview (live − baked) in TypesetOverlayItem/BoxItem.preview_rotation
  - rotation-aware TypesetOverlayItem.boundingRect (no straight-edge clipping during preview)
  - Inspector size_spin range 0..1024 matching the TextStyle model clamp
affects: [canvas rotation drag UX, inspector font-size entry]
tech-stack:
  added: []
  patterns: [baked-angle tracking + delta transform, prepareGeometryChange-before-mutation discipline, QTransform mapRect for rotated bounds]
key-files:
  created: []
  modified:
    - manga_ai_studio/gui/box_item.py
    - manga_ai_studio/gui/inspector_panel.py
    - tests/test_gui_sfx_editing.py
    - tests/test_gui_inspector_styling.py
decisions:
  - _baked_rotation lives on TypesetOverlayItem (next to the pixmap it describes); BoxItem.preview_rotation reads overlay._baked_rotation to compute the delta
  - prepareGeometryChange fires BEFORE both setRotation mutations (preview + clear) so Qt repaints/releases the enlarged boundingRect
  - boundingRect returns the byte-identical legacy base rect at rotation ≈ 0; only the active-preview path maps through QTransform rotate-about-origin
actuals:
  tokens: 12000   # chars/4 over the realized diff (294 insertions / 13 deletions across 4 files)
  tasks: 2
  commits: 2
status: complete
---

# Quick Task 260825-wfy: Fix rotation drag UX (double rotation, preview clipping, font-size cap) Summary

**One-liner:** Rotation drag now applies the (live − baked) delta so already-rotated boxes track the mouse without doubling or snapping, a rotation-aware boundingRect ends straight-edge clipping during preview, and the Inspector accepts font sizes up to the model max of 1024.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Delta-based rotation preview + rotation-aware boundingRect | 905fade | manga_ai_studio/gui/box_item.py, tests/test_gui_sfx_editing.py |
| 2 | Raise Inspector font-size spinbox cap to model max 1024 | bd0c238 | manga_ai_studio/gui/inspector_panel.py, tests/test_gui_sfx_editing.py, tests/test_gui_inspector_styling.py |

TDD gates honored per task: RED confirmed against pre-change code (delta test failed on missing `_baked_rotation`; spinbox tests failed at `200 == 800`), then GREEN.

## What Was Built

### Task 1 — box_item.py
- `TypesetOverlayItem._baked_rotation` tracks the angle baked INTO the cached pixmap; set by the `_render_rotated` branch of `set_content`, reset to 0.0 on the empty-text path AND the straight-through unrotated path (no stale bake on rotated→unrotated re-renders).
- `BoxItem.preview_rotation` applies `delta = _normalize_rotation(live − baked)` instead of the absolute live angle — an ALREADY-ROTATED box previews only the mouse DELTA and `_commit_rotation` re-renders at live with NO visible snap.
- `preview_rotation` and `clear_preview_rotation` call `prepareGeometryChange()` BEFORE mutating rotation so Qt repaints the enlarged extents.
- `boundingRect` is rotation-aware: legacy base rect when `|rotation| ≤ 1e-6`, otherwise the base rect mapped through `QTransform().translate(origin).rotate(rot).translate(-origin)`.
- Canvas `_advance_rotation`/`_commit_rotation` untouched — their live-angle contract becomes correct as-is with the delta preview.

### Task 2 — inspector_panel.py
- `size_spin.setRange(0, 1024)` matching the `TextStyle.font_size_px` clamp (1..1024, 0 = Auto sentinel D-15).
- Stale "0..200" prose updated at all three sites (~line 35 docstring, ~line 63 security note, ~line 479 inline comment).

## Test Results

- `tests/test_gui_sfx_editing.py`: **31 passed** (20 pre-existing + 11 new: delta-over-baked, from-zero parity, clear parity, D-01 placement spot-check vs direct render, empty-text reset, unrotated-rerender reset, boundingRect identity at 0, boundingRect containment of mapped corners, prepareGeometryChange spy, spinbox range endpoints, 800px round-trip).
- Full suite under the pinned interpreter (`C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe -m pytest -q`): **1153 passed** across two runs (baseline 1138 + additions), with the flaky-test observations below.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated old-max assertion in tests/test_gui_inspector_styling.py**
- **Found during:** Task 2 full-suite verify
- **Issue:** `test_styling_section_present` pinned `panel.size_spin.maximum() == 200` — the plan's action step anticipated "tests asserting the old max" but listed no file.
- **Fix:** Assertion + comment updated to 0..1024 phrasing.
- **Files modified:** tests/test_gui_inspector_styling.py
- **Commit:** bd0c238

**2. [Rule 1 - Bug] Fixed wrong-object attribute reference during implementation**
- **Found during:** Task 1 GREEN run
- **Issue:** First cut read `self._baked_rotation` inside `BoxItem.preview_rotation`; the tracker lives on the `TypesetOverlayItem` child.
- **Fix:** Read `overlay._baked_rotation`. Caught by the existing `test_preview_rotation_is_pure_transform`.
- **Commit:** included in 905fade

### Out-of-scope observations (not fixed, per scope boundary)

Two DIFFERENT GUI tests failed on separate full-suite runs, each passing standalone and in combined-file runs — pre-existing order/timing flakiness unrelated to this task's files (neither touches OCR dispatch or scroll/undo painting):
- Run 1: `tests/test_gui_boxes.py::test_no_ghost_after_undo_and_scroll`
- Run 2: `tests/test_gui_boxes.py::test_run_ocr_selected_dispatches_worker_not_inline`

Both verified green individually after each failure. Logged here for the flakiness record; not addressed.

### Grep findings (Task 2 action 3)

Remaining `200` literals in `manga_ai_studio/gui/` are QColor alpha components (canvas.py:117, 244, 1173, 1176, 2636) — unrelated to font-size handling. No validators/clamps assuming the old cap remain.

## Threat Model Compliance

- T-WFY-01 (raised spinbox bound): accepted — values still clamp through `core/text_style.py from_dict` (1..1024) on commit; GUI cannot inject out-of-model values.
- T-WFY-02 (per-query QTransform map): accepted — single 4-point rect map only while a preview is active (rotation ≠ 0); zero cost at rest.

No new security-relevant surface introduced (UI-only geometry change).

## Self-Check: PASSED

- Commits verified: 905fade, bd0c238 present in `git log`.
- All modified files exist and are tracked.
- Verification greps clean: no `setRange(0, 200)` / `0..200` anywhere in gui/ or tests/.

## Known Stubs

None.
