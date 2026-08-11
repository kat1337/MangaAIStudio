---
phase: 07-typesetting-tran-02-render-translated-text-into-the-page
plan: 02
subsystem: ui
tags: [pyqt, pyside6, qgraphicsview, multi-select, group-move, undo-history]

# Dependency graph
requires:
  - phase: 07-01 (typesetting tracer)
    provides: TextStyle model + shared renderer + opaque overlay + typeset bake; the `_sync_handles` handle-visibility seam and `boxes_snapshot` full-list snapshot the group ops ride on
  - phase: 03 (text boxes)
    provides: Phase 3 D-08 single-select, D-12 silent delete, WR-04 no-drag gate, `boxes_modified` push hook
  - phase: 06 (refinement)
    provides: the 06-WR-01 recorded-op-name undo-flash pattern
provides:
  - Multi-select interaction (Shift+click toggle, plain-click single, empty-canvas clear-all, Esc deselect-all, Ctrl+A Select All Boxes)
  - Grouped move + grouped delete with ONE BOXES snapshot per group op (one Ctrl+Z restores the group) and op-name undo flashes
  - N-selected affordance (3px border + tint on all selected, corner handles on the PRIMARY box only) + single-box resize gate
  - The `_primary_box` tracking + `_is_primary_provider`/`set_primary_owner` seam the Inspector bulk-styling section (plan 07-05) consumes
affects:
  - 07-05 (Inspector common-value styling — "Select All Boxes + apply")
  - 07-04 (typesetting depth plans reusing the multi-select)

# Actuals (#2632) — pairs with the plan's `estimate` (45000) to calibrate.
actuals:
  tokens: 11363    # chars/4 over the realized diff (canvas + box_item + main_window + tests)
  tasks: 3         # tasks completed
  commits: 3       # task commits (plus this docs commit)

# Tech tracking
tech-stack:
  added: []        # zero new packages (T-07-SC accepted)
  patterns:
    - "Group-op ONE-snapshot discipline: arm-time full-list snapshot + single boxes_modified emission (D-09 / T-07-06)"
    - "Recorded-op-name undo flash: canvas stores pending group-op name, main_window consumes via take_pending_boxes_op_name() (06-WR-01 pattern)"
    - "Primary-box tracking: _selection_order list + _primary_box pointer + _refresh_primary_box promotion; box_item consults via weakref owner (cycle discipline)"

key-files:
  created:
    - .planning/phases/07-typesetting-tran-02-render-translated-text-into-the-page/07-02-DIAGNOSTIC.md
  modified:
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/main_window.py
    - manga_ai_studio/gui/box_item.py
    - tests/test_gui_boxes.py

key-decisions:
  - "Ctrl+A verified free in the Phase 1-6 shortcut map (T-07-05) — bound via QKeySequence('Ctrl+A') with a single binding; D-16's Ctrl+- stays untouched (Zoom Out keeps it)"
  - "Group move/delete push exactly ONE BOXES snapshot (arm-time before-state) so one Ctrl+Z reverses the whole group — delete stays silent (D-09/Phase 3 D-12)"
  - "Primary-box ownership via WEAKREF (set_primary_owner(_weakref(self))) — a strong canvas capture would stall Python GC and break Qt teardown ordering"
  - "The QAction 'Select All Boxes' is created in _build_edit_menu (parented, with the other Edit actions) — NOT in __init__ (the crash-prone allocation site identified by the QAction investigation)"

patterns-established:
  - "Multi-select = N=1 case of one state machine: plain click still yields exactly one selected box with the Phase 3 affordance (no parallel single/multi machines — assumption_delta_decision promote)"
  - "Resize stays single-box: _begin_resize gated to len(selectedItems()) == 1; a CornerHandle press in a multi-selection is a no-op (RESEARCH Open Q6)"

