---
phase: 06-refinement-polish-deferred-fixes-full-curve-editor
plan: 04
subsystem: ui
tags: [pyside6, qpainter, curves, histogram, collector-dialog, numpy]

# Dependency graph
requires:
  - phase: 06-refinement-polish-deferred-fixes-full-curve-editor
    provides: 06-01 curve_lut/curves_page (LUT math + A1 composition)
provides:
  - CurveWidget: QPainter curve control (grid/diagonal/histogram/points, D-04/D-07 interaction)
  - CurvesDialog: collector + preview driver (D-01…D-08: presets, channels, In/Out, gamma↔midpoint, cross-clamps, once-at-open histogram, 14px Body)
affects: [06-05 (wiring into _on_curves + levels_dialog.py deletion), verify-work UAT surface 30]

# Actuals (#2632) — pairs with the plan's estimate (45000 tokens) to calibrate future estimates.
actuals:
  tokens: 27152    # chars/4 over the two files changed (curves_dialog.py + test file)
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Collector + preview driver (Pitfall 9): dialog never mutates models; ONE _updating-guarded _refresh is the single sync+preview path"
    - "Curve as single source of truth (D-02/D-03): _refresh re-points the channel dict at the widget's list every pass (reference can never diverge)"
    - "Forward-only gamma injection: _gamma_syncing guard makes the back-map a display mirror that never re-injects the (128,y) point"
    - "Cross-clamp applied to the CURVE state itself (black max = white−1, white min = black+1) — the slider-side mirror of levels_dialog"

key-files:
  created:
    - manga_ai_studio/gui/curves_dialog.py
    - tests/test_gui_curves_dialog.py

key-decisions:
  - "CurveWidget._points is assigned BY REFERENCE from _channel_points[current]; _refresh re-points the dict from the widget's list each pass so external reassignment can never desync the collector"
  - "points_changed fires on press-add / release (NOT per move pixel) — the T-06-06 preview-storm mitigation; the widget still repaints live during the drag"
  - "Gamma back-map snaps the diagonal to exactly 1.00 (raw 1.0054 rounds to 1.01) so the defaults contract 'gamma 1.00 ↔ midpoint 128' holds at open; injection stays forward-only (user gamma edits) via _gamma_syncing"
  - "Endpoint cross-clamp enforced on the curve points themselves (not just the slider/spin pairs): a widget-dragged inversion clamps immediately (T-05-07, test_curve_endpoint_cross_clamp_no_inversion)"
  - "In spinbox disabled for endpoints (x fixed at 0/255, range [x,x]) — 'endpoints never move horizontally' rendered in the numeric row"

patterns-established:
  - "Pattern 1: every control change funnels through ONE _refresh (levels_dialog discipline, verified by an inspect-based single-call-site regression test)"
  - "Pattern 2: histogram arrays stored raw (256 counts), normalized by max at paint time — resize-safe, computed ONCE at open (D-08 identity-locked)"

requirements-completed: [PROJ-04]

