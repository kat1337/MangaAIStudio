# Phase 2: Cleaning Output & Batch - Pattern Map

**Mapped:** 2026-07-23
**Files analyzed:** 7 (2 MODIFY + 5 NEW)
**Analogs found:** 7 / 7 (every file has a concrete, exact-match analog in the Phase 1 codebase or the in-repo PanelCleaner reference)

Phase 2 is an **integration/wiring phase**, not a new-pipeline phase (02-RESEARCH.md §Summary). Every "hard" subproblem already has a Phase 1 solution; the new code is small (a page-loop task function, an `ImageFile.mask` persistence seam, a ~30-line output writer). This document points the planner at the exact analog line ranges to copy patterns from.

> **Line-number caveat:** Line numbers below are accurate as of this mapping session (2026-07-23) for the files read in full. When the planner copies a pattern, it should anchor on the *named method/identifier*, not the raw line, because preceding edits may shift offsets. Every excerpt names its source method.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `manga_ai_studio/core/image_file.py` (MODIFY) | model | in-memory state | `manga_ai_studio/core/image_file.py` (itself) + `manga_ai_studio/gui/canvas.py:set_mask`/`get_mask` | exact (self) |
| `manga_ai_studio/gui/main_window.py` (MODIFY) | controller | request-response + event-driven | `manga_ai_studio/gui/main_window.py:detect_text`/`inpaint` + `on_page_selected` (itself) | exact (self) |
| `manga_ai_studio/core/batch_runner.py` (NEW) | service | batch / event-driven | `manga_ai_studio/gui/main_window.py:_run_detection_task`/`_run_inpaint_task` + `worker_thread.py:Worker` | exact |
| `manga_ai_studio/core/image_io.py` (NEW) | utility | file-I/O / transform | `../PanelCleaner/pcleaner/image_export.py:save_optimized` | exact (GPL v3, adapt per D-12) |
| `tests/test_core/test_image_io.py` (NEW) | test | unit | `tests/test_inpainting/test_lama_adapter.py` (unit marker, tmp_path, PIL round-trip asserts) | exact |
| `tests/test_core/test_batch_runner.py` (NEW) | test | unit/integration | `tests/test_inpainting/test_lama_adapter.py:FakeSimpleLama` + `test_inpaint_gui.py:_FakeInpaintModel` | exact |
| `tests/test_gui_batch.py` (NEW) | test | GUI (pytest-qt) | `tests/test_inpainting/test_inpaint_gui.py:_make_window`/`_open_page`/`_paint_mask_on_canvas` + `_FakeInpaintModel` | exact |

**Data-flow glossary for this phase:**
- "in-memory state" (image_file.py) — the D-11 mask lives on a dataclass slot, not a service.
- "request-response" (main_window.py batch actions) — one menu click → one Worker dispatched; mirrors Phase 1 detect/inpaint.
- "batch / event-driven" (batch_runner.py) — a single Worker task fn loops pages, emitting `progress_callback` + reading `abort_flag` between pages (RESEARCH Pattern 2).
- "file-I/O / transform" (image_io.py) — pure numpy→PIL→file; no Qt, thread-safe.

---

## Pattern Assignments

### `manga_ai_studio/core/image_file.py` (model, in-memory state — MODIFY)

**Analog:** itself (`C:\Src\Manga AI Studio\manga_ai_studio\core\image_file.py`). The `mask: QImage | None` slot **already exists** (verified at `ImageFile` dataclass line 69) and is currently unused for persistence. Phase 2 changes the *semantics* (populate at `on_page_selected` boundary), not the *schema*.

**Current dataclass** (lines 54-70) — no field additions needed:
```python
@dataclass
class ImageFile:
    path: Path
    thumbnail: QPixmap | None = None
    mask: QImage | None = None     # <-- D-11 persistence target (already here)
    dirty: bool = False
```

**`clear_mask` helper already present** (lines 88-91) — reuse it for Batch Clean's mask-clear-after-inpaint path if needed:
```python
def clear_mask(self) -> None:
    self.mask = None
    self.dirty = True
```

**Imports pattern** (lines 14-20) — unchanged; the module already imports `QImage`:
```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
```

**Change required (small):** Possibly add a `has_mask_content()` convenience that mirrors `canvas.has_mask_content()` (canvas.py:348-365) for the D-03 gate when reading a persisted mask. RESEARCH.md §Code Examples gives the shape — reuse `core.mask_editor.mask_to_numpy_binary` (do NOT reimplement the alpha scan):

```python
# Adapted shape (RESEARCH.md §Code Examples → "Mask content check"):
from manga_ai_studio.core.mask_editor import mask_to_numpy_binary
def has_mask_content(self) -> bool:
    if self.mask is None or self.mask.isNull():
        return False
    return bool(mask_to_numpy_binary(self.mask).any())
```

**Buffer discipline (Pitfall 2, CRITICAL):** Anything written into `self.mask` MUST be `.copy()`-detached from the canvas buffer. See the `on_page_selected` seam in `main_window.py` (next file) — the `.copy()` happens at the boundary, so `image_file.py` itself stays free of `.copy()` calls.

