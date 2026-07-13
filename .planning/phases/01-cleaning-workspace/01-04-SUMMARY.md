---
phase: "01"
plan: "04"
subsystem: mask-editing
tags: [mask-editor, brush, rectangle, lasso, eraser, qgraphicsview, qactiongroup, cursor-visuals, tools-panel, gpl]
requires:
  - "manga_ai_studio.gui.canvas.EditorCanvas (plan 01-02 image/mask item stack + pan/zoom; plan 01-03 set_mask/toggle_mask_overlay/has_mask/clear_mask)"
  - "manga_ai_studio.gui.main_window.MainWindow (plan 01-02 menu/shell + Tools dock placeholder; plan 01-03 Detect Text wiring)"
  - "C:\\Users\\Stella\\Downloads\\MangaCleaner_GPU\\_internal\\src\\frontend\\canvas.py (REFERENCE ONLY per D-12 — reimplement, do not vendor)"
  - "C:\\Users\\Stella\\Downloads\\MangaCleaner_GPU\\_internal\\src\\frontend\\widgets.py (REFERENCE ONLY per D-12 — reimplement)"
  - "C:\\Src\\PanelCleaner\\pcleaner\\image_ops.py convert_mask_to_rgba pattern (GPL v3)"
provides:
  - "manga_ai_studio.core.mask_editor (pure ops, testable headless): ToolMode enum (MOVE/BRUSH/RECTANGLE/LASSO/ERASER), MASK_PAINT_COLOR QColor(255,0,0,160), MIN/MAX/DEFAULT_BRUSH_SIZE, clamp_brush_size, paint_mask_stroke (Qt.RoundCap/RoundJoin), paint_mask_rect, paint_mask_lasso, clear_mask, mask_to_numpy_binary (alpha thresholded to 0/255 + .copy()), numpy_binary_to_mask_qimage (qimg.copy())"
  - "manga_ai_studio.gui.tools_panel.ToolsPanel(QWidget): QActionGroup (5 exclusive tools), QSlider(1-300)+QSpinBox(1-300) synced, 'Brush size: {n} px' label, signals tool_changed(ToolMode)+brush_size_changed(int), QSS active-tool highlight #00d4ff"
  - "manga_ai_studio.gui.canvas.EditorCanvas (extended): current_tool/brush_size/is_eraser_modifier state, self._mask QImage (editable), preview_item (QGraphicsPathItem dashed-cyan z=900) + cursor_item (QGraphicsEllipseItem z=1000 red/cyan), set_tool/set_brush_size/_update_cursor_visuals/_effective_eraser, tool-dispatching mousePress/Move/Release, Shift transient Brush<->Eraser, mask_modified Signal (once per stroke), get_mask/update_mask_display"
  - "manga_ai_studio.gui.main_window.MainWindow (extended): tools_panel (ToolsPanel in Tools dock), set_active_tool(tool) sync, toolbar tool-buttons section, QShortcuts B/R/L/E/V, Clear Mask with [Cancel][Clear Mask] confirmation"
affects:
  - "plan 05 (inpaint) consumes core.mask_editor.mask_to_numpy_binary to extract the (H,W) binary mask for the LaMa adapter, and numpy_binary_to_mask_qimage to re-display post-inpaint masks"
  - "plan 06 (undo/redo) consumes EditorCanvas.mask_modified (emitted once per stroke) as the snapshot trigger for the mask undo stack, and get_mask() for snapshot capture"
  - "plan 05 Inpaint (C) action enable state will also gate on canvas.has_mask() (already wired in _refresh_action_states)"
