# Phase 7: Typesetting (TRAN-02) — Pattern Map

**Mapped:** 2026-08-10
**Files analyzed:** 21 (2 new source + 8 modified source + 5 new test + 6 modified test)
**Analogs found:** 20 / 21

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `core/text_style.py` (NEW — or same-module as PageBox; planner picks) | model | CRUD | `core/box_model.py` `PageBox` (:53-178) | exact |
| `gui/text_renderer.py` (NEW) | utility | transform | `gui/box_item.py` `refresh_text_overlay` (:487-565) + `gui/canvas.py` numpy↔QImage bridges (:622-661) | partial (new territory) |
| `core/box_model.py` (MOD — style field + copy() detach) | model | CRUD | self — `PageBox.copy()` (:166-178) | exact (self) |
| `gui/box_item.py` (MOD — overlay rework, vertical, effects) | component | transform | self — `refresh_text_overlay` (:487-565), `_current_focus_text` (:720-746), constants (:102-122) | exact (self) |
| `gui/canvas.py` (MOD — multi-select, grouped move/delete) | component | event-driven | self — `_select_and_begin_move` (:1841-1867), `boxes_snapshot` (:1710-1746), `_remove_box` (:2013-2027), `mousePressEvent` (:979-1059) | exact (self) |
| `gui/inspector_panel.py` (MOD — styling section, Mixed, live vertical) | component | event-driven | self — `load_box` (:220-281), `connect_commit_handlers` (:320-344), no-op guards (:351-372) | exact (self) |
| `gui/main_window.py` (MOD — actions, style-commit routing) | controller | request-response | self — `_build_file_menu` (:296-445), `_refresh_action_states` (:966-1112), `_inspector_commit_pre/post` (:2794-2834), `export_page` (:4534-4575) | exact (self) |
| `core/project_io.py` (MOD — style field in `.mas`) | service | CRUD | self — `pagebox_to_json` (:182-206), `json_to_pagebox` (:209-271), `_coerce_int` (:79-91) | exact (self) |
| `core/ocr_export.py` (MOD — style block in `_ocr.json`) | service | CRUD | self — `build_page_ocr_json` (:121-182), `ocr_json_target_dir` (:199-212) | exact (self) |
| `tests/test_core/test_text_style.py` (NEW) | test | — | `tests/test_payload_aliasing.py` (Pitfall 8 guards) + `tests/test_core/test_box_model.py` | exact |
| `tests/test_core/test_typeset_layout.py` (NEW) | test | — | `tests/test_core/test_image_ops.py` (pure-function layout tests) | role-match |
| `tests/test_core/test_typeset_effects.py` (NEW — QImage pixel asserts) | test | — | `tests/test_core/test_image_ops.py` (qapp QImage/QFontMetrics) | role-match |
| `tests/test_core/test_typeset_bake.py` (NEW — composite + placement) | test | — | `tests/test_core/test_ocr_export.py` (placement rule tests) | exact |
| `tests/test_gui_inspector_styling.py` (NEW) | test | — | `tests/test_gui_boxes.py` (qtbot + `@pytest.mark.gui` + importorskip) | exact |
| `tests/test_core/test_box_model.py` (MOD) | test | — | self | exact (self) |
| `tests/test_core/test_history_boxes.py` (MOD — style undo regression) | test | — | self + `tests/test_payload_aliasing.py` | exact |
| `tests/test_core/test_project_io.py` (MOD — style round-trip + legacy) | test | — | self | exact (self) |
| `tests/test_core/test_ocr_export.py` (MOD — style block shape) | test | — | self | exact (self) |
| `tests/test_gui_boxes.py` (MOD — multi-select/group tests) | test | — | self | exact (self) |
| `tests/test_gui_export.py` (MOD — bake action test) | test | — | self | exact (self) |

---

## Pattern Assignments

### `core/text_style.py` (model, CRUD) — NEW

**Analog:** `core/box_model.py` `PageBox` — the composition dataclass discipline this phase must mirror (D-14 anti-pattern: style composes, never subclasses vendored `Box`/`TextBlock`).

**Module header / import pattern** (box_model.py:38-44):
```python
from __future__ import annotations

import copy as _copy
from dataclasses import dataclass, replace
from typing import Optional

from panelcleaner.structures import Box
```

