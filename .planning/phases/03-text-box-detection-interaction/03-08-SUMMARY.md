---
phase: 03-text-box-detection-interaction
plan: 08
subsystem: gui (mask-undo before-state + null-current crash guard)
tags: [gui, undo, mask, flow-02, baseline-seeding, before-state, one-behind, wr-01, gap-closure, uat-test-3-addendum, tdd, text-03, pitfall-2, pitfall-3, surface-8, surface-13]
requirements: [FLOW-02]
status: complete

dependency_graph:
  requires:
    - "01-06: HistoryManager mask stack + pop_mask_undo + _on_mask_modified push hook + test_undo_does_not_repush (the Phase 1 mask-undo surface this plan repairs — the one-behind defect is Phase 1 debt surfaced by Phase 3's unified timeline)"
    - "03-02: HistoryManager unified undo()/redo() + the (stamp, value) cross-store pop (the path that makes the latent WR-01 None.copy() crash reachable — unified pop delegates to pop_mask_undo with current_mask=None when canvas.has_mask() is False)"
    - "03-05: _current_undo_state returns current_mask=None when has_mask() is False (main_window.py:1120) — the WR-01 trigger; on_undo/on_redo unified handlers; Surface 13 collapse"
    - "03-07: the detection-baseline discipline this plan mirrors for the mask side (the first edit pushes a before-state against an implicit non-undoable baseline; this plan applies the same discipline to the first mask stroke of a per-page session)"
  provides:
    - "main_window._on_mask_modified now pushes the mask BEFORE-state per stroke (tracked via self._pre_stroke_mask, defaulting to a clean baseline for the first stroke of a per-page session) — the one-behind defect closed; undo of any stroke restores the state that preceded it, and the first stroke undoes to a clean canvas"
    - "main_window self._pre_stroke_mask per-page before-state tracker (None until first stroke seeds the clean baseline; refreshed after each push; reset_history clears it)"
    - "history_manager.pop_mask_undo / pop_mask_redo / pop_image_undo / pop_image_redo — null-current guards (WR-01 closed; the redo stash is skipped when current is None, the popped previous is still returned)"
    - "tests/test_history.py — 3 new regression tests (symptom reproduction driving the _on_mask_modified hook, isolated first-stroke mechanism + bare-history pin, WR-01 null-mask crash) + 2 helpers (_opaque_stroked_mask, _paint_brush_stroke — real two-point strokes because the single-point _painted_mask draws zero opaque pixels on this Qt build)"
  affects:
    - "Phase 1 FLOW-02 contract restored: a mask brush stroke is fully undoable; repeated Ctrl+Z does not re-materialize it; the first stroke of a session undoes to a clean baseline"
    - "03-REVIEW.md WR-01 (open warning) closed"
    - "03-UAT.md test 3 addendum (the mask-stuck symptom) resolved"
    - "No regression: test_undo_does_not_repush (baseline push is at STROKE time in _on_mask_modified, never at undo-application time), test_mask_snapshot_is_copied / test_mask_pop_returns_copy (Pitfall-2 detachment), unified-timeline cross-store ordering, plans 03-06/03-07 (hit-target + detection baseline) untouched"

tech_stack:
  added: []
  patterns:
    - "Before-state push convention for the mask stack (mirrors the IMAGE side's pre-edit push contract and plan 03-07's BOXES before-state discipline): each stroke pushes the mask state as it was BEFORE the stroke began (= the previous stroke's after-state, or a clean baseline for the first stroke). pop_mask_undo returns the stack TOP, so the top at undo-time MUST be the state to restore to — pushing the after-state (the pre-fix code) made pop return the after-state itself (a no-op that left the stroke on the canvas)."
    - "Reconstructed before-state without a canvas-side _begin_paint snapshot: because _on_mask_modified fires AFTER the stroke is painted (canvas _end_paint paints then emits), the before-state cannot be read from canvas.get_mask() (that is the post-stroke state). It is reconstructed as the previous stroke's after-state, tracked in self._pre_stroke_mask. This keeps mask changes localised to main_window.py (no canvas.py edit), honouring the plan's directive."
    - "Null-current guard on per-type pops (WR-01): when current_mask/current_img is None, skip the redo-stash step (there is nothing to swap into redo) but still return the popped previous. The guard is a pure short-circuit — behaviour is unchanged when current values are present."
    - "Real-stroke test fixtures: the existing _painted_mask helper paints a single-point drawLine(p1,p1) which renders ZERO opaque pixels on PySide6 6.x (a degenerate zero-length line is a no-op), so masks built from it are indistinguishable from the transparent baseline and any assertion comparing 'stroked' vs 'clean' is a false-pass. The new _opaque_stroked_mask / _paint_brush_stroke helpers paint a real two-point segment whose round-cap caps fill a measurable disc, so the regression tests genuinely distinguish a stroked mask from a clean baseline."

