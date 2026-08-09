---
phase: 06-refinement-polish-deferred-fixes-full-curve-editor
plan: 01
subsystem: core
tags: [numpy, curve-lut, image-ops, levels, curves, proj-04]

# Dependency graph
requires:
  - phase: 05-project-persistence-image-ops-export
    provides: levels_lut/levels_page + the image_ops discipline (image_io validation, T-05-07 monotone backstop, .copy() detachment)
provides:
  - curve_lut(points) -> 256-entry uint8 piecewise-linear LUT with the sort/dedupe-last-wins/clip/np.interp backstop
  - curves_page(image, master_points, channel_points) -> master-then-per-channel LUT composition, (H,W,3) uint8 validation, detached .copy()
  - 9 headless curve unit tests pinning identity, monotone, degenerate-input, A1 order, channel independence, idempotency, duplicate-x last-wins
affects: [06-04-curves-dialog, 06-05-mainwindow-curves-wiring, tests/test_core/test_image_ops.py]

actuals:
  tokens: 2658
  tasks: 2
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "LUT backstop (T-05-07 discipline): sort by x, duplicate-x last-wins, clip x/y to [0,255], default (0,0)/(255,255) endpoints, np.interp, round, astype(uint8)"
    - "Master-then-per-channel composition (A1): out_c = channel_lut_c[master_lut[v]] — pinned by test, not prose"

key-files:
  created: []
  modified:
    - manga_ai_studio/core/image_ops.py
    - tests/test_core/test_image_ops.py

key-decisions:
  - "A1 composition order (per-channel LUT AFTER master) confirmed correct in the Task 1 implementation; the Task 2 probe passed immediately — no production change needed"
  - "Duplicate-x dedupe is LAST-WINS (A6), matching the plan's must_haves; locked by test_curve_lut_duplicate_x_last_wins"

patterns-established:
  - "Curve LUTs land beside levels_lut/levels_page — both kept, both still tested (prohibition respected; diff is additions only)"

requirements-completed: [PROJ-04]

coverage:
  - id: D1
    description: "curve_lut: points -> 256-entry uint8 LUT; identity for Linear, monotone S-curve, degenerate-input backstop (no NaN/out-of-range), duplicate-x last-wins"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_core/test_image_ops.py#test_curve_lut_linear_is_identity"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_image_ops.py#test_curve_lut_s_curve_monotone"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_image_ops.py#test_curve_lut_degenerate_backstop"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_image_ops.py#test_curve_lut_duplicate_x_last_wins"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_image_ops.py#test_curve_lut_and_page_idempotent"
        status: pass
    human_judgment: false
  - id: D2
    description: "curves_page: (H,W,3) uint8 validation, master-then-channel composition (A1), channel independence, byte-exact LUT apply, detached .copy()"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_core/test_image_ops.py#test_curves_page_channel_after_master_order"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_image_ops.py#test_curves_page_channel_independence"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_image_ops.py#test_curves_page_master_apply_byte_exact"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_image_ops.py#test_curves_page_validation_and_detach"
        status: pass
    human_judgment: false

# Metrics
duration: 4min
completed: 2026-08-09
status: complete
---

# Phase 6 Plan 1: Curves Headless Math Summary

**curve_lut + curves_page landed in core/image_ops.py beside the kept levels_lut/levels_page — piecewise-linear 256-entry uint8 curve LUTs with the T-05-07 backstop (sort/dedupe-last-wins/clip/np.interp/round/astype) and master-then-per-channel (A1) composition, pinned by 9 headless unit tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-08-09T21:05:53Z
- **Completed:** 2026-08-09T21:09:09Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `curve_lut(points)` — 256-entry uint8 LUT: Linear (no interior points) is byte-identical to `np.arange(256)`; degenerate input (duplicate x, out-of-range y) can never produce NaN or out-of-range values (T-05-07 discipline).
- `curves_page(image_rgb, master_points, channel_points)` — validates (H,W,3) uint8 with the `levels_page` error string, applies the master LUT to all channels then each per-channel LUT after the master (A1: `out_c = channel_lut_c[master_lut[v]]`), returns a detached `.copy()` (Pitfall 2).
- A1 composition order, channel independence, idempotency (single + double application), and duplicate-x last-wins are all pinned by tests — the GUI plans (06-04 CurvesDialog, 06-05 `_on_curves`) build on locked pixel math.
- `levels_lut`/`levels_page` and their tests untouched (prohibition respected; the diff is additions only).