**Dataclass shape to mirror** (box_model.py:53-94) — plain `@dataclass` with defaults, module-level string constants as the source of truth. The `TextStyle` field defaults (per RESEARCH Code Example 1) mirror the Phase 4 overlay look: `font_family="Liberation Sans"`, `color="#e8e8ea"`, `auto_fit=True`, `outline={"enabled": True, "color": "#0b0b0e", "width_px": 2.0}`, glow/shadow OFF (box_item.py:102-104 are the current hardcoded values).

**Copy-detach discipline (Pitfall 8 — the load-bearing pattern).** `PageBox.copy()` (box_model.py:166-178) currently detaches ONLY the payload; Phase 7 extends it to also detach `style`:
```python
# box_model.py:166-178 (verbatim, pre-change)
def copy(self) -> "PageBox":
    """Return a NEW ``PageBox`` with a detached payload (RESEARCH Pitfall 8). ..."""
    return replace(self, payload=_copy.copy(self.payload))
# Phase 7 change (RESEARCH Pitfall 1 / Code Example 1):
def copy(self) -> "PageBox":
    return replace(self, payload=_copy.copy(self.payload), style=_copy.copy(self.style))
```

**`to_dict`/`from_dict` serialization pattern** — mirror the hand-picked-field projection discipline of `pagebox_to_json` (project_io.py:182-206: plain dict, no `TextBlock.to_dict()` calls) and the V5 load coercion of `json_to_pagebox` (project_io.py:209-271: every numeric int()-coerced, unknown keys ignored). `from_dict(None)` → defaults (Pitfall 8 — old `.mas`/`_ocr.json` files lack the style block).

**Setters pattern** (box_model.py:96-163) — `_ensure_payload()`-style single centralized guard; the style setters should never mutate in place; always assign a fresh instance via `dataclasses.replace` (RESEARCH Pitfall 1).

---

### `gui/text_renderer.py` (utility, transform) — NEW

**No exact analog exists** (no shared renderer in the repo today). Closest analogs, used jointly:

**Analog A: `box_item.py` `refresh_text_overlay` (:487-565)** — the existing plain-text style+fit machinery the renderer generalizes:
```python
# box_item.py:509-559 (verbatim excerpt — the QTextCharFormat merge pattern)
self._text_overlay.setPlainText(text)          # ASVS V5: PLAIN text, never setHtml
doc = self._text_overlay.document()
...
inner_w = max(1.0, self.rect().width() - 2.0 * inset)
inner_h = max(1.0, self.rect().height() - 2.0 * inset)
self._text_overlay.setTextWidth(inner_w)
...
for _ in range(_OVERLAY_FIT_MAX_ITERS):        # bounded fit loop (D-15 Auto-fit)
    if target_vp <= _OVERLAY_FIT_FLOOR_VP:
        break
    font = QFont(_OVERLAY_FONT)
    font.setPointSizeF(target_vp / zoom)
    fmt = QTextCharFormat()
    fmt.setFont(font)
    fmt.setTextOutline(QPen(_OVERLAY_OUTLINE.color(), 2.0 / zoom))
    fmt.setForeground(QBrush(_OVERLAY_FILL))
    cursor = QTextCursor(doc)
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.mergeCharFormat(fmt)
    if doc.size().height() <= inner_h:
        break
    target_vp *= _OVERLAY_FIT_STEP
```
Fit-loop constants to preserve as the Auto-fit mode (box_item.py:116-122): `_OVERLAY_BOX_REF_DIM = 100.0`, `_OVERLAY_FIT_MAX_ITERS = 12`, `_OVERLAY_FIT_STEP = 0.9`, `_OVERLAY_FIT_FLOOR_VP = 5.0`, `_OVERLAY_INSET = 2.0`. The [10,28] clamp + `2/zoom` viewport outline (box_item.py:108/535/552) are SUPERSEDED for opaque text by scene-px style sizing (RESEARCH Pattern 1 note).

**Analog B: `canvas.py` numpy↔QImage bridges (:622-661)** — the bake compositor needs the same detached conversion discipline:
```python
# canvas.py:660-661 — MANDATORY .copy() detach (Pitfall 2)
arr = ...reshape(h, w, 3)
return arr.copy()
```
Note the 4-byte scanline padding handling (:643-659: `bytes_per_line` vs `w*3` — CR-08 lesson) — the bake's `QImage`→numpy conversion must replicate it or reuse `get_image_numpy`-style code. `mask_editor.numpy_binary_to_mask_qimage` (:194) is the other in-repo bridge.

