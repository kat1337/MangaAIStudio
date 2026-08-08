---
phase: 04-ocr-recognition-text-editing
plan: 08
subsystem: gui (box display objects — text overlay tracking + zoom legibility)
tags: [gui, box-item, editor-canvas, text-overlay, overlay-tracking, zoom-clamp, gap-closure, uat-test-1, tdd, pytest-qt]
requires:
  - Phase 04 Plan 01 text-overlay-tracking debug session (.planning/debug/04-01-text-overlay-tracking.md — measured root causes RC-1/2/3)
  - Phase 04 Plan 04 BoxItem text overlay (QGraphicsTextItem child z=120, refresh_text_overlay, _sync_handles)
provides:
  - BoxItem._reposition_text_overlay() — setPos-only geometry sync called from _sync_handles / _sync_handles_for_state / refresh_text_overlay (RC-1)
  - BoxItem.apply_overlay_zoom(zoom) + _overlay_zoom stored zoom — re-derives the §16 font clamp + viewport-px outline on every zoom change (RC-2/RC-3)
  - EditorCanvas._on_zoom_changed_reposition_handles forwards its zoom to apply_overlay_zoom (wheel / zoom_reset / fit_to_window)
  - 7 new regression tests (13 parametrized cases) locking the overlay-tracking + zoom-style contracts
  - 04-UI-SPEC.md deviation notes: 2px outline reinterpreted as viewport-px; §16 clamp implemented via scene-font scaling
affects:
  - UAT test 1 re-verification (the acceptance contract this plan closes)
  - Any future plan touching overlay/badge rendering or canvas zoom handling (viewport-px child philosophy)
tech-stack:
  added: []
  patterns:
    - setPos-only geometry sync: split a lightweight reposition method out of a full re-render so per-mousemove sync paths (canvas calls _sync_handles on every mouseMoveEvent) never rebuild the document
    - stored-zoom style re-derivation: refresh paths without a zoom argument reuse _overlay_zoom so content commits (Inspector/OCR/inline-editor) never reset the style to zoom-1
    - viewport-px pen via zoom inversion: constant-viewport-px outline = 2/zoom scene px (same philosophy as the ItemIgnoresTransformations badge/handles, applied to the text-layout renderer which ignores cosmetic pens)
key-files:
  created: []
  modified:
    - manga_ai_studio/gui/box_item.py
    - manga_ai_studio/gui/canvas.py
    - tests/test_gui_boxes.py
    - .planning/phases/04-ocr-recognition-text-editing/04-UI-SPEC.md
key-decisions:
  - "RC-1 fix is a setPos-only _reposition_text_overlay() called from _sync_handles (per plan): the canvas runs _sync_handles on EVERY mouseMoveEvent during a drag, so a full refresh_text_overlay (setPlainText + document rebuild) per mousemove would be wasteful; the setPos-only split keeps the drag path light while fixing the fixed-scene-position defect."
  - "RC-2/RC-3 apply on a single canvas slot: _on_zoom_changed_reposition_handles now forwards its (previously discarded) zoom argument to item.apply_overlay_zoom(zoom) — wheel zoom (820), zoom_reset (827), and fit_to_window (851) all emit zoom_changed, so the app default fit-to-window zoom on every page load engages the fixes exactly where the outline was invisible."
  - "The §16 clamp is implemented by scaling the SCENE font (clamp(14*zoom, 10, 28)/zoom scene px) rather than the ItemIgnoresTransformations fallback — same rendered [10,28] viewport-px contract, keeps the overlay a normal zoom-scaling child (no jump at clamp boundaries)."
  - "The 2px outline is reinterpreted as VIEWPORT-px (2/zoom scene px): the literal scene-px reading renders a sub-pixel halo below 100% zoom (2710 -> 260 -> 0 dark pixels at 1.0/0.5/0.25, measured in the debug session) — the UAT test-1 legibility truth is the acceptance contract, documented as a spec deviation note in 04-UI-SPEC.md."
