---
phase: 06-refinement-polish-deferred-fixes-full-curve-editor
plan: 06
subsystem: gui
tags: [curves, show-original, baseline, inpaint-result, gap-closure, pyqt6]

# Dependency graph
requires:
  - phase: 06-refinement-polish-deferred-fixes-full-curve-editor
    provides: 06-05 Curves landed in the MainWindow (_on_curves preview/apply/cancel lifecycle, b376f8a ordering)
provides:
  - CR-01 closed: fresh-page Curves Cancel is a capture-suppressed display-only restore — no baseline capture, no inpaint-result claim, Show Original stays disabled
  - Canvas `_inpainted_qimage` claim gated on `capture_original` (T-06-10) — the preview path can no longer light up before/after compare with no inpaint run
  - Apply pre-restore hardened to the capture-suppressed path; D-14 re-baseline remains exclusively `_apply_geometry_op`'s tail rebaseline_original()
  - No-pre-baseline regression test `test_curves_cancel_fresh_page_no_baseline_poison` (the IN-01 mask removed)
affects: [07-typesetting, verify-work UAT for phase 06]

# Actuals (#2632) — pairs with the plan's estimate (18000 tokens estimateTokens).
# chars/4 over the realized diff (git diff 2cfe8ba..HEAD on the three touched files).
actuals:
  tokens: 1588
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Capture-suppressed display restore: every _on_curves display call goes through set_image_from_numpy_preview(..., capture_original=False)"
    - "Inpaint-result claim gate: _inpainted_qimage set only when capture_original — preview path can never claim an inpaint result"

key-files:
  created: []
  modified:
    - manga_ai_studio/gui/main_window.py
    - manga_ai_studio/gui/canvas.py
    - tests/test_gui_curves_dialog.py

key-decisions:
  - "Cancel restore does NOT call canvas.rebaseline_original() (deliberate deviation from the review's '+ rebaseline_original()' suggestion): VERIFICATION truth 25 prescribes _original_image_numpy STAYS None on fresh pages, and a rebaseline on Cancel would clobber a legitimate pre-inpaint baseline on an already-baselined page. The honest D-14 baseline is established exclusively by _apply_geometry_op's tail rebaseline on Apply."
  - "IN-03 (Cancel leaves stale action enablement) needs no separate fix — moot: the canvas gate keeps _inpainted_qimage None through the whole preview+cancel lifecycle, so _refresh_action_states' has_inpaint gating is correct on every path (proven by Task 1 assertion (d))."

patterns-established:
  - "Cancel/restore paths in dialog slots must use the capture-suppressed preview setter unless the call is a real display write-back"

requirements-completed: [PROJ-04]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "CR-01 closed — fresh-page Curves open→preview→Cancel restores byte-identical with no baseline captured and no inpaint-result claim; Show Original (P) stays disabled (VERIFICATION truth 25 / CR-01 restored)"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_curves_cancel_fresh_page_no_baseline_poison"
        status: pass
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_curves_preview_no_baseline_poison"
        status: pass
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_curves_cancel_restores_exactly"
        status: pass
    human_judgment: false
  - id: D2
    description: "Apply pre-restore hardened — capture-suppressed, b376f8a restore-before-Apply ordering intact, D-14 re-baseline preserved via _apply_geometry_op tail; one undo entry, Ctrl+Z restores the true pre-dialog image"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_curves_apply_pushes_one_entry"
        status: pass
      - kind: unit
        ref: "tests/test_inpainting/test_inpaint_gui.py#test_inpaint_result_contract (capture-enabled claim preserved)"
        status: pass
      - kind: unit
        ref: "tests/test_gui_canvas.py#test_rebaseline_original_after_op"
        status: pass
      - kind: other
        ref: "full suite: python -m pytest -q → 598 passed, 0 failed"
        status: pass
    human_judgment: false

# Metrics
duration: 14min
completed: 2026-08-09
status: complete
---

# Phase [6] Plan [06]: CR-01 Curves Cancel baseline-poison closure Summary

**Capture-suppressed Curves Cancel + apply pre-restore: the fresh-page Show Original baseline can no longer be poisoned, the preview path can no longer claim an inpaint result, and the no-pre-baseline regression test closes the IN-01 masking gap.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-08-09T21:33:50Z
- **Completed:** 2026-08-09T21:47:50Z
- **Tasks:** 2 (1 tracer-TDD, 1 auto)
- **Files modified:** 3

## Accomplishments

