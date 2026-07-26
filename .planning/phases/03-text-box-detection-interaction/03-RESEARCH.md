# Phase 3: Text Box Detection & Interaction - Research

**Researched:** 2026-07-25
**Domain:** PySide6/Qt6 desktop QGraphicsView canvas — adding an editable text-box layer; PanelCleaner source vendoring (structures.py + masker.py); per-box std-deviation seam for a deferred selective inpaint.
**Confidence:** HIGH (all claims verified against local source files — `../PanelCleaner/pcleaner/`, the vendored `panelcleaner/` tree, and `manga_ai_studio/`; web search providers are disabled in this config, but local source is the highest-authority source for this phase anyway).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Detection entry point**
- **D-01:** One Detect action with a mode toggle (mask + boxes vs mask-only). CTD's single model pass already yields both the heatmap mask AND `blk_list`; Phase 3 surfaces the boxes instead of discarding them. No separate "Detect Boxes" action, no second model pass.
- **D-02:** Boxes are a separate layer on the canvas — independent of the mask overlay, toggleable on/off (View → Toggle Box Overlay, `Shift+M`). Z-order: image → mask overlay → box layer → tool preview/cursor (top).
- **D-03:** Re-running detection replaces detected boxes but preserves user boxes. A box carries an `origin` flag (`"detected"` vs `"user"`). On re-detect, the `"detected"` set is replaced wholesale by the fresh `blk_list`; `"user"` boxes survive.
- **D-04:** Per-page only, with a confirm gate. Running detection on a page that already has boxes prompts a confirm (mirroring `_confirm_replace_mask`, main_window.py:1328).

**Box object & interaction model**
- **D-05:** Each box is a `QGraphicsRectItem` subclass with four child handle items at the corners for resize. Native Qt selection (dashed outline) + drag-to-move come free; resize via corner handles. Box z-value above the mask overlay, below the tool preview/cursor.
- **D-06:** Resize by dragging a corner handle. Four corner handles are the resize affordance; edges are not independently resizable in v1. Minimum box size enforced (8×8 scene px) to avoid zero-area boxes.
- **D-07:** Boxes are always interactive when the box layer is visible — no new tool mode added to the existing 5-tool `QActionGroup`. Click on a box → selects/moves it; click on empty canvas with a mask tool active → paints mask as today. The box layer being hidden disables box interaction entirely.
- **D-08:** Single-select. One box selected at a time.
- **D-09:** Color boxes by origin — detected `#5fd068` (green), user `#f5a623` (amber) (locked in 03-UI-SPEC.md).

**Box edits & undo**
- **D-10:** Add a 3rd undo stack, BOXES, alongside MASK and IMAGE — preserving Phase 1's per-type snapshot semantics. Do NOT collapse Phase 1's two stacks into one.
- **D-11:** Unified `Ctrl+Z` / `Ctrl+Shift+Z` over a merged timeline. The three underlying stacks stay separate, but Ctrl+Z pops the most-recent-by-timestamp entry across all three.
- **D-12:** Delete box is immediate and silent — no confirm dialog. Safety comes from D-10/D-11.
- **D-13:** Draw-to-create a user box is in Phase 3 scope (Alt+drag on empty canvas, locked in 03-UI-SPEC.md §12e).

**Vendoring (NEW — supersedes prior "no vendoring" assumption)**
- **D-14:** Vendor PanelCleaner's `structures.py` AND `masker.py` into `panelcleaner/`, near-verbatim per Phase 1 D-12 (GPL v3 → GPL v3, license-compatible). `structures.py` provides the canonical `Box` dataclass + `BoxType` enum; `masker.py` provides mask-refinement + box/mask interaction logic (incl. the D-15 std-deviation machinery). D-12 discipline applies: adapt near-verbatim; preserve GPL v3 headers; do NOT vendor MangaCleaner_GPU (reference-only). The CTD subtree was already vendored in Phase 1 and is NOT re-touched.
- **D-15:** Plan-for (but defer the inpaint itself) a "selective per-box inpaint" seam driven by masker's std-deviation checks. Phase 3 does NOT implement the inpaint (later phase); Phase 3 vendors `masker.py` so the machinery exists AND structures the box/mask data model so a later phase can compute per-box std-dev and selectively inpaint without rework. **This is a plan-for-it decision, not a build-it-now decision** — surface it explicitly so the planner doesn't accidentally close the seam.

