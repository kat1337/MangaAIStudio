# Phase 6: Refinement & Polish (deferred fixes + full curve editor) — Pattern Map

**Mapped:** 2026-08-09
**Files analyzed:** 14 (2 new, 10 extended/modified, 1 deleted, 1 integration point)
**Analogs found:** 13 / 14

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `gui/curves_dialog.py` (NEW) | component (dialog + custom widget) | request-response + event-driven | `gui/levels_dialog.py` (full 247 lines) | exact (successor dialog) |
| `core/image_ops.py` (EXTEND) | model (pure numpy math) | transform | `image_ops.py:431-470` `levels_lut`/`levels_page` | exact (in-file) |
| `gui/main_window.py` (EXTEND) | controller | request-response | `main_window.py:1227-1274` `_on_levels` + `:1106-1188` `_apply_geometry_op` | exact (in-file) |
| `gui/canvas.py` (EXTEND) | component (view) | event-driven | `canvas.py:383` (set_image calls `_update_empty_state`) + `:277-279` hint trio | exact (in-file) |
| `gui/crop_dialog.py` (MOD) | component (dialog) | request-response | `gui/load_translations_dialog.py:120` (only existing dialog setFont) | role-match |
| `gui/resize_dialog.py` (MOD) | component (dialog) | request-response | same as above | role-match |
| `gui/load_translations_dialog.py` (MOD) | component (dialog) | request-response | itself (`:120` mono exception stays) | exact (in-file) |
| `gui/levels_dialog.py` (DELETE) | component (dialog) | request-response | — (replaced by curves_dialog) | — |
| `gui/tools_panel.py` (integration point, likely unchanged) | component (panel) | event-driven | `tools_panel.py:105-106, 206-221` (the QActionGroup to join) | exact |
| `tests/test_gui_curves_dialog.py` (NEW) | test | — | `tests/test_gui_image_dialogs.py` (full 377 lines) | exact (Levels tests migrate here) |
| `tests/test_core/test_image_ops.py` (EXTEND) | test | — | `tests/test_core/test_image_ops.py:352-410` `test_resize_and_levels` | exact (in-file) |
| `tests/test_gui_image_dialogs.py` (MOD) | test | — | itself (Levels tests move out; D-12 typography test lands) | exact (in-file) |
| `tests/test_gui_canvas.py` (EXTEND) | test | — | `tests/test_gui_canvas.py:206-217` `test_empty_state_heading` | exact (in-file) |
| `tests/test_gui_project.py` (EXTEND) | test | — | `tests/test_gui_project.py:273-286` `test_ctrl_o_opens_project_not_image` + `:309` `test_open_project_restores_session` | exact (in-file) |
| `tests/test_gui_crop_tool.py` (EXTEND) | test | — | `tests/test_gui_crop_tool.py:227-267` `test_crop_action_in_tools_menu` | exact (in-file, must EXTEND not replace) |

## Pattern Assignments

### `manga_ai_studio/gui/curves_dialog.py` (NEW — component, request-response + event-driven)

**Analog:** `manga_ai_studio/gui/levels_dialog.py` — the dialog it replaces (D-01). The black/white/gamma rows survive as the quick-access row; the collector+preview-driver skeleton is inherited wholesale.

**Imports pattern** (levels_dialog.py:26-41):
```python
from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)
```

**Dark QSS pattern** (levels_dialog.py:46-77) — `_DIALOG_QSS` module-level string: `QDialog { background: #232328; }`, labels `#e8e8ea`, spinbox `#2d2d33`/`#3a3a42` border, slider handle + sub-page accent `#00d4ff`, buttons `#2d2d33` with `QPushButton:default { border: 1px solid #00d4ff; }`. Curves adds rules for the QPainter widget only if needed (canvas-side painting is not QSS-styled).

