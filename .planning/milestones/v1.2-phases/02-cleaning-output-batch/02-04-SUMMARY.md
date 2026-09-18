---
phase: 02-cleaning-output-batch
plan: 04
subsystem: gui-wiring
tags: [export-page, batch-actions, cancel, nav-gate, d-04, d-08, d-09, d-10, d-11, pitfall-5, pitfall-7, tdd, manual-smoke, canvas-desync]
requires:
  - Plan 02-01 save_image_optimized (core/image_io.py — the Export Page write primitive)
  - Plan 02-02 on_page_selected D-11 seam + _last_page_index + ImageFile.mask slot (gui/main_window.py, core/image_file.py)
  - Plan 02-03 batch_detect/batch_clean/batch_detect_and_clean + _run_batch_task (core/batch_runner.py)
  - Phase 1 Worker(QRunnable) + SharableFlag + Abort + WorkerSignals.aborted (gui/worker_thread.py)
  - Phase 1 EditorCanvas get_image_numpy / get_mask / set_mask / has_mask_content (gui/canvas.py)
provides:
  - MainWindow.export_page (PROJ-02 — writes the DISPLAYED canvas image to a user-chosen PNG/JPG via QFileDialog.getSaveFileName; NOT a re-clean, Pitfall 5)
  - MainWindow._dispatch_batch(mode) + batch_detect / batch_clean / batch_detect_and_clean public handlers (FLOW-03 D-01 three-action menu wiring)
  - MainWindow.batch_abort_requested (class Signal) + _cancel_batch + Esc QShortcut (D-09 cancel affordance)
  - MainWindow._on_batch_progress / _on_batch_finished / _on_batch_error / _on_batch_cleanup signal handlers (D-10, D-04, Pitfall 7)
  - MainWindow._batch_active + _batch_mode + _batch_cancelled instance fields (mode-aware progress + cleanup)
  - MainWindow._flush_current_canvas_mask_to_data_model (Bug D root-cause fix — mirrors on_page_selected step 1)
  - MainWindow._refresh_current_page_after_batch (Bug C/D1 mode-aware post-batch UI refresh)
  - T-02-05 navigation-disable-while-running mitigation (file_table.setEnabled(False) at dispatch, re-enabled at cleanup)
  - File-menu Export Page (Ctrl+E) + Batch submenu (Detect / Clean / Detect+Clean) + Tools-menu Cancel Batch + Esc
affects:
  - Phase close (this is the final plan of Phase 02 — completes PROJ-02 + FLOW-03)
tech-stack:
  added: []
  patterns:
    - "One _dispatch_batch(mode) helper parameterized by 'detect' / 'clean' / 'detect_and_clean' drives all three menu actions (avoids triplication; mode picks the Plan 03 task fn + which model paths/backends to resolve)"
    - "Worker constructed with abort_signal=self.batch_abort_requested — auto-injects abort_flag + connects to Worker.abort (worker_thread.py:138-140)"
    - "Cleanup handler connected to BOTH aborted AND finished (Pitfall 7 — Worker.run's finally ALWAYS emits finished, so _op_running is unconditionally cleared; idempotent so the aborted-then-finished double-call is safe)"
    - "navigation-disable (file_table.setEnabled(False)) at dispatch + re-enable at cleanup closes the T-02-05 concurrent-write race on ImageFile.mask during a batch run"
    - "Canvas mask MUST be flushed to ImageFile.mask BEFORE batch dispatch (_flush_current_canvas_mask_to_data_model) — the batch worker operates on the data model, not the live canvas; mirrors on_page_selected step 1 (Bug D root cause)"
    - "Post-batch refresh is mode-aware: detect-only restores the just-detected mask onto the canvas via the D-11 step-4 restore pattern (no cleaned output to reload); clean reloads the page image and clears the canvas overlay (Bug D1 root cause)"
key-files:
  created: []
  modified:
    - manga_ai_studio/gui/main_window.py
    - tests/test_gui_batch.py
