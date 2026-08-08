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

## 2026-08-08 — toolbar tool-button highlight never functional (during plan 05-07)

- The window's tool actions (`action_tool_move`/`brush`/`rectangle`/`lasso`/
  `eraser`/`crop`) are NOT checkable and NOT members of the ToolsPanel's
  `QActionGroup`; `QToolButton.setChecked` on a button bound to a non-checkable
  default action is a no-op, so `MainWindow.set_active_tool`'s toolbar sync
  never highlights anything (verified by probe: all toolbar tool buttons stay
  unchecked after `set_active_tool`). The comment at `_make_tool_toolbar_button`
  (main_window.py) claims group membership that does not exist. Pre-existing
  since plan 04, out of scope for 05-07 (the accent-highlight contract lives on
  the ToolsPanel, which works); owning plan: any future plan touching the
  toolbar/tool wiring — fix by making the window tool actions checkable and
  adding them to the panel's exclusive group.

