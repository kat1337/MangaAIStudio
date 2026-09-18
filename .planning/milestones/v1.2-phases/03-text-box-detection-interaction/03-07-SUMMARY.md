---
phase: 03-text-box-detection-interaction
plan: 07
subsystem: gui (detection-undo baseline + moved-position persistence)
tags: [gui, undo, d-10, d-11, detection-baseline, before-state, persistence, gap-closure, uat-test-3, uat-test-4, wr-04, tdd, text-01, text-03, pitfall-3, pitfall-6, surface-13]
requirements: [TEXT-01, TEXT-03]
status: complete

dependency_graph:
  requires:
    - "03-04: _build_detected_boxes + push_boxes_state (the D-10 push this plan removes to make detection a non-undoable baseline)"
    - "03-05: on_page_selected Step 1b/4b persistence + unified on_undo/on_redo + apply_undo_boxes + _suppress_boxes_push guard (the persistence seam + the restore guard this plan's Gap-4 probe validates and reuses)"
    - "03-06: CornerHandle.shape()/boundingRect() hit-target (NOT regressed — this plan's canvas.py delta-checks are on the move/resize commit branches, not the handle geometry)"
  provides:
    - "main_window._build_detected_boxes Step 5 — detection is a NON-undoable baseline (the explicit push_boxes_state(pre_detection_snapshot) removed; the Step 3 _suppress_boxes_push guard already suppresses the set_boxes emission, so detection produces NO boxes stack entry)"
    - "canvas._select_and_begin_move captures _move_start_rect; mouseReleaseEvent move-commit branch + _commit_resize delta-check (WR-04: a no-op select-click / resize-with-no-drag no longer emits boxes_modified)"
    - "tests/test_box_persistence.py — 4 new regression tests (detection baseline, edit-after-detection exactly-one-entry, moved-position persistence for detected+user, CREATE-undo contract guard)"
  affects:
    - "03-08 (mask-undo gap-closure): serializes after this plan by the wave-3 dependency; history_manager.py is touched by BOTH plans but not concurrently (no file-ownership conflict). This plan did NOT need to modify history_manager.py (the Gap-4 probe exonerated the detachment path)."

tech_stack:
  added: []
  patterns:
    - "Detection-as-baseline (not detection-as-edit): detection establishes the live box layer as the implicit undo baseline WITHOUT pushing an entry; the first real user edit pushes its before-snapshot against it. Mirrors how the initial mask presence from a detect is not individually undoable, only subsequent strokes are (the same CR-01 before-state convention, applied selectively to REAL edits only)."
    - "WR-04 delta-check on emit: a box-edit commit (move/resize) only emits boxes_modified when the rect actually changed vs the arm-time rect — a plain click-to-select or click-handle-with-no-drag is a no-op that must NOT seed a spurious BOXES history entry (which would consume a slot and disable redo). _commit_create is EXEMPT (it already early-returns on < MIN_BOX_SIZE)."
    - "Live-probe-first diagnosis for a partially-diagnosed UAT gap: before coding a fix for Gap 4, drive the REAL production path (move-commit + on_page_selected round-trip) and confirm the actual cause; do not speculate-implement multiple candidate fixes."

key_files:
  created: []
  modified:
    - manga_ai_studio/gui/main_window.py
    - manga_ai_studio/gui/canvas.py
    - tests/test_box_persistence.py
    - tests/test_gui_detection_boxes.py

