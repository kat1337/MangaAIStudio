# Phase 9: UI Rework - Research

**Researched:** 2026-08-21
**Domain:** PySide6 desktop GUI restructuring — unified collapsible side panel, vertical tools strip, menu/section reorganization
**Confidence:** HIGH

## Summary

Phase 9 is a pure PySide6 layout/wiring refactor of an already-stable GUI: replace the tabified `dock_tools` + `dock_inspector` pair with ONE dock whose body is a stack of four independently-collapsible sections (Detection settings → Brush → Typesetting → Edit), move the 6 tool buttons + Detect Text + Inpaint into a small icon-only vertical strip LEFT of the canvas, rename "Inspector" → "Typesetting", and consolidate the image-op dialog entry points into the new Edit section while slimming the Tools/Edit menus. No new functionality, no new external packages, no data-model changes.

Two Qt facts dominate the design space, both verified by live probes this session on the project interpreter (PySide6 6.10.1, Windows):

1. **A QMainWindow left-area toolbar lands OUTSIDE the Pages dock, not beside the canvas.** `addToolBar(Qt.LeftToolBarArea, …)` places the toolbar at window x=0 with the left dock at x=40 (toolbar column is outermost), and `setCorner()` does not change this ordering. D-05's "Pages | strip | canvas | side panel" order therefore cannot be achieved with a QMainWindow-managed toolbar. The probe-verified fix: embed a vertical `QToolBar` (`setOrientation(Qt.Vertical)`, fixed width) as the first item of a horizontal container that wraps the canvas in the central-widget slot — the probe reproduced exactly Pages | strip | canvas | Panel.
2. **`QToolBox` cannot implement UI-01.** QToolBox shows only its *current* item ("displays a column of tabs one above the other, with the current item displayed below the current tab" [CITED: doc.qt.io/qt-6/qtoolbox.html]) — it is exclusive-show, not independent collapse. The standard pattern is a custom collapsible-section widget: a checkable header row toggling its body's visibility, stacked in the existing scroll-wrapped panel body (the A11 scroll-wrap rule carries over).

Everything else is relocation of proven machinery: the Edit section binds `QToolButton.setDefaultAction` to the **existing** `action_curves` / `action_crop_dialog` / `action_resize` / rotate actions (enablement gating from `_refresh_action_states` follows for free); the strip buttons mirror the existing standalone window tool actions exactly like today's top-toolbar buttons (`_make_tool_toolbar_button` pattern); collapse-state persistence follows the `detectBoxesMode` QSettings view-state precedent; icons are ~8 hand-authored SVGs loaded by file path (PySide6 ships the SVG imageformat + iconengine plugins — probe-verified).

**Primary recommendation:** Build the side panel as one dock containing a scroll area of custom `CollapsibleSection` widgets whose bodies are the relocated `ToolsPanel` detection-settings block, brush rows, `InspectorPanel`, and a new Edit button grid bound via `setDefaultAction`; build the strip as an embedded vertical `QToolBar` inside a new central-widget container wrapping the canvas; keep all existing QAction objects alive so shortcuts, gating, and tests survive the move.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Side-panel composition (D-01..D-03):**
- **D-01:** One unified right-side panel — a single dock whose body is a stack of independently collapsible sections. Replaces today's tabified `dock_tools` + `dock_inspector` pair. Hosts ALL sections: Detection settings, Brush, Typesetting, Edit.
- **D-02:** Four sections in workflow order: Detection settings → Brush → Typesetting → Edit. Collapse state persists across sessions (QSettings precedent: `detectBoxesMode`, plan 08-05 A7).
- **D-03:** Brush size stays in the panel as its own collapsible section; the Detection-settings controls become a collapsible section (the existing `ToolsPanel._build_detection_settings_section` body carries over). Only the 6 tool buttons leave the panel for the canvas strip.

**Vertical tools strip (D-04..D-07):**
- **D-04:** Strip contents = the 6 exclusive tools + Detect Text + Inpaint (8 buttons), with a visual divider separating Detect/Inpaint from the tool group.
- **D-05:** Placement deviation from UI-03's literal wording: the strip sits LEFT of the canvas, between the Pages file list and the canvas. Final layout left→right: **Pages | tools strip | canvas | side panel**. Planning must update UI-03's wording (ROADMAP + REQUIREMENTS) to match — intent honored, only the side changes.
- **D-06:** Icon-only strip buttons with tooltips — NEW bundled icon assets (~8 icons) created this phase. Introduces an assets directory (e.g. `gui/assets/icons/`). Icons cover the strip only.
- **D-07:** Top toolbar shrinks to: Open Folder, zoom controls (Fit/100%/Out/In), Undo/Redo, Mask Overlay toggle, Preview (hold) — keeping its current text-label style.