**Collector contract** (levels_dialog.py:95-112, 244-247):
```python
def __init__(self, parent=None, page_image=None, preview_callback=None) -> None:
    super().__init__(parent)
    self.setWindowTitle("Levels")            # -> "Curves" (D-01)
    self.setObjectName("levels_dialog")      # -> "curves_dialog"
    self.setModal(True)
    self._page_image = page_image            # caller's detached pre-dialog image
    self.preview_callback = preview_callback
    self._updating = False                   # re-entrancy guard
    self.result_values: tuple[int, int, float] = (0, 255, 1.0)  # -> curves payload

def _on_apply(self) -> None:
    """Store the collected values and accept (no image mutation here)."""
    self.result_values = self._current_values()
    self.accept()
```

**Slider↔spin sync (loop-free)** (levels_dialog.py:164-169) — direct `valueChanged`→`setValue` links; Qt does not re-emit identical values, so no recursion guard needed. Reuse for slider↔endpoint and gamma↔midpoint sync (D-02/D-03), PLUS the `_updating`-guarded `_refresh` clamp (below).

**`_updating`-guarded clamp + preview driver** (levels_dialog.py:211-234) — the D-02/D-03 clamp mechanism (RESEARCH Pitfall 4: black max = white−1, white min = black+1; gamma defined as curve output at input 128):
```python
def _refresh(self) -> None:
    if self._updating:
        return
    self._updating = True
    try:
        black = self.black_spin.value()
        white = self.white_spin.value()
        self.white_slider.setMinimum(black + 1)
        self.white_spin.setMinimum(black + 1)
        self.black_slider.setMaximum(white - 1)
        self.black_spin.setMaximum(white - 1)
    finally:
        self._updating = False
    if self.preview_callback is not None:
        self.preview_callback(self._current_values())
```

**Gamma log-slider mapping** (levels_dialog.py:90-93, 190-208) — `GAMMA_MIN/MAX/STEPS` constants + `_gamma_to_slider`/`_slider_to_gamma` with `math.log`/`math.exp`; keep verbatim for the D-03 gamma row.

**CurveWidget (no existing analog — greenfield QPainter)** — closest in-repo painting code is `box_item.py` (QGraphicsItem paint() with QPainterPath, `_OVERLAY_FONT = QFont("Liberation Sans", 14)` at :104) and `canvas.py` QGraphicsScene items. Follow RESEARCH Common Operation 3 skeleton: `QWidget` subclass with `setFocusPolicy(Qt.FocusPolicy.StrongFocus)` (D-07), `paintEvent` constructs `QPainter(self)` + `setRenderHint(Antialiasing)`, `points_changed = Signal()` / `point_selected = Signal(int)` class signals, mouse handlers clamp to grid [0,255]² with x-order preservation, endpoints y-locked (D-04). No QWidget-with-paintEvent precedent exists — planner uses RESEARCH.md Common Operation 3 as the shape.

**Histogram (D-08)** — RESEARCH Don't-Hand-Roll: `np.histogram(image, bins=256, range=(0, 256))` computed ONCE in the dialog constructor from the detached `page_image` (Pitfall 2 — defensive `.copy()`; RESEARCH Pitfall 5). Luminance `0.299R+0.587G+0.114B` for the master (assumption A7).

---

### `manga_ai_studio/core/image_ops.py` (EXTEND — model, transform)

**Analog:** `image_ops.py:431-470` `levels_lut`/`levels_page` — the LUT pipeline `curve_lut`/`curves_page` land BESIDE (keep both; levels math stays tested at test_image_ops.py:352).

**LUT builder with T-05-07 backstop** (image_ops.py:431-450) — the discipline model for `curve_lut`:
```python
def levels_lut(black: int, white: int, gamma: float) -> np.ndarray:
    if not isinstance(gamma, (int, float)) or gamma <= 0:
        raise ValueError("gamma must be a positive number")
    lo = min(black, white)
    hi = max(black, white)
    lut = np.arange(256, dtype=np.float64)
    lut = (lut - lo) / max(hi - lo, 1)
    lut = np.clip(lut, 0.0, 1.0) ** (1.0 / gamma)
    return (lut * 255.0).round().astype(np.uint8)
```
`curve_lut` replaces the linear/gamma math with `np.interp` over sorted/deduped points, keeping: docstring discipline (input range, backstop guarantee, output contract), `ValueError` on bad input, `round().astype(np.uint8)` output. RESEARCH Common Operation 1 has the recommended shape verbatim.