key_files:
  created: []
  modified:
    - manga_ai_studio/gui/main_window.py
    - manga_ai_studio/core/history_manager.py
    - tests/test_history.py

decisions:
  - "03-08 FIX A (one-behind): the mask push hook now pushes the BEFORE-state per stroke, tracked via self._pre_stroke_mask. The pre-fix code pushed canvas.get_mask() (the AFTER-state), so pop_mask_undo returned the after-state itself — a no-op that left the stroke on the canvas. The before-state is reconstructed as the previous stroke's after-state (None until the first stroke seeds a clean baseline of the current mask's size/format). reset_history clears _pre_stroke_mask per page. This mirrors the IMAGE side's pre-edit push contract and plan 03-07's BOXES before-state discipline."
  - "03-08 probe finding (load-bearing — the plan's literal Option 2 does NOT work): the plan's Option 2 text described 'seed [clean-baseline, after-state-1]; undo pops after-state-1 -> restores clean-baseline'. A live probe against the REAL pop_mask_undo semantics proved this conflates two operations: pop_mask_undo returns the stack TOP (the after-state), so applying it is a no-op — the stroke was NEVER removed. The actual correct fix is to push the BEFORE-state (so the stack top at undo-time IS the state to restore to). This is documented in the _on_mask_modified docstring and drove the implementation away from the plan's literal Option 2 toward the before-state convention. Confirmed by probe: after stroke1 stack=[clean], undo->live clean; after stroke2 stack=[clean, after_1], undo->live after_1, undo->live clean."
  - "03-08 no canvas.py change (Option 1 rejected): the before-state is reconstructed in MainWindow from the tracked previous after-state rather than snapshotted at canvas._begin_paint. This keeps mask changes localised to main_window.py per the plan's directive and avoids a canvas.py edit that would co-locate with plan 03-07's wave-2 changes. A canvas-side _begin_paint snapshot would only differ from the reconstructed before-state for the impossible case where a page has mask content before its first undoable stroke — but reset_history clears _pre_stroke_mask per page, so 'first stroke' is genuinely the first."
  - "03-08 FIX B (WR-01): guarded all four per-type pops (pop_mask_undo/pop_mask_redo/pop_image_undo/pop_image_redo) against a null current value. The unconditional current_mask.copy() / current_img[...] slicing crashed with AttributeError when _current_undo_state passed current_mask=None (canvas.has_mask() False) and the mask stack was non-empty. The guard skips the redo-stash when current is null and still returns the popped previous. The symmetric image guard is included because pop_image_undo slices current_img[y:y+h, x:x+w] which also crashes on None."
  - "03-08 test placement (Rule 3 deviation, documented): the plan's Tests A/B were written to build a bare HistoryManager and call push_mask_state(stroked) directly. But the plan's documented fix location is _on_mask_modified (the GUI push hook), and a bare push_mask_state call has no notion of 'first stroke of a session' — it could not be turned GREEN by the plan's own fix. Tests A/B were rewritten to drive the _on_mask_modified hook via _paint_brush_stroke + on_undo (mirroring the existing test_undo_mask_applies_snapshot pattern), so they exercise the mechanism the fix addresses. Test C stays at the HistoryManager layer (it tests pop_mask_undo's null guard directly, which IS in history_manager.py). RED was re-confirmed against the pre-fix source for all three."
  - "03-08 fixture discovery (Rule 1 — the existing _painted_mask is a false-pass generator): the single-point drawLine(p1==p2) in _painted_mask / _paint_brush_dot renders zero opaque pixels on this Qt build, so every existing mask test that compares stroked vs transparent is a vacuous 0==0 comparison (they still pass, but do not exercise real stroke content). The new _opaque_stroked_mask / _paint_brush_stroke helpers use a real two-point segment. The existing helpers were left UNTOUCHED (out of scope — pre-existing weakness, not caused by this plan); only the new tests use the real-stroke helpers."