## Task Commits

Each task was committed atomically:

1. **Task 1 (tracer, TDD): curve_lut + curves_page — points→LUT→page path** — RED `a79e79e`, GREEN `ff392ee`, plus docstring `83e5362`
   - `a79e79e` (test): 5 failing tests (identity, S-curve monotone, degenerate backstop, byte-exact master apply, validation + detach)
   - `ff392ee` (feat): curve_lut + curves_page implementations
2. **Task 2 (auto, TDD): composition-order probe + idempotency + per-channel independence** — `1551c2c` (test)
   - 4 probe/lock tests; all pass on the Task 1 implementation — the A1 order was already correct, so no production change was needed (per plan's "no other production change expected")
3. **Rule 1 doc fix:** `83e5362` (docs) — module docstring now names curves in the module's ownership line

**Plan metadata:** `(docs: complete plan)` — final commit follows.

## Files Created/Modified

- `manga_ai_studio/core/image_ops.py` - Added `curve_lut` + `curves_page` (63 lines) below the kept levels functions; module docstring updated to include curves
- `tests/test_core/test_image_ops.py` - Added 9 curve tests (151 lines): identity, S-curve monotone, degenerate backstop, master byte-exact apply, validation + detach, A1 order pin, channel independence, idempotency, duplicate-x last-wins

## Decisions Made

- **A1 composition confirmed by probe, not just prose:** the Task 2 probe test passed immediately against the Task 1 implementation — per-channel-after-master was already the implemented order, so no fix was needed. The pin is now permanent.
- **Duplicate-x dedupe is last-wins (A6):** implemented via an ordered dict pass after sorting — `(64,200)` beats `(64,40)`; locked by `test_curve_lut_duplicate_x_last_wins`.
- No new dependencies (numpy only, as planned).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Stale module docstring after curves math landed**
- **Found during:** Post-Task-2 verification
- **Issue:** The `image_ops.py` module docstring stated the module owns math for "rotate / crop / resize / levels" — false the moment curves math landed; the file's own contract statement was stale.
- **Fix:** One-word docstring update ("... / levels / curves").
- **Files modified:** manga_ai_studio/core/image_ops.py
- **Verification:** Module suite re-run green (17 passed); levels_lut/levels_page untouched.
- **Committed in:** `83e5362`

---

**Total deviations:** 1 auto-fixed (1 bug/doc-accuracy)
**Impact on plan:** Minor doc-accuracy fix only. No scope creep, no new dependencies.

## Issues Encountered

None.

## TDD Gate Compliance

- Task 1: RED `a79e79e` (test) → GREEN `ff392ee` (feat) — gates satisfied in order.
- Task 2: the plan explicitly designed its tests as probes that "fail only if the composition order is wrong" and noted "the idempotency and last-wins tests must pass immediately". All four passed against the Task 1 implementation, so Task 2's RED stage was a lock-in pass with no GREEN needed — a single `test(...)` commit (`1551c2c`) is per-plan behavior, not a gate violation.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The curves pixel math is locked for plans 06-04 (CurvesDialog) and 06-05 (`_on_curves`/`action_curves` wiring) — they consume `curve_lut`/`curves_page` directly with byte-exact contracts.
- Ready for 06-02 (canvas deferred fixes: empty-state overlay, hint copy).

---
*Phase: 06-refinement-polish-deferred-fixes-full-curve-editor*
*Completed: 2026-08-09*

## Self-Check: PASSED

- SUMMARY.md exists on disk
- Commits verified in git log: a79e79e (test RED), ff392ee (feat GREEN), 1551c2c (test Task 2), 83e5362 (docs)
- Final module run: 17 passed / 0 failed
