# Deferred Items — Phase 05

Out-of-scope discoveries logged per the executor scope boundary (do NOT fix
here; the owning plan handles them).

## 2026-08-08 — pre-existing test_gui_boxes.py failures (during plan 05-03)

- **`test_moved_box_via_real_events_persists_round_trip`** — fails in the full
  suite AND in isolation: real-event body-drag lands the box at
  (69,69,129,129) instead of (70,70,130,130) — an off-by-one in Qt event
  coordinate handling. File last touched by 04-10 UAT fixes (f400073).
- **`test_run_ocr_selected_dispatches_worker_not_inline`** — fails in the full
  suite but PASSES in isolation: test-ordering flakiness in GUI event tests.

Both are in `tests/test_gui_boxes.py`, untouched by plan 05-03 (pure core
module, not imported by the GUI). Plan 05-09 (same wave) owns the
`test_gui_boxes.py` regression fixes per its plan text.
