---
phase: quick-260822-gnq-fix-box-move-auto-re-detect-annoyance-br
plan: 01
subsystem: gui-canvas
tags: [canvas, boxes, ocr, ux-fix, regression-guards]
status: complete
requires:
  - Phase 08 masker fit engine (_refit_changed_boxes / derive_page_mask_state)
  - Plan 04-06 OCR dispatcher (Worker + _op_running)
provides:
  - geometry_stale BoxItem marker + RedetectHandle corner affordance
  - EditorCanvas.box_interaction_started / box_redetect_requested signals
  - MainWindow stationary-grace timer (STATIONARY_GRACE_MS = 5000) with _mark_geometry_changed / _on_stationary_grace_timeout / _on_box_redetect_requested / _redetect_single_box
  - OCR dispatch on CURRENT geometry routed by id(pagebox) (STATE.md Phase 08 follow-up closed)
affects:
  - manga_ai_studio/gui/canvas.py
  - manga_ai_studio/gui/box_item.py
  - manga_ai_studio/gui/main_window.py
tech-stack:
  added: []
  patterns:
    - weakref-seamed per-item callback -> canvas-level signal (G-07-6 lifetime discipline)
    - singleshot QTimer interval supplied at start() from a module constant (test-monkeypatchable)
key-files:
  created: []
  modified:
    - manga_ai_studio/gui/main_window.py
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/box_item.py
    - tests/test_gui_boxes.py
    - tests/test_gui_detection_boxes.py
    - tests/test_gui_gap_closure.py
decisions:
  - Refit-on-commit replaced by stale-mark + 5 s stationary grace; _refit_changed_boxes kept intact as the explicit/stationary recompute engine
  - RedetectHandle click wired via canvas-level box_redetect_requested signal; closure holds the item WEAKLY or it breaks the graveyard release (caught by an existing lifetime test)
  - ocr_requested signal kept declared but no longer emitted from _commit_create (grace period supersedes instant D-01 dispatch)
  - OCR routing switched from id(pagebox.box) to id(pagebox) echoed through the worker (T-QG-01); single and batch workers now receive current_box() rects
metrics:
  duration: ~100 min (across two sessions)
  completed: 2026-08-22
  tasks: 3
  commits: 3
actuals:
  tokens: 78000
  tasks: 3
  commits: 3
---

# Quick Task 260822-gnq: Fix box-move auto re-detect annoyance + brush ghost + Move-tool cursor Summary

Box moves became cheap (stale-mark + amber "re-run detection" corner affordance + one automatic detection-fit/OCR after a cancellable ~5 s grace), scrolling can no longer resurrect erased brush strokes, and Move/Pan lost its phantom brush-dot cursor — plus the STATE.md "[Phase 08 follow-up]" OCR birth-geometry fix.

## Tasks Completed

| # | Task | Commit | Key changes |
|---|------|--------|-------------|
| 1 | Decouple move from re-detect; re-run affordance + stationary grace; OCR birth-geometry fix | b204678 | `_mark_geometry_changed` replaces refit-on-commit; `RedetectHandle` (z=160, ItemIgnoresTransformations, amber); `box_interaction_started` cancel seam; `_redetect_single_box` shared engine with D-04 edited-text gate; `_dispatch_ocr_for_box`/`_run_ocr_task`/`run_ocr_all` pass `current_box()` + route by `id(pagebox)` |
| 2 | Brush-stroke scroll ghost + Move-tool cursor | d634ef4 | `FullViewportUpdate` on EditorCanvas; `_update_cursor_visuals` shows the ellipse only under PAINT_TOOLS |
| 3 | Regression guards + full pinned-interpreter run | ed00312 | 8 new guards in test_gui_boxes.py; 2 refit-on-commit contract tests updated; full suite **1031 passed, 0 failed** |

## Verification

- `tests/test_gui_boxes.py`: 209 passed
- `tests/test_gui_canvas.py tests/test_gui_boxes.py`: 237 passed
- Full suite (`python.exe` pinned 3.14.2): **1031 passed, 4 warnings, 0 failed** (~155 s)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Weakref-seamed redetect callback (reference cycle)**
- **Found during:** Task 1 verify
- **Issue:** The first `_install_redetect_hook` closure captured the item strongly, creating `item → _redetect → activate_callback → item`; "dropped" wrappers survived past the graveyard flush (`test_undo_style_commit_with_dropped_refs_no_crash` failed).
- **Fix:** Closure holds a `weakref.ref(item)` (the `set_primary_owner` cycle-discipline precedent); dead weak ref silently ignores the click.
- **Files modified:** manga_ai_studio/gui/canvas.py
- **Commit:** b204678

### Planned-behavior test updates (not defects)

- `test_alt_drag_draw_release_emits_ocr_requested` → rewritten as `..._defers_ocr_to_grace` (instant D-01 dispatch deliberately superseded by the grace period).
- `test_on_canvas_ocr_requested_dispatches_single_box_worker` → rewritten to drive the shortened-grace end-to-end path (waits on observable payload, not the racy `_op_running` flag).
- `test_move_commit_refits_box_and_border` (detection_boxes) → rewritten as `test_move_commit_defers_refit_to_redetect`: move preserves std_dev + marks stale; explicit re-detect re-measures above the gate.
- `test_recompose_after_move_uses_live_geometry` (gap_closure) → asserts NO recompose on commit (birth position preserved), then recompose-at-moved-rect via the explicit redetect path.
- Fixture note: `_blk` SimpleNamespace payloads gained `.text = ""` in the two updated tests (real TextBlock payloads always carry `.text`; fixture-only artifact).

## Known Stubs

None — all affordances, signals, timer paths, and routing are fully wired.

## Self-Check: PASSED

- Commits verified: b204678, d634ef4, ed00312 (git log)
- Full suite green under `C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe`