requirements-completed: [TEXT-04]
coverage:
  - id: D1
    description: "Text overlay tracks box geometry through move and TL-edge resize — after setRect + _sync_handles the overlay sits INSIDE the moved/resized box rect at the inset position (pen width/2 + 2px), repositioned via a setPos-only _reposition_text_overlay() that does NOT rebuild the document."
    requirement: TEXT-04
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_text_overlay_tracks_box_after_setrect_move"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_text_overlay_tracks_box_after_tl_edge_resize"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_text_overlay_reposition_does_not_rebuild_document"
        status: pass
    human_judgment: false
  - id: D2
    description: "Overlay zoom legibility — the overlay font renders within [10,28] viewport px at every zoom (scene font = clamp(14*zoom, 10, 28)/zoom) and the dark outline stays a constant 2 viewport px (2/zoom scene px), re-applied from the stored _overlay_zoom on zoom change AND on content refreshes."
    requirement: TEXT-04
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_text_overlay_font_clamp_scales_with_zoom"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_text_overlay_outline_width_scales_with_zoom"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_text_overlay_zoom_style_survives_content_refresh"
        status: pass
    human_judgment: false
  - id: D3
    description: "Canvas zoom wiring — the zoom_changed slot forwards its zoom to every box's overlay style (handles reposition as before), so wheel zoom / zoom_reset / fit_to_window all re-derive the clamp + outline."
    requirement: TEXT-04
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_zoom_changed_reapplies_overlay_style_canvas"
        status: pass
    human_judgment: false
  - id: D4
    description: "Visual legibility of the outlined overlay over light AND dark artwork at 100-800% zoom (the UAT test-1 truth) — the mechanical contracts (position, clamp, outline width) are locked by the automated suite, but the on-artwork visual judgment is a human UAT call."
    requirement: TEXT-04
    verification: []
    human_judgment: true
    rationale: "The overlay legibility on real manga artwork (outline visible over light and dark regions at every zoom) is a visual judgment no offscreen test can make — deferred to the UAT test-1 re-verification, exactly as the original D-11 rationale in plan 04-04."
metrics:
  duration: 6 min
  completed: 2026-08-08
  tasks: 2
  files: 4
status: complete
---

# Phase 04 Plan 08: UAT Test 1 Gap Closure — Overlay Geometry Tracking + Zoom Legibility Summary

Closed UAT test 1 (MAJOR) with the three verified root causes from `.planning/debug/04-01-text-overlay-tracking.md` fixed as two TDD tasks: the overlay now tracks the box through every move/resize/zoom path (RC-1), the §16 [10,28] viewport-px font clamp is implemented (RC-2), and the 2px outline is a constant 2 VIEWPORT px so it stays visible at the default fit-to-window zoom (RC-3) — the overlay is now a reliable per-box display surface at every zoom.

## What Was Built

### Task 1 — RC-1: overlay repositions on box move/resize (setPos-only sync in `_sync_handles`)

`manga_ai_studio/gui/box_item.py`:

- **`_reposition_text_overlay()`** — the overlay-position step of `refresh_text_overlay` (pen_w/2 + 2px inset, `setPos` in parent local coords) split into a NEW setPos-ONLY method (documented as no text/document rebuild). `refresh_text_overlay` now delegates geometry to it (the final `setVisible(self._text_overlay_visible)` line stays in the refresh).
- **`_sync_handles`** calls `self._reposition_text_overlay()` after `refresh_badge()` (docstring updated: "Also refreshes the bubble badge and repositions the text overlay so both track the box through move/resize/zoom"). The canvas moves/resizes boxes via `setRect` + `_sync_handles` on every drag-mousemove (canvas.py:1022-1023) and resize commit (1597-1598, 1618-1619), so this ONE change lands the RC-1 fix on every geometry path — including zoom, which also syncs through `_sync_handles`.
- **`_sync_handles_for_state`** also calls it (after the handle loop): selection changes the pen width (2px unselected / 3px selected), which changes the inset (`pen_w/2`), so the overlay inset stays exact on selection change. `itemChange` applies the new pen via `_apply_look_for` BEFORE this runs, so the inset uses the new width.

### Task 2 — RC-2 + RC-3: zoom font clamp [10,28] viewport px + 2-viewport-px outline, zoom forwarded from canvas

`manga_ai_studio/gui/box_item.py`:

