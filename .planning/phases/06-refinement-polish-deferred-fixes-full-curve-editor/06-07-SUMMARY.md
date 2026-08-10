---
phase: 06-refinement-polish-deferred-fixes-full-curve-editor
plan: 07
subsystem: gui
tags: [curves, undo, redo, flash-label, op-name, gap-closure, pyqt6]

# Dependency graph
requires:
  - phase: 06-refinement-polish-deferred-fixes-full-curve-editor
    provides: 06-06 CR-01 curves cancel/apply lifecycle + 06-VERIFICATION truth 26 gap (WR-01)
provides:
  - WR-01 closed: Ctrl+Z after a curves apply flashes 'Undo: curves', Ctrl+Shift+Z flashes 'Redo: curves' (UI-SPEC surface 28 copy contract honored at runtime)
  - The op-name override is scoped to full-frame (0,0) geometry entries — bbox inpaint pops keep the 'inpaint' label even with a stale recorded op name (T-06-11)
  - Flash-text assertions locked into the curves lifecycle test; scoping guard test added
affects: [07-typesetting, verify-work UAT for phase 06]

# Actuals (#2632) — pairs with the plan's estimate (15000 estimateTokens).
# chars/4 over the realized diff (git diff 168df67..HEAD on the two touched files).
actuals:
  tokens: 1388
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single-entry (0,0)-gated op-name override: _undo_op_label_for_result prefers _last_geometry_op_name for image-only pops whose patch sits at (0,0) — the push_geometry_state full-frame shape — and falls through to the kind-based label otherwise"

key-files:
  created: []
  modified:
    - manga_ai_studio/gui/main_window.py
    - tests/test_gui_curves_dialog.py

key-decisions:
  - "The op-name override is scoped by the (0,0) full-frame gate, not by the recorded-name presence alone: push_geometry_state stores geometry records as (0, 0, patch) (history_manager.py:435), so (x, y) == (0, 0) identifies the geometry-record shape; a stale _last_geometry_op_name must never leak into ordinary bbox inpaint undos"
  - "Accepted limitation documented in the _undo_op_label_for_result docstring: after two consecutive image-only geometry ops, the second undo labels by the LAST recorded op name (both pops are single (0,0) image entries) — stamp-based robust resolution is out of gap scope; the code review's minimal fix is the prescribed shape"

patterns-established:
  - "Label resolution for a single-entry image pop must distinguish geometry-record shape ((0,0) full-frame) from inpaint-patch shape (non-origin bbox) before consulting the recorded op name"

requirements-completed: [PROJ-04]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "WR-01 closed — after a curves Apply, Ctrl+Z flashes 'Undo: curves' and Ctrl+Shift+Z flashes 'Redo: curves' with a byte-exact post-op restore; VERIFICATION truth 26 PASS-able at runtime (UI-SPEC surface 28 copy contract)"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_curves_apply_pushes_one_entry (flash assertions + byte-exact redo restore)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Scoping guard — a non-origin bbox image entry (real push_image_action) undos as 'Undo: inpaint' even while _last_geometry_op_name == 'curves' (stale); the superseded op-name set ('rotate', 'crop', 'curves', 'resize') is intact, 'levels' only in the historical comment"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_single_image_pop_keeps_inpaint_label"
        status: pass
      - kind: other
        ref: "grep: set literal count == 1 at main_window.py:2916; 'levels' only at :2906 (historical indented comment)"
        status: pass
      - kind: other
        ref: "full suite: python -m pytest -q → 599 passed, 0 failed"
        status: pass
    human_judgment: false

# Metrics
duration: 6min
completed: 2026-08-09
status: complete
---

# Phase [6] Plan [07]: WR-01 Undo/Redo Flash Labels 'curves' — Gap Closure Summary

**The curves undo/redo flash now names the op the user actually undid: Ctrl+Z after a curves Apply flashes 'Undo: curves' (not 'Undo: inpaint'), scoped by a (0,0) full-frame gate that keeps ordinary bbox inpaint undos labeled 'inpaint' — VERIFICATION truth 26 is PASS-able at runtime.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-08-09T21:54:39Z
- **Completed:** 2026-08-09T21:59:12Z
- **Tasks:** 2 (1 tracer-TDD, 1 auto)
- **Files modified:** 2

## Accomplishments

