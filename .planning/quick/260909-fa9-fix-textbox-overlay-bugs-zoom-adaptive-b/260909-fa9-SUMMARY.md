---
phase: quick-260909-fa9
plan: 01
subsystem: gui
tags: [canvas, box-item, zoom, handles, keyboard, undo]
requires:
  - EditorCanvas zoom_changed -> apply_overlay_zoom seam (plan 04-08)
  - boxes_modified BEFORE-snapshot undo contract (plan 03-05/07)
provides:
  - "_zoom_pen_width(base, zoom) — zoom-compensated border pen (2/3 vp px on-screen at any zoom)"
  - "Zoom-divided anchoring for CornerHandle/RotationHandle/RedetectHandle/badge + _handle_hit_rect centre (4/zoom)"
  - "_register_box_item apply_overlay_zoom seeding (boxes born at fit-zoom are correct immediately)"
  - "Arrow-key nudge under Move tool with one boxes_modified (undo entry) per burst"
affects:
  - manga_ai_studio/gui/box_item.py
  - manga_ai_studio/gui/canvas.py
tech-stack:
  added: []
  patterns:
    - "device-px offsets of ItemIgnoresTransformations children are divided by the live zoom at the setPos boundary"
    - "burst-coalesced undo: BEFORE-snapshot opened on first press, ONE emit on non-auto-repeat release, safety-net flushes (other key release / mouse press / layer rebuild)"
key-files:
  created:
    - tests/test_gui_textbox_overlay_fixes.py
  modified:
    - manga_ai_studio/gui/box_item.py
    - manga_ai_studio/gui/canvas.py
    - tests/test_gui_boxes.py
decisions:
  - "D-BUG1 pen: scene width = base/zoom, capped at 24 scene px, NO lower floor — on-screen thickness is exactly base viewport px at every zoom; zoom 1.0 stays byte-identical 2/3 so the existing suite passes unchanged"
  - "D-BUG2 anchors: every ignores-transformations device-px offset divided by zoom at the setPos boundary; hit-rect centre moves to local (4/zoom, 4/zoom) so the SCENE-space hit centre stays on the true corner while the painted 8x8 stays centred on the VISIBLE corner"
  - "D-BUG2 seeding: _register_box_item calls apply_overlay_zoom(zoom_factor) once at creation — the single seeding site (pen + handles + hit zones all correct at birth, no forked construction logic)"
  - "D-BUG3 emission reuses the move-commit contract (boxes_modified(before_snapshot)); op-name override 'Nudged N boxes' only for n > 1 — MainWindow's existing handler supplies undo + dirty + geometry-stale for free"
metrics:
  duration: 24 min
  completed: 2026-09-09
status: complete
actuals:
  tokens: 12700
  tasks: 3
  commits: 6
---

# Quick Task 260909-fa9: Fix textbox overlay bugs — zoom-adaptive border, corner-anchored handles/buttons, arrow-key nudging Summary

Zoom-compensated textbox border (~2/~3 viewport px on-screen at any zoom), zoom-divided anchoring so corner handles / angle handle / re-detect button / badge sit exactly on their corners at every zoom (plus creation-time zoom seeding), and arrow-key nudging under the Move tool with one undo entry per key-repeat burst.

## What Was Built

### BUG-1 — Zoom-adaptive border pen (Task 1)

- `box_item.py`: new `_PEN_MAX_SCENE_WIDTH = 24.0` + module helper `_zoom_pen_width(base, zoom)` → `min(base / zoom, cap)` with the `set_hit_zoom` non-positive/non-numeric guard and NO lower floor (2/100 scene px at MAX_ZOOM is the intended constant on-screen minimum).
- `_apply_origin_pen` / `_apply_look_for` derive the width through `_zoom_pen_width(..., self._overlay_zoom)`; `apply_overlay_zoom` re-derives the pen after storing the zoom + propagating `set_hit_zoom` (the `set_inpaint_state` selected-aware path).
- `_INPAINT_DASH_PATTERN` values untouched — Qt dash units are pen-width multiples, so the rendered dash rides the compensated width automatically (one-line comment at the constant).

