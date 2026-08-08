# Phase 5: Project Persistence, Image Ops & Export - Pattern Map

**Mapped:** 2026-08-08
**Files analyzed:** 20 (6 new core/GUI modules + 3 new dialogs + 7 new test files + 4 modified source files + 1 extended test file... adjusted: 13 new + 7 modified)
**Analogs found:** 13 / 13 new files have external analogs; 7 modified files self-reference (analog = the file itself)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `manga_ai_studio/core/project_io.py` (NEW) | utility/service (serialization) | file-I/O + transform | `manga_ai_studio/core/image_io.py` | exact |
| `manga_ai_studio/core/ocr_export.py` (NEW) | utility/service (projection) | transform + file-I/O | `manga_ai_studio/core/image_io.py` (shape) + `core/batch_runner.py:129-188` (batch loop) | exact / role-match |
| `manga_ai_studio/core/image_ops.py` (NEW) | service (pixel + geometry math) | transform | `manga_ai_studio/core/mask_editor.py` | exact |
| `manga_ai_studio/gui/levels_dialog.py` (NEW) | component (QDialog) | request-response | `manga_ai_studio/gui/load_translations_dialog.py` | exact |
| `manga_ai_studio/gui/resize_dialog.py` (NEW) | component (QDialog) | request-response | `manga_ai_studio/gui/load_translations_dialog.py` | exact |
| `manga_ai_studio/gui/crop_dialog.py` (NEW) | component (QDialog) | request-response | `manga_ai_studio/gui/load_translations_dialog.py` | exact |
| `manga_ai_studio/gui/main_window.py` (EXTEND) | controller (main window) | request-response + event-driven | itself (`_build_file_menu` 258-321, `_build_text_menu` 448-519, `_build_tools_menu` 521-562, `_refresh_action_states` 724-804, `_refresh_recent_menu` 1080-1093, `_dispatch_batch` 3013-3121) | self (sections cited) |
| `manga_ai_studio/gui/canvas.py` (EXTEND) | component (view) | event-driven + transform | itself (`set_image_from_numpy` 609-670, `get_image_numpy` 568-607, `set_mask` 389-419, `mousePressEvent` 858-949, `boxes_snapshot` 1382+, `MAX_IMAGE_DIMENSION` 79) | self (sections cited) |
| `manga_ai_studio/gui/tools_panel.py` (EXTEND) | component (tool dock) | event-driven | itself (`_make_tool_action` 194-209, `_action_to_tool` 127-133, QActionGroup 105-106) | self (sections cited) |
| `manga_ai_studio/core/mask_editor.py` (EXTEND) | utility | transform | itself (`ToolMode` enum 56-69) | self (section cited) |
| `manga_ai_studio/core/history_manager.py` (EXTEND) | store (undo engine) | event-driven | itself (`_stamp` 113-122, `push_image_action` 185-200, `undo` 344-378) + RESEARCH Pattern 2 | self + research |
| `manga_ai_studio/core/image_file.py` (EXTEND) | model | CRUD | itself (dataclass 54-76 — add `original_verified` flag per RESEARCH Open Q6) | self (section cited) |
| `tests/test_core/test_project_io.py` (NEW) | test | — | `tests/test_core/test_image_io.py` | exact |
| `tests/test_core/test_ocr_export.py` (NEW) | test | — | `tests/test_core/test_image_io.py` | exact |
| `tests/test_core/test_image_ops.py` (NEW) | test | — | `tests/test_core/test_box_model.py` / `tests/test_mask_editor/test_mask_editor.py` | exact |
| `tests/test_history.py` (EXTEND) | test | — | itself (add stamp-shared triple-pop tests) | self |
| `tests/test_gui_project.py` (NEW) | test (pytest-qt) | — | `tests/test_gui_batch.py` (MainWindow instantiation) | role-match |
| `tests/test_gui_crop_tool.py` (NEW) | test (pytest-qt) | — | `tests/test_gui_boxes.py` (canvas interaction) | role-match |
| `tests/test_gui_image_dialogs.py` (NEW) | test (pytest-qt) | — | `tests/test_gui_boxes.py` (dialog-driven) | role-match |