metrics:
  duration: "~22 min"
  tasks_completed: 2
  files_modified: 3
---

# Phase 03 Plan 08: Mask-Stroke Undo Baseline Seeding + WR-01 Null-Mask Crash Guard Summary

Mask strokes are now fully undoable (FLOW-02 restored): each stroke pushes its BEFORE-state so undo restores the preceding canvas, the first stroke of a session undoes to a clean baseline, and repeated Ctrl+Z never re-materializes a removed stroke. WR-01 (the `None.copy()` crash in `pop_mask_undo` when the canvas mask is null) is closed via null-current guards on all four per-type pops.

## What Was Built

### FIX A — Mask before-state push (the one-behind fix, UAT test 3 addendum)

`MainWindow._on_mask_modified` (the only mask push path — verified post-03-07) previously pushed `canvas.get_mask()` (the AFTER-state). Because `pop_mask_undo` returns the stack TOP, applying the popped after-state was a no-op — the stroke stayed on the canvas, and after an inpaint interleaving the brush appeared "stuck" on the 2nd Ctrl+Z (the user's UAT test 3 addendum report).

The hook now pushes the mask BEFORE-state per stroke. The before-state is reconstructed as the previous stroke's after-state, tracked in `self._pre_stroke_mask` (None until the first stroke of a per-page session seeds a clean baseline of the current mask's size/format). `reset_history` clears it per page. Result:

- Stroke 1: stack = `[clean]`. undo → live clean (stroke gone).
- Stroke 2: stack = `[clean, after_1]`. undo → live after_1 (stroke 2 gone); undo → live clean (stroke 1 gone).

This mirrors the IMAGE side's pre-edit push contract and plan 03-07's BOXES before-state discipline.

### FIX B — WR-01 null-current guard

`pop_mask_undo` / `pop_mask_redo` / `pop_image_undo` / `pop_image_redo` now guard against a null `current_mask` / `current_img`. The unconditional `.copy()` / slicing crashed with `AttributeError` when `_current_undo_state` passed `current_mask=None` (whenever `canvas.has_mask()` is False) and the mask stack was non-empty. The guard skips the redo-stash when current is null and still returns the popped previous — a pure short-circuit, behaviour unchanged when current values are present.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Plan's literal Option 2 does not match actual pop semantics**
- **Found during:** Task 2 (GREEN implementation)
- **Issue:** The plan's Option 2 described seeding `[clean-baseline, after-state-1]` then "undo pops after-state-1 → restores clean-baseline." A live probe against `pop_mask_undo` proved this conflates two operations: `pop_mask_undo` returns the stack TOP (the after-state), so applying it is a no-op — the stroke was never removed (probe showed `after undo: mask opaque = 276`, unchanged).
- **Fix:** Push the BEFORE-state per stroke (so the stack top at undo-time IS the state to restore to), tracked via `self._pre_stroke_mask`. Confirmed by re-probe: after stroke1 stack=`[clean]`, undo → live clean.
- **Files modified:** `manga_ai_studio/gui/main_window.py`
- **Commit:** 9eb9d36