### BUG-2 — Corner-exact anchoring at every zoom (Task 2)

- `RedetectHandle.reposition` / `RotationHandle.reposition` / `CornerHandle.reposition` gain a `zoom: float = 1.0` param (guarded once at the top) and divide every device-px offset by it: re-detect `(right + 2/z, top - 12/z)`, rotation `(left - 5/z, top - 23/z)`, corner handles `corner - 4/z` per axis.
- `_handle_hit_rect` centre moves from local `(4, 4)` to `(4/zoom, 4/zoom)` — the scene-space hit centre stays exactly on the true corner while the `width * zoom ≈ _HANDLE_HIT_SIZE` viewport-px contract (quick-260824-t64) is unchanged.
- `BoxItem._sync_handles` / `_sync_handles_for_state` / `_reposition_redetect` pass the stored `_overlay_zoom` to every reposition; `refresh_badge` divides the TL-outside offset `(bw + 2)/zoom` and the edge-flip inset `2/zoom`.
- `canvas.py`: `_register_box_item` seeds `item.apply_overlay_zoom(self.zoom_factor)` right after scene insertion (boxes created at fit-to-window zoom are correct at birth); `_on_zoom_changed_reposition_handles` now applies the zoom BEFORE `_sync_handles` (reposition consumes the stored zoom).

### BUG-3 — Arrow-key nudging (Task 3)

