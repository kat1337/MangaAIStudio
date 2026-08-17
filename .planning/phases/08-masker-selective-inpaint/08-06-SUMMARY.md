---
phase: 08-masker-selective-inpaint
plan: 06
subsystem: gui
tags: [boxitem, border-states, inpaint-state, pen-dimension, qpen, dash-pattern, ui-spec-a1, d11-seam]

requires:
  - phase: 08-masker-selective-inpaint
    provides: plan 08-01 — PageBox.inpaint_state(threshold) + inpaint_override (the four return values this plan renders)
  - phase: 03-text-box-detection-interaction
    provides: BoxItem/CornerHandle component layer + _apply_origin_pen/_apply_look_for/itemChange pen paths
provides:
  - BoxItem._inpaint_state attribute (str | None, default None)
  - BoxItem.set_inpaint_state(state) public API — the 08-07 refresh helper's call target
  - Border-state constants: forced hex #e8e8ea, never hex #9a9aa2, dash [6.0, 4.0] scene px (zero new hex values)
  - The 08-UI-SPEC §Color token mapping rendered: solid/dashed = outcome, origin hue = auto gate, greys = user override
affects: [08-masker-selective-inpaint, 09-ui-rework]

tech-stack:
  added: []
  patterns:
    - "Event-driven state -> pen: set_inpaint_state stores the model-derived state and re-derives through the itemChange paths (_apply_origin_pen unselected / _apply_look_for selected) so the ItemSelectedChange hook keeps working unchanged"
    - "The two pen-dimension helpers (_inpaint_pen_color + the dash-style branch) are shared by both apply paths — one behaviour, no divergence between the init path and the selection-change path"
    - "Qt.PenStyle.CustomDashLine + setDashPattern([6.0, 4.0]) in scene-units — dash scales with zoom like the border itself (high-DPI note in UI-SPEC §Accessibility)"

key-files:
  created:
    - tests/test_gui_border_states.py
  modified:
    - manga_ai_studio/gui/box_item.py

key-decisions:
  - "BoxItem consumes the state STRING from PageBox.inpaint_state(threshold) (08-01) and never computes the gate — the single-derivation decision (08-01) holds; this plan only renders the four returns + None"
  - "set_inpaint_state routes through _apply_origin_pen/_apply_look_for (NOT a new pen path) so itemChange:606-624 re-apply stays byte-identical and the selected pen is always re-derived with the CURRENT state"
  - "forced/never replace the origin hue via _inpaint_pen_color — reading rule 2 (hue = who decided) is encoded at the one colour-decider helper, giving rgba(232,232,234,~0.12) / rgba(154,154,162,~0.12) selection tints for free"
  - "Dash only on gate_skipped/never (_INPAINT_DASHED_STATES frozenset) — pattern = outcome (reading rule 1); will_inpaint/forced/None stay SolidLine so the Phase 3 look is the None default"

patterns-established:
  - "Border-state rendering is a pure extension of the existing pen-derivation methods: the four-state matrix is locked at the test file (state x selection x origin grid, 24 parametrized tests), asserting exact hex/style/width/dash read-backs — no pixel-level golden tests needed for a QPen dimension"

requirements-completed: [MASK-03]

coverage:
  - id: D1
    description: "BoxItem.set_inpaint_state renders the four UI-SPEC border states — solid/dashed = outcome, origin hue = auto gate, #e8e8ea forced / #9a9aa2 never greys = user override — at 2px unselected / 3px selected + state-colour tint, with set_inpaint_state(None) preserving the Phase 3 look and selection changes re-deriving the CURRENT state"
    requirement: MASK-03
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_border_states.py#test_will_inpaint_unselected_renders_origin_hue_solid"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_border_states.py#test_gate_skipped_unselected_renders_origin_hue_dashed"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_border_states.py#test_forced_unselected_renders_near_white_solid"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_border_states.py#test_never_unselected_renders_muted_grey_dashed"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_border_states.py#test_selected_auto_states_tint_with_origin_hue"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_border_states.py#test_selected_override_states_tint_with_their_grey"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_border_states.py#test_selected_override_states_keep_handles_visible"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_border_states.py#test_selection_change_rederives_pen_with_current_state"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_border_states.py#test_set_inpaint_state_none_renders_phase3_look"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_border_states.py#test_set_inpaint_state_on_selected_item_rederives_live"
        status: pass
    human_judgment: false
  - id: D2
    description: "Border-state legibility at working zooms on real manga pages (solid-vs-dashed distinguishable, hue readable for all four states, coexisting with the red mask overlay) — the UI-SPEC §UI Considerations backstop row"
    verification: []
    human_judgment: true
    rationale: "Automation proves the QPen values (color/style/width/dash) exactly match the contract, but readability over varied real artwork at 100% and fit-to-window zoom requires a human visual check — held out to the end-of-phase UAT gate per the existing phase cadence."

duration: 6 min
completed: 2026-08-17
status: complete
---

# Phase 08 Plan 06: BoxItem Inpaint Border-State Dimension Summary