coverage:
  - id: D1
    description: "CurveWidget D-04 interaction — click-add (last-wins on occupied x), drag clamps (x strictly between neighbors, y 0..255, endpoints y-only), double-click-delete (never endpoints), 10px hit radius, 280x240 minimum"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_click_adds_point_at_mapped_coordinate_and_selects"
        status: pass
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_drag_moves_point_with_clamps"
        status: pass
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_double_click_deletes_interior_but_never_endpoints"
        status: pass
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_endpoint_drag_changes_only_y"
        status: pass
    human_judgment: false
  - id: D2
    description: "CurveWidget D-07 keyboard story — arrows nudge ±1 (Shift=±10), Tab/Shift+Tab cycle selection, StrongFocus"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_arrow_keys_nudge_selected_point"
        status: pass
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_tab_cycles_selection"
        status: pass
    human_judgment: false
  - id: D3
    description: "CurveWidget paint — grid 64/16, muted diagonal, faint histogram bars (0.14 alpha), accent 2px curve, 8x8/10x10 handles; paint smoke with and without a histogram"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_widget_paint_smoke"
        status: pass
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_widget_paint_with_histogram"
        status: pass
    human_judgment: false
  - id: D4
    description: "CurvesDialog defaults + D-12 typography — 0/255/1.00, Linear (0 interior points), RGB, In/Out at the selected point, 14px Body from birth"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_dialog_defaults"
        status: pass
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_dialog_font_14px"
        status: pass
    human_judgment: false
  - id: D5
    description: "Bidirectional sync D-02/D-03 — black/white rows drive the endpoints with the white>black cross-clamp (on sliders AND curve state), gamma 1.00↔midpoint 128 with back-map and forward injection, In/Out spins drive the selected point with neighbor-respecting ranges"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_black_slider_moves_left_endpoint_with_clamp"
        status: pass
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_curve_endpoint_cross_clamp_no_inversion"
        status: pass
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_in_spin_range_respects_neighbors"
        status: pass
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_gamma_100_matches_midpoint_and_backmaps"
        status: pass
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_gamma_change_injects_midpoint_point"
        status: pass
    human_judgment: false
  - id: D6
    description: "Collector contract — Apply stores detached (master, channel_points) result_values; Cancel/reject never stores; preview fires on every control change with the composed payload"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_on_apply_stores_result_values_and_accepts"
        status: pass
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_reject_does_not_store"
        status: pass
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_preview_fires_on_control_changes"
        status: pass
    human_judgment: false
  - id: D7
    description: "Presets D-05 + channel switcher D-06 — A2 coordinates replace the current channel's points and stay editable; Linear restores the diagonal; per-channel edits preserved across switches; verbatim UI-SPEC copy"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_preset_replaces_points_and_stays_editable"
        status: pass
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_channel_switcher_preserves_per_channel_edits"
        status: pass
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_preset_and_channel_copy_verbatim"
        status: pass
    human_judgment: false
  - id: D8
    description: "Histogram D-08 computed ONCE at open (luminance master, plane per channel) — array identity unchanged after editing; widget histogram follows channel switches"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_histogram_computed_once_at_open"
        status: pass
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_channel_switch_updates_widget_histogram"
        status: pass
    human_judgment: false
  - id: D9
    description: "Preview composition driver — _refresh is the single preview_callback call site; payload is byte-exact image_ops.curves_page output (A1 master→channel)"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_preview_byte_exact_vs_curves_page"
        status: pass
      - kind: unit
        ref: "tests/test_gui_curves_dialog.py#test_refresh_is_single_preview_driver"
        status: pass
    human_judgment: false

# Metrics
duration: 47min
completed: 2026-08-10
status: complete
---

# Phase 6 Plan 4: Full Curve Editor Dialog Summary

**CurveWidget (QPainter curve control) + CurvesDialog (collector + preview driver) implementing UI-SPEC surface 30 — the dialog that replaces the Levels dialog, with the curve as the single source of truth (D-01…D-08, PROJ-04 "curves" half)**

## Performance

- **Duration:** 47 min
- **Started:** 2026-08-09T23:39:49Z
- **Completed:** 2026-08-10T00:26:49Z
- **Tasks:** 3
- **Files modified:** 2 (both new)

## Accomplishments

- **CurveWidget** — custom QPainter control: 256-unit square plot with 64/16 gridlines, muted diagonal, faint D-08 histogram bars (0.14 alpha), accent 2px curve polyline, 8x8 interior / 10x10 endpoint handles. Full D-04 mouse story (10px hit-test, click-add with last-wins on occupied x, drag with x-order + [0,255] clamps, double-click-delete, endpoints y-draggable only) and D-07 keyboard story (arrows ±1 / Shift=±10, Tab/Shift+Tab cycling, StrongFocus). `points_changed`/`point_selected` signals drive the dialog.
- **CurvesDialog collector** — Levels collector shape extended: preset row (Linear/S-curve/Brighten/Darken, editable starting points), exclusive RGB/R/G/B channel switcher (per-channel point sets), black/white quick-access rows above the grid, gamma row, In/Out spins, Cancel/Apply. ONE `_updating`-guarded `_refresh` is the single sync + preview path: cross-clamp enforced on the curve state itself (black max = white−1, white min = black+1 — T-05-07), gamma back-mapped from the sampled output at input 128 (A3) with forward-only (128,y) injection, In spinbox range [prev_x+1, next_x−1] (disabled for endpoints).
- **Histogram D-08** — computed ONCE at open from the detached page image (luminance 0.299R+0.587G+0.114B for the master, plane for R/G/B); array identity locked by test; follows channel switches.
- **Preview driver** — `_refresh` composes `image_ops.curves_page(master, channels)` (A1 master→channel) and fires `preview_callback` — the single call site in the file (grep + inspect-based test). 14px Body typography from birth (D-12).
- **27 new tests** (tracer 9 + dialog 11 + task-3 7) all green; full suite 596 passed, 0 failed.

