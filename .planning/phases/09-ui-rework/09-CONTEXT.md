# Phase 9: UI Rework - Context

**Gathered:** 2026-08-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Reorganize the editor chrome into its final v1.2 layout without removing any functionality:

1. **One modular side panel** replacing the tabified Tools+Inspector docks — a stack of discrete, independently collapsible sections (Detection settings, Brush, Typesetting, Edit).
2. **A vertical tools strip beside the canvas** holding the 6 paint/pan/crop tools plus Detect Text and Inpaint, relocated off the top toolbar.
3. **A new "Edit" section** consolidating the image ops (curves, crop, rotate, resize) that currently live scattered across menus/dialogs.
4. **"Inspector" → "Typesetting"** rename (UI-04) and the **inspector toggle at the top of the side panel** (UI-02).

This activates the `06-UAT.md` sidebar-revamp deferral ("Consider adding Curves (and possibly other tools) to the sidebar — user plans a later phase to revamp the sidebar a bit").

**Explicitly NOT in scope:** new image-edit operations (all ops exist from Phases 5/6 — entry points only), MT integration (TRAN-01, v2), any change to inpaint/detection behavior (Phase 8/08.1 just landed it).

</domain>

<decisions>
## Implementation Decisions

### Side-panel composition (discussed — user-locked)
- **D-01:** **One unified right-side panel — a single dock whose body is a stack of independently collapsible sections.** It replaces today's tabified `dock_tools` + `dock_inspector` pair (`main_window.py:299-334`). The panel hosts ALL sections: Detection settings, Brush, Typesetting, Edit. — **Reversibility:** costly — restructures `_build_docks`, the View-menu dock-toggle actions, and every test/automation keyed to the two-dock tabified chrome.
- **D-02:** **Four sections in workflow order: Detection settings → Brush → Typesetting → Edit.** Collapse state persists across sessions (QSettings precedent: `detectBoxesMode`, plan 08-05 A7).
- **D-03:** **Brush size stays in the panel** as its own collapsible section; the Detection-settings controls become a collapsible section (their existing `ToolsPanel._build_detection_settings_section` body carries over). Only the 6 tool buttons leave the panel for the canvas strip.

### Vertical tools strip (discussed — user-locked, includes UI-03 deviation)
- **D-04:** **Strip contents = the 6 exclusive tools + Detect Text + Inpaint (8 buttons)**, with a visual divider separating Detect/Inpaint from the tool group.
- **D-05:** **Placement deviation from UI-03's literal wording: the strip sits LEFT of the canvas, between the Pages file list and the canvas.** Final layout left→right: **Pages | tools strip | canvas | side panel**. The user was shown the conflict with UI-03's "small vertical toolbar on the right side of the canvas" and explicitly chose left-of-canvas. Planning must update UI-03's wording (ROADMAP + REQUIREMENTS) to match — the requirement's intent (vertical strip relocated off the top toolbar) is honored; only the side changes.
- **D-06:** **Icon-only strip buttons with tooltips — NEW bundled icon assets (~8 icons) are created this phase.** The repo currently has NO icon assets (tool buttons render text-only via `ToolButtonTextOnly`), so this phase introduces an assets directory (e.g. `gui/assets/icons/`). Icons cover the strip only.
- **D-07:** **Top toolbar shrinks** to: Open Folder, zoom controls (Fit/100%/Out/In), Undo/Redo, Mask Overlay toggle, Preview (hold) — keeping its current text-label style.

### Edit section (discussed — user-locked)
- **D-08:** **Edit section = buttons that open the EXISTING dialogs** — Curves…, Crop… (numeric dialog), Resize… — plus instant actions Rotate 90° CW / 90° CCW / 180°. Same behavior, new location. **No separate Levels entry** — Levels was superseded by Curves (Phase 6 D-01); UI-05's "levels" mention reads as "the curves dialog that replaced it". **The Crop TOOL (G, armed on-canvas rect) stays a strip button** — the Edit section hosts the numeric Crop… dialog entry, the strip hosts the interactive tool.
- **D-09:** **Menus slim down once the Edit section exists** — Rotate ▸ / Curves… / Resize… leave the Tools menu's Image section, Crop… leaves the Edit menu. The panel section is the single mouse-driven home; all keyboard shortcuts survive unchanged (keyboard-reachability contract, 05-UI-SPEC).

