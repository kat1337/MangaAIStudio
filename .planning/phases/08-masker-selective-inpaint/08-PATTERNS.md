# Phase 8: Masker & Selective Inpaint - Pattern Map

**Mapped:** 2026-08-15
**Files analyzed:** 14 new/modified source files + 6 test files
**Analogs found:** 14 / 14 (2 partial — see "No Analog Found")

All paths are relative to repo root `C:\Src\Manga AI Studio`. Line numbers verified against the working tree on the mapping date.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `manga_ai_studio/gui/main_window.py` (`_on_detection_finished` + new slots) | controller | event-driven (worker result → mask/box state) | itself: `_build_detected_boxes` (:3901) + `on_page_selected` (:1664) | exact |
| `manga_ai_studio/gui/canvas.py` (3-plane mask model + `recompose_mask`) | component/state store | transform (derive composite from planes) | `canvas.set_mask` (:449-496) + `mask_editor.py` bridges | partial (new model; helpers reused) |
| `manga_ai_studio/gui/canvas.py` (`mousePressEvent` carve-out) | component | event-driven (input dispatch) | itself: current dispatch (:997-1107) | exact |
| `manga_ai_studio/core/detection_boxes.py` (NEW — headless box-build + mask-derivation core) | service/utility | batch transform (heatmap+blocks+boxes → per-box state + auto plane) | `core/image_ops.py` pure-function modules; `_build_detected_boxes` V5 loop (:3944-3970) | role-match |
| `manga_ai_studio/gui/tools_panel.py` (detection-settings section) | component | request-response (widget → signal → MainWindow slot) | brush-size row (:175-200) + slider/spin sync (:275-288) | role-match |
| `manga_ai_studio/gui/box_item.py` (inpaint border states) | component | event-driven (state → pen) | `_apply_origin_pen` (:549-566) / `_apply_look_for` (:626-639) | exact |
| `manga_ai_studio/core/box_model.py` (`inpaint_override` + `inpaint_state()`) | model | CRUD (dataclass field + pure state fn) | Phase 7 `style` field (:102-105) + `copy()` (:177-193) | exact |
| `manga_ai_studio/gui/inspector_panel.py` (override field) | component | request-response (commit signal → handler) | style-section rows (:442-465) + `connect_commit_handlers` (:1067-1147) | exact |
| `manga_ai_studio/core/batch_runner.py` (constrained masks + boxes) | service | batch | itself: detect branch (:149-156) | exact |
| `manga_ai_studio/core/project_io.py` (per-box field round-trip) | utility/serialization | file-I/O | `style` optional-key precedent (:182-280) | exact |
| `manga_ai_studio/core/image_file.py` (`raw_detected_mask` slot) | model | state retention | `mask`/`boxes`/`current_image` slots (:90-101) | exact |
| `manga_ai_studio/core/image_ops.py` (geometry-op field policy) | utility | transform | itself: `transform_box_payload` (:127-163) | exact (it IS the trap) |
| `panelcleaner/config.py` (`MaskerConfig` dilation field — optional) | config | file-I/O (INI round-trip) | itself: existing fields + export/import (:553-659) | exact |
| `manga_ai_studio/__main__.py` (startup profile load) | config | file-I/O | `_default_font_family` QSettings reader (main_window.py:1888-1897) | role-match |

Test files:

| Test File | Role | Analog |
|-----------|------|--------|
| `tests/test_core/test_masker_machinery.py` (NEW) | test (unit) | `tests/test_core/test_masker_vendor.py` import-tests; call contracts from RESEARCH §1 |
| `tests/test_gui_detection_boxes.py` (extend) | test (gui) | itself: harness (:47-88) |
| `tests/test_core/test_project_io.py` (extend) | test (unit) | itself: `test_legacy_mas_without_style_loads_with_defaults` (:175) |
| `tests/test_core/test_batch_runner.py` (extend) | test (unit) | itself: fake det_model pattern |
| `tests/test_core/test_box_model.py` (extend) | test (unit) | itself: copy()/field tests |
| `tests/test_gui_canvas.py` or new `test_gui_paint_under_boxes.py` (NEW/extend) | test (gui) | QTest press patterns at `zoom_reset()` (canvas.py:961) |

## Pattern Assignments

### 1. `manga_ai_studio/gui/main_window.py` — detection→mask seam rework (controller, event-driven)

**Analog:** itself — `_on_detection_finished` (:3863-3899) + `_build_detected_boxes` (:3901-4015) + `on_page_selected` (:1664-1850).

**The seam as it exists today** (main_window.py:3879-3897) — the reorder target. Currently the FULL heatmap is composited first, boxes built second:

