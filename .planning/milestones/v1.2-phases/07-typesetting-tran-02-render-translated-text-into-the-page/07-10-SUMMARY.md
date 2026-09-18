---
phase: 07-typesetting-tran-02-render-translated-text-into-the-page
plan: 10
subsystem: ui
tags: [pyside6, text-renderer, auto-fit, grow-to-fit, tategaki, G-07-4]

# Dependency graph
requires:
  - phase: 04-09-fit-in-box (04-ocr-recognition-text-editing)
    provides: the box-adaptive base / [10,28] clamp / 12x0.9 bounded loop / 5 px floor constants preserved at scene px (D-15)
  - phase: 07-08
    provides: manual-size overlay tests (auto_fit=False) that intentionally isolate this plan's change
provides:
  - "grow-while-fits-with-cap phase in BOTH Auto-fit loops (horizontal layout() + _vertical_fit_size): short text now fills large boxes beyond the old 28 px clamp, capped at min(inner_w, inner_h)"
  - "byte-identical shrink path for text that never fits at the base (5 px floor at the loop TOP, 12-iteration bound)"
affects: [07-UAT test 2 (effects visual quality), canvas overlay rendering, bake_typeset_page, inspector rendered-size display, verify-work]

# Actuals (#2632) — pairs with the plan's `estimate` (16500 estimateTokens) to calibrate future estimates.
actuals:
  tokens: 2332    # chars/4 over the realized diff (9328 diff chars incl. +/- prefixes) — the estimate over-shot ~7x
  tasks: 2
  commits: 5

# Tech tracking
tech-stack:
  added: []  # zero new packages (RESEARCH Package Legitimacy Audit — T-07-SC accept)
  patterns:
    - "grow-while-fits-with-cap: each iteration builds the candidate; fits -> record as doc/size (overflow False), advance target = min(cap, target * 1.1); does not fit -> keep the last-fitting candidate (never a shrink fall-through after growth), else the old 0.9 shrink path"
    - "the growth cap and the fit check share the SAME inner box (min(inner_w, inner_h)) so growth can never overshoot the box"

key-files:
  created: []
  modified:
    - manga_ai_studio/gui/text_renderer.py
    - tests/test_core/test_typeset_layout.py
    - tests/test_gui_boxes.py

key-decisions:
  - "The [10,28] base clamp is the STARTING target, not a hard max — growth multiplies up by _OVERLAY_FIT_GROW_STEP (1.1) while the candidate fits, capped at min(inner_w, inner_h) (the user's 'big enough to fit' report)"
  - "The last-FITTING candidate is always retained on growth overshoot — overflow stays False on the kept candidate (T-07-17)"
  - "A text that never fits at the base follows the exact old shrink path (12 x 0.9, 5 px floor at the loop TOP) — the shrink/floor/budget tests pass byte-identical assertions"
  - "Platform-robust range assertions (used > base, used <= cap) replace the clamp-as-max equality locks for grown text — no magic exact sizes"
  - "The 04-09 overlay twins in test_gui_boxes.py locked the same clamp-as-max sizes; updated to the grow contract (deviation, see below)"

patterns-established:
  - "Pattern: grow-while-fits-with-cap — both loops (horizontal layout() branch and _vertical_fit_size) share the identical shape: floor check at TOP, fit check per candidate, growth capped at min(inner_w, inner_h), last-fit retention on overshoot, byte-equivalent shrink fallback"

requirements-completed: [TRAN-02]

# Coverage metadata (#1602) — drives deterministic UAT routing in verify-work.
coverage:
  - id: D1
    description: "Horizontal Auto-fit grows short text to fill the box (beyond the old 28 px clamp, capped at min(inner_w, inner_h), overflow False) while the shrink/floor/budget paths stay byte-identical"
    requirement: TRAN-02
    verification:
      - kind: unit
        ref: "tests/test_core/test_typeset_layout.py#test_auto_fit_grows_short_text_to_fit"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_typeset_layout.py#test_auto_fit_uses_box_adaptive_base"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_typeset_layout.py#test_auto_fit_shrinks_wrapped_text_to_fit"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_typeset_layout.py#test_auto_fit_floor_terminates_for_huge_text"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_typeset_layout.py#test_auto_fit_fits_long_text_within_loop_budget"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_text_overlay_font_adapts_to_box_size"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_text_overlay_size_is_zoom_independent_scene_px"
        status: pass
    human_judgment: false
  - id: D2
    description: "Vertical Auto-fit grows under the same cap/iteration rules (5 CJK chars grow above the 14 px base, capped); the 2000-char case still floors at 5 px with overflow True"
    requirement: TRAN-02
    verification:
      - kind: unit
        ref: "tests/test_core/test_typeset_layout.py#test_vertical_auto_fit"
        status: pass
    human_judgment: false

