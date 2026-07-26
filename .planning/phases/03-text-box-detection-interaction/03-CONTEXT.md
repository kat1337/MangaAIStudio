# Phase 3: Text Box Detection & Interaction - Context

**Gathered:** 2026-07-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver **two** requirements (the first half of the text/OCR track — no recognition yet):

1. **TEXT-01** — Run text-box detection across a page to create editable text-box **objects** (not a pixel mask).
2. **TEXT-03** — Select, move, resize, and delete text boxes on the canvas to correct detection errors (and create new boxes by drawing).

The central insight: **the detection model already produces the boxes — Phase 1 just throws them away.** CTD's `TextDetector.__call__` returns a 3-tuple `(mask, mask_refined, blk_list)` (`panelcleaner/comic_text_detector/inference.py:210`), and `TorchCTDModel.detect()` (`adapters/torch_impl.py:104-129`) already returns `(mask_refined, blk_list)` to the GUI — but `_on_detection_finished` (`main_window.py:1284`) reads only `result["mask"]` and discards `blk_list`. Phase 3 surfaces those `TextBlock` objects as first-class, editable canvas items so the user can correct detection before OCR runs in Phase 4.

**In scope:** (a) wire `blk_list` from the existing CTD call into a new boxes layer; (b) render each `TextBlock.xyxy` as an interactive `QGraphicsRectItem` with corner resize handles; (c) select / move / resize / delete boxes; (d) draw-to-create a user-origin box; (e) a 3rd undo stack (BOXES) merged into a unified Ctrl+Z timeline; (f) per-page box persistence across navigation (mirrors Phase 2 D-11 mask persistence).

**Out of scope (later phases):** running manga-ocr on a box to fill its text (TEXT-02 — Phase 4), inline editing of recognized text (TEXT-04 — Phase 4), manual translation field (TEXT-05 — Phase 4), batch box-detection across a chapter (a future batch extension), `.mas` save/load of boxes (PROJ-01 — Phase 5), `_ocr.json` box export (PROJ-03 — Phase 5), multi-select / marquee selection of boxes (optional polish — Phase 3 is single-select), vertical-text / rotated-box rendering and typesetting (Out of Scope per PROJECT.md — v2+).

</domain>

<decisions>
## Implementation Decisions

