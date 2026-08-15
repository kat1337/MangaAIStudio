# Phase 8 Research: Masker & Selective Inpaint

**Researched:** 2026-08-15
**Objective:** Answer "What do I need to know to PLAN this phase well?" for MASK-01/02/03/05/06.
**Decisions honored:** 08-CONTEXT.md D-01..D-18 (user-locked; not re-litigated here).

---

## 0. Executive Summary

Phase 8 is a **detection→mask seam rework + first real caller of already-vendored machinery**. Every function the phase needs (`border_std_deviation`, `pick_best_mask`, `grow_mask`, `make_mask_steps_convolution`, `mask_intersection`, `compose_masks`, `Box.pad`) is already in `panelcleaner/image_ops.py` / `panelcleaner/structures.py` — **no new vendoring**. The four genuinely new engineering surfaces are:

1. **A layered mask model** — today the canvas has ONE composite mask QImage (`canvas._mask`, canvas.py:493) where detection output and hand strokes are indistinguishable and `set_mask` full-replaces. D-02/D-07/D-08 (discard-at-seam, dilation-never-touches-strokes, live re-dilate from a retained raw mask) are **not expressible** on that flat layer. §2 proposes a 3-plane model (auto-derived / manual / erase-ledger) that keeps the existing paint helpers, undo stacks, and LaMa call byte-identical in shape.
2. **The `_on_detection_finished` reorder** (main_window.py:3863) — build boxes first, then derive the auto layer from heatmap ∩ box-interiors, then per-box std-dev + border state. The D-02 discard has an exact vendored precedent: `ops.mask_intersection(mask, box_mask)` in `panelcleaner/masker.py:75`.
3. **The mouse-dispatch carve-out** (canvas.py:997-1107) — a small, contained restructure; the exact branch order is mapped in §7.
4. **`.mas` + PageBox field extension** — three new per-box fields ride the proven "optional key, no version bump" pattern (the Phase 7 `style` precedent, project_io.py:236-240). **Naming trap:** `manual_override` is already taken (Phase 4 reading-order pin, box_model.py:101) — the tri-state override needs a new name (e.g. `inpaint_override`).

Biggest hidden landmine found: **`core/image_ops.py` geometry transforms rebuild `PageBox` with an explicit field list that already silently drops `style`** (transform_box_payload, image_ops.py:156-163; crop at :283-290; resize at :370-420). Phase 8's per-box fields would be dropped the same way unless the transforms are extended or the fields are invalidated on geometry ops (§6.5, Pitfall 13).

Test baseline: **717 tests collected** (`pytest --collect-only`, pinned interpreter). The masker machinery is currently only *import-tested* (test_masker_vendor.py, test_structures.py:101) — Phase 8 writes its first real call-site tests, all headless (pure PIL/numpy; no torch/LaMa).

---

## 1. The Vendored Masker Machinery — Exact Contracts & Call Sequence

### 1.1 Function contracts (all in `panelcleaner/image_ops.py`, GPL v3, verified line numbers)

| Function | Inputs | Returns | Notes |
|---|---|---|---|
| `border_std_deviation` (:483) | `base: PIL` (RGB ok — internally `.convert("L")` when `not allow_color`), `mask: PIL mode "1"`, `off_white_threshold: int`, `allow_color: bool` | `(std: float, median_color: (r,g,b))` | Measures **edge pixels of the mask** (`ImageFilter.FIND_EDGES`), not the box border. Raises `BlankMaskError` on an empty mask (:513-515). Grayscale path: plain `np.std`; RGB path: `color_std` (Euclidean distances from mean) + heuristic/geometric median color. Off-white rounding at :535-536. |
| `pick_best_mask` (:584) | `base: PIL` (full page ok — it cuts out itself), `precise_mask: PIL "1"`, `box_mask: PIL "1"`, `masking_box: st.Box`, `reference_box: st.Box`, `masker_conf: cfg.MaskerConfig`, `analytics_page_path: Path` (only used in a log line) | `None` (blank precise mask in box → noise) or `st.MaskFittingResults` | Cuts `base` by `reference_box`, cuts/pads masks by `masking_box` (offset math at :624-641); generates growth-step candidates via `make_mask_steps_convolution`; measures `border_std_deviation` per candidate; picks "lowest std at greatest size" with the `mask_improvement_threshold` hysteresis (:694-702); `failed=True` (best_mask None) when std > `mask_max_standard_deviation` (:705). `mask_selection_fast` short-circuits on std==0 (:685). |
| `make_mask_steps_convolution` (:350) | `mask: PIL "1"`, `growth_step, steps, min_thickness: int` | generator of `(PIL "1", thickness)` | scipy `convolve2d` with `make_growth_kernel` (rounded square ≤5px, ellipse above, :323-347). First yield is at `min_thickness`. |
| `grow_mask` (:811) | `mask: PIL "1"`, `size: int` | `PIL "1"` | **The MASK-01 dilation primitive.** Single-shot grow by `size` px via one convolution. `size == 0` returns input unchanged (:820-821). |
| `mask_intersection` (:116) | `mask1, mask2: PIL "1"` (same size) | `PIL "1"` = mask1 ∩ mask2 | **The D-02 discard primitive** — this is exactly "detected text outside boxes never enters the mask layer". |
| `compose_masks` (:127) | `base_size: (w,h)`, `[(mask, (x,y)), ...]` | `PIL "1"` union paste | Composes per-box masks back to a full-page "1" mask. |
| `combine_best_masks` (:730) | `image_size`, `Iterable[MaskFittingResults]` | `PIL RGBA` (colored by median_color) | PC's batch path colors masks by border median — **we do NOT want this for LaMa** (LaMa takes a binary mask; use `compose_masks` instead). |
| `cut_out_box` (:541) / `cut_out_mask` (:552) | image / mask "1", `st.Box` (+ optional target_shape/offsets) | cropped PIL | The box→cutout helpers; `cut_out_mask` pads to a target shape with black. |

### 1.2 `MaskFittingResults` (structures.py:579-616, `@frozen`)

```
best_mask: PIL "1"            # None when failed (std too high) — sized to reference_box
median_color: (r,g,b)
mask_coords: (x, y)           # = (reference_box.x1, reference_box.y1) — paste origin
analytics_page_path, analytics_std_deviation: float, analytics_mask_index: int,
analytics_thickness: int | None, mask_box: Box, debug_masks: list[PIL]
# properties: .failed (best_mask is None), .analytics, .mask_data, .noise_mask_data
```