---

### `manga_ai_studio/gui/main_window.py` (controller, request-response + event-driven — MODIFY)

**Analog:** itself. This is the highest-leverage edit surface. The four sub-changes below each copy a Phase 1 method verbatim in shape.

#### 4a. `on_page_selected` D-11 mask save/restore seam (the central change)

**Analog:** `MainWindow.on_page_selected` (lines 561-580). Current body:
```python
def on_page_selected(self, path: Path) -> None:
    self.reset_history()
    if not self.canvas.set_image_from_path(path):
        QMessageBox.warning(self, "Couldn't open file", ...)
        return
    self.setWindowTitle(f"Manga AI Studio \u2014 {path.name}")
    self.canvas.fit_to_window()
    self._add_recent_file(path)
    self._refresh_status_bar()
```

**Change required (RESEARCH.md §Code Examples → "D-11 persistence seam"):** Persist the OUTGOING page's canvas mask before `reset_history`, restore the INCOMING page's persisted mask after `set_image_from_path`. Keep `reset_history` (undo is correctly per-page — Pitfall 1 warning). Helpers to reuse: `canvas.has_mask()` (canvas.py:344), `canvas.get_mask()` (canvas.py:379), `canvas.set_mask()` (canvas.py:289), `_current_page_index()` (main_window.py:490).

```python
# The seam shape to insert (every .copy() is MANDATORY — Pitfall 2):
def on_page_selected(self, path: Path) -> None:
    # 1. Persist OUTGOING page's mask (if any) BEFORE resetting.
    current_idx = self._current_page_index()
    if current_idx is not None and self.canvas.has_mask():
        self.image_files[current_idx].mask = self.canvas.get_mask().copy()
    # 2. Existing per-page undo reset (unchanged).
    self.reset_history()
    # 3. Load the new page image (unchanged).
    if not self.canvas.set_image_from_path(path):
        QMessageBox.warning(self, "Couldn't open file", ...); return
    # 4. Restore INCOMING page's persisted mask (if any).
    target_idx = self._current_page_index()
    if (target_idx is not None
            and self.image_files[target_idx].mask is not None
            and not self.image_files[target_idx].mask.isNull()):
        self.canvas.set_mask(self.image_files[target_idx].mask.copy())
    # 5. Unchanged tail.
    self.setWindowTitle(...); self.canvas.fit_to_window()
    self._add_recent_file(path); self._refresh_status_bar()
```

Note: `_current_page_index()` reads `file_table.current_path()`, which flips to the new path on the `select_path` call that precedes `on_page_selected` (see `_set_pages` lines 553-556). The OUTGOING index must therefore be captured BEFORE any path mutation, OR captured by tracking the previous selection in a field. **Flag for planner:** verify which side of `file_table.select_path` the `on_page_selected` call sits; if `select_path` runs first, `_current_page_index()` already returns the INCOMING index and the OUTGOING index needs a stored `_last_page_index` field. (RESEARCH.md Open Question Q2 / assumption A5 also recommend disabling page-switch during a batch to avoid a write/write race on `ImageFile.mask`.)

#### 4b. Three batch action dispatch (mirror `detect_text`/`inpaint`)

**Analog:** `MainWindow.detect_text` (lines 955-996) and `MainWindow.inpaint` (lines 1252-1298). Both are identical in shape: `_op_running` guard → resolve path → `backend_factory` → build `Worker` → connect 4 signals → set `_op_running` + refresh actions + show progress bar + status text → `QThreadPool.globalInstance().start(worker)`.

```python
# Source: main_window.py:955-996 (detect_text dispatch, VERIFIED):
if self._op_running:
    return
path = self.file_table.current_path()
if path is None:
    return
model = backend_factory("detection", self._detection_backend())

worker = Worker(self._run_detection_task, path, model)
worker.signals.progress.connect(self._on_detection_progress)
worker.signals.result.connect(self._on_detection_finished)
worker.signals.error.connect(self._on_detection_error)
worker.signals.finished.connect(self._on_detection_cleanup)
worker.setAutoDelete(True)

self._op_running = True
self._refresh_action_states()
self.error_chip.hide()
self.progress_bar.setRange(0, 100)
self.progress_bar.setValue(0)
self.progress_bar.show()
self.status_bar_left.setText("Detecting text\u2026 0%")
QThreadPool.globalInstance().start(worker)
```

**Batch variant differences (D-05/D-09):**
- Task fn is `self._run_batch_task` (in `batch_runner.py`, see next file) instead of `_run_detection_task`.
- Pass the page list (`self.image_files` / their paths), the mode (`"detect"`/`"clean"`/`"detect_and_clean"`), and both resolved model paths. **Load each model ONCE before the loop** (Pitfall 3) — see batch_runner pattern.
- Add `abort_signal=self._batch_abort_signal` to the `Worker(...)` constructor → it auto-injects `abort_flag` into the task kwargs and connects the signal to `Worker.abort` (worker_thread.py:138-140). Connect `worker.signals.aborted` to a `_on_batch_aborted` handler (mirrors `_on_detection_cleanup`).
- No `_confirm_replace_mask` (batch is non-interactive; review happens in between per D-02, and Batch Clean uses masks as-is — CONTEXT.md D-02 "edits are sacred").