### Claude's Discretion
- **UI-02 toggle semantics + UI-04 rename reach** — user chose not to discuss these. Sensible defaults: the toggle control at the top of the side panel collapses/expands the panel (or the Typesetting section — pick what best matches the "inspector toggle" intent after the rename); the "Inspector" name becomes "Typesetting" everywhere user-visible (dock/panel title, View-menu action label, status messages, tooltips).
- **Collapse mechanism** — custom header+body collapsible widgets vs `QToolBox` vs other; default open/collapsed states per section.
- **Icon art style, format (SVG/PNG), and drawing approach** — must read correctly at strip size on the dark QSS background; active-tool highlight stays accent `#00d4ff`.
- **Active-tool highlight wiring through the strip** — MUST preserve the 06 D-10 / WR-02 contract: checkable window actions, explicit `set_active_tool` sync loop covering keyboard/menu/programmatic paths; the strip group holds exactly its own actions.
- **Section enablement** — mirror `_refresh_action_states` gating (page-open / op-running) per control.
- **What happens to `ToolsPanel`/`InspectorPanel` classes** — refactored into section bodies vs new section widgets wrapping their content; either satisfies the contract.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase Scope
- `.planning/ROADMAP.md` §Phase 9 — **THE scope anchor.** Goal, scope list (UI-01..UI-05), success criteria 1–5, Depends on Phase 8. NOTE: UI-03's "right side of the canvas" wording is superseded by decision D-05 (left of canvas) — planning updates it.
- `.planning/REQUIREMENTS.md` — UI-01..UI-05 definitions (:54-58) + tracking table (:130-134).

### Deferral source
- `.planning/phases/06-refinement-polish-deferred-fixes-full-curve-editor/06-UAT.md` — the sidebar-revamp deferral (test 3 idea, deferred 2026-08-09): "Consider adding Curves (and possibly other tools) to the sidebar".

