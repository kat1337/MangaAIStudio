---
phase: 08-masker-selective-inpaint
plan: 05
subsystem: ui
tags: [tools-panel, detection-settings, masker-config, qsettings, ini-persistence, qscrollarea, pyqt-gui, gui-tests]

requires:
  - phase: 08-masker-selective-inpaint
    provides: 08-01's MaskerConfig.mask_dilation_radius + the startup load_profile fix (load applies to config.current_profile)
  - phase: 01-cleaning-workspace
    provides: vendored MaskerConfig INI machinery + ProfileManager profile save/load
provides:
  - ToolsPanel "Detection settings" section (10 contracted rows: Detect Boxes toggle + 9 masker parameters) with verbatim UI-SPEC Copywriting tooltips
  - The D-15 paint-tool tooltip extension ("… hold Alt to select or move a box.") while Crop's tooltip is byte-identical
  - ToolsPanel signals detect_boxes_changed / dilation_changed / std_dev_threshold_changed / masker_params_changed + set_masker_values/masker_values readers
  - MainWindow wiring: Detect Boxes removed from the Tools menu (A8), QSettings "detectBoxesMode" view-state (A7), _save_masker_profile + four commit handlers (D-10 save-through)
  - Vertical-only QScrollArea body wrap so the dock never clips at 1024x720 (A11)
affects: [08-masker-selective-inpaint, 09-ui-rework]

tech-stack:
  added: []
  patterns:
    - "QScrollArea vertical-only body wrap for dock overflow (A11) — tool/brush rows pinned at top, section scrolls"
    - "QSettings IniFormat bool coercion on read (default True) for mode-style view-state (A7: Detect Boxes is a mode, not a profile param)"
    - "Action-as-state-holder + dock-checkbox sync with bidirectional blockSignals (no feedback loop; single QSettings write path)"
    - "Programmatic widget population with blockSignals so a startup/load never re-emits (set_masker_values); mirror pairs emit exactly once"

key-files:
  created:
    - tests/test_gui_detection_settings.py
  modified:
    - manga_ai_studio/gui/tools_panel.py
    - manga_ai_studio/gui/main_window.py

key-decisions:
  - "Detect Boxes persists as QSettings view-state 'detectBoxesMode' (A7) NOT the profile INI; action_detect_boxes_mode is kept alive as the state holder (its isChecked() is still read by the detection seam) and removed from the Tools menu (A8)"
  - "masker_values() returns a MaskerConfig-field-keyed dict so MainWindow's _on_masker_params_changed setattrs directly onto profile.masker (one save per change for the seven shared-fate fit params)"
  - "The two LIVE handlers (_on_dilation_changed / _on_std_dev_threshold_changed) persist ONLY in this plan with an explicit 08-07 extension-point comment — live re-dilate/gate-re-derive ride the seam plan"
  - "The Task-1 Tab-chain test enumerates the radius slider AND spinbox as separate widgets (11 total) — the UI-SPEC 'ten controls' contract counts the pair as one row; both members are asserted reachable"

patterns-established:
  - "Panel section builder extracted as _build_detection_settings_section() — the QScrollArea body is shared with the existing tool/brush rows"
  - "beans: QSS objectName selectors (#_detection_divider / #_detection_section_header) for the 1px #3a3a42 divider + 12px Semibold muted header instead of inline per-widget styles"

requirements-completed: [MASK-01, MASK-02]

coverage:
  - id: D1
    description: "ToolsPanel 'Detection settings' section — Detect Boxes toggle + nine masker parameters with verbatim Copywriting tooltips, declared ranges/defaults, four class-scope signals"
    requirement: MASK-01
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_detection_settings.py#test_set_masker_values_populates_without_emission"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_detection_settings.py#test_section_defaults_match_ui_spec"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_detection_settings.py#test_all_section_controls_reachable_in_tab_chain"
        status: pass
    human_judgment: false
  - id: D2
    description: "D-15 paint-tool tooltip extension (verbatim Copywriting row) with Crop tooltip byte-identical — no production behavior change, pure copy"
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_detection_settings.py#test_paint_tool_tooltips_extended_crop_unchanged"
        status: pass
    human_judgment: false
  - id: D3
    description: "MainWindow save-through — dilation/std-dev/threshold and the seven fit params persist to profile.masker and the 'default' profile INI round-trip across sessions (D-10)"
    requirement: MASK-01
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_detection_settings.py#test_dilation_change_updates_profile_and_ini_round_trips"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_detection_settings.py#test_std_dev_threshold_change_persists"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_detection_settings.py#test_masker_params_change_persists_once"
        status: pass
    human_judgment: false
  - id: D4
    description: "Detect Boxes relocation — absent from the Tools menu (A8), action state-holder retained, QSettings view-state persisted and applied at startup (A7, default on)"
    requirement: MASK-02
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_detection_settings.py#test_detect_boxes_removed_from_tools_menu_action_kept"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_detection_settings.py#test_checkbox_toggle_syncs_action_and_persists_qsettings"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_detection_settings.py#test_startup_renders_persisted_profile_and_qsettings"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_detection_settings.py#test_startup_defaults_detect_boxes_on_when_no_key"
        status: pass
    human_judgment: false
  - id: D5
    description: "Visual adequacy of the dock section at the 1024x720 minimum — QScrollArea scrollability, divider/header rendering, tooltip wrap legibility"
    verification: []
    human_judgment: true
    rationale: "Automation proves the widgets exist, are wired, and are keyboard-reachable, but the physical 'never clips / renders cleanly' truth at minimum window size is a visual property no Qt unit test asserts — deferred to the end-of-phase visual gate."