# Metrics
duration: 50min
completed: 2026-08-12
status: complete
---

# Phase 07 Plan 10: Auto-fit grow-to-fit Summary

**Both Auto-fit loops (horizontal `layout()` and `_vertical_fit_size`) now grow text to fill the box — short text renders beyond the old 28 px clamp, bounded by a per-box cap `min(inner_w, inner_h)` — while the shrink path, 5 px floor, and 12-iteration bound stay byte-identical for text that cannot fit (G-07-4).**

## Performance

- **Duration:** 50 min
- **Started:** 2026-08-12T01:45:00Z (approx.)
- **Completed:** 2026-08-12T02:35:00Z (approx.)
- **Tasks:** 2 (both TDD — RED + GREEN each)
- **Files modified:** 3

## Accomplishments

- Horizontal Auto-fit: `layout()`'s auto-fit branch restructured into grow-while-fits-with-cap — the box-adaptive base `14·min(w,h)/100` clamped `[10,28]` is now the STARTING target; short text grows by `_OVERLAY_FIT_GROW_STEP = 1.1` per iteration while the candidate fits, capped at `min(inner_w, inner_h)` (the fit check and the cap share the same inner box, so growth cannot overshoot). 'hello' in a 300x300 box: 28 → 88 px (was clamped at 28). The last-fitting candidate is always retained on growth overshoot (overflow stays False).
- Vertical Auto-fit: `_vertical_fit_size` restructured with the identical shape on the unchanged fit check (`ncols <= max_cols and block_h <= inner_h + _EPS`) — 5 CJK chars in a 200x100 box: 14 → 19 px (was pinned at 14); the 2000-char case still floors at 5 px with overflow True.
- Shrink/floor/budget behavior is byte-identical for text that never fits at the base: `test_auto_fit_shrinks_wrapped_text_to_fit`, `test_auto_fit_floor_terminates_for_huge_text`, `test_auto_fit_fits_long_text_within_loop_budget` pass UNCHANGED.
- New `test_auto_fit_grows_short_text_to_fit` + updated `test_auto_fit_uses_box_adaptive_base` / `test_vertical_auto_fit` (range-based growth assertions per the platform-robust convention — no magic exact sizes for grown text).
- Overlay-level twins updated: 9 assertions in `test_gui_boxes.py` that locked the clamp-as-max sizes now assert the grow contract (deviation, below).

## Task Commits

Each task was committed atomically (TDD: test → feat):

1. **Task 1 RED: grow-to-fit contract tests (horizontal)** - `0841914` (test)
2. **Task 1 GREEN: horizontal Auto-fit grows short text to fill the box** - `af86ca1` (feat)
3. **Task 2 RED: vertical Auto-fit contract updated to the grow rule** - `72393bf` (test)
4. **Task 2 GREEN: vertical Auto-fit grows under the same cap/iteration rules** - `32dd5d4` (feat)
5. **Deviation: overlay Auto-fit tests updated to the grow contract** - `5414fa2` (test)

**Plan metadata:** SUMMARY commit is orchestrator-owned (this executor does not write STATE.md/ROADMAP.md).

## Files Created/Modified

