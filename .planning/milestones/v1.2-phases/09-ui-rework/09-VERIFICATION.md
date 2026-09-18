---
phase: 09-ui-rework
verified: 2026-08-22T00:00:00Z
status: passed
score: 25/26 must-haves verified
behavior_unverified: 1
overrides_applied: 0
human_verification:

  - test: "Backstop (09-01/UI-SPEC): with the app running at 100% zoom, select each tool on the strip — the checked button must render the 1px #00d4ff accent border on its :checked state; unchecked buttons sit flat on #2d2d33 with a 1px #3a3a42 border."
    expected: "Visible cyan accent border on the active tool button only; flat dark chrome on the rest."
    why_human: "QSS rendering/pixel judgment — explicitly marked verification: backstop (visual check on the running app, not pixel-unit-testable). QSS presence verified in code (tools_strip.py _STRIP_QSS), rendering not."

  - test: "End-of-phase UAT visual pass: confirm the final layout reads Pages | tools strip | canvas | Panel (left→right); collapse/expand each of the four sections independently; click the chevron and View ▸ Toggle Panel; restart the app and confirm collapsed sections stay collapsed while the chevron state resets."
    expected: "Layout matches D-01/D-02/D-05; independent collapse feels correct; persistence survives restart; chevron is session-transient."
    why_human: "Overall layout feel and interaction quality — the plans' own verification sections defer this to the end-of-phase human gate (human_verify_mode=end-of-phase)."

  - test: "Review the plans' flagged-unverified assumptions/prohibitions (UI-01 'modular = four D-02 sections', UI-02 idempotency/concurrency probes, UI-04 rename reach, UI-05 'levels = curves dialog', and the 13 [flagged-unverified] prohibitions across the three plans)."
    expected: "Human accepts the planner assumptions as implemented (all 13 prohibitions were code-verified compliant this run — see Anti-Prohibition table) or requests changes."
    why_human: "Judgment-tier items per the plans' probe discipline; automated checks cannot ratify a judgment call."
---

# Phase 9: UI Rework Verification Report

**Phase Goal:** User works in a reorganized editor — a modular side panel of discrete independently-collapsible sections, a relocated tools toolbar (corrected by D-05 to sit LEFT of the canvas, between the Pages file list and the canvas), a renamed "Typesetting" section, and a new "Edit" section consolidating the image-editing tools — replacing the monolithic panel and scattered menu/dialog access without removing any existing functionality.
**Verified:** 2026-08-22
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