requirements-completed: [TRAN-02]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "Multi-select selection mechanics — Shift+click toggle, plain-click single, empty-canvas clear-all (with mask-tool fall-through), Esc deselect-all, Ctrl+A Select All Boxes action with gating"
    requirement: TRAN-02
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_boxes.py#test_multi_select_shift_toggle"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_boxes.py#test_multi_select_plain_click_clears_others"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_boxes.py#test_empty_click_clears_all"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_boxes.py#test_select_all_boxes"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_boxes.py#test_esc_deselects_all"
        status: pass
    human_judgment: false
  - id: D2
    description: "Grouped move + grouped delete — one arm-time snapshot per group op, same-delta group drag, silent group delete, ONE Ctrl+Z restores the whole group, op-name undo flashes ('Moved {n} boxes' / 'Deleted {n} boxes')"
    requirement: TRAN-02
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_boxes.py#test_group_move_one_undo"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_boxes.py#test_group_delete_one_undo"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_boxes.py#test_group_move_no_relayout"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_boxes.py#test_group_move_no_drag_no_op"
        status: pass
    human_judgment: false
  - id: D3
    description: "N-selected affordance — 3px border + hue tint on ALL selected boxes, corner handles on the PRIMARY (last-clicked) box only, single-box resize gate, primary promotion on removal"
    requirement: TRAN-02
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_boxes.py#test_multi_select_affordance_primary_handles"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_boxes.py#test_resize_single_box_only"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_boxes.py#test_primary_removal_promotes"
        status: pass
    human_judgment: false

# Metrics
duration: 105min
completed: 2026-08-11
status: complete
---

# Phase 07 Plan 02: Multi-Select — Grouped Move/Delete + Select All Boxes Summary

**Multi-select interaction lifted from Phase 3 single-select (D-08/D-09): Shift+click toggle, Ctrl+A Select All Boxes, grouped move/delete each pushing ONE BOXES snapshot (one Ctrl+Z reverses the whole group) with op-name undo flashes, and a primary-box affordance (handles on the last-clicked member only) — the bulk-edit foundation plan 07-05's Inspector styling consumes.**

## Performance

