---
phase: 04-ocr-recognition-text-editing
fixed_at: 2026-08-06T21:18:13Z
review_path: .planning/phases/04-ocr-recognition-text-editing/04-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 04: Code Review Fix Report

**Fixed at:** 2026-08-06T21:18:13Z
**Source review:** `.planning/phases/04-ocr-recognition-text-editing/04-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (1 critical CR-01, 5 warnings WR-01..WR-05)
- Fixed: 6
- Skipped: 0

All in-scope findings were fixed. Each fix is a separate atomic commit on the
`gsd-reviewfix/04-*` branch (fast-forwarded onto `master`). Each fix includes
a regression test; the full suite runs 426 passed with only the known
pre-existing GUI drag flake (`tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip`)
failing, which also fails at the base commit in the unmodified main repo.

## Fixed Issues

### CR-01: Inspector commit pushes an aliased pre-edit snapshot — undo of Inspector edits is a no-op

**Files modified:** `manga_ai_studio/gui/main_window.py`, `tests/test_gui_boxes.py`
**Commit:** `456898a`
**Applied fix:** `_inspector_commit_pre` now detaches every snapshot payload
(`pb.payload = copy.copy(pb.payload)`) before the commit handlers mutate the
shared TextBlock in place — the exact Pitfall-8 pattern `InlineEditor.commit`
uses. Without the detach, `history.push_boxes_state`'s push-time `PageBox.copy()`
ran AFTER the mutation and stored the post-edit text, making Ctrl+Z a no-op.
Added `test_inspector_commit_undo_restores_pre_edit_text`, which drives the
real commit handler (`_on_inspector_recognized_committed`), asserts the pushed
before-snapshot carries the pre-edit text with a detached payload, and
round-trips a full `on_undo()` restore.

### WR-01: Unchanged Inspector field focus-cycles still commit — spurious `edited=True`, accidental manual-override pinning, and no-op undo pushes

**Files modified:** `manga_ai_studio/gui/inspector_panel.py`, `tests/test_gui_boxes.py`
**Commit:** `5deabd2`
**Applied fix:** The panel now remembers the values each field displayed at
`load_box` time (the InlineEditor `_entry_text` pattern, read back from the
widgets so Qt text normalization cannot create a phantom diff) and the commit
wiring routes through `_emit_recognized_if_changed` / `_emit_translation_if_changed`
/ `_emit_bubble_if_changed` — a focus-out / `editingFinished` commit whose
value is unchanged is a silent no-op (no `edited=True` flip, no
`manual_override=True` pin on a box that never had a bubble number, no no-op
BOXES push). `clear()` resets the loaded-value memory. The Vertical checkbox
needs no guard (`toggled` only fires on a real change; `load_box` blocks it).
Added three tests: panel-level no-op focus cycles, a real bubble change still
committing, and an end-to-end MainWindow test asserting no push / no flag
flips.

### WR-02: XY-Cut cluster walk measures gaps against the previous cluster START, not the previous box — spurious column fragmentation

**Files modified:** `manga_ai_studio/core/reading_order.py`, `tests/test_core/test_reading_order.py`
**Commit:** `a0aabe0`
**Applied fix:** The cluster walk now tracks `prev = x` (the previous unique
center-x element) and starts a new cluster when `x - prev > col_tol` instead
of comparing against the previous cluster start. A column whose cumulative
span exceeds tol while every consecutive gap is within tol no longer fragments
(reviewer repro `[(0,0),(39,1),(78,2)]` now yields one column). Added
`test_reading_order_no_fragmentation_within_cumulative_tolerance` covering
both the no-fragment case and that a genuine beyond-tol gap still splits.

### WR-03: `TorchCTDModel.configure` stores `conf_thresh`/`nms_thresh` but `load()` never applies them

**Files modified:** `manga_ai_studio/adapters/torch_impl.py`, `tests/test_detection/test_ctd_adapter.py`
**Commit:** `9b5b602`
**Applied fix:** `load()` now passes `conf_thresh=self._conf_thresh` and
`nms_thresh=self._nms_thresh` to the vendored `TextDetector` constructor
(which accepts and uses them in `postprocess_yolo` — verified against
`panelcleaner/comic_text_detector/inference.py`). Added
`test_load_passes_conf_and_nms_thresholds_to_detector`, which swaps in a
recording fake `TextDetector` and asserts the configured thresholds (and the
other knobs) reach the constructor.

### WR-04: Load Translations onto a never-visited page crashes into a spurious error dialog

**Files modified:** `manga_ai_studio/gui/main_window.py`, `tests/test_gui_boxes.py`
**Commit:** `ba7f6eb`
**Applied fix:** The non-current-page branch passes
`self.image_files[page_index].boxes or []` so a never-visited target page
(`ImageFile.boxes` defaults to `None`) reports the clean no-match copy instead
of raising `TypeError: 'NoneType' object is not iterable` into the error
dialog. Added `test_apply_translations_never_visited_page_no_crash` (two-page
folder, only page 1 visited, apply to page 2: asserts no `critical` dialog and
the "No lines matched any bubble number on page 2." report).

### WR-05: Inspector fields go stale after an inline-editor commit

**Files modified:** `manga_ai_studio/gui/main_window.py`, `tests/test_gui_boxes.py`
**Commit:** `ba337c0`
**Applied fix:** `_on_boxes_modified` now re-populates the Inspector from the
still-selected box after the BOXES push (the inline editor emits through the
same `boxes_modified` signal, so its commit is covered; canvas create/move/
resize commits are covered too). `load_box` blocks signals during population,
so no commit loop is possible. Added
`test_inspector_refreshes_after_inline_editor_commit`, which drives the real
`InlineEditor.enter`/`commit` path and asserts the Inspector's Recognized
field shows the committed text while the box stays selected.

## Skipped Issues

None — all 6 in-scope findings fixed.

## Out-of-scope notes

The review also filed 4 Info findings (IN-01 vertical commit no-op push when
`payload is None`; IN-02 OCR crop not bounds-clamped; IN-03 duplicated
`_current_focus_text`; IN-04 `_run_ocr_all_task` lacks the image-read guard).
These were outside the `critical_warning` fix scope and were not touched; they
remain open for a follow-up pass.

---

_Fixed: 2026-08-06T21:18:13Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
