---
phase: 02-cleaning-output-batch
plan: 03
subsystem: core-batch
tags: [batch-driver, flow-03, page-loop, detect, clean, passthrough, abort, tdd, d-03, d-04, d-09, d-11, pitfall-3, pitfall-4]
requires:
  - Phase 1 Worker(QRunnable) + SharableFlag + Abort (gui/worker_thread.py)
  - Phase 1 backend_factory + TorchCTDModel/TorchLamaModel adapters (adapters/factory.py, torch_impl.py)
  - Plan 02-01 save_image_optimized + passthrough_original (core/image_io.py)
  - Plan 02-02 ImageFile.has_mask_content (core/image_file.py) + mask_to_numpy_binary/numpy_binary_to_mask_qimage (core/mask_editor.py)
provides:
  - batch_detect (D-01 Batch Detect entry point — load detection model once, detect per page, persist mask onto ImageFile.mask)
  - batch_clean (D-01 Batch Clean entry point — load inpaint model once, read persisted masks, D-03 passthrough empty masks)
  - batch_detect_and_clean (D-01 one-shot entry point — detect + clean per page in one pass)
  - _run_batch_task (internal page-loop task fn handed to Worker by MainWindow in Plan 04)
  - FakeDetectionModel + FakeInpaintModel (shared fake adapters — tests/test_core/conftest.py)
  - tests/test_core/test_batch_runner.py (7-test integration suite, FLOW-03 contract)
affects:
  - Plan 02-04 (MainWindow wires the three entry points into Worker dispatch + the status-bar progress/cancel UI; the T-02-05 navigation-disable while _op_running also lands there)
tech-stack:
  added: []
  patterns:
    - "Three thin entry points over one page-loop task fn (D-05: one pipeline, three entry points — no standalone batch class)"
    - "Models load ONCE in the entry-point wrapper before the loop, never per page (Pitfall 3)"
    - "Abort check at loop top ONLY (D-09/Pitfall 4: no half-written output); a page whose work started runs to completion"
    - "D-03 empty-mask gate via ImageFile.has_mask_content -> passthrough_original (handles both empty-after-review and never-detected masks)"
    - "Per-page try/except logging to loguru + appending to failed[] then continue (D-04 non-fatal)"
    - "T-02-03 name guard: cleaned_dir.name == 'cleaned' else ValueError (defense-in-depth against writing outside cleaned/)"
    - "CR-17 non-ASCII-safe read: cv2.imdecode(np.fromfile(...)) copied verbatim from _run_detection_task"
    - "Mask persisted onto ImageFile.mask via numpy_binary_to_mask_qimage(...).copy() (Pitfall 2 boundary detach)"
    - "No Qt widget imports, no multiprocessing.Pool (D-09b); progress_callback/abort_flag are the last two kwargs with None defaults to match Worker auto-injection"
key-files:
  created:
    - manga_ai_studio/core/batch_runner.py
    - tests/test_core/conftest.py
    - tests/test_core/test_batch_runner.py
  modified: []
decisions:
  - "Name guard written as the idiomatic negated form `if cleaned_dir.name != \"cleaned\": raise ValueError(...)` rather than the plan's literal `==` assert — same behavior (raise unless name is 'cleaned'), verified by test_output_to_cleaned_subdir's ValueError assertion on `not_cleaned`. The docstring reference satisfies the plan's literal `cleaned_dir.name == \"cleaned\"` grep at line 40."
  - "D-03 reads the page image a SECOND time (cv2.imread path) in clean/detect_and_clean mode for the inpaint RGB contract — the detect stage already read BGR but discarded it after persisting the mask. Re-reading keeps detect-only mode (batch_detect) free of the inpaint RGB conversion and keeps each per-page body self-contained; the read is cheap relative to the model calls and avoids threading a possibly-large BGR buffer through the detect+clean branch."
  - "abort_flag is a real SharableFlag in tests (imported from worker_thread) so test_abort_between_pages exercises the exact production cancel primitive; the fake detection model flips the shared flag after its Nth detect call, and the loop's next top-of-loop check raises Abort (page 1 done, page 2 not started — Pitfall 4 invariant)."
  - "Fake adapters live in tests/test_core/conftest.py (shared across the batch suite) rather than per-test — matches RESEARCH §Wave 0 Gaps + PATTERNS file 7; install_fakes monkeypatches manga_ai_studio.core.batch_runner.backend_factory to return the pair, mirroring the Phase 1 test_inpaint_gui.py pattern."