**Geometry-free page apply** (image_ops.py:453-470) — the `curves_page` contract:
```python
def levels_page(image_rgb, black, white, gamma) -> np.ndarray:
    # levels is image-only: validate the image shape without a mask argument.
    if (image_rgb.ndim != 3 or image_rgb.shape[2] != 3
            or image_rgb.dtype != np.uint8):
        raise ValueError("expected (H,W,3) uint8 RGB")
    return levels_lut(black, white, gamma)[image_rgb].copy()
```
`curves_page(img, master_points, channel_points)` mirrors: same validation, fancy-index LUT apply, trailing `.copy()` (Pitfall 2). Composition `out_c = channel_lut_c[master_lut[v]]` per RESEARCH A1 (probe-test the order).

---

### `manga_ai_studio/gui/main_window.py` (EXTEND — controller, request-response)

**Analog (A):** `main_window.py:1227-1274` `_on_levels` — becomes `_on_curves` with the dialog swap. Copy verbatim including the b376f8a ordering (RESEARCH Pitfall 3 — MUST NOT regress):
```python
def _on_levels(self) -> None:
    if self._op_running or self._current_page_index() is None:
        return
    from manga_ai_studio.gui.levels_dialog import LevelsDialog   # -> curves_dialog

    base = self.canvas.get_image_numpy()
    if base is None:
        return
    base = base.copy()                                           # Pitfall 2
    dialog = LevelsDialog(
        self,
        page_image=base,
        preview_callback=lambda values: self.canvas.set_image_from_numpy_preview(
            image_ops.levels_page(base, *values), capture_original=False
        ),                                                       # -> curves_page(base, master, chans)
    )
    if dialog.exec() != QDialog.DialogCode.Accepted:
        self.canvas.set_image_from_numpy(base.copy())            # Cancel: silent exact restore
        return
    black, white, gamma = dialog.result_values

    # b376f8a: restore the detached pre-dialog base BEFORE _apply_geometry_op
    # so the undo before-state is the TRUE pre-op image (previews mutated the canvas).
    self.canvas.set_image_from_numpy(base.copy())

    def _transform():
        return image_ops.levels_page(base, black, white, gamma), None, None

    self._apply_geometry_op(
        "levels", geometry=False, transform_fn=_transform, flash="Levels applied."
    )   # -> op_name "curves", flash "Curves applied."
```

**Analog (B):** `main_window.py:1106-1188` `_apply_geometry_op` — reused unchanged (op_name="curves", geometry=False ⇒ `geometry_altered` NOT set — D-15/D-22).

**Rename surfaces (RESEARCH Runtime State Inventory):**
- `action_levels` (main_window.py:793-798, added to Tools menu at :824, gated in `_refresh_action_states` at :1090) → `action_curves` "Curves…" (Alt+T Image-section placement stays — D-01)
- `_undo_op_label` set (main_window.py:2888) — `("rotate", "crop", "levels", "resize")` → replace "levels" with "curves"
- Flash "Levels applied." → "Curves applied." (test assertions at test_gui_image_dialogs.py:196, 242 migrate)

**Analog (C) — D-10 toolbar fix:** the six window tool actions (main_window.py:710-753) gain `setCheckable(True)` + `self.tools_panel.tool_group.addAction(act)` per RESEARCH Common Operation 4. Copy the ToolsPanel checkable-action pattern (tools_panel.py:214-220 — `act.setCheckable(True)`, `act.setChecked(checked)`, `act.setData(tool)`, `self.tool_group.addAction(act)`) into the window action creation. Fix the false comment at `_make_tool_toolbar_button` (main_window.py:3106-3118). `set_active_tool` (main_window.py:3120-3138) already does `btn.setChecked(True)` with `blockSignals` — becomes functional once the default action is checkable. Research Pitfall 1 warning: window actions must NOT connect `toggled` (panel actions connect `toggled` at tools_panel.py:149-150; window `triggered` lambdas already call `set_active_tool`).

---

### `manga_ai_studio/gui/canvas.py` (EXTEND — component/view, event-driven)