**Module shape:** pure functions `layout(text, style, box_rect, vertical) -> LayoutResult` + `paint(painter, layout_result, style)`, Qt-imports-only (no widget/main-window deps — RESEARCH core/ discipline: Qt text APIs cannot live in `core/`). Imports mirror `box_item.py:48-62` (PySide6.QtCore/QtGui only). Vertical classification constants from RESEARCH Common Operation 2: `_ASCII_ROTATE = set(chr(i) for i in range(0x21, 0x7F))`, `_ROTATE_EXTRA = {"「","」","『","』","（","）","《","》","〈","〉","【","】","—","…","～","-","(",")"}`, `_ALIGN_CENTER = {"。","．","，","、","·","：","；","！","？"}`. Rotated-run paint per RESEARCH Common Operation 3: `painter.save(); painter.translate(x, y); painter.rotate(90); painter.drawText(0, 0, run); painter.restore()`. Outline via `QPainterPath.addText` + `strokePath` (Common Operation 4); glow/shadow via silhouette alpha + numpy stack blur + `CompositionMode_DestinationOver` (Common Operation 5).

**Performance discipline (04-08 RC-1):** layout + effect pixmap caches keyed `(text, style, box_rect, vertical)`; reposition never re-layouts (box_item.py:566-580 is the setPos-only precedent).

---

### `core/box_model.py` (model, CRUD) — MODIFY

**Analog:** self. Change sites:
1. Add `style: Optional["TextStyle"] = None` field next to the Phase 4 peer fields (:92-94), with the D-15-seam-style docstring convention (:87-89: `# D-15 seam: per-box mask (DEFERRED — later phase)`).
2. `copy()` (:166-178) — extend to detach style (see `core/text_style.py` section above).
3. `boxes_snapshot()` in canvas.py (:1710-1746) constructs fresh `PageBox`es per item — it MUST also forward `style=item.pagebox.style` or style edits will drop on every snapshot/restore round-trip (Pitfall 1 mirrored for style).

**V5 note:** `set_translation`/`set_recognized_text` (:111-149) stay untouched — Phase 7 does not change text setters.

---

### `gui/box_item.py` (component, transform) — MODIFY

**Analog:** self. The overlay child (:340-343) and its refresh path (:487-608) are the render surface D-01/D-14/D-15 rebuild.

**Overlay construction pattern** (:340-349) — the custom-painted replacement child inherits this shape:
```python
self._text_overlay = QGraphicsTextItem(self)
self._text_overlay.setZValue(_TEXT_OVERLAY_Z)      # 120 — below handles z=150, above box z=100
self._text_overlay.setFont(_OVERLAY_FONT)
self._text_overlay.setVisible(False)
self._text_overlay_visible = True                  # T toggle state (D-12)
self._overlay_zoom = 1.0
```

**D-04 current-focus rule — reuse verbatim for both canvas and bake** (box_item.py:720-746, `_current_focus_text`): translation when present (`getattr(payload, "translation", "")`), else recognized (`payload.text` str/list-aware, `.strip()`), `""` when neither. The bake calls this same logic (RESEARCH Common Operation 7 `current_focus_text(pb)`).

**T toggle / vertical flag plumbing** (:670-686 `set_text_overlay_visible`, :591-608 `apply_overlay_zoom` with the `zoom <= 0 → 1.0` guard) — the vertical mode switch (D-13) follows the same "store flag + refresh" pattern; `apply_overlay_zoom`'s refresh call may be superseded by scene-px sizing (RESEARCH Pattern 1 note — planner confirms in UI-SPEC pass).

**Text inset discipline** (:582-589 `_overlay_inset` = `pen().widthF()/2 + _OVERLAY_INSET`) — one formula shared by position + wrap width; the renderer takes the same inner-rect approach (`box_rect` minus insets).

---

### `gui/canvas.py` (component, event-driven) — MODIFY

**Analog:** self. Multi-select (D-08/D-09) extends the existing single-select state machine.

