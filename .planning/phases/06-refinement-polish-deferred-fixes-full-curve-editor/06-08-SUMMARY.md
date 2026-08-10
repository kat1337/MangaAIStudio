---
phase: 06-refinement-polish-deferred-fixes-full-curve-editor
plan: 08
subsystem: gui
tags: [dock, toolbar, active-tool, qactiongroup, wr-02, gap-closure, pyqt6]

# Dependency graph
requires:
  - phase: 06-refinement-polish-deferred-fixes-full-curve-editor
    provides: 06-03 the six window tool actions joined the panel's exclusive group (the WR-02 defect) + 06-06/06-07 the other two gaps closed
provides:
  - WR-02 closed: dock tool-button clicks (the most common entry) sync dock + toolbar + window actions — two consecutive dock clicks regression-tested
  - The panel's exclusive QActionGroup holds exactly its own six actions; the six window tool actions are checkable STANDALONE actions driven by set_active_tool's explicit action-sync loop
  - Docstrings tell the truth: _make_tool_toolbar_button names the standalone-action + explicit-sync mechanism; zero stale group-membership claims remain
affects: [07-typesetting, verify-work UAT for phase 06]

# Actuals (#2632) — pairs with the plan's estimate (20000 estimateTokens).
# chars/4 over the realized diff (git diff 5b7f05c..HEAD on the two touched files).
actuals:
  tokens: 3444
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Standalone checkable window actions: the six action_tool_* live OUTSIDE the panel's exclusive QActionGroup; set_active_tool's action-sync loop (blockSignals -> setChecked(act.data() == tool) -> unblock) drives their checked state explicitly, and the QToolButtons mirror their default actions"

key-files:
  created: []
  modified:
    - manga_ai_studio/gui/main_window.py
    - tests/test_gui_crop_tool.py

key-decisions:
  - "Ungroup, don't re-wire: the window actions keep their triggered->set_active_tool connections and stay checkable; the group-membership lines are removed and set_active_tool gains an explicit window-action sync loop BEFORE the existing toolbar loop — the group's exclusivity is no longer load-bearing for the toolbar"
  - "No toggled connections on window actions (RESEARCH Pitfall 1): the panel already connects toggled at tools_panel.py:150; a double connection would double-emit tool_changed"

patterns-established:
  - "Dock/toolbar/window tri-surface sync on EVERY entry path: dock click -> panel toggled -> tool_changed -> set_active_tool -> panel set_active_tool + window-action sync loop + toolbar mirror loop"

requirements-completed: [PROJ-04]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "WR-02 closed — dock tool-button clicks (two consecutive) sync the dock panel action, tools_panel.active_tool(), the window action, and the toolbar button; exactly one tool checked everywhere (VERIFICATION truths 9/10 restored)"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_gui_crop_tool.py#test_dock_button_click_syncs_dock_toolbar_and_window"
        status: pass
      - kind: unit
        ref: "tests/test_gui_crop_tool.py#test_toolbar_buttons_track_active_tool (flipped membership assertion + 3 entry paths)"
        status: pass
      - kind: unit
        ref: "tests/test_gui_crop_tool.py#test_crop_is_sixth_exclusive_tool (panel group untouched)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Docstring truth — _make_tool_toolbar_button names the standalone checkable-action mechanism driven by set_active_tool's explicit sync; no stale group-membership claim anywhere in main_window.py"
    requirement: PROJ-04
    verification:
      - kind: other
        ref: "grep: 'standalone checkable-action' == 1 occurrence; 'members of the ToolsPanel' == 0; non-comment 'tool_group.addAction' == 0; 'action_tool_.*setCheckable\\(True\\)' == 6"
        status: pass
      - kind: other
        ref: "full suite: python -m pytest -q → 600 passed, 0 failed"
        status: pass
    human_judgment: false

# Metrics
duration: 11min
completed: 2026-08-09
status: complete
---

# Phase [6] Plan [08]: WR-02 Dock/Toolbar Active-Tool Desync — Gap Closure Summary

**The dock-click path — the most common tool-selection entry — now syncs dock + toolbar + window actions on every click: the six window tool actions are standalone checkable-actions driven by set_active_tool's explicit action-sync loop, and the panel's exclusive group holds exactly its own six actions (VERIFICATION truths 9/10 PASS-able, WR-02 closed).**

## Performance

- **Duration:** 11 min
- **Started:** 2026-08-09T22:03:13Z (22:03:13 -0500, pre-plan HEAD 5b7f05c)
- **Completed:** 2026-08-09T22:13:57Z (22:13:57 -0500)
- **Tasks:** 2 (1 tracer-TDD, 1 auto)
- **Files modified:** 2

## Accomplishments

