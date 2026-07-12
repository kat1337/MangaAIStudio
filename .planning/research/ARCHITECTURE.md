# Architecture Research

**Domain:** Manga scanlation desktop application (PySide6 + ONNX)
**Researched:** 2026-07-11
**Confidence:** HIGH (primary reference is MangaCleaner_GPU source code, read in full)

## Reference Architecture: MangaCleaner_GPU (STARTING POINT)

**This is the most important finding of the research phase.** MangaCleaner_GPU (`~/Downloads/MangaCleaner_GPU/_internal/src/`) is already ~60% of our target app. We are not building from scratch — we are *extending* it.

### MangaCleaner_GPU's structure (read and verified)

```
src/
├── backend/
│   ├── onnx_engine.py    # ONNXEngine: hardware-aware ONNX session (CUDA→CPU fallback)
│   ├── ai_manager.py     # AIManager: singleton managing OCR + LaMa engine lifecycle, VRAM flush
│   ├── processor.py      # ImageProcessor: run_ocr_logic (heatmap mask), run_clean_logic (LaMa tiles)
│   ├── workers.py        # AIWorker(QObject): QThread worker with finished/progress/error signals
│   ├── batch_engine.py   # BatchEngine(QObject): folder batch with page_started signal
│   └── photoshop.py      # PhotoshopBridge (Windows COM — defer/drop)
├── frontend/
│   ├── canvas.py         # MangaCanvas(QGraphicsView): image+mask layers, brush/rect/lasso tools
│   ├── main_window.py    # MainWindow: 3-pane layout (file list | canvas | tools), shortcuts, threading
│   ├── widgets.py        # FileListWidget, ToolGroup, BrushSlider, HardwareMonitor
│   ├── help_system.py    # In-app help
│   └── styles.qss        # Deep Obsidian theme
└── utils/
    ├── config.py         # Config: colors, brush size, max history, tile width
    ├── history.py        # HistoryManager: 4-stack undo/redo (image undo/redo, mask undo/redo)
    ├── logger.py         # logging wrapper
    ├── paths.py          # Paths: frozen-aware BASE_DIR, models/logs/cache/processed dirs
    └── system_info.py    # SystemMonitor: RAM/GPU telemetry
```

### What MangaCleaner_GPU already gives us (reuse directly)
- ✅ PySide6 QGraphicsView canvas with pan/zoom (`MangaCanvas`)
- ✅ Image + mask as stacked QGraphicsPixmapItems
- ✅ Brush / rectangle / lasso mask painting with eraser toggle (Shift)
- ✅ ONNX inference with CUDA→CPU auto-fallback (`ONNXEngine`)
- ✅ Engine lifecycle + VRAM management (`AIManager`)
- ✅ LaMa tile-based inpainting with connected-components blob analysis (`run_clean_logic`)
- ✅ Heatmap-based text detection → binary mask (`run_ocr_logic`)
- ✅ QThread async execution with progress signals (`AIWorker`)
- ✅ 4-stack undo/redo (`HistoryManager`)
- ✅ Folder batch processing (`BatchEngine`)
- ✅ PNG/JPG export
- ✅ PyInstaller packaging layout (frozen-aware `Paths`)

### What MangaCleaner_GPU LACKS (we must build)
- ❌ **Text boxes as first-class objects** — its detection produces a *pixel mask*, not editable box objects
- ❌ **manga-ocr per-box OCR** — its `ocr.onnx` is a heatmap detector, not a text recognizer
- ❌ **Text editing / translation layer**
- ❌ **Project save/load** — no persistence beyond batch output
- ❌ **OCR JSON export**
- ❌ **Basic image ops** (crop/rotate/levels/resize)
- ❌ **Per-region LaMa params** — single global tile size only
- ❌ **Dual-mode batch→editor navigation**
- ❌ **Box move/resize/delete** interaction

## Proposed Architecture for Manga AI Studio

### Component Map