**Analog (A) — D-09 one-liner:** `set_image` already calls `self._update_empty_state()` at the END of the display path (canvas.py:383); `_set_image_from_numpy` (canvas.py:710-767) is the only display path missing it. Add `self._update_empty_state()` before the final `return qimg` (line 767). Research Pitfall 1: the call is benign/idempotent on the preview path (`_update_empty_state` at canvas.py:1545-1575 only toggles visibility + calls `_refresh_empty_box_hint` when an image is present).

**Analog (B) — D-11 hint copy:** the empty-state hint text (canvas.py:277-279):
```python
self._empty_hint = QGraphicsTextItem(
    "File \u2192 Open Image\u2026 (Ctrl+O)   \u00b7   or drag files here"
)
```
must drop "(Ctrl+O)" or reference Open Folder (Ctrl+Shift+O) — exactly ONE Ctrl+O binding exists (main_window.py:310-311, `action_open_project`; the Ctrl+O contract is locked by `test_ctrl_o_opens_project_not_image`, test_gui_project.py:273-286). The body text "Open a single image or a folder of images to begin cleaning." (canvas.py:275) STAYS. Font styling pattern for the trio (canvas.py:285-293): heading `QFont("Segoe UI", 13)` DemiBold, body `QFont("Segoe UI", 11)` ≈14px, hint `QFont("Segoe UI", 10)` accent `#00d4ff`.

---

### `manga_ai_studio/gui/crop_dialog.py`, `resize_dialog.py`, `load_translations_dialog.py` (MOD — D-12 typography)

**Analog:** `load_translations_dialog.py:120` — the only existing dialog-level setFont: `self.paste_edit.setFont(QFont("Consolas", 10))` (mono exception stays). No app-wide font exists (theme.py sets palette only — verified via grep: no QFont in theme.py).

**14px Body pattern:** set the dialog font in `__init__` after `super().__init__(parent)`:
```python
self.setFont(QFont("Segoe UI", 11))   # ≈14px at 96 DPI (project ~1.33 pt→px convention)
```
Acceptance truth per RESEARCH A4: tests assert `QFontInfo(dialog.font()).pixelSize() == 14`. Apply to LevelsDialog→CurvesDialog (ships at 14px from birth), CropDialog, ResizeDialog, LoadTranslationsDialog (all four in one pass per RESEARCH Open Question 2 recommendation).

---

### `tests/test_gui_curves_dialog.py` (NEW — test)

**Analog:** `tests/test_gui_image_dialogs.py` — the Levels tests migrate here with the dialog.

**Fixture helpers** (test_gui_image_dialogs.py:43-73):
```python
def _window_with_page(qtbot, tmp_path, size=(60, 40)) -> MainWindow:
    folder = tmp_path / "chapter"
    folder.mkdir(parents=True, exist_ok=True)
    w, h = size
    PILImage.new("RGB", (w, h), color=(40, 80, 120)).save(folder / "page_01.png")
    pm = ProfileManager(tmp_path / "config")
    window = MainWindow(pm)
    qtbot.addWidget(window)
    window._load_folder(folder)
    QApplication.processEvents()
    return window

def _seed_mask_and_box(window) -> tuple[np.ndarray, PageBox]:
    # binary mask + one USER box under _suppress_boxes_push (no undo push)
```

**`_fake_exec` monkeypatch shape** (test_gui_image_dialogs.py:218-226) — the dialog lifecycle test template:
```python
def _fake_exec(dlg):
    dlg.black_spin.setValue(30)          # real user drags -> live preview fires
    dlg.white_spin.setValue(200)
    dlg.gamma_spin.setValue(1.0)
    dlg.result_values = (30, 200, 1.0)   # collector payload
    return QDialog.DialogCode.Accepted

monkeypatch.setattr(LevelsDialog, "exec", _fake_exec)   # -> CurvesDialog
window._on_levels()                                     # -> _on_curves
QApplication.processEvents()
```

