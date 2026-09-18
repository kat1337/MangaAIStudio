# Phase 9: UI Rework - Pattern Map

**Mapped:** 2026-08-21
**Files analyzed:** 13 (6 new, 7 modified)
**Analogs found:** 11 / 13 (2 have no in-codebase analog: SVG icon assets, CollapsibleSection widget)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `manga_ai_studio/gui/side_panel.py` (NEW) | component | event-driven | `manga_ai_studio/gui/tools_panel.py` | role-match (shell/QSS/section-header) |
| `manga_ai_studio/gui/tools_strip.py` (NEW) | component | event-driven | `tools_panel.py:173-254` tool row + `main_window._make_tool_toolbar_button` | exact |
| `manga_ai_studio/gui/assets/icons/*.svg` (NEW, ~8 files) | asset (static) | n/a | none — repo has zero icon assets today | **no analog** |
| Side panel header toggle (UI-02, inside `side_panel.py`) | component | event-driven | `main_window.py:644-653` toggleViewAction wiring | role-match |
| `EditSection` body (inside `side_panel.py`) | component | request-response | `main_window.py:903-971` image-op actions + toolbar `addAction` | role-match |
| `main_window.py` `_build_docks` (:299-334) MODIFIED | provider (window assembly) | n/a | itself — replaced by single-dock build | self |
| `main_window.py` `_build_toolbar` (:981-1034) MODIFIED | provider | n/a | itself — shrunk per D-07 | self |
| `main_window.py` `_build_view_menu` (:643-668) MODIFIED | route | event-driven | itself — Toggle actions re-target unified dock | self |
| `main_window.py` `_build_tools_menu`/:555-570 `_build_edit_menu` MODIFIED | route | event-driven | itself — entries removed, actions kept alive (`action_detect_boxes_mode` precedent :807-818) | self |
| `manga_ai_studio/gui/tools_panel.py` MODIFIED (slimmed) | component | event-driven | itself minus tool row (:173-254 removed) | self |
| `manga_ai_studio/gui/inspector_panel.py` MODIFIED (Typesetting body) | component | event-driven | itself; rename reach enumerated below | self |
| `pyproject.toml` MODIFIED ([tool.setuptools.package-data] :52) | config | n/a | existing package-data section | exact |
| `tests/test_gui_side_panel.py`, `tests/test_gui_tools_strip.py`, `tests/test_gui_edit_section.py` (NEW) + 4 updated test files | test | event-driven | `tests/test_gui_canvas.py:355-414`, `tests/test_gui_detection_settings.py:275-354` | exact |

## Pattern Assignments

### `side_panel.py` (component, event-driven)

**Analog:** `manga_ai_studio/gui/tools_panel.py` — copy its panel shell verbatim.

**Panel shell / A11 scroll-wrap** (tools_panel.py:149-171):
```python
root = QVBoxLayout(self)
root.setContentsMargins(0, 0, 0, 0)
root.setSpacing(0)

self.body_scroll = QScrollArea(self)
self.body_scroll.setObjectName("tools_body_scroll")
self.body_scroll.setWidgetResizable(True)
self.body_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
self.body_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
# Frame-less: the scroll area must not draw chrome around the panel.
self.body_scroll.setFrameShape(QFrame.Shape.NoFrame)

body = QWidget()
self.body_layout = QVBoxLayout(body)
# sm (8px) contents margins + sm spacing (UI-SPEC §Spacing).
self.body_layout.setContentsMargins(8, 8, 8, 8)
self.body_layout.setSpacing(8)
```

**Class-scope Signal declarations** (tools_panel.py:129-138):
```python
tool_changed = Signal(object)
brush_size_changed = Signal(int)
detect_boxes_changed = Signal(bool)
dilation_changed = Signal(int)
std_dev_threshold_changed = Signal(float)
masker_params_changed = Signal()
```

**Section divider + muted 12px Semibold header** (tools_panel.py:400-409) — reuse as the visual language for each section header:
```python
divider = QFrame(self)
divider.setObjectName("_detection_divider")
divider.setFrameShape(QFrame.Shape.HLine)
divider.setFixedHeight(1)
body.addWidget(divider)

section_header = QLabel("Detection settings")
section_header.setObjectName("_detection_section_header")
body.addWidget(section_header)
```

**Detection-settings section body** (tools_panel.py:386-559) carries over nearly verbatim into the first CollapsibleSection body: `QFormLayout` with `setVerticalSpacing(6)` (:412), Detect Boxes checkbox (:417-425), dilation slider+spinbox mirror (:429-452), std-dev spin (:455-469), max-inpaint spin (:472-480), seven fit params (:484-559). Programmatic population via `set_masker_values` with the bulk blockSignals try/finally (tools_panel.py:597-644).