duration: 45 min
completed: 2026-08-17
status: complete
---

# Phase 08 Plan 05: Detection-Settings UI + Persistence Summary

**ToolsPanel "Detection settings" section (Detect Boxes toggle relocated from the Tools menu + the nine masker parameters with verbatim PanelCleaner tooltips) over a vertical QScrollArea, wired to MainWindow commit handlers that save-through the profile INI (D-10) and QSettings "detectBoxesMode" view-state (A7/A8) — 806 tests green**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-08-17T18:20:00Z
- **Completed:** 2026-08-17T19:03:45Z
- **Tasks:** 2 (Task 1 TDD: RED + GREEN commits)
- **Files modified:** 3 (1 created test file, 2 production GUI files)

## Accomplishments

- **ToolsPanel detection-settings section** (UI-SPEC surface 36): the panel body now wraps in a vertical-only `QScrollArea` (A11 — the dock never clips at 1024×720; tool + brush rows pinned at top), then the section: 1px `#3a3a42` divider, 12px Semibold muted "Detection settings" header, and `QFormLayout` rows (6px spacing) for the relocated **Detect Boxes** checkbox (D-05), **Dilation radius** slider+spinbox mirror 0–10 default 2 (D-09), **Std-dev threshold** 0–100 / 0.5-step / 1-decimal default 15 (D-12), and the seven next-detect fit params (growth step/steps, min thickness, off-white, improvement, allow colored, fast selection). Every tooltip is verbatim from the 08-UI-SPEC Copywriting table (which adapts the vendored `MaskerConfig` INI comments + appends the live/next-detect clauses — A12).
- **D-15 tooltip extension**: the four paint-tool action tooltips now read "… — paints under text boxes; hold Alt to select or move a box." verbatim; Crop's tooltip is byte-identical to its pre-Phase-8 text (D-17).
- **Four new class-scope Signals** (`detect_boxes_changed(bool)`, `dilation_changed(int)`, `std_dev_threshold_changed(float)`, `masker_params_changed()`) with `set_masker_values(masker_conf, detect_boxes)` (blockSignals population, no re-emission) and `masker_values()` (a `MaskerConfig`-field-keyed dict for the seven params).
- **MainWindow wiring**: the `tools_menu.addAction(self.action_detect_boxes_mode)` line is gone (A8) while the action lives on as the state holder (still read by `_on_detection_finished`); the dock checkbox syncs it bidirectionally (blockSignals — no feedback loop) and persists QSettings `"detectBoxesMode"` (A7, default on). `_save_masker_profile()` (OSError-guarded, loguru warning) backs the four commit handlers: dilation + std-dev thresholds persist only with explicit 08-07 live-application extension points; the seven fit params copy through `masker_values()` and save once. Startup populates the section from `config.current_profile.masker` + the view-state (riding 08-01's load fix).

## Task Commits

Each task was committed atomically (Task 1 was TDD):

1. **Task 1: ToolsPanel detection-settings section** - `c0f34e1` (test) + `df44fa1` (feat)
2. **Task 2: MainWindow wiring — toggle relocation, persistence, save-through** - `84c4ee7` (feat)

**Plan metadata:** final docs commit (below)

## Files Created/Modified

- `manga_ai_studio/gui/tools_panel.py` - QScrollArea body wrap; `_build_detection_settings_section()` with the ten rows + verbatim tooltips; new Signals; `set_masker_values()`/`masker_values()`; radius mirror handlers; D-15 tool action tooltips
- `manga_ai_studio/gui/main_window.py` - Tools-menu removal note + state-holder comment; `_wire_tool_actions` detection-settings wiring + startup population; `_read_detect_boxes_mode`, `_save_masker_profile`, `_on_detect_boxes_changed`, `_on_action_detect_boxes_toggled`, `_on_dilation_changed`, `_on_std_dev_threshold_changed`, `_on_masker_params_changed`
- `tests/test_gui_detection_settings.py` - NEW: 12 tests (5 widget-level Task-1 + 7 MainWindow Task-2)

## Decisions Made

- Detect Boxes is **view-state (QSettings)**, not a profile param (A7) — the dock checkbox is the single user-facing control (A8); the action remains as the state holder for the detection seam
- `masker_values()` keys match `MaskerConfig` field names so the seven fit params setattr directly onto `profile.masker` in one handler + one save
- `_read_detect_boxes_mode()` coerces non-bool QSettings reads (`"true"/"1"/"yes"/"on"`) for IniFormat robustness; QSettings round-trips native bools on this platform (probe-verified)
- LIVE handlers persist-only with inline 08-07 extension-point comments (the plan's explicit seam boundary)

## Deviations from Plan

### Auto-fixed Issues

None — plan executed as written. Two TEST-side notes (not production deviations):

**1. [Test note] Tab-chain test enumerates 11 widgets, not "ten"**
- **Found during:** Task 1 (widget-level tests)
- **Issue:** The plan's behavior line says "all ten controls are focusable and in the Tab chain". The section's radius row is a slider+spinbox PAIR, so the actual focusable widget set is 11 (10 contracted rows, one row = two widgets).
- **Fix:** The test asserts all 11 widgets (including both radius members) are reachable — a strict superset of the contract; the UI-SPEC "ten controls" wording counts the pair as one row.
- **Files modified:** tests/test_gui_detection_settings.py
- **Verification:** `test_all_section_controls_reachable_in_tab_chain` passes
- **Committed in:** c0f34e1 (Task 1 test commit)

**2. [Test note] QMenu wrapper-lifetime handling in the Tools-menu lookup**
- **Found during:** Task 2 (toggle relocation test)
- **Issue:** Resolving the Tools `QMenu` through a temporary `QMenuBar.actions()` wrapper tripped `RuntimeError: Internal C++ object (QMenu) already deleted` — the known PySide6 wrapper-lifetime trap (STATE.md 06-05 precedent).
- **Fix:** The test helper holds the `QMenuBar.actions()` wrappers (and the menu's action wrappers) while collecting the texts, returning the text list instead of a menu reference.
- **Files modified:** tests/test_gui_detection_settings.py
- **Verification:** `test_detect_boxes_removed_from_tools_menu_action_kept` passes
- **Committed in:** 84c4ee7 (Task 2 commit)

---

**Total deviations:** 0 auto-fixed production deviations (2 test-side notes)
**Impact on plan:** No production scope creep; both notes are test-side robustness/precision adjustments.

## TDD Gate Compliance

Task 1 is `tdd="true"`; git log shows the RED→GREEN sequence:
- Task 1: `test(08-05)` c0f34e1 → `feat(08-05)` df44fa1

The RED gate failed for the right reasons — every failing test referenced not-yet-existing ToolsPanel attributes (`detect_checkbox`, `dilation_slider`, the new signals) or asserted the stale pre-Phase-8 tooltip strings. No refactor commit needed (the implementation matched the test contract on the first GREEN pass).

## Issues Encountered

- The single Task-1-file iteration in which `test_detect_boxes_removed_from_tools_menu_action_kept` failed on the PySide6 QMenu wrapper lifetime: resolved with the wrapper-holding helper (note 2 above). No production issue.
- Full suite (pinned interpreter): **806 passed / 0 failed** (prior 08-04 baseline + 12 new). The pre-existing `test_run_ocr_selected_dispatches_worker_not_inline` flake (deferred-items.md) did not reproduce in this run.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Every symbol plan 08-07 consumes is in place: `dilation_changed`/`std_dev_threshold_changed`/`masker_params_changed` signals, `_save_masker_profile`, and the two LIVE handlers with documented 08-07 extension points — the seam plan wires live re-dilate/gate-re-derive onto the already-persisting handlers
- `masker_values()`/`set_masker_values()` give 08-07 a stable read/populate contract for the masker config object
- No blockers.

## Self-Check: PASSED

All 3 created/modified files exist on disk; all 3 task commits found in git log; `git log --grep="08-05"` returns the expected commits. Full suite re-verified green (806 passed / 0 failed) before SUMMARY.

---
*Phase: 08-masker-selective-inpaint*
*Completed: 2026-08-17*