tech-stack:
  added: []
  patterns:
    - "Pure mask-mutation ops in core/ testable without QWidget (D-10): gui/canvas.py dispatches mouse events; core/mask_editor.py holds the QPainter draws (brush stroke RoundCap/RoundJoin, rect fillRect, lasso fillPath, eraser CompositionMode_Clear)"
    - "Editable mask as self._mask QImage mutated IN PLACE (RESEARCH Pitfall 4): update_mask_display refreshes the pixmap from the same QImage; no new QImage allocated per mouse-move"
    - "QImage<->numpy .copy() discipline both directions (RESEARCH Pitfall 2; PATTERNS.md §Shared Pattern 5): mask_to_numpy_binary thresholds alpha>0 to true binary 0/255 and .copy()-detaches (OWNDATA True); numpy_binary_to_mask_qimage returns qimg.copy()"
    - "Tool dispatch via enum (not stringly-typed): ToolMode.MOVE/BRUSH/RECTANGLE/LASSO/ERASER; differs from MangaCleaner_GPU's 'NONE'/'BRUSH'/'RECT'/'LASSO' — Eraser is a first-class tool per UI-SPEC, Shift is a transient Brush<->Eraser modifier"
    - "QActionGroup exclusivity via toggled signal (not triggered): each action's toggled(checked=True) emits tool_changed so programmatic setChecked and user clicks both fire"
    - "Viewport->scene coordinate mapping via mapToScene(toPoint()): QGraphicsView.mapToScene takes QPoint not QPointF; mapFromScene computes the right viewport coords for synthesized test events regardless of canvas centering/zoom"
key-files:
  created:
    - manga_ai_studio/core/mask_editor.py
    - manga_ai_studio/gui/tools_panel.py
    - tests/test_mask_editor/__init__.py
    - tests/test_mask_editor/test_mask_editor.py
  modified:
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_gui_canvas.py
    - pytest.ini
key-decisions:
  - "mask_to_numpy_binary thresholds alpha>0 to a true binary 0/255 mask (not raw alpha 160): the inpaint backend needs a crisp binary mask, and the on-canvas overlay alpha (160 ~= 0.63) is a display concern, not the mask content. The plan's literal action returned the raw alpha; the behavior contract (test_mask_to_numpy_binary_round_trip) required 255 where painted — thresholding reconciles them (Rule 1 bug fix)."
  - "QActionGroup toggled signal (not triggered) drives tool_changed: QActionGroup.triggered only fires on user activation, missing programmatic setChecked (used by set_active_tool). Connecting each action's toggled(checked=True) fires for both paths."
  - "mapToScene takes QPoint, not QPointF (PySide6): event.position() returns QPointF; convert via toPoint() before mapToScene, then wrap back to QPointF for sub-pixel-accurate scene coords. Test events use mapFromScene to compute viewport coords that land at the desired scene pixel."
  - "Shift modifier keyed off event.key()==Key_Shift, NOT event.modifiers(): Qt delivers the Shift KeyPress with modifiers()==NoModifier (modifiers reflect pre-press state), so the modifiers() check never saw the Shift press. Keying off event.key() is reliable."
  - "self._mask is the editable QImage (distinct from mask_item the QGraphicsPixmapItem): set_image and set_mask both store it; brush/rect/lasso/eraser mutate it in place and call update_mask_display. has_mask()/clear_mask()/get_mask() all key off self._mask now."
  - "Clear Mask emits mask_modified (same as a stroke): it is a mask-mutating op the plan-06 history stack should snapshot; added a [Cancel][Clear Mask] confirmation per UI-SPEC §Copywriting destructive."
patterns-established:
  - "Tool-dispatch test pattern: fabricate QMouseEvents with mapFromScene-mapped viewport coords so assertions on scene pixels (mask.pixelColor) hold regardless of canvas centering/zoom — robust against QGraphicsView viewport<->scene offset"
  - "Single mask_modified emission per stroke: mousePress paints a dot, mouseMove advances the stroke, mouseRelease commits + emits once; clear_mask also emits once (both are the history snapshot triggers)"
  - "Tool sync triangle: ToolsPanel.tool_changed -> MainWindow.set_active_tool -> canvas.set_tool + toolbar button checked state; set_active_tool blockSignals on programmatic setChecked to avoid re-emission loops"
requirements-completed:
  - CLEAN-03
  - CLEAN-04
  - CLEAN-05