#### 4c. Batch progress + cleanup handlers (mirror `_on_detection_*`)

**Analog:** `_on_detection_progress` (lines 1108-1115), `_on_detection_finished` (1117-1136), `_on_detection_error` (1138-1153), `_on_detection_cleanup` (1155-1159).

```python
# Progress handler — D-10 says progress = "page count + current page name".
# Source shape: _on_detection_progress (main_window.py:1108-1115):
def _on_batch_progress(self, payload) -> None:
    if isinstance(payload, tuple) and len(payload) == 2:
        percent, page_name = payload
        self.progress_bar.setValue(int(percent))
        self.status_bar_left.setText(f"Cleaning\u2026 {int(percent)}% \u2014 {page_name}")

# Cleanup handler — Pitfall 7: _op_running MUST clear unconditionally
# (the Worker.run finally ALWAYS emits finished). Source: _on_detection_cleanup (1155-1159):
def _on_batch_cleanup(self, _args) -> None:
    self._op_running = False
    self.progress_bar.hide()
    self._refresh_action_states()

# Result/summary handler — D-04: show "28/30, 2 failed" summary.
# Shape mirrors _on_detection_finished but the payload is a summary dict:
def _on_batch_finished(self, summary) -> None:
    ok = summary.get("ok", 0); total = summary.get("total", 0)
    failed = summary.get("failed", [])
    if failed:
        self.status_bar_left.setText(
            f"Cleaned {ok}/{total} pages \u2014 {len(failed)} failed, see log")
    else:
        self.status_bar_left.setText(f"Cleaned {ok}/{total} pages")
    self._refresh_action_states()
```

#### 4d. File menu wiring for the three batch actions + Export Page (Ctrl+E) + Cancel