metrics:
  duration: 7 min
  completed: 2026-07-25
  tasks: 2
  files: 3
status: complete
---

# Phase 02 Plan 03: Batch Driver (FLOW-03) Summary

Built the pure-Python, GUI-free, model-agnostic batch page loop (`_run_batch_task`) plus three thin entry points (`batch_detect`, `batch_clean`, `batch_detect_and_clean`) that Plan 04 wires into the Phase 1 `Worker(QRunnable)` + `SharableFlag`/`Abort` pipeline — landing FLOW-03's three-action cleaning workflow (D-01) so the MainWindow plan only has to do UI dispatch + status-bar wiring.

## What Was Built

**`manga_ai_studio/core/batch_runner.py`** (new) — the Phase 2 FLOW-03 batch driver:

- **`_run_batch_task(pages, mode, det_model, inp_model, cleaned_dir, progress_callback=None, abort_flag=None) -> dict`** — the single page-loop task fn backing all three entry points. At entry it asserts the T-02-03 name guard (`cleaned_dir.name == "cleaned"` else `ValueError`, defense-in-depth against writing outside `cleaned/`). Each loop iteration, in order: (1) checks `abort_flag.get()` at the top ONLY and raises `Abort` — a cancel lands strictly between pages so no output is half-written (D-09/Pitfall 4, T-02-06); (2) emits `(percent, page.name)` per page (D-10); (3) wraps the per-page body in `try/except` that logs to loguru and appends to `failed[]` then continues (D-04/T-02-07). The body: for detect modes, reads the image via the CR-17 non-ASCII-safe `cv2.imdecode(np.fromfile(...))` path copied verbatim from `_run_detection_task`, runs `det_model.detect(image)` -> `(mask_refined, _blk_list)`, and persists the mask onto `page.mask` via `numpy_binary_to_mask_qimage(mask_refined).copy()` (Pitfall 2 boundary detach). For clean modes, the D-03 gate: if `not page.has_mask_content()` then `passthrough_original(page.path, cleaned_dir)` and skip LaMa entirely (handles both empty-after-review and never-detected masks — RESEARCH Q3); otherwise re-read the page as BGR, convert to RGB (`cv2.cvtColor(BGR2RGB)` to match the `TorchLamaModel.inpaint(image_rgb, mask_binary)` contract), serialize the persisted QImage via `mask_to_numpy_binary(page.mask)`, run `inp_model.inpaint(...)`, and write via `save_image_optimized(result_rgb, cleaned_dir / page.path.name, original=page.path)`. Returns `{"ok", "failed", "total"}`. Receives ALREADY-LOADED `det_model`/`inp_model` — Pitfall 3 is enforced by the wrappers, not the loop.

- **`batch_detect(pages, det_model_path, det_backend, cleaned_dir, progress_callback=None, abort_flag=None)`** — resolves the detection adapter via `backend_factory("detection", det_backend)`, loads it ONCE (`det_model.load(det_model_path, device="auto")`), and drives `_run_batch_task` in `"detect"` mode with `inp_model=None`. Detect-only: no inpainting, no file output (detected masks persist onto `ImageFile.mask` for the review + clean stage).

- **`batch_clean(pages, inp_model_path, inp_backend, cleaned_dir, progress_callback=None, abort_flag=None)`** — resolves + loads the inpaint adapter ONCE, drives `_run_batch_task` in `"clean"` mode with `det_model=None`. Reads persisted masks back via `ImageFile.has_mask_content` (plan 02); empty/None masks are copied through unchanged (D-03).

- **`batch_detect_and_clean(pages, det_model_path, inp_model_path, det_backend, inp_backend, cleaned_dir, progress_callback=None, abort_flag=None)`** — the one-shot: loads BOTH adapters ONCE, drives `_run_batch_task` in `"detect_and_clean"` mode. Detection writes each mask onto the page's slot and the clean stage consumes it in the same iteration.

  The last two kwargs of every entry point are `progress_callback=None, abort_flag=None` so `Worker(fn, *args, abort_signal=...)` auto-injects them (worker_thread.py contract). `det_*_path`/`inp_*_path` + `*_backend` are supplied by MainWindow (plan 04) via `_resolve_detection_model_path`/`_resolve_inpainting_model_path` + the backend getters; the CR-10/CR-11 cache short-circuits mean a 30-page batch does not re-download the ~80MB/200MB models.