**BoxItem.set_inpaint_state(state) renders the 08-UI-SPEC §Color border-state token mapping — solid/dashed encodes the inpaint outcome, origin hue = auto gate, reused-palette greys (#e8e8ea forced / #9a9aa2 never) = user override, widths/tints unchanged — a self-contained pen extension locked by a 24-test state x selection x origin matrix — 830 tests green**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-08-17T19:10:03Z
- **Completed:** 2026-08-17T19:16:10Z
- **Tasks:** 1 (TDD: 1 RED + 1 GREEN commit)
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- `BoxItem` now carries the fourth pen dimension: `_inpaint_state` (str | None, default None) + the public `set_inpaint_state(state)` that stores the state and re-derives the pen through the SAME paths `itemChange` uses — `_apply_origin_pen` (unselected) / `_apply_look_for` (selected) — so the ItemSelectedChange re-apply hook works unchanged and a selection change always renders the CURRENT state (dash, hue, and tint survive select/deselect)
- The UI-SPEC §Color contract is encoded exactly: `will_inpaint` = origin hue SolidLine 2px (the Phase 3 look), `gate_skipped` = origin hue CustomDashLine [6.0, 4.0], `forced` = `#e8e8ea` SolidLine, `never` = `#9a9aa2` CustomDashLine [6.0, 4.0] — **zero new hex values** (both greys are reused palette members, declared like the Phase 1 mask red)
- Selection stays width-encoded: the state's colour/style at 3px with a tint derived from the same state colour at `_TINT_ALPHA` — giving `rgba(232,232,234,~0.12)` / `rgba(154,154,162,~0.12)` for the override states for free — and handles stay visible for every state (D-18: only the box rect's QPen/QBrush participate)
- `set_inpaint_state(None)` renders the Phase 3 look — the backward-compat default before 08-07's `refresh_box_inpaint_states()` ever runs; state strings come straight from `PageBox.inpaint_state(threshold)` (08-01), the single derivation site (BoxItem never computes the gate)
- Verification-wide: the shared pen helpers mean init-path and selection-change-path behaviour cannot diverge; proven by 24 parametrized tests reading exact pen/brush values back

## Task Commits

Each task was committed atomically (TDD: RED test commit → GREEN feat commit):

1. **Task 1: BoxItem.set_inpaint_state — the state pen dimension** - `edce9c6` (test) + `82343de` (feat)

**Plan metadata:** final docs commit (below)

## Files Created/Modified
- `tests/test_gui_border_states.py` - NEW: 24 tests across the four states + None, both origins, selected/unselected + handle visibility + selection-change re-apply + live re-derive while selected; hex/style/width/dash read-backs asserted exactly (probe-verified Qt enum/read-back values)
- `manga_ai_studio/gui/box_item.py` - `_inpaint_state` init attr; `set_inpaint_state()` public API; `_inpaint_pen_color()` helper; `_INPAINT_FORCED_HEX`/`_INPAINT_NEVER_HEX`/`_INPAINT_GREY_STATES`/`_INPAINT_DASH_PATTERN`/`_INPAINT_DASHED_STATES` constants; `_apply_origin_pen` (:606-620) + `_apply_look_for` (:714-728) extended with the colour + dash branches

## Decisions Made
- BoxItem consumes the state STRING; the derivation logic lives only in `PageBox.inpaint_state(threshold)` (08-01) — 08-06 renders, 08-07 refreshes, nobody duplicates
- `set_inpaint_state` routes through the existing pen paths rather than building a new one — `itemChange` (box_item.py:606-624) is byte-identical
- The grey/dashed sets are frozenset module constants — the decider (hue) and the outcome (pattern) are each named once
- Dash uses `Qt.PenStyle.CustomDashLine` + `setDashPattern([6.0, 4.0])` (scene units) — the plan's "CustomLine" shorthand resolves to the real Qt enum (probe-confirmed; dashPattern() reads back `[6.0, 4.0]`, solid reads `[]`)

## Deviations from Plan

None - plan executed exactly as written. All acceptance criteria (state x selection x origin matrix green, source assertions present, full suite green) passed on the first GREEN pass.

## Issues Encountered
None - the RED gate failed for the right reason (`AttributeError: 'BoxItem' object has no attribute 'set_inpaint_state'`), and the GREEN pass went clean on the first implementation attempt; full suite 830 passed / 0 failed (baseline 806 at plan start + 24 new border-state tests).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- 08-07's `MainWindow.refresh_box_inpaint_states()` has its single call target ready: `canvas._box_items` iteration → `PageBox.inpaint_state(threshold)` → `BoxItem.set_inpaint_state(state)`; the trigger wiring (detection finish, threshold/dilation change, override commit, box move/resize release, page load) is the sole remaining seam
- Full suite green confirms the additive rendering broke nothing: box rendering, plane undo/persistence, and detection-settings GUI files all pass unchanged
- No blockers.

## Self-Check: PASSED

Both created/modified files exist on disk; both task commits found in git log (`git log --grep="08-06"` returns 2: edce9c6 test + 82343de feat); full suite re-verified green (830 passed / 0 failed, pinned interpreter); source done-criteria assertions re-run and passing (`def set_inpaint_state`, dash pattern constants, both apply paths consuming the state, zero new hex values).

---
*Phase: 08-masker-selective-inpaint*
*Completed: 2026-08-17*