- `manga_ai_studio/gui/text_renderer.py` - `_OVERLAY_FIT_GROW_STEP = 1.1` constant; horizontal auto-fit branch (was :547-556) restructured into grow-while-fits-with-cap with last-fit retention; `_vertical_fit_size` (was :463-486) restructured identically; both docstrings updated
- `tests/test_core/test_typeset_layout.py` - `test_auto_fit_uses_box_adaptive_base` (range assertions; clamp-as-max locks removed), `test_auto_fit_grows_short_text_to_fit` (new), `test_vertical_auto_fit` (range assertion; floor case unchanged); shrink/floor/budget tests untouched
- `tests/test_gui_boxes.py` - `test_text_overlay_size_is_zoom_independent_scene_px`, `test_text_overlay_content_refresh_keeps_scene_px_style`, `test_zoom_changed_reapplies_overlay_style_canvas` (overlay == renderer's own layout, > 14), `test_text_overlay_font_adapts_to_box_size` (parametrized base < used <= cap), `test_resize_commit_rewraps_overlay_text_canvas` (re-fit > 28, capped)

## Decisions Made

- Growth cap = `min(inner_w, inner_h)` — the same box the fit check runs against, so the grow phase is bounded by construction (T-07-16 DoS mitigation: no runaway size path; the 12-iteration budget still bounds the loop).
- Last-fitting-candidate retention: a growth overshoot never falls through to a shrink — the kept candidate is always the largest that fit (T-07-17 overflow contract unchanged: overflow False on the kept candidate).
- The 5 px floor stays at the loop TOP and the shrink path is byte-equivalent when the base never fits — per plan prohibition.
- Manual-size rendering (`font_size_px` set, `auto_fit=False`) is untouched — the 07-08 manual-size overlay tests pass unchanged (full suite green proves it).
- Baseline correction: the plan asserted "687 + 1 = 694" but 07-VERIFICATION.md's 687 predates the 07-06/07-07 additions; the actual current baseline was 703 (per the 07-08 rebaselining) → final count **704 passed, 0 failed**.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1/2 - Contract lock] The 04-09 overlay twins in test_gui_boxes.py locked the same clamp-as-max sizes the plan changes**
- **Found during:** Task 2 verification (full suite)
- **Issue:** The plan's affected-test list covered only the layout-level file; 9 assertions across 5 overlay tests in `tests/test_gui_boxes.py` (`test_text_overlay_size_is_zoom_independent_scene_px` x3, `test_text_overlay_content_refresh_keeps_scene_px_style`, `test_zoom_changed_reapplies_overlay_style_canvas`, `test_text_overlay_font_adapts_to_box_size` x3, `test_resize_commit_rewraps_overlay_text_canvas`) asserted the exact old sizes (`== 14.0` / `== 21.0` / `== 28.0`) for auto-fit text — the precise behavior the user reported as a gap. They failed with the grow change (e.g., 14.0 -> 40.0).
- **Fix:** Updated to the platform-robust range convention (same as the layout-level tests): zoom-independence/content-refresh/canvas-zoom tests now compare the overlay against the renderer's OWN `layout()` result for the same box (preserving their zoom-independence purpose) plus a `> 14.0` growth assertion; `test_text_overlay_font_adapts_to_box_size` asserts `base < used <= min(inner_w, inner_h)` per box; the resize-commit test asserts the re-fit exceeds the old 28 px clamp, capped. Overlay shrink/floor/containment tests unchanged.
- **Files modified:** tests/test_gui_boxes.py
- **Verification:** full suite 704 passed, 0 failed
- **Committed in:** `5414fa2`

---

**Total deviations:** 1 auto-fixed (1 contract-lock test update)
**Impact on plan:** Necessary to align overlay-level tests with the plan's own must-have truth (growth beyond the old clamp). No production-code scope creep; no architectural change.

## Issues Encountered

- QRectF(20, 20, 220, 120) vs Box(20, 20, 220, 120): QRectF takes (x, y, width, height) while the Box tuple is (x1, y1, x2, y2) — the reference box is a 200x100 rect, not 220x120. My first expected-value calls used the raw Box tuple as a QRectF, producing a wrong reference (48 px vs the overlay's 40 px). Fixed by constructing `QRectF(20, 20, 200, 100)`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The Auto-fit contract is now "grow to fill, capped; shrink to fit, floored" for both orientations — the canvas overlay, bake, and inspector rendered-size display all consume the same `layout()` result, so the change is uniform across surfaces.
- Remaining G-07 gaps: G-07-1 (vertical/Latin rotation), G-07-2 (font dropdown substring search), G-07-3 (default font), G-07-6 (Ctrl+Z crash), G-07-7 (Mixed align override — already closed by plan 07-09).
- UAT test 2 (effects visual quality) is the human gate that originally surfaced this gap — a visual re-check of a large box with auto-fit short text is the natural verification.

---
*Phase: 07-typesetting-tran-02-render-translated-text-into-the-page*
*Completed: 2026-08-12*