**Brush section body** (tools_panel.py:256-283): label + slider/spinbox row move in as-is.

**Typesetting section body**: the entire `InspectorPanel` (`inspector_panel.py`) becomes the body unchanged — including its Mixed-state machinery and `_INSPECTOR_QSS`. Its docstring line 4 ("QDockWidget 'Inspector'") is part of the UI-04 rename reach.

**QSettings collapse persistence — tolerant bool parse** (main_window.py:2997-3006) — copy this parse shape per-section:
```python
def _read_detect_boxes_mode(self) -> bool:
    raw = self._settings().value("detectBoxesMode", True)
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ("true", "1", "yes", "on")
```
with the accessor (main_window.py:2004-2007):
```python
def _settings(self):
    from PySide6.QtCore import QSettings
    return QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
```

### Panel-header toggle (UI-02, inside `side_panel.py`)

**Analog:** `main_window.py:644-653` — today's View-menu toggles delegate to dock toggleViewActions; re-target at the single unified dock:
```python
self.action_toggle_sidebar = QAction("Toggle Sidebar", self)
self.action_toggle_sidebar.triggered.connect(self.dock_pages.toggleViewAction().trigger)

self.action_toggle_tools = QAction("Toggle Tools", self)
self.action_toggle_tools.triggered.connect(self.dock_tools.toggleViewAction().trigger)

self.action_toggle_inspector = QAction("Toggle Inspector", self)
self.action_toggle_inspector.triggered.connect(
    self.dock_inspector.toggleViewAction().trigger
)
```
Rework: one "Toggle Panel" action replaces Toggle Tools/Toggle Inspector (both dead docks); the panel-header chevron collapses/expands the panel BODY (dock stays docked — plain `setVisible`, no animation).

### `tools_strip.py` (component, event-driven)

**Analog:** `main_window.py:4250-4266` `_make_tool_toolbar_button` — the exact button-mirroring pattern the strip reuses:
```python
def _make_tool_toolbar_button(self, action: QAction) -> QToolButton:
    btn = QToolButton(self.toolbar)
    btn.setDefaultAction(action)
    btn.setCheckable(True)
    btn.setText(action.text())
    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    return btn
```

**The window actions it mirrors** (main_window.py:842-893) — standalone checkable, `setData(ToolMode)`, `triggered -> lambda set_active_tool(...)`:
```python
self.action_tool_move = QAction("Move/Pan", self)
self.action_tool_move.setCheckable(True)
self.action_tool_move.setData(ToolMode.MOVE)
self.action_tool_move.triggered.connect(lambda: self.set_active_tool(ToolMode.MOVE))
# ... same shape for brush/rectangle/lasso/eraser/crop ...
self.action_tool_crop.setToolTip(
    "Crop tool (G): drag a rectangle on the page, Enter applies," " Esc cancels."
)
```
Detect Text / Inpaint are plain non-checkable actions (:794-798, :821-830).

**Central-widget embedding skeleton (D-05, probe-verified)** — from 09-RESEARCH.md Pattern 2 / Code Examples; replaces `setCentralWidget(self.canvas)` (main_window.py:135):
```python
central = QWidget()
row = QHBoxLayout(central)
row.setContentsMargins(0, 0, 0, 0); row.setSpacing(0)
strip = QToolBar("Tools", central)
strip.setOrientation(Qt.Orientation.Vertical)
strip.setIconSize(QSize(20, 20))
for act in (self.action_tool_move, ... , self.action_tool_crop):
    btn = QToolButton(strip); btn.setDefaultAction(act); btn.setCheckable(True)
    btn.setToolTip(act.text())
    strip.addWidget(btn)
strip.addSeparator()          # D-04 divider before Detect/Inpaint
for act in (self.action_detect_text, self.action_inpaint):
    btn = QToolButton(strip); btn.setDefaultAction(act)
    strip.addWidget(btn)
strip.setFixedWidth(44)
row.addWidget(strip)
row.addWidget(self.canvas, 1)
self.setCentralWidget(central)
```
DO NOT use `addToolBar(Qt.LeftToolBarArea)` — probe-verified it renders OUTSIDE the Pages dock column.