**Edit section (D-08/D-09):**
- **D-08:** Edit section = buttons that open the EXISTING dialogs — Curves…, Crop… (numeric dialog), Resize… — plus instant actions Rotate 90° CW / 90° CCW / 180°. Same behavior, new location. No separate Levels entry (superseded by Curves, Phase 6 D-01). The Crop TOOL (G, armed on-canvas rect) stays a strip button; the Edit section hosts the numeric Crop… dialog entry.
- **D-09:** Menus slim down once the Edit section exists — Rotate ▸ / Curves… / Resize… leave the Tools menu's Image section, Crop… leaves the Edit menu. All keyboard shortcuts survive unchanged (keyboard-reachability contract, 05-UI-SPEC).

### Claude's Discretion
- UI-02 toggle semantics + UI-04 rename reach (sensible defaults acceptable).
- Collapse mechanism — custom header+body vs QToolBox vs other; default open/collapsed states per section.
- Icon art style, format (SVG/PNG), drawing approach — must read at strip size on dark QSS background; active-tool highlight accent `#00d4ff`.
- Active-tool highlight wiring through the strip — MUST preserve the 06 D-10 / WR-02 contract: checkable window actions, explicit `set_active_tool` sync loop covering keyboard/menu/programmatic paths; the strip group holds exactly its own actions.
- Section enablement — mirror `_refresh_action_states` gating per control.
- What happens to `ToolsPanel`/`InspectorPanel` classes — refactored into section bodies vs wrapped; either satisfies the contract.

### Deferred Ideas (OUT OF SCOPE)
- Icons on the shrunken top toolbar — declined for this phase; future polish pass could extend the icon set.
- New image-edit operations, MT integration (TRAN-01 v2), any change to inpaint/detection behavior.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| UI-01 | Side panel is modular — discrete, independently collapsible sections rather than one monolithic panel | CollapsibleSection widget pattern (custom header + body visibility); QToolBox rejected — single-current-item semantics fail "independently collapsible" [CITED: doc.qt.io/qt-6/qtoolbox.html]; scroll-wrap A11 carries over |
| UI-02 | Inspector toggle button moved to the top of the side panel | Discretion recommendation: panel-header toggle row; old dock toggleViewAction wiring at main_window.py:644-653 re-targeted |
| UI-03 | Tools toolbar relocated to small vertical toolbar beside canvas (D-05: LEFT of canvas) | PROBE-VERIFIED pitfall: `addToolBar(LeftToolBarArea)` puts strip outside the Pages dock; fix = embed vertical QToolBar in central-widget container wrapping canvas (probe reproduced Pages \| strip \| canvas \| Panel) |
| UI-04 | Former "Inspector" section renamed to "Typesetting" | Rename reach enumerated: `QDockWidget("Inspector", …)` title (main_window.py:326), View-menu "Toggle Inspector" (:650), docstrings; no persisted state keyed on the name |
| UI-05 | New "Edit" panel section houses image-edit tools (curves, crop, rotate, resize) | Edit section binds existing `action_curves` / `action_crop_dialog` / `action_resize` / rotate actions via `setDefaultAction` — gating inherited from `_refresh_action_states`; menus slim per D-09 |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Unified side panel + collapse state | GUI layer (`main_window.py`, new `gui/side_panel.py`) | QSettings (view-state persistence) | Pure presentation; collapse state follows the `detectBoxesMode` view-state precedent (NOT profile INI) |
| Vertical tools strip | GUI layer (central-widget container around canvas) | Existing window `action_tool_*` actions | QMainWindow toolbar areas cannot express the D-05 ordering; strip mirrors standalone checkable actions |
| Active-tool highlight sync | GUI layer (`MainWindow.set_active_tool`) | Strip buttons via default-action mirroring | WR-02 contract: explicit sync loop drives checked state across all entry paths |
| Edit-section entry points | GUI layer (new EditSection body) | EXISTING image-op actions/dialogs | Pure relocation of proven entry points; zero new ops logic |
| Icon assets | Bundled files (`gui/assets/icons/*.svg`) | QIcon file-path loading | No build system exists (source-run app); qrc/rcc adds a compile step for no benefit |
| Menu slimming | GUI layer (`_build_tools_menu`, `_build_edit_menu`) | Action objects kept alive as state holders | Precedent: `action_detect_boxes_mode` removed from menu but kept as state holder |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PySide6 | 6.10.1 [VERIFIED: project interpreter probe] | The entire phase — QDockWidget, QToolBar, QToolButton, QScrollArea, QSettings | Already the app's GUI framework; no additions |
| pytest / pytest-qt | installed [VERIFIED: pytest.ini `qt_api = pyside6`] | GUI tests for the reworked chrome | Established RED-GREEN regression discipline (552-pass baseline per AGENTS.md) |