## Pattern Assignments

### `manga_ai_studio/core/project_io.py` (utility/service, file-I/O)

**Analog:** `manga_ai_studio/core/image_io.py` — the pure-stdlib+numpy+PIL module template. RESEARCH explicitly names it: "a `core/project_io.py` (`.mas` save/load) and a `core/ocr_export.py` (`_ocr.json`) mirroring its stdlib+PIL-only discipline, headless-testable."

**Module docstring + dependency contract** (image_io.py:1-24) — copy the structure: state the source/origin, the dependency contract ("imports ONLY stdlib + numpy + Pillow — no Qt, no torch, no models — so it is safe to call from a worker thread and unit-testable headless"), and the GPL v3 attribution line. `project_io.py` additionally imports `lzma`, `struct`, `hashlib`, `json` (stdlib — RESEARCH Standard Stack).

**Imports pattern** (image_io.py:26-32):
```python
from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
from PIL import Image
```

**Input validation BEFORE any file I/O** (image_io.py:65-72) — the T-02-01 boundary discipline; project_io must schema-validate `.mas`/manifest input the same way (RESEARCH Security Domain: "strict schema/type validation on load — mirror the Phase 3 V5 `textblock_to_box` `int()` discipline at box_model.py:181-204"):
```python
    # Validate input BEFORE any file is opened/written (mirrors
    # canvas.py:set_image_from_numpy input validation; T-02-01 boundary).
    if (
        image_rgb.ndim != 3
        or image_rgb.shape[2] != 3
        or image_rgb.dtype != np.uint8
    ):
        raise ValueError("expected (H,W,3) uint8 RGB")
```

**Directory creation + write** (image_io.py:105-106):
```python
    path.parent.mkdir(parents=True, exist_ok=True)
    pil.save(path, **kwargs)
```

**Container layout** — use RESEARCH Pattern 1 verbatim (`_MAGIC = b"MAS\x00"`, `_FORMAT_VERSION = 1`, `_pack_entry` with `struct.pack("<HQ", ...)` + `lzma.compress(payload, format=lzma.FORMAT_XZ, preset=6)`, `save_page_file`/`load_page_file` at 05-RESEARCH.md:259-283). Decompression MUST bound sizes: `lzma.decompress(data, format=lzma.FORMAT_XZ, memlimit=…)` + validate image dims against `MAX_IMAGE_DIMENSION = 10000` (canvas.py:79) — RESEARCH Pitfall 6.

**PageBox → JSON mapping** — RESEARCH Common Operation 1 (05-RESEARCH.md:471-490): hand-pick fields (`box` from `Box.as_tuple`, `origin`, `edited`, `bubble_no`, `manual_override`, payload `xyxy`/`lines`/`vertical`/`language`/`font_size`/`text`/`translation`). Do NOT use `TextBlock.to_dict()` (RESEARCH Anti-Pattern 1 — deep-copies numpy arrays, not JSON-serializable). Verified field sets: `PageBox` box_model.py:85-94; `ImageFile` image_file.py:72-76; `TextBlock` textblock.py:50-68.

**Serialization units:** `ImageFile` (image_file.py:54-76) is the per-page unit; `save_image_optimized` (image_io.py:46-106) is the embedded-image writer — call it with PIL `BytesIO` for in-memory encode (RESEARCH Standard Stack "Supporting").

---

### `manga_ai_studio/core/ocr_export.py` (utility/service, transform + file-I/O)

**Analog:** `manga_ai_studio/core/image_io.py` (module shape — pure projection of `PageBox`/`TextBlock` state, no models, no Qt) + `manga_ai_studio/core/batch_runner.py` (batch loop contract for `batch_export_ocr`).