**Analog:** `_build_file_menu` (lines 157-184) — shows the QAction→setShortcut→triggered.connect→file_menu.addAction pattern. Export Page uses `QFileDialog.getSaveFileName` (sibling of `open_image`'s `getOpenFileName` at lines 508-513, VERIFIED for the dialog family).

```python
# QAction + shortcut pattern (from _build_file_menu lines 159-166):
self.action_export_page = QAction("Export Page\u2026", self)
self.action_export_page.setShortcut(QKeySequence("Ctrl+E"))
self.action_export_page.triggered.connect(self.export_page)
# Batch actions follow the same pattern; add a Batch submenu or a File-menu section.
```

**Export Page handler** (RESEARCH.md §Code Examples → "Export Page action" — Claude's Discretion):
```python
# Analog dialog: open_image (main_window.py:501-516) uses getOpenFileName.
# Pitfall 5: write canvas.get_image_numpy() — do NOT re-clean.
def export_page(self) -> None:
    if self._op_running:
        return
    current = self.file_table.current_path()
    if current is None:
        return
    image_rgb = self.canvas.get_image_numpy()   # the DISPLAYED image (not a re-clean)
    if image_rgb is None:
        return
    suffix = current.suffix.lower()
    filt = "PNG (*.png)" if suffix == ".png" else "JPEG (*.jpg *.jpeg)"
    path, _ = QFileDialog.getSaveFileName(self, "Export Page", current.name, filt)
    if not path:
        return
    from manga_ai_studio.core.image_io import save_image_optimized
    save_image_optimized(image_rgb, Path(path), original=current)
```

**Cancel control (Open Question Q1):** A `Tools → Cancel Batch` action (disabled unless `_op_running` for a batch) + Esc `QShortcut` is the safest read of D-10's "no new widgets". Emit `self._batch_abort_signal` → `Worker.abort()` sets the flag → next page boundary raises `Abort`. `self._batch_abort_signal = Signal()` must be a `Signal` on a `QObject`; reuse the `QShortcut(self, QKeySequence("Esc"))` pattern from `_wire_history_actions`/`_wire_tool_actions` (lines 686-765).

---

### `manga_ai_studio/core/batch_runner.py` (service, batch/event-driven — NEW)

**Analogs (two):**
1. `manga_ai_studio/gui/main_window.py:_run_detection_task` (lines 998-1050) + `_run_inpaint_task` (1300-1327) — the per-page task shape (the loop body).
2. `manga_ai_studio/gui/worker_thread.py:Worker` (full file) — the `Worker(QRunnable)` + `SharableFlag` + `Abort` + auto-injected `progress_callback`/`abort_flag` machinery.

**Recommended module shape:** three thin functions (`batch_detect`, `batch_clean`, `batch_detect_and_clean`) each returning a `Worker` built by `MainWindow` (or a single `_run_batch_task` task fn called by a `build_batch_worker` factory). D-05 is explicit: "One pipeline, three entry points — no standalone decoupled batch class." **Reject** PanelCleaner's `multiprocessing.Pool` (processing.py:4 import) per D-09b.

#### The per-page task shape (detect) — copy from `_run_detection_task`

```python
# Source: main_window.py:998-1050 (_run_detection_task, VERIFIED) — loop body is this
# MINUS the model.load (load ONCE before the loop, per Pitfall 3):
import cv2, numpy as np
def _detect_one_page(image_path, model):
    # Non-ASCII-safe read (Phase 1 CR-17 pattern — main_window.py:1027-1030):
    image = cv2.imdecode(
        np.fromfile(str(image_path), dtype=np.uint8), cv2.IMREAD_COLOR
    )
    if image is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")
    mask_refined, _blk_list = model.detect(image)   # adapter: (mask, blocks)
    return mask_refined                               # (H, W) uint8 heatmap
```

#### The per-page task shape (inpaint) — copy from `_run_inpaint_task`

```python
# Source: main_window.py:1300-1327 (_run_inpaint_task, VERIFIED):
def _inpaint_one_page(image_rgb, mask_binary, model):
    result_rgb = model.inpaint(image_rgb, mask_binary)  # (H,W,3) uint8 RGB
    return result_rgb
# Adapter contract: image_rgb (H,W,3) uint8 RGB; mask_binary (H,W) uint8 0/255.
# size-reclamp crop is INSIDE TorchLamaModel.inpaint (torch_impl.py:251-253).
```

#### The loop + abort + per-page try/except (RESEARCH Pattern 2, the core of D-04/D-09)

```python
# Shape adapted from main_window.py task fns + worker_thread.py Worker contract.
# progress_callback / abort_flag are auto-injected by Worker (worker_thread.py:134-139).
from manga_ai_studio.gui.worker_thread import Abort
from manga_ai_studio.core.image_io import save_image_optimized, passthrough_original
from manga_ai_studio.core.mask_editor import mask_to_numpy_binary

def _run_batch_task(pages, mode, det_model, inp_model, det_loaded, inp_loaded,
                   cleaned_dir, progress_callback=None, abort_flag=None):
    failed = []
    total = len(pages)
    for i, page in enumerate(pages):
        # D-09: check BETWEEN pages only — never mid-page (Pitfall 4).
        if abort_flag is not None and abort_flag.get():
            raise Abort()   # worker_thread.py:155 catches -> signals.aborted
        progress_callback.emit((int(i / total * 100), page.path.name))
        try:
            if mode in ("detect", "detect_and_clean"):
                mask = _detect_one_page(page.path, det_model)
                page.mask = <qimage from mask>           # persist (D-11)
            if mode in ("clean", "detect_and_clean"):
                # D-03 gate: skip LaMa if mask empty -> copy original through.
                if not _mask_has_content(page):
                    passthrough_original(page.path, cleaned_dir)
                    continue
                image_rgb = _read_rgb(page.path)
                mask_binary = mask_to_numpy_binary(page.mask)
                result = _inpaint_one_page(image_rgb, mask_binary, inp_model)
                save_image_optimized(result, cleaned_dir / page.path.name,
                                     original=page.path)
        except Exception as exc:   # D-04: per-page failure non-fatal
            logger.error(f"Batch: page {page.path.name} failed: {exc}")
            failed.append((page.path, str(exc)))
            continue
    return {"ok": total - len(failed), "failed": failed, "total": total}
```

**Pitfall 3 (load ONCE before loop):** `det_model.load(...)` / `inp_model.load(...)` happen ONCE in the task fn prologue (or in the dispatch handler before `Worker` start), NOT inside the loop. Source: `_run_inpaint_task` loads at line 1318 (once per worker); batch must load once per *batch*. `_resolve_detection_model_path` (main_window.py:1052-1106) and `_resolve_inpainting_model_path` (1198-1252) short-circuit on cache presence (CR-10/CR-11) — reuse them to avoid 30× re-download.

**D-03 mask-content check:** reuse `canvas.has_mask_content()` shape (canvas.py:348-365) on the persisted QImage via `mask_to_numpy_binary(page.mask).any()` (RESEARCH §Code Examples). Do NOT reimplement the alpha scan.

**Thread-safety (T-01-07):** the task fn touches only numpy/Python + the adapters + `ImageFile.mask` (a plain dataclass attribute assignment, no Qt call). All Qt mutation stays in the main-thread signal handlers. **WARNING (Open Question Q2):** if page navigation is enabled during a batch, `on_page_selected` writes `ImageFile.mask` on the GUI thread while the batch worker writes `ImageFile.mask` for the page it just detected — a write/write race. Planner should disable page-switch while a batch runs (set `file_table` non-interactive while `_op_running` for a batch).

---

### `manga_ai_studio/core/image_io.py` (utility, file-I/O/transform — NEW)

**Analog:** `../PanelCleaner/pcleaner/image_export.py:save_optimized` (lines 32-80, VERIFIED in-repo, GPL v3). This is a **near-verbatim adaptation** per D-12 — the only changes are (a) input is a numpy RGB array (not a `Path | Image.Image`), (b) drop the `psd_tools`/`tiff`/`compression_method` branches Phase 2 doesn't need, (c) add `path.parent.mkdir(parents=True, exist_ok=True)`.

#### The adapted `save_image_optimized`

```python
# Adapted from ../PanelCleaner/pcleaner/image_export.py:32-80 (VERIFIED, GPL v3).
# Source suffix_to_format map (image_export.py:18-29) + the kwargs match (lines 65-80).
_SUFFIX_TO_FORMAT = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG",
                     ".webp": "WEBP", ".bmp": "BMP"}

def save_image_optimized(image_rgb: np.ndarray, path: Path,
                         original: Path | None = None) -> None:
    pil = Image.fromarray(image_rgb, mode="RGB")
    mode = dpi = None
    if original is not None and _SUFFIX_TO_FORMAT.get(original.suffix.lower()):
        try:
            with Image.open(original) as orig:
                if _SUFFIX_TO_FORMAT[original.suffix.lower()] == orig.format:
                    mode = orig.mode
                    dpi = orig.info.get("dpi")
        except (OSError, ValueError):
            pass
    if mode is not None:
        pil = pil.convert(mode)
    kwargs = {"optimize": True}              # image_export.py:65
    suf = path.suffix.lower()
    if suf == ".png":
        kwargs["compress_level"] = 9         # image_export.py:69
    elif suf in (".jpg", ".jpeg"):
        kwargs["quality"] = 95               # image_export.py:71
        kwargs["progressive"] = True         # image_export.py:72
    if dpi is not None:
        kwargs["dpi"] = dpi                  # image_export.py:78
    path.parent.mkdir(parents=True, exist_ok=True)
    pil.save(path, **kwargs)
```

**Imports pattern:**
```python
# Pure stdlib + numpy + PIL — NO Qt (thread-safe, unit-testable without a GUI).
from __future__ import annotations
from pathlib import Path
import shutil
import numpy as np
from PIL import Image
```

#### The D-03 empty-mask passthrough (`shutil.copy2`)

```python
# Source: python stdlib shutil.copy2 (RESEARCH.md §Don't Hand-Roll + §Code Examples).
# copy2 preserves bytes AND metadata (mtime, Windows ACLs) exactly — do NOT re-encode.
def passthrough_original(original: Path, cleaned_dir: Path) -> Path:
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    dest = cleaned_dir / original.name
    shutil.copy2(original, dest)
    return dest
```

**File header note (GPL v3 compliance, CLAUDE.md §Licensing):** the module header MUST note this is adapted from PanelCleaner `image_export.py` under GPL v3, mirroring the attribution style in `worker_thread.py:1-12` and `torch_impl.py:40-42` ("vendored PanelCleaner model code (D-12, GPL v3)").

**Path-safety guard (Security §V12):** the batch output dir is DERIVED (`source.parent / "cleaned"`, D-06/D-07) — never user-supplied — which removes the traversal vector. RESEARCH §Security recommends an assert `output_dir.name == "cleaned"` as defense-in-depth so the writer never writes to `source.parent` directly.

---

### `tests/test_core/test_image_io.py` (test, unit — NEW)

**Analog:** `tests/test_inpainting/test_lama_adapter.py` (the Phase 1 unit-test template). Copy its structure: module docstring, `from __future__ import annotations`, `pytest.mark.unit` decorators, small numpy/PIL fixtures, `tmp_path` for isolation.

**Pattern (from test_lama_adapter.py:49-58, the `_rgb_4x4`/`_mask_4x4` fixture style):**
```python
from __future__ import annotations
from pathlib import Path
import numpy as np
import pytest
from PIL import Image

def _rgb_4x4() -> np.ndarray:
    return np.full((4, 4, 3), 200, dtype=np.uint8)

@pytest.mark.unit
def test_save_png_kwargs(tmp_path: Path) -> None:
    out = tmp_path / "out.png"
    save_image_optimized(_rgb_4x4(), out)
    with Image.open(out) as im:
        assert im.format == "PNG"
        # Re-open and assert compress_level=9 was applied (PIL exposes info).
```

**Tests to write (from RESEARCH.md §Validation Architecture → Phase Requirements → Test Map):**
- `test_save_png_kwargs` (compress_level=9, optimize)
- `test_save_jpg_kwargs` (quality=95, progressive)
- `test_preserves_dpi_mode` (open an original with a known DPI/mode, re-save, assert preserved)
- `test_passthrough_copy2` (D-03: bytes + mtime identical — `shutil.cmp` + `os.stat` mtime check)
- `test_rejects_non_rgb_input` (ValueError on wrong ndim/dtype — mirror `canvas.set_image_from_numpy` validation at canvas.py:531-534)

**pytest config (pytest.ini, VERIFIED):** markers `unit`/`gui`; `qt_api = pyside6`. `test_core/` runs headless (`pytest tests/test_core/ -x`) — image_io tests need NO Qt.

---

### `tests/test_core/test_batch_runner.py` (test, unit/integration — NEW)

**Analogs (two):**
1. `tests/test_inpainting/test_lama_adapter.py:FakeSimpleLama` (lines 29-46) — the fake-adapter that records calls and returns a canned result, no torch/weights.
2. `tests/test_inpainting/test_inpaint_gui.py:_FakeInpaintModel` (lines 86-115) — a fake adapter that ALSO records the numpy inputs, mirroring the real `inpaint(image_rgb, mask_binary)` contract.

**Fake-adapter pattern to extend (RESEARCH.md §Wave 0 Gaps):**
```python
# Extend the FakeSimpleLama shape (test_lama_adapter.py:29-46) to BOTH adapters:
class FakeDetectionModel:
    def __init__(self): self.calls = []
    def load(self, model_path, device="cpu"): self.loaded = model_path
    def detect(self, image):              # mirrors TorchCTDModel.detect contract
        self.calls.append(image)
        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        mask[1:3, 1:3] = 255              # a small detected region
        return mask, []                   # (mask_refined, blk_list) 3-tuple unpack

class FakeInpaintModel:                   # mirrors _FakeInpaintModel (test_inpaint_gui.py:86)
    def __init__(self, fill=7): self.fill = fill; self.calls = []
    def load(self, model_path): self.loaded = model_path
    def inpaint(self, image_rgb, mask_binary):
        self.calls.append((image_rgb, mask_binary))
        return np.full(image_rgb.shape, self.fill, dtype=np.uint8)
```

**Place shared fakes in** `tests/test_core/conftest.py` (new) per RESEARCH.md §Wave 0 Gaps, mirroring `tests/conftest.py`'s fixture style.

**Tests to write (RESEARCH.md §Test Map — FLOW-03):**
- `test_batch_clean_skips_empty_mask` (D-03: empty mask → `shutil.copy2` passthrough, no inpaint call)
- `test_batch_detect_and_clean` (one-shot writes `cleaned/` for all pages)
- `test_per_page_failure_continues` (D-04: one page raises, batch continues, summary lists it)
- `test_abort_between_pages` (D-09: set abort_flag mid-loop, assert `Abort` raised, pages already written stay written)
- `test_output_to_cleaned_subdir` (D-07: outputs land in `source.parent / "cleaned"`)
- `test_progress_per_page` (D-10: progress_callback emits `(percent, page.name)` per page)
- `test_model_loaded_once` (Pitfall 3: assert `FakeDetectionModel.load` called exactly once for a 3-page batch)

---

### `tests/test_gui_batch.py` (test, GUI/pytest-qt — NEW)

**Analog:** `tests/test_inpainting/test_inpaint_gui.py` (the Phase 1 GUI test template). Copy its helpers VERBATIM (they are public test infra, RESEARCH.md §Wave 0 Gaps):

**Helpers to reuse (test_inpaint_gui.py:43-83, VERIFIED):**
```python
def _make_window(qtbot, tmp_path):              # lines 43-48
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    return window

def _open_page(window, tmp_path, size=16):       # lines 57-64 — writes a PNG + opens it
    img_path = tmp_path / "page.png"
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(QColor(255, 255, 255))
    img.save(str(img_path))
    window._open_single_image(img_path)
    return img_path

def _paint_mask_on_canvas(canvas):               # lines 67-83 — paints a 4x4 mask region
    mask = QImage(canvas.image_item.pixmap().size(), QImage.Format.Format_Grayscale8)
    mask.fill(0)
    painter = QPainter(mask)
    painter.setPen(QColor(255, 255, 255))
    for x in range(4, 8):
        for y in range(4, 8):
            painter.drawPoint(x, y)
    painter.end()
    canvas.set_mask(mask)
```

**Fake adapter to reuse:** `_FakeInpaintModel` (test_inpaint_gui.py:86-115) — inject via `monkeypatch` on `backend_factory` or by constructing the window then replacing its resolved model.

**Module header pattern (test_inpaint_gui.py:17-35, VERIFIED):**
```python
from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock
import numpy as np
import pytest

pytest.importorskip("PySide6")                    # lines 25 — graceful skip on Qt-less CI

from PySide6.QtCore import QThreadPool             # noqa: E402
from PySide6.QtGui import QColor, QImage, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication         # noqa: E402
from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow             # noqa: E402
```

**Tests to write (RESEARCH.md §Test Map — PROJ-02 + FLOW-03 GUI):**
- `test_export_writes_displayed_image` (Pitfall 5: Export writes `canvas.get_image_numpy()`, NOT a re-clean — assert the fake inpaint model was NOT called)
- `test_batch_detect_persists_masks` (D-11: after Batch Detect, `ImageFile.mask` is non-None on each page)
- `test_mask_survives_navigation` (D-11 crux: detect on page 1, navigate to page 2 and back, assert page 1's `ImageFile.mask` survives + `canvas.has_mask()` is True after restore)
- `test_mask_persistence_uses_copy` (Pitfall 2 regression: mutate the canvas mask after persistence, assert `ImageFile.mask` is unaffected — the `test_inpaint_result_display_uses_copy` template from test_inpaint_gui.py)
- `test_batch_sets_op_running` (D-08: during a batch, detect/inpaint/batch actions are disabled)
- `test_op_running_cleared_after_batch` (Pitfall 7: after batch finish/abort/error, `_op_running` is False)

---

## Shared Patterns

These cross-cut the new/modified files; the planner should apply them to every relevant plan's action section.

### Shared Pattern 1 — numpy↔QImage buffer discipline (`.copy()` at every boundary) [Pitfall 2, CRITICAL]

**Source:** `manga_ai_studio/core/mask_editor.py:162-207` (`mask_to_numpy_binary` line 187 + `numpy_binary_to_mask_qimage` line 207) and `manga_ai_studio/gui/canvas.py:289-336` (`set_mask` line 305), `468-507` (`get_image_numpy` line 507), `509-570` (`set_image_from_numpy` line 563).

**Apply to:** `image_file.py` (D-11 mask persistence seam), `main_window.py` (on_page_selected save/restore, batch result handling), `image_io.py` (the numpy→PIL bridge — numpy already owns its buffer by contract, no QImage involved).

```python
# The two canonical helpers (mask_editor.py) — REUSE, do NOT reimplement:
def mask_to_numpy_binary(mask: QImage) -> np.ndarray:        # line 162
    ... return binary.copy().astype(np.uint8)                # line 187 — trailing .copy()

def numpy_binary_to_mask_qimage(arr: np.ndarray) -> QImage:  # line 190
    ... return qimg.copy()                                    # line 207 — trailing .copy()

# At every boundary in Phase 2:
self.image_files[idx].mask = self.canvas.get_mask().copy()    # outgoing save
self.canvas.set_mask(self.image_files[idx].mask.copy())       # incoming restore
```

### Shared Pattern 2 — Worker dispatch (build → connect 4 signals → `_op_running` → QThreadPool) [T-01-07]

**Source:** `manga_ai_studio/gui/main_window.py:detect_text` (955-996) and `inpaint` (1252-1298). `manga_ai_studio/gui/worker_thread.py:Worker` (86-174) — constructor auto-injects `progress_callback` and (if `abort_signal` provided) `abort_flag`.

**Apply to:** `main_window.py` batch action handlers (all three batch actions are the same shape with different task fns/mode strings).

```python
worker = Worker(self._run_batch_task, pages, mode, det_model, inp_model,
                abort_signal=self._batch_abort_signal)   # D-09 cancel
worker.signals.progress.connect(self._on_batch_progress)
worker.signals.result.connect(self._on_batch_finished)
worker.signals.error.connect(self._on_batch_error)
worker.signals.aborted.connect(self._on_batch_cleanup)   # cancel path
worker.signals.finished.connect(self._on_batch_cleanup)  # ALWAYS — Pitfall 7
worker.setAutoDelete(True)
self._op_running = True; self._refresh_action_states()
QThreadPool.globalInstance().start(worker)
```

### Shared Pattern 3 — Non-ASCII-safe image read (`cv2.imdecode(np.fromfile(...))`) [CR-17]

**Source:** `manga_ai_studio/gui/main_window.py:_run_detection_task` lines 1027-1030 (VERIFIED, with the CR-17 comment block 1020-1026).

**Apply to:** `batch_runner.py` (every page read in the loop).

```python
image = cv2.imdecode(
    np.fromfile(str(image_path), dtype=np.uint8), cv2.IMREAD_COLOR
)   # NOT cv2.imread — fails on non-ASCII Windows paths + some codecs (webp)
if image is None:
    raise FileNotFoundError(f"Could not read image: {image_path}")
```

### Shared Pattern 4 — Per-page failure isolation (D-04 non-fatal) + Abort-between-pages (D-09)

**Source:** `../PanelCleaner/pcleaner/gui/processing.py:check_abortion` (lines 80-94) for the SHAPE (abort-flag poll → emit aborted → raise `wt.Abort()`); `worker_thread.py:Abort` (80-83) + `Worker.run` (142-169, the `except Abort → signals.aborted` branch at 155-156) for the mechanism.

**Apply to:** `batch_runner.py` loop. **REJECT** processing.py's `multiprocessing.Pool` (line 4 import) per D-09b — adopt only the abort-between-units + per-unit-progress + summary-return patterns.

```python
# Loop-top abort check (D-09: between pages only — Pitfall 4):
if abort_flag is not None and abort_flag.get():
    raise Abort()   # worker_thread.py:155 converts to signals.aborted
# Per-page try/except (D-04: failure non-fatal):
try:
    ...detect/inpaint/save for this page...
except Exception as exc:
    logger.error(f"Batch: page {page.path.name} failed: {exc}")
    failed.append((page.path, str(exc)))
    continue
```

### Shared Pattern 5 — Error/logging contract (tracebacks to loguru, friendly copy to UI) [T-01-08]

**Source:** `manga_ai_studio/gui/main_window.py:_on_detection_error` (1138-1153) and `_on_inpaint_error` (1413-1428). `logger` imported at main_window.py:34 (`from loguru import logger`).

**Apply to:** `main_window.py` batch error handler; `batch_runner.py` per-page failure logging.

```python
logger.error(f"Batch failed: {worker_error}")        # full traceback to loguru
self._show_error_chip("Batch error")                 # friendly chip copy
# QMessageBox shows only user-friendly text (UI-SPEC §Copywriting) — never the traceback.
```

### Shared Pattern 6 — Fake-adapter test pattern (record calls, return canned numpy, no torch)

**Source:** `tests/test_inpainting/test_lama_adapter.py:FakeSimpleLama` (29-46) + `tests/test_inpainting/test_inpaint_gui.py:_FakeInpaintModel` (86-115).

**Apply to:** `tests/test_core/conftest.py` (NEW shared fakes) → consumed by `test_batch_runner.py` and `test_gui_batch.py`. The fakes mirror the real adapter contracts: `TorchCTDModel.detect → (mask_refined, blk_list)` (torch_impl.py:104-129) and `TorchLamaModel.inpaint(image_rgb, mask_binary) → result_rgb` (torch_impl.py:225-254).

---

## No Analog Found

**None.** Every Phase 2 file has a concrete exact-match analog:

| File | Analog verdict |
|------|----------------|
| `core/image_file.py` | exact — the `mask` slot already exists; semantics change only |
| `gui/main_window.py` | exact — `detect_text`/`inpaint`/`on_page_selected` are the templates |
| `core/batch_runner.py` | exact — `_run_detection_task`/`_run_inpaint_task` + `Worker` |
| `core/image_io.py` | exact — PanelCleaner `save_optimized` (GPL v3, in-repo) |
| `tests/test_core/test_image_io.py` | exact — `test_lama_adapter.py` unit template |
| `tests/test_core/test_batch_runner.py` | exact — `FakeSimpleLama` + `_FakeInpaintModel` |
| `tests/test_gui_batch.py` | exact — `_make_window`/`_open_page`/`_paint_mask_on_canvas` |

The genuinely novel code is small (a page-loop task fn body, an `ImageFile.mask` save/restore seam, a ~30-line output writer). Everything else is wiring. (02-RESEARCH.md §Don't Hand-Roll → "Key insight.")

---

## Metadata

**Analog search scope:**
- `manga_ai_studio/` (full tree, 17 .py files read/indexed)
- `tests/` (full tree, 13 .py files; deep-read `test_inpainting/test_lama_adapter.py`, `test_inpainting/test_inpaint_gui.py`, `conftest.py`)
- `../PanelCleaner/pcleaner/image_export.py` (read lines 1-90, the `save_optimized` + `suffix_to_format`)
- `../PanelCleaner/pcleaner/gui/processing.py` (read lines 1-120, the `generate_output` orchestration shape + `check_abortion`)
- `.planning/phases/02-cleaning-output-batch/02-CONTEXT.md`, `02-RESEARCH.md` (upstream inputs, read in full)
- `.claude/CLAUDE.md` (project constraints — Tech stack, Platform, Licensing)

**Files scanned:** 23 source/test files + 2 PanelCleaner references + 2 upstream phase docs.

**Files read in full (single pass, no re-reads):** `worker_thread.py`, `image_file.py`, `mask_editor.py`, `factory.py`, `canvas.py` (978 lines), `torch_impl.py` (281 lines), `test_lama_adapter.py` (309 lines), `conftest.py`, `main_window.py` (targeted non-overlapping ranges: 1-160, 157-286, 393-612, 945-1224, 1252-1476), `test_inpaint_gui.py` (1-130, the helpers section), `image_export.py` (1-90), `processing.py` (1-120).

**Pattern extraction date:** 2026-07-23.

**Key load-bearing facts the planner must respect:**
1. **D-11 seam ordering** — OUTGOING mask must be captured BEFORE `reset_history`/path-switch; INCOMING mask restored AFTER `set_image_from_path`. `_current_page_index()` semantics around `file_table.select_path` need verification (file 4a note).
2. **Pitfall 3 (load ONCE)** — models load before the page loop, never inside it. Reuse `_resolve_detection_model_path`/`_resolve_inpainting_model_path` (CR-10/CR-11 cache short-circuits).
3. **Pitfall 4 (abort between pages only)** — the `abort_flag.get()` check is at the loop TOP, never mid-page, so no half-written output.
4. **D-09b (reject multiprocessing.Pool)** — adopt processing.py's *shape* (`check_abortion`, `progress_callback`, summary return); reject its *mechanism* (Pool).
5. **GPL v3 header** — `image_io.py` must carry the PanelCleaner attribution (CLAUDE.md §Licensing; mirror `worker_thread.py:1-12`).
6. **D-06/D-07 path safety** — batch output dir is derived (`source.parent / "cleaned"`), never user-supplied; the Export path is the only user-supplied path and goes through `QFileDialog.getSaveFileName` (OS-validated, T-01-01 sibling).