```python
import numpy as np

mask = result["mask"]
if mask is None:
    self.status_bar_left.setText("Detection complete (no mask)")
    return
# numpy (H,W) uint8 -> QImage grayscale, copy-detached (Pitfall 2).
h, w = mask.shape[:2]
qimage = QImage(mask.data, w, h, w, QImage.Format.Format_Grayscale8)
self.canvas.set_mask(qimage.copy())
self.status_bar_left.setText("Detection complete")

if self.action_detect_boxes_mode.isChecked():
    blk_list = result.get("blocks") or []
    self._build_detected_boxes(blk_list)
```

New sequence per RESEARCH §3.2: build boxes FIRST (via the extracted headless core), retain the raw thresholded mask on the page, derive the auto plane, compute per-box std_dev, refresh border states. Mode OFF keeps the two lines above verbatim (D-03).

**Worker result contract — do not change** (:3792-3796): `mask_refined, blk_list = model.detect(image)` → `return {"mask": mask_refined, "blocks": blk_list}`. Phase 8 consumes both; no adapter/worker change.

**Gate ordering pitfall** — `_build_detected_boxes` Step 1 (:3929-3932) aborts on Cancel *after* which today's mask is already set. Under D-02 the new sequence must make the auto-plane derivation conditional on the box build not aborting (RESEARCH §3.2 item 6):

```python
detected_now, _user_now = self.canvas.box_origin_counts()
if detected_now >= 1:
    if not self._confirm_replace_boxes():
        return  # Cancel — no replace (D-04)
```

**Non-undoable baseline discipline** — keep detection seeding no history entries. `_suppress_boxes_push` guard (:3985-3989) and the Step 5 rationale (:3996-4008). The new `recompose_mask` must NOT emit `mask_modified` (mirrors `set_mask` emitting nothing; Pitfall 13-1).

```python
self._suppress_boxes_push = True
try:
    self.canvas.set_boxes(user_pageboxes, detected_pageboxes)
finally:
    self._suppress_boxes_push = False
```

**Per-page persistence seam to extend** (`on_page_selected`, :1703-1733 outgoing / :1785-1837 incoming) — the raw detected mask + any new plane state rides the identical outgoing-index rule (`_last_page_index`, NEVER `_current_page_index()` which has already flipped):

```python
outgoing_idx = self._last_page_index
if (
    outgoing_idx is not None
    and 0 <= outgoing_idx < len(self.image_files)
    and self.canvas.has_mask()
):
    # MANDATORY .copy(): detaches the QImage from the live canvas buffer
    self.image_files[outgoing_idx].mask = self.canvas.get_mask().copy()
```

**Live re-dilate slot (D-08)** — wire like `tools_panel.brush_size_changed` → `canvas.set_brush_size` (main_window.py:2697-2698): ToolsPanel `dilation_changed(int)` → MainWindow slot → recompute auto plane from retained raw mask → `canvas.recompose_mask()` → `refresh_box_inpaint_states()`. No worker, no model. Also reword `_confirm_replace_mask` copy (:4100-4104, "Your manual edits will be lost" is false under the layered model — Pitfall 13-3).

**Undo integration** — `_on_mask_modified` before-state machinery (:2827-2877) stays; `_pre_stroke_mask` becomes per-plane (manual plane for paint strokes, erase ledger for erase strokes). Override flips go through the grouped-commit shape below.

---

### 2. `manga_ai_studio/gui/canvas.py` — layered mask model + recompose (component, transform)

**Analog:** `set_mask` (:449-496) for the numpy→tinted-QImage bridge; `mask_editor.py` bridges for the composite rebuild.

**The bridge to reuse for `recompose_mask`** (canvas.py:477-496 — threshold, tint BGRA, copy-detach):

```python
mask_pixels = arr[:, :, 2] > 0  # R channel (BGRA byte order)
out = np.zeros((h, w, 4), dtype=np.uint8)
out[mask_pixels] = [0, 0, 255, 160]  # BGRA: red @ alpha 160/255~=0.63
tinted = QImage(out.data, w, h, w * 4, QImage.Format.Format_ARGB32)
tinted = tinted.copy()
self._mask = tinted
self.mask_item.setPixmap(QPixmap.fromImage(tinted))
```

The composite is `numpy_binary_to_mask_qimage((manual_bin | auto_bin) & ~erase_bin)` (mask_editor.py:194-211 — returns `.copy()`-detached QImage). Recompose at stroke-commit / detect / radius change / box change / override flip — never inside `mouseMoveEvent` (Pitfall 13-14). Keep `_mask` as the displayed attribute so `get_mask/has_mask/update_mask_display/apply_undo_mask` and the LaMa path (main_window.py:4204 `mask_to_numpy_binary(self.canvas.get_mask())`) are untouched.