- **WR-02 closed (T-06-12):** the six `action_tool_*` membership lines added in 06-03 are removed — the window actions STAY `setCheckable(True)` but become standalone, so the 12-action mirrored exclusive group can never fight itself on dock clicks. `set_active_tool` gains a window-action sync loop BEFORE the existing toolbar loop: for each of the six actions, `blockSignals` → `setChecked(act.data() == tool)` → unblock (check the target, uncheck the other five — the group no longer does this). The toolbar loop is kept verbatim; the QToolButtons mirror their default actions, so the buttons follow the actions.
- **RED gate proven live:** `test_dock_button_click_syncs_dock_toolbar_and_window` failed pre-fix with the probe's exact symptom — after `window.tools_panel.action_rectangle.trigger()`, the panel's own action was UNCHECKED (`checked=false`) — and passes post-fix including the SECOND consecutive dock click (Brush), which pre-fix desynced everything.
- **Membership assertions flipped:** `test_toolbar_buttons_track_active_tool` now asserts `action.actionGroup() is None` for all six window actions (shortcut/menu/programmatic sync assertions unchanged and green); `test_crop_is_sixth_exclusive_tool` and `test_tools_panel_tool_group_exclusive` (panel-only) pass untouched — the panel group holds exactly its own six actions.
- **No lying comments:** the `:710-713` D-10 comment block, the `:752-758` crop comment, the toolbar comment at `:878-880`, the `_make_tool_toolbar_button` docstring, and the `set_active_tool` docstring all describe the real mechanism (standalone checkable-actions + explicit sync). No toggled connections added on window actions (RESEARCH Pitfall 1 honored).
- **Full suite re-baselined:** **600 passed, 0 failed** (599 baseline + 1 new dock regression test) — no test elsewhere relied on the window actions' group membership, no new dependencies (T-06-SC intact).

## Task Commits

Each task was committed atomically:

1. **Task 1 (tracer, TDD RED): dock-click sync regression** - `a4264f1` (test)
2. **Task 1 (tracer, TDD GREEN): ungroup window actions + explicit sync loop** - `43a20a5` (feat)
3. **Task 2: docstring gate compliance (no stale group-membership claim)** - `d16afca` (fix)

## Files Created/Modified

- `manga_ai_studio/gui/main_window.py` - six `tool_group.addAction(...)` lines removed (action creation blocks :714-769); D-10/crop/toolbar comment blocks + `_make_tool_toolbar_button` docstring + `set_active_tool` docstring rewritten to the standalone-action + explicit-sync truth; `set_active_tool` gains the window-action sync loop before the toolbar loop
- `tests/test_gui_crop_tool.py` - new `test_dock_button_click_syncs_dock_toolbar_and_window` (two consecutive dock clicks, 6 assertions per click); `test_toolbar_buttons_track_active_tool` membership loop flipped to `actionGroup() is None` + docstring updated

## Decisions Made

- **Ungroup, don't re-wire:** the window actions keep their `triggered` → `set_active_tool` connections and stay checkable — only the group membership is removed. `set_active_tool` is the single sync point for all three surfaces (panel via `tools_panel.set_active_tool`, window actions via the new sync loop, toolbar via the existing mirror loop). This is the plan's prescribed WR-02 fix.
- **Window-action sync loop placed BEFORE the toolbar loop:** the actions are checked explicitly first; the toolbar loop then re-checks the matching buttons (whose QToolButton state propagates back to the action — a harmless no-op now that no group can uncheck anything).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Docstring wording tripped the plan's own grep gate**
- **Found during:** Task 2 (WR-02 closure sweep — acceptance criterion 2)
- **Issue:** My Task 1 docstring rewordings said the window actions are "deliberately NOT members of the ToolsPanel's exclusive QActionGroup" — the phrase still contained the grep-target substring `members of the ToolsPanel`, so `grep -c "members of the ToolsPanel" == 0` found 3 occurrences and failed.
- **Fix:** Rephrased all three occurrences to "deliberately outside the ToolsPanel's exclusive QActionGroup" (D-10 comment at :711, `_make_tool_toolbar_button` docstring :3162, `set_active_tool` docstring :3183).
- **Files modified:** manga_ai_studio/gui/main_window.py
- **Verification:** gate rerun — `members of the ToolsPanel` == 0, `standalone checkable-action` == 1; module 15 passed; full suite 600 passed, 0 failed
- **Committed in:** d16afca (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug — self-inflicted wording that tripped the plan's own acceptance gate; the CONTENT of the fix was already correct)
**Impact on plan:** None — the deviation was a docstring-phrase choice, not a behavior change; all gates green at closure.

## Issues Encountered

None — beyond the docstring gate deviation above, the plan executed exactly as written: the RED gate failed for the right reason (the probe's desync), the GREEN fix passed all six assertions on both dock clicks, and the full suite re-baselined at 600.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Truths 9/10 ("Exactly one checkable window tool action is checked at all times; toolbar mirrors on every entry path" / "Toolbar and Tools dock always show the same active tool") are now PASS-able: the dock-click path — the most common entry — is explicitly regression-tested including the second-click desync the probe found; shortcut/menu/programmatic paths remain locked by the flipped-membership test.
- The panel's exclusive group holds exactly its own six actions (`test_crop_is_sixth_exclusive_tool`, `test_tools_panel_tool_group_exclusive` green); window actions are checkable standalone.
- All three phase-06 review gaps are now closed: CR-01 (06-06), WR-01 (06-07), WR-02 (06-08). Full suite green at 600, no new dependencies.
- The VERIFICATION.md human_verification item (curve drag fluidity + grid/handle legibility at 150%/200% DPI) is held for the phase UAT gate via /gsd-verify-work — explicitly out of gap scope.

---
*Phase: 06-refinement-polish-deferred-fixes-full-curve-editor*
*Completed: 2026-08-09*