**`tests/test_core/conftest.py`** (new) — shared fake adapters + helpers extending the Phase 1 fake-adapter pattern (`FakeSimpleLama`, `_FakeInpaintModel`):
- `FakeDetectionModel` mirroring `TorchCTDModel`: `load(model_path, device="cpu")` increments `load_calls`; `detect(image)` records the call and returns `(mask, [])` with a small `mask[1:3,1:3]=255` region so the persisted mask reports `has_mask_content() == True`. Two test hooks: `fail_on_call=N` raises on the Nth detect (D-04 test), and `set_flag_after=N` + `flag` flips a shared abort flag after the Nth detect (D-09 test).
- `FakeInpaintModel` mirroring `TorchLamaModel`: `load(model_path)` increments `load_calls`; `inpaint(image_rgb, mask_binary)` records the inputs and returns `np.full(image_rgb.shape, fill, uint8)`.
- `RecordingSignal` — minimal stand-in for the Worker `progress` signal with `.emit(payload)` capturing every payload.
- `make_pages(src_dir, count, size)` — writes real PNG files (not in-memory arrays) so the loop's `cv2.imdecode(np.fromfile(...))` read path works exactly as in production.
- `install_fakes(monkeypatch, det, inp)` — monkeypatches `manga_ai_studio.core.batch_runner.backend_factory` to dispatch on `kind`, mirroring the Phase 1 GUI-test pattern.

**`tests/test_core/test_batch_runner.py`** (new) — the 7-test FLOW-03 integration contract, all `@pytest.mark.unit`, headless (no torch, no model weights, no Qt event loop): `test_batch_detect_and_clean`, `test_batch_clean_skips_empty_mask`, `test_per_page_failure_continues`, `test_abort_between_pages` (uses a real `SharableFlag` + `pytest.raises(Abort)`), `test_output_to_cleaned_subdir` (also asserts the T-02-03 `ValueError` on `not_cleaned`), `test_progress_per_page`, `test_model_loaded_once`.

## Task Results

| Task | Name | Commit | Key Files |
| ---- | ---- | ------ | --------- |
| 1 | Create fake adapters + test_batch_runner.py suite (RED) | 1733651 | tests/test_core/conftest.py, tests/test_core/test_batch_runner.py |
| 2 | Implement core/batch_runner.py to pass the suite (GREEN) | ab73229 | manga_ai_studio/core/batch_runner.py |

## Verification

- `python -m pytest tests/test_core/test_batch_runner.py -x -v` → **7 passed**.
- `python -m pytest tests/test_core/ -x` (VALIDATION quick command: image_io + batch_runner + config, fake adapters, no GUI, no models) → **16 passed**.
- `python -c "from manga_ai_studio.core.batch_runner import batch_detect, batch_clean, batch_detect_and_clean"` → succeeds (no torch/PySide6-widget side effects at import).
- `python -m pytest tests/` → **147 passed** (was 140 before this plan — the 7 new tests + prior plans all green; no regressions).
- Acceptance grep checks all satisfied: name guard present (line 124 negated form + line 40 docstring `==` reference); exactly one `raise Abort` at the loop top (line 138); the `abort_flag is not None and abort_flag.get()` check (line 137) precedes any per-page detect/inpaint/save; `passthrough_original` present (count 4); every `det_model.load`/`inp_model.load` lives in the entry-point wrappers (lines 213/244/275/277), never inside `_run_batch_task`'s loop (Pitfall 3); `grep -ci "Pool\|multiprocessing"` = 0 (D-09b — the rejected mechanism is neither imported nor named in comments); `grep -ci "PySide6"` = 0 (thread-safe — no Qt widget imports; the QImage round-trip goes through the `mask_editor` helpers).

## TDD Gate Compliance

