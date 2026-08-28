---
phase: quick-260828-k4q
plan: 01
subsystem: gui-export
status: complete
tags: [batch-export, typeset, qdialog, worker-thread, pyside6]
requires:
  - bake_typeset_page (gui/text_renderer.py — D-01 compositor)
  - batch_export_ocr contract (core/ocr_export.py — abort/progress/{ok,failed,total})
  - default_typeset_path (core/ocr_export.py — D-03 sidecar placement)
  - Phase 2 batch surface (main_window _op_running/_batch_active/progress bar/Cancel Batch)
  - PageSelectionDialog collector template (gui/resize_dialog.py)
provides:
  - PageSelectionDialog (gui/page_select_dialog.py — modal all-checked page picker, selected_indices())
  - TypesetPage dataclass + batch_export_typeset loop (core/ocr_export.py)
  - action_batch_export_typeset + _dispatch_batch_typeset_export + 4 _on_batch_typeset_* handlers (gui/main_window.py)
  - _batch_typeset_total state + identical-to-OCR-batch gating
affects:
  - Batch menu surface (new entry "Export Typeset Pages…")
  - core/ocr_export.py import graph (unchanged — lazy imports only, still Qt/numpy-free at module top)
tech-stack:
  added: []
  patterns:
    - pure-collector QDialog (ResizeDialog shape, per-file _DIALOG_QSS)
    - structural mirror of batch_export_ocr (loop-top Abort, D-10 progress, per-page isolation)
    - .copy() detachment at every worker handoff (T-QHH-01)
key-files:
  created:
    - manga_ai_studio/gui/page_select_dialog.py
    - tests/test_gui_page_select_dialog.py
  modified:
    - manga_ai_studio/core/ocr_export.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_core/test_ocr_export.py
    - tests/test_gui_export.py
decisions:
  - "Progress percents assert the pinned D-10 formula int(i/total*100) -> 0/33/66 for 3 items (the plan prose's 50/100 contradicted its own formula and the existing test_batch_progress_emits precedent)"
  - "TypesetPage.image annotated np.ndarray | None as a never-evaluated string (PEP 563) — zero numpy import at module top, keeping the core module's stdlib-only graph"
  - "Modal collected FIRST and names-only so cancel/Esc churns zero state; flush seam runs only after Export is accepted"
  - "Every image .copy()-detached at dispatch handoff (incl. the canvas path) — _page_image_source's current_image branch returns the live array"
metrics:
  duration: 12 min
  completed: 2026-08-28
  tasks: 3
  files: 6
actuals:
  tokens: 11846
  tasks: 3
  commits: 3
---

# Quick Task 260828-k4q: Batch-menu Export Typeset Pages with per-page selection — Summary

Batch-menu "Export Typeset Pages…" opens a modal all-checked page picker, then bakes + writes ONLY the checked pages to their `{stem}_typeset.png` sidecars (pristine beside the source, geometry-altered in `cleaned/`) on ONE Worker with determinate progress, Cancel, and per-page failure isolation — no per-page Save As dialogs.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | PageSelectionDialog — modal checkable page list (pure collector) | 87ca6d8 | manga_ai_studio/gui/page_select_dialog.py, tests/test_gui_page_select_dialog.py |
| 2 | batch_export_typeset core loop + TypesetPage projection | 809728d | manga_ai_studio/core/ocr_export.py, tests/test_core/test_ocr_export.py |
| 3 | Wire Batch menu entry + dispatch flow + progress surface + tests | 724152e | manga_ai_studio/gui/main_window.py, tests/test_gui_export.py |

## What Was Built