coverage:
  - id: M1
    description: "paint_mask_stroke draws a round-cap red stroke (opaque band crossing the stroked row; cap discs fill endpoints)"
    requirement: "CLEAN-03"
    verification:
      - kind: unit
        ref: "tests/test_mask_editor/test_mask_editor.py#test_brush_paint_draws_red_stroke"
        status: pass
      - kind: unit
        ref: "tests/test_mask_editor/test_mask_editor.py#test_brush_paint_uses_round_cap"
        status: pass
      - kind: unit
        ref: "tests/test_mask_editor/test_mask_editor.py#test_brush_stroke_paint_color_is_red"
        status: pass
      - kind: integration
        ref: "tests/test_gui_canvas.py#test_canvas_set_tool_routes_to_mask_editor_brush"
        status: pass
      - kind: integration
        ref: "tests/test_gui_canvas.py#test_cursor_circle_follows_brush_size"
        status: pass
    human_judgment: true
    rationale: "Stroke-smoothness feel (anti-aliasing, no gaps, cursor tracking) is a manual check per VALIDATION.md §Manual-Only CLEAN-03; the unit/integration tests prove the paint routing and pixel correctness."
  - id: M2
    description: "paint_mask_rect fills a rectangle; paint_mask_lasso fills a closed path; dashed-cyan preview follows the drag"
    requirement: "CLEAN-04"
    verification:
      - kind: unit
        ref: "tests/test_mask_editor/test_mask_editor.py#test_rect_fill"
        status: pass
      - kind: unit
        ref: "tests/test_mask_editor/test_mask_editor.py#test_lasso_fill"
        status: pass
      - kind: integration
        ref: "tests/test_gui_canvas.py#test_canvas_set_tool_routes_to_mask_editor_rectangle"
        status: pass
      - kind: integration
        ref: "tests/test_gui_canvas.py#test_canvas_set_tool_routes_to_mask_editor_lasso"
        status: pass
      - kind: integration
        ref: "tests/test_gui_canvas.py#test_preview_item_dashed_cyan"
        status: pass
    human_judgment: false
  - id: M3
    description: "Eraser clears mask regions via CompositionMode_Clear; Shift transiently toggles Brush<->Eraser; brush size 1-300 clamped"
    requirement: "CLEAN-05"
    verification:
      - kind: unit
        ref: "tests/test_mask_editor/test_mask_editor.py#test_eraser_clears"
        status: pass
      - kind: unit
        ref: "tests/test_mask_editor/test_mask_editor.py#test_eraser_clears_rect_region"
        status: pass
      - kind: unit
        ref: "tests/test_mask_editor/test_mask_editor.py#test_clamp_brush_size"
        status: pass
      - kind: integration
        ref: "tests/test_gui_canvas.py#test_canvas_eraser_tool_clears"
        status: pass
      - kind: integration
        ref: "tests/test_gui_canvas.py#test_canvas_shift_toggles_brush_eraser"
        status: pass
    human_judgment: false
  - id: M4
    description: "5 exclusive tools (QActionGroup) Move/Brush/Rectangle/Lasso/Eraser with synced brush slider/spinbox; mask_modified once per stroke (plan-06 hook)"
    requirement: "CLEAN-03"
    verification:
      - kind: integration
        ref: "tests/test_gui_canvas.py#test_tools_panel_tool_group_exclusive"
        status: pass
      - kind: integration
        ref: "tests/test_gui_canvas.py#test_tools_panel_brush_slider_spinbox_sync"
        status: pass
      - kind: integration
        ref: "tests/test_gui_canvas.py#test_tools_panel_brush_range_clamped"
        status: pass
      - kind: integration
        ref: "tests/test_gui_canvas.py#test_canvas_emits_mask_modified"
        status: pass
      - kind: integration
        ref: "tests/test_gui_canvas.py#test_main_window_tool_shortcuts"
        status: pass
    human_judgment: false
  - id: M5
    description: "QImage<->numpy conversions enforce .copy() both directions (RESEARCH Pitfall 2 regression guard)"
    requirement: "CLEAN-03"
    verification:
      - kind: unit
        ref: "tests/test_mask_editor/test_mask_editor.py#test_numpy_extract_copies_buffer"
        status: pass
      - kind: unit
        ref: "tests/test_mask_editor/test_mask_editor.py#test_numpy_binary_to_mask_qimage_returns_detached_qimage"
        status: pass
      - kind: unit
        ref: "tests/test_mask_editor/test_mask_editor.py#test_mask_to_numpy_binary_round_trip"
        status: pass
    human_judgment: false
