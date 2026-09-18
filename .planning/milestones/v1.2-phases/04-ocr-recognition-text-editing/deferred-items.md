# Deferred Items — Phase 04 (ocr-recognition-text-editing)

Out-of-scope discoveries logged during execution. These are NOT caused by the
logging plan's changes and are not fixed (scope-boundary rule).

## PRE-EXISTING (re-confirmed in plan 04-02)

### `tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip`

- **First logged:** plan 04-01 (commit history; 04-01-SUMMARY.md "Deferred Issues").
- **Re-confirmed failing in plan 04-02:** full-suite run (`pytest tests/ -q`)
  reports `1 failed, 306 passed`. Same 1px drag-coordinate rounding:
  real-event body-drag lands a box at `(69, 69, 129, 129)` instead of the
  asserted `(70, 70, 130, 130)`.
- **Scope:** a GUI drag-simulation rounding issue. Does NOT exercise
  `translation_parser` or `reading_order` (the plan 04-02 deliverables are
  pure-stdlib headless modules with no GUI/drag code path). Not caused by this
  plan; verified failing identically against pristine pre-04-01 source
  (commit `210a178`) in plan 04-01.
- **Action:** tracked here; not fixed.

## [04-05] Inspector commit path payload aliasing (Pitfall 8 push-side) — OUT OF SCOPE

- **Found during:** plan 04-05 Task 1 GREEN (design review of the inline-editor commit path)
- **Issue:** `main_window._inspector_commit_pre` captures the before-snapshot via
  `canvas.boxes_snapshot()`, whose PageBoxes share the live TextBlock by reference;
  the 04-04 commit handlers mutate `payload.text`/`payload.translation` IN PLACE
  before `boxes_modified.emit(before)`. `history_manager._materialize_snapshot`
  copies each item via `PageBox.copy()` at PUSH-time (after the mutation), so the
  pushed "before" payload carries the POST-edit text — Ctrl+Z after an Inspector
  text edit restores a no-op. The 04-05 inline editor fixed the same aliasing by
  detaching the before-snapshot payloads (`copy.copy`) before mutating
  (`inline_editor.commit()`, test `test_inline_editor_commit_emits_boxes_modified_with_before_state`).
- **Action:** tracked here; not fixed (04-04 code, outside 04-05's files_modified).
  Fix pattern proven in 04-05; apply `copy.copy` per snapshot payload in
  `_inspector_commit_pre` (or detach in `_inspector_commit_post` before the emit).