**Assertion contract to carry over:**
- `test_levels_apply_pushes_one_entry` (test_gui_image_dialogs.py:200-253): ONE image-only entry (`len(history._image_undo) == 1`, mask/boxes stores 0), `geometry_altered is False`, flash text, `_original_image_numpy` re-baselined to post-op (D-14), Ctrl+Z (`window.on_undo()`) → pre-dialog image byte-identical + stack empty (b376f8a restore semantics)
- `test_levels_cancel_restores_exactly` (:174-196): Rejected → byte-identical restore, `not history.can_undo()`, no flash
- `test_levels_preview_no_baseline_poison` (:257-288): preview path never re-baselines Show Original
- `test_levels_defaults_and_clamp` (:145-170): defaults + clamp + preview never receives inverted map (the D-02/D-03 slider↔endpoint clamp tests mirror this)

**New curve-specific tests** (from RESEARCH Validation Architecture): defaults (Linear, endpoints fixed), preset apply (S-curve/Brighten/Darken = editable starting points), channel switch, point add/drag/double-click-delete, in/out spins, arrow nudge (Shift=10), Tab selection, gamma↔midpoint sync.

---

### `tests/test_core/test_image_ops.py` (EXTEND — test)

**Analog:** `tests/test_core/test_image_ops.py:352-410` `test_resize_and_levels` — the byte-exact LUT math test shape: `np.array_equal` against expected outputs, `flags["OWNDATA"]` + `not np.shares_memory` for Pitfall-2 detachment, `ValueError` assertions for bad input (see `test_crop_zero_area_dropped` style at :334). Add `curve_lut` identity-for-Linear, monotone S-curve, degenerate-input backstop (never NaN/out-of-range), clamp checks; `curves_page` composition-order probe (A1), validation errors, `.copy()` detach.

---

### `tests/test_gui_canvas.py` (EXTEND — D-09/D-11 regression)

**Analog:** `tests/test_gui_canvas.py:206-217` `test_empty_state_heading` — asserts text content and scene membership only (NOT transitions); the new D-09 test must drive a transition: `canvas.set_image_from_numpy(...)` on a canvas showing the empty state, then assert `not canvas._empty_heading.isVisible()` and (zero-box page) `canvas.empty_box_hint.isVisible()`. D-11 test: assert the hint text no longer contains "Ctrl+O" and matches the chosen wording.

---

### `tests/test_gui_project.py` (EXTEND — D-09 project-open regression)

**Analog:** `tests/test_gui_project.py:309` `test_open_project_restores_session` + `:273` `test_ctrl_o_opens_project_not_image`. The D-09 regression drives the project-open numpy path: `window._display_page_state(imf)` (main_window.py:2292-2302 → `canvas.set_image_from_numpy` → `_set_image_from_numpy` — the bug site) and asserts the empty-state trio stays hidden + the empty-box hint shows on a zero-box page. Must FAIL RED on current code.

---

### `tests/test_gui_crop_tool.py` (EXTEND — D-10 checked-state regression)

**Analog:** `tests/test_gui_crop_tool.py:227-267` `test_crop_action_in_tools_menu` — the toolbar-button lookup pattern (find QToolButtons by `btn.defaultAction().data() == ToolMode.X`) and the shortcut-emission pattern (find QShortcut by key, `shortcut.activated.emit()`). RESEARCH Pitfall 2: the existing test asserts `defaultAction().data()`, NOT `isChecked()` — EXTEND it (RED-gate the new `btn.isChecked()` assertions: matching button checked, all others unchecked, after V/B/R/L/E/G shortcut, menu trigger, and programmatic `set_active_tool`). Also `test_crop_is_sixth_exclusive_tool` (:187-223) shows the group-membership assertion shape: `action.actionGroup() is panel.tool_group` — extend to the window actions after the D-10 fix.

---

## Shared Patterns

### Collector + preview driver (Pitfall 9)
**Source:** `levels_dialog.py:95-179` + `_on_levels` (main_window.py:1227-1274)
**Apply to:** `curves_dialog.py` (entire dialog), `main_window.py` `_on_curves`
The dialog never mutates models; `preview_callback` drives the capture-suppressed canvas preview; Cancel = silent exact restore; Apply = ONE image-only IMAGE-stack entry via `_apply_geometry_op`; Show Original re-baselines post-op (D-14).