## Task Commits

Each task was committed atomically:

1. **Task 1: CurveWidget QPainter curve control (tracer)** - `c41d91f` (feat)
2. **Task 2: CurvesDialog collector — quick-access rows, bidirectional sync, In/Out spins** - `906da5f` (feat)
3. **Task 3: Presets + channel switcher + histogram + preview composition driver** - `a522ca9` (feat)

**Plan metadata:** pending (docs commit)

## Files Created/Modified

- `manga_ai_studio/gui/curves_dialog.py` (NEW, ~830 lines) — `CurveWidget` (paint/mouse/keyboard/signals + geometry helpers) and `CurvesDialog` (collector + preview driver, `_DIALOG_QSS` extended with QToolButton accent-checked rules + 12px helper labels)
- `tests/test_gui_curves_dialog.py` (NEW, ~470 lines) — 9 widget tests + 11 dialog contract tests + 7 presets/channels/histogram/preview tests

## Decisions Made

- **Widget-points-by-reference + re-point in `_refresh`:** the dialog hands `CurveWidget._points` the current channel's list; every `_refresh` re-points `_channel_points[current]` at the widget's list, so the reference can never diverge even if code reassigns `widget._points` directly (test-driven — the first cross-clamp test caught a desync).
- **Gamma back-map snaps the diagonal to exactly 1.00** (raw ln(0.5)/ln(128/255) ≈ 1.0054 would round to 1.01) so the defaults contract "gamma 1.00 ↔ midpoint 128" holds; `_gamma_syncing` makes the back-map display-only so it never re-injects the (128,y) point (injection is forward-only, on user gamma edits).
- **Cross-clamp applied to the curve points themselves** (not just the slider/spin pairs): a widget-dragged endpoint inversion clamps immediately, keeping the preview and every control consistent — the exact T-05-07 mirror of the Levels slider clamp.
- **`points_changed` fires on press-add/release, not per move pixel** (the plan's prescription — keeps the preview storm bounded per T-06-06); the widget repaints live during the drag.

## Deviations from Plan

None - plan executed exactly as written. (Two implementation refinements surfaced by the plan's own tests and settled within the plan's design space: the `_gamma_syncing` forward-only injection guard and the `_refresh` re-pointing of the channel dict — both documented in Decisions Made.)

## Issues Encountered

- Gamma back-map rounding: `round(ln(0.5)/ln(128/255), 2)` = 1.01 ≠ 1.00, which would violate the defaults contract (dialog would open at gamma 1.01 and inject a midpoint point). Fixed with the snap-to-1.00 on the raw value + `_gamma_syncing` guard. (Rule 1 auto-fix, committed in Task 2's commit.)
- Widget/dict reference desync in tests that reassign `widget._points` directly — fixed by re-pointing the channel dict from the widget's list in `_refresh`. (Rule 1 auto-fix, Task 2 commit.)

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 06-05 can wire `_on_curves` (renamed from `_on_levels`) against `CurvesDialog`: read `result_values` = (master_points, channel_points), run the b376f8a restore-before-Apply ordering, `_apply_geometry_op("curves", geometry=False, …)`, delete `levels_dialog.py` and migrate its tests. The collector contract (no model mutation, single preview driver) is ready for that wiring.
- The end-of-phase visual backstop (drag fluidity, grid/handle legibility at 150%/200% DPI) is held out for the phase UAT gate per UI-SPEC surface 30.

## Self-Check: PASSED

- Files: `manga_ai_studio/gui/curves_dialog.py`, `tests/test_gui_curves_dialog.py`, `06-04-SUMMARY.md` — all FOUND on disk.
- Commits: `c41d91f` (T1 tracer), `906da5f` (T2), `a522ca9` (T3) — all FOUND in git log.
- Verification: `tests/test_gui_curves_dialog.py` 27 passed; full suite 596 passed, 0 failed; grep gate — exactly one `preview_callback(` call site.

---
*Phase: 06-refinement-polish-deferred-fixes-full-curve-editor*
*Completed: 2026-08-10*