### Supporting (no installs required)
| Facility | Source | Purpose | When Used |
|----------|--------|---------|-----------|
| SVG icon engine plugin | ships inside PySide6 wheel: `plugins/iconengines/qsvgicon.dll` + `imageformats/qsvg.dll` [VERIFIED: filesystem probe of installed wheel] | `QIcon("…svg")` renders without extra deps | Strip icons (D-06) |
| Qt Resource System | Qt 6 docs [CITED: doc.qt.io/qt-6/resources.html] | Alternative icon bundling via `.qrc` + `rcc -g python` | NOT recommended here — adds a generated-module/build step for a source-run app with deferred packaging |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom collapsible sections | QToolBox | QToolBox shows ONE item at a time — fails independent-collapse requirement; rejected |
| Embedded vertical QToolBar in central layout | QMainWindow LeftToolBarArea | Toolbar area renders OUTSIDE the left dock column (probe-verified); wrong order for D-05 |
| File-path QIcon loading | qrc/rcc resources | qrc embeds into binary and needs rcc each build; packaging is explicitly deferred, so file paths are simpler and test-friendly |
| Reusing existing QActions in Edit section | New buttons calling `.trigger()` lambdas | setDefaultAction inherits enabled-state gating + tooltips free; lambda buttons need manual `_refresh_action_states` coupling |

**Installation:** None. Zero external packages added or upgraded this phase.

## Package Legitimacy Audit

> No external packages are installed by this phase (icons are hand-authored repo assets, not packages). Gate not run — nothing to audit.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| *(none)* | — | — | — | — | — | No installs this phase |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
 MainWindow (QMainWindow)
 │
 ├─ dock_pages "Pages" ──── FileTable                    (left dock, unchanged)
 │
 ├─ CENTRAL: container QWidget ── QHBoxLayout
 │    ├── tools_strip: QToolBar (vertical, icon-only)     ← NEW (D-04/D-05/D-06)
 │    │     [6 tool buttons] ─ divider ─ [Detect Text][Inpaint]
 │    │      mirrors standalone action_tool_* / action_detect_text / action_inpaint
 │    └── canvas: EditorCanvas                             (existing central widget)
 │
 ├─ toolbar "Main" (top, text-only)                        ← SHRUNK (D-07)
 │     Open Folder | Fit 100% Out In | Undo Redo | Mask Overlay | Preview(hold)
 │
 └─ dock_panel (right, single) ── SidePanel                ← NEW unified panel (D-01)
       header row: [panel toggle ▸]                         ← UI-02
       QScrollArea (vertical-only, A11 rule)
         ├─ CollapsibleSection "Detection settings"        ← ToolsPanel §36 body moves in
         ├─ CollapsibleSection "Brush"                     ← brush label/slider/spinbox move in
         ├─ CollapsibleSection "Typesetting"               ← InspectorPanel body moves in (UI-04)
         └─ CollapsibleSection "Edit"                      ← NEW button grid → existing dialogs/actions

 Data flow (primary use case — user paints then edits):
   strip click → window action triggered → set_active_tool(ToolMode) → canvas.set_tool
   + explicit checked-sync loop (window actions + strip buttons follow)
   Edit-section click → existing QAction.triggered → _on_curves/_on_crop_dialog/_on_resize/_rotate_page
   section collapse → QSettings view-state key (persist across sessions)