### Claude's Discretion
- Exact color/style pair for detected-vs-user boxes (D-09) — RESOLVED in 03-UI-SPEC.md (green `#5fd068` / amber `#f5a623`).
- The draw-to-create gesture (D-13) — RESOLVED in 03-UI-SPEC.md (Alt+drag).
- How the `origin` flag + undo identity layer onto the vendored `Box` (D-03/D-10/D-14) — a thin `Box` subclass vs a parallel tracks-origin struct vs a wrapper. Do not mutate the vendored `panelcleaner/structures.py:Box` itself.
- Box-data persistence shape (per-page, alongside Phase 2's `ImageFile.mask`) — extend `core/image_file.py:ImageFile` with a `boxes` slot (mirrors the `mask` slot pattern from Phase 2 D-11) vs a new page-state structure.
- Box-undo record granularity (full boxes-list snapshot per op vs per-op diff records) — boxes are lightweight (a list of bboxes), so a full per-page boxes snapshot per op is cheap and matches the Phase 1 shape. Planner decides.
- Confirm-gate copy for re-detect with existing boxes (D-04) — mirror `_confirm_replace_mask`'s tone. RESOLVED in 03-UI-SPEC.md §Copywriting.

### Deferred Ideas (OUT OF SCOPE)
- **Selective per-box inpaint via std-deviation (D-15)** — DEFERRED but PLAN-FOR-IT. Phase 3 vendors `masker.py` and keeps the data-model seam open; it does NOT implement the inpaint. Likely lands in a later phase.
- **OCR text recognition inside boxes (TEXT-02 draw-to-OCR, TEXT-04 inline text edit, TEXT-05 translation field)** — Phase 4. The `TextBlock.text`/`translation`/`vertical`/`language` slots are preserved through Phase 3.
- **Batch box-detection across a chapter** — future batch extension.
- **`.mas` project save/load of boxes (PROJ-01) and `_ocr.json` export (PROJ-03)** — Phase 5. Phase 3 persists boxes per-page in-memory (and across navigation) but does NOT serialize them to disk.
- **Multi-select / marquee selection of boxes** — optional polish; Phase 3 is single-select (D-08).
- **Edge handles (resize one edge independently), rotated/vertical box rendering, bubble auto-sizing** — Out of Scope (v2+).
- **Inline text rendering / typesetting inside boxes** — Out of Scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TEXT-01 | Run text-box detection across a page to create editable text-box objects (not a pixel mask) | `TorchCTDModel.detect()` (`adapters/torch_impl.py:104`) already returns `(mask_refined, blk_list)`; `_run_detection_task` (`main_window.py:1165`) already puts it in `result["blocks"]`; `_on_detection_finished` (line 1284) currently discards it. The seam is a one-line thread-through + a build-BoxItem loop gated by the D-01 mode toggle. No new model, no new worker. See §Detection Seam. |
| TEXT-03 | Select, move, resize, and delete text boxes on the canvas to correct detection errors | `EditorCanvas` (`gui/canvas.py`) is a `QGraphicsView` with a `QGraphicsScene`; `QGraphicsRectItem` selection/move/z-order/hit-testing are native Qt. Phase 3 adds a `BoxItem` subclass with 4 corner-handle children (D-05/D-06), slots box hit-testing before the mask-tool branch in `mousePressEvent` (line 758), wires Delete/Esc/Alt+drag. Undo via the new BOXES stack (D-10/D-11). See §BoxItem, §Hit-Testing & Dispatch. |
</phase_requirements>

## Summary

Phase 3 is a **pure-additive UI + data-model layer** built on an already-proven pipeline. The two load-bearing facts: (1) the detection model ALREADY returns the boxes — Phase 1's `TorchCTDModel.detect()` (`adapters/torch_impl.py:104-129`) unpacks CTD's 3-tuple `(mask, mask_refined, blk_list)` at line 124 and returns `(mask_refined, blk_list)`; the worker `result` dict ALREADY carries `"blocks": blk_list` (`main_window.py:1217`); only the finished handler discards it (line 1284). (2) the std-deviation machinery D-15 needs is ALREADY in our tree — Phase 1 vendored the full 1158-line `panelcleaner/image_ops.py` including `border_std_deviation` (line 483), `color_std` (line 464), and the `pick_best_mask` orchestrator (line 568). What's NOT vendored is the thin batch driver `masker.py` (151 lines) and the full `structures.py` (currently a stub placeholder).

The highest-risk item — the D-14 vendoring surface — turns out to be SMALLER and SAFER than the CONTEXT anticipated. The CONTEXT worried `masker.py` "transitively imports `output_structures.py`, `analytics.py`, `helpers.py`". Verified reality: `masker.py` imports exactly three modules — `image_ops` (vendored ✓), `structures` (stub, needs the full version, all deps resolve ✓), and `output_structures` (NOT vendored, but used ONLY by the batch `mask_page` driver for `ost.OutputPathGenerator`, which Phase 3 does not call). `analytics.py` is NOT in the transitive closure at all (only imported by `gui/mainwindow_driver.py` and `main.py`). The vendored slice that lets the D-15 seam work is **{full `structures.py`, full `masker.py`}** — plus a stubbed/removed `ost.OutputPathGenerator` reference. `output_structures.py` itself is NOT needed unless we call `mask_page` (we don't).

The D-15 seam shape is also clearer than the CONTEXT allowed: the unit of "uniform-enough region" computation is `border_std_deviation(base_image_L_or_RGB, mask_1bit, off_white_threshold, allow_color) -> (std_dev, median_color)` (`image_ops.py:467-522`); the per-box orchestration is `pick_best_mask(base, precise_mask, box_mask, masking_box, reference_box, masker_conf, analytics_page_path) -> MaskFittingResults | None` (line 568) whose result carries `analytics_std_deviation` and `mask_box`. The data-model seam that lets Phase 3 ship without the inpaint but lets a later phase compute std-dev without rework is: **each box carries a `(Box, mask_or_None, std_dev_or_None)` triple**, where Phase 3 populates only `Box` and leaves the other two `None`; the later phase fills them by calling `pick_best_mask` per box against the page image + mask.

**Primary recommendation:** Vendor the full `structures.py` (replacing the stub) and `masker.py` (adapted to remove the `ost.OutputPathGenerator` batch coupling), then build a `BoxItem(QGraphicsRectItem)` with 4 corner-handle children, wire `blk_list` through `_on_detection_finished`, add the BOXES stack + unified-timeline pop to `HistoryManager`, and add the `ImageFile.boxes` slot mirroring Phase 2's mask persistence. The vendoring risk is LOW (verified transitive surface); the HistoryManager unified-timeline is the one genuinely new algorithmic piece.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Box detection (model inference) | API / Backend (worker thread) | — | `TorchCTDModel.detect` runs off-GUI-thread via `Worker(QRunnable)`; returns numpy + `blk_list`. Boxes ride on the EXISTING Phase 1 detect op (D-01). No new worker. |
| Box rendering + interaction | Browser / Client (Qt scene) | — | `BoxItem(QGraphicsRectItem)` + corner handles live in the existing `QGraphicsScene`; selection/move/resize/hit-test are native Qt Graphics View. |
| Box data model (`Box` + `origin` + payload) | core/ (pure Python) | — | Vendored `panelcleaner/structures.py:Box` (immutable) + a thin origin-tagging wrapper. Pure, headless-testable, no Qt. |
| Box persistence (per-page) | core/ (`ImageFile`) | — | `ImageFile.boxes` slot mirrors `ImageFile.mask` (Phase 2 D-11). Saved/restored on page navigation. |
| Box undo/redo | core/ (`HistoryManager`) | — | New BOXES stack (D-10) + unified-timeline pop across MASK/IMAGE/BOXES (D-11). Pure, headless-testable. |
| Box-overlay layer toggle | gui/ (`EditorCanvas` + View menu) | — | `QGraphicsItemGroup.setVisible(bool)` at z=100; checkable `QAction` (Shift+M). |
| Selective per-box inpaint (D-15, DEFERRED) | API / Backend (later phase) | core/ (seam) | NOT built in Phase 3. The seam is the `Box` + `mask` + `std_dev` data shape; the later phase calls `pick_best_mask` per box. |
| Mode toggle (Detect Boxes on/off) | gui/ (`MainWindow`) | — | Checkable `QAction` in Tools menu; gates whether `_on_detection_finished` builds boxes from `blk_list`. |

## Standard Stack

No new third-party packages are installed in Phase 3 — every dependency is already in `pyproject.toml` and verified present in the active env. Phase 3's "stack" additions are vendored PanelCleaner source + Qt Graphics View primitives.

### Core (existing, reused — no install)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PySide6 | 6.7+ | `QGraphicsRectItem`, `QGraphicsItemGroup`, `QGraphicsTextItem`, `QAction`, `QShortcut`, `QMessageBox` | Already the framework; `QGraphicsRectItem` is the native box primitive. LGPL. `[VERIFIED: local source — pyproject.toml + env]` |
| attrs | 25.4.0 | `@frozen`/`@define` for the vendored `Box`/`PageData`/`MaskFittingResults` | Required by the full vendored `structures.py`. Already a dep. `[VERIFIED: local env — python -c "import attrs"]` |
| Pillow (PIL) | 12.0.0 | `Image`, `ImageDraw`, `ImageFilter` for the vendored std-deviation machinery | Required by `image_ops.py` std-dev path (`Image.FIND_EDGES`, mask mode "1"). Already a dep. `[VERIFIED: local env]` |
| NumPy | <2.0 | `np.std`, `np.linalg.norm`, `np.array` in `color_std`/`border_std_deviation` | Required by std-dev math. Already pinned <2. `[VERIFIED: local env]` |

### Vendored additions (D-14 — near-verbatim, GPL v3 → GPL v3)

| File | Lines | Purpose | Status |
|------|-------|---------|--------|
| `panelcleaner/structures.py` | ~750 | Full `Box` (frozen, x1/y1/x2/y2 + `as_tuple`/`as_tuple_xywh`/`__contains__`/`area`/`merge`/`overlaps`/`pad`/`scale`/`translate`) + `BoxType` enum + the batch-pipeline structs (`PageData`, `MaskData`, `MaskFittingResults`, `MaskerData`, etc.) | Currently a STUB placeholder (18 lines). Replace with the full upstream version. All upstream imports (`pcleaner.config`, `pcleaner.data`, `pcleaner.ocr.supported_languages`, `pcleaner.helpers`) resolve in our vendored tree. `[VERIFIED: local source — C:\Src\PanelCleaner\pcleaner\structures.py + env import test]` |
| `panelcleaner/masker.py` | 151 | Batch mask driver: `mask_page(m_data)` + `save_denoising_data(...)`. Thin orchestrator; the real std-dev logic is in `image_ops.py` (already vendored). | NOT vendored. Vendor near-verbatim with the `ost.OutputPathGenerator` batch-coupling stubbed/removed per D-12 (Phase 3 doesn't call `mask_page`; the file is vendored so the std-dev seam machinery exists per D-15). `[VERIFIED: local source — C:\Src\PanelCleaner\pcleaner\masker.py]` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Vendoring full `structures.py` (D-14) | Hand-roll a minimal `Box` dataclass, leave the stub | Rejected by CONTEXT D-14 explicitly: vendor PanelCleaner's `Box` rather than hand-roll. Vendoring also brings the `MaskFittingResults`/`MaskData` structs the D-15 inpaint phase needs for free — no rework. |
| Vendoring `masker.py` (D-14) | Call `image_ops.pick_best_mask`/`border_std_deviation` directly from a later inpaint phase | D-14 mandates vendoring `masker.py` so the machinery exists; the later phase imports it rather than re-glueing `image_ops` calls. The cost is ~151 lines + a one-line stub for `ost.OutputPathGenerator`. |
| `QGraphicsRectItem` for boxes (D-05) | `QGraphicsPolygonItem` / custom paint | Rect is the bbox shape; polygon is overkill (rotated/vertical boxes are Out of Scope). Native rect selection/move is free. `[CITED: 03-UI-SPEC.md §12a]` |
| Full boxes-list snapshot per undo op (Claude's Discretion) | Per-op diff records (before/after bbox per box_id) | Boxes are lightweight (list of bboxes); full snapshot per op matches Phase 1's full-snapshot shape and avoids diff-application bugs. Recommended. |

**Installation:**
```bash
# No packages to install. Phase 3 adds vendored source + Qt primitives.
# The full structures.py + masker.py are copied from ../PanelCleaner/pcleaner/
# into panelcleaner/ per D-14 (GPL v3 → GPL v3, D-12 near-verbatim adaptation).
```

**Version verification (all confirmed present in active env):**
```
attrs      25.4.0   (python -c "import attrs; print(attrs.__version__)")
PIL        12.0.0   (python -c "import PIL; print(PIL.__version__)")
loguru     present  (python -c "import loguru")
numpy      <2.0     (pyproject pin)
scipy      present  (required by image_ops.py; in pyproject)
tifffile   2026.1.28 (required by vendored helpers.py)
psutil     7.2.2    (required by vendored helpers.py)
configupdater present
```

## Package Legitimacy Audit

> Phase 3 installs **no** external packages — every dependency is already in `pyproject.toml` (verified above) and the only new code is vendored PanelCleaner source (GPL v3 → GPL v3 per Phase 1 D-12, already cleared) plus our own Qt Graphics View code. No `npm`/`pip`/`cargo` install step. The legitimacy gate is satisfied by policy (Phase 1 D-12 vendoring discipline), not by a registry lookup.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none — Phase 3 installs nothing new) | — | — | — | — | — | N/A |

**Packages removed due to [SLOP] verdict:** none (no installs).
**Packages flagged as suspicious [SUS]:** none.

## Architecture Patterns

### System Architecture Diagram

```
[User action: Tools → Detect Text (D), mode = Detect Boxes ON]
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│ MainWindow.detect_text()  (main_window.py:1122)             │
│   ├─ _op_running gate (skip if a model op is in flight)      │
│   ├─ _confirm_replace_mask()  (if canvas.has_mask())         │
│   └─ [NEW D-04] _confirm_replace_boxes() (if detected boxes) │
└─────────────────────────────────────────────────────────────┘
        │  Worker(QRunnable) → QThreadPool.globalInstance()
        ▼
┌─────────────────────────────────────────────────────────────┐
│ _run_detection_task (main_window.py:1165)  [off-GUI thread] │
│   mask_refined, blk_list = model.detect(image)               │
│   return {"mask": mask_refined, "blocks": blk_list}  ◄ ALREADY
└─────────────────────────────────────────────────────────────┘
        │  worker.signals.result (main thread)
        ▼
┌─────────────────────────────────────────────────────────────┐
│ _on_detection_finished(result)  (main_window.py:1284)        │
│   ├─ set_mask(result["mask"])              (Phase 1, kept)   │
│   └─ [NEW D-01/D-03] if mode on:                             │
│        ┌─ replace detected boxes (keep user boxes by origin) │
│        ├─ build BoxItem per TextBlock (origin="detected")    │
│        ├─ add to canvas box layer (z=100)                    │
│        ├─ push BOXES snapshot to HistoryManager              │
│        └─ auto-show box overlay (Shift+M toggle checked)     │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│ EditorCanvas (gui/canvas.py) — QGraphicsScene                │
│   z=0    image_item  (QGraphicsPixmapItem)                   │
│   z=0    mask_item    (QGraphicsPixmapItem, above image)     │
│   z=100  box layer    [NEW: QGraphicsItemGroup / BoxItems]   │
│   z=150  corner handles [NEW: child QGraphicsRectItem per box]│
│   z=850  empty-box-hint [NEW: QGraphicsTextItem]             │
│   z=900  preview_item (QGraphicsPathItem — amber for create) │
│   z=1000 cursor_item   (QGraphicsEllipseItem)                │
│                                                              │
│   mousePressEvent dispatch (line 758):                       │
│     1. Pan (middle/Space+left) ─── highest priority          │
│     2. [NEW] box layer visible?                              │
│          ├─ hit corner handle of selected box → RESIZE       │
│          ├─ hit box body → SELECT + MOVE                     │
│          ├─ Alt+left-drag on empty → CREATE user box         │
│          └─ else → deselect + FALL THROUGH to mask tools     │
│     3. (existing) left+mask tool → _begin_paint              │
└─────────────────────────────────────────────────────────────┘
        │  box edits (create/move/resize/delete)
        ▼
┌─────────────────────────────────────────────────────────────┐
│ HistoryManager (core/history_manager.py)  [REDESIGN D-10/D-11]│
│   _mask_undo/_redo   (QImage snapshots — Phase 1, kept)      │
│   _image_undo/_redo  ((x,y,patch) — Phase 1, kept)           │
│   _boxes_undo/_redo  [NEW: full per-page boxes-list snapshot]│
│                                                              │
│   [NEW] unified undo(): pop most-recent-by-timestamp across  │
│         all three undo lists; redo() likewise                │
└─────────────────────────────────────────────────────────────┘
        │  page navigation
        ▼
┌─────────────────────────────────────────────────────────────┐
│ on_page_selected (main_window.py:653) — Phase 2 D-11 seam    │
│   Step 1: persist OUTGOING mask + [NEW] boxes (ImageFile.*)  │
│   Step 2: reset_history (all three stacks)                   │
│   Step 3: set_image_from_path                                │
│   Step 4: restore INCOMING mask + [NEW] boxes (.copy() both) │
│   Step 5: tail (title/fit/status)                            │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│ ImageFile (core/image_file.py)  [NEW boxes slot]             │
│   path, thumbnail, mask (Phase 2), boxes: list[Box] | None   │
│                                                              │
│   [DEFERRED D-15 seam] each box carries                      │
│     (Box, mask_or_None, std_dev_or_None)                     │
│   Phase 3 populates Box only; later phase fills mask+std_dev │
│   via image_ops.pick_best_mask / border_std_deviation        │
└─────────────────────────────────────────────────────────────┘
```

A reader can trace the TEXT-01 path (top → `_on_detection_finished` → box layer) and the TEXT-03 path (canvas dispatch → HistoryManager → ImageFile) end to end.

### Recommended Project Structure

```
manga_ai_studio/
├── gui/
│   ├── canvas.py          # EditorCanvas: ADD box layer, hit-test dispatch, BoxItem wiring
│   ├── box_item.py        # [NEW] BoxItem(QGraphicsRectItem) + corner handles + resize logic
│   ├── main_window.py     # _on_detection_finished seam, mode toggle, View menu, confirm gates
│   └── ...
├── core/
│   ├── image_file.py      # ImageFile: ADD `boxes` slot
│   ├── history_manager.py # HistoryManager: ADD BOXES stack + unified-timeline pop
│   └── box_model.py       # [NEW, optional] origin-tagging wrapper over vendored Box
└── ...
panelcleaner/              # vendored PanelCleaner source (GPL v3 → GPL v3)
├── structures.py          # [REPLACE stub] full Box + BoxType + batch structs
├── masker.py              # [NEW] mask_page driver + std-dev seam (ost coupling stubbed)
├── image_ops.py           # ALREADY has border_std_deviation / pick_best_mask (D-15 machinery)
└── ... (config.py, helpers.py — already vendored, untouched)
tests/
├── test_core/
│   ├── test_history.py        # EXTEND: BOXES stack + unified-timeline tests
│   ├── test_box_model.py      # [NEW] origin-tagging wrapper tests
│   └── test_structures_box.py # [NEW] vendored Box round-trip tests
├── test_gui_box_layer.py      # [NEW] BoxItem render/select/move/resize/delete/create
└── test_gui_detection_boxes.py# [NEW] _on_detection_finished builds boxes from blk_list
```

### Pattern 1: BoxItem with corner resize handles (D-05/D-06)

**What:** A `QGraphicsRectItem` subclass representing one text box; four child `QGraphicsRectItem`s at TL/TR/BL/BR are the resize affordance. Selection state drives handle visibility; origin drives pen hue.

**When to use:** Every box on the canvas (detected or user-origin).

**Example:**
```python
# Source: 03-UI-SPEC.md §12a-12b (design contract); Qt Graphics View framework
# [CITED: 03-UI-SPEC.md lines 190-211]

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPen, QBrush, QColor

DETECTED_HUE = "#5fd068"   # UI-SPEC §Color — green for detected (D-09)
USER_HUE = "#f5a623"       # amber for user

class CornerHandle(QGraphicsRectItem):
    """One of 4 corner resize handles; child of a BoxItem.
    ItemIgnoresTransformations keeps it a constant 8×8 viewport-px grab
    target regardless of zoom (UI-SPEC §Spacing exceptions). Repositioned
    on parent geometry change + on canvas.zoom_changed."""
    def __init__(self, corner: str, parent: "BoxItem"):
        super().__init__(0, 0, 8, 8, parent)
        self.corner = corner  # "TL"/"TR"/"BL"/"BR"
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setZValue(150)
        # fill = box hue; outline = matte #0b0b0e (1px separation)
        ...

class BoxItem(QGraphicsRectItem):
    """One editable text box (D-05). Origin-coloured border (D-09) +
    4 corner handles shown only when selected (D-08 single-select)."""
    def __init__(self, box: Box, origin: str, payload=None):
        x, y, w, h = box.as_tuple_xywh        # Box → QRectF (structures.py:39)
        super().__init__(QRectF(x, y, w, h))
        self.box = box                        # vendored Box (immutable bbox)
        self.origin = origin                  # "detected" | "user" (D-03)
        self.payload = payload                # TextBlock for Phase 4/5; None for user boxes
        self.setZValue(100)                   # above mask_item, below preview_item
        self.setFlags(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable
                      | QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.handles = [CornerHandle(c, self) for c in ("TL","TR","BL","BR")]
        self._apply_origin_pen()
        self._sync_handles()

    def _apply_origin_pen(self):
        hue = DETECTED_HUE if self.origin == "detected" else USER_HUE
        width = 3 if self.isSelected() else 2     # UI-SPEC: 3px selected, 2px unselected
        self.setPen(QPen(QColor(hue), width))
        tint = QColor(hue); tint.setAlpha(31)     # ≈0.12 alpha fill when selected
        self.setBrush(QBrush(tint) if self.isSelected() else Qt.BrushStyle.NoBrush)
```

### Pattern 2: Unified-timeline undo across three stores (D-10/D-11)

**What:** Three independent stores (MASK QImage snapshots, IMAGE `(x,y,patch)` tuples, BOXES boxes-list snapshots) each stay separate; Ctrl+Z pops whichever store has the most-recent timestamp; Ctrl+Shift+Z redoes likewise.

**When to use:** Every undoable op (mask stroke, inpaint, box create/move/resize/delete).

**Key design point:** Each push stamps a monotonic counter (cheaper than wall-clock and avoids time-skew). The unified pop walks the three undo lists' tail timestamps and pops the newest. Phase 1's per-type pop methods stay (the unified pop delegates to them).

```python
# Source: existing core/history_manager.py + CONTEXT D-10/D-11
# [CITED: core/history_manager.py:49-192; 03-CONTEXT.md D-10/D-11]

class HistoryManager:
    def __init__(self, limit=DEFAULT_HISTORY_LIMIT):
        self.limit = limit
        self._mask_undo, self._mask_redo = [], []
        self._image_undo, self._image_redo = [], []
        self._boxes_undo, self._boxes_redo = [], []   # [NEW D-10]
        self._seq = 0                                  # monotonic stamp

    def _stamp(self):
        self._seq += 1
        return self._seq

    def push_boxes_state(self, boxes: list) -> None:   # [NEW D-10]
        """Full per-page boxes-list snapshot per op (Claude's Discretion —
        boxes are lightweight; matches Phase 1's full-snapshot shape)."""
        snap = [(b.box, b.origin, b.payload) for b in boxes]  # deep-ish copy
        self._boxes_undo.append((self._stamp(), snap))
        self._boxes_redo.clear()
        if len(self._boxes_undo) > self.limit:
            self._boxes_undo.pop(0)

    def undo(self, current_mask, current_img, current_boxes):
        """Unified pop (D-11): most-recent-by-stamp across all three stores."""
        candidates = []
        if self._mask_undo:   candidates.append(("mask",  self._mask_undo[-1][0]))
        if self._image_undo:  candidates.append(("image", self._image_undo[-1][0]))   # image uses (x,y,patch) tuples — store stamp alongside
        if self._boxes_undo:  candidates.append(("boxes", self._boxes_undo[-1][0]))
        if not candidates:
            return None
        kind = max(candidates, key=lambda c: c[1])[0]
        if kind == "mask":  return ("mask",  self.pop_mask_undo(current_mask))
        if kind == "image": return ("image", self.pop_image_undo(current_img))
        return ("boxes", self.pop_boxes_undo(current_boxes))
```

> Note: Phase 1's IMAGE stack stores bare `(x, y, patch)` tuples without a stamp. To unify the timeline, Phase 3 must add a stamp to IMAGE entries (and to MASK entries, which are bare `QImage`s). This is the one mechanical change to Phase 1's existing stores — wrap each entry as `(stamp, value)` and update the four pop/push methods. The push/pop semantics are unchanged; only the container shape widens. Flag this as a Phase 1 regression-test update task (the existing `test_history.py` guards assert on the bare values and will need updating to unpack `(stamp, value)`).

### Pattern 3: Box layer hit-test before mask-tool dispatch (D-07)

**What:** Slot a box-hit-test branch into `EditorCanvas.mousePressEvent` (line 758) AFTER pan but BEFORE the existing mask-tool branch.

**When to use:** Every left-press when the box layer is visible.

**Example:**
```python
# Source: gui/canvas.py:758-785 (existing dispatch); 03-UI-SPEC.md §12d
# [CITED: 03-UI-SPEC.md lines 222-235; gui/canvas.py:758]

def mousePressEvent(self, event):
    # 1. Pan (unchanged, highest priority)
    if middle or space_left: ...; return

    # 2. [NEW D-07] Box layer visible → box hit-test first
    if self.box_layer.isVisible() and event.button() == Qt.MouseButton.LeftButton:
        scene_pos = self._scene_pos(event)
        item = self._scene.itemAt(scene_pos, self.transform())
        if isinstance(item, CornerHandle):
            self._begin_resize(item, scene_pos); event.accept(); return
        if isinstance(item, BoxItem):
            self._select_and_begin_move(item, scene_pos); event.accept(); return
        # empty canvas:
        if event.modifiers() & Qt.KeyboardModifier.AltModifier:
            self._begin_create_box(scene_pos); event.accept(); return   # D-13 Alt+drag
        self._deselect_box()   # fall through to mask tools

    # 3. (existing) mask-tool branch
    if (event.button() == Qt.MouseButton.LeftButton
        and self.current_tool != ToolMode.MOVE
        and self._mask is not None and not self._mask.isNull()):
        self._begin_paint(event); event.accept(); return
    super().mousePressEvent(event)
```

### Anti-Patterns to Avoid

- **Splitting BOXES into per-op-type stacks (create/move/resize/delete):** CONTEXT D-10 is explicit ("BOXES is ONE logical stack, not split per-op-type"). The Phase 1 warning ("two logical stacks not four") extends to "three logical stacks not seven". One BOXES store, op-type lives inside each record's metadata. `[CITED: 01-CONTEXT.md D-01-06; STATE.md "01-06: two logical stacks (MASK + IMAGE) not four"]`
- **Mutating the vendored `panelcleaner/structures.py:Box`:** D-14 + Claude's Discretion: origin/identity layer ON TOP of the vendored `Box` (a thin subclass or parallel struct), not by editing the vendored class. Keeps the GPL-v3 source near-verbatim per D-12. `[CITED: 03-CONTEXT.md D-14 + Claude's Discretion]`
- **Calling `mask_page` (the batch driver) from Phase 3:** `masker.mask_page` is batch-oriented (reads JSON, writes cache files, uses `ost.OutputPathGenerator`). Phase 3 vendors it for the std-dev SEAM only — it does NOT call it. Calling it would pull `output_structures.py` into the transitive runtime dep. `[VERIFIED: local source — masker.py:12-120]`
- **Computing std-deviation by hand:** Use `image_ops.border_std_deviation` / `image_ops.color_std` / `image_ops.pick_best_mask` (already vendored). Hand-rolling reintroduces the off-white-threshold + geometric-median + edge-pixel logic that took PanelCleaner years to tune. `[VERIFIED: local source — panelcleaner/image_ops.py:383-522]`
- **Adding a 6th tool to `ToolsPanel.QActionGroup` for box selection:** D-07 forbids it; boxes are always interactive when the layer is visible. `[CITED: 03-CONTEXT.md D-07; 03-UI-SPEC.md §12d "Anti-pattern honored"]`

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Box data model | A custom `Box` class with `x1/y1/x2/y2` + bbox math | Vendored `panelcleaner/structures.py:Box` (D-14) | Already has `as_tuple_xywh` (Qt-ready), `__contains__` (hit-test), `merge`/`overlaps`/`pad`/`scale`/`translate` (the merge logic the D-15 inpaint phase needs). Hand-rolling re-implements 750 lines of tested geometry. `[VERIFIED: local source — C:\Src\PanelCleaner\pcleaner\structures.py:24-145]` |
| Per-box std-deviation (D-15) | A new "compute uniformity" function | `panelcleaner.image_ops.border_std_deviation` + `pick_best_mask` (already vendored) | The off-white-threshold rounding, grayscale-vs-RGB branch, geometric-median fallback, and growth-step generator are non-trivial. `[VERIFIED: local source — panelcleaner/image_ops.py:467-720]` |
| Box selection / move / z-order | Custom selection state + drag math | `QGraphicsRectItem` flags `ItemIsSelectable | ItemIsMovable | ItemSendsGeometryChanges` | Native Qt Graphics View does this; only the look (pen/brush/handles) is ours. `[CITED: 03-UI-SPEC.md §12a]` |
| Box hit-testing | Manual point-in-rect over the boxes list | `QGraphicsScene.itemAt(scene_pos)` filtered to box layer | Native scene-level hit-test respects z-order and transforms for free. `[CITED: 03-UI-SPEC.md §12d]` |
| Corner-handle constant viewport size | Manual scale-compensation on every paint | `QGraphicsItem.ItemIgnoresTransformations` | Qt flag — handle stays 8×8 viewport px at any zoom. `[CITED: 03-UI-SPEC.md §Spacing exceptions]` |
| Confirm dialog for box re-detect | A new dialog template | Mirror `_confirm_replace_mask` (main_window.py:1328) | Same `QMessageBox` custom-button pattern, same tone (CONTEXT D-04). `[VERIFIED: local source — main_window.py:1328-1348]` |
| Per-page box persistence | A new page-state structure | `ImageFile.boxes` slot mirroring `ImageFile.mask` (Phase 2 D-11) | The 5-step `on_page_selected` seam (save outgoing / reset / load / restore incoming / tail) already exists for masks; boxes ride the same seam. `[VERIFIED: local source — main_window.py:653-747]` |

**Key insight:** Phase 3's hardest pieces (box geometry, std-deviation, selection/move/hit-test, persistence seam) all have battle-tested implementations either vendored already or native to Qt. The genuinely new code is: (a) the `BoxItem` Qt subclass + handles, (b) the unified-timeline pop algorithm, (c) the box→`ImageFile.boxes` persistence wiring. Everything else is wiring.

## Runtime State Inventory

> Phase 3 involves vendoring + additive UI/data-model changes. There is no rename/refactor/migration of an existing string, so the canonical "what runtime system still caches the old string" question does not apply in the rename sense. However, two Phase-3-specific runtime-state concerns apply:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None on disk — Phase 3 does NOT serialize boxes (PROJ-01 `.mas` save is Phase 5). Boxes live only in `ImageFile.boxes` (in-memory, per-page). | None for Phase 3; Phase 5 will add serialization. |
| Live service config | None. The D-01 mode toggle ("Detect Boxes" on/off) is a checkable `QAction`; its checked-state is session-only (no persistence required for v1 — defaults to checked per UI-SPEC). | None; consider persisting the toggle in QSettings as optional polish (not required). |
| OS-registered state | None. No Task Scheduler / launchd / pm2 registrations involved. | None. |
| Secrets/env vars | None. No new secrets. | None. |
| Build artifacts | The vendored `panelcleaner/__pycache__/structures.cpython-*.pyc` is the OLD stub's bytecode; after replacing `structures.py` with the full version, the stale `.pyc` must be invalidated (Python does this automatically via mtime, but a clean `__pycache__` wipe avoids confusion). New `masker.py` will produce a fresh `.pyc`. | Planner: no explicit task needed (Python auto-recompiles); mention in the vendoring task that `__pycache__` may be stale on first run. |
| **Vendoring transitive surface (D-14-specific)** | **VERIFIED:** the full `structures.py` imports `pcleaner.config`, `pcleaner.data`, `pcleaner.ocr.supported_languages`, `pcleaner.helpers`, plus stdlib + `PIL`/`attrs`/`loguru`. ALL of these resolve in our vendored tree (config.py ✓ 1746 lines, data/ ✓, ocr/supported_languages.py ✓, helpers.py ✓ 335 lines; attrs/PIL/loguru verified present in env). `masker.py` imports `image_ops` (vendored ✓), `structures` (becomes full ✓), `output_structures` (NOT vendored — used only inside `mask_page`'s `ost.OutputPathGenerator` call at masker.py:28; stub it per D-12 or guard the import). | Vendoring task must (a) replace the stub with the full `structures.py`, (b) add `masker.py` with the `ost` coupling stubbed, (c) verify `python -c "import panelcleaner.structures, panelcleaner.masker"` succeeds. |

**Nothing found in category:** "Stored data" and "OS-registered state" have no Phase-3 items — verified by reading `core/image_file.py` (no on-disk box serialization) and confirming no OS-registration code exists in the tree.

## Common Pitfalls

### Pitfall 1: Forgetting `output_structures.py` is NOT vendored
**What goes wrong:** Copying `masker.py` verbatim and running `import panelcleaner.masker` raises `ModuleNotFoundError: pcleaner.output_structures` (rewritten to `panelcleaner.output_structures`).
**Why it happens:** `masker.py` line 9 `import pcleaner.output_structures as ost`, and `mask_page` uses `ost.OutputPathGenerator` at line 28. Our tree does NOT vendor `output_structures.py` (it's a batch-pipeline path manager).
**How to avoid:** Per D-12 "adapt near-verbatim": stub the `ost` import (e.g. `try: import panelcleaner.output_structures as ost; except ImportError: ost = None`) OR remove the `ost` usage entirely from the vendored `masker.py` (Phase 3 does not call `mask_page`, so `ost.OutputPathGenerator` is dead code in our context). Do NOT vendor `output_structures.py` — that drags in the batch GUI analytics pipeline (`Output`/`Step`/`ProgressData`/`ImageAnalytics`) which is far more than Phase 3 needs.
**Warning signs:** `ModuleNotFoundError` on first import; tests failing at collection time. `[VERIFIED: local source — C:\Src\PanelCleaner\pcleaner\masker.py:9,28]`

### Pitfall 2: Reusing the stub `structures.py` and finding `MaskFittingResults is None`
**What goes wrong:** Calling `image_ops.pick_best_mask` raises `AttributeError: 'NoneType' object has no attribute 'MaskFittingResults'` because `image_ops.py:706,717` call `st.MaskFittingResults(...)` and the stub `structures.py` defines nothing.
**Why it happens:** Phase 1 left `panelcleaner/structures.py` as an 18-line stub (only `image_ops.py`'s lazy annotations imported it, so the stub was sufficient). The full `structures.py` defines `MaskFittingResults` (line 564), `MaskData` (625), `PageData` (148), etc. — all needed once the D-15 seam calls into `pick_best_mask`.
**How to avoid:** Replace the stub with the full upstream `structures.py` as the FIRST vendoring task. Verify `python -c "from panelcleaner.structures import Box, BoxType, MaskFittingResults, MaskData, PageData; print('ok')"` succeeds before any other Phase 3 work.
**Warning signs:** Any `AttributeError` mentioning `st.<Anything>` or `structures.<Anything>`. `[VERIFIED: local source — C:\Src\Manga AI Studio\panelcleaner\structures.py (stub) vs C:\Src\PanelCleaner\pcleaner\structures.py (full, 750 lines)]`

### Pitfall 3: Two-phase Qt mouse-move during box resize corrupting the BOXES undo snapshot
**What goes wrong:** Box-move/resize snapshots taken at press-time alias the live `box.box` immutable; a mid-drag undo restores a half-moved box.
**Why it happens:** The vendored `Box` is `@frozen` (immutable), so `box.box` itself is safe — BUT the `BoxItem`'s `QRectF` (the QGraphicsRectItem geometry) is mutable and updated live during drag. If the BOXES snapshot stores a reference to the `BoxItem` rather than a deep copy of its current bbox, the snapshot mutates with the drag.
**How to avoid:** The `push_boxes_state` snapshot must materialize a fresh `Box` per item from its CURRENT `QRectF` at push-time (`Box(int(r.x()), int(r.y()), int(r.x()+r.width()), int(r.y()+r.height()))`), not store a reference to the live `BoxItem`. This mirrors Phase 1 Pitfall 2's `.copy()` discipline applied to box geometry. The existing regression-guard pattern (`test_mask_snapshot_is_copied`) should be replicated as `test_boxes_snapshot_is_detached`.
**Warning signs:** Undo after a partial drag restores a box at the drag-end position, not the drag-start position. `[CITED: STATE.md "01-05: every numpy<->QImage bridge enforces .copy() detachment (Pitfall 2)"]`

### Pitfall 4: The unified-timeline pop needs stamps on ALL three stores
**What goes wrong:** Implementing `undo()` as "pop whichever of mask/image/boxes has the newest entry" by list-length or insertion order produces wrong results because Phase 1's MASK and IMAGE stores have no timestamp.
**Why it happens:** Phase 1's `_mask_undo` holds bare `QImage`s and `_image_undo` holds bare `(x,y,patch)` tuples — neither carries a stamp. A unified chronological pop is impossible without per-entry ordering.
**How to avoid:** Widen Phase 1's two store entry shapes to `(stamp, value)` (mask: `(stamp, QImage)`; image: `(stamp, (x,y,patch))`; boxes: `(stamp, list_of_box_tuples)`). This is a mechanical change to the four existing push/pop methods (`push_mask_state`, `pop_mask_undo`, `pop_mask_redo`, `push_image_action`, `pop_image_undo`, `pop_image_redo`) — wrap/unwrap the stamp. Update `test_history.py`'s existing guards to unpack `(stamp, value)`. Do NOT introduce wall-clock (time skew across threads); use a monotonic integer counter incremented on every push.
**Warning signs:** Undo pops the wrong stack after interleaved mask-then-box edits. `[VERIFIED: local source — core/history_manager.py:73-163 (bare values, no stamps)]`

### Pitfall 5: Box layer hidden should fully disable box hit-testing (D-07)
**What goes wrong:** Boxes remain selectable via keyboard or via `scene.items()` even when the layer is `setVisible(False)`, intercepting clicks meant for mask painting.
**Why it happens:** `QGraphicsItemGroup.setVisible(False)` hides the items visually but does not always disable their hit-testing unless each child is also disabled, OR the dispatch explicitly checks `box_layer.isVisible()` before the box branch.
**How to avoid:** The dispatch guard (`if self.box_layer.isVisible() and ...`) in `mousePressEvent` is the load-bearing check (UI-SPEC §12d / §11). Do NOT rely solely on Qt visibility for hit-test disabling. As belt-and-suspenders, also set `box_item.setEnabled(False)` on hide (disabled items are not hit-tested). Test: with the box layer hidden, a left-click on a box's former location must paint mask (not select a box).
**Warning signs:** Mask painting fails where a hidden box used to be. `[CITED: 03-UI-SPEC.md §11 "Hidden = not interactable", §12d step 3]`

### Pitfall 6: `TextBlock.xyxy` ints vs `QRectF` floats
**What goes wrong:** Box geometry drifts by sub-pixel over many move/resize ops because `QRectF` carries floats and `TextBlock.xyxy` is `[int, int, int, int]`.
**Why it happens:** `Box.as_tuple_xywh` returns ints, but `QGraphicsRectItem.setRect(QRectF(...))` stores floats; reading `rect().x()` back yields a float.
**How to avoid:** Round to int at every Box↔QRectF boundary: `Box(int(r.x()), int(r.y()), int(r.x()+r.width()), int(r.y()+r.height()))` when snapshotting for undo/persistence; `QRectF(x, y, w, h)` from `box.as_tuple_xywh` (already ints) when building. Keep the on-canvas `QRectF` float-precise for smooth dragging, but materialize int `Box`es at the trust boundaries (undo, persistence, detection-build).
**Warning signs:** Boxes slowly migrate across undo cycles; persisted boxes drift from detected positions. `[VERIFIED: local source — C:\Src\PanelCleaner\pcleaner\structures.py:39-41 (as_tuple_xywh returns ints); textblock.py:50 (xyxy ints)]`

## Code Examples

### TextBlock → BoxItem → QRectF (TEXT-01 build step)
```python
# Source: panelcleaner/comic_text_detector/utils/textblock.py:50 (xyxy);
#         panelcleaner/structures.py:24-41 (Box); 03-UI-SPEC.md §12a (QRectF)
# [VERIFIED: local source]

from panelcleaner.structures import Box
from panelcleaner.comic_text_detector.utils.textblock import TextBlock

def textblock_to_box(blk: TextBlock) -> Box:
    """TextBlock.xyxy = [x1,y1,x2,y2] ints → vendored Box."""
    x1, y1, x2, y2 = blk.xyxy
    return Box(int(x1), int(y1), int(x2), int(y2))

# In _on_detection_finished (main_window.py:1284), AFTER set_mask:
def _build_detected_boxes(self, blk_list):
    """D-01/D-03: build BoxItems from blk_list when mode is on.
    D-03: replace detected boxes, keep user boxes."""
    user_boxes = [b for b in self.canvas.boxes() if b.origin == "user"]
    detected = [textblock_to_box(blk) for blk in (blk_list or [])]
    self.canvas.set_boxes(user_boxes, detected)   # canvas rebuilds BoxItems
    self.canvas.set_box_overlay_visible(True)     # auto-show on first detect
    self.history.push_boxes_state(self.canvas.boxes_snapshot())  # D-10
```

### Vendoring verification (run after copying structures.py + masker.py)
```bash
# Smoke test the vendored slice imports cleanly with ost stubbed.
python -c "from panelcleaner.structures import Box, BoxType, MaskFittingResults, MaskData, PageData; print('structures ok')"
python -c "import panelcleaner.masker; print('masker ok')"
python -c "from panelcleaner.image_ops import border_std_deviation, color_std, pick_best_mask; print('std-dev machinery ok')"
python -c "
from panelcleaner.structures import Box
b = Box(10, 20, 110, 220)
assert b.as_tuple_xywh == (10, 20, 100, 200), b.as_tuple_xywh
assert (50, 50) in b and (5, 5) not in b
print('Box geometry ok')
"
```

### D-15 seam shape (data model — Phase 3 populates Box only)
```python
# Source: CONTEXT D-15 + panelcleaner/image_ops.py:467-720 (the std-dev machinery)
# [CITED: 03-CONTEXT.md D-15; VERIFIED: panelcleaner/image_ops.py:467-720]

from dataclasses import dataclass
from typing import Optional
from panelcleaner.structures import Box

@dataclass
class PageBox:
    """Phase 3 box data model. The D-15 seam: mask + std_dev are None in
    Phase 3 (populated by a LATER inpaint phase via image_ops.pick_best_mask).
    Phase 3 builds these with mask=None, std_dev=None."""
    box: Box
    origin: str                       # "detected" | "user" (D-03)
    payload: Optional[object] = None  # TextBlock for Phase 4/5; None for user boxes
    mask: Optional[object] = None     # D-15 seam: per-box mask (DEFERRED — later phase)
    std_dev: Optional[float] = None   # D-15 seam: per-box std-dev (DEFERRED)

# === What Phase 3 builds ===
#   PageBox(box=Box(...), origin="detected", payload=blk)
#   PageBox(box=Box(...), origin="user", payload=None)
#
# === What the LATER inpaint phase will build (NOT Phase 3) ===
#   from panelcleaner.image_ops import pick_best_mask
#   fitment = pick_best_mask(base_image, precise_mask, box_mask,
#                            masking_box=page_box.box,
#                            reference_box=page_box.box.pad(n, canvas_size),
#                            masker_conf=config.current_profile.masker,
#                            analytics_page_path=path)
#   if fitment and not fitment.failed:
#       page_box.mask = fitment.best_mask
#       page_box.std_dev = fitment.analytics_std_deviation
#       if page_box.std_dev < threshold:   # uniform-enough region → selective inpaint
#           inpaint_only_the_mask_inside(page_box)
```

### Per-page box persistence (mirrors Phase 2 D-11, T-02-04)
```python
# Source: main_window.py:653-747 (existing on_page_selected seam);
#         core/image_file.py:54-70 (ImageFile dataclass).
# [VERIFIED: local source — main_window.py:692-734 (5-step seam)]

# Step 1 (persist OUTGOING) — extend with boxes, .copy()-detach:
outgoing_idx = self._last_page_index
if outgoing_idx is not None and 0 <= outgoing_idx < len(self.image_files):
    if self.canvas.has_mask():
        self.image_files[outgoing_idx].mask = self.canvas.get_mask().copy()
    if self.canvas.has_boxes():                                    # [NEW]
        # .copy()-detach: materialize fresh Box tuples from current QRectFs
        self.image_files[outgoing_idx].boxes = self.canvas.boxes_snapshot()

# Step 4 (restore INCOMING) — extend with boxes:
incoming_idx = self._current_page_index()
if incoming_idx is not None and 0 <= incoming_idx < len(self.image_files):
    if self.image_files[incoming_idx].mask is not None:
        self.canvas.set_mask(self.image_files[incoming_idx].mask.copy())
    if self.image_files[incoming_idx].boxes:                      # [NEW]
        # .copy()-detach at the incoming boundary (belt-and-suspenders)
        self.canvas.set_boxes([b for b in self.image_files[incoming_idx].boxes])
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 2-stack undo (MASK + IMAGE), surfaced as 4 buttons + 4 shortcuts (`Ctrl+Z`/`Ctrl+Shift+Z` image, `Alt+Z`/`Alt+Shift+Z` mask) | 3-stack undo (MASK + IMAGE + BOXES), unified Ctrl+Z timeline, 2 buttons + 2 shortcuts (D-10/D-11) | Phase 3 | Existing Phase 1 IMAGE entries must widen to `(stamp, (x,y,patch))`; MASK entries to `(stamp, QImage)`. `test_history.py` guards update. `Alt+Z`/`Alt+Shift+Z` removed; two inherited Phase 1 confirm-dialog strings referencing `Alt+Z` must be updated (UI-SPEC §Copywriting PLANNER TODO). |
| Discard `blk_list` from detect result (Phase 1) | Surface `blk_list` as editable BoxItems (Phase 3, D-01) | Phase 3 | `_on_detection_finished` (main_window.py:1284) builds boxes when mode toggle is on. `_run_detection_task` already returns `result["blocks"]` — no worker change. |
| Vendored `panelcleaner/structures.py` as a stub (Phase 1) | Full vendored `structures.py` + new `masker.py` (Phase 3, D-14) | Phase 3 | Stub replaced near-verbatim; std-dev machinery (`MaskFittingResults`, `border_std_deviation`, `pick_best_mask`) becomes available for the D-15 seam. |

**Deprecated/outdated:**
- `Alt+Z` / `Alt+Shift+Z` mask-undo shortcuts (Phase 1): removed in Phase 3 (subsumed by unified `Ctrl+Z`). The `Undo Mask` / `Redo Mask` toolbar buttons (main_window.py:451-452) and Edit-menu items are removed entirely (UI-SPEC Surface 13). `[CITED: 03-UI-SPEC.md §13 + Copywriting PLANNER TODO]`
- The stub `panelcleaner/structures.py` (18-line placeholder): replaced by the full vendored version. The stub's explanatory comment ("Phase 2 scope, deferred here") is now stale — Phase 3 owns the replacement. `[VERIFIED: local source — panelcleaner/structures.py:1-18]`

## Assumptions Log

> All claims in this research were verified against local source files (`../PanelCleaner/pcleaner/`, the vendored `panelcleaner/` tree, and `manga_ai_studio/`). The single `[ASSUMED]` item below is a UX default the planner may override.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The "Detect Boxes" mode toggle defaults to CHECKED (UI-SPEC §Copywriting says "default checked"). | Standard Stack / State of the Art | Low — if the user prefers mask-only by default, the toggle is a one-line default flip; no architectural impact. `[CITED: 03-UI-SPEC.md §Copywriting "Detect Boxes" row]` |

**If this table is otherwise empty:** All other claims in this research were verified or cited — no user confirmation needed. (The single `[ASSUMED]` is a UI default already locked by the UI-SPEC.)

## Open Questions

1. **Should the unified-timeline pop update Phase 1's `MainWindow` shortcut wiring AND the toolbar buttons in the SAME task, or split?**
   - What we know: UI-SPEC Surface 13 contracts the collapse (4 buttons → 2, 4 shortcuts → 2). The `Alt+Z` removal also touches two inherited confirm-dialog strings (main_window.py:1104, 1342).
   - What's unclear: whether the planner wants one task for the HistoryManager algorithm + a separate task for the UI surface collapse, or one combined task.
   - Recommendation: Split — HistoryManager BOXES-stack + unified-timeline pop is pure-core (headless-testable, low risk); the UI-surface collapse (toolbar/menu/shortcut/dialog-string edits) is GUI-wiring (pytest-qt). Two tasks, two test files. Matches Phase 1's plan-06 (core) + plan-04 (GUI) split.

2. **Does the `origin`-tagging wrapper live in `core/box_model.py` (new file) or inline in `gui/box_item.py`?**
   - What we know: D-14 + Claude's Discretion say don't mutate the vendored `Box`; layer origin/identity on top. The wrapper is needed by both the GUI (`BoxItem`) and the persistence layer (`ImageFile.boxes`) and the undo layer (BOXES snapshots).
   - Recommendation: `core/box_model.py` (`PageBox` dataclass per §Code Examples) — pure Python, headless-testable, imported by both GUI and persistence. Keeps `BoxItem` as the Qt view of a `PageBox`.

3. **Is `mask_page` (the batch driver in masker.py) worth keeping in the vendored file at all, or should the vendored `masker.py` contain ONLY the `save_denoising_data` helper + the std-dev seam re-exports?**
   - What we know: Phase 3 does not call `mask_page`. The D-15 later phase calls `image_ops.pick_best_mask` directly (not `mask_page`). `mask_page` is the ONLY consumer of `ost.OutputPathGenerator`.
   - Recommendation: Keep `mask_page` in the vendored file but guard the `ost` import (`try/except ImportError`) so the module imports cleanly. Rationale: near-verbatim per D-12 is easier to audit/diff against upstream than a carved-up file; the dead code is harmless if `ost` is None. The planner decides; this is low-stakes.

4. **Should the `ImageFile.boxes` slot store `list[PageBox]` (origin-tagged) or `list[Box]` (bare vendored)?**
   - What we know: Persistence needs origin (D-03 re-detect rule) and the payload (TextBlock for Phase 4/5). Bare `Box` loses both.
   - Recommendation: `list[PageBox]` (the §Code Examples dataclass). Consistent with the D-15 seam shape.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PySide6 6.7+ | BoxItem, QGraphicsScene, QAction, QMessageBox, QShortcut | ✓ | in pyproject (`>=6.7`); env-verified importable | — |
| attrs | Vendored `structures.py` `@frozen`/`@define` | ✓ | 25.4.0 | — |
| Pillow (PIL) | Vendored std-deviation machinery (`Image.FIND_EDGES`, mode "1") | ✓ | 12.0.0 | — |
| NumPy (<2.0) | `color_std`/`border_std_deviation` math | ✓ | pinned `<2` | — |
| scipy | `image_ops.py` (vendored) | ✓ | in pyproject | — |
| loguru | Vendored `masker.py`/`image_ops.py` | ✓ | in pyproject | — |
| tifffile | Vendored `helpers.py` (transitive, debug drawers only) | ✓ | 2026.1.28 | — |
| psutil | Vendored `helpers.py` (transitive, memory helpers only) | ✓ | 7.2.2 | — |
| configupdater | Vendored `config.py` | ✓ | in pyproject | — |
| `../PanelCleaner/pcleaner/` (GPL v3 reference source) | D-14 vendoring source | ✓ | local checkout at `C:\Src\PanelCleaner\pcleaner\` | — |
| Qt display (for pytest-qt GUI tests) | BoxItem render/select/move/resize tests | ✓ (Windows dev machine per CLAUDE.md) | — | Headless CI would skip GUI tests (existing pattern: `pytest.importorskip("PySide6")`) |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none.

## Validation Architecture

> `workflow.nyquist_validation` is `true` in `.planning/config.json` — this section applies.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-qt + pytest-mock (in `[project.optional-dependencies].dev`) |
| Config file | `pytest.ini` (qt_api=pyside6, testpaths=tests, markers unit/gui) |
| Quick run command | `pytest tests/test_core/test_history.py tests/test_core/test_box_model.py tests/test_core/test_structures_box.py -x` |
| Full suite command | `pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TEXT-01 | `blk_list` → BoxItems when mode on; discarded when off | unit (worker result shape) + gui (canvas build) | `pytest tests/test_gui_detection_boxes.py -x` | ❌ Wave 0 |
| TEXT-01 | Mode toggle gates box creation; box layer auto-shows on detect | gui | `pytest tests/test_gui_detection_boxes.py::test_mode_toggle_gates_boxes -x` | ❌ Wave 0 |
| TEXT-01 | Re-detect replaces detected boxes, keeps user boxes (D-03) | gui | `pytest tests/test_gui_detection_boxes.py::test_redetect_replaces_detected_keeps_user -x` | ❌ Wave 0 |
| TEXT-01 | Confirm gate when re-detecting over detected boxes (D-04) | gui | `pytest tests/test_gui_detection_boxes.py::test_redetect_confirm_gate -x` | ❌ Wave 0 |
| TEXT-03 | Box select (single, D-08) | gui | `pytest tests/test_gui_box_layer.py::test_select_single -x` | ❌ Wave 0 |
| TEXT-03 | Box move (drag body) | gui | `pytest tests/test_gui_box_layer.py::test_move_box -x` | ❌ Wave 0 |
| TEXT-03 | Box resize (corner handle, min 8×8 clamp, D-06) | gui | `pytest tests/test_gui_box_layer.py::test_resize_corner_clamp -x` | ❌ Wave 0 |
| TEXT-03 | Box delete (Delete key, silent, undo recovers, D-12) | gui | `pytest tests/test_gui_box_layer.py::test_delete_silent_undo_recovers -x` | ❌ Wave 0 |
| TEXT-03 | Box create (Alt+drag on empty canvas, D-13) | gui | `pytest tests/test_gui_box_layer.py::test_alt_drag_create -x` | ❌ Wave 0 |
| TEXT-03 | Hit-test before mask-tool dispatch (D-07); hidden layer disables boxes | gui | `pytest tests/test_gui_box_layer.py::test_hidden_layer_no_box_hit -x` | ❌ Wave 0 |
| TEXT-03 | BOXES undo stack + unified-timeline pop (D-10/D-11) | unit | `pytest tests/test_core/test_history.py -k boxes -x` | ❌ Wave 0 (extend existing) |
| TEXT-03 | BOXES snapshot detached from live BoxItems (Pitfall 3) | unit | `pytest tests/test_core/test_history.py::test_boxes_snapshot_is_detached -x` | ❌ Wave 0 |
| TEXT-03 | Per-page box persistence (Phase 2 D-11 mirror, .copy() both boundaries) | gui | `pytest tests/test_gui_box_layer.py::test_box_persistence_uses_copy -x` | ❌ Wave 0 |
| VENDOR (D-14) | Full `structures.py` + `masker.py` import cleanly; ost stubbed | unit | `pytest tests/test_core/test_structures_box.py -x` | ❌ Wave 0 |
| VENDOR (D-14) | `Box.as_tuple_xywh` maps to QRectF; `__contains__` hit-test | unit | `pytest tests/test_core/test_structures_box.py::test_box_qrectf_mapping -x` | ❌ Wave 0 |
| SEAM (D-15) | PageBox carries mask=None, std_dev=None (seam open, not closed) | unit | `pytest tests/test_core/test_box_model.py::test_pagebox_seam_defaults_none -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_core/test_history.py tests/test_core/test_box_model.py tests/test_core/test_structures_box.py -x` (fast, headless core tests)
- **Per wave merge:** `pytest` (full suite incl. pytest-qt GUI tests on the Windows dev machine)
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_core/test_structures_box.py` — covers D-14 vendoring smoke (structures + masker import, Box geometry, QRectF mapping, ost-stubbed masker)
- [ ] `tests/test_core/test_box_model.py` — covers the `PageBox` origin-tagging wrapper + D-15 seam defaults
- [ ] `tests/test_gui_box_layer.py` — covers TEXT-03 select/move/resize/delete/create/hit-test + box-layer toggle + per-page persistence
- [ ] `tests/test_gui_detection_boxes.py` — covers TEXT-01 `_on_detection_finished` builds boxes from `blk_list`, mode toggle, D-03 re-detect rule, D-04 confirm gate
- [ ] EXTEND `tests/test_core/test_history.py` — BOXES stack + unified-timeline pop + Pitfall-3 snapshot-detachment guard; UPDATE existing Phase 1 guards to unpack `(stamp, value)` after the entry-shape widen
- No framework install needed (pytest/pytest-qt/pytest-mock already in `[dev]`).

## Security Domain

> `workflow.security_enforcement` is `true`, `security_asvs_level` is `1`. Phase 3's security surface is small — it adds an interactive UI layer and reads model-produced data structures; no new auth, network, or persistence-trust boundaries. The applicable categories are input validation (blk_list shapes from the model) and the existing Pitfall-2 buffer discipline extended to box geometry.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Desktop app, single-user, no auth (unchanged from Phase 1/2) |
| V3 Session Management | no | No sessions (desktop) |
| V4 Access Control | no | No privileged operations; box edits are local user actions |
| V5 Input Validation | yes | `TextBlock.xyxy` from the model is treated as untrusted: validate it's a 4-int list, clamp to image bounds, reject non-positive-area boxes (the 8×8 min-size clamp on create/resize is the user-facing analog). `Box` constructor takes ints; coerce via `int()` at every TextBlock→Box boundary. The vendored `Box` is `@frozen` (immutable) — no aliasing mutation. |
| V6 Cryptography | no | No crypto (unchanged) |
| V7 Error Handling & Logging | yes | Detection errors ride the existing Phase 1 error path (`_on_detection_error`, loguru + error chip). Box-edit errors (e.g. resize below min) clamp silently per D-06 — no exception surfaced. |
| V8 Data Protection | yes (minimal) | Per-page boxes persist in-memory only (`ImageFile.boxes`); no on-disk serialization in Phase 3 (PROJ-01 `.mas` is Phase 5). `.copy()`-detachment at both persistence boundaries (Pitfall-3 analog of Phase 1 Pitfall-2). |

### Known Threat Patterns for the PySide6/Qt6 + vendored-source stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed `TextBlock.xyxy` (non-int, negative, or out-of-image bounds) crashes box build | Tampering / DoS | Coerce to int, clamp to `[0, image_w/h]`, drop boxes with non-positive area at build-time. The 8×8 min-size clamp (D-06) is the user-facing version. `[VERIFIED: textblock.py:50 stores ints; Box constructor expects ints]` |
| BOXES undo snapshot aliases live `BoxItem` → undo restores wrong state (Pitfall 3) | Tampering | Materialize fresh `Box` tuples from current `QRectF` at push-time; regression guard `test_boxes_snapshot_is_detached`. `[CITED: STATE.md Pitfall-2 discipline]` |
| Crafted image causes vendored `pick_best_mask` / `border_std_deviation` to allocate unbounded memory (the D-15 LATER phase, not Phase 3) | DoS | Phase 3 does not call these. The later inpaint phase must enforce the existing `limit` on mask sizes (image_ops already bounds via `cut_out_box`). Out of scope for Phase 3. |
| Vendored `masker.py`/`structures.py` pull in unmaintained transitive deps | Supply chain | All transitive deps verified present and standard (attrs, PIL, loguru, numpy, scipy — all in pyproject, all top-100 Python packages). No `output_structures.py`/`analytics.py` vendored (stubbed/skipped). `[VERIFIED: env import tests]` |

## Sources

### Primary (HIGH confidence — local source files, the authoritative references for this phase)
- `C:\Src\PanelCleaner\pcleaner\structures.py` (750 lines) — full `Box`/`BoxType`/`PageData`/`MaskData`/`MaskFittingResults` definitions; verified the `as_tuple_xywh` QRectF mapping (line 39-41), `__contains__` (51-59), and the import surface.
- `C:\Src\PanelCleaner\pcleaner\masker.py` (151 lines) — verified imports are exactly `image_ops`/`structures`/`output_structures`; verified `ost.OutputPathGenerator` is used ONLY at line 28 inside `mask_page`; verified `analytics.py` is NOT imported.
- `C:\Src\Manga AI Studio\panelcleaner\image_ops.py` (1158 lines, already vendored) — verified `border_std_deviation` (line 483), `color_std` (464), `pick_best_mask` (568), `cut_out_box` (541) are present and call `st.MaskFittingResults` at lines 706/717 (requires the full structures.py).
- `C:\Src\Manga AI Studio\panelcleaner\structures.py` (18-line stub) — confirmed it must be REPLACED; its comment says "deferred to Phase 2" but Phase 3 now owns the replacement.
- `C:\Src\Manga AI Studio\manga_ai_studio\core\history_manager.py` (193 lines) — verified the 2-stack shape (`_mask_undo/_redo`, `_image_undo/_redo`), the push/pop `.copy()` discipline, the `clear()` reset, the absence of per-entry stamps (Pitfall 4).
- `C:\Src\Manga AI Studio\manga_ai_studio\core\image_file.py` (111 lines) — verified the `mask` slot + `has_mask_content`; confirmed `boxes` slot mirrors cleanly.
- `C:\Src\Manga AI Studio\manga_ai_studio\gui\canvas.py` — verified z-order (image_item → mask_item → preview_item z=900 → cursor_item z=1000 → empty-state z=2000), the mouse-event dispatch (lines 758-837), `_scene_pos`, `zoom_changed` signal, `mask_modified` signal.
- `C:\Src\Manga AI Studio\manga_ai_studio\gui\main_window.py` — verified `_run_detection_task` returns `{"mask":..., "blocks": blk_list}` (line 1217), `_on_detection_finished` discards blocks (line 1284), `_confirm_replace_mask` pattern (1328), `on_page_selected` 5-step seam (653-747), `detect_text` entry (1122), `_op_running` gate.
- `C:\Src\Manga AI Studio\manga_ai_studio\adapters\torch_impl.py` — verified `detect()` (line 104) returns `(mask_refined, blk_list)`; 3-tuple unpack at line 124.
- `C:\Src\Manga AI Studio\panelcleaner\comic_text_detector\utils\textblock.py` — verified `TextBlock.xyxy` is `[int,...]` (line 50), `bounding_rect()` returns `[x,y,w,h]` (line 144-150).
- `C:\Src\Manga AI Studio\pyproject.toml` — verified deps (attrs, pillow, loguru, numpy<2, scipy, natsort, configupdater, PySide6, opencv).
- Active env: verified `attrs 25.4.0`, `PIL 12.0.0`, `loguru`, `tifffile 2026.1.28`, `psutil 7.2.2`, `configupdater` importable; verified `MaskerConfig` has all 8 std-dev fields; verified `panelcleaner.data` + `panelcleaner.ocr.supported_languages` importable.

### Secondary (MEDIUM confidence — design contracts)
- `.planning/phases/03-text-box-detection-interaction/03-UI-SPEC.md` — the locked design contract (D-09 colors, D-13 Alt+drag, Surface 12 BoxItem spec, Surface 13 undo collapse, z-order table, copywriting PLANNER TODO for the orphaned Alt+Z strings).
- `.planning/phases/03-text-box-detection-interaction/03-CONTEXT.md` — D-01..D-15 locked decisions.
- `.planning/STATE.md` — Phase 1/2 accumulated decisions (Pitfall-2 `.copy()` discipline, 2-stack-not-4 warning, vendored-FULL-CTD-tree lesson, per-page persistence seam).
- `.planning/phases/01-cleaning-workspace/01-CONTEXT.md` — Phase 1 foundation (D-10 code org, D-12 vendoring discipline, 2-stack undo).
- `.planning/phases/02-cleaning-output-batch/02-CONTEXT.md` — Phase 2 D-11 per-page persistence pattern (the seam Phase 3 box-persistence mirrors).

### Tertiary (LOW confidence)
- None. All claims verified against local source or cited from a project design doc. Web search providers were disabled in this config; no web claims are made.

## Metadata

**Confidence breakdown:**
- Standard stack (vendoring surface + transitive deps): HIGH — every import path traced through local source and verified importable in the active env.
- Architecture (BoxItem, hit-test dispatch, persistence seam, HistoryManager extension): HIGH — all patterns grounded in existing local code (canvas.py, history_manager.py, main_window.py, image_file.py) and the locked UI-SPEC.
- Pitfalls: HIGH — each pitfall verified against a specific local source line range; Pitfall 1/2 (ost-not-vendored, stub-structures) are concrete import-failure scenarios; Pitfall 3/4 (snapshot aliasing, missing stamps) are direct reads of the existing history_manager.py shape.
- D-15 seam shape: HIGH — `border_std_deviation`/`pick_best_mask`/`MaskFittingResults` verified present in vendored image_ops.py; the `(Box, mask, std_dev)` data-model seam is the natural shape given those signatures.

**Research date:** 2026-07-25
**Valid until:** 2026-08-25 (stable — all claims grounded in committed local source; the only drift risk is upstream PanelCleaner changing `masker.py`/`structures.py`, which is irrelevant since we vendor a snapshot).