### b376f8a restore-before-Apply ordering
**Source:** `main_window.py:1261-1267` (comment + `self.canvas.set_image_from_numpy(base.copy())` before `_apply_geometry_op`)
**Apply to:** `_on_curves` — MUST NOT regress. Regression: `test_curves_apply_pushes_one_entry` asserts Ctrl+Z → byte-identical pre-dialog image, stack empty.

### LUT backstop discipline (T-05-07)
**Source:** `image_ops.py:431-450` (`levels_lut` — "an inverted map can never render")
**Apply to:** `curve_lut`/`curves_page`, slider↔endpoint sync clamps, gamma↔midpoint clamps (D-02/D-03). Degenerate inputs must never produce NaN, out-of-range indices, or an inverted map.

### Pitfall 2 `.copy()` detachment
**Source:** `image_ops.py:470` (`return ... .copy()`), `main_window.py:1246` (`base = base.copy()`), `canvas.py:755-760` (QImage buffer detach), test assertions `test_image_ops.py:365-367` (`flags["OWNDATA"]`, `not np.shares_memory`)
**Apply to:** every file — dialog `page_image`, preview base, histogram source (D-08), `curves_page` result, `_on_curves` base.

### `_updating` guard + clamp mechanism
**Source:** `levels_dialog.py:211-234`, `resize_dialog.py:183-206` (aspect lock)
**Apply to:** `curves_dialog.py` `_refresh` (bidirectional sync must be clamps, not free ranges — RESEARCH Pitfall 4).

### Dark dialog QSS (`_DIALOG_QSS`)
**Source:** `levels_dialog.py:46-77` (shared across crop/resize/load_translations with per-dialog widget rules)
**Apply to:** `curves_dialog.py` — same tokens (#232328 bg, #e8e8ea text, #00d4ff accent, #2d2d33 controls).

### Exclusive QActionGroup
**Source:** `tools_panel.py:105-106, 214-220` (`QActionGroup(exclusive=True)` + checkable actions)
**Apply to:** D-10 — the window tool actions join the panel's group. Warning (RESEARCH Pitfall 1): no `toggled` connects on window actions; panel already connects per-action at tools_panel.py:149-150.

### Test: byte-identical restore + one-entry assertions
**Source:** `test_gui_image_dialogs.py:174-253` (Cancel/Apply lifecycle trio)
**Apply to:** all Curves lifecycle tests in the new `test_gui_curves_dialog.py`.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `gui/curves_dialog.py` — the CurveWidget class | component (custom QPainter widget) | event-driven | No QWidget subclass with paintEvent exists in the codebase; closest are QGraphicsItem painters (box_item.py) and the mask-tool mouse dispatch (canvas.py). Planner uses RESEARCH.md Common Operation 3 skeleton + QPainter doc conventions |

## Metadata

**Analog search scope:** `manga_ai_studio/gui/` (levels_dialog, resize_dialog, crop_dialog, load_translations_dialog, main_window, canvas, tools_panel, theme), `manga_ai_studio/core/image_ops.py`, `tests/` (test_gui_image_dialogs, test_gui_canvas, test_gui_project, test_gui_crop_tool, test_core/test_image_ops)
**Files scanned:** 17 source files + 6 test files
**Pattern extraction date:** 2026-08-09
**Key contract lines (verbatim-verified):** `_on_levels` main_window.py:1227-1274 (incl. b376f8a restore at 1261-1267); `_apply_geometry_op` main_window.py:1106-1188; `levels_lut`/`levels_page` image_ops.py:431-470; `_set_image_from_numpy` canvas.py:710-767 (D-09 site, missing `_update_empty_state()`); hint copy canvas.py:277-279 (D-11 site); `_update_empty_state` canvas.py:1545-1575; tool actions main_window.py:710-753 + false comment at 3109-3111; `set_active_tool` main_window.py:3120-3138; `_make_tool_action` tools_panel.py:206-221; `_undo_op_label` main_window.py:2880-2896; Ctrl+O single binding main_window.py:310-311