```

### Recommended Project Structure
```
manga_ai_studio/gui/
├── main_window.py          # _build_docks/_build_toolbar/_build_*_menu rework; setCentralWidget swap
├── side_panel.py           # NEW: SidePanel + CollapsibleSection (+ EditSection body)  [name at implementer's discretion]
├── tools_strip.py          # NEW (or a builder fn): vertical strip widget mirroring window actions
├── tools_panel.py          # SLIMMED: loses tool row; keeps brush + detection-settings bodies (or they move into side_panel.py)
├── inspector_panel.py      # becomes the Typesetting section body (class may keep its name internally)
├── assets/icons/*.svg      # NEW: ~8 hand-authored SVGs (D-06)
└── theme.py                # existing helpers; extend QSS tokens for section headers if needed
```

### Pattern 1: Custom collapsible section (the UI-01 mechanism)
**What:** A QWidget with a checkable header row (arrow + title, styled like `_detection_section_header`) whose `toggled` shows/hides the body. Stack them vertically inside the existing vertical-only QScrollArea pattern.
**When to use:** Always for this phase — QToolBox cannot show multiple sections open simultaneously.
```python
# Source: standard Qt widgets composition; verified against project conventions (tools_panel.py:400-409)
class CollapsibleSection(QWidget):
    def __init__(self, title: str, body: QWidget, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        self.header = QToolButton(checkable=True, checked=True)
        self.header.setText(title)                       # arrow via QSS/property or ▸/▾ prefix
        self.header.setObjectName("_section_header")     # reuse 12px Semibold muted token style
        self.body = body
        lay.addWidget(self.header); lay.addWidget(self.body)
        self.header.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        self.body.setVisible(checked)   # NO animation — setVisible + layout adjust is the stable form
```
Persistence per D-02: save each section's checked state to QSettings on toggle, restore after build — copy the tolerant bool-parse from `_read_detect_boxes_mode` (`raw = self._settings().value("detectBoxesMode", True)` then accept `"true"/"1"/"yes"/"on"`, main_window.py:3003-3006). QSettings returns strings on some backends even when a bool was written.

### Pattern 2: Vertical strip between Pages and canvas (D-05) — probe-verified
**What:** The canvas stops being the direct central widget (`self.setCentralWidget(self.canvas)`, main_window.py:135). Wrap it in a container whose horizontal layout is `[strip][canvas]`.
**Why:** A QMainWindow left-area toolbar is laid out OUTSIDE the left dock column and `setCorner()` does not change that.
```
PROBE RESULTS (PySide6 6.10.1, offscreen, this session):
  addToolBar(LeftToolBarArea):            tb.x=0  dock.x=40  central.x=166  → toolbar LEFT OF PAGES DOCK (wrong)
  setCorner(TopLeft/BottomLeft→DockArea): identical ordering                     (no fix)
  vertical QToolBar inside central HBox:  dock_l.x=0..120, strip x=126..166,
                                          canvas x=166+, dock_r x=600  → ORDER OK: Pages | strip | canvas | Panel
```
Strip buttons mirror the standalone window actions exactly as today's top-toolbar buttons do (`QToolButton.setDefaultAction(action)` + `setCheckable(True)`, main_window.py:4250-4266), so checked-state sync stays automatic once `set_active_tool`'s explicit loop drives the actions (main_window.py:4268-4299). Detect Text + Inpaint are plain (non-checkable) default-action buttons; insert a `QToolBar.addSeparator()`-equivalent divider between the groups (D-04).

### Pattern 3: Edit section reuses live QActions (D-08) — zero new logic
**What:** Each Edit-section button calls `btn.setDefaultAction(self.action_curves)` etc.
**Why:** The enabled state of those actions is already recomputed by `_refresh_action_states` on every page/op event; a default-action button tracks enabled/tooltip/status-tip automatically. New lambda-buttons would need manual gating mirrors.
Buttons: Curves…, Crop… (numeric dialog — NOT the G tool), Resize…, plus three instant Rotate buttons. All six QActions stay alive; only their menu membership changes (D-09).

### Pattern 4: Rename reach (UI-04) and toggle semantics (UI-02)
Verified user-visible occurrences of the old name:
- `self.dock_inspector = QDockWidget("Inspector", self)` — main_window.py:326 [VERIFIED]
- `self.action_toggle_inspector = QAction("Toggle Inspector", self)` — main_window.py:650 [VERIFIED]
- inspector_panel.py docstring line 4 (doc-only) [VERIFIED]

Recommendation (discretion): the unified dock title becomes "Panel"; the Typesetting *section* carries the UI-04 name; View menu gains one "Toggle Panel" action replacing Toggle Tools/Toggle Inspector; the UI-02 control is a chevron button in the panel's header row that collapses/expands the whole panel body (dock stays docked — avoids re-fighting QMainWindow dock visibility state).

### Anti-Patterns to Avoid
- **Adding the strip via `addToolBar(Qt.LeftToolBarArea)`**: renders outside the Pages dock (probe-verified); embed in central layout instead.
- **Using QToolBox for the side panel**: exclusive-show semantics violate UI-01's independence requirement.
- **Putting the window `action_tool_*` actions into the strip's exclusive group**: WR-02 regression — a mirrored multi-widget group fights itself; the group holds exactly its own actions and `set_active_tool` drives the rest explicitly (06-CONTEXT D-10).
- **Animated collapse (QPropertyAnimation on maximumHeight)**: interacts badly with QScrollArea sizing; plain `setVisible` is the established, test-stable form.
- **Deleting removed menu QActions**: shortcuts/state/tests die with them; keep actions alive as state holders (the `action_detect_boxes_mode` precedent, main_window.py:807-818).
- **Re-checking tool state in both strip AND panel**: the tool row leaves the panel (D-03); keep ONE emission path (`toggled` on the strip's own actions) so `tool_changed` fires exactly once per selection.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Icon rendering/scaling | Runtime QPainter-drawn icons or custom raster cache | Hand-authored SVG files + `QIcon(path)` | Qt scales SVG crisply at any DPI; PySide6 ships the SVG plugins |
| Enablement gating for Edit buttons | Per-button enable logic mirroring page/op state | `setDefaultAction(existing_action)` | `_refresh_action_states` already owns that truth |
| Tool-highlight sync | New signal mesh between strip and panel | Existing `set_active_tool` explicit sync loop | Proven across keyboard/menu/click paths since Phase 1 (01-04 toggled-not-triggered lesson) |
| Slider↔spinbox mirrors | Rewritten sync code during relocation | Move the blockSignals mirror pairs verbatim | Established pattern (tools_panel.py:275-288, :563-573) |
| Collapse persistence | A new settings framework | `_settings()` QSettings accessor + tolerant parse | Precedent at main_window.py:2004-2007, :2997-3006 |

**Key insight:** This phase wins by moving proven widgets, not rewriting behavior. Every signal surface (`tool_changed`, `brush_size_changed`, `detect_boxes_changed`, `dilation_changed`, `std_dev_threshold_changed`, `masker_params_changed`, Inspector style signals) must survive relocation unchanged because tests and MainWindow wiring emit/consume them directly (tests/test_gui_detection_boxes.py emits `tools_panel.dilation_changed` etc.).

## Runtime State Inventory

> Rename/refactor phase — all 5 categories answered explicitly.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — the app never calls QMainWindow `saveState`/`restoreState` (grep-verified across `manga_ai_studio/`), so dock titles/objectNames are not persisted. QSettings keys in use: `recentProjects`, `recentFiles` (implied by Recent menus), `detectBoxesMode`, `defaultFontFamily` — none keyed to "Tools"/"Inspector" names | None |
| Live service config | None — no external services own UI strings | None |
| OS-registered state | None — source-run app via start.bat; no task/pm2/launchd registrations | None |
| Secrets/env vars | None — no env-var or secret keys reference panel/dock names | None |
| Build artifacts | None yet; if icons land under `manga_ai_studio/gui/assets/icons/`, add a `[tool.setuptools.package-data]` entry so a future packaging phase doesn't silently drop them | Add package-data line (cheap now, prevents a later trap) |

**Canonical question answered:** after every file is updated, no runtime system retains the old "Inspector"/two-dock chrome — window state is rebuilt from code each launch.

## Common Pitfalls

### Pitfall 1: Left-area toolbar lands outside the Pages dock
**What goes wrong:** Implementing D-05 with `self.addToolBar(Qt.LeftToolBarArea, strip)` puts the strip at the far window edge, LEFT of the Pages list.
**Why it happens:** QMainWindow lays toolbar columns outside dock columns on each side; corner configuration cannot swap them.
**How to avoid:** Wrap canvas in a container widget: `container → QHBoxLayout → [strip_widget, canvas]`; `setCentralWidget(container)` (canvas currently IS the central widget, main_window.py:135).
**Warning signs:** Screenshot shows order strip | Pages | canvas; geometry probe of `mapTo(window)` x-coordinates.

### Pitfall 2: QToolBox chosen for collapsible sections
**What goes wrong:** Only one section visible at a time; users can't see Brush while adjusting Typesetting.
**Why:** QToolBox is tabbed-single-current by design [CITED: doc.qt.io/qt-6/qtoolbox.html].
**How to avoid:** Custom header+body sections stacked in a scroll area.
**Warning signs:** `currentIndex`/`currentWidget` calls appear in the new panel.

### Pitfall 3: WR-02 regression through the strip rework
**What goes wrong:** Double `tool_changed` emissions or desynced highlights when tools are selected from menu vs strip.
**Why:** Connecting BOTH `triggered` and `toggled`, or merging window actions into an exclusive group with the strip's actions (the original Phase-6 bug shape).
**How to avoid:** Keep exactly one emission path — `action.toggled(checked=True)` on the strip's own actions; window actions stay standalone checkable and are driven explicitly by `set_active_tool`'s blockSignals loop; strip buttons follow via default-action mirroring.
**Warning signs:** Two `tool_changed` firings per click in tests; previous tool staying visually checked.

### Pitfall 4: Tests keyed to the two-dock chrome break mid-rework
**What goes wrong:** Suite red after `_build_docks` changes even though behavior is intact.
**Verified test touchpoints this session:**
- tests/test_gui_canvas.py:561 — `assert isinstance(window.dock_tools.widget(), ToolsPanel)`
- tests/test_gui_curves_dialog.py:587-591 — asserts `window.action_curves in tools_menu.actions()` (D-09 removes that membership) and no "Levels…"
- tests/test_gui_crop_tool.py:358 — `test_crop_action_in_tools_menu`
- tests/test_gui_detection_settings.py:346 + :275 helper — `_tools_menu_texts` / Detect Boxes menu-absence assertions (pattern reusable for Edit-section slimming)
- tests/test_gui_canvas.py:358+ — tool-group exclusivity/brush unit tests target `ToolsPanel` directly
**How to avoid:** Update affected GUI tests in the same commit as the layout change (RED-GREEN discipline); assert action-list membership, not widget parents (Phase-4 lesson).

### Pitfall 5: Shortcut loss during menu slimming
**What goes wrong:** Removing Rotate/Curves/Resize/Crop… entries appears to drop keyboard access.
**How to avoid:** Audit first: rotate/curves/resize/crop-dialog actions carry NO shortcuts today; tool shortcuts V/B/R/L/E/G are window-level QShortcuts independent of menus; Detect Text (D)/Inpaint (C)/undo shortcuts live on their actions. Keeping the QAction objects alive preserves everything — only remove `tools_menu.addAction(...)` lines.
**Warning signs:** Any `setShortcut` removed rather than just menu membership.

### Pitfall 6: Icon path resolution breaks under pytest/workdir differences
**What goes wrong:** Icons load as null QIcon when CWD ≠ repo root.
**How to avoid:** Resolve against the module file: `Path(__file__).parent / "assets" / "icons"` inside the gui package (or `importlib.resources.files`). Never relative-to-CWD.
**Warning signs:** `QIcon.isNull()` true in offscreen tests; buttons blank.

### Pitfall 7: Scroll-wrap regression (A11)
**What goes wrong:** With four sections expanded the panel clips at 1024x720.
**How to avoid:** The unified panel body keeps the vertical-only QScrollArea wrap (`setWidgetResizable(True)`, horizontal scrollbar always off) exactly like `tools_panel.py:149-171`.
**Warning signs:** Fixed-height bodies or scroll areas nested per-section without widgetResizable.

### Pitfall 8: Dock toggle actions referencing dead docks
**What goes wrong:** `dock_tools.toggleViewAction().trigger` connections (main_window.py:648, :650-653) crash or orphan once the docks are gone.
**How to avoid:** Re-target Toggle Sidebar/Tools/Inspector View-menu actions at the single unified panel in the same task that rebuilds docks.

## Code Examples

### Strip embedding (probe-verified skeleton)
```python
# Source: live probe this session (PySide6 6.10.1, offscreen)
central = QWidget()
row = QHBoxLayout(central)
row.setContentsMargins(0, 0, 0, 0); row.setSpacing(0)

strip = QToolBar("Tools", central)
strip.setOrientation(Qt.Orientation.Vertical)
strip.setIconSize(QSize(20, 20))
for act in (self.action_tool_move, self.action_tool_brush, self.action_tool_rectangle,
            self.action_tool_lasso, self.action_tool_eraser, self.action_tool_crop):
    btn = QToolButton(strip); btn.setDefaultAction(act)
    btn.setCheckable(True); btn.setToolTip(act.text())
    # icon-only style + accent checked border via QSS tokens (_TOOLS_QSS :checked form)
    strip.addWidget(btn)
strip.addSeparator()                       # D-04 divider before Detect/Inpaint
for act in (self.action_detect_text, self.action_inpaint):
    btn = QToolButton(strip); btn.setDefaultAction(act)
    strip.addWidget(btn)
strip.setFixedWidth(44)

row.addWidget(strip)
row.addWidget(self.canvas, 1)
self.setCentralWidget(central)             # replaces setCentralWidget(self.canvas), main_window.py:135
```

### Icon loading (file-path SVG)
```python
# PySide6 6.10.1 ships qsvgicon.dll/qsvg.dll — QIcon renders .svg without extra deps [VERIFIED]
from pathlib import Path
from PySide6.QtGui import QIcon

_ICONS = Path(__file__).parent / "assets" / "icons"

def _icon(name: str) -> QIcon:
    return QIcon(str(_ICONS / f"{name}.svg"))

btn.setIcon(_icon("brush"))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| QToolBox for side stacks | Custom collapsible header+body sections | Long-standing Qt practice | Required here: UI-01 needs independent collapse |
| QMainWindow toolbars for canvas-side strips | Embedded toolbar widgets inside central layout | Intrinsic to QMainWindow layout | D-05 ordering only achievable this way (probe-verified) |
| qrc/rcc resource embedding | File-path resources for source-run Python apps | Packaging-deferred projects | Simpler builds/tests; revisit only if packaging lands |

**Deprecated/outdated:** none affecting this phase.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | UI-02 toggle = chevron in panel header collapsing the whole panel body (dock stays docked); View menu gains single "Toggle Panel" action | Pattern 4 | Cosmetic/UX mismatch — user may expect dock hide; trivially adjustable at UAT |
| A2 | Default section states: all four expanded on first run; per-section collapse persisted thereafter (D-02) | Pattern 1 | Minor UX preference; persisted after first toggle anyway |
| A3 | Icon art direction: monochrome `#e8e8ea` strokes on transparent, ~24px viewBox SVGs so the accent checked-border reads as THE highlight | Pattern 2 / D-06 | Icons may need one visual-polish iteration at end-of-phase UAT |
| A4 | Strip width ~44px with 20px icons is comfortable at min window size | Code Examples | Purely cosmetic; adjust during UAT |
| A5 | SVG rendering via shipped plugins behaves identically under offscreen test platform | Pitfall 6 | If not, tests fall back to asserting non-null QIcon + button wiring, not pixels |

## Open Questions

1. **Fate of `ToolsPanel` class file**
   - What we know: D-03 keeps brush + detection-settings bodies; tool row leaves. Tests import `ToolsPanel` and emit its signals directly.
   - What's unclear: keep `ToolsPanel` as the Brush+Detection widget inside the panel vs dissolve into `side_panel.py`.
   - Recommendation: keep the class (least test churn) but strip its tool row/group; planner picks.
2. **Where the exclusive QActionGroup lives**
   - What we know: today it lives in ToolsPanel (:174-231). With the tool row gone, either move group+toggled machinery into the strip or rely purely on standalone window actions + explicit sync.
   - Recommendation: relocate the group verbatim into the strip widget — preserves the proven toggled-emission contract with zero MainWindow changes beyond signal re-wiring.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Pinned CPython | All test runs | ✓ | 3.14.2 at `C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe` [VERIFIED: AGENTS.md + probes used it] | — |
| PySide6 | Everything GUI | ✓ | 6.10.1 [VERIFIED: probe] | — |
| SVG icon engine plugin | D-06 icons | ✓ | ships in wheel (`qsvgicon.dll`, `qsvg.dll`) [VERIFIED: filesystem probe] | PNG fallback (no extra dep needed) |
| pytest / pytest-qt | Validation | ✓ | installed (tests use qtbot) [VERIFIED: pytest.ini + existing suites] | — |
| Offscreen Qt platform | Headless GUI tests | ✓ | probe ran clean on win32 | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-qt (`qt_api = pyside6`) [VERIFIED: pytest.ini] |
| Config file | `pytest.ini` (testpaths=tests, markers unit/gui) [VERIFIED] |
| Quick run command | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_canvas.py -x -q` |
| Full suite command | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q` (baseline 552 passed per AGENTS.md) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| UI-01 | Four sections independently collapse/expand; state persists via QSettings | gui | `pytest tests/test_gui_side_panel.py -x` (new) | ❌ Wave 0 |
| UI-02 | Panel-header toggle collapses/expands panel body | gui | same new file | ❌ Wave 0 |
| UI-03 | Strip sits between Pages dock and canvas; 8 buttons; divider; icon-only | gui | `pytest tests/test_gui_tools_strip.py -x` (new) + geometry assertion | ❌ Wave 0 |
| UI-04 | Section labeled "Typesetting"; no user-visible "Inspector" remains | gui | extend side-panel tests | ❌ Wave 0 |
| UI-05 | Edit section buttons trigger curves/crop-dialog/resize/rotates; menus slimmed; shortcuts intact | gui | `pytest tests/test_gui_edit_section.py tests/test_gui_curves_dialog.py tests/test_gui_crop_tool.py -x` | partial ❌ Wave 0 |
| WR-02 guard | Single `tool_changed` emission per selection from every entry path | gui | port existing exclusivity tests (test_gui_canvas.py:358+) to strip | ✅ update in place |

### Sampling Rate
- **Per task commit:** quick command above for the touched file(s)
- **Per wave merge:** full suite green
- **Phase gate:** full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_gui_side_panel.py` — collapsible sections, persistence, Typesetting rename, header toggle (UI-01/02/04)
- [ ] `tests/test_gui_tools_strip.py` — order/membership/divider/sync contract (UI-03)
- [ ] `tests/test_gui_edit_section.py` — dialog-entry buttons + menu-slimming assertions (UI-05)
- [ ] Update in place: test_gui_canvas.py:561 dock assertion; test_gui_curves_dialog.py:579-591; test_gui_crop_tool.py:358; test_gui_detection_settings.py menu-texts helper

## Security Domain

> security_enforcement enabled (ASVS Level 1). This phase adds no network, persistence, or input-parsing surfaces — desktop chrome only.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | minimal | No new user-input surfaces; Inspector QTextEdits remain plain-text renderers; spinbox ranges unchanged; icons loaded ONLY from bundled module-relative paths (no user-controlled path reaches QIcon) |
| V2/V3/V4/V6 | no | No auth/session/access-control/crypto surface in a local single-user GUI refactor |

### Known Threat Patterns for PySide6 desktop chrome

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Resource loading from relative/CWD paths | Tampering | Resolve icons via `Path(__file__).parent` / importlib.resources (Pitfall 6) |
| Rich-text injection via labels/tooltips | Tampering | Keep QLabel/QToolTip plain text (existing convention; no setTextFormat(Html) introduced) |

## Sources

### Primary (HIGH confidence)
- Live probes this session (project interpreter, PySide6 6.10.1, offscreen): left-toolbar-area ordering; setCorner no-op; central-layout embedding yields Pages | strip | canvas | Panel; SVG plugin presence in wheel
- Codebase reads this session: main_window.py (:125-149, :299-343, :540-707, :792-1101, :2004-2009, :2965-3009, :4240-4299), tools_panel.py (full), inspector_panel.py (:1-120), pytest.ini, pyproject/AGENTS.md checks
- `.planning/phases/09-ui-rework/09-CONTEXT.md`, ROADMAP §Phase 9, REQUIREMENTS.md UI-01..UI-05

### Secondary (MEDIUM confidence)
- doc.qt.io/qt-6/qtoolbox.html — single-current-item semantics
- doc.qt.io/qt-6/resources.html — resource system, `rcc -g python`, QIcon(":/…")

### Tertiary (LOW confidence)
- None — all external claims above were cross-checked by probes or code reads.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new packages; versions probed on the actual interpreter
- Architecture: HIGH — layout claims reproduced by live probes on this exact machine/wheel; code seams read line-by-line this session
- Pitfalls: HIGH — each pitfall is tied to verified test/code touchpoints or probe output

**Research date:** 2026-08-21
**Valid until:** 2026-09-20 (stable domain; only PySide6 upgrades would invalidate)