- **`_OVERLAY_FONT_BASE = 14.0`** module constant (the §16 base at 100% zoom; `_OVERLAY_FONT` itself unchanged so `test_text_overlay_uses_outlined_text_format` — widthF >= 1.0 at zoom 1.0 -> 2.0 — keeps passing).
- **`self._overlay_zoom = 1.0`** instance field, initialized BEFORE the first `refresh_text_overlay()` in `__init__` so a fresh box renders the zoom-1 style (byte-identical to pre-plan output).
- **`apply_overlay_zoom(zoom)`** — defensive guard `zoom <= 0 -> zoom = 1.0` (T-4-08g: the clamp/zoom and 2/zoom divisions must never divide by zero; canvas `zoom_factor` is always positive so this is defense only), stores `self._overlay_zoom = zoom`, then calls `refresh_text_overlay()`.
- **`refresh_text_overlay`** builds the format from the STORED zoom: `viewport_px = _OVERLAY_FONT_BASE * zoom`; `clamped_vp = min(28.0, max(10.0, viewport_px))`; `font.setPointSizeF(clamped_vp / zoom)` — the rendered viewport-px size stays within [10, 28] at every zoom (UI-SPEC §16); `fmt.setTextOutline(QPen(_OVERLAY_OUTLINE.color(), 2.0 / zoom))` — a constant 2 viewport px (the RC-3 documented deviation). `_OVERLAY_OUTLINE` itself is untouched (zoom-1.0 reference).

`manga_ai_studio/gui/canvas.py`:

- **`_on_zoom_changed_reposition_handles(zoom)`** — parameter renamed `_zoom` -> `zoom` (no longer discarded); the body now calls `item._sync_handles()` AND `item.apply_overlay_zoom(zoom)` per box. This single slot covers wheel zoom (canvas.py:820), zoom_reset (827), and fit_to_window (851) — the app default on every page load (main_window.py:1009), exactly the zoom where the pre-fix outline was invisible.

`.planning/phases/04-ocr-recognition-text-editing/04-UI-SPEC.md` (two scoped edits only):

- **Spacing table "2px Text-overlay outline" row** — appended the 04-08 interpreting note: the 2px is VIEWPORT-px (2/zoom scene px); the scene-px reading renders a sub-pixel halo below 100% zoom, violating the UAT test-1 legibility truth which is the acceptance contract; matches the badge/handle constant-viewport-px philosophy.
- **§16 clamp line** — appended the implementation note: clamp(14*zoom, 10, 28)/zoom scene px rather than the ItemIgnoresTransformations fallback — same rendered [10,28] viewport-px contract, keeps the overlay a normal zoom-scaling child.

## Verification

```
# Task 1 RED (confirmed pre-fix): 2 failed, 1 passed
#   (Test A + Test B fail — overlay stuck at (23,23); Test C passes pre-fix by
#    design — its setPos-only contract is enforced by the <done> grep gate)
python -m pytest tests/test_gui_boxes.py::test_text_overlay_tracks_box_after_setrect_move \
  tests/test_gui_boxes.py::test_text_overlay_tracks_box_after_tl_edge_resize \
  tests/test_gui_boxes.py::test_text_overlay_reposition_does_not_rebuild_document -q

# Task 1 GREEN: 3 passed; grep gates: def _reposition_text_overlay == 1,
# _reposition_text_overlay() >= 3 (from _sync_handles, _sync_handles_for_state,
# refresh_text_overlay)

# Task 2 RED (confirmed pre-fix): all 10 parametrized cases fail
#   (apply_overlay_zoom AttributeError; canvas handler discards its zoom)

# Task 2 GREEN: 10 passed; grep gates: def apply_overlay_zoom == 1,
# _overlay_zoom >= 3 (actual 6), canvas apply_overlay_zoom == 1,
# both UI-SPEC notes present (1 each)

# Suite regression (GUI): 186 passed, 1 deselected (pre-existing flake)
python -m pytest tests/test_gui_boxes.py tests/test_gui_canvas.py -q \
  --deselect tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip

# Full suite: 439 passed (426 baseline + 13 new cases), 0 failed
python -m pytest tests/ -q --deselect tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip
```

## Performance