```
┌─────────────────────────────────────────────────────────────┐
│                     frontend/ (PySide6)                       │
│  ┌──────────────┐  ┌────────────────────┐  ┌──────────────┐ │
│  │  PageList     │  │     EditorCanvas    │  │  ToolPanels  │ │
│  │  (file sidebar│  │  (QGraphicsView)    │  │  (mask tools,│ │
│  │  + batch nav) │  │                     │  │   box tools, │ │
│  └──────┬───────┘  │  Layers (Z-order):   │  │   text panel,│ │
│         │          │   1. image pixmap    │  │   image ops) │ │
│         │          │   2. cleaned overlay │  └──────┬───────┘ │
│         │          │   3. mask pixmap     │         │         │
│         │          │   4. box items       │─────────┘         │
│         │          │   5. cursor          │                   │
│         │          └──────────┬───────────┘                   │
│         │                     │                               │
│  ┌──────▼─────────────────────▼───────────────────────────┐  │
│  │            MainWindow (controller)                       │  │
│  │  tool mode switching, threading, shortcuts, export       │  │
│  └──────┬────────────────┬───────────────┬─────────────────┘  │
└─────────┼────────────────┼───────────────┼────────────────────┘
          │                │               │
┌─────────▼───────┐ ┌──────▼──────┐ ┌──────▼─────────┐
│   PageState      │ │ AIWorker    │ │ ProjectStore    │
│   (data model)   │ │ (QThread)   │ │ (.mas read/write)│
│  - source_img    │ │             │ │                  │
│  - cleaned_img   │ │  runs:      │ │  serializes:     │
│  - mask (QImage) │ │  - detect   │ │  - image refs    │
│  - boxes[]       │ │  - inpaint  │ │  - mask PNG      │
│  - tool mode     │ │  - ocr      │ │  - boxes JSON    │
│  - image ops log │ │             │ │  - settings      │
└────────┬─────────┘ └──────┬──────┘ └──────┬───────────┘
         │                  │               │
┌────────▼──────────────────▼───────────────▼──────────────────┐
│                       backend/                                │
│  ┌────────────┐ ┌──────────────┐ ┌──────────┐ ┌────────────┐ │
│  │ ONNXEngine │ │ ImageProc    │ │ OCR       │ │ Exporter   │ │
│  │ (LaMa,det) │ │ (clean,dilate│ │ (manga-ocr│ │ (PNG, JSON)│ │
│  │            │ │  tile, ops)  │ │  per-box) │ │            │ │
│  └─────┬──────┘ └──────────────┘ └─────┬────┘ └────────────┘ │
│        │                                │                     │
│  ┌─────▼────┐                     ┌─────▼──────┐              │
│  │AIManager │                     │ manga_ocr  │              │
│  │(lifecycle│                     │ OR onnxocr │              │
│  │ VRAM)    │                     │ (model)    │              │
│  └──────────┘                     └────────────┘              │
└───────────────────────────────────────────────────────────────┘
```

### Key Architectural Decisions

**1. Canvas = single QGraphicsView with layered items + tool modes**

MangaCleaner_GPU's `MangaCanvas` already stacks `image_item` and `mask_item` as QGraphicsPixmapItems. We extend this pattern:
- Add a `cleaned_item` layer (overlay of inpainted result, toggleable)
- Add **box items** as QGraphicsRectItem/QGraphicsTextItem children (NOT a pixmap — boxes are objects)
- Tool mode determines what mouse events do: `MOVE`, `MASK_BRUSH`, `MASK_RECT`, `MASK_LASSO`, `BOX_DRAW`, `BOX_SELECT`, `IMAGE_CROP`

This avoids the "two canvases" trap — one canvas, one event handler, mode-dispatched behavior. This is how MangaCleaner_GPU already works for mask tools.

**2. Text boxes are data objects, not pixels**

```python
@dataclass
class TextBox:
    id: str
    rect: QRectF           # position/size on canvas
    recognized_text: str   # manga-ocr output
    translated_text: str   # manual translation (empty until user types)
    ocr_confidence: float  # optional, from model
    source: str            # "auto-detect" | "manual-draw"
```

`PageState.boxes: list[TextBox]`. The canvas renders them as box graphics items; the side panel edits their text fields. This separation is what makes boxes movable/editable/deletable — unlike MangaCleaner_GPU's mask pixels.

**3. OCR runs per-box, not per-page**

MangaCleaner_GPU's `run_ocr_logic` produces a *page-wide heatmap mask*. We keep that for **mask detection** (LaMa cleaning). But for **text recognition**, we add a separate path: for each `TextBox`, crop the source image to the box rect → run manga-ocr → fill `recognized_text`. This runs in `AIWorker` on a QThread, emitting results per-box.