- **WR-01 closed (T-06-11):** `_undo_op_label_for_result` (main_window.py:2938) gained a single-entry image branch — when `kind == "image"` and a geometry op name is recorded, a pop whose patch sits at `(0, 0)` (the `push_geometry_state` full-frame shape, history_manager.py:435) flashes the recorded op name instead of falling through to the kind-based 'inpaint' label. RED gate proven live: the extended lifecycle test failed pre-fix with `'Undo: curves' in 'Undo: inpaint'` — the exact probe symptom — and passes post-fix with 'Undo: curves' / 'Redo: curves'.
- **Byte-exact redo restore asserted:** the lifecycle test now also redo-restores the post-op image (`np.array_equal` vs the `curves_page` `expected`) and locks the 'Redo: curves' flash.
- **Scoping guard (T-06-11):** `test_single_image_pop_keeps_inpaint_label` drives a real curves Apply (recording `_last_geometry_op_name == 'curves'`), undoes it, pushes a non-origin `(5, 5)` bbox entry through the REAL `HistoryManager.push_image_action`, and asserts the next undo flashes 'Undo: inpaint' with the stack empty — the override cannot leak into ordinary inpaint undos.
- **Supersession sweep green:** the op-name set literal `("rotate", "crop", "curves", "resize")` occurs exactly once (main_window.py:2916); `'levels'` exists only in the historical indented comment (:2906). Full suite: **599 passed, 0 failed** (598 baseline + 1 new test) — no test lost, no regressions, no new dependencies.
- **All pre-existing lifecycle assertions untouched and green:** byte-exact apply, ONE image-only entry, mask/boxes untouched, `geometry_altered` False, 'Curves applied.' flash, D-14 post-op baseline, b376f8a restore semantics (Ctrl+Z → byte-identical pre-dialog image + empty stack).

## Task Commits

Each task was committed atomically:

1. **Task 1 (tracer, TDD RED): curves undo/redo flash labels regression** - `50b75d6` (test)
2. **Task 1 (tracer, TDD GREEN): single-entry (0,0)-gated op-name override** - `09986c4` (feat)
3. **Task 2: single-image-pop inpaint-label scoping guard** - `1b49071` (test)

## Files Created/Modified

- `manga_ai_studio/gui/main_window.py` - `_undo_op_label_for_result` single-entry image branch: `(x, y) == (0, 0)` + recorded op name → the geometry-op label; otherwise the kind-based label; docstring documents the accepted two-consecutive-image-only-ops limitation; `len(result) > 1` branch kept verbatim
- `tests/test_gui_curves_dialog.py` - `test_curves_apply_pushes_one_entry` extended with 'Undo: curves' / 'Redo: curves' flash assertions + byte-exact redo restore (14 lines); new `test_single_image_pop_keeps_inpaint_label` (44 lines)

## Decisions Made

- **The (0,0) gate, not recorded-name presence, scopes the override:** geometry records are stored as full-frame patches at (0,0) by `push_geometry_state`; bbox inpaint entries (`push_image_action`) are non-origin. Checking `(x, y) == (0, 0)` on the popped value is the only reliable discriminator between a curves pop and an inpaint pop — the recorded op name alone is ambiguous after consecutive ops.
- **Accepted limitation documented in the docstring:** two consecutive image-only geometry ops label the second undo by the LAST recorded op name. The stamp-based robust resolution (resolving the label from the popped record's own stamp) is deliberately out of gap scope — the review's minimal fix is the prescribed shape per the plan's `must_haves`/action text.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- **Acceptance-grep line windows drifted ~10 lines:** the plan's grep-gate line ranges (`29[2-4][0-9]` for the fix site, `:2905` set literal, `:2895` historical comment) were estimates from pre-fix line numbers; the docstring growth in `_undo_op_label_for_result` shifted the consult to :2969/:2975, the set literal to :2916, and the 'levels' comment to :2906. The CONTENT of every gate is satisfied (op-name consult inside the single-entry branch; set literal exactly once; 'levels' only in the historical comment) — only the literal line heuristics drifted.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Truth 26 ("The undo/redo flash op-name set is ('rotate', 'crop', 'curves', 'resize') — 'levels' replaced, not appended") is now PASS-able at runtime: Ctrl+Z flashes 'Undo: curves', Ctrl+Shift+Z flashes 'Redo: curves', and ordinary single-kind pops keep their Phase-3 labels (mask edit / box edit / inpaint).
- The remaining phase-06 gap is 06-08 (WR-02 dock/toolbar highlight desync) — the next plan in this phase.
- The VERIFICATION.md human_verification item (curve drag fluidity + grid/handle legibility at 150%/200% DPI) is held for the phase UAT gate via /gsd-verify-work — explicitly out of gap scope.

---
*Phase: 06-refinement-polish-deferred-fixes-full-curve-editor*
*Completed: 2026-08-09*

## Self-Check: PASSED

- FOUND: `.planning/phases/06-refinement-polish-deferred-fixes-full-curve-editor/06-07-SUMMARY.md`
- FOUND: `50b75d6` test(06-07): curves undo/redo flash labels regression (RED)
- FOUND: `09986c4` feat(06-07): single-entry (0,0)-gated op-name override for undo/redo flash
- FOUND: `1b49071` test(06-07): single-image-pop inpaint-label scoping guard
- Full suite: 599 passed, 0 failed (run post-fix)
