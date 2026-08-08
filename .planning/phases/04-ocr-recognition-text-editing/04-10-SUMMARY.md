---
phase: 04-ocr-recognition-text-editing
plan: 10
subsystem: gui (bubble badge digit-fit + inspector bubble-number 0-sentinel)
tags: [gui, box-item, badge, inspector, bubble-number, gap-closure, uat-test-4, uat-test-6, tdd, pytest-qt]
requires:
  - Phase 04 Plan 04 badge rendering (BoxItem._badge rect + _badge_digit child, refresh_badge TL-outside placement + edge-flip, UI-SPEC §17)
  - Phase 04 Plan 04 InspectorPanel bubble spinbox + WR-01 no-op guard (_loaded_bubble baseline, _emit_bubble_if_changed)
  - Phase 04 Plan 04 MainWindow _on_inspector_bubble_committed (D-16 manual_override pin)
provides:
  - DIGIT-SIZED bubble badge: refresh_badge measures the digit's tight glyph line box (document margin 0) after setPlainText, resizes the badge rect to digit_w + 2x4 by digit_h + 2x2 padding, re-centers the digit, and places TL-outside with the same 2px offset computed from the ACTUAL badge size; the edge-flip decision uses the actual size; measured-digit floor guard max(1.0, ...) (T-4-16g)
  - 0-sentinel bubble number: bubble_spin setRange(0, 9999) + setSpecialValueText em dash; load_box maps None -> 0; clear() resets to 0; WR-01 guard (number != _loaded_bubble) unchanged — a user-entered 1 now differs from the unset baseline and commits; _on_inspector_bubble_committed maps 0 -> bubble_no=None + manual_override=False (clearing is not an override), 1..9999 -> assign + pin (D-16 unchanged)
  - 10 new test cases (Gap A: 3 digit-count size/containment/centering cases + 2 per-digit TL-outside placement cases + 1 cross-size tracking case + 1 edge-flip case = 7; Gap B: 3) — full suite 461 passed, 0 failed (451 baseline + 10 new; the pre-existing flake test_moved_box_via_real_events_persists_round_trip stays deselected)
  - Four 04-UI-SPEC amendment notes (Spacing badge-size row SUPERSEDED, §17 Widget digit-sized, §Color bullet 3 size correction, §18 Bubble # 0-sentinel deviation)
affects:
  - UAT test 4 + test 6 re-verification (the mechanical contracts are now observable; the on-artwork visual judgment stays a human UAT call per the project cadence)
  - Any future plan touching badge geometry, the Inspector bubble field, or the bubble_no write path (the 0 sentinel never reaches the model — T-4-08 unchanged)
tech-stack:
  added: []
  patterns:
    - measure-then-size badge: setPlainText FIRST, then boundingRect() (never sceneBoundingRect on the ignores-transformations child — local units are viewport px), floor with max(1.0, ...), resize the rect and re-center the digit from the SAME measured locals so placement (one source of truth) cannot diverge from the rendered geometry
    - 0-sentinel QSpinBox: setRange(0, 9999) + setSpecialValueText('\u2014') makes the unset state display as an em dash (consistent with the Origin/Language placeholder labels); the sentinel is mapped to None in the MainWindow handler BEFORE the model write, so pagebox.bubble_no only ever receives None or 1..9999
key-files:
  created: []
  modified:
    - manga_ai_studio/gui/box_item.py
    - manga_ai_studio/gui/inspector_panel.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_gui_boxes.py
    - .planning/phases/04-ocr-recognition-text-editing/04-UI-SPEC.md
key-decisions:
  - "Platform font metrics differ from the plan-checker's probe: on the exec machine the digit glyph line box at the 12pt semibold Liberation Sans badge font is 9.45x19 px per digit (not 16x19), so the badge sizes are 17.45x23 / 26.9x23 / 36.36x23 (not 24x23 / 40x23 / 56x23). The badge tests derive expectations from the MEASURED digit rect (per the plan's own NOTE: don't hard-code platform font assumptions); the plan's probe values stay as docstring reference values. The digit-height 19 does match the probe; only the width differs (Liberation Sans advance on this Qt/font stack)."
  - "Gap A has 7 test cases (not 6): the platform-robust Test B can no longer encode the fixed-size bug as a hard-coded position (pre-fix placement (-3,3) vs the plan's probe-reference (-7,-6)/(-23,-6) is platform-dependent), so the RED-carrying cross-size assertion lives in a separate test_badge_tl_outside_tracks_size_across_digits; the parametrized per-case tests document the actual-size contract. Suite target becomes 461 (451 + 10), not 460 — superset of the plan count, 0 failed."
  - "The 0-sentinel keeps the WR-01 no-op discipline byte-for-byte: the guard comparison (number != _loaded_bubble) is unchanged; only the baseline value moved (1 -> 0). A numbered box loads with _loaded_bubble = its number, so 0 != n always commits — the 0-clearing path can never be confused with an unchanged cycle (T-4-18g)."
  - "setSpecialValueText is display-only: typing still edits normally and value 1 renders '1' (probe-verified on PySide6 6.10.1); negatives clamp to 0 (the sentinel)."
requirements-completed: [TEXT-05]
coverage:
  - id: D1
    description: "Bubble badge fits its number (UAT test-4 truth): refresh_badge measures the digit glyph line box (document margin 0) after setPlainText, resizes the badge rect to digit_w + 8 by digit_h + 4, re-centers the digit ((badge_w - dw)/2, (badge_h - dh)/2), keeps the digit fully contained (no top-half clipping, no multi-digit overflow) at any zoom (ItemIgnoresTransformations), and places TL-outside with the same 2px offset computed from the ACTUAL badge size; the edge-flip at the page TL corner uses the actual size."
    requirement: TEXT-05
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_badge_rect_sizes_to_digit"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_badge_tl_outside_uses_actual_badge_size"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_badge_tl_outside_tracks_size_across_digits"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_badge_edge_flip_uses_actual_size"
        status: pass
    human_judgment: false
  - id: D2
    description: "Bubble # 1 is manually assignable (UAT test-6 truth): an unset box (bubble_no=None) displays the em-dash sentinel (setSpecialValueText at value 0, never a phantom '1'); entering 1 + Enter commits bubble_no_changed(1) (1 != the 0-sentinel baseline passes the WR-01 guard) and end-to-end sets pagebox.bubble_no=1 with manual_override=True (D-16 amber badge refreshed); committing 0 clears to bubble_no=None + manual_override=False (unset is not an override)."
    requirement: TEXT-05
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inspector_bubble_spin_unset_sentinel"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inspector_bubble_1_commit_assigns_unset_box"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inspector_bubble_1_assigned_and_cleared_end_to_end"
        status: pass
    human_judgment: false
  - id: D3
    description: "WR-01 preserved: unchanged focus cycles stay silent no-ops on both unset (0 vs 0) and numbered (n vs n) boxes — no spurious edited/manual-override/BOXES entries; only REAL changes commit."
    requirement: TEXT-05
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inspector_unchanged_focus_cycle_is_noop"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inspector_unchanged_commit_is_noop_end_to_end"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inspector_bubble_changed_commit_still_emits"
        status: pass
    human_judgment: false
  - id: D4
    description: "On-artwork visual judgment: the digit-sized badge fits its number over real manga artwork at the TL-outside corner at production zooms (UAT test-4 re-verification)."
    requirement: TEXT-05
    verification: []
    human_judgment: true
    rationale: "The mechanical contract (digit measurement basis, badge size = glyph + padding, containment, centering, actual-size placement, edge-flip) is fully covered by the automated suite; whether the badge reads well over REAL manga artwork is a visual judgment no offscreen test can make — deferred to the UAT test-4 re-verification (end-of-phase human gate per the project cadence in STATE.md)."
metrics:
  duration: 12 min
  completed: 2026-08-08
  tasks: 2
status: complete
---

# Phase 04 Plan 10: UAT Gap Closure Round 3 (Badge Digit-Fit + Bubble-1 Sentinel) Summary

**Round-3 gap closure: the bubble badge is now DIGIT-SIZED (measured glyph line box + 4px/2px padding, actual-size TL-outside placement and edge-flip, no more top-half clipping or multi-digit overflow) and bubble # 1 is manually assignable (0 is the unset sentinel — the em-dash display, the WR-01 baseline, and the clear-to-None handler all agree).**

## Performance
- **Duration:** 12 min
- **Tasks:** 2 (TDD: RED + GREEN per task)
- **Files modified:** 5

## Accomplishments
- **Gap A (UAT test 4) closed:** `_BADGE_W`/`_BADGE_H` fixed 20x14 constants deleted; `_BADGE_PAD_W=4.0`/`_BADGE_PAD_H=2.0` padding constants added. `refresh_badge` now sets the digit text first, measures the digit's LOCAL bounding rect (document margin 0.0 — the tight glyph line box; floor `max(1.0, ...)` per T-4-16g), resizes the badge rect, re-centers the digit, and places TL-outside from the ACTUAL rect (same 2px offset for every digit count). Edge-flip logic untouched (now sees the real size). Stale "constant 20x14" prose reworded (checker W1). Badge sizes on this platform: 17.45x23 (1 digit) / 26.9x23 (2) / 36.36x23 (3) — always digit + 8 x digit + 4.
- **Gap B (UAT test 6) closed:** `bubble_spin` range 1..9999 -> 0..9999 with `setSpecialValueText("\u2014")` (the same em dash as the Origin/Language placeholder labels) and initial value 0. `load_box` maps `None -> 0`; `clear()` resets to the 0 sentinel; the WR-01 guard is unchanged (a user-entered 1 now passes: 1 != 0). `_on_inspector_bubble_committed` branches: 0 -> `bubble_no=None` + `manual_override=False` (clearing is not an override); 1..9999 -> assign + `manual_override=True` (D-16 unchanged). The model only ever receives None or 1..9999 (T-4-08 mitigation unchanged).
- **TDD discipline:** 4 commits — `test(04-10)` RED (badge fcddc09, sentinel 4fcebd2) then `fix(04-10)` GREEN (badge 3b7ca6f, sentinel f400073). RED failures verified against the true pre-fix source before each fix.
- **Suite:** 461 passed, 0 failed, 1 deselected (the pre-existing flake `test_moved_box_via_real_events_persists_round_trip` — out of scope, not touched). 451 baseline + 10 new cases. The deferred manga reading-order gap (UAT test 5) is untouched; the 04-08/04-09 deliverables are untouched (Task 2's main_window.py edit is scoped to `_on_inspector_bubble_committed`).

## Task Commits
1. **Task 1: Gap A — badge sized to the digit** - `fcddc09` (RED tests) + `3b7ca6f` (GREEN fix + spec notes a/b/c)
2. **Task 2: Gap B — 0 is the unset bubble sentinel** - `4fcebd2` (RED tests + range-test update + comment-only WR-01 wording) + `f400073` (GREEN fix + spec note d)

## Files Created/Modified
- `manga_ai_studio/gui/box_item.py` - padding constants replace fixed badge sizes; constructor builds a 1x1 badge + margin-0 digit at (0,0); refresh_badge measures/sizes/centers/places from the actual badge geometry
- `manga_ai_studio/gui/inspector_panel.py` - spinbox 0..9999 + em-dash special value; None->0 mapping in load_box; clear() resets to 0; 0-sentinel docstrings (module, class security note, WR-01 guard)
- `manga_ai_studio/gui/main_window.py` - `_on_inspector_bubble_committed` sentinel branch (0 -> None + no override; 1..9999 -> assign + pin)
- `tests/test_gui_boxes.py` - 7 new badge digit-fit cases + 3 new sentinel cases; `test_inspector_bubble_spin_range_is_bounded` minimum 1->0; comment-only 0-sentinel wording in two WR-01 tests
- `.planning/phases/04-ocr-recognition-text-editing/04-UI-SPEC.md` - four amendment notes (a: Spacing badge-size row SUPERSEDED, b: §17 digit-sized, c: §Color bullet 3 size correction, d: §18 0-sentinel deviation)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking reference values] Platform font metrics differ from the plan-checker's probe**
- **Found during:** Task 1 GREEN verification
- **Issue:** The plan's probe-verified digit width (16x19 px per digit at the 12pt semibold badge font; badges 24x23/40x23/56x23; placements -7/-6 and -23/-6) does not reproduce on the exec machine: the digit measures 9.45x19 px per digit (probe: `QFontMetricsF` '3' = 7.95x17.88; in-item `boundingRect` = 9.45x19), so the badge sizes are 17.45x23 / 26.9x23 / 36.36x23 and the placements are -0.45/-6 and -9.9/-6. Hard-coded 24/40/56 assertions can never pass GREEN on this platform.
- **Fix:** Per the plan's own NOTE ("the test must not hard-code an assumption that the platform font differs; use the measured digit boundingRect"), the badge-size/placement assertions derive from the MEASURED digit rect: rect == digit + 8 x digit + 4, centering from the measured size, placement == actual rect + 2px gap, edge-flip (1,1) unchanged (size-independent). The plan's probe values are preserved as docstring references.
- **Files modified:** tests/test_gui_boxes.py
- **Commit:** 3b7ca6f, 4fcebd2

**2. [Rule 1 - Test design] Gap A carries 7 cases (not 6) — suite 461 (not 460)**
- **Found during:** Task 1 GREEN
- **Issue:** With measured-derived assertions, the per-case parametrized placement test passes pre-fix (rect and placement both read the fixed constants, so the gap check holds) — the fixed-size bug needed a cross-case assertion. The platform-robust RED gate for "badge tracks its size" is a separate test function (`test_badge_tl_outside_tracks_size_across_digits`: the 2-digit badge must sit further TL than the 1-digit one — fails pre-fix at -3 vs -3). Gap A: 3 + 2 + 1 + 1 = 7 cases.
- **Fix:** Split the placement test; documented the count delta.
- **Files modified:** tests/test_gui_boxes.py
- **Commit:** 4fcebd2 (test restructure rides the Task 2 RED commit — test-only)

**3. [Process] Task 2 RED commit includes the Gap A test restructure**
- **Found during:** post-Task-1 cleanup
- **Issue:** The Test B restructure (deviation 2) landed after the Task 1 GREEN commit and was swept into the next test-only commit (4fcebd2).
- **Fix:** None needed — 4fcebd2 is test-only and the final tree state is correct; noted for history accuracy.
- **Files modified:** tests/test_gui_boxes.py
- **Commit:** 4fcebd2

## Known Stubs

None — both fixes are fully wired (badge sizes from the live digit measurement; sentinel flows through load_box/clear/guard/handler with no placeholder values reaching the UI).

## Threat Flags

None — no new network endpoints, auth paths, or file access patterns. The bounded-spinbox trust boundary (T-4-08) is preserved (0..9999 with the sentinel mapped to None before the model write); badge digit-measure arithmetic floored (T-4-16g); placement one-source-of-truth (T-4-17g); WR-01 guard unchanged with the new baseline (T-4-18g).

## Next Phase Readiness
- UAT test 4 and test 6 re-verification can now pass on the mechanical contract; the on-artwork visual judgment remains the end-of-phase human gate.
- The 0-sentinel contract (None or 1..9999 reaches the model; 0 is display/handler-internal) is the documented baseline for any future bubble-number plan.
- Deferred items unchanged: manga reading-order gap (UAT test 5) and the pre-existing round-trip flake — both out of scope per the user's explicit instructions.

## Self-Check: PASSED
- Files verified on disk: box_item.py, inspector_panel.py, main_window.py, test_gui_boxes.py, 04-UI-SPEC.md, 04-10-SUMMARY.md
- Commits verified in git log: fcddc09 (Task 1 RED), 3b7ca6f (Task 1 GREEN), 4fcebd2 (Task 2 RED), f400073 (Task 2 GREEN)
- Full suite (flake deselected): 461 passed, 0 failed
- Grep gates: `_BADGE_W|_BADGE_H` == 0, `_BADGE_PAD_*` refs >= 2, setDocumentMargin == 1, `self._badge_digit.boundingRect()` == 1, `setRect(0.0, 0.0` == 1; setRange(0, 9999) == 1, setSpecialValueText == 1, `is not None else 0` == 1, `_loaded_bubble = 0` == 2, `if number == 0` (main_window) == 1, setRange(1, 9999) == 0