- **Duration:** 6 min
- **Started:** 2026-08-08T00:46:32Z
- **Completed:** 2026-08-08T00:52:09Z
- **Tasks:** 2 implementation tasks (both `tdd="true"`)
- **Files modified:** 4 (3 code/test + 1 spec)

## Task Commits

Each task was committed atomically as a RED test → GREEN fix pair:

1. **Task 1 RED:** `44d395c` — `test(04-08): add failing tests for overlay geometry tracking on box move/resize (RC-1)` (2 failed pre-fix, 1 passed by design — see Deviations)
2. **Task 1 GREEN:** `d3c967f` — `fix(04-08): reposition text overlay on box move/resize/zoom via setPos-only sync (RC-1)` (3/3 pass)
3. **Task 2 RED:** `0ceef08` — `test(04-08): add failing tests for overlay zoom font clamp + viewport-px outline (RC-2/RC-3)` (all 10 parametrized cases fail pre-fix)
4. **Task 2 GREEN:** `dd2f09a` — `fix(04-08): overlay zoom font clamp [10,28] viewport px + 2-viewport-px outline, zoom forwarded from canvas (RC-2/RC-3)` (10/10 pass)

## Files Created/Modified

- `manga_ai_studio/gui/box_item.py` — `_reposition_text_overlay()` (setPos-only split) + wiring into `_sync_handles` / `_sync_handles_for_state` / `refresh_text_overlay`; `_OVERLAY_FONT_BASE` + `_overlay_zoom` + `apply_overlay_zoom()`; `refresh_text_overlay` builds the format from the stored zoom (clamped font + 2/zoom outline).
- `manga_ai_studio/gui/canvas.py` — `_on_zoom_changed_reposition_handles` forwards its zoom to `item.apply_overlay_zoom(zoom)` alongside `_sync_handles`.
- `tests/test_gui_boxes.py` — two plan-04-08 sections after `test_text_overlay_uses_outlined_text_format` (~line 1100): 3 RC-1 geometry tests + 4 RC-2/RC-3 zoom-style tests (parametrized 0.25/0.5/1.0/4.0) = 7 functions, 13 cases.
- `.planning/phases/04-ocr-recognition-text-editing/04-UI-SPEC.md` — two scoped edits: the 2px-outline viewport-px interpreting note + the §16 clamp implementation note.

## Decisions Made

See the `key-decisions:` frontmatter above. Highlights:

- The RC-1 fix is a setPos-only `_reposition_text_overlay()` (NOT calling `refresh_text_overlay` from `_sync_handles`): the canvas syncs handles on EVERY `mouseMoveEvent` during a drag, and a full document rebuild per mousemove would be wasteful (the plan's exact reasoning, preserved).
- The §16 clamp scales the scene font (`clamp(14*zoom, 10, 28)/zoom` scene px) instead of switching to `ItemIgnoresTransformations` — same rendered [10,28] viewport-px contract with no item-transform discontinuity at the clamp boundaries.
- The 2px outline is a DOCUMENTED deviation: 2 viewport px (2/zoom scene px), matching the badge/handle constant-viewport-px philosophy, because the scene-px reading fails the UAT legibility truth below 100% zoom (and cosmetic pens are not honored by the text-layout renderer — verified in the debug session).
- The stored-zoom contract (`_overlay_zoom`) makes content refreshes (Inspector/OCR/inline-editor commits, auto-number) reuse the current zoom style instead of resetting to zoom-1.

## Deviations from Plan

None — the plan executed exactly as written. Two notes:

1. **RED gate observed 2 failures, not 3 (Task 1)** — `test_text_overlay_reposition_does_not_rebuild_document` passes pre-fix. This was ANTICIPATED by the plan-checker (info-level note): Test C locks the structural "setPos-only" contract, which the `<done>` grep gate (`'_reposition_text_overlay()'` count >= 3) enforces, not an assertion on position. The RED gate is confirmed (Tests A/B fail with the exact diagnosed symptom: overlay stays at (23,23), 0.0 intersection). Not a plan deviation — the plan's own `<done>` accepts the grep gate as the enforcement mechanism.
2. **In-flight grep-gate self-fix (Task 2 GREEN)** — the initial `_on_zoom_changed_reposition_handles` docstring mentioned `apply_overlay_zoom` by name, making the canvas grep count 2 vs the required 1; reworded the docstring (final state satisfies `== 1`). No behavior change; corrected before the commit.

## Issues Encountered

None beyond the anticipated Test-C-pass-pre-fix observation above. The pre-existing flake `tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip` (1px drag-coordinate rounding, verified pre-existing in plans 04-01..04-07) remains deselected in all gates and was NOT touched, per the plan's scope boundary.

## Authentication Gates

None.

## Known Stubs

None. No placeholder text, hardcoded empty values, or unwired data paths introduced. `_overlay_zoom` defaults to 1.0 for fresh boxes (identical rendering to pre-plan output, not a stub).

## Deferred Issues

- `tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip` — pre-existing flake, out of scope, deselected in all runs (already logged to `.planning/phases/04-ocr-recognition-text-editing/deferred-items.md`).

## Threat Surface

No new security-relevant surface. The two trust boundaries hold as planned:

- **T-4-07 (OCR/pasted text → overlay document):** unchanged — the zoom-clamp re-merge uses `QTextCharFormat` + `setPlainText` only (no HTML/rich-text parsing); `test_text_overlay_document_is_plain_not_rich` stays green (full suite).
- **T-4-08g (apply_overlay_zoom zoom argument):** mitigated — `zoom <= 0 -> zoom = 1.0` guard before both divisions (2/zoom, clamp/zoom); canvas `zoom_factor` is always positive (setTransform scale / fitInView m11), so the guard is defensive only.

## TDD Gate Compliance

Plan frontmatter `type: execute`, `gap_closure: true`; both implementation tasks are `tdd="true"`. Gate sequence observed per task (separate RED `test(...)` commit then GREEN `fix(...)` commit):

- **Task 1:** RED `44d395c` — 2/3 tests fail pre-fix with the diagnosed symptom (overlay stale at (23,23) after setRect move; intersection False) — confirmed before implementation. GREEN `d3c967f` — 3/3 pass + grep gates (`def _reposition_text_overlay` == 1, `_reposition_text_overlay()` == 3).
- **Task 2:** RED `0ceef08` — all 4 test functions (10 parametrized cases) fail pre-fix (`apply_overlay_zoom` AttributeError; canvas handler discards its zoom) — confirmed before implementation. GREEN `dd2f09a` — 10/10 pass + grep gates (`def apply_overlay_zoom` == 1, `_overlay_zoom` == 6, canvas `apply_overlay_zoom` == 1, both UI-SPEC notes present).

Both RED→GREEN gates observed. No separate `refactor(...)` commit needed — implementations were clean on first pass.

## Self-Check: PASSED

Created/modified files:
- FOUND: manga_ai_studio/gui/box_item.py
- FOUND: manga_ai_studio/gui/canvas.py
- FOUND: tests/test_gui_boxes.py
- FOUND: .planning/phases/04-ocr-recognition-text-editing/04-UI-SPEC.md

Commits:
- FOUND: 44d395c (test(04-08): add failing tests for overlay geometry tracking on box move/resize (RC-1))
- FOUND: d3c967f (fix(04-08): reposition text overlay on box move/resize/zoom via setPos-only sync (RC-1))
- FOUND: 0ceef08 (test(04-08): add failing tests for overlay zoom font clamp + viewport-px outline (RC-2/RC-3))
- FOUND: dd2f09a (fix(04-08): overlay zoom font clamp [10,28] viewport px + 2-viewport-px outline, zoom forwarded from canvas (RC-2/RC-3))

## Next Phase Readiness

- UAT test 1's mechanical contract is closed: overlay tracks geometry (drag-move, TL-edge resize) and stays legible at every zoom ([10,28] viewport-px font, constant 2-viewport-px outline) — ready for the UAT re-test on real artwork (the visual legibility judgment, D4).
- The stored-zoom pattern (`_overlay_zoom`) means future text-surface work (inline editor, typesetting) reuses the current zoom style automatically; the `apply_overlay_zoom` seam is the single re-derivation point for the canvas zoom paths.

---
*Phase: 04-ocr-recognition-text-editing*
*Completed: 2026-08-08*