decisions:
  - "Bug D (canvas mask lost on batch dispatch) root cause was a cross-plan INTEGRATION defect in the DISPATCH layer, not batch_runner: the canvas mask was never flushed to ImageFile.mask before the worker started, so the batch read None/empty. Fix = _flush_current_canvas_mask_to_data_model mirroring on_page_selected step 1's canvas.get_mask().copy() -> image_file.mask write, called at the top of _dispatch_batch."
  - "Bug D1 (detect-only batch current-page canvas desync + erasure cascade on backwards navigation) root cause was a canvas/data-model DESYNC: _refresh_current_page_after_batch (originally written for Bug C's clean-batch reload) unconditionally cleared the canvas overlay, including for detect-only batches where there is NO cleaned output to reload — leaving the canvas mask-empty while ImageFile.mask was correctly set. The D-11 seam (on_page_selected step 1) then snapshotted that empty canvas back onto the outgoing page's ImageFile.mask on the next navigation, cascading the erasure backwards. Fix = mode-aware refresh (detect restores the mask via the D-11 step-4 pattern; clean keeps reload+clear). The D-11 seam itself was correct throughout and was NEVER touched."
  - "_batch_mode and _batch_cancelled are distinct from _batch_active: _batch_active gates the Cancel action enablement; _batch_mode ('detect' / 'clean' / 'detect_and_clean') routes the mode-aware post-batch refresh; _batch_cancelled disambiguates the cancel path so the cleanup status text can say 'cancelled' rather than 'failed'."
  - "Progress handler is mode-aware: detect mode labels 'Detecting N% — {name}', clean mode labels 'Cleaning N% — {name}' (Bug A — initial implementation hardcoded 'Cleaning' for all three actions, wrong for detect-only)."
  - "The cancel path sets a cancel-specific status text (Bug B — initial implementation left the last progress text stranded)."
metrics:
  duration: 22 min
  completed: 2026-07-25
  tasks: 3
  files: 2
status: complete
---

# Phase 02 Plan 04: MainWindow Wiring (PROJ-02 Export + FLOW-03 Batch) Summary

Wired the Phase 2 UI into MainWindow — the File-menu Export Page action (Ctrl+E, PROJ-02), the three batch actions (Batch Detect / Clean / Detect+Clean, FLOW-03 D-01), the Cancel affordance (Tools menu + Esc, D-09), the progress/result/cleanup signal handlers (D-10, D-04, Pitfall 7), and the navigation-disable-while-running mitigation (T-02-05). This plan connects Plans 01 (image_io) + 02 (mask persistence) + 03 (batch_runner) to the user and is the final plan of Phase 02. Two post-smoke-test fix cycles resolved 5 integration bugs (A/B/C/D/D1); all 6 manual smoke checks now pass and the full suite is green at 156 tests.

## What Was Built

**`manga_ai_studio/gui/main_window.py`** (modified) — the Phase 2 user-facing surface:

- **`MainWindow.batch_abort_requested`** — class-level `Signal()` (declared alongside the QObject class body; an instance attribute would not work for PySide6 signals). Connected to `Worker(..., abort_signal=self.batch_abort_requested)` which auto-injects the shared abort flag + connects to `Worker.abort`.
- **`MainWindow._batch_active: bool`**, **`_batch_mode: str | None`**, **`_batch_cancelled: bool`** — instance fields in `__init__` alongside `_last_page_index` (Plan 02) and `_op_running` (Phase 1). `_batch_active` gates Cancel enablement; `_batch_mode` routes the mode-aware post-batch refresh; `_batch_cancelled` disambiguates the cancel status text.
- **`MainWindow.export_page(self) -> None`** (PROJ-02) — guards on `_op_running` + an open current path; reads `self.canvas.get_image_numpy()` (the DISPLAYED image, NOT a re-clean — Pitfall 5, regression-guarded by `test_export_writes_displayed_image`); picks PNG/JPEG filter from the current page's suffix; calls `QFileDialog.getSaveFileName`; writes via Plan 01's `save_image_optimized(image_rgb, Path(path), original=current)`. Does NOT call any model.
- **`MainWindow._dispatch_batch(self, mode: str) -> None`** — the single shared dispatch helper driving all three menu actions. Guards on `_op_running` + a non-empty `image_files`; resolves model paths via the existing `_resolve_detection_model_path` / `_resolve_inpainting_model_path` helpers (CR-10/CR-11 cache short-circuits prevent re-download) and backends via the existing accessors; derives `cleaned_dir = first.path.parent / "cleaned"` (D-07); picks the Plan 03 task fn + args by mode; **flushes the current canvas mask to the data model before dispatch** (`_flush_current_canvas_mask_to_data_model` — Bug D fix); builds `Worker(task_fn, *args, abort_signal=self.batch_abort_requested)`; connects `progress`/`result`/`error`/`aborted`/`finished`; sets `_op_running = True`, `_batch_active = True`, `_batch_mode = mode`, `_batch_cancelled = False`; disables `file_table` (T-02-05 navigation gate); shows + resets the progress bar; starts on `QThreadPool.globalInstance()`.
- **`MainWindow.batch_detect` / `batch_clean` / `batch_detect_and_clean`** — three thin public handlers each calling `_dispatch_batch("detect" | "clean" | "detect_and_clean")`, so menu actions can connect to named methods.
- **`MainWindow._flush_current_canvas_mask_to_data_model(self)`** (Bug D fix) — mirrors `on_page_selected` step 1: if the current page index is in range and `canvas.has_mask()` is True, `self.image_files[idx].mask = self.canvas.get_mask().copy()`. The batch worker operates on the data model (ImageFile.mask), not the live canvas buffer — so the unsaved canvas mask would otherwise be lost when the worker started reading.
- **`MainWindow._on_batch_progress(self, payload)`** — mode-aware (Bug A fix): unpacks `(percent, name)`; sets the progress bar value; status-bar text labels `"Detecting N% — {name}"` for detect mode or `"Cleaning N% — {name}"` for clean/detect_and_clean mode (D-10).
- **`MainWindow._on_batch_finished(self, summary)`** — D-04 summary text: `Cleaned {ok}/{total} pages` (or `... — {len(failed)} failed, see log` when `failed` is non-empty) for clean/detect_and_clean; `Detected {ok}/{total} pages` for detect-only. Refreshes action states.
- **`MainWindow._on_batch_error(self, worker_error)`** — T-01-08 mirror of `_on_detection_error`: loguru error + `error_chip` + status text.
- **`MainWindow._on_batch_cleanup(self, _args)`** (Pitfall 7 — unconditional) — connected to BOTH `aborted` and `finished` signals (Worker.run's `finally` always emits `finished`, so cleanup always runs). Sets `_op_running = False`, `_batch_active = False`; re-enables `file_table` (T-02-05 mitigation); hides the progress bar; runs the **mode-aware** `_refresh_current_page_after_batch` (Bug C/D1 fix); refreshes action states. Idempotent — the aborted-then-finished double call is safe.
- **`MainWindow._refresh_current_page_after_batch(self)`** (Bug C + Bug D1 fix) — mode-aware:
  - **detect mode** — restores the just-detected mask onto the canvas via the Plan 02 D-11 step-4 restore pattern (`canvas.set_mask(image_files[idx].mask.copy())`). There is no cleaned output to reload for a detect-only batch; the page's mask was just written by the worker and must be reflected on the canvas. (Bug D1 root cause: the original unconditional reload+clear left the canvas mask-empty while ImageFile.mask was set, and the next backwards navigation snapshotted the empty canvas back onto the outgoing page via on_page_selected step 1, cascading the erasure.)
  - **clean / detect_and_clean mode** — reloads the page image (the displayed image did not change for a clean-only batch on the current page) and clears the canvas overlay (Bug C — post-clean UI refresh so the stale detected mask is not left visible on the reloaded image).
- **`MainWindow._cancel_batch(self) -> None`** (D-09) — `if self._batch_active: self.batch_abort_requested.emit(); self._batch_cancelled = True`. The emitted signal sets the shared abort flag; the worker checks it at the next page boundary (loop top, D-09/Pitfall 4) and raises `Abort` → `signals.aborted` → `_on_batch_cleanup`.
- **Menu actions** — File menu extended with Export Page (Ctrl+E) + a Batch submenu (Detect / Clean / Detect+Clean); Tools menu gains Cancel Batch. An Esc `QShortcut` is wired to `_cancel_batch` (mirrors the Phase 1 history QShortcut pattern). `_refresh_action_states` (line 451 region) extended so the batch + export actions are enabled iff a folder is open AND not `_op_running`; Cancel is enabled iff `_batch_active`.

**`tests/test_gui_batch.py`** (modified) — extended with the Plan 04 tests across the three cycles:

- **Initial RED (Task 1):** `test_export_writes_displayed_image`, `test_batch_sets_op_running`, `test_op_running_cleared_after_batch` — the PROJ-02 / D-08 / Pitfall-7 contract. `test_export_writes_displayed_image` monkeypatches `QFileDialog.getSaveFileName`, asserts the file exists, asserts the export did NOT invoke the detect/inpaint models (Pitfall 5), and compares the exported bytes to `canvas.get_image_numpy()`.
- **Fix Cycle 1 RED (4 bugs):** regression tests for Bug A (wrong detect label), Bug B (cancel status text), Bug C (post-clean UI refresh), Bug D2 (mask-edit flush before batch dispatch). All carry `@pytest.mark.gui`.
- **Fix Cycle 2 RED (Bug D1):** `test_detect_only_batch_does_not_clear_current_page_mask` (canvas desync — after a detect-only batch the current page's canvas mask must survive) and `test_detect_only_batch_does_not_cascade_erasures_backwards` (the navigation cascade — after a detect-only batch on a 2-page folder, navigating away and back must not have wiped either page's mask).

## Task Results

| Task | Name | Commit | Key Files |
| ---- | ---- | ------ | --------- |
| 1 | Extend test_gui_batch.py with the UI-wiring tests (RED) | 2c2d4f6 | tests/test_gui_batch.py |
| 2 | Implement Export Page + batch actions + handlers + cancel + nav-gate (GREEN) | 6ce2446 | manga_ai_studio/gui/main_window.py |
| 3 | Human smoke test of the real-model output path (blocking) | (no code) | (gate only) — approved after 2 fix cycles |

### Fix Cycles (post-smoke-test regressions, all Rule 1 bug fixes)

| Cycle | RED | GREEN | Bugs Closed |
| ----- | --- | ----- | ----------- |
| 1 | 79a206f | bc9ce75 | A (detect label), B (cancel status text), C (post-clean UI refresh), D2 (mask-edit flush) |
| 2 | c664535 | d9ad035 | D1 (detect-only batch current-page canvas desync + erasure cascade on backwards navigation) |

## Verification

- `python -m pytest tests/test_gui_batch.py -x` → all Plan 02 + Plan 04 GUI tests green (6 initial + 4 cycle-1 + 2 cycle-2 = 12 tests in the module).
- `python -m pytest tests/` → **156 passed** (was 150 at checkpoint start: +3 initial, +3 cycle-1, +2 cycle-2; no Phase 1 regression).
- Acceptance grep checks (Task 2) all satisfied: `def export_page`, `def _dispatch_batch`, all three public batch handlers, `_on_batch_progress/finished/error/cleanup`, `_cancel_batch`, `_flush_current_canvas_mask_to_data_model`, `_refresh_current_page_after_batch` all present; `QFileDialog.getSaveFileName` in export_page; `get_image_numpy` as the export source; `abort_signal=self.batch_abort_requested` on Worker construction; BOTH `file_table.setEnabled(False)` (dispatch) and `setEnabled(True)` (cleanup); `self._op_running = False` count >= 2 (existing cleanup + batch cleanup); Ctrl+E / Batch Detect / Cancel Batch menu action definitions; D-04 summary status text.
- **Manual smoke (Task 3, blocking checkpoint — RESOLVED):** all 6 checks pass on the project venv (Python 3.12, numpy<2) with the real CTD + LaMa models and a real manga chapter — (1) Export Page matches the displayed canvas; (2) Batch Detect+Clean cycles the status bar + advances the progress bar + prints the D-04 summary; (3) `cleaned/` outputs are visually clean, no-text pages are byte-identical to source (copy2 passthrough), nothing written to the source folder; (4) Cancel (Esc / Tools → Cancel Batch) stops cleanly after the current page with no truncation and re-enables the editor; (5) review-in-between preserves the edited mask through Batch Clean; (6) navigation is gated during a run.

## TDD Gate Compliance

- RED gate: `test(02-04): add failing GUI suite for export + batch wiring` (2c2d4f6) — suite was RED via `AttributeError: ... no attribute 'export_page'` / `'_run_batch_detect'`.
- GREEN gate: `feat(02-04): wire Export Page + batch actions + cancel + nav-gate` (6ce2446) — all 3 initial tests green; full suite green.
- Two additional RED→GREEN cycles (`79a206f`→`bc9ce75`, `c664535`→`d9ad035`) closed the smoke-test regressions — each followed RED (failing regression test) → GREEN (fix passing it) discipline; the cycle-2 RED correctly FAILED before the GREEN fix (fail-fast rule honored — the D1 bug was real, not a phantom).

## Deviations from Plan

### Auto-fixed Issues (both Rule 1 — bug fixes surfaced by the manual smoke test)

**1. [Rule 1 - Bug] Bug D: canvas mask not flushed to data model before batch dispatch**
- **Found during:** Task 3 smoke test #5 (review-in-between) — an edited mask was lost when a Batch Clean was dispatched.
- **Issue:** The batch worker reads `ImageFile.mask` from the data model, but the live canvas mask is only written back to `ImageFile.mask` by `on_page_selected` step 1 (on navigation). Dispatching a batch without first flushing the canvas mask meant the worker operated on stale/empty data. This was a cross-plan integration defect in the DISPATCH layer (main_window), not batch_runner — batch_runner correctly read whatever was in `ImageFile.mask`.
- **Fix:** Added `_flush_current_canvas_mask_to_data_model()` mirroring `on_page_selected` step 1 (`canvas.get_mask().copy()` → `image_files[idx].mask`), called at the top of `_dispatch_batch`.
- **Files modified:** manga_ai_studio/gui/main_window.py
- **Commit:** bc9ce75

**2. [Rule 1 - Bug] Bug D1: detect-only batch current-page canvas desync + erasure cascade on backwards navigation**
- **Found during:** Task 3 smoke test re-verification after cycle 1 — a detect-only batch left the current page's canvas mask-empty, and navigating backwards propagated the erasure to the previous page.
- **Issue:** `_refresh_current_page_after_batch` (written for Bug C's clean-batch reload) unconditionally cleared the canvas overlay — including for detect-only batches where there is NO cleaned output to reload. This left the canvas mask-empty while `ImageFile.mask` was correctly set by the worker. The D-11 seam (on_page_selected step 1, Plan 02-02) then snapshotted that empty canvas back onto the outgoing page's `ImageFile.mask` on the next navigation, cascading the erasure backwards. The D-11 seam itself was correct throughout — the bug was the desync between canvas and data model introduced by the unconditional refresh.
- **Fix:** Made `_refresh_current_page_after_batch` mode-aware: detect mode restores the just-detected mask onto the canvas via the D-11 step-4 restore pattern (`canvas.set_mask(image_files[idx].mask.copy())`); clean / detect_and_clean mode keeps the reload+clear (Bug C's original intent). The D-11 seam was never touched.
- **Files modified:** manga_ai_studio/gui/main_window.py
- **Commit:** d9ad035

### Minor cosmetic fixes (cycle 1, same GREEN commit bc9ce75)

- **Bug A** — progress handler hardcoded "Cleaning" for all three actions; made mode-aware ("Detecting" for detect).
- **Bug B** — cancel path left the last progress text stranded; added a cancel-specific status text gated on `_batch_cancelled`.

No architectural deviations (Rule 4); no auth gates; no package-install checkpoints. Both fix cycles were Rule 1 bug fixes within the same plan's `files_modified` scope.

## Known Stubs

None. `export_page` writes a real file via `save_image_optimized`; `_dispatch_batch` dispatches a real `Worker` on the real Plan 03 entry points; all signal handlers are fully wired. No placeholder/mock data reaches any caller.

## Threat Flags

None. The implementation introduces no security surface beyond what the plan's `<threat_model>` enumerated, and all mitigations are in place:

- **T-02-01** (export save path tampering) — mitigated by `QFileDialog.getSaveFileName` (OS-validated path); the path is never derived from untrusted input. Regression-guarded by `test_export_writes_displayed_image`.
- **T-02-02** (originals via batch) — the batch output dir is derived (`first.path.parent / "cleaned"`, D-07) and double-guarded by batch_runner's T-02-03 name guard; originals are read-only inputs.
- **T-02-05** (concurrent write/write on `ImageFile.mask`) — THIS PLAN closes it: `file_table.setEnabled(False)` at dispatch prevents `on_page_selected` from firing during the run; `_on_batch_cleanup` re-enables it.
- **T-02-06** (editor stuck disabled, Pitfall 7) — `_on_batch_cleanup` is connected to BOTH `aborted` and `finished` and unconditionally clears `_op_running` + re-enables `file_table`. `test_op_running_cleared_after_batch` is the regression guard.
- **T-02-09** (Esc shortcut hijack) — accepted; Esc is guarded by `if self._batch_active` and bound only to cancel.

No new network endpoints, auth paths, file access patterns, or trust-boundary schema changes were introduced.

## Open Items / Follow-ups

- **Phase 2 follow-up — deliberate re-verification of `cleaned/` output quality.** Smoke-test spot-check #3 passed (outputs visually clean, no-text pages byte-identical to source, files written only into `cleaned/`), but the user has asked for a deliberate re-confirmation before the phase is considered fully shipped. Specifically to re-confirm: outputs are visually clean (text removed, artwork restored); no-text pages are byte-identical to their source (the D-03 copy2 passthrough is not silently re-encoding); files are written ONLY into `cleaned/` and never into the source chapter folder. Captured in STATE.md under Blockers/Concerns.

## Self-Check: PASSED

- [x] `manga_ai_studio/gui/main_window.py` modified (FOUND — export_page, _dispatch_batch, _flush_current_canvas_mask_to_data_model, _refresh_current_page_after_batch, all handlers + menu actions present)
- [x] `tests/test_gui_batch.py` modified (FOUND — 3 initial + 4 cycle-1 + 2 cycle-2 tests)
- [x] Commit 2c2d4f6 exists in git log (FOUND — test(02-04): add failing GUI suite)
- [x] Commit 6ce2446 exists in git log (FOUND — feat(02-04): wire Export Page + batch actions)
- [x] Commit 79a206f exists in git log (FOUND — test(02-04): RED regression for 4 checkpoint bugs)
- [x] Commit bc9ce75 exists in git log (FOUND — fix(02-04): GREEN fix 4 checkpoint bugs)
- [x] Commit c664535 exists in git log (FOUND — test(02-04): RED detect-only desync)
- [x] Commit d9ad035 exists in git log (FOUND — fix(02-04): GREEN mode-aware refresh)