**Selection entry point** — `mousePressEvent` dispatch (:1024-1059). Phase 7 changes the BoxItem branch (:1048-1051) for Shift+click toggle (no clear) vs plain click (clear others + arm group move), and the empty-canvas branch (:1056-1059) already deselects — extended to `clearSelection()` for the multi case:
```python
# canvas.py:1043-1059 (verbatim excerpt — current behavior)
item = self._box_item_at(scene_pos)
if isinstance(item, CornerHandle):
    self._begin_resize(item, scene_pos); event.accept(); return
if isinstance(item, BoxItem):
    self._select_and_begin_move(item, scene_pos); event.accept(); return
if event.modifiers() & Qt.KeyboardModifier.AltModifier:
    self._begin_create_box(scene_pos); event.accept(); return
self._deselect_box()   # empty canvas: deselect + fall through to mask tool
```

**Grouped move — ONE snapshot, delta to all selected** (extends `_select_and_begin_move` :1841-1867 + `mouseMoveEvent` :1149-1161 + `mouseReleaseEvent` :1203-1218). RESEARCH Common Operation 6 spells the change; the existing arm-time snapshot + WR-04 delta-check patterns are copied verbatim:
```python
# canvas.py:1854-1867 (verbatim excerpt — current single-box arm)
item.setSelected(True)
self._moving_box = item
r = item.rect()
self._move_anchor_box_pos = QPointF(r.x(), r.y())
self._move_start_rect = QRectF(r)                      # WR-04: no-drag no-op gate
self._box_drag_anchor = scene_pos
self._boxes_interaction_start_snapshot = self.boxes_snapshot()  # CR-01: PRE-state
self.viewport().grabMouse()
```
Move commit (:1209-1218) emits `boxes_modified.emit(before)` ONCE only when `_mb.rect() != self._move_start_rect` — group move keeps this shape with the before-state captured at arm time (already full-list; `boxes_snapshot()` :1710-1746 needs the style-forwarding change listed under `core/box_model.py`).

**Grouped delete** — the Delete/Backspace handler (:1470-1475) loops `selectedItems()`; `_remove_box` (:2013-2027) is the per-item removal template (silent, captures pre-delete snapshot, emits once) — the group version captures ONE snapshot then removes all (Phase 3 D-12 "silent + undo recovers").

**Single-box resize gate** (RESEARCH Open Q6): `_begin_resize` (:1869-1880) only arms when the hit item is a `CornerHandle`; Phase 7 gates to exactly-one-selected.

**Text overlay toggle plumbing** (:1669-1691) — `set_text_overlay_visible_flag`/`toggle_text_overlay` unchanged; bake-placement state (`geometry_altered`) is read off `ImageFile` (see Shared Patterns).

---

### `gui/inspector_panel.py` (component, event-driven) — MODIFY

**Analog:** self. The D-05 styling section extends the existing QFormLayout + class-scope-Signal + follower pattern.

**QSS to extend** (inspector_panel.py:64-89 `_INSPECTOR_QSS`) — add `QFontComboBox`, `QDoubleSpinBox`, `QComboBox`, `QToolButton` rows reusing the same tokens (`#2d2d33` bg, `#3a3a42` border, `#e8e8ea` fg, `:disabled` → `#25252b`/`#6a6a72`).

**Class-scope Signal declarations** (:142-146, verbatim):
```python
translation_changed = Signal(str)
recognized_edited = Signal(str)
bubble_no_changed = Signal(int)
vertical_changed = Signal(bool)
```
Phase 7 adds e.g. `style_font_changed = Signal(str)`, `style_size_changed = Signal(float)`, `style_color_changed = Signal(str)`, `style_align_changed = Signal(str, str)`, `style_effect_changed = Signal(str, dict)`, `style_auto_fit_changed = Signal(bool)` (spelling is planner discretion — one signal per commit-able control).

**load_box population discipline** (:220-281): every widget populated with `blockSignals(True)` around `setValue`/`setChecked`, then the WR-01 loaded-value recorded (`self._loaded_*` — :212-214, :256, :266). The styling section mirrors this per control AND computes the D-10 common-value set across the multi-selection (all-equal → value; differing → "Mixed" sentinel; sentinel never leaves the widget layer — RESEARCH Pitfall 7). `clear()` (:283-307) + `_set_fields_enabled` (:309-317) extend to the new controls; multi-select disables the text fields while the styling section stays enabled (D-10).

