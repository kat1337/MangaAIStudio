---
phase: quick-260822-vk7-fix-translation-field-bug-resizing-a-box
plan: 01
subsystem: gui
status: complete
tags: [gui, inspector, stationary-grace, ocr, focus-guard, regression]
requires:
  - quick-260822-gnq stationary-grace machinery (STATIONARY_GRACE_MS + _stationary_timer)
provides:
  - InspectorPanel.is_text_edit_active() edit-session probe
  - _on_canvas_selection_changed reload guard (clobber suppression)
  - _on_stationary_grace_timeout edit-session deferral (re-arm instead of dispatch)
affects:
  - OCR-finished -> boxes_modified -> load_box chain
  - stationary-grace auto detect-fit + OCR timing
tech-stack:
  added: []
  patterns: [commit-deferred-edit-session probe, timer re-arm deferral]
key-files:
  created: []
  modified:
    - manga_ai_studio/gui/inspector_panel.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_gui_boxes.py
decisions:
  - Guard-release tests observe a load_box recorder, not field content — focus-out COMMITS the typed text to the pagebox, so the post-focus-out reload legitimately shows the committed value (field-content assertions would false-fail)
  - Grace deferral re-arms via STATIONARY_GRACE_MS read at start() time — preserves the established monkeypatch seam from quick-260822-gnq
  - Deferral check placed BEFORE the _op_running gate so a deferred grace is never silently dropped when an op happens to be running at first fire; T-QG-02 silent-skip semantics preserved for subsequent fires
metrics:
  duration: ~25 min
  completed: 2026-08-22
actuals:
  tokens: 76500   # chars/4 over the realized diff (306 inserted lines x ~1000 chars effective context+output scale)
  tasks: 3
  commits: 5
requirements: [QUICK-VK7-FIX]
---

# Quick Task 260822-vk7: Fix translation field bug resizing a box Summary

Resize-then-type no longer freezes mid-typing or wipes the translation field: the stationary-grace auto re-detect now DEFERS (re-arms) while an edit session is active, and Inspector reloads are suppressed during commit-deferred text edits.

## What Was Built

1. **`InspectorPanel.is_text_edit_active()`** (inspector_panel.py) — public probe returning True iff `translation_edit` or `recognized_edit` has keyboard focus (the two `_CommitTextEdit` fields whose commits are deferred to focus-out).
2. **Reload guard** in `MainWindow._on_canvas_selection_changed` — early-return with a debug log while the probe is True. This suppresses every reload caller (selectionChanged follower, WR-05 `_on_boxes_modified` sync, style-commit syncs), closing the reported clobber chain `_on_ocr_finished -> canvas.boxes_modified -> _on_boxes_modified -> _on_canvas_selection_changed -> load_box`. Model writes are untouched; the panel resyncs on the next event after focus-out.
3. **Grace deferral** in `MainWindow._on_stationary_grace_timeout` — before the `_op_running` gate, an active Inspector text-edit session OR active canvas inline editor causes a debug log + `self._stationary_timer.start(STATIONARY_GRACE_MS)` (module constant read at start-time — the established monkeypatch seam) and return WITHOUT touching stale markers. The synchronous full-page `derive_page_mask_state` refit never runs mid-typing; the pending work runs exactly once once editing finishes.
4. **9 regression tests** in tests/test_gui_boxes.py: 4 Task-1 guards (probe False/True, follower reload suppression + release, end-to-end `boxes_modified` shape), 4 Task-2 guards (deferral while focused / inline editor, no-session control mirroring `test_stationary_grace_dispatches_once`, deferred-runs-exactly-once-after-focus-out), plus 1 exact-repro end-to-end guard (Task 3) asserting typed text survives verbatim, the timer re-arms rather than dispatches, and the pagebox ends up carrying BOTH the OCR text and the typed translation.

## Tasks

| Task | Name | Commit(s) |
| ---- | ---- | --------- |
| 1 | InspectorPanel.is_text_edit_active() + reload guard | 6a3836d (RED), 088ca99 (GREEN) |
| 2 | Stationary-grace timeout defers during edit sessions | d8bcca5 (RED), 0acb90d (GREEN) |
| 3 | Reported-repro guard + full suite | 77e09bf |

## Verification

- Task 1 verify: `-k "text_edit_active or selection_changed or inspector"` — 21 passed.
- Task 2 verify: `-k "stationary or grace"` — 9 passed (all pre-existing grace guards green).
- Full suite (pinned interpreter `C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe`): **1040 passed, 0 failed** in 114 s — baseline was 1031 passed, so the suite grew by exactly the 9 new tests with zero regressions.

## Deviations from Plan

### Test-design adjustments (within task scope, Rule 1)

1. **Guard-release assertion rewritten to a `load_box` recorder** (test_selection_follower_reload_skipped_while_translation_focused): the plan's "after clearing focus the field shows the pagebox value again" is unobservable by field content — focus-out itself COMMITS the typed text to the pagebox (`_CommitTextEdit.committed` -> `_on_inspector_translation_committed`), so the post-focus-out reload legitimately shows that same committed string. A monkeypatched recorder around the real `load_box` asserts suppression (0 calls while focused) and release (>=1 call after focus-out) directly.
2. **Selection added before focusing in grace tests**: without a selected box the panel fields are disabled and cannot take focus (`is_text_edit_active()` stayed False). Selecting the item mirrors the real repro (user edits the selected box).
3. **Deferral placed before `_op_running` gate** exactly per plan; noted explicitly because order matters for T-QG-02 semantics.

No architectural deviations. No auth gates encountered.

## Known Issues (pre-existing, out of scope)

- `tests/test_gui_boxes.py::test_no_ghost_after_undo_and_scroll` failed intermittently mid-session ("stroke should be visible" viewport-grab sanity). **Verified pre-existing**: it fails identically on the untouched baseline commit 5176998 in a throwaway worktree. It is a render-timing/environment flake in the grab-based assertion, touches none of this task's code paths, and passed in the final full-suite run. Not fixed per the scope boundary rule (only issues caused by this task's changes are auto-fixed).

## Self-Check: PASSED

- Files exist: manga_ai_studio/gui/inspector_panel.py (is_text_edit_active), manga_ai_studio/gui/main_window.py (guarded _on_canvas_selection_changed, deferring _on_stationary_grace_timeout), tests/test_gui_boxes.py (9 new tests). Confirmed on disk.
- Commits exist: 6a3836d, 088ca99, d8bcca5, 0acb90d, 77e09bf — all in `git log`.
- Full suite: 1040 passed / 0 failed under python.exe 3.14.2.
