---
phase: 09-ui-rework
plan: 02
subsystem: gui
tags: [pyside6, side-panel, collapsible-sections, qsettings, ui-01, ui-02, ui-04, wr-02]
requires:
  - ToolsStrip (09-01) — sole tool-button home; set_active_tool drops the panel sync call
  - ToolsPanel detection-settings + brush bodies (relocated verbatim into section bodies)
  - InspectorPanel instance (becomes the Typesetting body by identity)
provides:
  - manga_ai_studio/gui/side_panel.py — CollapsibleSection (checkable ▸/▾ header, plain setVisible toggle, settings_key/provider, restore_expanded) + SidePanel (chevron row, one vertical-only scroll wrap, add_section API)
  - MainWindow.dock_panel ("Panel") hosting self.side_panel with sections in D-02 order
  - action_toggle_panel View action driving the session-transient panel-body toggle
  - QSettings persistence: sidePanel/detectionExpanded, brushExpanded, typesettingExpanded (editExpanded lands lazily in 09-03)
  - manga_ai_studio/gui/tools_panel.py slimmed to BrushBody + DetectionSettingsBody
affects:
  - 09-03 (Edit section) — appends its CollapsibleSection via side_panel.add_section; editExpanded key mechanism is generic and ready
tech-stack:
  added: [] # zero new packages
  patterns:
    - custom header+body collapsible sections (QToolBox forbidden — independence requirement)
    - plain setVisible collapse, never animation (fights QScrollArea sizing)
    - blockSignals seed for restore-without-write (main_window precedent)
    - tolerant QSettings bool parse extended with an explicit falsy set so legit false round-trips while malformed values fall back to expanded
key-files:
  created:
    - manga_ai_studio/gui/side_panel.py
    - tests/test_gui_side_panel.py
  modified:
    - manga_ai_studio/gui/main_window.py
    - manga_ai_studio/gui/tools_panel.py
    - manga_ai_studio/gui/tools_strip.py
    - manga_ai_studio/gui/inspector_panel.py
    - tests/test_gui_canvas.py
    - tests/test_gui_detection_settings.py
    - tests/test_gui_crop_tool.py
    - tests/test_gui_detection_boxes.py
    - tests/test_gui/test_tools_panel_masker.py
    - tests/test_gui/test_detection_settings_tooltip.py
decisions:
  - DetectionSettingsBody/BrushBody drop the old internal divider+static-header chrome — the wrapping CollapsibleSection now owns section titles/dividers (avoids double headers); the §36 control form moved verbatim
  - window attribute naming: self.detection_body / self.brush_body replace self.tools_panel; all test access paths updated in the same commits (plan explicitly permitted path updates over aliasing)
  - the tolerant parse keeps an explicit falsy set (false/0/no/off) alongside the truthy set — required so a persisted False round-trips while "banana" (T-09b-01) still falls back to expanded per the acceptance criterion
  - D-15 extended paint-tool tooltips (Alt clause) ported onto the strip actions — supersedes the 09-01 short-tooltip note; the strip is now the tools' single tooltip surface
metrics:
  duration: 34 min
  completed: 2026-08-22
status: complete
actuals:
  tokens: 23200 # chars/4 over the realized diff (92.8k chars, 12 files, +896/-511)
  tasks: 3
  commits: 3
---

# Phase 9 Plan 02: Unified Side Panel + Collapsible Sections + Rename Summary

One right-side "Panel" dock whose body stacks independently collapsible sections in workflow order (Detection settings → Brush → Typesetting), a chevron "Toggle panel" + single View-menu action that hide only the panel body, the Inspector→Typesetting user-visible rename, and per-section collapse persistence via QSettings — with every relocated signal name and emission semantics byte-identical.

## What Was Built