- **Duration:** 105 min (continuation session; the cancelled prior session's uncommitted work was reviewed and preserved)
- **Started:** 2026-08-11 (continuation executor)
- **Completed:** 2026-08-11
- **Tasks:** 3
- **Files modified:** 4 (canvas.py, box_item.py, main_window.py, tests/test_gui_boxes.py) + diagnostics

## Accomplishments
- **Selection mechanics (D-08):** Shift+click toggles a box's selection membership without clearing others; a plain click keeps Phase 3 single-select (now the N=1 case); clicking empty canvas clears the WHOLE selection then falls through to the mask-tool dispatch; Esc deselects all; `select_all_boxes()` + the Edit ▸ Select All Boxes action (Ctrl+A, zero-arg-lambda G-05-1 wiring, gated on page_open ∧ box_count>0 ∧ ¬_op_running)
- **Grouped move (D-09):** `_group_move = {item: rect()}` armed at press for every selected box; mousemove applies the SAME delta to all members (setRect + `_sync_handles` per item — reposition-only, RC-1: zero re-layouts, locked by test); release emits `boxes_modified` ONCE with the arm-time snapshot (WR-04 no-drag gate preserved); N>1 records "Moved {n} boxes"
- **Grouped delete (D-09/D-12):** Delete/Backspace with N>1 removes ALL selected boxes silently with ONE pre-delete snapshot and the "Deleted {n} boxes" op name; single-box delete keeps the Phase 3 singular path
- **Op-name undo flashes (06-WR-01):** `take_pending_boxes_op_name()` consumed by `_on_boxes_modified` at push time → the Ctrl+Z flash reads "Undo: Moved 3 boxes" / "Undo: Deleted 2 boxes" instead of the generic "box edit"
- **Affordance (UI-SPEC §32):** 3px hue border + tint on ALL selected members; corner handles on the PRIMARY box only (`_is_primary_provider` via a canvas-installed WEAKREF — cycle discipline); `_begin_resize` gated to exactly one selected box; primary promotion when the last-clicked member leaves the selection
- **QAction issue resolved:** the prior session's native access-violation crash (exit -1073741819) was diagnosed via controlled experiments as heap-layout exposure of a latent teardown UAF — triggered by the stray parentless `QAction("Bisect")` probe in `__init__`, NOT by the plan's code. Probe deleted; full suite green (646 passed).

## Task Commits

Each task was committed atomically:

1. **Task 1: Selection mechanics + Select All Boxes action** - `c60a5b3` (feat)
2. **Task 2: Grouped move + grouped delete — ONE snapshot per group op + op-name flash** - `5f670b8` (feat)
3. **Task 3: N-selected affordance + primary-only handles + single-box resize gate** - `364beca` (feat)

**Plan metadata:** (docs commit follows this summary)

## Files Created/Modified
- `manga_ai_studio/gui/canvas.py` - multi-select state (`_group_move`/`_primary_box`/`_selection_order`/`_pending_boxes_op_name`), Shift+click toggle, `_clear_selection` on empty-canvas click, Esc deselect-all, `select_all_boxes()`, group-move arm/loop/commit, grouped delete, `take_pending_boxes_op_name()`, `_begin_resize` single-box gate, primary-owner weakref wiring, `_add_box`/`_remove_box` primary promotion
- `manga_ai_studio/gui/main_window.py` - `action_select_all_boxes` (Edit menu after Undo/Redo, Ctrl+A, zero-arg lambda) + `_refresh_action_states` gate; `_on_boxes_modified` consumes `take_pending_boxes_op_name()` and records group op names; `_undo_op_label`/`_undo_op_label_for_result` extended op set
- `manga_ai_studio/gui/box_item.py` - `_sync_handles(primary=...)` kwarg (N=1 byte-identical), `set_primary_owner` weakref + `_primary_owner` field, `_sync_handles_for_state` primary consultation
- `tests/test_gui_boxes.py` - 12 new tests (5 selection mechanics + 4 group ops + 3 affordance)
- `.planning/phases/07-typesetting-tran-02-render-translated-text-into-the-page/07-02-DIAGNOSTIC.md` - the QAction crash investigation record (must survive even if the fix failed)

## Decisions Made
- **Ctrl+A binding kept single** (T-07-05): verified free in the Phase 1-6 shortcut map; the action test asserts `shortcut().toString() == "Ctrl+A"`; Ctrl+- remains Zoom Out's (D-16 belongs to 07-05)
- **One snapshot per group op** (D-09/T-07-06): arm-time before-state + single emission, so one Ctrl+Z restores the whole group; group delete stays silent (Phase 3 D-12)
- **Primary via weakref**: `set_primary_owner(_weakref(self))` — a strong canvas capture would stall GC and break Qt teardown ordering
- **`action_select_all_boxes` lives in `_build_edit_menu`**, not `__init__` — the crash investigation showed `__init__`-time QAction allocation perturbs the heap and exposes a latent teardown UAF (see Deviations)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Native access violation in the GUI test battery — misattributed "QAction problem"**
- **Found during:** plan continuation (prior session cancelled on this exact issue)
- **Issue:** the full `tests/test_gui_boxes.py` battery died with `Windows fatal exception: access violation` (exit -1073741819) inside `TextOverlayItem.paint` (`box_item.py:333`). The prior session suspected the Ctrl+A QAction and left a parentless `QAction("Bisect")` probe in `__init__`. Controlled experiments (4 runs) proved: probe present → crash 3/3 (parented AND parentless); probe absent → green 2/2. The extra QAction allocation perturbs the C++ heap, exposing a latent teardown use-after-free (bare-scene `QGraphicsScene` GC'd with a paint event still queued; pytest-qt flushes it at the next test).
- **Fix:** deleted the BISECT probe (diagnostic debris — never part of the plan); created the real `action_select_all_boxes` in `_build_edit_menu` per the plan (parented, shortcut-wired) and re-ran the battery green.
- **Files modified:** manga_ai_studio/gui/main_window.py
- **Verification:** full battery 180 passed (t3 state) + full suite 646 passed, 0 failed
- **Committed in:** c60a5b3 (Task 1 commit), 364beca (Task 3 final state)
- **Documented in:** 07-02-DIAGNOSTIC.md (survives independently)

**2. [Rule 2 - Missing Critical] Task 1's empty-canvas click must clear ALL + keep the mask-tool fall-through**
- **Found during:** Task 1 review of the prior session's staged work
- **Issue:** the staged work had already wired the empty-canvas branch to the multi-select clear, but the acceptance contract (UI-SPEC §12d: mask-tool left-click must still paint) needed an explicit test lock.
- **Fix:** `test_empty_click_clears_all` asserts `selectedItems() == 0` AND `get_mask().pixelColor(...).alpha() > 0` after an empty-canvas brush click.
- **Files modified:** tests/test_gui_boxes.py
- **Verification:** test passes in the Task-1 state and the final suite
- **Committed in:** c60a5b3 (Task 1 commit)

**3. [Rule 1 - Bug] Test-design fixes during battery authoring (no production code change)**
- **Found during:** Task 2/3 test authoring
- **Issue:** three new tests initially failed against CORRECT implementation behavior: (a) plain-click test clicked an already-selected member, which correctly keeps the group for dragging (D-09) — the test must click an UNSELECTED box; (b) group-move delta was asserted against the nominal (40,30) but the synthetic QMouseEvent helpers report `button()=NoButton` on release so the commit path never runs — rewrote to REAL QTest delivery (the `_drive_real_body_drag` pattern) and assert the delivered delta; (c) the corner press at the exact box corner resolved to the box body (arming a group move), not the handle — the press must land in the handle's ±5px offset zone outside the body.
- **Fix:** corrected the three tests (task1_tests/task2_tests/task3_tests blocks).
- **Files modified:** tests/test_gui_boxes.py
- **Verification:** 12/12 new tests pass
- **Committed in:** c60a5b3, 5f670b8, 364beca (per-task test commits)

---

**Total deviations:** 3 auto-fixed (1 blocking, 1 missing-critical-test, 1 test-design)
**Impact on plan:** All auto-fixes necessary for correctness and honest verification. No scope creep — no production behavior was changed beyond the plan's spec (only the probe deletion, which was the fix).

## Issues Encountered
- **QAction crash investigation (major):** see Deviations #1 + `07-02-DIAGNOSTIC.md` for the full controlled-experiment record. Key insight: the crash was NOT a QAction bug — a stray heap-perturbing allocation exposed a latent teardown race; the fix was removing the probe. The latent UAF is logged in `deferred-items.md` (out of scope — does not manifest with plan code).
- **Subagent spawn unavailable:** the user instruction asked to spawn a `gsd-debugger` subagent for the QAction research-and-fix; this runtime has no Task tool. The gsd-debug scientific-method protocol was executed inline by the executor instead (controlled experiments A-D), and the full record was written to 07-02-DIAGNOSTIC.md before any fix attempt.
- **Staged-work preservation:** the prior session's staged changes (canvas.py/box_item.py) and unstaged main_window.py work were preserved and committed across the three task commits; per-task intermediate states were verified green in temp worktrees before each commit.

## Known Stubs

None — every plan deliverable is wired to its data source and exercised by the 12 new tests.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or trust-boundary schema changes. The new surface (Edit-menu action + canvas selection state machine) is UI-internal; the single Ctrl+A binding is locked by test (T-07-05) and the group-op snapshot discipline by T-07-06.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- **Ready for 07-05 (Inspector common-value styling):** `select_all_boxes()` + the multi-select selection state + `boxes_modified` single-snapshot discipline are exactly the mechanism "Select All Boxes + apply style" needs; `_primary_box`/`_is_primary_provider` give the Inspector a stable anchor
- **Ready for 07-04:** the typesetting depth plans can reuse the multi-select for batch text ops
- **Blocker:** none. One deferred item (text-overlay teardown UAF) tracked in `deferred-items.md` — latent, non-manifesting, for a future robustness plan

---
*Phase: 07-typesetting-tran-02-render-translated-text-into-the-page*
*Completed: 2026-08-11*

## Self-Check: PASSED

Verified: SUMMARY.md and DIAGNOSTIC.md exist on disk; task commits c60a5b3 / 5f670b8 / 364beca exist in git log.