### Prior Phase Context (contracts this phase inherits)
- `.planning/phases/06-refinement-polish-deferred-fixes-full-curve-editor/06-CONTEXT.md` — **D-10** (toolbar active-tool highlight: checkable window actions + exclusive group) and the WR-02 fix shape (panel group holds ONLY its own actions; `set_active_tool` drives window actions explicitly — the strip rework must not regress this), **D-12** (dialog typography 14px Body).
- `.planning/phases/07-typesetting-tran-02-render-translated-text-into-the-page/07-CONTEXT.md` — **D-05** (styling controls live in the Inspector panel — that content becomes the Typesetting section verbatim).
- `.planning/phases/08-masker-selective-inpaint/08-CONTEXT.md` + `08-UI-SPEC.md` §surface 36 — detection-settings section contract (scroll-wrap rule A11, tooltip copy A12, LIVE signals).
- `.planning/phases/08.1-inpaint-correction-oom-safe-patching-invert-the-std-dev-gate/08.1-CONTEXT.md` — max-inpaint-size control + Inspector override combo that move into the reworked sections.
- `.planning/phases/05-project-persistence-image-ops-export/05-UI-SPEC.md` — typography table (Body 14px), keyboard-reachability contract, dark-QSS/token conventions.
- `.planning/phases/01-cleaning-workspace/01-UI-SPEC.md` — base design contract (color tokens, spacing, accent `#00d4ff` reserved use #1 active-tool highlight).

### Existing Code (the build surfaces)
- `manga_ai_studio/gui/main_window.py` — `_build_docks` (:299-334, the two-dock + tabify structure D-01 replaces), `_build_toolbar` (:981-1034, the toolbar D-07 shrinks and the strip empties), `_build_view_menu` (:644-668, Toggle Sidebar/Tools/Inspector actions), `_build_edit_menu` (Crop… :555-568), `_build_tools_menu` Image section (:904-946, Rotate/Curves/Resize — D-09 removes these), `_make_tool_toolbar_button` (:4250), `_refresh_action_states`, QSettings view-state precedent.
- `manga_ai_studio/gui/tools_panel.py` — the whole file: tool row + `QActionGroup`/toggled wiring (the strip's action machinery source), brush-size slider/spinbox mirror (Brush section source), `_build_detection_settings_section` (:386-559, Detection settings section source), `_TOOLS_QSS` tokens.
- `manga_ai_studio/gui/inspector_panel.py` — the InspectorPanel (text fields + style section + inpaint combo) that becomes the Typesetting section body.
- `manga_ai_studio/gui/theme.py` — existing theming helpers.
- `tests/test_gui_*.py` — dock/toolbar/menu/panel assertions that the rework updates (menu-membership assertion precedent: action-list membership, not parent()).

### External References (researcher may fetch)
- Qt collapsible-section patterns (custom QWidget headers vs QToolBox trade-offs) and QIcon/SVG bundling practice for PySide6 resource files — only as needed for Claude's Discretion items.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`ToolsPanel._build_detection_settings_section`** (`tools_panel.py:386-559`) — the complete Detection-settings body (divider + header + QFormLayout + tooltips + LIVE signal wiring) that becomes the Detection settings section nearly verbatim.
- **`InspectorPanel`** (`inspector_panel.py`) — the entire Typesetting section body (fields + Style + Inpaint override), including the Mixed-state machinery.
- **Tool-action machinery** (`tools_panel.py:174-254`) — `QActionGroup` + per-action `toggled` connection + `set_active_tool` blockSignals discipline; the strip reuses this pattern.
- **QSettings persistence precedents** — `detectBoxesMode` (08-05 A7) for persisting collapse states.
- **Dark QSS token blocks** (`_TOOLS_QSS`) — styling vocabulary for new section chrome and the strip.

### Established Patterns
- **06 D-10 / WR-02 active-tool sync** — checkable window actions + explicit `set_active_tool` sync loop; exclusive groups hold only their own actions. Any new strip/group wiring must preserve one `tool_changed` emission per selection across click/shortcut/menu/programmatic paths.
- **blockSignals mirror pairs** — slider↔spinbox sync pattern used across the panel; keep it when controls move between sections.
- **Keyboard-reachability contract** — every removed menu entry keeps its shortcut working; shortcut audit before rebinding.
- **Menu-membership testing precedent** — assert action-list membership, not widget parents (Recent/Batch submenu lesson, Phase 4).
- **RED-GREEN regression discipline** — tests exercise real bug sites; layout changes update the affected GUI tests in the same commit.

### Integration Points
- `main_window._build_docks` — replaced by the single-panel build (D-01).
- `main_window._build_toolbar` — loses Detect/Inpaint/tool buttons (D-04/D-07).
- `main_window._build_view_menu` — Toggle Tools/Inspector actions re-target the unified panel (+ rename, D-04 discretion item).
- Tools/Edit menus — Image-section entries removed (D-09); shortcuts unchanged.
- NEW `manga_ai_studio/gui/assets/icons/` (or equivalent) — bundled strip icons loaded via Qt resources or file paths (D-06).

</code_context>

<specifics>
## Specific Ideas

- **Workflow order is the organizing principle** — the user ordered the sections to match how they work: configure detection → paint/brush → typeset → edit the image.
- **Icons were a deliberate choice** — offered the text-only option (zero new assets), the user chose to invest in bundled icons for the strip; the top toolbar staying text-only was equally deliberate (scope containment).
- **Left-of-canvas placement was chosen knowingly** — the user picked it AFTER seeing UI-03's "right side" wording flagged as conflicting. Do not "fix" the placement back to the right during planning; instead correct the requirement wording.
- **Same dialogs, new home** — the Edit section is pure relocation of proven dialog entry points; no inline-control redesign of Curves/Crop/Resize.

</specifics>

<deferred>
## Deferred Ideas

- **Icons on the shrunken top toolbar** — offered during discussion ("Icons everywhere"), declined for this phase; a future polish pass could extend the icon set to open/zoom/undo/redo/overlay buttons.

None else — discussion stayed within phase scope.

</deferred>

---

*Phase: 9-UI Rework*
*Context gathered: 2026-08-21*