### Detection entry point
- **D-01:** **One Detect action with a mode toggle** (mask + boxes vs mask-only). CTD's single model pass already yields both the heatmap mask AND `blk_list`; Phase 3 surfaces the boxes instead of discarding them. The mode toggle controls whether the Detect action emits just the mask (Phase 1 behavior, preserved) or mask + boxes (Phase 3 new). No separate "Detect Boxes" action, no second model pass.
- **D-02:** **Boxes are a separate layer** on the canvas — independent of the mask overlay, toggleable on/off like the mask overlay is (View → Toggle Box Overlay, mirroring the existing View → Toggle Mask Overlay / `M`). The mask layer and the box layer coexist; showing/hiding one does not affect the other. Z-order on the scene: image → mask overlay → box layer → tool preview/cursor (top).
- **D-03:** **Re-running detection replaces detected boxes but preserves user boxes.** A box carries an `origin` flag (`"detected"` vs `"user"`). On re-detect, the `"detected"` set is replaced wholesale by the fresh `blk_list`; `"user"` boxes survive. This mirrors Phase 2 D-02 ("hand-edits before inpaint are sacred") — user corrections are never silently discarded by a re-detect. Dedup/overlap handling of detected-vs-user is a planner detail.
- **D-04:** **Per-page only, with a confirm gate.** Phase 3 box detection runs on the current page (TEXT-01 says "across a page"). Batch box-detection is deferred. Running detection on a page that already has boxes prompts a confirm (mirroring Phase 1's `_confirm_replace_mask` gate, `main_window.py:1328`).

### Box object & interaction model
- **D-05:** **Each box is a `QGraphicsRectItem` subclass** with four child handle items at the corners for resize. Native Qt selection (dashed outline) + drag-to-move come free from the Graphics View framework; resize is implemented via the corner handles. This fits the existing `QGraphicsScene` stack directly (the canvas is already a `QGraphicsView`; image/mask/preview/cursor items are all `QGraphics*Item`). Box z-value sits above the mask overlay, below the tool preview/cursor.
- **D-06:** **Resize by dragging a corner handle** (user's explicit requirement). The four corner handles are the resize affordance; edges are not independently resizable in v1 (corner-drag resizes both adjacent edges). Minimum box size enforced to avoid zero-area boxes.
- **D-07:** **Boxes are always interactive when the box layer is visible** — no new tool mode added to the existing 5-tool `QActionGroup` (Move/Brush/Rect/Lasso/Eraser). Click on a box → selects/moves it; click on empty canvas with a mask tool active → paints mask as today. The hit-test is "is the click on a box item?" (Qt does this natively); if yes, route to box interaction, else fall through to the active mask tool. The box layer being hidden disables box interaction entirely.
- **D-08:** **Single-select.** One box selected at a time. Move/resize/delete act on the selected box. Multi-select (shift-click) and marquee selection are out of scope for v1 (TEXT-03 is singular: "select, move, resize, delete").
- **D-09:** **Color boxes by origin** so the user can see which boxes re-detect would replace vs keep (the D-03 rule). Detected boxes and user-created boxes use distinct border styles drawn from the existing UI-SPEC color tokens (accent `#00d4ff` reserved use, etc. — researcher/planner pick the exact pair consistent with `.planning/phases/01-cleaning-workspace/01-UI-SPEC.md` and the theme).

### Box edits & undo
- **D-10:** **Add a 3rd undo stack, BOXES, alongside MASK and IMAGE** — preserving Phase 1's per-type snapshot semantics. Each box op (move, resize, delete, create) pushes a record onto the BOXES stack (bbox before/after, box identity, op type). Do NOT collapse Phase 1's two stacks into one — the per-type shape and the UI-SPEC 2-stack contract (`01-CONTEXT.md` D-01-06: "two logical stacks (MASK + IMAGE) not four") are preserved; BOXES is a third sibling.
- **D-11:** **Unified Ctrl+Z / Ctrl+Shift+Z over a merged timeline.** The three underlying stacks (MASK, IMAGE, BOXES) stay separate, but Ctrl+Z pops the most-recent-by-timestamp entry across all three; Ctrl+Shift+Z redoes likewise. One shortcut pair, chronological, no stack-switching exposed to the user. (This reconciles the user's two answers: "3rd BOXES stack" + "unified Ctrl+Z" = three stores, one merged pop order.) The Phase 1 shortcuts (`Ctrl+Z` mask, `Ctrl+Shift+Z` image, plus the `Alt+Z` variants) are subsumed by the unified timeline — researcher/planner confirm the exact final binding set against `01-CONTEXT.md` and the Phase 1 UI-SPEC.
- **D-12:** **Delete box is immediate and silent** — no confirm dialog. Deleting false-positive detections is the most common correction, so friction is unwanted. Safety comes from D-10/D-11: Delete pushes onto the BOXES stack, so Ctrl+Z recovers it. (Contrast with destructive image ops like Clear Mask, which DO confirm — boxes are cheap to undo.)
- **D-13:** **Draw-to-create a user box is in Phase 3 scope.** A click-drag on empty canvas (box layer visible) with the create-box gesture creates a new `"user"`-origin box (empty — no text yet; OCR to fill it is Phase 4 / TEXT-02). This makes TEXT-03's correction workflow complete without waiting for Phase 4, and gives the D-03 "user boxes survive re-detect" rule something to preserve. The exact gesture (a dedicated create mode, a modifier+drag, or a 6th tool) is a planner decision — but it is NOT a 6th always-present tool in the mask `QActionGroup` (D-07 stands: no new tool mode for selecting/moving boxes).

### Claude's Discretion
- **Exact color/style pair for detected-vs-user boxes** (D-09) — pick from the UI-SPEC color tokens; keep contrast against the dark canvas matte `#0b0b0e`.
- **The draw-to-create gesture** (D-13) — modifier+drag vs a transient create-mode vs a toolbar button. Choose what is least surprising alongside D-07's "boxes always interactive" rule.
- **Whether `blk_list` `TextBlock` objects are wrapped in our own `Box` data class or used directly** — `TextBlock` (`panelcleaner/comic_text_detector/utils/textblock.py`) already carries `xyxy`, `lines`, `text`, `translation`, `vertical`, `language`, `font_size` (richer than Phase 3 needs, but the `text`/`translation`/`vertical` slots are exactly what Phase 4 consumes). A thin `Box` wrapper adding the `origin` flag (D-03) + stable identity for undo (D-10) is likely cleaner than mutating `TextBlock` directly; researcher/planner decide.
- **Box-data persistence shape** (per-page, alongside Phase 2's `ImageFile.mask`) — extend `core/image_file.py:ImageFile` with a `boxes` slot (mirrors the `mask` slot pattern from Phase 2 D-11) vs a new page-state structure. The `ImageFile` extension is the path of least resistance and matches D-11 of Phase 2; planner confirms.
- **Box-undo record granularity** (full boxes-list snapshot per op vs per-op diff records) — Phase 1 used full QImage snapshots for mask/image; boxes are lightweight (a list of bboxes), so a full per-page boxes snapshot per op is cheap and matches the Phase 1 shape. Planner decides.
- **Confirm-gate copy for re-detect with existing boxes** (D-04) — mirror `_confirm_replace_mask`'s tone.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Foundation
- `.planning/PROJECT.md` — PanelCleaner (GPL v3) foundation; single-env in-process `QThreadPool` (D-07/D-09b fallback is the active choice); model adapter interface; frontend/backend env split. **Phase 3 boxes reuse the detection adapter, not a new model.**
- `.planning/REQUIREMENTS.md` — **TEXT-01** (run text-box detection → editable box objects, not a pixel mask) and **TEXT-03** (select/move/resize/delete boxes). Traceability maps both to Phase 3.

### Phase Scope
- `.planning/ROADMAP.md` §Phase 3 — Goal, success criteria (2), requirements mapping (TEXT-01, TEXT-03), "UI hint: yes", Depends on Phase 1.

### Prior Phase Context (carries forward)
- `.planning/phases/01-cleaning-workspace/01-CONTEXT.md` — the foundation: model adapter interface (D-01/D-02), code organization (D-10: `adapters/` + `panelcleaner/` vendored + `gui/` + `core/`), the 2-stack undo contract (D-01-06 of Phase 1), Pitfall-2 `.copy()` discipline, single-env in-process execution.
- `.planning/phases/02-cleaning-output-batch/02-CONTEXT.md` — **D-11 per-page mask persistence pattern** (the exact seam Phase 3's per-page box persistence mirrors: save on navigation, restore on page-select, `.copy()` at both boundaries), the `ImageFile.mask` slot + `has_mask_content` reuse pattern, the `Worker(QRunnable)` + `SharableFlag` abort + `_op_running` gate, status-bar progress reuse.

### Source References (PanelCleaner — GPL v3, the reference to reuse for boxes)
- `panelcleaner/comic_text_detector/inference.py` — **`TextDetector.__call__`** (class at line 130, return at line 210): `return mask, mask_refined, blk_list`. **This is THE load-bearing fact** — box detection needs no new model; `blk_list` is already produced by the Phase 1 detect call. The 3-tuple unpack is verified in `torch_impl.py:124`.
- `panelcleaner/comic_text_detector/utils/textblock.py` — **`TextBlock`** class: fields `xyxy` (bbox `[x1,y1,x2,y2]`), `lines` (per-line polygons), `text` (list), `translation` (str), `vertical` (bool), `language`, `font_size`, `angle`, `vec`, `norm`. Phase 3 uses `xyxy` (+ maybe `lines` for finer handles); the `text`/`translation`/`vertical`/`language` slots are reserved for Phase 4 OCR and Phase 5 export — do not strip them.
- `../PanelCleaner/pcleaner/gui/image_diff_viewers.py` and `output_review_driver.py` — PanelCleaner's own review viewers; check (during research) whether they already render `TextBlock` boxes as interactive `QGraphicsRectItem`s we can pattern off. (Initial grep found no `QGraphicsRectItem` in PanelCleaner GUI — likely they DON'T have interactive box editing; MangaCleaner_GPU canvas + Qt Graphics View framework are the actual references. Researcher confirms.)
- `../PanelCleaner/LICENSE` — GPL v3; derivative works must be GPL v3 (boxes-layer code is our own, not vendored, but the `TextBlock` consumption is derivative use).

### Existing Code (Phase 1 + 2 — what Phase 3 builds on)
- `manga_ai_studio/adapters/torch_impl.py` — **`TorchCTDModel.detect(image) → (mask_refined, blk_list)`** (lines 104-129). ALREADY returns `blk_list`; Phase 3 just needs the caller to stop discarding it. The 3-tuple unpack (`mask, mask_refined, blk_list`) at line 124 is verified.
- `manga_ai_studio/gui/main_window.py` — **`_on_detection_finished`** (line 1284): currently reads only `result["mask"]` and ignores any boxes. **This is the seam to change.** Also: `_run_detection_task` (1165), `_confirm_replace_mask` (1328, the confirm-gate pattern for D-04), `compute_mask_bbox` (2058), `_build_menus` (187) / `_build_tools_menu` (337) / `_build_toolbar` (413) for where the box-toggle + create actions wire, `_build_status_bar` (471), `set_active_tool` (1059), `_refresh_action_states` (529), the `_op_running` gate.
- `manga_ai_studio/gui/canvas.py` — **`EditorCanvas(QGraphicsView)`** with `QGraphicsScene`. Layered items: `image_item`, `mask_item`, `preview_item` (z=900), `cursor_item` (z=1000), empty-state text (z=2000). **Box items go in a new layer between `mask_item` and `preview_item`.** Reuse: `set_image` / `set_image_from_path` / `set_image_from_numpy`, `_scene_pos` (sub-pixel scene mapping), `get_image_numpy`, mouse-event dispatch in `mousePressEvent`/`mouseMoveEvent`/`mouseReleaseEvent` (758-837) — box hit-testing slots in alongside the existing mask-tool dispatch.
- `manga_ai_studio/gui/tools_panel.py` — **`ToolsPanel`** + the `QActionGroup` exclusive-tool pattern. D-07 says NO new tool mode for boxes, so this file likely needs no change for selection/move (boxes are always interactive); a create-box gesture (D-13) MAY add a transient control here or elsewhere — planner decides.
- `manga_ai_studio/core/image_file.py` — **`ImageFile`** dataclass (`path`, `thumbnail`, `mask`, `dirty`). D-11 (Phase 2) added per-page mask persistence; Phase 3 adds a `boxes` slot here (Claude's Discretion) mirroring the `mask` slot.
- `manga_ai_studio/core/history_manager.py` — **the 2-stack HistoryManager** (MASK + IMAGE). D-10 adds a 3rd stack (BOXES); D-11 merges the pop order into a unified timeline. Researcher reads this to design the BOXES stack + merged-timeline pop.
- `manga_ai_studio/gui/worker_thread.py` — `Worker(QRunnable)` + `WorkerSignals` + `SharableFlag`. Box detection reuses the SAME detection worker Phase 1 already runs (no new worker needed — `blk_list` rides along on the existing `result` dict).
- `manga_ai_studio/core/mask_editor.py` — `ToolMode` enum (MOVE/BRUSH/RECTANGLE/LASSO/ERASER). D-07 keeps this enum unchanged for v1.

### UI / Design contract
- `.planning/phases/01-cleaning-workspace/01-UI-SPEC.md` — the design contract: color tokens (accent `#00d4ff` reserved use #1, mask overlay `rgba(255,0,0,0.63)`, canvas matte `#0b0b0e`, secondary surface `#2d2d33`), spacing scale, the 2-stack undo UI contract (surface 8). D-09 (box colors) and D-11 (merged undo) must stay consistent with this. **Phase 3 has `UI hint: yes` — a `/gsd-ui-phase 3` pass will likely follow this discuss step.**

### Licensing
- `../PanelCleaner/LICENSE` — GPL v3. Box-layer code is our own; consumption of `TextBlock` from the vendored PanelCleaner tree is derivative use under GPL v3 (consistent with Phase 1 D-12).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`TorchCTDModel.detect()` already returns `blk_list`** (`adapters/torch_impl.py:104`) — the box data is free; Phase 3 wires it through. No model work, no new adapter, no new worker.
- **`EditorCanvas`'s `QGraphicsScene`** — `QGraphicsRectItem` is a first-class scene item; selection, move, z-ordering, hit-testing are native Qt. Corner resize handles = child `QGraphicsRectItem`s (standard Qt pattern). The canvas's existing layered-item setup (`image_item` → `mask_item` → `preview_item` → `cursor_item`) has a clear slot for a boxes-group/layer between `mask_item` and `preview_item`.
- **Phase 1 detection worker + dispatch** (`_run_detection_task` → `_on_detection_finished`) — `blk_list` just needs to be added to the worker's `result` dict and read in the finished handler. The `_op_running` gate, progress UI, and error path already work.
- **`Worker(QRunnable)` + `SharableFlag`** (`gui/worker_thread.py`) — unchanged; box detection is the same async op as mask detection.
- **`ImageFile` + Phase 2 D-11 persistence seam** (`core/image_file.py`, `main_window.on_page_selected`) — the exact pattern (save outgoing page's state, `.copy()` at both boundaries, restore incoming) is reused for boxes. The `mask` slot + `has_mask_content` are the template for a `boxes` slot.
- **`HistoryManager`** (`core/history_manager.py`) — the 2-stack shape extends to a 3rd (BOXES); the merged-timeline pop (D-11) is the new wrinkle researcher/planner design.
- **`compute_mask_bbox`** (`main_window.py:2058`) — bbox-from-mask helper; may inform user-box creation if a "box from mask region" path emerges (not required, but available).

### Established Patterns
- **Pitfall 2 (`.copy()` buffer discipline)** — every numpy↔QImage / numpy↔history bridge detaches. Box data is bbox tuples (not pixel buffers), so Pitfall 2 applies mainly where box state meets QImage snapshots in the BOXES undo stack — researcher keeps the discipline.
- **In-process `QThreadPool` (Phase 1/2 D-09b)** — single env, models called off the GUI thread via `Worker`. Box detection follows identically (it IS Phase 1 detection).
- **2-stack undo (Phase 1 D-01-06)** — "two logical stacks (MASK + IMAGE) not four"; Phase 3 extends to THREE (MASK + IMAGE + BOXES), preserving the per-type shape. The Phase 1 CONTEXT warning against "a 4-stack interpretation" is honored — BOXES is one logical stack, not split per-op-type.
- **Per-page persistence `.copy()` at both boundaries** (Phase 2 D-11 / T-02-04) — the boxes slot follows the same belt-and-suspenders copy discipline as the mask slot.
- **Confirm-gate before destructive replace** (`_confirm_replace_mask`, `main_window.py:1328`) — D-04's box re-detect confirm mirrors this. Delete-box does NOT confirm (D-12 — undo recovers).
- **Thread-safety contract (T-01-07)** — worker tasks touch only numpy/Python + emit signals; Qt mutation only in main-thread handlers. The boxes-rendering happens in `_on_detection_finished` (main thread), so it's safe.

### Integration Points
- **`_on_detection_finished`** (`main_window.py:1284`) — primary seam: stop discarding `blk_list`, build box items, add them to the canvas's box layer.
- **`EditorCanvas`** — new methods for add/remove/move/resize/delete box, toggle box layer, box-layer hit-testing in the mouse-event dispatch.
- **`ImageFile`** — new `boxes` slot; `on_page_selected` save/restore seam extended (Phase 2 D-11 pattern).
- **`HistoryManager`** — new BOXES stack + merged-timeline pop.
- **`_build_menus` / `_build_view_menu` / `_build_toolbar`** — View → Toggle Box Overlay action; whatever create-box gesture (D-13) lands; status-bar reflects box count if useful.
- **`ToolsPanel` + `ToolMode`** — UNCHANGED for v1 per D-07 (no new tool mode for box selection/move).

</code_context>

<specifics>
## Specific Ideas

- **"We'll be reusing a lot of the code PanelCleaner uses for box detection, but we'll allow modifying the box size by dragging the corner to resize them."** (User, Area selection.) — Confirms: (a) box detection = the CTD `blk_list` PanelCleaner already produces (no new detector); (b) corner-drag resize is an explicit, locked requirement (D-06). This is the phase's defining user-facing behavior.
- **Boxes are correction objects, not display objects.** TEXT-01/TEXT-03 frame boxes as "editable objects to correct detection errors" — Phase 3 does NOT render OCR text inside the boxes (that is Phase 4). The box is a selectable, movable, resizable rectangle whose `TextBlock` payload is carried for later phases. Researcher/planner keep the Phase 3 box visually minimal (border + handles, no inline text rendering).
- **Detected vs user-added must be visible.** The D-03 "re-detect replaces detected, keeps user" rule only works if the user can SEE which is which — hence D-09 color-by-origin. This is not decorative; it's how the user predicts what a re-detect will do.

</specifics>

<deferred>
## Deferred Ideas

- **OCR text recognition inside boxes (TEXT-02 draw-to-OCR, TEXT-04 inline text edit, TEXT-05 translation field)** — Phase 4. The `TextBlock.text`/`translation`/`vertical` slots are preserved through Phase 3 so Phase 4 can fill them; Phase 3 does not touch them.
- **Batch box-detection across a chapter** — a future batch extension (Phase 2's `batch_runner` shape could grow a box-detect mode, but that is not in Phase 3's per-page scope).
- **`.mas` project save/load of boxes (PROJ-01) and `_ocr.json` export (PROJ-03)** — Phase 5. Phase 3 persists boxes per-page in-memory (and across navigation) but does NOT serialize them to disk yet.
- **Multi-select / marquee selection of boxes** — optional polish; Phase 3 is single-select (D-08).
- **Edge handles (resize one edge independently), rotated/vertical box rendering, bubble auto-sizing** — Out of Scope per PROJECT.md (v2+ typesetting territory).
- **Inline text rendering / typesetting inside boxes** — Out of Scope (BallonsTranslator territory; PROJECT.md Out of Scope table).

</deferred>

---

*Phase: 3-Text Box Detection & Interaction*
*Context gathered: 2026-07-25*