**commit wiring** (:320-344 `connect_commit_handlers`) + **no-op guards** (:351-372 `_emit_*_if_changed` comparing against `_loaded_*`) — every new styling control gets the same WR-01 no-op guard so an unchanged focus cycle never pushes a no-op BOXES snapshot (Pitfall 7).

**Live vertical checkbox (D-13):** `vertical_check` (:199-203) currently writes metadata only + carries the "Coming soon" tooltip — remove the tooltip, keep the toggle commit path but route it through the overlay refresh (RESEARCH Pitfall 9: toggle must re-render the overlay).

---

### `gui/main_window.py` (controller, request-response) — MODIFY

**Analog:** self. Four change sites:

**1. Action creation** — File menu (:296-445). The bake action copies the `action_export_page` shape (:382-385):
```python
self.action_export_page = QAction("Export Page\u2026", self)
self.action_export_page.setShortcut(QKeySequence("Ctrl+E"))
self.action_export_page.triggered.connect(self.export_page)
self.action_export_page.setEnabled(False)
```
New: `action_export_typeset = QAction("Export Typeset Page\u2026", self)` placed next to Export Page in `_build_file_menu`; shortcut per RESEARCH Open Q5 (`Ctrl+Alt+E` recommended — Pitfall 4: Ctrl+E :383, Ctrl+Shift+E :658, Ctrl+- :500, Ctrl++ :496, Ctrl+0/1 all taken; Ctrl+A and Ctrl+= are verified free — Select All Boxes + Increase Font Size). Select All Boxes (Ctrl+A) + Size +/- (Ctrl+= / Ctrl+Shift+-) actions follow the same QAction shape; the zero-arg-lambda `triggered.connect` rule (main_window.py:315-327 G-05-1) applies to every new action.

**2. `_op_running` gate + `_refresh_action_states`** (:966-1112) — bake/select-all/size actions join the pattern:
```python
# main_window.py:1040 — the gate shape
self.action_export_page.setEnabled(page_open and not self._op_running)
```
Phase 7 adds: `action_select_all_boxes` (page_open + box_count>0 + not _op_running — mirrors :1079-1081), `action_export_typeset` (page_open + not _op_running — mirrors :1091-1093), size +/- (page_open + box_selected + not _op_running — mirrors :1067-1069).

**3. Style-commit routing** — the ONE-snapshot commit discipline already exists: `_inspector_commit_pre` (:2794-2819) captures the pre-edit snapshot AND detaches payloads push-side (Pitfall 8), `_inspector_commit_post` (:2821-2834) refreshes overlay + badge + emits `boxes_modified.emit(self._boxes_interaction_start_snapshot)` + re-loads the panel. Style commits for ALL selected boxes reuse this exact pair (D-10: one style commit = one snapshot + one overlay refresh); the handlers iterate the selected set (`self.canvas._selected_box()` → selectedItems() for multi).

**4. Undo flash naming** — `_undo_op_label` (:2907-2923) / `_undo_op_label_for_result` (:2937-2975). The `"boxes"` kind currently labels "box edit" (:2921-2922); group ops need op-name resolution — extend the `kind_or_op` set with "move"/"style"/"delete" group names (06-WR-01 geometry-op-name pattern; `_record_geometry_op_name` :2925-2935 is the precedent for recording op names at push time).

**5. Bake handler** — mirrors `export_page` (:4534-4575): `_op_running` guard first, then `_snapshot_current_page()` flush (the `_export_ocr_json` precedent :4605), `canvas.get_image_numpy()` for the page copy, renderer composite per box (D-04 text rule), `save_image_optimized(image_rgb, dest, original=page_path)` (:4575), D-03 placement via `ocr_json_target_dir(page_path.parent, imf.geometry_altered)` (:4621) → `<stem>_typeset.png`, save-failure critical dialog (T-05-12 copy, :4637-4645), `_show_transient_status` flash (:4646).

---

### `core/project_io.py` (service, CRUD) — MODIFY

**Analog:** self. The style field joins the existing PageBox projection.

**Write side** — `pagebox_to_json` (:182-206) gains `"style": pb.style.to_dict() if pb.style is not None else None` in the returned dict (:191-206). Hand-picks fields; NEVER writes mask/std_dev (D-15 seam, :184-188) — style is the new projected field.

