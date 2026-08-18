# Deferred Items — Phase 08-masker-selective-inpaint

Out-of-scope discoveries logged per the executor deviation-rules scope boundary
(do NOT auto-fix issues not caused by the current plan's changes).

| Category | Item | Status | Noted At |
|----------|------|--------|----------|
| Flaky test | `tests/test_gui_boxes.py::test_run_ocr_selected_dispatches_worker_not_inline` fails intermittently in FULL-suite runs (passes in file isolation and on the 08-02 baseline; full-suite runs alternate between green and a single failure). Reproduced with the plan-08-03 files excluded — pre-existing timing/order sensitivity in the Worker dispatch + `qtbot.waitUntil(…, timeout=5000)` under full-suite load, possibly aggravated by the network-touching `test_run_ocr_selected_real_model_end_to_end` that runs just before it. | Open | 2026-08-17 (08-03) |
| UX gap (fixed in a later plan) | Deleting a detected box does NOT recompose/refit — the deleted box's auto-mask content lingers in the auto plane until the next §37 refresh trigger (threshold/radius change, re-detect, page load). The plan's refit trigger list (08-07 Task 2 / UI-SPEC §37) covers move/resize/create only; delete was out of scope. A future plan can extend `_refit_changed_boxes` to recompose when a current box disappears from the before-snapshot. | Open | 2026-08-17 (08-07) |