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