decisions:
  - "03-07 Gap 3: detection is a NON-undoable baseline. The explicit self.history.push_boxes_state(pre_detection_snapshot) at _build_detected_boxes Step 5 (main_window.py:1633) is REMOVED. The Step 3 _suppress_boxes_push guard already suppresses the set_boxes emission, so after removing the explicit push the detection apply produces NO boxes stack entry. pre_detection_snapshot is retained ONLY for the user_pageboxes derivation (D-03 keep-user). _update_undo_redo_actions() is still called post-detection so undo/redo button enable state refreshes."
  - "03-07 Gap 4: NO production code change on the persistence read path. A live probe (3 independent scenarios: detected move, user move, detected resize + the exact UAT scenario) confirmed boxes_snapshot() -> BoxItem.current_box() -> self.rect() reads the MOVED rect at save-time, so on_page_selected Step 1b persists the live moved geometry. The UAT's 'diagnosed: partial' note explicitly admitted 'the probe fixture tripped on on_page_selected's signature' — never live-confirmed. The plan's FIX 4 note predicted exactly this landing ('candidate (a) should be FALSE ... no code change needed on the read side IF boxes_snapshot already reads live'). history_manager.py was NOT modified (the detachment path was exonerated)."
  - "03-07 WR-04: delta-checks added to the move-commit branch (mouseReleaseEvent) and _commit_resize; _commit_create LEFT UNTOUCHED (WARNING 5 — it already early-returns on < MIN_BOX_SIZE, so a no-op create emits nothing; adding a delta-check there risks the real-create push path). The CREATE-undo contract is locked by test_create_box_pushes_one_undoable_entry."
  - "03-07: the existing test_detection_pushes_boxes_snapshot was migrated to test_detection_does_not_push_boxes_snapshot (asserts the NEW non-undoable-baseline contract). In-scope per the SCOPE BOUNDARY rule — directly caused by FIX 3A (the push it asserted on is what the fix removes)."
  - "03-07: TEST B (moved-position persistence) is a PASSING regression guard, NOT a failing RED defect reproduction — honest TDD requires a test for a non-existent bug to pass (otherwise it would be fabricated). The probe proved the behavior already works."

metrics:
  duration: 12 min
  completed: 2026-07-31
  tasks: 2
  files: 4 (2 modified source + 2 modified test)
  tests-added: 4
  tests-updated: 1
  suite: 254 passed (was 249)
---

# Phase 03 Plan 07: Detection-Undo Baseline + Moved-Position Persistence Summary

Closed UAT test 3 (the third Ctrl+Z wiping ALL detected boxes) by making detection a NON-undoable baseline, and closed UAT test 4 (moved-position reset across a page round-trip) — which a live probe revealed was a misdiagnosis: the persistence read path already works correctly. Also closed WR-04 (the redundant no-op push on a plain select-click / resize-with-no-drag) as a contributing fix, with delta-checks confined to move/resize (never create, per WARNING 5). The CR-01 CREATE-undo contract is preserved and locked by a dedicated regression guard.

## What Was Built

### Task 1 (RED) — 4 regression tests in `tests/test_box_persistence.py`