**Plan 09-01 (Tools strip, UI-03/D-04/D-05/D-06/D-07):**

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Strip embedded between Pages dock and canvas (Pages \| strip \| canvas \| panel) | ✓ VERIFIED | `_build_central_widget` (main_window.py:429-453) builds `[ToolsStrip][canvas]` central container; `test_strip_sits_between_pages_dock_and_canvas` asserts window-x geometry order |
| 2 | Exactly 8 buttons: 6 tools + divider + Detect/Inpaint | ✓ VERIFIED | tools_strip.py:184-221; `test_strip_membership_and_exclusivity` + `test_strip_divider_between_crop_and_detect` |
| 3 | Exclusive selection, exactly ONE tool_changed emission per selection from every path | ✓ VERIFIED | `_on_action_toggled` checked-only path (tools_strip.py:259-272); `test_strip_single_emission_per_selection` covers click + programmatic paths |
| 4 | set_active_tool drives strip checked state; window action_tool_* stay outside the group | ✓ VERIFIED | blockSignals sync loop (tools_strip.py:274-294); group holds exactly the 6 strip actions (tools_strip.py:124-172); crop-tool sync tests green |
| 5 | Detect/Inpaint are non-checkable default-action buttons mirroring window-action gating | ✓ VERIFIED | `setDefaultAction(action_detect_text/action_inpaint)` (tools_strip.py:211-221); `test_detect_inpaint_buttons_mirror_window_actions`; `_refresh_action_states` gates strip actions (main_window.py:1290-1296) |
| 6 | 8 icon-only buttons, tooltips with shortcut, non-null QIcon | ✓ VERIFIED | `test_strip_icons_bundled_and_non_null`; 8 SVGs on disk (gui/assets/icons/); icons live on strip-owned actions (09-01 deviation #1, sound fix for default-action icon re-sync) |
| 7 | Top toolbar = Open Folder \| Fit·100%·Out·In \| Undo·Redo \| Mask Overlay \| Preview (hold) | ✓ VERIFIED | `_build_toolbar` (main_window.py:1115-1158) contains exactly that set; `test_top_toolbar_shrunk_to_d07_contents` |
| 8 | Icons resolve ONLY module-relative (Path(__file__).parent/assets/icons) | ✓ VERIFIED | `_icon()` (tools_strip.py:41,89-96); path-containment assertion in icon test |
| 9 | **Backstop:** checked button renders #00d4ff accent border, unchecked flat #2d2d33/#3a3a42 | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | QSS present verbatim (`QToolButton:checked { border: 1px solid #00d4ff; }`, _STRIP_QSS) but visual rendering is explicitly a backstop — see Human Verification |

**Plan 09-02 (Unified panel, UI-01/UI-02/UI-04/D-01/D-02):**

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 10 | Brush + Detection settings remain as collapsible sections; only 6 tool buttons left for strip | ✓ VERIFIED | `BrushBody`/`DetectionSettingsBody` in tools_panel.py (signals at :100,:184-187); detection-form content carried over; tool-row machinery absent (grep: no set_active_tool/QActionGroup/tool row in tools_panel.py) |
| 11 | ONE "Panel" dock, four sections in D-02 order Detection→Brush→Typesetting→Edit | ✓ VERIFIED | main_window.py:339-389 + `_build_edit_section` (:391-427); `test_panel_dock_hosts_side_panel` + `test_edit_section_is_fourth_in_workflow_order` |
| 12 | Independent collapse via checkable header + plain setVisible; no QToolBox | ✓ VERIFIED | `header.toggled → _apply_expanded → body.setVisible` (side_panel.py:162-183); repo-wide grep: zero QToolBox/QPropertyAnimation in gui/; `test_collapsible_sections_collapse_independently` |
| 13 | Typesetting body IS the InspectorPanel instance; signals unchanged | ✓ VERIFIED | `self.inspector_panel = InspectorPanel()` passed by identity (main_window.py:351-354); `test_typesetting_section_body_is_inspector`; InspectorPanel class/signal names untouched (grep) |
| 14 | Chevron at panel top toggles body, dock stays docked, session-transient | ✓ VERIFIED | `toggle_button` + `set_body_visible` (side_panel.py:274-334); `test_chevron_toggles_body_dock_stays_put` + `test_chevron_toggle_writes_no_settings_keys` |
| 15 | ONE View-menu "Toggle Panel" action; Toggle Sidebar unchanged; no dead-dock actions | ✓ VERIFIED | main_window.py:769-795; `test_view_menu_toggle_panel_drives_body`; grep: zero references to dock_tools/dock_inspector/action_toggle_tools/action_toggle_inspector remain |
| 16 | User-visible chrome reads "Typesetting"/"Panel"; class/signal names untouched | ✓ VERIFIED | `test_rename_sweep_positive_assertions`; remaining "Inspector" hits are internal only (class name, comments, QSS var, objectName — none user-visible); dock title "Panel", section "Typesetting", tooltip updated |
| 17 | Per-section collapse persists via sidePanel/*Expanded keys, tolerant parse, expanded defaults | ✓ VERIFIED | settings_key/provider wiring (main_window.py:352-369,416-427); `_read_side_panel_expanded` tolerant parse (main_window.py:3134-3154, truthy+explicit falsy sets, malformed→expanded); `test_first_run_all_sections_expanded` + `test_collapse_round_trips_through_qsettings` + `test_malformed_stored_value_falls_back_to_expanded` |
| 18 | ONE vertical-only scroll wrap; horizontal scrollbar permanently off | ✓ VERIFIED | single QScrollArea, `ScrollBarAlwaysOff` horizontal / `AsNeeded` vertical, widgetResizable (side_panel.py:286-306) |
| 19 | Relocated signals keep exact names/semantics (brush_size_changed, detect_boxes_changed, dilation_changed, std_dev_threshold_changed, masker_params_changed) | ✓ VERIFIED | Signal declarations verbatim (tools_panel.py:100,184-187); blockSignals mirror pairs + `set_masker_values` bulk guard intact (:350-432); full detection-settings suite green |
| 20 | Section controls keep _refresh_action_states gating | ✓ VERIFIED | Strip action gating carried (main_window.py:1290-1296); `test_all_six_buttons_start_disabled_then_follow_gating` + detect/inpaint mirror test |

**Plan 09-03 (Edit section, UI-05/D-08/D-09):**

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 21 | Fourth section "Edit" = 2-column grid of six text buttons bound via setDefaultAction to LIVE actions | ✓ VERIFIED | `EditSection` (side_panel.py:203-256, setDefaultAction, no lambdas); `test_edit_body_is_two_column_grid_of_six_text_buttons` + `test_buttons_default_action_identity` |
| 22 | Clicking an Edit button triggers the same handler as the old menu entry (zero new op logic) | ✓ VERIFIED | `test_curves_button_click_reaches_on_curves`, `test_crop_dialog_button_click_reaches_on_crop_dialog`, `test_rotate_button_click_rotates_page` (spy/real-effect assertions) |
| 23 | Edit buttons track _refresh_action_states via default-action binding | ✓ VERIFIED | `test_all_six_buttons_start_disabled_then_follow_gating` |
| 24 | Crop TOOL (G) stays strip-only; Edit hosts numeric Crop… dialog — distinct | ✓ VERIFIED | EditSection binds action_crop_dialog (side_panel.py:239-246); `test_crop_tool_and_crop_dialog_stay_distinct` |
| 25 | Menus slimmed (no Rotate▸/Curves…/Resize… in Tools; no Crop… in Edit) while QActions stay ALIVE | ✓ VERIFIED | Membership-removal-only with NOTE comments (main_window.py:1094-1103, 688-690); all six constructions intact (:1039-1077, :676-681); `test_tools_menu_no_longer_lists_image_entries` + `test_edit_menu_no_longer_lists_crop_dialog` |
| 26 | Keyboard reachability unchanged (no shortcuts added/removed; V/B/R/L/E/G, D/C intact) | ✓ VERIFIED | `test_slimmed_actions_carry_no_shortcuts`; shortcut suites green (80 passed at plan close; all touched suites green this run) |

**Score:** 25/26 truths verified (1 present, behavior-unverified — the 09-01 backstop visual row)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `manga_ai_studio/gui/side_panel.py` | CollapsibleSection + SidePanel + EditSection | ✓ VERIFIED | 337 lines; all three classes substantive, wired into MainWindow |
| `manga_ai_studio/gui/tools_strip.py` | ToolsStrip with tool_changed/tool_group/set_active_tool | ✓ VERIFIED | 301 lines; full tool-row machinery relocated |
| `manga_ai_studio/gui/tools_panel.py` | Slimmed to BrushBody + DetectionSettingsBody | ✓ VERIFIED | 19k chars, two body classes, no tool-row machinery |
| `manga_ai_studio/gui/assets/icons/*.svg` (8) | Monochrome 24×24 SVGs | ✓ VERIFIED | All 8 on disk; art-direction test green |
| `pyproject.toml` | package-data covers gui/assets/icons/*.svg | ✓ VERIFIED | `manga_ai_studio = ["gui/assets/icons/*.svg"]` (pyproject.toml:56) |
| `tests/test_gui_side_panel.py` | Collapse/persistence/rename coverage | ✓ VERIFIED | 9 tests, all green |
| `tests/test_gui_tools_strip.py` | Geometry/membership/emission/icon coverage | ✓ VERIFIED | 8 tests, all green |
| `tests/test_gui_edit_section.py` | Structure/parity/membership/shortcut coverage | ✓ VERIFIED | 11 tests, all green |
| Removed: dock_tools, dock_inspector, action_toggle_tools, action_toggle_inspector | Gone by design | ✓ VERIFIED | Zero grep hits in gui/ |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| CollapsibleSection.header | body visibility | `toggled → setVisible` | ✓ WIRED | side_panel.py:162,183 |
| SidePanel sections | QSettings sidePanel/*Expanded | settings_key + provider | ✓ WIRED | side_panel.py:176-177; main_window.py:384-387,425-427 |
| action_toggle_panel | SidePanel body toggle | triggered → set_body_visible | ✓ WIRED | main_window.py:772-773,789-795 |
| MainWindow signal consumers | relocated bodies' signals | unchanged names | ✓ WIRED | detection_body/brush_body wiring; suites green |
| ToolsStrip buttons | strip-owned QActions | setDefaultAction | ✓ WIRED | tools_strip.py:192-196 |
| MainWindow.set_active_tool | ToolsStrip.set_active_tool | direct call | ✓ WIRED | main_window.py:4429 |
| _refresh_action_states | strip Detect/Inpaint buttons | default-action inheritance | ✓ WIRED | main_window.py:1290-1296 + mirror test |
| _icon loader | module-relative assets dir | Path(__file__).parent | ✓ WIRED | tools_strip.py:41,96 |
| Edit buttons | six live window QActions | setDefaultAction | ✓ WIRED | main_window.py:408-415; side_panel.py:252 |
| Edit CollapsibleSection | sidePanel/editExpanded | settings_key | ✓ WIRED | main_window.py:416-427 |

### Data-Flow Trace (Level 4)

Not applicable — this phase relocates UI chrome and entry points; no new dynamic-data rendering surfaces. All section bodies render live, pre-existing widgets (InspectorPanel instance, relocated forms, action-bound buttons) rather than fetched data.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Panel collapse/persistence/rename suite | pytest tests/test_gui_side_panel.py (in batch) | 9 tests green | ✓ PASS |
| Strip geometry/exclusivity/emission/icons/toolbar suite | pytest tests/test_gui_tools_strip.py (in batch) | 8 tests green | ✓ PASS |
| Edit section structure/parity/menu-slimming suite | pytest tests/test_gui_edit_section.py (in batch) | 11 tests green | ✓ PASS |
| Regression: canvas/detection/curves/crop suites | pytest (4 files, in batch) | green | ✓ PASS |

Combined run: **126 passed, 0 failed** (pinned 3.14.2 interpreter, 2026-08-22). Executor-reported full-suite baselines (998 → 1007 → 1018) are consistent with these targeted results; full suite re-run deferred to the executor's own gate per spot-check constraints.

### Probe Execution

None declared — no `probe-*.sh` scripts exist for this phase and no PLAN/SUMMARY declares probe execution. Skipped (not a migration/tooling phase).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| UI-01 | 09-02 | Modular side panel of discrete, independently collapsible sections | ✓ SATISFIED | Truths 10-13, 17-18; side_panel tests |
| UI-02 | 09-02 | Inspector toggle moved to top of side panel | ✓ SATISFIED | Truths 14-15; chevron + Toggle Panel tests |
| UI-03 | 09-01 | Tools toolbar LEFT of canvas, between Pages list and canvas (D-05) | ✓ SATISFIED | Truths 1-8; geometry test proves x-order |
| UI-04 | 09-02 | "Inspector" renamed to "Typesetting" | ✓ SATISFIED | Truths 13, 16; positive rename assertions |
| UI-05 | 09-03 | New "Edit" section houses image-editing tools from menus/dialogs | ✓ SATISFIED | Truths 21-26; edit-section tests |

**Orphaned requirements:** none — REQUIREMENTS.md maps exactly UI-01…UI-05 to Phase 9, and all five appear in plan frontmatter (`09-01: [UI-03]`, `09-02: [UI-01,UI-02,UI-04]`, `09-03: [UI-05]`). No functionality removed: every retired menu/toolbar entry point is reachable via strip button, Edit-section button, or unchanged shortcut (truths 5, 7, 25, 26).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| inspector_panel.py | 176-444 | "placeholder" hits | ℹ️ Info | Qt placeholder text / em-dash placeholder labels — legitimate pre-existing UI copy, not stubs |
| pyproject.toml | 49-56 | `[tool.setuptools] packages` list omits sub-packages | ℹ️ Info | Advisory from 09-REVIEW.md — packaging bug predates Phase 9; package-data entry for icons IS present. Outside this phase's must_haves |

No TBD/FIXME/XXX/HACK debt markers in any phase-modified file. No empty implementations, no console-only handlers, no hardcoded-empty props.

### Prohibition Compliance (judgment-tier, non-authoritative LLM-judge verdicts)

All 13 `[flagged-unverified]` prohibitions across the three plans were checked against the code — **all 13 compliant** (human ratification still requested via Human Verification item 3):

| Prohibition | Verdict | Evidence |
| ----------- | ------- | -------- |
| Never addToolBar(Left) for the strip | ✓ compliant | Strip embedded in central container (main_window.py:429-453) |
| Never merge window action_tool_* into strip group | ✓ compliant | Group holds exactly 6 strip actions |
| Never connect both triggered+toggled for emission | ✓ compliant | Single checked-only toggled path |
| Never CWD-relative icon paths | ✓ compliant | `_icon()` module-relative only |
| Never use QToolBox | ✓ compliant | Zero QToolBox in gui/ |
| Never animate collapse | ✓ compliant | Zero QPropertyAnimation; plain setVisible |
| Never nest per-section scroll areas / horizontal scrollbar | ✓ compliant | One wrap, ScrollBarAlwaysOff |
| Never persist chevron state | ✓ compliant | No key write in toggle path; test-locked |
| Never rename InspectorPanel class/signals | ✓ compliant | Names untouched |
| Never delete QActions during menu slimming | ✓ compliant | All constructions intact |
| Never remove/alter setShortcut during slimming | ✓ compliant | Shortcut audit test green |
| Never put Crop TOOL in Edit / dialog in strip | ✓ compliant | Distinct bindings + test |
| Never implement Edit buttons as lambdas | ✓ compliant | setDefaultAction only |

### Human Verification Required

1. **Backstop: strip accent-border visual check** — run the app, select tools, confirm #00d4ff checked border / flat unchecked chrome (QSS verified present in code; rendering needs eyes). *Why human: explicit backstop — visual judgment, not pixel-unit-testable.*
2. **End-of-phase UAT layout pass** — Pages | strip | canvas | Panel arrangement, collapse feel, restart persistence, chevron session-transience. *Why human: the plans defer layout feel to this gate.*
3. **Ratify flagged-unverified assumptions/prohibitions** — all code-verified compliant this run (table above); human sign-off requested. *Why human: judgment-tier items.*

### Gaps Summary

No gaps. All 25 test-verifiable must-have truths verified with behavioral evidence (126 targeted tests green under the pinned interpreter); all 5 requirement IDs (UI-01…UI-05) satisfied with no orphaned requirements and no removed functionality. All key links wired; all prohibitions code-compliant; no debt markers. The single non-verified item is the 09-01 backstop row (visual accent-border rendering), which is by-design a human check and routes the phase to `human_needed` — not a goal-blocking failure.

**Advisory (outside must_haves, from 09-REVIEW.md):** the `pyproject.toml` `[tool.setuptools] packages` list omits sub-packages (predates Phase 9; icons package-data entry itself is present). Track separately.

---

_Verified: 2026-08-22_
_Verifier: the agent (gsd-verifier)_