**2. [Rule 3 — Blocking] Tests A/B rewritten to drive the fix location**
- **Found during:** Task 2 (GREEN)
- **Issue:** The plan's Tests A/B built a bare `HistoryManager` and called `push_mask_state(stroked)` directly. But the plan's documented fix location is `_on_mask_modified` (the GUI push hook), and a bare `push_mask_state` call has no notion of "first stroke of a session" — it could not be turned GREEN by the plan's own fix (verified: tests stayed RED after the fix because the hook never fired).
- **Fix:** Tests A/B now drive `_on_mask_modified` via `_paint_brush_stroke` + `on_undo` (mirroring the existing `test_undo_mask_applies_snapshot` pattern). Test C stays at the HistoryManager layer (it tests `pop_mask_undo`'s null guard directly). RED re-confirmed against pre-fix source for all three.
- **Files modified:** `tests/test_history.py`
- **Commit:** 9eb9d36

**3. [Rule 1 — Bug] Existing `_painted_mask` produces zero-opacity strokes (false-pass generator)**
- **Found during:** Task 1 (RED probe)
- **Issue:** The single-point `drawLine(p1==p1)` in `_painted_mask` / `_paint_brush_dot` renders ZERO opaque pixels on PySide6 6.x (a degenerate zero-length line is a no-op). Masks built from it are indistinguishable from the transparent baseline, so any test comparing "stroked" vs "clean" is a vacuous `0==0`. The new regression tests need a stroke with measurable content.
- **Fix:** Added `_opaque_stroked_mask` / `_paint_brush_stroke` helpers that paint a real two-point segment. The existing helpers were left UNTOUCHED (out of scope — pre-existing weakness not caused by this plan; the existing mask tests still pass because they only check flags / `alpha()==0`).
- **Files modified:** `tests/test_history.py`
- **Commit:** bcc8f83 (helper) + 9eb9d36

## Verification

- **Task 1's three regression tests PASS** (the symptom test, the mechanism test + bare-history pin, the WR-01 crash test).
- `python -m pytest tests/test_history.py tests/test_mask_editor -q` → 44 passed.
- `QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q` → **257 passed** (was 254 baseline; +3 new). No regression.
- Specific guards re-verified: `test_undo_does_not_repush` (baseline push at stroke time, not undo-application time — T-03-08-03 mitigated), `test_mask_snapshot_is_copied` + `test_mask_pop_returns_copy` (Pitfall-2 detachment).
- RED discipline: all three new tests confirmed FAILING against the pre-fix source (via `git stash` of the two production files), then GREEN after restore.

## TDD Gate Compliance

- **RED gate:** `bcc8f83` — `test(03-08): add failing mask-undo-stuck + WR-01 null-mask regression`. All three tests failed for the correct reason (Tests A/B: popped mask = stroked after-state, 288/324 opaque px, not the clean baseline; Test C: `AttributeError: 'NoneType' object has no attribute 'copy'`).
- **GREEN gate:** `9eb9d36` — `fix(03-08): push mask BEFORE-state on each stroke + WR-01 null-current guard`. All three tests pass; full suite 257 green.

The plan's checker had already corrected the round-1 RED rationale (pop_mask_undo on `[stroked]` returns `stroked.copy()`, NOT None) — the RED commit reflects this corrected rationale and the live probe confirmed it (288 opaque px returned).

## Threat Model Compliance

| Threat ID | Disposition | Status |
|-----------|-------------|--------|
| T-03-08-01 (Repudiation — undo does not remove the stroke) | mitigate | CLOSED — before-state push restores the FLOW-02 contract; Tests A/B lock first-stroke + repeated-undo behaviour |
| T-03-08-02 (DoS — None.copy() crash, WR-01) | mitigate | CLOSED — null-current guard on all four per-type pops; Test C locks it |
| T-03-08-03 (Tampering — baseline push re-corrupts timeline) | mitigate | CLOSED — baseline push happens at STROKE time in `_on_mask_modified`, never at undo-application time (`apply_undo_mask` emits nothing); `test_undo_does_not_repush` still passes |

## Known Stubs

None. The fix is fully wired: `_on_mask_modified` seeds and tracks the before-state on every real stroke; the null guard is on all four pops. No placeholder/TODO/mock data flows to the UI.

## Manual Verification (deferred to end-of-phase human-verify gate)

Paint a stroke, inpaint, Ctrl+Z (inpaint undone), Ctrl+Z (stroke gone, not returned), Ctrl+Z (no crash, no further change). This is the UAT test 3 addendum scenario and is deferred to the end-of-phase gate per `human_verify_mode: end-of-phase`.

## Self-Check: PASSED

- `manga_ai_studio/gui/main_window.py` — FOUND (modified, `_pre_stroke_mask` + before-state push)
- `manga_ai_studio/core/history_manager.py` — FOUND (modified, null-current guards on 4 pops)
- `tests/test_history.py` — FOUND (modified, 3 new tests + 2 helpers)
- `bcc8f83` (RED) — FOUND in `git log`
- `9eb9d36` (GREEN) — FOUND in `git log`
- Full suite: 257 passed (≥254 required) — CONFIRMED