metrics:
  duration: "22 min"
  completed: "2026-07-13"
  tasks: 2
  files: 8
  tests: 30
status: complete
---

# Phase 01 Plan 04: Mask Editing Slice Summary

Delivered the mask-editing vertical slice (CLEAN-03/04/05): a user can paint a mask with an adjustable round brush, fill rectangles and freehand lassos, and erase mask regions, using an exclusive 5-tool panel. Per D-10 the mask-mutation LOGIC lives in `core/mask_editor.py` as pure functions of `(QImage, tool, points, brush_size)` testable without any QWidget; the Qt event dispatch + cursor visuals live in `gui/canvas.py`; the tool buttons + brush slider/spinbox + QActionGroup live in `gui/tools_panel.py` (all three reimplemented patterned after MangaCleaner_GPU per D-12, never vendored). The QImage<->numpy conversions enforce `.copy()` both directions (RESEARCH Pitfall 2 regression guard).

## Performance

- **Duration:** 22 min
- **Started:** 2026-07-13T17:52:02Z
- **Completed:** 2026-07-13T18:14:02Z
- **Tasks:** 2
- **Files modified:** 8 (4 created + 4 modified)

## Accomplishments

- `core/mask_editor.py` (D-10 pure ops, headless-testable): `ToolMode` enum (MOVE/BRUSH/RECTANGLE/LASSO/ERASER), `MASK_PAINT_COLOR = QColor(255,0,0,160)` (rgba(255,0,0,0.63)), `MIN_BRUSH_SIZE=1`/`MAX_BRUSH_SIZE=300`/`DEFAULT_BRUSH_SIZE=40`, `clamp_brush_size`, `paint_mask_stroke` (`Qt.RoundCap`/`Qt.RoundJoin`), `paint_mask_rect`, `paint_mask_lasso`, `clear_mask`, `mask_to_numpy_binary` (alpha>0 thresholded to 0/255 + `.copy()`), `numpy_binary_to_mask_qimage` (`qimg.copy()`). Eraser path uses `QPainter.CompositionMode_Clear`.
- `gui/tools_panel.py` (`ToolsPanel(QWidget)`): `QActionGroup` (5 exclusive checkable tools), `QSlider(1-300)` + `QSpinBox(1-300)` synced brush-size pair (default 40), `"Brush size: {n} px"` label, signals `tool_changed(ToolMode)` + `brush_size_changed(int)`; QSS active-tool highlight `#00d4ff` (accent reserved use #1). Reimplemented patterned after MangaCleaner_GPU `widgets.py` (D-12 reference-only).
- `gui/canvas.py` (`EditorCanvas` extended): tool dispatch (`set_tool`/`set_brush_size`/`_effective_eraser`), `QGraphicsPathItem` dashed-cyan preview (z=900, `QPen(QColor(0,212,255,200), 2, Qt.DashLine)`), `QGraphicsEllipseItem` cursor circle (z=1000, red paint / cyan erase), mousePress/Move/Release routing to `core/mask_editor` ops, `self._mask` QImage (editable, mutated in place per RESEARCH Pitfall 4), `mask_modified = Signal()` (once per stroke on release — plan-06 history hook), `get_mask`/`update_mask_display`. Shift transiently toggles Brush<->Eraser (modifier only; the active tool action stays Brush).
- `gui/main_window.py` (`MainWindow` extended): Tools dock populated with `ToolsPanel` (replacing the plan-02 placeholder), toolbar tool-buttons section (checkable `QToolButton`s sharing the panel's state), `QShortcut` B/R/L/E/V per UI-SPEC §Keyboard, `set_active_tool(tool)` keeping panel+toolbar+canvas in sync, Clear Mask wired with the `[Cancel][Clear Mask]` confirmation (UI-SPEC §Copywriting destructive). Tool actions enabled when a page is open; Move always enabled.
- 30 new tests green (18 `test_mask_editor` unit + 12 `test_gui_canvas` integration); full suite 69 passed (39 prior + 30 new), no regressions.

## Task Commits

Each task was committed atomically:

1. **Task 1: core/mask_editor.py pure mask ops + QImage/numpy conversions** - `aea4425` (feat)
2. **Task 2: ToolsPanel + canvas tool dispatch + cursor visuals + MainWindow wiring** - `aec63bb` (feat)

## Files Created/Modified

- `manga_ai_studio/core/mask_editor.py` - ToolMode enum + pure paint/erase ops + QImage<->numpy conversions with .copy() both directions
- `manga_ai_studio/gui/tools_panel.py` - ToolsPanel: QActionGroup (5 tools) + synced brush slider/spinbox + signals
- `manga_ai_studio/gui/canvas.py` - tool dispatch, dashed-cyan preview, brush-size cursor circle, mask_modified signal, self._mask editable QImage, Shift modifier
- `manga_ai_studio/gui/main_window.py` - Tools dock populated, toolbar tool buttons, B/R/L/E/V shortcuts, set_active_tool, Clear Mask
- `tests/test_mask_editor/test_mask_editor.py` - 18 unit tests (brush/rect/lasso/eraser/clear/clamp/round-trip/buffer-lifetime)
- `tests/test_gui_canvas.py` - 12 new integration tests (tool-group, slider/spinbox sync, BRUSH/RECT/LASSO routing, eraser, Shift toggle, cursor resize, dashed-cyan preview, mask_modified once, shortcuts)
- `pytest.ini` - suppress PySide6 QMouseEvent 5-arg ctor deprecation noise

## Decisions Made

- **Binary threshold in mask_to_numpy_binary:** the plan's literal action returned the raw alpha channel (160 for painted pixels), but the inpaint backend needs a crisp binary mask. Threshold alpha>0 to 255 so the round-trip test (255 where painted) holds and plan 05 receives a true binary mask. The 160-alpha overlay is a display concern, not the mask content.
- **QActionGroup toggled (not triggered) drives tool_changed:** `QActionGroup.triggered` only fires on user activation, missing programmatic `setChecked` (used by `set_active_tool`). Each action's `toggled(checked=True)` fires for both paths.
- **mapToScene(QPoint) not QPointF:** PySide6's `QGraphicsView.mapToScene` takes a `QPoint`; `event.position()` returns `QPointF`. Convert via `toPoint()` then wrap back to `QPointF` for sub-pixel accuracy. Test events use `mapFromScene` to compute viewport coords landing at the desired scene pixel.
- **Shift modifier keyed off event.key():** Qt delivers the Shift KeyPress with `modifiers()==NoModifier` (modifiers reflect pre-press state), so the `modifiers() & ShiftModifier` check never fired. Keying off `event.key() == Key_Shift` is reliable.
- **self._mask as the editable QImage:** distinct from `mask_item` (the display pixmap); `set_image` and `set_mask` both store it; paint ops mutate it in place; `has_mask`/`clear_mask`/`get_mask` all key off it.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] mask_to_numpy_binary returned raw alpha (160) instead of a true binary mask**
- **Found during:** Task 1 (`test_mask_to_numpy_binary_round_trip` failed: `assert 160 == 255`)
- **Issue:** The plan's literal action said `alpha = arr[:,:,3]; return alpha.copy()`, which returns the raw alpha channel. Painted pixels have alpha 160 (the rgba(255,0,0,0.63) overlay), not 255. The behavior contract required 255 where painted (a binary mask for the inpaint backend), and the round-trip test asserted `binary[50,50] == 255`.
- **Fix:** Threshold alpha>0 to 255: `binary = np.where(alpha > 0, np.uint8(255), np.uint8(0)); return binary.copy()`. The 160-alpha is a display concern; the backend needs a crisp binary.
- **Files modified:** `manga_ai_studio/core/mask_editor.py`
- **Verification:** `test_mask_to_numpy_binary_round_trip` passes (255 painted / 0 elsewhere).
- **Committed in:** `aea4425` (Task 1)

**2. [Rule 1 - Bug] tool_changed not emitted on programmatic setChecked (QActionGroup.triggered only fires on user activation)**
- **Found during:** Task 2 (`test_tools_panel_tool_group_exclusive` timed out: signal not emitted)
- **Issue:** The first ToolsPanel wired `self.tool_group.triggered` to the emit slot. `QActionGroup.triggered` fires on user activation (click/menu/shortcut), NOT on programmatic `setChecked(True)`. The test called `panel.action_brush.setChecked(True)` directly, so no signal fired.
- **Fix:** Connect each action's `toggled` signal instead; the slot emits `tool_changed` only on `checked=True`. This fires for both user clicks and programmatic `setChecked`.
- **Files modified:** `manga_ai_studio/gui/tools_panel.py`
- **Verification:** `test_tools_panel_tool_group_exclusive` passes; signal carries the correct ToolMode.
- **Committed in:** `aec63bb` (Task 2)

**3. [Rule 1 - Bug] mapToScene(QPointF) raised TypeError — QGraphicsView.mapToScene takes QPoint**
- **Found during:** Task 2 (`test_canvas_set_tool_routes_to_mask_editor_brush` failed: `TypeError: mapToScene called with wrong argument types`)
- **Issue:** `_begin_paint`/`_advance_paint`/`_end_paint`/`mouseMoveEvent` called `self.mapToScene(event.position())`. `QMouseEvent.position()` returns a `QPointF`, but `QGraphicsView.mapToScene` requires a `QPoint` (int) in PySide6.
- **Fix:** Added a `_scene_pos(event)` helper that does `QPointF(self.mapToScene(event.position().toPoint()))`; all four call sites use it. Tests use `mapFromScene` to compute viewport coords landing at the desired scene pixel (robust against canvas centering/zoom offset).
- **Files modified:** `manga_ai_studio/gui/canvas.py`, `tests/test_gui_canvas.py`
- **Verification:** All canvas tool-routing tests pass (brush stroke lands at scene row 10).
- **Committed in:** `aec63bb` (Task 2)

**4. [Rule 1 - Bug] Shift KeyPress delivered with modifiers()==NoModifier (modifiers reflect pre-press state)**
- **Found during:** Task 2 (`test_canvas_shift_toggles_brush_eraser` failed: `is_eraser_modifier` stayed False)
- **Issue:** The Shift-toggle logic checked `event.modifiers() & Qt.KeyboardModifier.ShiftModifier`. Qt delivers the Shift KeyPress with `modifiers()==NoModifier` (modifiers reflect the state BEFORE the key was pressed), so the check never saw the Shift press. (Verified via debug script: `event.modifiers()` was `NoModifier` for a Shift press carrying `ShiftModifier` in its ctor.)
- **Fix:** Key off `event.key() == Qt.Key.Key_Shift` instead of `event.modifiers()` for both press and release. This is reliable across Qt's modifier-timing quirk.
- **Files modified:** `manga_ai_studio/gui/canvas.py`
- **Verification:** `test_canvas_shift_toggles_brush_eraser` passes (modifier toggles, active tool stays Brush).
- **Committed in:** `aec63bb` (Task 2)

---

**Total deviations:** 4 auto-fixed (all Rule 1 bugs — PySide6 API / Qt semantics differences from the plan's PyQt5-flavored action text)
**Impact on plan:** All fixes necessary for correctness (binary mask contract, signal wiring, coordinate typing, Shift-key timing). No scope creep.

## Authentication Gates

None — no auth-required operations in this plan.

## Known Stubs

This plan intentionally ships stubs whose backing logic lands in later plans:

| Stub | File | Line | Reason | Resolved By |
|------|------|------|--------|-------------|
| Inpaint (C) action still disabled | `manga_ai_studio/gui/main_window.py` | `_build_tools_menu` | LaMa inpainting is plan 05 (CLEAN-06). | Plan 01-05 |
| mask_modified signal consumed but no history stack yet | `manga_ai_studio/gui/canvas.py` | `mask_modified = Signal()` | The undo/redo (Alt+Z) stack that snapshots on this signal is plan 06. The signal is wired and emitted correctly; plan 06 connects the consumer. | Plan 01-06 |
| Toolbar tool buttons render text-only (no icons) | `manga_ai_studio/gui/tools_panel.py` + `main_window.py` | tool row / toolbar | UI-SPEC surface 6 contracts icon buttons, but no SVG icon assets are bundled in Phase 1. The QToolButtons use `ToolButtonTextOnly` so labels show; icon assets are a polish task. | Future polish |

No stubs that block this plan's goal (paint/fill/erase a mask with the 5-tool panel).

## Threat Flags

No new security-relevant surface beyond the plan's `<threat_model>`. All four registered threats mitigated as specified:

- **T-01-09 (brush size input validation):** `clamp_brush_size` clamps every integer reaching a QPen width to `[1,300]`; the QSpinBox/QSlider also enforce `setMinimum(1)`/`setMaximum(300)`. `test_clamp_brush_size` + `test_tools_panel_brush_range_clamped` are the guards.
- **T-01-10 (QGraphicsView perf on large pages):** paint ops mutate `self._mask` in place and call `update_mask_display()` (no new QImage per mouse-move). `test_canvas_emits_mask_modified` confirms the single-emission-per-stroke discipline.
- **T-01-11 (QImage buffer lifetime):** `mask_to_numpy_binary` returns `binary.copy()` (OWNDATA True — `test_numpy_extract_copies_buffer`); `numpy_binary_to_mask_qimage` returns `qimg.copy()` (`test_numpy_binary_to_mask_qimage_returns_detached_qimage` GC-survival guard).
- **T-01-12 (out-of-canvas coordinates):** accepted — QPainter's own scissoring to the QImage bounds clips out-of-rect drags; no separate bounds check needed.

## Commits

- `aea4425` — feat(01-04): core/mask_editor.py pure mask ops + QImage/numpy conversions (Task 1)
- `aec63bb` — feat(01-04): ToolsPanel + canvas tool dispatch + cursor visuals + MainWindow wiring (Task 2)

## Self-Check: PASSED

- All 8 key files FOUND on disk: `core/mask_editor.py`, `gui/tools_panel.py`, `gui/canvas.py` (modified), `gui/main_window.py` (modified), `tests/test_mask_editor/__init__.py`, `tests/test_mask_editor/test_mask_editor.py`, `tests/test_gui_canvas.py` (modified), `pytest.ini` (modified).
- Both task commits FOUND in git log: `aea4425` (Task 1), `aec63bb` (Task 2).
- Plan `<verification>`: `pytest tests/test_mask_editor/ tests/test_gui_canvas.py -x` exits 0 (41 passed).
- Buffer-lifetime regression guards PASSED: `test_numpy_extract_copies_buffer` (OWNDATA True) + `test_numpy_binary_to_mask_qimage_returns_detached_qimage` (survives GC).
- mask_modified single-emission PASSED (exactly one emit per stroke, verified by `test_canvas_emits_mask_modified`).
- D-12 compliance: both new modules say "reimplemented patterned after MangaCleaner_GPU"; neither says "copied"/"vendored from MangaCleaner_GPU".
- Full suite 69 passed (39 prior + 30 new). No regressions vs plans 01-01/01-02/01-03.