**Batch loop shape** (batch_runner.py:129-188) — copy the loop skeleton for `batch_export_ocr(pages, progress_callback=None, abort_flag=None) -> {"ok", "failed", "total"}`:
```python
    failed: list[tuple[Path, str]] = []
    total = len(pages)
    cleaned_dir.mkdir(parents=True, exist_ok=True)

    for i, page in enumerate(pages):
        # abort check at the loop TOP ONLY (batch_runner.py:137-138)
        if abort_flag is not None and abort_flag.get():
            raise Abort()
        # per-page progress (batch_runner.py:142-144)
        if progress_callback is not None:
            percent = int(i / total * 100) if total else 0
            progress_callback.emit((percent, page.path.name))
        try:
            ...
        except Exception as exc:  # D-04: per-page failure non-fatal
            logger.error(f"Batch: page {page.path.name} failed: {exc}")
            failed.append((page.path, str(exc)))
            continue
    return {"ok": total - len(failed), "failed": failed, "total": total}
```
The last two kwargs MUST be `progress_callback=None, abort_flag=None` to match the Worker auto-injection contract (worker_thread.py:103-109, 113-140). `Abort` + `logger` imports: `from loguru import logger` (batch_runner.py:56), `from manga_ai_studio.gui.worker_thread import Abort` (batch_runner.py:66).

**D-22 location rule** — pristine → `<source>/<stem>_ocr.json` sidecar; geometry-altered → `<source>/cleaned/<stem>_ocr.json` (research Pattern 3 + Open Q4 recommendation; `cleaned/` convention is Phase 2 D-07, asserted by name at batch_runner.py:124-127).

**JSON shape** — RESEARCH Pattern 3 dict (05-RESEARCH.md:334-354): snake_case fields `version`/`img_width`/`img_height`/`blocks[]` with `box`/`vertical`/`text`/`translation`/`bubble_no`/`origin`/`lines[]`. `origin` values from box_model.py:49-50 (`DETECTED = "detected"`, `USER = "user"`). D-20 `\n`-split + per-line box: RESEARCH Common Operation 5 (05-RESEARCH.md:571-581).

---

### `manga_ai_studio/core/image_ops.py` (service, transform)

**Analog:** `manga_ai_studio/core/mask_editor.py` — the pure-mutation-ops module template (D-10: "core/ holds ops"; Qt event dispatch stays in canvas.py).

**Module docstring + imports pattern** (mask_editor.py:1-41) — same shape: pure functions only, `from __future__ import annotations`, `enum` + `numpy` + (PIL for resize); NO Qt imports. Mirror the "Qt EVENT DISPATCH lives in gui/canvas.py" separation statement.

**Pure function shape** (mask_editor.py:72-79 — clamp helper as the T-01-09 discipline model):
```python
def clamp_brush_size(size: int) -> int:
    """Clamp ``size`` to ``[MIN_BRUSH_SIZE, MAX_BRUSH_SIZE]`` (T-01-09)."""
    return max(MIN_BRUSH_SIZE, min(MAX_BRUSH_SIZE, int(size)))
```
Image-op equivalents: clamp spinbox ranges (crop bounds, resize min dims, levels white>black guard — RESEARCH Pattern 4).

**Mask numpy↔QImage boundary to reuse** (mask_editor.py:162-207) — `mask_to_numpy_binary` (alpha threshold to binary `(H,W)` uint8, `.copy()` at 186-187) and `numpy_binary_to_mask_qimage` (rebuild `MASK_PAINT_COLOR` overlay, `.copy()` at 206-207). These are the D-18 pixel-exact transform input/output boundaries. The `.copy()` trailing detach at both bridges is the Pitfall-2 discipline (mask_editor.py:172-176, 197-199).

**Transform math** — RESEARCH Common Operation 3 (05-RESEARCH.md:528-551): `np.rot90(image, k=k).copy()` (k=-1 CW, 1 CCW, 2 180 — ONE convention for image AND mask, RESEARCH Pitfall 4), slice crop `.copy()`, PIL LANCZOS image / NEAREST mask resize, numpy LUT levels `lut[rgb].copy()`.

