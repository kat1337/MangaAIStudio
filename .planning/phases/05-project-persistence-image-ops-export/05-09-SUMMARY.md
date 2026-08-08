---
phase: 05-project-persistence-image-ops-export
plan: 09
subsystem: testing
tags: [pytest, pyside6, qtest, regression-fix, gui-testing, gap-closure]

# Dependency graph
requires:
  - phase: 03-project
    provides: BoxItem move via _moving_box -> setRect (canvas.py:1013-1025) — the exact move math referenced by the fix
  - phase: 04-ocr-recognition-text-editing
    provides: UAT re-test 4 regression tests in tests/test_gui_boxes.py (the failing test fixed here)
provides:
  - Green full-suite baseline (493 passed / 0 failed) unblocking every remaining Phase 05 plan's full-suite acceptance criterion and 05-04 Task 2's tests/test_gui_boxes.py verify
  - Root-cause documentation of the QTest int-truncation vs fractional fit-transform artifact for future GUI-test authors
affects: [05-04 (Wave 2 verify targets tests/test_gui_boxes.py), all remaining Phase 05 plans' full-suite green criteria]

actuals:
  tokens: 1551  # chars/4 over the realized diff (6206 diff chars) — test-only fix, 56 insertions / 18 deletions
  tasks: 2      # tasks completed
  commits: 1    # source commits (Task 1); Task 2 was re-measurement only, no changes

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Truncation-tolerant assertions anchor on the DELIVERED value (moved_now) rather than hardcoded literals — environment-independent by construction (T-05-21)"
    - "Real-QTest GUI regressions document their measurement artifacts (int QPoint delivery vs fractional fit transform) in the docstring alongside the historical defect"

key-files:
  created: []
  modified:
    - tests/test_gui_boxes.py — test_moved_box_via_real_events_persists_round_trip: truncation-tolerant precondition + moved-position-anchored round-trip assertion + root-cause docstring

key-decisions:
  - "The 1px-shortfall failure is a TEST-side sub-pixel truncation artifact (QTest/mapFromScene deliver int viewport coords at fractional fit scale 0.18333), NOT a canvas defect — canvas.py:1013-1025 applies the delivered delta exactly; no production code changed"
  - "Precondition asserts movement via rect() (~50px within 45..50 band, axis-symmetric, 60x60 shape intact) so a pos()-divergence defect (delta 0) still fails; the round-trip assertion compares persisted == moved_now exactly"
  - "Post-fix full-suite baseline re-measured: 493 collected / 493 passed, 0 failed (suite grew past the plan-time 462 — strict superset of the 462/462 target)"

patterns-established: []

requirements-completed: [PROJ-04]

coverage:
  - id: D1
    description: "UAT re-test 4 move-round-trip regression test fixed — truncation-tolerant while preserving the pos()/rect() divergence detection value"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_moved_box_via_real_events_persists_round_trip"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_boxitem_pos_and_rect_do_not_diverge_after_move"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_corner_resize_via_real_qtest_events_changes_rect"
        status: pass
      - kind: other
        ref: "full suite: & C:/Users/Stella/.pyenv/pyenv-win/versions/3.14.2/python.exe -m pytest -q -> 493 passed, 0 failed"
        status: pass
    human_judgment: false

# Metrics
duration: 12min
completed: 2026-08-08
status: complete
---

# Phase 05 Plan 09: Move-Round-Trip Regression Fix Summary

**Remediated the deterministic UAT re-test 4 regression failure (462-collected suite, 1 failed) with a test-only, truncation-tolerant fix — precondition anchors on the delivered move via rect() (~50px, 45..50 band, 60x60 shape intact), the round-trip assertion checks persisted == moved_now exactly, and the root-cause docstring records the measured QTest int-truncation artifact at the fractional fit scale; full suite re-measured green (493 passed / 0 failed).**

## Performance

- **Duration:** 12 min
- **Started:** 2026-08-08T14:32:00Z
- **Completed:** 2026-08-08T14:44:00Z
- **Tasks:** 2
- **Files modified:** 1 (tests/test_gui_boxes.py — test-only)

## Baseline Note (for later plans)

Post-fix full-suite baseline: **493 collected / 493 passed, 0 failed** (measured 2026-08-08 via `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q`).
Pre-fix plan-time baseline was 462 collected / 461 passed / 1 failed. The suite grew to 493 since the plan was written (later phase-05 test additions); the failure is gone and the suite is a strict superset of the plan's 462/462 target. Later plans should reference 493 as the green baseline.

## Accomplishments

- Fixed `test_moved_box_via_real_events_persists_round_trip` (precondition + round-trip assertions) so it passes deterministically in the pytest environment where it previously failed with `(69, 69, 129, 129)` vs `(70, 70, 130, 130)`
- Preserved the regression value: a pos()/rect() divergence defect (box left at `(20,20,80,80)`, delivered delta 0) still fails the precondition — assertions are truncation-tolerant, not weaker (T-05-21: bounded 45..50 tolerance + 60x60 shape check + exact `persisted == moved_now` persistence check)
- No production code changed: `manga_ai_studio/gui/canvas.py` untouched — the move math (canvas.py:1013-1025) verified exact; the 1px shortfall is a TEST-side sub-pixel truncation artifact of PySide6 QTest/mapFromScene int delivery at the fractional fit transform (measured scale 0.18333, viewport 1188x1037)
- Sibling regression tests verified unchanged and green: `test_boxitem_pos_and_rect_do_not_diverge_after_move` (exact (70,70) assertions intact — integer-exact canvas-only path) and `test_corner_resize_via_real_qtest_events_changes_rect`
- Full suite re-measured green: 493 passed / 0 failed — unblocks every remaining Phase 05 plan's full-suite criterion and 05-04 Task 2's `tests/test_gui_boxes.py` verify

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix the move-round-trip regression test** — `298effb` (fix(test))
2. **Task 2: Full-suite re-measure** — no commit (re-measurement only; verified 493 passed / 0 failed)

**Plan metadata:** (final docs commit via gsd-tools)

## Files Created/Modified

- `tests/test_gui_boxes.py` - `test_moved_box_via_real_events_persists_round_trip` fixed:
  - Docstring: documents the measured root cause (QTest/mapFromScene int viewport delivery at fractional fit scale → ~0.9px delivered shortfall; canvas applies the delivered delta exactly) and that the assertions are truncation-tolerant while still failing the real UAT re-test 4 defect
  - Precondition: `moved_now[0] != 20 or moved_now[1] != 20` (moved at all), `moved_now[0] - 20 == moved_now[1] - 20` (axis-symmetric delta), `45 <= moved_now[0] - 20 <= 50` (~50px with truncation tolerance), `moved_now[2] - moved_now[0] == 60 and moved_now[3] - moved_now[1] == 60` (60x60 shape preserved)
  - Round-trip: `assert restored[0].box.as_tuple == moved_now` — persisted == actually-moved, environment-independent
  - Surrounding flow untouched (folder setup, real-event move, A→B→A navigation, boxes_snapshot checks); `_drive_real_body_move` unchanged

## Decisions Made

- The 1px shortfall is a TEST-side artifact, not a canvas defect — the checker's verified-fix instruction (fix the test, don't touch production) was honored; canvas.py:1013-1025 is referenced in the docstring as the exact math that applies the delivered delta verbatim
- Assertions anchor on the DELIVERED move position (`moved_now`), never a hardcoded literal — environment-independent by construction; the round-trip assertion compares exactly (`==`), preserving the UAT re-test 4 persistence contract (persisted == moved)
- Regression-value preservation is structural: a pos()-routed move leaves rect() at the original → delta 0 → `45 <= 0 <= 50` fails; a resize-vs-move confusion → shape check fails; the two checks together bound the tolerance (T-05-21)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. The failing state matched the plan's measured diagnosis exactly (`(69, 69, 129, 129)`); the fix produced a green suite on the first run.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Full suite green (493/493) — every remaining Phase 05 plan's "full suite green" acceptance criterion and 05-04 Task 2's `tests/test_gui_boxes.py` verify now run against a green baseline
- The 05-04 Task 2 verify (Wave 2) targets this file — it will now pass where it previously inherited the suite's single failure
- No production changes landed; Phase 4 code remains untouched and correct

## Self-Check: PASSED

- FOUND: tests/test_gui_boxes.py (modified file exists)
- FOUND: .planning/phases/05-project-persistence-image-ops-export/05-09-SUMMARY.md
- FOUND: commit 298effb (fix(test) task 1 commit)
- Full suite re-measure: 493 passed / 0 failed (verified live during Task 2)

---
*Phase: 05-project-persistence-image-ops-export*
*Completed: 2026-08-08*