**Load side** — `json_to_pagebox` (:209-271) gains an OPTIONAL style read with V5 coercion:
```python
# project_io.py:224-232 (verbatim — the required-key validation style)
if not isinstance(d, dict):
    raise ProjectFormatError("pagebox data must be a JSON object")
try:
    box_vals = d["box"]; origin = d["origin"]; ...
except KeyError as exc:
    raise ProjectFormatError(f"pagebox missing required key: {exc}") from exc
```
`"style"` is NOT a required key (Pitfall 8 — legacy `.mas` files lack it): `style_raw = d.get("style")` → `TextStyle.from_dict(style_raw)` (returns defaults when absent/None). The `_coerce_int` V5 discipline (:79-91) is the template for `TextStyle.from_dict`'s numeric clamps.

---

### `core/ocr_export.py` (service, CRUD) — MODIFY

**Analog:** self. The D-07 style block extends the published D-19 block dict.

**Version + shape anchors:**
```python
# ocr_export.py:69 (verbatim)
OCR_JSON_VERSION = "1"
# ocr_export.py:164-176 (verbatim — the block dict the style block joins)
blocks.append({
    "box": list(pagebox.box.as_tuple),  # [x1, y1, x2, y2]
    "vertical": payload.vertical if payload is not None else False,
    "text": text,
    "translation": (payload.translation or "") if payload is not None else "",
    "bubble_no": pagebox.bubble_no,  # None -> JSON null (04-10 rule)
    "origin": pagebox.origin,  # DETECTED / USER strings (box_model)
    "lines": lines,
})
```
Phase 7 adds `"style": pagebox.style.to_dict() if pagebox.style is not None else None` at BLOCK level (Pitfall 6: ONE spelling — `TextStyle.to_dict()` — shared with `project_io`; per-box flat style, D-06). Version policy: bump to `"2"` OR keep `"1"` with additive keys — the planner picks once and pins under test (RESEARCH Open Q4/A5; `test_style_block_shape` pins the exact JSON).