- **`side_panel.py`** (new): `CollapsibleSection` — checkable QToolButton header (▸/▾ glyph + title, muted 12px/600 token style, min-height 28px), `header.toggled` → plain `body.setVisible`, optional `settings_key` + `settings_provider`, `set_expanded()` (normal signals) and `restore_expanded()` (blockSignals seed — zero write-back); 1px `#3a3a42` bottom divider. `SidePanel` — chevron QToolButton row ("Toggle panel" tooltip/accessibility name), ONE vertical-only widgetResizable QScrollArea wrap (A11 rule verbatim from tools_panel.py:149-171), order-preserving `add_section` (count NOT hard-coded for 09-03).
- **MainWindow `_build_docks` rework**: `dock_tools`+`dock_inspector` tabified pair deleted; one `QDockWidget("Panel")` hosts the SidePanel with sections in D-02 order — Detection settings (`DetectionSettingsBody`), Brush (`BrushBody`), Typesetting (the existing `InspectorPanel` INSTANCE — identity preserved). Restore loop seeds each section post-build.
- **View menu**: `action_toggle_panel` ("Toggle Panel") replaces Toggle Tools/Toggle Inspector; drives the same body toggle as the chevron; dock stays docked; Toggle Sidebar untouched.
- **`tools_panel.py` slimmed**: two embeddable bodies with ALL signal names preserved verbatim (`brush_size_changed`, `detect_boxes_changed`, `dilation_changed`, `std_dev_threshold_changed`, `masker_params_changed`) including the blockSignals mirror pairs and the `set_masker_values` bulk guard; tool-row/group/set_active_tool machinery removed (strip owns it since 09-01).
- **Persistence (D-02)**: keys `sidePanel/detectionExpanded|brushExpanded|typesettingExpanded` written on every user toggle through the single-sourced `_settings()` accessor; tolerant parse (truthy true/1/yes/on, falsy false/0/no/off, anything else → expanded); chevron writes nothing (session-transient, asserted).
- **Rename sweep (UI-04)**: dock "Panel", section "Typesetting", View "Toggle Panel"; a live user-visible tooltip referencing the retired "Tools dock" chrome now reads "Panel → Detection settings"; class/signal names untouched.

## Tasks Completed

| Task | Name | Commit |
| ---- | ---- | ------ |
| 1 | Unified Panel dock end-to-end (tracer): shell + Typesetting + View retarget | 3c7b253 |
| 2 | Relocate Detection-settings + Brush bodies; slim tools_panel.py | d0bed4a |
| 3 | Collapse persistence + rename sweep verification | 6d59b02 |

## Verification

- Task 1 verify re-run green before expansion (tracer gate): 42 passed (`test_gui_side_panel.py` + `test_gui_canvas.py`).
- Task quick commands green after each task; full suite at plan close: **1007 passed, 0 failed** (pinned 3.14.2 interpreter) — strict superset of the 998 at 09-01 close (+10 new side-panel/persistence tests, −1 duplicated tool-row exclusivity test).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] D-15 extended tooltips ported to the strip**
- **Found during:** Task 2
- **Issue:** The Phase 8 D-15 Alt-clause tooltip copy lived on the panel's tool actions; deleting the tool row would have silently dropped user-visible hints. The strip carried only short copy (the 09-01 summary noted that choice).
- **Fix:** Extended copy ported onto `tools_strip.py` actions (supersedes the 09-01 note); the D-15 test now asserts against `window.tools_strip`.
- **Files modified:** manga_ai_studio/gui/tools_strip.py
- **Commit:** d0bed4a

**2. [Rule 3 - Blocking] Test files outside `files_modified` updated**
- **Found during:** Task 2
- **Issue:** `tests/test_gui_crop_tool.py` (panel active-tool assertions), `tests/test_gui_detection_boxes.py` (signal emissions off `window.tools_panel.*`), and `tests/test_gui/test_*` files (constructing the dissolved class) would have broken.
- **Fix:** Access paths re-targeted (`window.detection_body`, strip assertions); crop-tool exclusivity test rebuilt on a standalone ToolsStrip; canvas tool-group exclusivity test dropped as an exact duplicate of test_gui_tools_strip.py coverage.
- **Files modified:** tests/test_gui_crop_tool.py, tests/test_gui_detection_boxes.py, tests/test_gui/test_tools_panel_masker.py, tests/test_gui/test_detection_settings_tooltip.py
- **Commit:** d0bed4a

### Notes
- Tolerant parse needed an explicit falsy set beyond the plan's verbatim `_read_detect_boxes_mode` shape: without it, a persisted `False` reads back expanded and round-trip fails; with it, malformed values still fall back to expanded exactly as the acceptance criterion and T-09b-01 require.
- Section bodies no longer render their own static divider/header labels — the CollapsibleSection owns that chrome (double-header avoidance during relocation).

## Known Stubs

None — every section body is fully wired; no placeholder data paths. The Edit section is intentionally absent (plan 09-03 delivers it; the SidePanel API accepts it without changes).

## Threat Flags

None — the only new trust boundary (sidePanel/*Expanded strings parsed at startup) is inside the plan's threat model; the tolerant parse mitigation (T-09b-01) is implemented and test-locked.

## Self-Check: PASSED

- side_panel.py + tests/test_gui_side_panel.py exist on disk (FOUND).
- Commits 3c7b253, d0bed4a, 6d59b02 present in git log (FOUND).
- Full suite green post-plan (1007 passed).