`Box` (structures.py:39-160, `@frozen`): `x1,y1,x2,y2` ints; `.as_tuple`, `.pad(amount, canvas_size)` (clamped growth — the reference-box builder), `.merge`, `.overlaps`, `.translate`, `.scale`. `PageData.make_box_mask(image_size, BoxType)` (structures.py:341) draws a list of boxes as a mode-"1" mask — reusable to build the box-union mask (it only needs a duck-typed object with `.boxes_from_type`; simplest is to build the union with `ImageDraw` directly).

### 1.3 PanelCleaner's canonical end-to-end sequence (`panelcleaner/masker.py:40-148`)

1. Load base image (PIL), build `box_mask` = union of EXTENDED boxes (`make_box_mask`, masker.py:66).
2. Load the AI mask, binarize: `mask.convert("1", dither=Image.NONE)` (masker.py:72).
3. **Discard:** `cut_mask = ops.mask_intersection(mask, box_mask)` (masker.py:75) — the upstream D-02.
4. Per box: `pick_best_mask(base, precise_mask=cut_mask, box_mask=box_mask, masking_box=merged_extended_box, reference_box=reference_box, ...)` (masker.py:81-94). `masking_box` = the (merged, extended) box; `reference_box` = that box grown further (`Box.pad`) so candidates have room inside the base cutout.
5. Drop `None` fitments (noise) and `failed` fitments (std too high) (masker.py:96-102).
6. `combine_best_masks` → colored mask → paste onto page → clean output.

### 1.4 Minimal sequence for OUR interactive context (per box)

The worker already returns `{"mask": mask_refined (H,W) uint8 heatmap, "blocks": blk_list}` (main_window.py:3796; adapter torch_impl.py:109-134). Per page, in `_on_detection_finished` (or a headless twin for batch):

```python
page = Image.fromarray(image_rgb)                                  # base (RGB PIL)
heatmap = Image.fromarray(np.where(mask_refined > 0, 255, 0).astype(np.uint8))
detected = heatmap.convert("1", dither=Image.NONE)                 # binarize (masker.py:72 pattern)
# D-02 discard (mask+boxes mode only):
box_union = draw union of ALL boxes (user + detected) as "1"       # masker.py:66 pattern
cut = mask_intersection(detected, box_union)                       # image_ops.py:116
# MASK-01 dilation at the seam (auto only — D-07):
cut = grow_mask(cut, radius) if radius else cut                    # image_ops.py:811
# per box b (masking_box = b.box; reference_box = b.box.pad(growth_room, page.size)):
fit = pick_best_mask(page, cut, box_union, b.box, ref_box, masker_conf, path)
if fit is None:            b.mask, b.std_dev = None, None          # noise / no text in box
else:                      b.mask, b.std_dev = fit.best_mask (box-cropped), fit.analytics_std_deviation
# auto layer = compose_masks(page.size, [(b.mask, b.box.xywh_topleft) for b in boxes_that_will_inpaint])
```

Two design forks the planner must settle (see Open Questions Q1/Q2):
- **Fork A (full masker):** run `pick_best_mask` per box (as above). The growth-step machinery then already "covers letter edges" starting at `min_mask_thickness=4`; the MASK-01 radius is an *additional* pre-grow of the precise mask (or only used on the mask-only path D-03). Cost: `mask_growth_steps` convolutions × boxes on main thread (fast on box-sized cutouts; PC does exactly this per page; `mask_selection_fast` short-circuits).
- **Fork B (gate-only):** skip growth-step selection; per-box mask = `grow_mask(heatmap ∩ box, radius)` and `border_std_deviation(page, that_mask, ...)` for the gate. Cheaper, simpler, but then the exposed growth/thickness/improvement params (D-06) have no effect and `pick_best_mask` stays dead code. **D-06's explicit exposure of growth params points at Fork A**; the dilation radius then composes (dilate raw → growth candidates measure from the dilated edge).

**Cheap-math note:** everything in §1 is PIL/numpy/scipy — main-thread-safe, no worker needed (08-CONTEXT "Established Patterns" confirms: "std-dev computation is cheap and main-thread-safe"). `scipy` is already a pinned dependency (pyproject.toml).

### 1.5 Coordinate/format gotchas

- PIL masks are **mode "1"**; our canvas/QImage world is ARGB32-with-red-alpha-160. Bridges already exist both ways: `mask_to_numpy_binary(qimage) -> (H,W) 0/255` (mask_editor.py:166) and `numpy_binary_to_mask_qimage(arr) -> red-overlay QImage` (mask_editor.py:194). PIL↔numpy: `Image.fromarray(arr)` / `np.array(pil)`.
- Scene coords == page pixel coords 1:1 (scene rect = pixmap rect, canvas.py:388; Phase 5 keeps image/mask/boxes in one frame) — `PageBox.box` ints are directly usable as `st.Box` for the machinery (they ARE `panelcleaner.structures.Box` already — box_model.py:44 composes the same class, so **no conversion needed at all**).
- `pick_best_mask`'s returned `best_mask` is sized to the *reference box*, pasted at `mask_coords` — when storing `PageBox.mask`, crop it back to the masking box (`cut_out_mask(fit.best_mask_padded... )` is fiddly; simpler: keep per-box mask as the box-cropped region, paste at `b.box.as_tuple[0:2]`).

---

## 2. Mask Composition Model (D-01/D-02/D-07/D-08) — the central design decision

### 2.1 What exists today (the flat layer)

- `EditorCanvas._mask` is ONE QImage ARGB32 (red, alpha 160) — canvas.py:449-496. `set_mask` **full-replaces** it (detection), brush/rect/lasso/eraser mutate it in place (`mask_editor.py` helpers), `mask_to_numpy_binary(canvas.get_mask())` feeds LaMa (main_window.py:4204).
- Persistence: the flat QImage round-trips `ImageFile.mask` ↔ canvas via the D-11 seam (main_window.py:1716/1798) and `.mas mask.bin` (project_io.py:328-329).
- Undo: MASK stack = full-QImage before-states per stroke (`_on_mask_modified` + `_pre_stroke_mask`, main_window.py:2827-2877).
- Detection is already a **non-undoable baseline** (`set_mask` emits nothing) — matching Phase 3's box-detection baseline decision.

**Why the flat layer cannot carry Phase 8:** re-dilate (D-08) needs the pre-dilation detected content *as a separate fact* from strokes; dilation-must-not-touch-strokes (D-07) needs to know which pixels are auto; discard (D-02) must not eat strokes. On a flat layer, an erase stroke destroys provenance irrecoverably.