**Eraser dual-write (Pitfall 13-11)** — eraser currently uses `CompositionMode_Clear` on the flat `_mask` (mask_editor.py:93-101). Under Option B an erase stroke must ALSO paint into the erase-ledger plane or it is lost on the next recompose:

```python
painter = QPainter(mask)
if eraser:
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    color = ERASER_PAINT_COLOR  # Qt.transparent
```

**`set_image` mask reset** (:390-397) — a new page reinitializes `_mask` transparent; the new planes must reset here too.

---

### 3. `manga_ai_studio/gui/canvas.py` — `mousePressEvent` carve-out (component, event-driven)

**Analog:** itself — the exact dispatch to restructure (:1040-1081).

**Current box branch** (canvas.py:1042-1081):

```python
if (
    self.box_layer.isVisible()
    and event.button() == Qt.MouseButton.LeftButton
):
    scene_pos = self._scene_pos(event)
    # Hit-test WITHOUT passing the view's zoom transform (BSP trap at zoom >= ~3.5;
    # cursor/preview overlays skipped) — _box_item_at handles both.
    item = self._box_item_at(scene_pos)
    if isinstance(item, CornerHandle):
        if len(self._scene.selectedItems()) == 1:
            self._begin_resize(item, scene_pos)
        event.accept()
        return
    if isinstance(item, BoxItem):
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._toggle_box_selection(item)
        else:
            self._select_and_begin_move(item, scene_pos)
        event.accept()
        return
    if event.modifiers() & Qt.KeyboardModifier.AltModifier:
        self._begin_create_box(scene_pos)
        event.accept()
        return
    # Empty canvas, no Alt: clear the WHOLE selection and FALL THROUGH
    self._clear_selection()
```

**The paint branch it must fall into** (:1098-1106):

```python
if (
    event.button() == Qt.MouseButton.LeftButton
    and self.current_tool not in (ToolMode.MOVE, ToolMode.CROP)
    and self._mask is not None
    and not self._mask.isNull()
):
    self._begin_paint(event)
    event.accept()
    return
```

Carve-out per RESEARCH §7.2: introduce `PAINT_TOOLS = {BRUSH, RECTANGLE, LASSO, ERASER}`; Alt-gate the box branch when a paint tool is active (Alt+handle resize with the same sole-selection gate, Alt+body select/move via `_select_and_begin_move`, Alt+empty create); no-Alt + paint tool → fall through so box bodies AND handles paint (MASK-06). Crop unchanged (CROP ∉ PAINT_TOOLS). Double-click (:1109-1137) has no tool gate — unchanged (D-16; note the first-press-paints-dot corner). Preserve the inline-editor guard (:1020-1028) FIRST and pan (:1030-1038) as-is. Do not touch `_box_item_at` (:2016-2038) — routing only.

---

### 4. `manga_ai_studio/core/detection_boxes.py` (NEW — service, batch transform)

**Analog:** the V5 loop inside `_build_detected_boxes` (main_window.py:3944-3970) — extract it headless; plus the `core/image_ops.py` module shape (pure functions, numpy/PIL only, no Qt, docstring-heavy, headless-testable).

**The loop to extract** (reads canvas pixmap for dims + QSettings for font — parametrize both):

```python
pixmap = self.canvas.image_item.pixmap()
img_w = pixmap.width()
img_h = pixmap.height()
default_family = self._default_font_family()
detected_pageboxes: list[PageBox] = []
for blk in blk_list:
    box = textblock_to_box(blk)  # int coercion (plan 03-01, pure)
    clamped = Box(
        min(max(box.x1, 0), img_w),
        min(max(box.y1, 0), img_h),
        min(max(box.x2, 0), img_w),
        min(max(box.y2, 0), img_h),
    )
    if clamped.x2 <= clamped.x1 or clamped.y2 <= clamped.y1:
        continue
    detected_pageboxes.append(
        PageBox(box=clamped, origin=DETECTED, payload=blk,
                style=default_style(default_family) if default_family else None)
    )
```

Signature shape: `build_detected_pageboxes(blk_list, img_w, img_h, default_family=None)`. The mask-derivation core (heatmap + boxes + MaskerConfig + radius → per-box (mask, std_dev) + constrained auto-plane binary) lives beside it as pure PIL/numpy — the vendored call sequence (§Shared Pattern 1) is its body. GUI handler and batch loop both consume it (RESEARCH §5.1).

