# Deferred Items — Phase 08-masker-selective-inpaint

Out-of-scope discoveries logged per the executor deviation-rules scope boundary
(do NOT auto-fix issues not caused by the current plan's changes).

| Category | Item | Status | Noted At |
|----------|------|--------|----------|
| Flaky test | `tests/test_gui_boxes.py::test_run_ocr_selected_dispatches_worker_not_inline` fails intermittently in FULL-suite runs (passes in file isolation and on the 08-02 baseline; full-suite runs alternate between green and a single failure). Reproduced with the plan-08-03 files excluded — pre-existing timing/order sensitivity in the Worker dispatch + `qtbot.waitUntil(…, timeout=5000)` under full-suite load, possibly aggravated by the network-touching `test_run_ocr_selected_real_model_end_to_end` that runs just before it. | Open | 2026-08-17 (08-03) |