**WR-02 sync loop the strip must not regress** (main_window.py:4268-4309):
```python
def set_active_tool(self, tool: ToolMode) -> None:
    self.canvas.set_tool(tool)
    self.tools_panel.set_active_tool(tool)
    for act in (self.action_tool_move, ..., self.action_tool_crop):
        was = act.blockSignals(True)
        act.setChecked(act.data() == tool)
        act.blockSignals(was)
    for btn in self.toolbar.findChildren(QToolButton):
        act = btn.defaultAction()
        if act is not None and act.data() == tool:
            was = btn.blockSignals(True)
            btn.setChecked(True)
            btn.blockSignals(was)
```
Rule: the strip's exclusive group (if kept) holds ONLY the strip's own 6 actions; window actions stay standalone and driven explicitly. Exactly one emission path — `toggled` on checked transition (the proven form is tools_panel.py:314-327 `_on_action_toggled`, which fires only on `checked=True`; note the group's `triggered` misses programmatic changes — tools_panel.py:226-231 comment).

### `assets/icons/*.svg` + loading helper (asset, NO ANALOG)

Repo has zero icon assets (grep-confirmed: only planning-doc mentions). No codebase analog exists — use the research pattern:

```python
from pathlib import Path
from PySide6.QtGui import QIcon

_ICONS = Path(__file__).parent / "assets" / "icons"   # NEVER CWD-relative (Pitfall 6)

def _icon(name: str) -> QIcon:
    return QIcon(str(_ICONS / f"{name}.svg"))
```
Art direction per 09-RESEARCH A3: monochrome `#e8e8ea` strokes, ~24px viewBox, transparent background; active highlight stays the QSS accent border (`:checked { border: 1px solid #00d4ff; }`). Add `[tool.setuptools.package-data]` entry covering `gui/assets/icons/*.svg` in the same commit (pyproject.toml:52 already has the section header).

### EditSection body (component, request-response)

**Analog:** the six image-op actions it binds, created at main_window.py:903-947 — bind these EXISTING actions via `setDefaultAction`, never recreate:
```python
self.action_rotate_cw.triggered.connect(lambda: self._rotate_page(-1))
self.action_rotate_cw.setEnabled(False)      # gated in _refresh_action_states
...
self.action_curves.triggered.connect(self._on_curves)
...
self.action_resize.triggered.connect(self._on_resize)
```
plus `action_crop_dialog` (:555-560, "Crop…" numeric dialog — NOT the G tool). Gating is inherited free because `_refresh_action_states` (main_window.py:1095-1130+) recomputes enabled state on every page/op event and default-action buttons track their action's enabled state.

### `main_window.py` menu slimming (route, event-driven)

**Analog:** the `action_detect_boxes_mode` state-holder precedent (main_window.py:807-818, :951-954):
```python
# NOTE (plan 08-05, A8): action_detect_boxes_mode is deliberately NOT
# added here — the Detect Boxes toggle moved to the Tools dock's
# detection-settings section (the single user-facing control). The
# action lives on as the state holder only.
```
Apply identically for D-09: remove `rotate_menu`/`action_curves`/`action_resize` lines from `tools_menu.addAction(...)` (:964-969) and `action_crop_dialog` from the edit menu (:568) — keep every QAction object alive so shortcuts/state/tests survive. Shortcut audit (research Pitfall 5): rotate/curves/resize/crop-dialog carry NO shortcuts today; V/B/R/L/E/G/D/C live on window QShortcuts/actions independent of menus — removal is menu-membership-only.

### `tools_panel.py` slimmed (component, event-driven)

Remove the tool row + group construction (:173-254) and the tool-row API surface (`_make_tool_action`, `_on_action_toggled`, `set_active_tool`, `active_tool`) OR relocate them wholesale into the strip (open question #2 in research — recommendation: relocate the group verbatim). Keep: brush rows, detection-settings section, ALL signals (`brush_size_changed`, `detect_boxes_changed`, `dilation_changed`, `std_dev_threshold_changed`, `masker_params_changed`) — tests emit them directly (test_gui_detection_settings.py:299, :316, :332-333).

### `inspector_panel.py` → Typesetting body

Rename reach (UI-04, verified occurrences): `main_window.py:326` `QDockWidget("Inspector", ...)`, `main_window.py:650` `QAction("Toggle Inspector", ...)`, `inspector_panel.py:1-62` docstring mentions. No persisted state keyed on the name (research Runtime State Inventory: grep-verified, app never calls saveState/restoreState). The class may keep its name internally; user-visible strings change everywhere.

### Test files (test, event-driven)

**Exclusivity/sync test port target** — test_gui_canvas.py:358-387 is the template for the new strip tests:
```python
actions = panel.tool_group.actions()
assert len(actions) == 6
assert panel.tool_group.isExclusive()
with qtbot.waitSignal(panel.tool_changed, timeout=1000) as blocker:
    panel.action_brush.setChecked(True)
assert blocker.args == [ToolMode.BRUSH]
```

**Menu-slimming assertion template** — test_gui_detection_settings.py:275-288 helper + :346-354 assertion:
```python
def _tools_menu_texts(window: MainWindow) -> list[str] | None:
    bar_actions = window.menuBar().actions()
    for bar_act in bar_actions:
        menu = bar_act.menu()
        if menu is not None and "Tools" in menu.title():
            menu_actions = menu.actions()
            return [act.text() for act in menu_actions]
    return None
...
texts = _tools_menu_texts(window)
assert "Detect Boxes" not in texts
```
Assert action-list MEMBERSHIP, never widget parents (Phase-4 lesson). Also holds wrappers while resolving (PySide6 wrapper-lifetime quirk — test_gui_curves_dialog.py:583-591).

**In-place updates required:** test_gui_canvas.py:561 (`isinstance(window.dock_tools.widget(), ToolsPanel)` — dock dies), test_gui_canvas.py:350-354 (toolbar-button mirror assertions), test_gui_curves_dialog.py:579-591 (`action_curves in tools_menu.actions()` — D-09 removes membership), test_gui_crop_tool.py:358 (`test_crop_action_in_tools_menu`), test_gui_detection_settings.py helper.

## Shared Patterns

### Dark QSS token vocabulary
**Source:** `tools_panel.py:59-123` (`_TOOLS_QSS`) and `inspector_panel.py:101-168` (`_INSPECTOR_QSS`)
**Apply to:** side panel chrome, strip styling, any new section headers.
Tokens: bg `#2d2d33`, border `#3a3a42`, fg `#e8e8ea`, muted `#9a9aa2`, disabled `#25252b`/`#6a6a72`, accent `#00d4ff` (checked border ONLY — reserved use #1). Section headers: `color:#9a9aa2; font-weight:600; font-size:12px`. Dividers: `#_detection_divider` 1px HLine pattern. Palette-level tokens also declared in `theme.py:17-23`.

### blockSignals mirror pairs
**Source:** `tools_panel.py:360-383` (brush), :561-573 (dilation), :597-644 (`set_masker_values` bulk guard)
**Apply to:** every relocated slider↔spinbox pair and programmatic population — move verbatim, do not rewrite during relocation.

### Default-action mirroring for enablement gating
**Source:** `main_window.py:4250-4266` + `_refresh_action_states` (:1095-1130)
**Apply to:** strip buttons AND Edit-section buttons — always `setDefaultAction(existing_action)`, never lambda-buttons calling `.trigger()` (they'd need manual gating mirrors).

### QSettings view-state persistence (NOT profile INI)
**Source:** `main_window.py:2004-2007` (accessor), :2997-3006 (tolerant parse), :2986-2992 (seed-with-blockSignals)
**Apply to:** per-section collapse state keys (new keys, e.g. `sidePanel/<section>`); seed after build with signals blocked.

### Keep-actions-alive-as-state-holders
**Source:** `main_window.py:807-818` (`action_detect_boxes_mode`)
**Apply to:** all D-09 menu removals — delete `addAction` calls only, never the QAction objects.

### Keyboard-reachability preservation
**Source:** shortcuts live on window-level QShortcuts (main_window.py:2960-2964) and action-level `setShortcut` (e.g. :794-796, :822) — independent of menu membership.
**Apply to:** audit before rebinding; warning sign = any `setShortcut` call removed rather than a menu `addAction` line.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `gui/assets/icons/*.svg` (8 files) | asset | n/a | Repo contains zero icon/image assets (glob + grep confirmed across `manga_ai_studio/`); all buttons render `ToolButtonTextOnly`. Use 09-RESEARCH.md Code Examples §Icon loading + A3 art direction. |
| `CollapsibleSection` widget (inside `side_panel.py`) | component | event-driven | No collapsible-section widget exists anywhere in the GUI layer (checked tools_panel/inspector_panel/theme/main_window). Closest partial: the static divider+header pattern at tools_panel.py:400-409 supplies the VISUAL language; the toggle mechanism comes from 09-RESEARCH.md Pattern 1 (plain `setVisible`, no animation — QPropertyAnimation interacts badly with QScrollArea sizing). |

## Metadata

**Analog search scope:** `manga_ai_studio/gui/` (all files), `tests/test_gui_*.py`, `pyproject.toml`
**Files scanned:** ~20 (4 read in full or large sections: tools_panel.py, inspector_panel.py, theme.py; main_window.py via 8 targeted non-overlapping ranges; 5 test touchpoints)
**Pattern extraction date:** 2026-08-21