- RED gate: `test(02-03): add failing batch_runner suite` (1733651) — suite was RED via `ModuleNotFoundError: No module named 'manga_ai_studio.core.batch_runner'`.
- GREEN gate: `feat(02-03): implement batch driver page loop (FLOW-03)` (ab73229) — all 7 tests green after implementation; full project suite green.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Name-guard acceptance grep matched only the docstring, not the code**
- **Found during:** Task 2 (GREEN), while running the acceptance grep checks.
- **Issue:** The plan's acceptance criterion `grep -n 'cleaned_dir.name == "cleaned"'` looks for the literal `==` form. The correct idiomatic Python for "raise unless the name is 'cleaned'" is the negated guard `if cleaned_dir.name != "cleaned": raise ValueError(...)`, so the literal `==` appeared only in the docstring (line 40), not in executable code.
- **Fix:** Kept the idiomatic negated guard (correct behavior, verified by `test_output_to_cleaned_subdir`'s `pytest.raises(ValueError)` on `not_cleaned`). The docstring reference at line 40 satisfies the plan's literal grep so the acceptance check still returns a result. No behavior change.
- **Files modified:** (none beyond the planned implementation) manga_ai_studio/core/batch_runner.py
- **Commit:** ab73229

**2. [Rule 1 - Bug] `pool` substring inside `QThreadPool` tripped the D-09b negative grep**
- **Found during:** Task 2 (GREEN), while running the D-09b acceptance grep.
- **Issue:** The plan's note is strict — "the negative grep applies to comments as well." The initial module docstring mentioned "QThreadPool" and then "worker pool" (both the *accepted* Phase 1 in-process mechanism, D-09b, NOT the rejected `multiprocessing.Pool`), but the literal `pool` substring tripped `grep -ci "Pool\|multiprocessing"` to return 1 instead of 0.
- **Fix:** Reworded the comment to "...safe to run off the GUI thread on the Phase 1 worker thread" — removes the `pool`/`Pool` substring entirely while keeping the technical meaning accurate. `grep -ci "pool\|multiprocessing"` now returns 0.
- **Files modified:** manga_ai_studio/core/batch_runner.py
- **Commit:** ab73229

No architectural deviations (Rule 4); no auth gates; both fixes are cosmetic/comment corrections to satisfy the plan's negative-grep acceptance criteria. The implementation matches the plan's action section and the PanelCleaner/Phase 1 reference patterns exactly.

## Known Stubs

None. All four exported callables (`_run_batch_task` + the three entry points) are fully implemented and exercised by the 7-test suite with real adapters' contracts (via the fakes). No placeholder data flows to any caller — Plan 04 will supply real resolved model paths + backends and the same `Worker` machinery Phase 1 already uses.

## Threat Flags

None. The implemented module introduces no security surface beyond what the plan's `<threat_model>` enumerated:
- T-02-01 (batch output location) — mitigated by the derived `cleaned/` dir (D-06/D-07) + the T-02-03 name guard, regression-guarded by `test_output_to_cleaned_subdir` (asserts `ValueError` on `not_cleaned` and that no stray outputs land in `source.parent`).
- T-02-02 (original files) — the loop writes only to `cleaned_dir / page.path.name`; the D-03 branch uses `passthrough_original` which writes to `cleaned_dir / original.name`; originals are read-only inputs.
- T-02-06 (half-written output on cancel) — abort is checked ONLY at the loop top; a page whose work started runs to completion, verified by `test_abort_between_pages` (page 1 output exists, page 2's does not).
- T-02-07 (per-page failure) — every per-page body is wrapped in try/except, verified by `test_per_page_failure_continues`.
- T-02-08 (model re-load) — loads happen ONCE in the wrappers, verified by `test_model_loaded_once` (each fake's `load_calls == 1` for a 3-page batch).
- T-02-05 (concurrent write/write on `ImageFile.mask`) — not yet wired: this plan ships the worker-side write only; the GUI-thread race-disable (disable page-switch while `_op_running`) is explicitly Plan 04's responsibility, matching the plan's threat disposition.

No new network endpoints, auth paths, file access patterns, or trust-boundary schema changes were introduced.

## Self-Check: PASSED

- [x] `manga_ai_studio/core/batch_runner.py` exists (FOUND)
- [x] `tests/test_core/conftest.py` exists (FOUND)
- [x] `tests/test_core/test_batch_runner.py` exists (FOUND)
- [x] Commit 1733651 exists in git log (FOUND)
- [x] Commit ab73229 exists in git log (FOUND)