Two OCR models in play:
- **Text detector** (existing `ocr.onnx` or PanelCleaner's detector): page-wide heatmap → where is text? (drives mask + box creation)
- **Text recognizer** (manga-ocr): per-crop → what does the text say?

**4. Threading: QThread + AIWorker (proven pattern)**

MangaCleaner_GPU's pattern is correct and we keep it: `worker.moveToThread(worker_thread)` → `worker_thread.started` connects to the worker slot → worker emits `finished`/`progress`/`error` signals → `main_window` handles them on the GUI thread. **Never call ONNX/OCR on the GUI thread.**

**5. .mas project format — zip-based**

```
project.mas (zip)
├── manifest.json     # version, page count, app version, settings
├── pages/
│   ├── 001/
│   │   ├── source.png     # original (or path reference if too large)
│   │   ├── cleaned.png    # inpainted result (optional — regenerable)
│   │   ├── mask.png       # mask layer
│   │   └── boxes.json     # TextBox[] for this page
│   ├── 002/
│   └── ...
└── settings.json     # LaMa tile size, brush defaults, etc.
```

Zip (not a custom binary format) because: Python's `zipfile` is stdlib, easy to inspect/debug, and handles many files cleanly. Source images can be referenced by path (not copied) if the user opts for a lightweight project.

**6. Model file layout (reuse MangaCleaner_GPU's Paths)**

```
models/
├── lama.onnx          # inpainting (from MangaCleaner_GPU, 197MB)
├── detector.onnx      # text heatmap detection (from MangaCleaner_GPU's ocr.onnx, 4.6MB)
└── manga-ocr/         # manga-ocr model (transformers or ONNX export)
    ├── config.json
    ├── model.safetensors (or onnx/model.onnx)
    └── ...
```

### Data Flow

**Cleaning flow (single page):**
```
user clicks "Detect" → AIWorker.run_detect(source_img)
  → ImageProcessor.run_ocr_logic → heatmap → binary mask + dilation
  → mask displayed on canvas (red overlay)
user paints/erases mask edits → mask updated, push_mask_state (undo)
user clicks "Clean" → AIWorker.run_clean(source_img, mask, tile_size)
  → ImageProcessor.run_clean_logic → LaMa per blob-tile
  → cleaned image replaces source on canvas, push_image_action (undo)
```

**OCR flow (single page):**
```
user clicks "Detect Boxes" → AIWorker.run_box_detect(source_img)
  → box detector → list of QRectF regions
  → creates TextBox objects on PageState, renders box items on canvas
user draws a box (BOX_DRAW tool) → creates empty TextBox → AIWorker.run_ocr(crop)
  → manga-ocr → recognized_text → fills box, renders in side panel
user edits text in side panel → TextBox.recognized_text updated
user adds translation → TextBox.translated_text updated
```

**Batch flow (chapter):**
```
user selects folder → BatchEngine.initialize_batch(paths)
loop per page (AIManager.set_persistence(True) keeps models hot):
  load image → run_detect → run_clean → run_box_detect → run_ocr (per box)
  save cleaned PNG + boxes.json to output dir
finalize: AIManager.flush()
user can then open any page in editor to fix masks/boxes/text
```

### Suggested Build Order

Derived from the dependency graph in FEATURES.md:

1. **Foundation: Canvas + image load + mask tools** — lift MangaCleaner_GPU's `canvas.py`, `widgets.py`, `main_window.py` (simplified). Get to parity with MangaCleaner_GPU's cleaning: open, detect mask, paint mask, LaMa clean, export.
2. **Text-box data model + canvas box items** — the new core. `TextBox` dataclass, box graphics items, draw/select/move/resize/delete interaction.
3. **Box detection pipeline** — adapt a text-box detector (mokuro's model or PanelCleaner's Comic Text Detector) to output `TextBox[]` instead of a heatmap. ONNX export.
4. **manga-ocr per-box recognition** — integrate `MangaOcr` (transformers path first). Wire to AIWorker.
5. **Text editing + translation panel** — side panel with recognized/translated text fields per selected box.
6. **Project persistence (.mas)** — zip format, save/load, resume session.
7. **Basic image ops** — crop/rotate/levels/resize (OpenCV, modest).
8. **Batch orchestrator (extended)** — extend MangaCleaner_GPU's BatchEngine to run detect+clean+ocr+save, then allow editor re-entry.
9. **JSON export** — mokuro-style `_ocr.json` per page.
10. **Packaging** — PyInstaller spec, model distribution, first-run download UX.

This order ensures each phase delivers testable value and depends only on prior phases.

---
*Architecture research for: manga scanlation desktop application*
*Researched: 2026-07-11*
