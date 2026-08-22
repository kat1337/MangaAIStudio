---
phase: 09-ui-rework
plan: 01
subsystem: gui
tags: [pyside6, tools-strip, icons, toolbar, wr-02]
requires:
  - main_window.py action_detect_text/action_inpaint/action_tool_* standalone checkable actions
  - ToolsPanel tool-row machinery (relocated verbatim into ToolsStrip)
provides:
  - manga_ai_studio/gui/tools_strip.py — ToolsStrip (tool_changed signal, tool_group, set_active_tool/active_tool, 8 icon-only buttons + divider)
  - 8 bundled SVG icons under manga_ai_studio/gui/assets/icons/ + module-relative _icon() loader
  - central-widget container ([strip][canvas]) replacing setCentralWidget(canvas)
  - D-07 shrunken top toolbar
affects:
  - 09-02 (unified side panel) — consumes the strip as the permanent tool-button home; will remove the panel's tool row + the temporary tools_panel.set_active_tool sync call
tech-stack:
  added: [] # zero new packages
  patterns:
    - central-widget container embedding (never addToolBar LeftToolBarArea — probe-verified)
    - default-action mirroring for gating inheritance
    - action-carried icons (QToolButton re-syncs its icon FROM its default action on state changes)
key-files:
  created:
    - manga_ai_studio/gui/tools_strip.py
    - manga_ai_studio/gui/assets/icons/{move,brush,rectangle,lasso,eraser,crop,detect-text,inpaint}.svg
    - tests/test_gui_tools_strip.py
  modified:
    - manga_ai_studio/gui/main_window.py
    - pyproject.toml
    - tests/test_gui_crop_tool.py