- **CR-01 closed (T-06-09):** `_on_curves` Cancel restore (:1281) now routes through `set_image_from_numpy_preview(base.copy(), capture_original=False)` — a fresh page (`_original_image_numpy is None`, the folder-load state) never captures the last preview frame as the Show Original baseline, and no rebaseline runs on Cancel. RED gate proven live: the new regression failed pre-fix with `_original_image_numpy` == the curve-distorted frame (136,151,167) and passes post-fix.
- **T-06-10 closed:** `_set_image_from_numpy` gates `self._inpainted_qimage = qimg` on `capture_original` — the capture-suppressed preview path can no longer claim an inpaint result, so `has_inpaint_result()` stays False through the whole preview+cancel lifecycle and Show Original (P)/Preview-hold stay disabled (IN-03 folded in, proven by assertion (d)).
- **Apply pre-restore hardened:** the b376f8a restore-before-Apply at :1297 also switched to the capture-suppressed preview method — no intermediate capture of the last preview frame on fresh pages; the post-Apply D-14 baseline is still established exclusively by `_apply_geometry_op`'s tail `rebaseline_original()` (:1198), so `test_curves_apply_pushes_one_entry`'s post-op baseline assertion holds unchanged.
- **Missing-test contract delivered:** `test_curves_cancel_fresh_page_no_baseline_poison` — the no-pre-baseline variant (IN-01 mask removed) asserting the `(_original_image_numpy is None, has_inpaint_result() is False)` pair CR-01 violated, byte-exact restore, and Show Original disabled after `_refresh_action_states`.
- **Full suite green at the re-baselined count:** 598 passed, 0 failed (597 + the one new test) — no new dependencies, threat register T-06-09/T-06-10 mitigated as planned.

## Task Commits

Each task was committed atomically:

1. **Task 1 (tracer, TDD RED): fresh-page Cancel baseline-poison regression** - `0e1e673` (test)
2. **Task 1 (tracer, TDD GREEN): capture-suppress cancel restore + gate inpaint claim** - `8816b9c` (feat)
3. **Task 2: capture-suppress curves apply pre-restore** - `b063388` (feat)

## Files Created/Modified

- `manga_ai_studio/gui/main_window.py` - `_on_curves` Cancel restore (:1281) and apply pre-restore (:1297) both via `set_image_from_numpy_preview(base.copy(), capture_original=False)`; no baseline writer on the cancel path
- `manga_ai_studio/gui/canvas.py` - `_set_image_from_numpy` : `_inpainted_qimage = qimg` gated on `capture_original` (:777); the pre-existing None-capture gate (:742-743) untouched
- `tests/test_gui_curves_dialog.py` - new `test_curves_cancel_fresh_page_no_baseline_poison` (50 lines)

## Decisions Made

- **No rebaseline on Cancel (deviation from the review's "+ rebaseline_original()" prescription):** the VERIFICATION missing-test contract asserts `_original_image_numpy` STAYS None on fresh pages; a rebaseline on Cancel would also clobber a legitimate pre-inpaint baseline on an already-baselined page (Show Original would show the pre-dialog image instead of the true pre-inpaint original). The honest D-14 baseline is established exclusively by `_apply_geometry_op`'s tail rebaseline on Apply. Plan-prescribed; documented in the task action.
- **IN-03 needs no separate fix:** moot once the preview path stops setting `_inpainted_qimage` — `_refresh_action_states`' has_inpaint gating (:996-1021) is correct on every path; Task 1's assertion (d) proves it.

## Deviations from Plan

None - plan executed exactly as written. (The "no rebaseline on Cancel" choice is the plan's own prescribed deviation from the review report, documented in the plan's task action — not an executor-introduced change.)

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Truth 25 ("Show Original re-baselines to the post-curves image after Apply (D-14) and is never re-baselined by live previews mid-dialog") is now PASS-able: fresh-page open→preview→Cancel leaves `_original_image_numpy` None, `has_inpaint_result()` False, byte-exact restore, Show Original disabled.
- Apply-path D-14 re-baseline + b376f8a restore ordering intact — existing lifecycle tests unchanged and green.
- Remaining gaps for phase 06: 06-07 (WR-02 dock/toolbar sync) and 06-08 (WR-01 undo-flash op-name) — the next plans in this phase.
- The VERIFICATION.md human_verification item (curve drag fluidity + grid/handle legibility at 150%/200% DPI) is held for the phase UAT gate via /gsd-verify-work — explicitly out of gap scope.

---
*Phase: 06-refinement-polish-deferred-fixes-full-curve-editor*
*Completed: 2026-08-09*

## Self-Check: PASSED

- FOUND: `.planning/phases/06-refinement-polish-deferred-fixes-full-curve-editor/06-06-SUMMARY.md`
- FOUND: `0e1e673` test(06-06): fresh-page Cancel baseline-poison regression (RED)
- FOUND: `8816b9c` feat(06-06): capture-suppress Curves cancel restore + gate inpaint claim
- FOUND: `b063388` feat(06-06): capture-suppress curves apply pre-restore
- Full suite: 598 passed, 0 failed (run post-fix)