**Placement rule for the bake sidecar** — `ocr_json_target_dir` (:199-212) is the D-22 shape D-03 mirrors verbatim:
```python
# ocr_export.py:210-212 (verbatim)
if geometry_altered:
    return source_dir / "cleaned"
return source_dir
```
`default_ocr_json_path` (:215-222) is the `<stem>_ocr.json` template → `<stem>_typeset.png` (suffix is the phase's output-sidecar spelling; planner pins it).

---

### Test files

**`tests/test_core/test_text_style.py` (NEW)** — mirror `tests/test_payload_aliasing.py` structure (:18-32: `pytest.importorskip("PySide6")` where needed, module-level `@pytest.mark.unit`, `_pagebox_with_text`-style builders):
```python
# test_payload_aliasing.py:36-65 (verbatim excerpt — the Pitfall 8 guard shape)
@pytest.mark.unit
def test_pop_boxes_undo_restores_pre_edit_text() -> None:
    history = HistoryManager(limit=20)
    pb = _pagebox_with_text("before")
    history.push_boxes_state([pb])
    pb.payload.text = "after"
    restored = history.pop_boxes_undo(current_boxes=[pb])
    ...
    assert restored_pb.payload.text == "before"
    assert restored_pb.payload is not pb.payload
```
New guards: `test_style_copy_detaches` (mutate live style after push → pop restores pre-edit style), `test_style_undo_restores_previous_style` (RESEARCH Pitfall 1), `to_dict`/`from_dict` round-trip + V5 clamping (size 1..1024, widths/radii 0..256, opacity 0..1).

**`tests/test_core/test_typeset_layout.py` / `test_typeset_effects.py` (NEW)** — pure-function + QImage-pixel tests under pytest-qt `qapp`; header mirrors `tests/test_core/test_image_ops.py` (module-level importorskip, `@pytest.mark.unit`). Layout tests assert pure geometry (wrap at inner width, alignment, vertical classification membership, RTL column order, rotated advance uses height not width — RESEARCH Pitfall 3); effect tests render to QImage and assert pixels (outline ring color, glow halo alpha outside glyph bbox, shadow offset, effect padding).

**`tests/test_core/test_typeset_bake.py` (NEW)** — composite-pixel tests + placement-rule tests. Placement tests mirror `tests/test_core/test_ocr_export.py`'s `test_*_target_dir` shape (pristine → source dir, altered → `cleaned/`, dir created if missing) + the `save_image_optimized` writer contract (PNG compress_level=9 / JPG quality=95 + DPI preserved, image_io.py:95-104).

**`tests/test_gui_inspector_styling.py` (NEW)** — mirror `tests/test_gui_boxes.py` header (:17-43: `pytest.importorskip("PySide6")`, `@pytest.mark.gui`, `qtbot`, `_solid_pixmap` helper :45-51, `_scene_with_box` :54-59, real `EditorCanvas`/`MainWindow` integration). The `RecordingSignal` class in `tests/test_core/conftest.py` (:115-129) is the signal-capture precedent for asserting ONE `boxes_modified` emit per style commit.

**Extended files** — `test_box_model.py` (style field defaults), `test_history_boxes.py` (style undo), `test_project_io.py` (style round-trip + `test_legacy_mas_without_style_loads_with_defaults` — Pitfall 8), `test_ocr_export.py` (`test_style_block_shape`), `test_gui_boxes.py` (`test_multi_select_*`, `test_group_move_one_undo`, `test_resize_single_box_only`, `test_vertical_checkbox_live`, `test_size_plus_minus_actions`, `test_group_move_no_relayout`), `test_gui_export.py` (`test_typeset_export_action`). All follow the in-file fixture/assert conventions of their target files.

---

## Shared Patterns

### 1. Pitfall 8 — style/payload detachment across undo snapshots
**Source:** `box_model.py:166-178` (`PageBox.copy()` → `replace(self, payload=_copy.copy(...), style=_copy.copy(...))`) + `main_window.py:2794-2819` (`_inspector_commit_pre`: push-side `pb.payload = copy.copy(pb.payload)` loop) + `history_manager.py:297-321` (`_materialize_snapshot`: `m.copy() if hasattr(m, "copy") else m`).
**Apply to:** `core/text_style.py`, `core/box_model.py`, all style-commit handlers in `main_window.py`, `canvas.boxes_snapshot` (:1710-1746 — must forward `style` into the fresh PageBox). Regression guard: extend `tests/test_payload_aliasing.py`-style tests.

### 2. BOXES undo — ONE snapshot per op, PRE-state payload
**Source:** `canvas.py:169` (`boxes_modified = Signal(list)` — payload is the PRE-mutation snapshot), `canvas.py:1863` (`_boxes_interaction_start_snapshot = self.boxes_snapshot()` at arm time), `canvas.py:1210-1215` (move commit emits once, WR-04 delta-check), `main_window.py:2741-2776` (`_on_boxes_modified` pushes via `history.push_boxes_state` + reloads the Inspector; suppressed via `_suppress_boxes_push` during restore).
**Apply to:** grouped move/delete (D-09), style commits (D-10) — every group/style op emits `boxes_modified` exactly once with the before-state; one Ctrl+Z reverses the whole group.

### 3. Pitfall 2 — `.copy()` buffer discipline on every numpy↔QImage bridge
**Source:** `canvas.py:660-661` (mandatory `arr.copy()` detach), `canvas.py:679-684` (QImage `.copy()`-detached before storage), `image_io.py:65-72` (`(H,W,3)` uint8 pre-validation).
**Apply to:** the bake compositor (works on a detached page copy, never the live canvas image — RESEARCH Pattern 5), `text_renderer.py` effect silhouette conversions.

### 4. `_op_running` gate + `_refresh_action_states`
**Source:** `main_window.py:4549` (`if self._op_running: return` at every export handler top), `main_window.py:966-1112` (the central enablement table — every new action joins it with `page_open and not self._op_running` (+ selection/box-count predicates)).
**Apply to:** `action_export_typeset`, `action_select_all_boxes`, size +/- actions. Bake runs INLINE (A4 — sub-second single-page composite); Worker (`worker_thread.py:86-120`, `Abort` :80-83, auto-injected `progress_callback`/`abort_flag`) is only needed if a batch typeset export is later added.

### 5. ASVS V5 — plain-text rendering, no rich-text injection
**Source:** `box_item.py:509` (`self._text_overlay.setPlainText(text)` — never `setHtml` on OCR/translation text), `inspector_panel.py:185/190` (`setAcceptRichText(False)`), the `QTextCharFormat` merge pattern (box_item.py:550-556).
**Apply to:** `text_renderer.py` (QTextLayout plain runs only — both orientations), all styling widgets. Styled text is untrusted: `TextStyle.from_dict` type-checks + clamps every numeric (project_io `_coerce_int` :79-91 shape).

### 6. D-10 current-focus rule — the D-04 bake content contract
**Source:** `box_item.py:720-746` (`_current_focus_text`: translation when present, else recognized, else `""`).
**Apply to:** canvas overlay AND bake — one function shared (RESEARCH Common Operation 7 calls it `current_focus_text(pb)`); boxes with neither render nothing.

### 7. `save_image_optimized` — the bake's writer (PROJ-02 contract)
**Source:** `image_io.py:47-107` — `(H,W,3)` uint8 validation, PNG `compress_level=9` / JPG `quality=95` + `progressive=True` + `optimize=True` (:95-104), mode/DPI preserved from `original=` (:79-89, malformed-original tolerated), `path.parent.mkdir(parents=True, exist_ok=True)` (:106).
**Apply to:** the bake export (D-02) — never write a new encode path (RESEARCH Don't-Hand-Roll).

### 8. D-22 state-dependent placement (mirrored by D-03)
**Source:** `ocr_export.py:199-212` (`ocr_json_target_dir`: `geometry_altered → source_dir/"cleaned"`, else source dir), read off `ImageFile.geometry_altered` (`image_file.py:99`) and the D-22 flag set at geometry-op apply (`main_window.py:1200/2274`).
**Apply to:** bake sidecar `<stem>_typeset.png` placement — pristine → beside source, geometry-altered → `cleaned/` (dir created if missing); the flush seam (`_snapshot_current_page` before reading state, main_window.py:4605) applies to the bake too.

### 9. Undo flash naming for group ops
**Source:** `main_window.py:2907-2923` (`_undo_op_label` — "mask edit"/"inpaint"/"box edit" kind labels), `main_window.py:2925-2935` (`_record_geometry_op_name` — op-name recorded at push time), `main_window.py:2937-2975` (`_undo_op_label_for_result` — multi-kind result prefers the recorded op name).
**Apply to:** grouped move/delete/style commits — record op names like "move 3 boxes"/"style 4 boxes"/"delete 2 boxes" at push time so the Ctrl+Z flash names the group op.

### 10. QFormLayout + class-scope Signal + WR-01 no-op-guard panel pattern
**Source:** `inspector_panel.py:142-146` (Signal declarations), :164-205 (QFormLayout rows), :220-281 (blockSignals population + `_loaded_*` memory), :351-372 (no-op guards).
**Apply to:** the D-05 styling section (font family/style/size/color/H+V alignment/effects + Auto-fit toggle + live vertical checkbox), the D-10 Mixed-state logic, `QFontComboBox`/`QColorDialog`/`QDoubleSpinBox` widgets (Don't-Hand-Roll).

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `gui/text_renderer.py` | utility | transform | No shared style→render module exists today — Phase 4's overlay is embedded in `BoxItem` and cannot render effects/vertical or serve the bake. Use the joint analog (`refresh_text_overlay` :487-565 + canvas numpy↔QImage bridges :622-661 + `image_ops.py` pure-module shape) plus RESEARCH Patterns 1-3 (tategaki classification, effects passes) as the contract. |

## Metadata

**Analog search scope:** `manga_ai_studio/core/*.py`, `manga_ai_studio/gui/*.py`, `tests/*.py`, `tests/test_core/*.py` (all read this session)
**Files scanned:** ~24 source + test files
**Pattern extraction date:** 2026-08-10
**Key line anchors verified this session:** box_model.py:53-94/96-163/166-178 · box_item.py:102-122/340-349/487-608/670-686/720-746 · canvas.py:169/248-264/622-661/979-1085/1149-1161/1203-1218/1454-1475/1599-1645/1669-1691/1710-1746/1773-1790/1804-1839/1841-1964/2013-2027 · inspector_panel.py:64-89/142-146/148-217/220-307/309-344/351-372 · main_window.py:296-445/584-675/966-1112/2741-2834/2880-2892/2907-2975/3605-3613/4534-4646 · history_manager.py:297-348/402-506 · image_io.py:47-107 · ocr_export.py:69/121-182/199-222 · project_io.py:79-91/182-271 · image_file.py:55-101 · worker_thread.py:50-120 · tests/conftest.py:18 · tests/test_payload_aliasing.py:18-106 · tests/test_gui_boxes.py:17-59 · tests/test_core/conftest.py:115-129