decisions:
  - icons live ON the strip-owned QActions (a default-action button re-syncs its icon from the action on every action change — e.g. disable — wiping button-side-only icons to null); shared window Detect/Inpaint actions stay icon-free (Tools menu is text-only) and their strip buttons re-assert the bundled icon on the action's `changed` signal
  - set_active_tool keeps BOTH tools_panel.set_active_tool and tools_strip.set_active_tool calls (plan said "replace"; keeping the panel sync avoids regressing the existing crop-tool sync tests until plan 09-02 removes the panel's tool row)
  - _build_central_widget runs after _build_menus because the strip mirrors action_detect_text/action_inpaint (construction-order constraint)
  - strip tool tooltips use the short name+shortcut copy from 09-UI-SPEC §39 (Move/Pan tool (V) …), not the panel's longer brush-family tooltips
metrics:
  duration: 27 min
  completed: 2026-08-21
status: complete
actuals:
  tokens: 58000
  tasks: 3
  commits: 3
---

# Phase 9 Plan 01: Vertical Tools Strip + Icon Assets + Slimmed Toolbar Summary

Vertical icon-only tools strip (6 exclusive tools + divider + Detect/Inpaint) embedded between the Pages dock and the canvas, 8 bundled module-relative SVG icons, and the top toolbar shrunk to its D-07 contents — with the WR-02 single-emission tool-sync contract intact from every entry path.

## What Was Built

- **ToolsStrip** (`manga_ai_studio/gui/tools_strip.py`): vertical QToolBar (fixed width 44, icon size 20, 36×36 buttons). Owns six exclusive checkable QActions in one QActionGroup (exactly the strip's own actions), checked-only `toggled` emission of `tool_changed`, `set_active_tool`/`active_tool` with the proven blockSignals discipline. Detect Text + Inpaint are plain non-checkable default-action buttons bound to the WINDOW actions, so `_refresh_action_states` gating is inherited free.
- **Central container**: `setCentralWidget(self.canvas)` replaced by a zero-margin QHBoxLayout `[ToolsStrip][canvas stretch]` — probe-verified Pages | strip | canvas ordering (never `addToolBar(LeftToolBarArea)`).
- **8 SVG icons**: hand-authored 24×24 monochrome (`#e8e8ea` strokes, width 2, round caps/joins, fill none) under `gui/assets/icons/`, loaded via `_icon()` resolving ONLY from `Path(__file__).parent / "assets" / "icons"` (threat T-09a-01 containment). `pyproject.toml` package-data covers `gui/assets/icons/*.svg`.
- **D-07 toolbar slim-down**: top toolbar is now exactly Open Folder | Fit · 100% · Out · In | Undo · Redo | Mask Overlay | Preview (hold); Detect/Inpaint/tool QActions survive as state holders with all shortcuts untouched; the dead `_make_tool_toolbar_button` helper and the toolbar-button sync loop were removed.
- **Tests**: new `tests/test_gui_tools_strip.py` (8 tests: geometry order, membership/exclusivity, divider, single emission, window-action identity, icon non-null + path containment, SVG art direction, D-07 toolbar membership); `test_gui_crop_tool.py` button lookups retargeted to the strip.

## Tasks Completed

| Task | Name | Commit |
| ---- | ---- | ------ |
| 1 | Vertical tools strip wired end-to-end (tracer) | 085fc08 |
| 2 | Icon assets — 8 SVGs, module-relative loader, package-data | 14a18cb |
| 3 | Shrink the top toolbar to D-07 contents | 2a2e03a |

## Verification

- Task commands: `pytest tests/test_gui_tools_strip.py tests/test_gui_canvas.py -x -q` green after each task (42 → 44 → 60 with crop-tool file).
- Full suite at plan close: **998 passed, 0 failed** (`python -m pytest -q`, pinned 3.14.2 interpreter) — strict superset of the 552 Phase-5 baseline.
- Tracer feedback gate: Task 1 verify re-run end-to-end green before Tasks 2–3.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Icons must live on the strip-owned actions, not only the buttons**
- **Found during:** Task 2
- **Issue:** A QToolButton bound via `setDefaultAction` re-syncs its icon FROM the action whenever the action changes state (disable/enable). Button-side-only icons were wiped to null the moment `_refresh_action_states` disabled the tool actions with no page open (probe: Move kept its icon, Brush..Crop went null).
- **Fix:** The six strip-owned actions carry the icons themselves; the shared window Detect/Inpaint actions (which must stay icon-free for the text-only Tools menu) get buttons that re-assert the bundled icon on the action's `changed` signal.
- **Files modified:** manga_ai_studio/gui/tools_strip.py
- **Commit:** 14a18cb

**2. [Rule 3 - Blocking] test_gui_crop_tool.py retargeted to the strip**
- **Found during:** Task 3
- **Issue:** Three tests located tool buttons via `window.toolbar.findChildren(QToolButton)`; the D-07 slim-down removed them (StopIteration → red suite). The file was outside the plan's `files_modified` list.
- **Fix:** Added a `_strip_tool_buttons` helper and retargeted the lookups to `window.tools_strip`; the WR-02/D-10 assertions now lock the strip click path (the stronger post-rework contract).
- **Files modified:** tests/test_gui_crop_tool.py
- **Commit:** 2a2e03a

**3. [Deviation] set_active_tool keeps the panel sync call**
- **Found during:** Task 1
- **Issue:** The plan prescribed replacing `tools_panel.set_active_tool(tool)` with the strip call; literal replacement would desync the still-existing dock panel and fail existing crop-tool tests.
- **Fix:** Both calls kept (each blocks its actions' signals — zero extra emissions). Plan 09-02 removes the panel call with the tool row.

### Notes
- `tests/test_gui_canvas.py` (listed in `files_modified`) needed NO changes: its tool tests target ToolsPanel directly and `dock_tools` still exists in this plan (it dies in 09-02).
- Task 1 followed RED-first discipline (test file failed on missing module before implementation) but was committed atomically per the tracer task-commit protocol.

## Known Stubs

None — all 8 buttons are live, icon-carrying, and wired; no placeholder data paths.

## Threat Flags

None — the only new surface (SVG file → QIcon loading) is inside the plan's threat model; `_icon()` resolves module-relative only, asserted by test.

## Self-Check: PASSED

- tools_strip.py, 8 SVGs, tests/test_gui_tools_strip.py exist on disk (FOUND).
- Commits 085fc08, 14a18cb, 2a2e03a present in git log (FOUND).
- Full suite green post-plan (998 passed).