- **TEST A `test_detection_via_build_detected_boxes_no_baseline`** (RED — the true Gap-3 defect): drives the REAL `_build_detected_boxes` method with a duck-typed `SimpleNamespace(xyxy=[...])` block (the only attribute `textblock_to_box` reads) and asserts `not history.can_undo_boxes()` after detection. Today this FAILS because the method's Step 5 explicitly pushes a 0-box pre-detection snapshot.
- **TEST A companion `test_detection_does_not_seed_undoable_baseline`** (passes today): drives the suppressed `set_boxes` path detection uses at Step 3 (wrapped in `_suppress_boxes_push`) and asserts no baseline — confirms the suppression guard works for the set_boxes path; the push lives only in `_build_detected_boxes` itself.
- **TEST A strengthened `test_edit_after_detection_pushes_exactly_one_entry`** (RED today): after detect + ONE real box-move, asserts the BOXES stack holds EXACTLY one entry (the move's before-snapshot), and undo restores the pre-move position while keeping the box. Today FAILS because detection seeds a baseline (so detect + 1 move = 2 entries, not 1).
- **TEST B `test_moved_box_position_persists_across_round_trip`** (passing guard): drives the LIVE move-commit path (`_select_and_begin_move` + setRect + `boxes_modified.emit`) for BOTH a detected box and a user box, then a REAL `on_page_selected` round-trip (A -> B -> A), and asserts the MOVED positions persist. The user-box case is its OWN named assertion (WARNING 4).
- **TEST C `test_create_box_pushes_one_undoable_entry`** (passing guard): drives a real Alt+drag CREATE (`_begin_create_box` + `_commit_create`) and asserts exactly one BOXES entry is pushed + one-press undo recovers it; a tiny `< MIN_BOX_SIZE` create produces zero entries (locks the CR-01 CREATE-undo path so WR-04's delta-checks cannot silently break it).

### Task 2 (GREEN) — FIX 3A + FIX 3B (WR-04) + FIX 4 (probe-confirmed no-op)

- **FIX 3A (Gap 3, UAT test 3)** in `main_window.py._build_detected_boxes`: REMOVED the explicit `self.history.push_boxes_state(pre_detection_snapshot)` at Step 5 and its `_update_undo_redo_actions()` was already there. The Step 3 `_suppress_boxes_push = True ... set_boxes ... False` guard already suppresses the set_boxes emission, so with the explicit push removed the detection apply produces NO boxes stack entry. `pre_detection_snapshot` retained only for the `user_pageboxes` derivation (D-03 keep-user). Docstring step 5 + comments rewritten to cite UAT test 3 and the new non-undoable-baseline contract.
- **FIX 3B (WR-04)** in `canvas.py`: added `self._move_start_rect = QRectF(item.rect())` capture in `_select_and_begin_move`; the move-commit branch of `mouseReleaseEvent` now reads `moved = self._moving_box.rect() != self._move_start_rect` and only emits `boxes_modified` when moved. `_commit_resize` now compares the final rect against `_resize_start_rect` (already captured at `_begin_resize`) and only emits when they differ. `_commit_create` LEFT UNTOUCHED (WARNING 5).
- **FIX 4 (Gap 4, UAT test 4)**: NO production code change. The live probe (see Deviations) confirmed the persistence read path is already correct.

### Migrated test — `tests/test_gui_detection_boxes.py`

`test_detection_pushes_boxes_snapshot` -> `test_detection_does_not_push_boxes_snapshot`: now asserts the NEW contract that detection seeds NO boxes undo entry (was asserting the old buggy behavior). In-scope per the SCOPE BOUNDARY rule — directly caused by FIX 3A.

## TDD Gate Compliance

Both tasks carried `tdd="true"`. RED/GREEN cycle with separate commits:

| Task | RED commit (test) | GREEN commit (feat) | Gate |
|------|-------------------|---------------------|------|
| 1 | `da02a63` (2 failing — the real-method + edit-after-detection tests; 3 passing guards) | — | RED before GREEN ✓ |
| 2 | — | `5d85b09` (all 7 GREEN + full suite 254 green) | GREEN ✓ |

The RED phase confirmed the Gap-3 tests genuinely failed before implementation (the real-method test failed at the `can_undo_boxes()` assertion because detection pushes today; the edit-after-detection test failed at the post-detection baseline check). TEST B and TEST C passed during RED by design — they are passing guards (TEST B locks correct persistence the probe proved already works; TEST C locks the CREATE-undo contract). This is honest TDD: a test for a non-existent bug must pass, and a contract guard is not a defect reproduction. The GREEN phase confirmed the minimal fix (remove one push line + add two delta-checks) made all Task-1 tests pass with no iteration. No separate REFACTOR gate.

## Verification

All plan `<verification>` block commands pass:

- `python -m pytest tests/test_box_persistence.py::test_detection_does_not_seed_undoable_baseline tests/test_box_persistence.py::test_detection_via_build_detected_boxes_no_baseline tests/test_box_persistence.py::test_moved_box_position_persists_across_round_trip tests/test_box_persistence.py::test_create_box_pushes_one_undoable_entry -q -m gui` -> **4 passed** (post-fix; 1 was RED pre-fix)
- `python -m pytest tests/test_box_persistence.py tests/test_history.py tests/test_gui_boxes.py tests/test_gui_detection_boxes.py tests/test_core/test_history_boxes.py -q -m gui` -> **75 passed**
- `python -m pytest tests/ -q` -> **254 passed** (was 249; +4 new Task-1 tests + 1 migrated detection test net; FULL suite green, no regression to Phase 1/2/3-01..06)

All `<success_criteria>` met:
- UAT test 3 resolved: detection is a non-undoable baseline — undoing through all box edits never removes the detected boxes (locked by 3 RED-now-GREEN tests).
- UAT test 4 resolved: a moved box's position persists across a page round-trip for both detected and user boxes (locked by the passing guard; the probe confirmed the read path was already correct).
- No regression to single-press undoability of real edits, redo, or unified-timeline ordering (test_box_edit_is_undoable, test_box_restore_does_not_repush, test_unified_undo_pops_across_stacks, test_new_edit_clears_redo all green).
- WR-04 closed as a contributing fix (delta-checks on move/resize; create exempt).
- The Gap-4 root cause is CONFIRMED by a live probe (not speculated) and documented below.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed the migrated detection test that asserted the old buggy behavior**
- **Found during:** Task 2 GREEN phase (full suite after FIX 3A: `test_detection_pushes_boxes_snapshot` failed because detection no longer pushes)
- **Issue:** The existing `test_detection_pushes_boxes_snapshot` (test_gui_detection_boxes.py:301) asserted the OLD contract (`can_undo()` True after detect-with-build) — exactly the Gap-3 bug. Per the SCOPE BOUNDARY rule, this failure IS in scope (directly caused by FIX 3A — the push it asserts on is what the fix removes).
- **Fix:** Migrated to `test_detection_does_not_push_boxes_snapshot` asserting the NEW contract (`not can_undo_boxes()` and `not can_undo()` after detect-with-build).
- **Files modified:** tests/test_gui_detection_boxes.py
- **Commit:** 5d85b09

### Probe-Confirmed Findings (Gap 4)

**Gap 4 (UAT test 4, diagnosed: partial) — the bug does NOT reproduce; no production fix needed.**

The plan required Task 1 to CONFIRM the actual Gap-4 root cause via a live probe before coding the fix (because the UAT marked it `diagnosed: partial`). Three independent live probes were run (throwaway scripts, deleted after), each driving the REAL production paths:

1. **Detected-box move + round-trip:** detect via `_build_detected_boxes` (synthetic `SimpleNamespace(xyxy=...)`), move via the live commit path (`_select_and_begin_move` + `setRect` + `boxes_modified.emit`), navigate A -> B -> A via real `file_table.select_path` + `on_page_selected`. Result: the moved rect (100,100,40,40) persisted and restored correctly.
2. **User-box move + detected-box resize + real delta path:** verified all three commit paths (user move, detected resize, and the real `mouseMoveEvent` anchor+delta logic at canvas.py:921-931). All persisted correctly.
3. **Exact UAT scenario:** detect boxes, move one, switch pages and back. Result: position persisted.

**Probe verdict:** `boxes_snapshot()` (canvas.py:1230-1255) -> `BoxItem.current_box()` (box_item.py:353-370) -> `self.rect()` reads the LIVE moved rect at save-time, so `on_page_selected` Step 1b persists the moved geometry. Candidate cause (a) from the UAT ("boxes_snapshot/current_box reads a cached PageBox.box not the live rect") is **FALSE**. Candidate cause (b) ("the CR-01 before-state snapshot is written back as authoritative state at page-switch") is also **FALSE** — `_boxes_interaction_start_snapshot` is consumed once by `_on_boxes_modified` (a local param, never stored on self) and is NOT read by `on_page_selected` Step 1b (which calls `canvas.boxes_snapshot()` live). The history_manager detachment path (`_materialize_snapshot` / `push_boxes_state`) was also exonerated — `_materialize_snapshot` deep-copies the tuple members, and `Box` is `@frozen` (immutable, safe to share).

The UAT note explicitly admitted "the probe fixture tripped on on_page_selected's signature" — the partial diagnosis was a static-read guess, never live-confirmed. The plan's FIX 4 note predicted exactly this landing: "VERIFY FIRST that boxes_snapshot reads the live rect ... candidate (a) should be FALSE ... no code change needed on the read side IF boxes_snapshot already reads live."

**Result:** `history_manager.py` was NOT modified (the plan added it to files_modified precisely so the GREEN gate would be completable in-wave IF the probe implicated the detachment path — it did not). TEST B was written as a passing regression guard (locking the correct behavior) rather than a failing RED test (honest TDD: a test for a non-existent bug must pass).

This is a documentation-level deviation (the plan anticipated it as the "most likely landing"), not a blocker — no checkpoint required.

## Checkpoint Handling

None. This plan is `autonomous: true` with no `checkpoint:*` tasks. Both tasks are `type="auto"`. The end-of-phase human-verify gate (per `config.json` `human_verify_mode: "end-of-phase"`) will run the manual spot-checks (Detect -> move a box -> Ctrl+Z reverts the move -> Ctrl+Z again does NOT remove the detected set; move a box, switch pages and back, confirm it stayed moved) on the real running app at phase close.

## Known Stubs

None. Both gap closures are wired end-to-end:
- Gap 3: detection establishes the live layer as a non-undoable baseline; real edits push against it; undo reverts edits without touching the detected set.
- Gap 4: moved positions persist for detected AND user boxes (verified by probe + locked by regression guard).
- WR-04: no-op select-clicks / resize-with-no-drag no longer seed spurious BOXES entries.

## Threat Flags

None. The threat register is fully mitigated in-plan:
- **T-03-07-01 (high, mitigate — Repudiation):** detection no longer destroys user data on the 3rd Ctrl+Z. The non-undoable-baseline fix restores the user's mental model (edits undo, the detection baseline does not). Regression guards: `test_detection_via_build_detected_boxes_no_baseline`, `test_detection_does_not_seed_undoable_baseline`, `test_edit_after_detection_pushes_exactly_one_entry`.
- **T-03-07-02 (high, mitigate — Tampering):** moved positions persist (the read path was already correct — verified by probe). Regression guard: `test_moved_box_position_persists_across_round_trip` (separate named assertions for detected and user boxes).
- **T-03-07-03 (low, mitigate — DoS):** the WR-04 delta-checks stop no-op emissions from consuming history slots / disabling redo. Existing `test_new_edit_clears_redo` semantics preserved for REAL edits.
- **T-03-07-04 (medium, mitigate — Tampering):** the history_manager detachment path was EXONERATED by the probe (no aliasing); no change needed. The CREATE-undo contract guard ensures the existing detachment discipline is not regressed.

No new network/auth/file-access surface introduced (single-user offline desktop app; the changes are purely in the in-memory undo/persistence state machine).

## Self-Check: PASSED

Modified files present:
- FOUND: manga_ai_studio/gui/main_window.py (FIX 3A — removed push_boxes_state at Step 5; docstring/comments updated)
- FOUND: manga_ai_studio/gui/canvas.py (FIX 3B — _move_start_rect capture + move-commit delta-check + _commit_resize delta-check; _commit_create untouched)
- FOUND: tests/test_box_persistence.py (+4 new Task-1 tests)
- FOUND: tests/test_gui_detection_boxes.py (test_detection_pushes_boxes_snapshot -> test_detection_does_not_push_boxes_snapshot)

Commits exist:
- FOUND: da02a63 (test RED Task 1)
- FOUND: 5d85b09 (fix GREEN Task 2)