### 2.2 Options

**Option A — two display-composited layers (auto derived + manual), eraser hits both destructively.**
`_mask_auto` derived from (raw heatmap ∩ boxes, dilated, gate-filtered); `_mask_manual` the stroke target; displayed/inpainted mask = union. Eraser applies Clear to both. *Fatal flaw:* an erase of auto content is indistinguishable from "never detected" after a re-dilate recompose re-adds it — radius change would resurrect erased false positives.

**Option B (recommended) — three planes: derived auto + manual + erase-ledger.**
- `_auto_bin: np.ndarray (H,W) 0/255` — DERIVED state, never painted into. Recomputed from: retained raw heatmap ∩ (union of boxes that will inpaint), dilated by radius. Cheap (~numpy ops).
- `_mask_manual: QImage` — brush/rect/lasso paint here (existing helpers unchanged).
- `_mask_erase: QImage` — eraser strokes accumulate here (paint red with normal composition = "erased" bitmap).
- Displayed `_mask` (the existing attribute — keeps `get_mask/has_mask/update_mask_display/apply_undo_mask` and the LaMa path working unchanged) = `numpy_binary_to_mask_qimage( (manual_bin | auto_bin) & ~erase_bin )`, recomposed at stroke-commit / detect / radius change / box change / override flip — **not per mousemove**. During an active stroke, double-write: paint the stroke into `_mask` directly for live feedback (today's path) AND into manual/erase plane; recompose at `_end_paint`.
- Invariants fall out naturally: hand strokes always inpaint (D-01 — manual plane is unconditional); discard (D-02 — auto plane is box∩ by construction); dilation never touches strokes (D-07 — grow only the auto plane); re-dilate (D-08 — recompute auto from the retained raw heatmap, then recompose; ledger and strokes survive); eraser still erases anything (today's capability preserved, §2.4).

**Option C — single mask + tracked provenance (per-pixel ownership map).** Rejected: fragile under anti-aliased stroke edges, doubles memory, complicated serialization.

Per-box masks (`PageBox.mask`) remain the *authoritative record* of each box's contribution; the auto plane is the composition of them (plus dilation state). Storing per-box masks makes `.mas` round-trip (criterion 5) and box move/resize recompute straightforward: a moved box re-runs its fit against the new region (or translates its mask — planner choice; recompute is more correct, translate is cheaper; see Open Q5).

### 2.3 Raw-mask retention (D-08) — where it lives

- Retention shape: the **pre-dilation, thresholded binary** of the detection pass (`detected` in §1.4). Keep as `np.packbits` (H*W/8 bytes ≈ 750 KB per page) or PIL "1"; NOT a full uint8 array (6 MB/page × N pages adds up). Store on `ImageFile` (e.g. `raw_detected_mask`) so it survives page switches via the D-11 seam pattern (Step 1b/4b, main_window.py:1718-1837) — extend `on_page_selected` and `_snapshot_current_page`.
- Live re-dilate wiring (cheapest path): ToolsPanel `dilation_changed(int)` signal → MainWindow slot → `recompute_auto_layer()` (uses current page's raw mask + current boxes + radius) → `canvas.recompose_mask()` + border-state refresh. No worker, no model. If no raw mask exists (page never detected / toggled mode), it's a no-op.

### 2.4 Interaction corners to decide

- **Erase of auto content inside a gate-passed box:** with Option B the ledger subtracts it from the composite; `PageBox.mask` still says "will inpaint". The border state should probably demote to a "partially erased" or stay "will-inpaint" — planner picks (simplest: border state reflects gate+override only; the erase is visible on the mask itself).
- **Detect Boxes toggle OFF (D-03):** auto plane = full heatmap (no box constraint), dilation still applies (MASK-01 exists precisely for the heatmap's conservative edges). Gate/override/border states are inert (no boxes).
- **Toggle ON + zero boxes detected:** auto plane is EMPTY (D-02 discards everything) — C inpaints only hand strokes. Deliberate per D-01/D-02, but a visible behavior change from Phase 1 (users will notice "detected but mask empty"). Surface in UAT copy.
- **Re-detect (D-03 replace-detected-keep-user):** detected boxes (and their mask/std_dev/override — new objects) are replaced wholesale; USER boxes survive with their state. Overrides on replaced boxes vanish with them (consistent with Phase 3 D-03; confirm in plan). The `_confirm_replace_boxes` gate already governs. The `_confirm_replace_mask` gate copy ("Your manual edits will be lost", main_window.py:4102-4104) becomes **wrong** under Option B — re-detect replaces only the auto plane; strokes survive. Reword or only fire when auto content exists.
- **Mask-only pages → C with no boxes and no strokes:** existing `has_mask_content` gate already short-circuits (main_window.py:4197).

---

## 3. Detection Seam Rework (`_on_detection_finished`)

### 3.1 Today (main_window.py:3863-3899)

```
mask = result["mask"]; canvas.set_mask(QImage(mask))        # FULL heatmap composited FIRST
if action_detect_boxes_mode.isChecked():
    _build_detected_boxes(result["blocks"])                  # boxes built SECOND (conditional)
```

### 3.2 New sequence (mask+boxes mode)

1. **Build boxes first** — reuse `_build_detected_boxes` (main_window.py:3901) *unchanged* for the box layer (D-03/D-04/V5 all live there). It reads `canvas.image_item.pixmap()` for dims (:3937-3939).
2. **Retain the raw mask** (D-08) on the page/ImageFile.
3. **Derive the auto plane** per §1.4/§2 (heatmap ∩ boxes ∪ overrides, dilated) and `canvas.recompose_mask()` — replaces the unconditional `set_mask` call for this mode. Mode OFF keeps today's `set_mask(full heatmap)` verbatim (D-03).
4. **Per-box fit + std_dev** (D-12): run per-box (`pick_best_mask` or `border_std_deviation`) against the page numpy (`canvas.get_image_numpy()`), write `PageBox.mask`/`std_dev`.
5. **Border states** (§8) refresh from std_dev + threshold + override.
6. Ordering/gates: the D-04 box gate (`_confirm_replace_boxes`) fires *inside* `_build_detected_boxes` and **Cancel aborts the box build** (:3930-3932) — under the new sequence a Cancel must also skip the auto-plane derivation (else you get new mask + old boxes). Either (a) run the gate before any mask work (move the gate check up, or pre-check in `detect_text`), or (b) make step 3-5 conditional on the box build not aborting. The existing `_confirm_replace_mask` gate runs pre-worker in `detect_text` (:3720) — reword per §2.4.
7. **Undo:** detection stays a non-undoable baseline (both mask side — `recompose` must not emit `mask_modified` — and boxes side, existing `_suppress_boxes_push`, :3985). History entries only for subsequent strokes/overrides.
8. **Page state:** mark session dirty as today (detection already dirties via mask path? — today `set_mask` does NOT emit `mask_modified`, so detection does NOT mark dirty; check and keep consistent — likely set dirty explicitly in the new handler).

Performance: per-box `pick_best_mask` on box-sized cutouts is main-thread-fast (tens of ms per page typically); if profiling disagrees, the whole derivation (steps 2-5) is numpy/PIL and can move into `_run_detection_task`'s worker tail (it already has the heatmap + blocks before returning — but the box build needs the D-04 gate first, so interactive flow prefers main thread; batch does it in the worker, §5).

---

## 4. MaskerConfig Parameter Surface (D-05/D-06/D-10)

### 4.1 Where the config lives today

- `Profile.masker: MaskerConfig` (config.py:944) — the vendored Profile already carries it; `Profile.bundle_config()` round-trips the `[Masker]` INI section (config.py:959; export at :566-640, import at :642-673 via `try_to_load` with typed coercion).
- Defaults (config.py:554-564): `mask_growth_step_pixels=2`, `mask_growth_steps=11`, `min_mask_thickness=4`, `allow_colored_masks=True`, `off_white_max_threshold=240`, `mask_max_standard_deviation=15`, `mask_improvement_threshold=0.1`, `mask_selection_fast=False`, `debug_mask_color` (not UI-relevant), `max_threads=0`.
- `ProfileManager` (config/profile_manager.py) exposes `save_profile(profile, name)` → `Profile.safe_write` (atomic) and `load_profile(name)`.
- **Startup gap:** `__main__.py:22-26` builds `ProfileManager(Path.home()/".manga_ai_studio")` and never loads/saves a profile — `config.current_profile` is always defaults today. D-10 persistence needs a load-at-startup (`load_profile("default")` — `Profile.load` already falls back to defaults on any failure, config.py:1031-1034) and a save-on-change (or save-on-close). Small, contained.
- Precedent for app-level (non-INI) settings: QSettings (`defaultFontFamily`, recent files — main_window.py:1883-1897). D-10 explicitly chooses the profile INI for the masker set; the Detect Boxes *toggle* is view-state like today's action (main_window.py:788-791) and can stay in-memory/QSettings (planner pick).

### 4.2 The dilation radius has no MaskerConfig field

`MaskerConfig` (config.py:554) has **no dilation radius** — PC's "growth" is the pick-best step machinery, not a simple radius. MASK-01/D-08/D-09 (default ≈2 px, live re-dilate) is a NEW parameter. Options:
- **(a) Add a field to the vendored `MaskerConfig`** (e.g. `mask_dilation_radius: Pixels = 2`) + one export line + one `try_to_load` line. Deviates from near-verbatim vendoring (Phase 3 D-14 discipline) but config.py is already ours to maintain; upstream PC ignores the extra key gracefully (unknown options are skipped by `import_from_conf`). Keeps ALL masker params in one object that the batch worker can receive in one piece.
- **(b) Keep it app-side** (a plain attribute next to the profile or in QSettings) and pass it alongside `profile.masker` at the seam. Zero vendored-file churn; two sources of truth for "masker params".

Recommend (a) for coherence with D-06/D-10 (the UI binds one object; the INI round-trips it for free). Flag in plan as a conscious vendoring deviation with a header comment (like the 03-01 qualified-name rewrites).

### 4.3 UI shape (D-05: right-side Tools dock; model on PanelCleaner)

Upstream reference (D-06: "look at how panelcleaner does it"): PC's profile dialog **generates** its Masker page by parsing `Profile.bundle_config(gui_mode=True)` — `parse_profile_structure` (../PanelCleaner/pcleaner/gui/profile_parser.py:426-526) maps each option's type annotation to a widget (bool→checkbox, `Pixels`→spinbox, float→doublespin...), and the INI **comments become the help text** (ProfileComment), with display names from `to_display_name` (snake→Title Case, :753). The MaskerConfig `export_to_conf` comments (config.py:584-634) are therefore the canonical user-facing descriptions — reuse them as tooltips verbatim.

For OUR ToolsPanel (tools_panel.py — QVBoxLayout, tool row + brush row, `root.addStretch(1)` at :202): add a "Detection settings" section below brush size: the relocated Detect Boxes toggle (D-05) + ~9 rows (radius slider/spin 0..~10 default 2; std-dev threshold double 0..100; growth step px; growth steps; min thickness; off-white threshold 0..255; improvement threshold double; allow-color checkbox; fast-selection checkbox). Follow the brush-row sync pattern (slider↔spinbox mirror with blockSignals, tools_panel.py:275-288) and the class-scope Signal + commit-handler pattern (the InspectorPanel D-08 follower shape). Keyboard reachability contract applies to every new control (08-CONTEXT Claude's Discretion). Exact layout/colors defer to the `/gsd-ui-phase 8` pass (UI hint: yes).

---

## 5. Batch Integration (D-04)

`batch_runner.py` today: `_run_batch_task` detect mode runs `mask_refined, _blk_list = det_model.detect(image)` and **discards `_blk_list`**, persisting the FULL heatmap to `page.mask` (batch_runner.py:149-156). Phase 8 changes:

1. **Extract the box-build core headless.** `_build_detected_boxes`'s V5 loop (main_window.py:3944-3970) reads the canvas pixmap for dims and QSettings for the default font family — batch has `image.shape` and no canvas. Extract a pure function (e.g. `manga_ai_studio/core/detection_boxes.py: build_detected_pageboxes(blk_list, img_w, img_h, default_family=None)`) consumed by BOTH the GUI handler and the batch loop. (The GUI keeps its D-03/D-04/gate/overlay wrapper.)
2. **Derive the constrained auto mask per page** in the loop (the §1.4 sequence, numpy/PIL only — thread-safe; QImage construction off-thread is already precedented at batch_runner.py:156). Needs `MaskerConfig` + radius threaded into `batch_detect`/`batch_detect_and_clean` signatures (MainWindow `_dispatch_batch` supplies from profile — main_window.py:5380 area).
3. **Populate `ImageFile.boxes` + per-box `mask`/`std_dev`** (D-04: "batch-detect-only runs persist per-page boxes + constrained masks"). `ImageFile.boxes` slot exists (image_file.py:93); `page.mask` receives the constrained composite (union of gate-passing per-box masks — batch has no overrides, so gate-only).
4. **batch_detect_and_clean:** the clean stage reads `mask_to_numpy_binary(page.mask)` (batch_runner.py:175) — already the constrained mask, LaMa untouched. The D-03 empty-mask passthrough (batch_runner.py:165-167) naturally extends: a page with zero gate-passing boxes has an empty mask → passthrough.
5. Post-batch refresh: `_refresh_current_page_after_batch` is mode-aware (02-04 lesson, STATE.md) — detect mode restores masks via the D-11 pattern; it must now ALSO restore boxes (and recompose per §2) or the current page desyncs (the 02-04 Bug-D family). Re-run the D-04 gate checks for the *current* page if batch replaced its detected boxes — or skip gate-in-batch entirely (batch is headless; the 03-04 D-04 gate is a GUI concern; replacing in batch is the point of batch).

---

## 6. `.mas` Serialization Impact (success criterion 5)

### 6.1 Current shape

- `pagebox_to_json` (project_io.py:182-207) hand-picks fields and **explicitly never writes mask/std_dev** (the D-15 seam docstring). `json_to_pagebox` (:210-280) rebuilds with V5 int coercion; unknown keys ignored, missing keys raise.
- Page container: `meta.json` (with `boxes` list) + `image.png` + `mask.bin` (raw H*W uint8 bytes, dims declared in meta) + `original.json` (build_page_entries :285-334; parse :423-483 with blob-length cross-check :467-471). `_FORMAT_VERSION = 1` (:47) enforced on both manifest and page header.

### 6.2 The pattern to follow (no version bump)

The Phase 7 style-field precedent: `"style"` is an **optional load key** — absent/None → defaults, never None (project_io.py:236-240; regression `test_legacy_mas_without_style_loads_with_defaults`, test_project_io.py:175). Phase 8's fields ride the same pattern:

- `pagebox_to_json` adds: `"std_dev": float|None`, `"inpaint_override": "always"|"never"|None` (None=Auto; **do not name it `manual_override` — taken**, box_model.py:101), and the per-box mask.
- `json_to_pagebox` adds optional-key reads with coercion (`float()`, enum-string validation).
- `validate_meta` (project_io.py:545) may need per-box light validation (std_dev float|None; override in the 2-value set) — keep it structural.

### 6.3 Per-box mask serialization format

Options (planner picks; all are optional-on-load so legacy files keep working):
- **(a) PNG bytes per box, base64 in the box JSON** — `save_image_bytes` (image_io, already the single source of truth per STATE) → b64. A text-box mask is mostly empty → PNG packbits ≈ a few hundred bytes. Simple, versioning-free; slight JSON bloat.
- **(b) RLE in JSON** — smallest code, but hand-rolled codec + tests.
- **(c) One container entry per page** (e.g. `boxmasks.bin` — concatenated or a tiny index) — keeps meta.json lean; more container plumbing; entry names are naturally optional in `parse_page_entries`.

Size: full-page per-box masks would be wasteful — store **box-cropped** masks (crop dims implicit in `box`). Recommend (a) or (c).

### 6.4 The raw heatmap (D-08) across save/load

Whether `.mas` persists the retained raw mask is discretionary. If not persisted, post-load radius changes cannot re-dilate (recompute would need a re-detect) — the auto layer loads from the per-box masks instead (union), and live re-dilate silently no-ops. Persisting it costs one more entry (~like mask.bin; 1-bit-packable). Recommend persisting (it is the D-08 contract's data); planner decides.

### 6.5 Geometry-op survival — the field-drop trap (Pitfall 13)

`core/image_ops.py` rotate/crop/resize rebuild each PageBox with an **explicit** field list: `transform_box_payload` (:127-163) carries box/origin/payload/edited/bubble_no/manual_override — and **already drops `style`** (a live Phase 7 latent issue); crop `_clip_box` (:283-290) and `resize_boxes` (:370-420) are the same. Phase 8's `mask`/`std_dev`/`inpaint_override` would be silently dropped by any rotate/crop/resize. Decide: (a) extend these transforms (mask would need its own crop/rotate/scale — doable, same math as lines) and ideally fix style while there (scope call), or (b) **invalidate**: geometry op clears per-box mask/std_dev (and recomputes lazily or on next detect) — simpler, honest (a rotated std-dev/border relation is genuinely stale). Recommend (b) for mask/std_dev + carry override through (override is a user intent, cheap to carry — but the explicit field lists still need the name added or it's dropped too).

---

## 7. Paint-Under-Boxes Dispatch (D-15..D-18)

### 7.1 Current dispatch (canvas.py:997-1107)

Order: (0) inline-editor guard :1020 → (1) pan :1030 → (2) **box hit-test** :1042-1081 [handle→resize (only when exactly 1 selected, :1063-1066); box→Shift toggle / select+move :1067-1073; Alt on empty→create :1074-1077; empty no-Alt→clear selection + FALL THROUGH :1078-1081] → (3) crop branch :1088-1096 → (4) paint branch :1098-1106 (left + tool ∉ {MOVE, CROP} + mask non-null) → (5) super().

### 7.2 The carve-out restructure

Introduce `PAINT_TOOLS = {BRUSH, RECTANGLE, LASSO, ERASER}`; when `self.current_tool in PAINT_TOOLS`, the box branch becomes Alt-gated:

```
if box_layer visible and left:
    if AltModifier:
        item = _box_item_at(...)
        if handle and len(selected)==1: _begin_resize(...)          # Alt+handle resize (same gate)
        elif BoxItem:                _select_and_begin_move(...)    # Alt+click select / Alt+drag move (D-15)
        else:                        _begin_create_box(...)         # Alt+drag create on EMPTY canvas (D-15)
        accept; return
    if current_tool not in PAINT_TOOLS:
        ... today's branch verbatim (handle / Shift-toggle / select+move; empty→clear+fall-through) ...
        (returns as today)
    # paint tool, no Alt: FALL THROUGH — clicks on box bodies AND handles paint (MASK-06)
    (empty canvas: keep the clear-selection-then-fall-through? today empty-no-Alt clears selection then
     paints — with a paint tool active, clearing selection on every paint start is correct/unchanged)
```

- Crop (D-17): CROP ∉ PAINT_TOOLS → crop keeps today's behavior (box presses still select/move) with zero changes to the crop branch.
- Double-click (D-16): `mouseDoubleClickEvent` (:1109-1137) has no tool gate — unchanged. **Corner:** with Brush active, the *first* press of a double-click paints a dot on the box before the editor opens (press dispatch precedes Qt's double-click synthesis). Acceptable (one dot, undoable) or suppress — planner picks; flag in UAT.
- **Shift multi-select conflict:** under a paint tool, Shift+click on a box now PAINTS (only Alt selects) — Phase 7 D-08 Shift-toggle is unreachable while painting (must be in Move/Pan). Note the Shift Brush↔Eraser tool toggle is keyed off `keyPressEvent` Key_Shift (01-04 lesson, STATE), not mouse modifiers — no conflict there. Document in UI copy.
- Hit-test nuances preserved: `_box_item_at` (:2016) already skips the cursor/preview overlays and the zoom-transform BSP trap (:1047-1060 comments); the carve-out does not change hit-testing, only branch routing. `Alt+handle` when the handle's box isn't the sole selection is a dead press today (:1063-1066 accepts without acting) — keep identical under Alt.
- `_mask` is always non-null after `set_image` (canvas.py:390-397), so the paint branch's mask guard never blocks painting on a loaded page.

---

## 8. Border State Indicator (D-11/D-12)

- Render site: `BoxItem._apply_origin_pen` (box_item.py:549-566) / `_apply_look_for` (:626-639) — pen is currently a pure function of (origin hue, selection width). Phase 8 adds an **inpaint-state dimension**: will-inpaint / gate-skipped / forced (Always) / user-skipped (Never) / no-auto-content. Exact colors defer to `/gsd-ui-phase 8` (01-UI-SPEC tokens; D-11 says token mapping is the UI-spec pass's call) — the code shape is: an `set_inpaint_state(state)` method that, like `_apply_origin_pen`, sets pen (e.g. state color when unselected; keep selection width semantics) and calls `update()`. Repaint cost is one item's rect — negligible.
- State derivation (predictive, D-12): `will = (override=="always") or (override is None and std_dev is not None and std_dev <= mask_max_standard_deviation and box has auto content)`; Never → user-skipped; std_dev above threshold → gate-skipped. Pure function of PageBox fields + the threshold — put it in the model layer (headless-testable), e.g. `PageBox.inpaint_state(threshold)`.
- Recompute triggers (wire in MainWindow, one `refresh_box_inpaint_states()` helper iterating `canvas._box_items`): detection finish, threshold/dilation/gate-param change, override flip, box move/resize **commit** (release, not per-mousemove — D-12's debounce note), re-dilate, page load/restore. Box move changes the region → std_dev is stale → either recompute per-box std_dev on release (a `border_std_deviation` call per moved box — cheap) or demote to "stale" state until recomputed; recommend recompute-on-release.
- Extending (not replacing) Phase 3 D-09 origin styling: origin hue stays the base (green/amber); the inpaint state modifies it (e.g. dash pattern for skipped, distinct hue for forced — UI-spec's call).

---

## 9. Undo/Redo Integration

- **Inpaint (C):** unchanged — ONE IMAGE entry (bbox-shaped pre-inpaint patch, main_window.py:4290-4311). The behavior change is purely in what the mask layer contains; the LaMa dispatch code is untouched (D-02). Silent + undo-recovers preserved.
- **Override flips:** BOXES entries — the Inspector commit handler captures `canvas.boxes_snapshot()` as the before-state and pushes via the existing `boxes_modified` path (the `_on_boxes_modified` hook, main_window.py:2879-2930). Multi-box override apply = ONE snapshot (Phase 7 D-09/D-10 grouped-op pattern, `set_pending_boxes_op_name`).
- **Mask strokes under the layered model:** MASK stack semantics unchanged in *mechanism* (full-QImage before-states, HistoryManager is QImage-generic, history_manager.py:125-201) but the snapshotted QImage becomes the **manual plane** for paint strokes and the **erase ledger** for erase strokes (both plain QImages — zero HistoryManager changes). `_pre_stroke_mask` (main_window.py:2827-2877) tracks the active plane's before-state; the first-stroke clean-baseline seeding (transparent QImage, :2869-2871) applies per plane — and note the semantic shift: undoing the first stroke now removes only the manual contribution, leaving the auto plane — correct per the new model, but the 03-08 test expectations need re-basing.
- **Non-undoable by design:** detection/baseline (existing), radius/threshold changes (settings), recompositions. Box move/resize already pushes BOXES (geometry snapshots); the auto plane recomposes on apply — no new stack needed.
- **Page switch:** `reset_history` (main_window.py:2813-2825) already clears `_pre_stroke_mask`; extend the per-page reset to any new plane tracking. Plane persistence rides `on_page_selected` Steps 1/4 (manual+erase planes as QImages like today's mask; raw heatmap + per-box state via `ImageFile`).

---

## 10. Test Strategy & Existing Patterns

- **Interpreter:** pinned `C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe` (AGENTS.md). Suite baseline at research time: **717 collected**.
- **Markers:** `unit` (no Qt, no weights) / `gui` (PySide6 + display, pytest-qt `qt_api=pyside6`) — pytest.ini.
- **The detection-seam fake pattern** (tests/test_gui_detection_boxes.py:47-73): drive `MainWindow._on_detection_finished(result)` directly with `{"mask": np zeros (H,W), "blocks": [SimpleNamespace(xyxy=[...])]}`; `_window_with_page` loads a real small PNG so V5 clamping has true dims; `_confirm_replace_boxes` patched with `return_value=True`; QSettings isolated to a tmp INI (:75-88). Phase 8's seam tests extend exactly this harness (add a nonzero heatmap region inside a box; assert the auto plane/mask layer content, per-box mask/std_dev, border states, discard behavior).
- **Headless masker tests:** the machinery is pure PIL/numpy/scipy — build synthetic pages (PIL `Image.new("RGB", ...)` with a uniform box region + text-like strokes; a noisy region for the gate-fail case) and call `grow_mask`/`mask_intersection`/`border_std_deviation`/`pick_best_mask` directly. **No torch/LaMa anywhere near these tests** (the adapters are fakeable anyway — test_ctd_adapter.py/test_lama_adapter.py patterns — but the seam tests don't need even those).
- **First real callers:** today `pick_best_mask`/`border_std_deviation` are only import-tested (tests/test_core/test_masker_vendor.py:68-88, test_structures.py:101-120). Phase 8 should include a small battery locking actual behavior (std of a uniform border ≈ 0; gate fails on a textured border; grow_mask grows exactly N px; intersection discards; BlankMaskError on empty) — these double as living documentation of the contracts in §1.
- **GUI dispatch tests (MASK-06):** QTest mouse presses at scene-mapped positions (the `mapFromScene` pattern from 01-04, zoom-exact lessons from 05-09: test at `zoom_reset()` for exact coordinates) asserting `_is_painting` under a box, Alt+click selection, Alt+drag move, crop unchanged, double-click editor unchanged.
- **Persistence tests:** extend test_project_io.py (optional-key round-trip, legacy-file-without-new-fields loads clean — the `test_legacy_mas_without_style_loads_with_defaults` template at :175) and test_box_persistence.py (plane round-trip via the D-11 seam).
- **Batch tests:** test_batch_runner.py drives `_run_batch_task` with fake models (`det_model.detect` returning `(heatmap, blk_list)` — see existing fakes) — extend for constrained-mask + boxes population.

---

## 11. Upstream PanelCleaner Reference (D-06, GPL v3)

- `../PanelCleaner/pcleaner/gui/profile_parser.py:426-526` — the generated profile UI (structure from `bundle_config(gui_mode=True)`, types→widgets, comments→help). OUR UI is a hand-built subset in ToolsPanel, but presentation conventions (labels from option names, INI comments as tooltips, per-option reset-to-default) are the reference.
- `../PanelCleaner/pcleaner/masker.py` — the canonical `pick_best_mask` driver (already vendored verbatim at panelcleaner/masker.py with the `output_structures` ImportError guard, masker.py:34-37).
- `../PanelCleaner/pcleaner/image_ops.py` — identical machinery (our vendored copy at panelcleaner/image_ops.py, offsets differ by the module header).
- `../PanelCleaner/pcleaner/gui/image_file.py:278-281` — where PC's GUI displays masker analytics (std-dev visualization) — relevant later for polish, not needed now.

---

## 12. Established Patterns to Reuse (with evidence)

1. **Worker + result-dict seam** — `_run_detection_task` returns `{"mask", "blocks"}` already (main_window.py:3796); Phase 8 consumes both without adapter/worker changes (03-RESEARCH's "one-line thread-through" insight, now fully realized).
2. **`.copy()` buffer discipline at every numpy↔Qt/PIL bridge** (Pitfall 2) — mask_editor.py bridges, `on_page_selected` Steps 1/4, history push/pop.
3. **D-11 per-page persistence seam** (`_last_page_index` outgoing-index rule, main_window.py:1664-1850) — extend for the new planes + raw mask + per-box state; the 02-02/03-05 regression tests are the templates.
4. **Before-state undo pushes** — MASK (`_pre_stroke_mask`), BOXES (`boxes_modified(before)` payload), IMAGE (pre-edit patch).
5. **`_suppress_boxes_push` guard** around restore-path `set_boxes` (main_window.py:3985, 1833, 1288) — the new recompose/restore paths must use the same guard discipline (and must not emit `mask_modified`).
6. **InspectorPanel follower + commit-handlers + Mixed** (inspector_panel.py:546/633; `connect_commit_handlers` main_window.py:2772-2786) — the override field plugs straight in; multi-select Mixed = the Phase 7 D-10 pattern (combobox "Mixed" entry).
7. **Optional-key .mas evolution** (project_io.py:236-240 + test_project_io.py:175).
8. **Grouped-op single snapshot + op-name flash** (Phase 7 D-09, canvas.py:1240-1244, main_window.py:2904-2918) — multi-box override apply.
9. **Pure-function extraction for headless reuse** (the 05-08 ExportPage precedent) — extract box-build + mask-derivation cores so batch and GUI share them.
10. **QSettings isolation in GUI tests** (`_isolate_settings`, test_gui_detection_boxes.py:75-88).

---

## 13. Pitfalls (file:line evidence)

1. **`set_mask` full-replaces and emits nothing** (canvas.py:449-496) — any new flow that calls it clobbers strokes; under the layered model only the mask-only mode (D-03) should call it.
2. **Detection currently composites the FULL heatmap BEFORE box building** (main_window.py:3881-3897) — the reorder must handle the D-04 Cancel aborting *after* the mask is already set (§3.2 item 6); today Cancel leaves the new full-page mask in place even when the box build aborts (pre-existing quirk; worse under D-02 semantics).
3. **`_confirm_replace_mask` copy promises manual edits are lost** (main_window.py:4101-4104) — false under the layered model (§2.4).
4. **`PageBox.manual_override` name is TAKEN** (box_model.py:99-101, Phase 4 reading-order pin) — the tri-state inpaint override must use a new field name; serialization + Inspector must not collide.
5. **`PageBox.copy()` detaches only payload + style** (box_model.py:191-193) — Pitfall 8: the new per-box mask (if a mutable PIL object) must be detached here too or undo restores post-edit masks (the 04-05 lesson).
6. **Geometry transforms rebuild PageBox with explicit field lists and DROP unlisted fields** — `style` already dropped today (core/image_ops.py:156-163, 283-290, 370-420); new fields would be too (§6.5).
7. **Heatmap→mask thresholding:** `set_mask` thresholds any non-zero pixel (canvas.py:480); PIL "1" conversion must threshold explicitly + `dither=Image.NONE` (masker.py:72) — a dithered convert would invent mask pixels.
8. **`border_std_deviation` raises `BlankMaskError` on empty masks** (image_ops.py:513-515) — per-box calls on boxes with no detected text must catch it (or pre-check `getbbox()` like pick_best_mask:631-639 does) instead of crashing the detection handler.
9. **`pick_best_mask` returns `None` for noise boxes** (image_ops.py:632-639) — a legitimate outcome meaning "no auto mask for this box", distinct from `failed` (std too high); the state model needs both.
10. **BOXES snapshots carry the whole PageBox list** (`boxes_snapshot`, canvas.py:1821) — once PageBox carries per-box masks (PIL objects), every BOXES push/memory entry copies them unless detached cheaply (Pitfall 3/8; `_materialize_snapshot` copies members with `.copy()`, history_manager.py:298-321 — PIL Image.copy() exists, so it works, but snapshot weight grows).
11. **Eraser uses `CompositionMode_Clear`** (mask_editor.py:96) — under the layered model an erase must ALSO write to the ledger plane or it's lost on recompose (§2.2).
12. **`ImageFile.mask` is a QImage and batch constructs QImages off-thread** (batch_runner.py:156) — precedented, but keep new per-page numpy/PIL state out of Qt types where possible for the worker path.
13. **The first-press-paints-dot before double-click editor** under paint tools (§7.2) — visible behavior change; decide consciously.
14. **Per-mousemove recomposition cost** — never recompose the composite inside `mouseMoveEvent` (paint into the display buffer live, recompose at commit; §2.2).
15. **`Profile.load` swallows all exceptions** → defaults (config.py:1031-1034) — a corrupt profile INI silently reverts masker params; acceptable (upstream behavior) but tests should not assume persistence succeeded blindly.

---

## 14. Open Questions (for the planner)

1. **Q1 — Full `pick_best_mask` vs gate-only** (§1.4 Fork A/B): D-06 exposes growth/selection params, implying Fork A; Fork B is simpler and makes several D-06 controls no-ops. Recommend Fork A (params real, machinery finally used) with the dilation radius applied to the precise mask before growth.
2. **Q2 — Dilation composition:** dilate raw heatmap then ∩ boxes, or ∩ boxes then dilate? (Dilate-then-∩ discards growth beyond the box edge — probably desired: the box certifies the region; recommend ∩-then-dilate but clamp visually at box edges? Actually ∩-then-dilate can bleed past the box border by `radius` px — decide whether auto content may exit its box.) Also: does the MASK-01 radius apply in mask-only mode (D-03)? (Recommend yes — it's the 01-UAT origin story.)
3. **Q3 — Field name + tri-state encoding** for the override (e.g. `inpaint_override: Optional[Literal["always","never"]]`, None=Auto) and whether it lives on PageBox (rides BOXES snapshots + `.mas`) — recommend yes.
4. **Q4 — std_dev recomputation on box move/resize:** recompute-on-release (recommend) vs stale-state demotion; and whether a *user-drawn* box triggers a fit at creation time (all boxes certify — natural reading; recommend fitting user boxes too, at create-commit and on move-release).
5. **Q5 — Per-box mask on move:** translate the stored mask vs refit against the new region (recommend refit — translation over artwork is wrong).
6. **Q6 — `.mas` persistence of the raw heatmap** (§6.4) and the per-box mask container format (§6.3).
7. **Q7 — Geometry-op policy for the new fields** (§6.5): invalidate vs transform (and whether to fix the pre-existing `style` drop in the same touch — scope call, likely a separate micro-fix).
8. **Q8 — Gate semantics on the mask layer:** confirm the reading that gate-failed/Never boxes contribute NOTHING to the mask layer (so an unchanged LaMa call naturally skips them) rather than the gate filtering inside the inpainter (D-02 settles this — but the *border-state vs mask-display* relationship should be stated explicitly in the UI spec).
9. **Q9 — Detect Boxes toggle persistence home** (QSettings view-state vs profile INI; recommend QSettings/view-state — it's a mode, not a quality param).
10. **Q10 — Dirty-flag semantics** for detection/re-dilate (settings changes that alter page output — do they mark the session dirty?).

---

## Validation Architecture

**Layer 1 — headless unit tests (`unit` marker, no Qt, no model weights).** The bulk of the phase:
- Masker machinery battery (§10): `grow_mask`, `mask_intersection`, `border_std_deviation` (uniform vs textured synthetic borders, BlankMaskError), `pick_best_mask` end-to-end on a synthetic page (fit found / failed / None-noise), `compose_masks` paste math.
- The extracted seam core (pure function): heatmap+blocks+boxes+MaskerConfig → per-box (mask, std_dev, state) + constrained auto-plane binary. Assert: out-of-box heatmap content discarded (D-02); dilation radius grows auto only (D-07); user boxes certify; gate threshold behavior; overrides force/skip; zero-boxes page → empty auto plane; mask-only mode → full heatmap.
- `inpaint_state(threshold)` pure-function states (will/skipped/forced/never/none).
- Model: `PageBox` new fields default None; `copy()` detachment (Pitfall 8); override field round-trip through `pagebox_to_json`/`json_to_pagebox` including legacy-without-new-keys (the test_project_io.py:175 template); geometry-op invalidation policy.
- Profile: MaskerConfig+dilation INI round-trip via `Profile.safe_write`/`Profile.load` (conftest `profile_manager` fixture, tmp_config_dir).

**Layer 2 — GUI tests (`gui` marker, pytest-qt).**
- Detection seam: extend the test_gui_detection_boxes.py harness — nonzero heatmap region inside/outside a box; assert canvas mask content (via `mask_to_numpy_binary`), per-box `mask`/`std_dev` populated, border-state pens, D-04 Cancel leaves boxes AND auto plane consistent, D-03 mode-off preserves Phase 1 behavior byte-for-byte.
- MASK-06 dispatch: QTest presses at `zoom_reset()` — paint under box bodies and handles; Alt+click select; Alt+drag move (group-move machinery); Alt+drag on empty creates; crop unchanged (press on box still selects); double-click editor opens; Shift+click paints (no toggle).
- Layered canvas: paint stroke → composite contains stroke ∪ auto; eraser removes auto pixel AND survives a radius change (re-dilate) without resurrection (the §2.2 ledger invariant — the single most load-bearing regression test of the phase); undo/redo of strokes under the layered model; re-dilate slot updates mask without re-detect (D-08).
- Tools panel: detection-settings controls bind/read the profile object; dilation change triggers recompose; keyboard reachability of new controls.
- Inspector: override field commits push ONE BOXES snapshot; multi-select Mixed presentation; border states flip live on override/threshold change (D-12).
- Batch: fake-model `_run_batch_task` (detect / detect_and_clean) populates `ImageFile.boxes` + constrained masks; empty-mask passthrough on zero gate-passing boxes.

**Layer 3 — manual UAT (end-of-phase gate).** Visual truth the suites can't check: letter edges covered at radius 2 on real pages (the 01-UAT origin story); gate behavior on real bubbles vs artwork; border-state color legibility (deferred token check to `/gsd-ui-phase 8`); paint-under-boxes feel; re-dilate latency while dragging the radius slider; batch output quality on a real chapter (the Phase 2 deliberate re-verification stance applies).

**Explicitly NOT testable headlessly / out of scope:** LaMa output quality (unchanged call), CTD model quality, torch paths (keep every new test off the torch import graph).

---

*Research complete; ready for `/gsd-plan-phase 8`.*