---

### 5. `manga_ai_studio/gui/tools_panel.py` — detection-settings section (component, request-response)

**Analog:** the brush-size row + slider↔spinbox sync (:175-200, :275-288) and the class-scope Signal convention (:89-93).

**Row layout pattern** (:175-200):

```python
self.brush_label = QLabel(f"Brush size: {DEFAULT_BRUSH_SIZE} px")
root.addWidget(self.brush_label)

brush_row = QHBoxLayout()
brush_row.setSpacing(4)  # xs (4px) slider<->spinbox gap (UI-SPEC §Spacing)
self.brush_slider = QSlider(Qt.Orientation.Horizontal)
self.brush_slider.setMinimum(MIN_BRUSH_SIZE)
self.brush_slider.setMaximum(MAX_BRUSH_SIZE)
self.brush_slider.setValue(DEFAULT_BRUSH_SIZE)
...
root.addLayout(brush_row)
root.addStretch(1)   # <- add the new section ABOVE this stretch (root layout order)
```

**Sync-with-blockSignals pattern** (:275-288) — mirror for the dilation slider/spin pair:

```python
def _on_slider_changed(self, value: int) -> None:
    # Mirror to spinbox without recursion, update label, emit.
    self.brush_label.setText(f"Brush size: {value} px")
    was = self.brush_spinbox.blockSignals(True)
    self.brush_spinbox.setValue(value)
    self.brush_spinbox.blockSignals(was)
    self.brush_size_changed.emit(value)
```

**Signals to add** (class scope, per :91-93): `dilation_changed = Signal(int)` plus per-param commit signals (or one `masker_param_changed(str, object)`). Follow the Inspector commit shape — widget signals route to MainWindow-supplied handlers; the panel never mutates the profile itself (the InspectorPanel follower rule, §Shared Pattern 6).

**Programmatic set without re-emission** (:290-298 `set_brush_size`) — needed for loading profile values at startup. Tooltips: reuse the `MaskerConfig.export_to_conf` INI comments verbatim (config.py:584-634 — they are the canonical user-facing descriptions; D-06/PanelCleaner reference). The relocated Detect Boxes toggle mirrors the checkable-QAction shape (main_window.py:788-794).

---

### 6. `manga_ai_studio/gui/box_item.py` — inpaint border states (component, event-driven)

**Analog:** `_apply_origin_pen` (:549-566) and `_apply_look_for` (:626-639) — pen as pure function of state; `itemChange` (:606-624) shows the re-apply hook.

```python
def _apply_origin_pen(self) -> None:
    hue = origin_hue(self.pagebox.origin)
    selected = self.isSelected()
    width = _SELECTED_PEN_WIDTH if selected else _UNSELECTED_PEN_WIDTH
    self.setPen(QPen(QColor(hue), width))
    if selected:
        tint = QColor(hue)
        tint.setAlpha(_TINT_ALPHA)
        self.setBrush(QBrush(tint))
    else:
        self.setBrush(Qt.BrushStyle.NoBrush)
```

Add `set_inpaint_state(state)` in this exact shape: derive pen from (origin hue, inpaint state, selection width semantics), call `update()`. Extends — does not replace — the Phase 3 origin hue (D-11: exact colors defer to `/gsd-ui-phase 8`). State derivation is a pure function on the model (`PageBox.inpaint_state(threshold)`, file 7) so it is headless-testable; MainWindow refreshes via one `refresh_box_inpaint_states()` iterating `canvas._box_items`, wired on: detection finish, threshold/dilation change, override flip, box move/resize **release** (mouseReleaseEvent commit at canvas.py:1229-1244 — not per-mousemove), page load.

---

### 7. `manga_ai_studio/core/box_model.py` — `inpaint_override` field + state fn (model, CRUD)

**Analog:** the Phase 7 `style` field addition (:102-105) and `copy()` detachment (:177-193).

**Field pattern** — the seam fields already exist (`mask`/`std_dev` at :95-96, docstring :67-72 documents this phase as their filler). Add the override the same way, and NOTE THE NAME TRAP: `manual_override` is TAKEN (:101, Phase 4 reading-order pin):

```python
mask: Optional[object] = None  # D-15 seam: per-box mask (DEFERRED — later phase)
std_dev: Optional[float] = None  # D-15 seam: per-box std-dev (DEFERRED)
edited: bool = False  # D-04 re-OCR gate
bubble_no: Optional[int] = None  # D-15/D-16 reading-order number
manual_override: bool = False  # D-16 preserve-manual conflict policy  <- NAME TAKEN
style: Optional[TextStyle] = None  # Phase 7 (D-06)
```