- **Task 1 — PageSelectionDialog** (`gui/page_select_dialog.py`): modal (ApplicationModal) pure collector modeled on ResizeDialog — one checkable `QListWidget` row per page in file order, ALL `Qt.CheckState.Checked` by default; word-wrapped output-contract disclosure ("{stem}_typeset.png beside its source … altered geometry go to cleaned/ … overwritten"); Select All / Select None (blockSignals bulk-check + one Export recompute); Export (AcceptRole, default) enabled iff checked-count > 0; `selected_indices()` is the ONLY result surface (no `result` attribute — the QDialog.result() shadowing rule).
- **Task 2 — core loop** (`core/ocr_export.py`): `TypesetPage` dataclass (path / detached image-or-None / live boxes / pre-computed dest) + `batch_export_typeset` — byte-for-byte structural mirror of `batch_export_ocr`: loop-top-only `Abort` (lazy `worker_thread` import, exact exception identity), D-10 `(percent, name)` progress per page, per-page `except Exception` isolation (None-image → honest ValueError "no image source"; OSError from save conflicts), loguru logs names + error strings only (T-05-05/T-K4Q-02), returns `{"ok", "failed", "total"}`. All Qt/numpy/PIL imports stay lazy inside the function — module-top graph remains stdlib-only (grep-verified).
- **Task 3 — wiring** (`gui/main_window.py`): `action_batch_export_typeset` ("Export Typeset Pages…" — ellipsis per UI-SPEC copywriting) appended to `batch_menu` after the OCR batch entry; `_refresh_action_states` gates it with the IDENTICAL `folder_open and not _op_running and not _batch_active` condition; `_batch_typeset_total` state; `_dispatch_batch_typeset_export` runs the dialog first (names-only → cancel churns nothing), then the Pitfall-7 flush seam (`_snapshot_current_page` + `_flush_current_canvas_mask_to_data_model`), then projects only checked pages — current page from `canvas.get_image_numpy()`, others from `_page_image_source(i)` — with an explicit `.copy()` on EVERY image at handoff (T-QHH-04/T-K4Q-04); ONE `Worker(partial(batch_export_typeset, items), abort_signal=batch_abort_requested)` with progress/result/error/aborted/finished wired to four handler mirrors of the OCR batch (aborted AND finished both to the unconditional cleanup — Pitfall 7), determinate bar + "Exporting typeset pages… 0/N" status, file_table disabled, completion copy "Exported typeset pages for N page(s)." (+ "M page(s) failed — see the log." on mixed runs, "Cancelled" on the cancel path).

## Verification

- Task 1: `pytest tests/test_gui_page_select_dialog.py -x -q` → **5 passed**
- Task 2: `pytest tests/test_core/test_ocr_export.py -x -q` → **18 passed** (13 existing + 5 new)
- Task 3: `pytest tests/test_gui_export.py tests/test_gui_page_select_dialog.py tests/test_core/test_ocr_export.py -x -q` → **41 passed**; extended set + `tests/test_core/test_typeset_bake.py` → **52 passed**
- Full pinned suite: `python -m pytest -q` → **1205 passed, 0 failed** (233s; no flakes observed this run)
- Module purity: `python -c "import manga_ai_studio.core.ocr_export"` OK; grep shows no module-top PySide6/text_renderer/numpy imports (docstring/comment mentions + in-body lazy imports only)

All test runs via the pinned interpreter `C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe -m pytest` (AGENTS.md).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Progress-shape test expectation contradicted the pinned formula**
- **Found during:** Task 2
- **Issue:** The plan's test 4 expected `[(0, name1), (50, name2), (100, name3)]`, but the formula the same plan mandates (`percent = int(i / total * 100)` — the batch_export_ocr D-10 shape) yields `(0, 33, 66)` for 3 items; the existing `test_batch_progress_emits` pins exactly 0/33/66.
- **Fix:** Test asserts the formula-correct `[(0, "page1.png"), (33, "page2.png"), (66, "page3.png")]`; production loop implements the mandated formula verbatim. Docstring records the plan-prose contradiction.
- **Files modified:** tests/test_core/test_ocr_export.py
- **Commit:** 809728d

**2. [Rule 1 - Bug] Test-side Qt API correction**
- **Found during:** Task 1
- **Issue:** `dialog.modality()` does not exist on PySide6 widgets (RED failure in the modality test).
- **Fix:** Assert `dialog.windowModality() == Qt.WindowModality.ApplicationModal` (the accessor `setModal(True)` actually sets).
- **Files modified:** tests/test_gui_page_select_dialog.py
- **Commit:** 87ca6d8

## Auth Gates

None.

## Known Stubs

None — every created component is fully wired (the dialog feeds the dispatch; the loop writes real files; the handlers drive the real status/bar/chip surfaces).

## TDD Gate Compliance

Not applicable — plan type is `execute` (no `type: tdd` frontmatter, no tdd="true" tasks).

## Self-Check: PASSED

- Files exist: page_select_dialog.py, page-Select test file, ocr_export.py modified, main_window.py modified, both test files modified — verified on disk.
- Commits exist: 87ca6d8, 809728d, 724152e — verified via `git log 2c81a08..HEAD`.
- Full suite green: 1205 passed / 0 failed.