**Geometry transforms (D-15/D-17)** — RESEARCH Common Operation 2 (05-RESEARCH.md:496-519): `_rotate_point`/`transform_box`/`transform_payload_lines`. Hard rules: NEVER mutate the vendored `Box` (`@frozen`, structures.py:39-44 — build `Box(min(nx1, nx2), min(ny1, ny2), max(nx1, nx2), max(ny1, ny2))`); NEVER mutate `payload.lines` in place before the undo push (Pitfall 3 — build fresh payload copies). D-16 drop/clip policy: RESEARCH Pitfall 10 (report dropped count, clip partial boxes' bbox AND lines).

---

### `manga_ai_studio/gui/levels_dialog.py` / `resize_dialog.py` / `crop_dialog.py` (component, request-response)

**Analog:** `manga_ai_studio/gui/load_translations_dialog.py` — the QSS + QDialog pattern RESEARCH explicitly names ("load_translations_dialog.py is the dialog QSS pattern to copy").

**Dark QSS block** (load_translations_dialog.py:47-72) — copy verbatim the token set (`#232328` bg, `#2d2d33` inputs, `#3a3a42` borders, `#e8e8ea` text, `#00d4ff` accent); extend selectors for the new widgets (QSlider/QSpinBox for Levels/Resize — reuse the slider/spinbox QSS from tools_panel.py:65-82):
```python
_DIALOG_QSS = """
QDialog { background: #232328; }
QLabel { color: #e8e8ea; }
QPlainTextEdit, QComboBox {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 2px;
    color: #e8e8ea;
}
...
QPushButton:default { border: 1px solid #00d4ff; }
"""
```

**QDialog class skeleton** (load_translations_dialog.py:83-149):
```python
    def __init__(self, parent=None, ...) -> None:
        super().__init__(parent)
        self.setWindowTitle("...")
        self.setObjectName("..._dialog")
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setSpacing(8)
        form = QFormLayout()
        ...widgets...
        root.addLayout(form)
        # [Cancel] [Apply] button row
        buttons = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.clicked.connect(self.reject)
        self.apply_btn = QPushButton("Apply", self)
        self.apply_btn.setDefault(True)
        self.apply_btn.clicked.connect(self._on_apply)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.apply_btn)
        root.addLayout(buttons)
        self.setStyleSheet(_DIALOG_QSS)
```

**Collector pattern (pure dialog, no mutation)** — the dialog collects values and stores them as result carriers read after `exec()` (load_translations_dialog.py:147-149, 179-192):
```python
        self.result_text: str = ""
        self.result_page_index: int = 0
```
```python
    def _on_apply(self) -> None:
        """Store the collected values and accept (no mutation)."""
        self.result_text = self.paste_edit.toPlainText()
        self.result_page_index = self.page_combo.currentIndex()
        self.accept()
```
Levels/Resize dialogs extend this with a live-preview contract: RESEARCH Pitfall 9 — preview mutations are SILENT (no history push), keep the pre-dialog numpy detached (`.copy()`) as restore/apply base, Cancel re-displays it silently, Apply pushes ONE entry. Levels white>black guard: RESEARCH Pattern 4 ("clamp internally — white slider minimum = black+1").

**File-dialog error copy** (for Export/Open flows; load_translations_dialog.py:152-177): `QFileDialog.getOpenFileName(self, "…", "", "filter")`, empty-path early return, `except (OSError, UnicodeDecodeError)` → `logger.error(...)` + `QMessageBox.critical(self, f"Couldn't read '{filename}'.", "The file may be corrupt or in an unsupported format.")`.

---

### `manga_ai_studio/gui/main_window.py` (EXTEND, controller)

**Analog:** itself — every section below is the in-file pattern to extend. DO NOT re-read; line refs verified.

**Menu action creation pattern** (`_build_file_menu`, 258-321) — new Save Project…/Open Project… actions copy the `QAction` + shortcut + disabled-init + `triggered.connect` shape; Save Project takes `Ctrl+S` — **and Open Project… (Ctrl+O) REQUIRES removing `self.action_open_image.setShortcut(QKeySequence("Ctrl+O"))` at line 261** (RESEARCH Pitfall 8):
```python
        self.action_export_page = QAction("Export Page\u2026", self)
        self.action_export_page.setShortcut(QKeySequence("Ctrl+E"))
        self.action_export_page.triggered.connect(self.export_page)
        self.action_export_page.setEnabled(False)
```
Menu assembly order (313-321): `file_menu.addAction(...)` / `addMenu(...)` / `addSeparator()`.

**Recent Files → Recent Projects** — the exact pattern to duplicate for `recentProjects` QSettings key (D-07):
- `MAX_RECENT_FILES = 8` (line 72)
- `_settings()` (1051-1054): `QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)`
- `_add_recent_file` (1068-1074): `current.insert(0, path)`; `setValue("recentFiles", [str(p) for p in current[:MAX_RECENT_FILES]])`; `_refresh_recent_menu()`
- `_refresh_recent_menu` (1080-1093): clear, `QAction(path.name)` per entry, `_make_recent_opener` closure (1095-1099), `(empty)` placeholder, separator + Clear action.

**`_build_text_menu` (448-519)** — Export OCR JSON… slot added here (D-21): QAction + status tip + disabled-init + `text_menu.addAction(...)`.

**`_build_tools_menu` (521-562)** — Rotate CW/CCW/180°, Levels…, Resize…, Crop… actions here; tool actions carry `setData(ToolMode)` (556) and connect via `lambda: self.set_active_tool(ToolMode.X)` (557).

**`_refresh_action_states` (724-804)** — the enablement gate pattern for every new action: `page_open = self._current_page_index() is not None`, `folder_open = bool(self.image_files)`, `not self._op_running`, and the D-06 Show Original gating extension (`self.action_show_original.setEnabled(has_inpaint)` at 753-754 → consult `ImageFile.original_verified` + `canvas.rebaseline_original()` per RESEARCH Open Q6). New actions: `setEnabled(page_open and not self._op_running)` shape.

**Save-side flush (Bug-D pattern)** — `_flush_current_canvas_mask_to_data_model` (3123-3142) + the outgoing-index rule. `.mas` save MUST flush canvas state to ImageFile BEFORE serializing (RESEARCH Pitfall 7 — read `_last_page_index`, NEVER `_current_page_index()`; the D-11 seam at on_page_selected 916-946 is the mirror):
```python
        idx = self._current_page_index()
        if idx is None or not (0 <= idx < len(self.image_files)):
            ...
        self.image_files[idx].mask = self.canvas.get_mask().copy()  # .copy() MANDATORY
        self.image_files[idx].boxes = self.canvas.boxes_snapshot()  # detached by construction
```
(RESEARCH Common Operation 4, 05-RESEARCH.md:558-566, gives the `_snapshot_current_page` shape.)

**Unified undo apply** — `_current_undo_state` (1467-1485), `on_undo`/`on_redo` (1487-1519), `_apply_undo_result` (1521-1535) route `(kind, value)` to `canvas.apply_undo_mask/apply_undo_image` / `apply_undo_boxes`. Phase 5 extends these to accept a LIST of `(kind, value)` pairs (RESEARCH Pattern 2: `undo()` returns a list; `on_undo` applies each and flashes `Undo: rotate|crop|levels|resize` via `_show_transient_status` 1566-1583).

**Batch dispatch (Worker path)** — `_dispatch_batch` (3013-3121) is the template for Batch Export OCR JSON (D-21, RESEARCH Open Q4 recommendation): `self._flush_current_canvas_mask_to_data_model()` before dispatch, `Worker(task_fn, *args, abort_signal=self.batch_abort_requested)`, connect progress/result/error/aborted/finished, `self._op_running = True`, `self.file_table.setEnabled(False)`, `progress_bar` setup, `QThreadPool.globalInstance().start(worker)`.

**Dirty tracking + window title** — `setWindowTitle` calls at 203 ("Manga AI Studio") and 1017 (`f"Manga AI Studio \u2014 {path.name}"`); the dirty `*` convention extends this (D-07). `self.history = HistoryManager(limit=20)` (144, 1240).

---

### `manga_ai_studio/gui/canvas.py` (EXTEND, component/view)

**Analog:** itself.

**Image round-trip (the `.mas` save/load bridge + image-op apply path)**:
- `get_image_numpy` (568-607): `qpix.toImage().convertToFormat(RGB888)`, the bytes-per-line padding handling (596-605), **MANDATORY trailing `.copy()`** (607).
- `set_image_from_numpy` (609-670): `(H,W,3)` uint8 validation (631-634), `_original_image_numpy` capture-once (640-641 — **the D-14 re-baseline pitfall**: RESEARCH Pitfall 5 says add `canvas.rebaseline_original()` that sets `self._original_image_numpy = self.get_image_numpy()` + `_showing_original = False`, called after EVERY image op; and a capture-suppressed path for the Levels live preview), `QImage(...).copy()` before `setPixmap` (658-663), sceneRect resize (665-666).
- `show_original` (672-689): the D-06 gate target (`_showing_original` + `_original_image_numpy`).

**Mask boundary** — `set_mask` (389-419: defensive `.copy()` at 405, ARGB32 tint to `MASK_PAINT_COLOR`); `has_mask`/`has_mask_content` (444-465); `get_mask` (479). The D-18 mask transform applies via `set_mask(numpy_binary_to_mask_qimage(transformed))` — mask_editor.py:190-207.

**Crop tool integration point** — `mousePressEvent` dispatch (858-949): the inline-editor guard FIRST (881-889), pan (891-899), box hit-test (903-938), then the mask-tool branch (940-948) — the CROP tool's armed-rect state machine slots alongside (`current_tool != ToolMode.MOVE and self._mask is not None`), with Enter/Esc dispatch in `keyPressEvent` (1146) and the dim-out overlay as a scene item. `MAX_IMAGE_DIMENSION = 10000` (79) is the bounds gate for load-side validation.

**Boxes boundary** — `set_boxes` (1271-1318: `_commit_inline_editor_if_active()` first, `boxes_modified.emit(before)` tail), `boxes_snapshot` (1382-1385+: fresh `PageBox` per item from live rects). Geometry ops apply via `set_boxes` + `apply_undo_boxes` (main_window.py:1537-1564, `_suppress_boxes_push` guard 1554-1564).

---

### `manga_ai_studio/gui/tools_panel.py` (EXTEND, component)

**Analog:** itself — add CROP as the 6th tool:
- `_make_tool_action` (194-209): `QAction(text, self)`, `setCheckable(True)`, `setData(tool)`, `self.tool_group.addAction(act)`.
- `_action_to_tool` dict (127-133): add `self.action_crop: ToolMode.CROP`.
- Tool row assembly (145-161): `QToolButton` + `setDefaultAction` per action.
- Docstring/UI-SPEC surface-6 note (1-23) updates to "6 exclusive tools".
- `ToolMode.CROP` itself is added to the enum in `core/mask_editor.py:56-69` (docstring: "The 5 exclusive mask-editing tools" → 6).

---

### `manga_ai_studio/core/mask_editor.py` (EXTEND, utility)

**Analog:** itself — `ToolMode` enum (56-69):
```python
class ToolMode(enum.Enum):
    MOVE = "move"
    BRUSH = "brush"
    RECTANGLE = "rectangle"
    LASSO = "lasso"
    ERASER = "eraser"
```
→ add `CROP = "crop"` (D-11, the 6th tool). No other changes to this file expected (RESEARCH structure: `core/mask_editor.py — EXTEND — ToolMode.CROP added to the enum`).

---

### `manga_ai_studio/core/history_manager.py` (EXTEND, store)

**Analog:** itself + RESEARCH Pattern 2 (05-RESEARCH.md:293-327) — the recommended stamp-shared triple push. Existing pieces to build on:

**The stamp source** (`_stamp`, 113-122) — monotonic integer counter, NOT wall-clock (Pitfall 4):
```python
    def _stamp(self) -> int:
        self._seq += 1
        return self._seq
```

**Single-store push shape** (`push_image_action`, 185-200 — the `.copy()` + redo-clear + limit discipline):
```python
        self._image_undo.append(
            (self._stamp(), (int(x), int(y), patch.copy()))
        )
        self._image_redo.clear()
        if len(self._image_undo) > self.limit:
            self._image_undo.pop(0)
```

**Full-frame IMAGE entry is already handled** — `pop_image_undo` (202-227) slices `current_img[y:y+h, x:x+w]` for the redo stash and returns `(x, y, patch.copy())`; a geometry op pushes a full-frame patch at `(0, 0)` and the existing machinery works (RESEARCH Pattern 2 rationale). Null-current guards (WR-01, 159-165) must be preserved.

**New method (from RESEARCH Pattern 2):**
```python
def push_geometry_state(self, image_patch: np.ndarray,
                        mask_qimage: QImage | None,
                        boxes: list | None) -> None:
    """Push one op across IMAGE + MASK + BOXES with a SINGLE stamp."""
    stamp = self._stamp()
    self._image_undo.append((stamp, (0, 0, image_patch.copy())))
    self._image_redo.clear()
    if mask_qimage is not None:
        self._mask_undo.append((stamp, mask_qimage.copy()))
        self._mask_redo.clear()
    if boxes is not None:
        self._boxes_undo.append((stamp, self._materialize_snapshot(boxes)))
        self._boxes_redo.clear()
```

**Unified pop extension** — existing `undo()` (344-378) pops only the max-stamp SINGLE store; Phase 5 changes it to pop EVERY store whose tail stamp equals the max and return `list[(kind, value)]` (RESEARCH Pattern 2:305-326). The `_materialize_snapshot` (251-275) detachment is reused for the boxes side; per-type pop methods (pop_mask_undo/pop_image_undo/pop_boxes_undo) stay untouched. Same change mirrored in `redo()` (380-403).

---

### `manga_ai_studio/core/image_file.py` (EXTEND, model)

**Analog:** itself — the dataclass (54-76). Add the D-06 flag (RESEARCH Open Q6):
```python
    path: Path
    thumbnail: QPixmap | None = None
    mask: QImage | None = None
    boxes: list["PageBox"] | None = None
    dirty: bool = False
```
→ add `original_verified: bool = False` (set during `.mas` load when path-ref + sha256 match; `_refresh_action_states` consults it for Show Original gating). No other model changes — `boxes` slot already holds `list[PageBox]` (the serialization source for both `.mas` and `_ocr.json`).

---

### Test files (NEW/EXTEND)

**Core tests — analog `tests/test_core/test_image_io.py`:**
- Module docstring stating scope + headless claim (1-17); imports `from pathlib import Path`, `numpy as np`, `pytest`, target module (19-29); `tmp_path` fixture param (38); `@pytest.mark.unit` (37).
- New files: `tests/test_core/test_project_io.py` (round-trips, checksum rule, climb detection, D-15 seam — RESEARCH Validation Architecture map), `tests/test_core/test_ocr_export.py` (shape, `\n`-split, D-22 location, zero-box), `tests/test_core/test_image_ops.py` (rotate/crop/resize/levels + geometry).

**History tests — extend `tests/test_history.py`:** the file already uses `pytest.importorskip("PySide6")` (23) + `HistoryManager` instantiation without widgets (86-100). Add the stamp-shared regression: `test_geometry_undo_reverses_all_three` (one Ctrl+Z pops image+mask+boxes; RESEARCH Open Q2).

**GUI tests — analog `tests/test_gui_batch.py` / `tests/test_gui_boxes.py`:** pytest-qt `qtbot`, real `MainWindow` instantiation. New: `tests/test_gui_project.py` (dirty title, Save/Open prompt, Show Original gating), `tests/test_gui_crop_tool.py` (armed rect, Enter/Esc, 8×8 min), `tests/test_gui_image_dialogs.py` (Levels Cancel-restores-exactly, Apply-pushes-one). `tests/conftest.py` needs NO change (importorskip + tmp_path already present — RESEARCH Wave 0).

---

## Shared Patterns

### `.copy()` buffer discipline (Pitfall 2 — the phase's #1 invariant)
**Sources:** `canvas.py:606-607` (`get_image_numpy` trailing `.copy()`), `canvas.py:658-663` (QImage-from-numpy `.copy()` before setPixmap), `mask_editor.py:186-187` / `206-207` (numpy↔QImage bridges), `main_window.py:929` (`ImageFile.mask` boundary), `image_file.py:91` (`load_thumbnail` detach).
**Apply to:** `.mas` load (every embedded QImage/numpy `.copy()` before entering `ImageFile.mask` / `set_image_from_numpy` / `set_mask`), image-op apply path, undo snapshots, Levels-dialog preview base. Regression guard style: `test_mask_persistence_uses_copy` (test_history.py) / `test_inpaint_result_display_uses_copy` (RESEARCH Pitfall 2).

### The D-11 seam / outgoing-index rule
**Source:** `main_window.py:877-966` (`on_page_selected` steps 1/1b, `_last_page_index`), `main_window.py:3123-3142` (Bug-D flush).
**Apply to:** Save Project… and Batch Export OCR JSON must flush the CURRENT canvas page via `_flush_current_canvas_mask_to_data_model()` + `boxes_snapshot()` and correlate via `_last_page_index` — never `_current_page_index()` (RESEARCH Pitfall 7).

### Worker + `_op_running` gate (Batch Export OCR JSON)
**Source:** `main_window.py:3013-3121` (`_dispatch_batch`), `worker_thread.py:103-169` (Worker contract: last-two-kwargs injection, `Abort` raise, `finished` always emitted — cleanup always runs).
**Apply to:** Batch Export OCR JSON (RESEARCH Open Q4 recommendation — Worker path; per-page failure isolation mirrors batch_runner.py:183-186).

### Input validation at untrusted-file boundaries
**Source:** `box_model.py:181-204` (`textblock_to_box` int coercion), `image_io.py:65-72` (pre-write validation), `canvas.py:79` (`MAX_IMAGE_DIMENSION`).
**Apply to:** `.mas` load (schema-check, int coercion, bounds clamp, `memlimit` on lzma.decompress — RESEARCH Pitfall 6 + Security Domain), manifest `original` ref (path resolve + suffix allowlist), Levels/Resize/Crop spinbox clamps.

### Error UX copy
**Source:** `load_translations_dialog.py:168-176` (`Couldn't read '{filename}'.` critical dialog + loguru traceback).
**Apply to:** `.mas` open failures ("Couldn't open '{filename}'." — RESEARCH Security Domain corrupt-project copy), save failures, single-page export errors.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | — | — | Every new file has an exact or role-match analog. The genuinely novel code (LZMA2 container, geometry transforms, stamp-shared undo) has no in-repo precedent — use RESEARCH.md Patterns 1-4 + Common Operations 1-5 as the design source (all empirically verified this session); the module SHAPES all come from the analogs above. |

## Metadata

**Analog search scope:** `manga_ai_studio/core/` (9 files), `manga_ai_studio/gui/` (12 files), `tests/` (30 files), `manga_ai_studio/config/`, `manga_ai_studio/adapters/`
**Files scanned:** 20 (13 new + 7 modified)
**Pattern extraction date:** 2026-08-08

**Research-derived patterns (no in-repo analog, verified by researcher):**
- LZMA2 container layout — 05-RESEARCH.md Pattern 1 (259-283)
- Stamp-shared triple push — 05-RESEARCH.md Pattern 2 (293-327)
- `_ocr.json` shape — 05-RESEARCH.md Pattern 3 (334-354)
- Levels LUT + 768-entry PIL pitfall — 05-RESEARCH.md Pattern 4 (366-374)
- Geometry transform math — 05-RESEARCH.md Common Operations 2-3, 5 (496-581)