New: `inpaint_override: Optional[str] = None` (None=Auto, "always"/"never"; RESEARCH Q3 recommendation).

**`copy()` detachment (Pitfall 8 — the 04-05 lesson)** — must detach the new per-box mask too or undo restores post-edit masks:

```python
return replace(
    self, payload=_copy.copy(self.payload), style=_copy.copy(self.style)
)
```

Extend with `mask=_copy.copy(self.mask) if self.mask is not None else None` (PIL `Image.copy()` exists; history `_materialize_snapshot` copies members with `.copy()` — Pitfall 13-10 snapshot weight note).

**State fn** — `inpaint_state(threshold)` mirrors the pure-method shape of `has_recognized_text` (:162-174): pure function of own fields + threshold, returns will-inpaint / gate-skipped / forced / user-skipped / no-auto-content.

---

### 8. `manga_ai_studio/gui/inspector_panel.py` — override field (component, request-response)

**Analog:** the style-section rows (:442-465), the loaded-memory guard (:509-540), `load_box` blocked-signals population (:546-630), and `connect_commit_handlers` (:1067-1147).

**Widget row pattern** (size row :442-457 — combobox or 3-radio choice is the planner's; the wiring is identical):

```python
self.size_spin = QSpinBox()
self.size_spin.setRange(0, 200)
self.size_spin.setSpecialValueText("Auto")
...
form.addRow("Size", size_row)
```

**Population with blocked signals** (bubble field, :562-567 — the no-spurious-commit rule):

```python
bubble = pagebox.bubble_no if pagebox.bubble_no is not None else 0
was = self.bubble_spin.blockSignals(True)
self.bubble_spin.setValue(bubble)
self.bubble_spin.blockSignals(was)
self._loaded_bubble = self.bubble_spin.value()  # WR-01 (spinbox guard)
```

**Multi-select Mixed** (:666-674) — differing overrides show the "Mixed" sentinel entry; the sentinel NEVER leaves the widget layer:

```python
self.font_combo.setCurrentText("Mixed")
self._loaded_style_font = "Mixed"
```

**Commit routing** — add `on_inpaint_override` to `connect_commit_handlers` as an optional kwarg (backward-compatible, per :1073-1090), wire in main_window.py:2772-2786 block. The MainWindow handler uses the ONE-snapshot grouped commit `_inspector_style_commit` shape (main_window.py:3027-3052) — capture before-snapshot with detached payloads, apply to every selected box, `set_pending_boxes_op_name("inpaint override")`, emit `boxes_modified` ONCE:

```python
before = self.canvas.boxes_snapshot()
for pb in before:
    if pb.payload is not None:
        pb.payload = copy.copy(pb.payload)
self._boxes_interaction_start_snapshot = before
for item in selected:
    apply_fn(item)
self.canvas.set_pending_boxes_op_name("style change")
self.canvas.boxes_modified.emit(before)
```

---

### 9. `manga_ai_studio/core/batch_runner.py` — constrained masks + boxes (service, batch)

**Analog:** itself — the detect branch that currently DISCARDS the blocks (:149-156):

```python
if mode in ("detect", "detect_and_clean"):
    image = _read_image_bgr(page.path)
    mask_refined, _blk_list = det_model.detect(image)
    page.mask = numpy_binary_to_mask_qimage(mask_refined).copy()
```

Replace the discarded `_blk_list` path: build boxes via the extracted core (file 4), derive the constrained composite (§Shared Pattern 1), persist `page.boxes` + per-box state + the composite onto `page.mask`. The empty-mask passthrough gate (:165-167) naturally extends — zero gate-passing boxes → empty mask → passthrough:

```python
if not page.has_mask_content():
    passthrough_original(page.path, cleaned_dir)
    continue
```

**Threading the config** — `MaskerConfig` + radius must reach `_run_batch_task`: add a parameter to `batch_detect`/`batch_detect_and_clean` signatures (mirror how `det_model_path`/`det_backend` flow, :191-222), supplied by `_dispatch_batch` from the profile (main_window.py:5391-5410 args-tuple site). Thread-safety contract (module docstring :45-49): keep new per-page state numpy/PIL in the worker; QImage construction off-thread is already precedented (:156).

---

### 10. `manga_ai_studio/core/project_io.py` — per-box field round-trip (utility, file-I/O)

**Analog:** the Phase 7 `style` optional-key precedent — THE pattern (no version bump).

**Write side** — `pagebox_to_json` (:182-207) hand-picks fields; today it "NEVER writes mask/std_dev (the D-15 seam stays None through save/load)" — that docstring contract is now superseded by this phase:

```python
return {
    "box": list(pb.box.as_tuple),
    "origin": pb.origin,
    "edited": pb.edited,
    "bubble_no": pb.bubble_no,
    "manual_override": pb.manual_override,
    "style": pb.style.to_dict() if pb.style is not None else None,  # D-07
    "payload": ...
}
```

Add `"std_dev": pb.std_dev`, `"inpaint_override": pb.inpaint_override`, and the per-box mask (box-cropped; PNG-bytes-b64 in JSON or a `boxmasks.bin` container entry — planner picks per RESEARCH §6.3; `save_image_bytes` from image_io is the single encode source).

**Load side — the optional-key pattern** (:236-240, exact):

```python
# D-07: "style" is an OPTIONAL load key (Pitfall 8 — legacy .mas files
# predate the style field). Absent/None -> TextStyle() defaults (a null
# round-trips to the default style, never None); a crafted dict clamps
# through TextStyle.from_dict (the V5 boundary), never raw.
style = TextStyle.from_dict(d.get("style"))
```

`std_dev = float(d["std_dev"]) if d.get("std_dev") is not None else None` with try/coercion; override validated against `{"always", "never"}`; unknown keys ignored, missing REQUIRED keys still raise (:226-234). Keep `validate_meta` (:545-588) structural: `_coerce_int` discipline, dims checks; light per-box validation only.

**Regression template** — `test_legacy_mas_without_style_loads_with_defaults` (tests/test_core/test_project_io.py:175): a legacy dict WITHOUT the new keys must load clean with defaults. Clone per new field.

---

### 11. `manga_ai_studio/core/image_file.py` — `raw_detected_mask` slot (model, state retention)

**Analog:** the existing slots (:90-101) — same declaration + docstring pattern:

```python
path: Path
thumbnail: QPixmap | None = None
mask: QImage | None = None
boxes: list["PageBox"] | None = None
dirty: bool = False
original_verified: bool = False
geometry_altered: bool = False
current_image: np.ndarray | None = None
```

Add `raw_detected_mask` (packed bits or PIL "1", NOT full uint8 — ~750 KB/page vs 6 MB; RESEARCH §2.3). It rides `on_page_selected` Steps 1b/4b (main_window.py:1718-1733 / :1800-1837) exactly like `boxes`. Content check mirrors `has_mask_content` (:124-141, reuse `mask_to_numpy_binary` — "do NOT reimplement the alpha scan").

---

### 12. `manga_ai_studio/core/image_ops.py` — geometry-op field policy (utility, transform)

**Analog:** itself — THE trap (Pitfall 13-6). All three transforms rebuild PageBox with an explicit field list that ALREADY silently drops `style`:

`transform_box_payload` (:156-163), crop `_clip_box` path (:283-290), `resize_boxes` (:413-422) — identical shape:

```python
return PageBox(
    box=new_box,
    origin=pagebox.origin,
    payload=fresh,
    edited=pagebox.edited,
    bubble_no=pagebox.bubble_no,
    manual_override=pagebox.manual_override,
    # NOTE: style is NOT carried — a live Phase 7 latent issue;
    # Phase 8's mask/std_dev/inpaint_override would be dropped the same way.
)
```

Phase 8 policy (RESEARCH §6.5 recommendation): **invalidate** `mask`/`std_dev` on geometry ops (a rotated std-dev/border relation is genuinely stale) and **carry** `inpaint_override` (user intent) — but the override MUST be added to all three explicit field lists or it is dropped too. Fixing the pre-existing `style` drop is a scope call (Q7 — likely a separate micro-fix).

---

### 13. `panelcleaner/config.py` — dilation radius field (config, file-I/O) [optional, Fork (a)]

**Analog:** the existing `MaskerConfig` members (:553-564) + their export/import lines.

```python
@define
class MaskerConfig:
    max_threads: ThreadLimit = 0
    mask_growth_step_pixels: Pixels | GreaterZero = 2
    mask_growth_steps: int | GreaterZero = 11
    min_mask_thickness: Pixels = 4
    allow_colored_masks: bool = True
    off_white_max_threshold: int = 240
    mask_max_standard_deviation: float = 15
    mask_improvement_threshold: float = 0.1
    mask_selection_fast: bool = False
```

Option (a): add `mask_dilation_radius: Pixels = 2` (D-09 default ≈2) + one `export_to_conf` line (:576-636 string block, with an INI comment that doubles as the UI tooltip) + one `try_to_load` line (:653-659). Flag as a conscious vendoring deviation with a header comment (Phase 3 D-14 discipline). Option (b): keep it app-side — planner decides (RESEARCH §4.2 recommends (a)).

**Persistence wiring** — `ProfileManager.save_profile`/`load_profile` (:31-49) already round-trip the whole `[Masker]` section. The startup gap is real: `__main__.py:22-26` builds `ProfileManager(Path.home()/".manga_ai_studio")` and never loads/saves — D-10 needs `load_profile("default")` at startup (`Profile.load` falls back to defaults on failure, config.py:1031-1034) + save-on-change/close. App-level toggle state (Detect Boxes) follows the QSettings reader pattern instead (main_window.py:1883-1897).

---

### 14. Test files

**Detection-seam harness** (tests/test_gui_detection_boxes.py:47-88) — extend exactly this shape; add a NONZERO heatmap region inside/outside a box and assert auto-plane content, per-box `mask`/`std_dev`, border pens, D-04 Cancel consistency:

```python
def _blk(x1, y1, x2, y2):
    return SimpleNamespace(xyxy=[x1, y1, x2, y2])

def _window_with_page(qtbot, tmp_path, w=60, h=50):
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    page_png = tmp_path / "page.png"
    Image.new("RGB", (w, h), color=(200, 200, 200)).save(page_png)
    assert window.canvas.set_image_from_path(page_png) is True
    return window
```

Drive `window._on_detection_finished(result)` directly; patch `_confirm_replace_boxes` with `return_value=True`; isolate QSettings via `_isolate_settings` (:75-88). MASK-06 dispatch tests: QTest presses at scene-mapped positions after `zoom_reset()` (canvas.py:961-966 — exact coordinates). Persistence tests clone the `test_legacy_mas_without_style_loads_with_defaults` template (test_project_io.py:175). Masker machinery battery: synthetic PIL pages, direct `grow_mask`/`mask_intersection`/`border_std_deviation`/`pick_best_mask` calls — no torch/LaMa anywhere (pin: `unit` marker = no Qt, no weights; `gui` marker = pytest-qt).

## Shared Patterns

### 1. The vendored masker call sequence (THE core pattern of the phase)

**Source:** `panelcleaner/masker.py:63-104` (canonical, GPL v3, near-verbatim vendored)
**Apply to:** the new seam core (`detection_boxes.py`), `_on_detection_finished`, batch loop.

```python
base_image = Image.open(page_data.image_path)
box_mask = page_data.make_box_mask(base_image.size, st.BoxType.EXTENDED_BOX)  # union of boxes
mask = Image.open(page_data.mask_path)
mask = mask.convert("1", dither=Image.NONE)  # Convert to bitmap.  <- dither=NONE is mandatory (Pitfall 13-7)
cut_mask = ops.mask_intersection(mask, box_mask)   # <- THE D-02 discard primitive
mask_fitments = [
    ops.pick_best_mask(base=base_image, precise_mask=cut_mask, box_mask=box_mask,
                       masking_box=masking_box, reference_box=reference_box,
                       masker_conf=m_conf, analytics_page_path=Path(original_path))
    for masking_box, reference_box in zip(...)
]
mask_fitments = [m for m in mask_fitments if m is not None]   # None = noise box (Pitfall 13-9)
best_masks = [m for m in mask_fitments if not m.failed]       # failed = std too high
```

Primitives (all `panelcleaner/image_ops.py`): `mask_intersection` (:116), `compose_masks` (:127 — use this, NOT `combine_best_masks`, for LaMa binary), `grow_mask` (:811 — `size == 0` returns input unchanged; the MASK-01 dilation). Exceptions: `border_std_deviation` raises `BlankMaskError` on empty masks (:513-515 — pre-check `getbbox()` or catch); `pick_best_mask` returns `None` for noise (:632-639 — a distinct legitimate outcome).

### 2. `.copy()` buffer discipline at every numpy↔Qt/PIL bridge (Pitfall 2)

**Source:** `mask_editor.py:166-211`, `canvas.set_mask` (:464-489), `on_page_selected` (:1712-1716).
**Apply to:** every new plane/recompose/per-box-mask path. Bridges to reuse as-is: `mask_to_numpy_binary` → `(H,W)` 0/255; `numpy_binary_to_mask_qimage` → red-overlay QImage (`.copy()`-detached). PIL↔numpy: `Image.fromarray` / `np.array(pil)`.

### 3. D-11 per-page persistence seam (outgoing-index rule)

**Source:** `main_window.py:1664-1850` — outgoing state from `self._last_page_index` (NOT `_current_page_index()`, which has already flipped); incoming restore with belt-and-suspenders `.copy()`.
**Apply to:** raw detected mask, new plane state, per-box fields. `reset_history` (:2813-2825) clears `_pre_stroke_mask` — extend to new plane tracking.

### 4. Before-state undo pushes + suppression guards

**Source:** `_on_mask_modified` (:2827-2877, `_pre_stroke_mask` tracking), `_on_boxes_modified` (:2879-2930), `_suppress_boxes_push` (:3985-3989, :1833-1837).
**Apply to:** override flips (BOXES, one grouped snapshot via `_inspector_style_commit` shape + `set_pending_boxes_op_name` canvas.py:2007-2015); strokes under the layered model (before-state = the active plane). Detection/re-dilate/recompose push NOTHING.

### 5. Worker + result-dict + `_op_running` gate

**Source:** `detect_text` (:3701-3742), `_run_detection_task` (:3744-3796), `_on_detection_finished` (:3863).
**Apply to:** any new async work (none expected — dilation/std-dev are pure numpy, main-thread-safe; only if per-box fitting proves slow does it move to the worker tail).

### 6. InspectorPanel follower + commit-handlers + Mixed

**Source:** class-scope Signals (:285-299), blocked-signals population (:562-614), WR-01 loaded-memory (:509-540), Mixed sentinels never leaving the widget layer (:666-674), `connect_commit_handlers` optional kwargs (:1067-1147); MainWindow wiring (:2772-2786).
**Apply to:** the Auto/Always/Never override field and every new ToolsPanel control.

### 7. Optional-key `.mas` evolution (no version bump)

**Source:** `project_io.py:236-240` + `test_legacy_mas_without_style_loads_with_defaults` (test_project_io.py:175).
**Apply to:** `std_dev`, `inpaint_override`, per-box mask — absent/None → defaults; coerced on load; structural `validate_meta` only.

### 8. Grouped-op single snapshot + op-name flash

**Source:** `_inspector_style_commit` (main_window.py:3027-3052), `_on_font_size_delta` (:3197-3226), canvas move-commit (:1229-1244).
**Apply to:** multi-box override apply — ONE snapshot, ONE `boxes_modified` emission, one Ctrl+Z.

### 9. Pure-function extraction for headless reuse

**Source:** `core/image_ops.py` module shape + the 05-08 ExportPage precedent; `PageBox.has_recognized_text` pure-method shape (box_model.py:162-174).
**Apply to:** box-build core + mask-derivation core + `inpaint_state(threshold)`.

### 10. QSettings isolation in GUI tests

**Source:** `_isolate_settings` (test_gui_detection_boxes.py:75-88) — monkeypatch `window._settings` to a tmp INI.
**Apply to:** any new test touching settings/profile state.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `canvas.py` 3-plane mask model (`_auto_bin`/`_mask_manual`/`_mask_erase` + `recompose_mask`) | component/state store | transform | No existing multi-layer mask state — today's `_mask` is one flat QImage full-replaced by `set_mask`. Closest building blocks: `set_mask` bridge (canvas.py:449-496), `mask_editor` bridges, `_on_mask_modified` before-state tracking. Use RESEARCH §2.2 Option B spec. |
| Interactive per-box `pick_best_mask` gate (Fork A) | service | transform | First real caller — machinery is only import-tested today (tests/test_core/test_masker_vendor.py, test_structures.py:101). Canonical sequence exists (masker.py) but no interactive caller. |

Everything else has a strong in-repo analog. The Planner should lean on RESEARCH §2 (mask model), §7.2 (dispatch pseudo-code), and §1.4 (minimal per-box sequence) for the two gaps above.

## Metadata

**Analog search scope:** `manga_ai_studio/{gui,core,config}`, `panelcleaner`, `tests`, `tests/test_core` — 22 files inspected; 1,700+ lines read across the 9 primary analogs (main_window.py, canvas.py, box_item.py, inspector_panel.py, tools_panel.py, box_model.py, project_io.py, batch_runner.py, image_file.py, mask_editor.py, image_ops.py, config.py, image_ops.py vendored, masker.py) + 3 test files.
**Key traps encoded:** `manual_override` name collision (box_model.py:101); geometry-transform explicit field lists drop unlisted fields (image_ops.py:156-163/283-290/413-422 — `style` already dropped); `set_mask` full-replaces + emits nothing; D-04 Cancel aborts after mask set; `_confirm_replace_mask` copy now false; `BlankMaskError`/None-return contracts; dither=NONE on binarize; eraser dual-write; recompose never per-mousemove.
**Pattern extraction date:** 2026-08-15