- `canvas.py` `keyPressEvent`: arrow-key branch (after F2, before Ctrl+C) gated on MOVE tool + no inline editor + no armed drag + ≥1 selected box; translates every selected rect 1 scene px per press (not gated on `isAutoRepeat` — repeats keep nudging), `setRect` + `_sync_handles` per item (the group-move reposition-only discipline).
- `_flush_pending_nudge`: ONE `boxes_modified` per burst carrying the BEFORE-burst snapshot (`_nudge_before`, opened on the burst's first press); `"Nudged N boxes"` op name only when n > 1 (the move-commit rule). Closes T-fa9-02 (key-repeat at ~30/s cannot flood the BOXES undo stack).
- Flush safety nets: first statement of `keyReleaseEvent` (any non-auto-repeat release), `mousePressEvent` right after the inline-editor guard, and `set_boxes` beside the multi-select reset — a stale pre-burst snapshot can never emit after a layer rebuild.

## Commits

| Task | Phase | Commit | Description |
| ---- | ----- | ------ | ----------- |
| 1 | RED | 8dc548e | test: zoom-adaptive border pen battery (8 failing) |
| 1 | GREEN | 971bd08 | feat: _zoom_pen_width + compensated pen in the three derivation paths |
| 2 | RED | 3f38f68 | test: corner-exact anchoring battery (34 failing) |
| 2 | GREEN | af7d671 | feat: zoom-divided anchors + seeding + slot reorder + BL-probe update |
| 3 | RED | 1524a70 | test: arrow-key nudge battery (7 failing) |
| 3 | GREEN | 3bea8a8 | feat: nudge branch + burst-flush contract + safety nets |

## Verification Results

1. New battery `tests/test_gui_textbox_overlay_fixes.py`: **74 passed** (10 pen incl. helper unit tests + 44 anchoring/seeding + 20 nudge/burst).
2. Regression neighbors `tests/test_gui_boxes.py` + `tests/test_gui_border_states.py` + `tests/test_gui_sfx_editing.py` + new file: **381 passed, 1 environmental flake** (see Notes).
3. Full suite (pinned interpreter): **1409 passed, 1 environmental flake** (`test_gui_ocr_grab.py::test_grab_history_click_recopies_older_entry` — OS-clipboard contention; passes in isolation, subsystem untouched by this task).
4. Existing pen/badge/hit-zone tests at zoom 1.0 pass unchanged — the only edited existing test is the one documented BL-probe anchor update (`mapToScene(QPointF(4.0/zoom, 4.0/zoom))`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Test-side derivation fixes during Task 2 RED→GREEN]**

- **Found during:** Task 2
- **Issue:** (a) The badge TL-outside test initially used a scene with no explicit `sceneRect` — the auto-computed rect includes the badge itself, which flipped the edge case; and a box at (100, 80) legitimately edge-flips inside at zoom 0.25 (the zoom-divided outside offset reaches ~100 scene px above the top). (b) The test's derived on-screen-gap formula treated the badge width as zoom-scaling; the badge ignores transformations so `bw` does NOT scale — the correct device-px gap is `sbr.left()*zoom - (pos.x()*zoom + bw)`.
- **Fix:** Explicit `scene.setSceneRect(0, 0, 1000, 1000)` (the production canvas sets sceneRect to image bounds; the existing edge-flip test precedent), moved the badge-outside box to (300, 300) so the TL-outside branch is exercised at the lowest zoom, and corrected the gap derivation.
- **Files modified:** tests/test_gui_textbox_overlay_fixes.py
- **Commit:** af7d671

**2. [Implementation shape] `_flush_pending_nudge` extracted as a private helper**

- **Found during:** Task 3
- **Issue:** The plan described the flush logic inline at three sites (keyReleaseEvent / mousePressEvent / set_boxes).
- **Fix:** Extracted one `_flush_pending_nudge()` method (guarded no-op) used by all three sites — identical behavior, no triplicated emission logic. The set_boxes flush sits beside `self._group_move = {}` as prescribed; its payload and op-name semantics are exactly the plan's.
- **Files modified:** manga_ai_studio/gui/canvas.py
- **Commit:** 3bea8a8

Otherwise the plan executed exactly as written.

## TDD Gate Compliance

All three tasks are `tdd="true"`: each has a `test(quick-260909-fa9)` RED commit (failing runs recorded: 8 / 34 / 7) followed by a `feat(quick-260909-fa9)` GREEN commit on the same task. Gate sequence verified in git log: 8dc548e → 971bd08 → 3f38f68 → af7d671 → 1524a70 → 3bea8a8.

## Notes

- **Environmental flakes (out of scope, pre-existing):** `tests/test_gui_boxes.py::test_no_ghost_after_undo_and_scroll` failed once during a neighbor run — verified failing identically on the PRISTINE `box_item.py` (git checkout comparison), then passing in a later full run and in isolation (pixel-grab rendering variance). `test_gui_ocr_grab.py::test_grab_history_click_recopies_older_entry` failed once in the full suite (Qt "Unable to obtain clipboard" — OS clipboard contention) and passes in isolation. Both triaged per the quick-260907-sni precedent (STATE.md "pre-existing environmental flakes"); no production code changed for either.
- **Undo-stack note (edge case):** pressing Delete mid-burst (arrow held) produces two coherent history entries (delete-before, then nudge-before) instead of one merged entry — snapshots remain full-list monotonic-time states, so undo is never corrupting. Accepted under the plan's "any other key release" safety-net design.
- The pre-existing unrelated working-tree deletions under `.planning/phases/` were left untouched (not staged by any task commit).

## Needs Visual Verification

Per the plan's verification step 4 (human spot-check):

1. Zoom out to fit-window on a real page — textbox borders stay clearly visible (~2 px on screen); zoom in — the border does not balloon.
2. Corner handles sit exactly ON their box corners at every zoom; the angle (rotation) button hugs 18 px above TL; the amber re-detect button hugs the TR corner.
3. Select a box with V and arrow-key it around; hold a key to repeat; Ctrl+Z undoes the whole burst in one press.
4. Create a box while at fit-to-window zoom — its border/handles are correct immediately (no drift until the next zoom change).

## Self-Check: PASSED

- All 4 key files exist on disk (box_item.py, canvas.py, test_gui_textbox_overlay_fixes.py, test_gui_boxes.py).
- All 6 task commits verified present in git log (8dc548e, 971bd08, 3f38f68, af7d671, 1524a70, 3bea8a8).
- Realized diff: 4 files changed, 829 insertions(+), 36 deletions(-).
