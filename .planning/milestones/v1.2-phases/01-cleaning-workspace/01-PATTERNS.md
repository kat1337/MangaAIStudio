# Phase 1: Cleaning Workspace - Pattern Map

**Mapped:** 2026-07-12
**Files analyzed:** 22 (new) + 0 (modified — greenfield repo)
**Analogs found:** 22 / 22 (every Phase 1 file has an analog; no "no analog" cases)
**Repo state:** Greenfield — only `.planning/`, `.git/`, `.claude/` exist. All analogs live OUTSIDE the repo under two distinct licensing regimes (see D-12).

## Analog Source Regimes (D-12 compliance)

Every analog below belongs to one of two regimes. The planner MUST respect this in every task action.

| Regime | Source root | License | Permitted use |
|--------|-------------|---------|---------------|
| **V (Vendored / GPL-compat)** | `C:\Src\PanelCleaner\pcleaner\` | GPL v3 (compatible with our GPL v3) | Copy near-verbatim into `panelcleaner/`. Adjust imports only. |
| **R (Reference-only / reimplementation)** | `C:\Users\Stella\Downloads\MangaCleaner_GPU\_internal\src\` | All-rights-reserved (no LICENSE in the binary distribution) | READ for patterns, REIMPLEMENT in our own words. NEVER copy source. Our `gui/canvas.py`, `gui/worker_thread.py`, `core/history_manager.py`, `adapters/onnx_impl.py` fall here. |

**Heuristic for the planner:** if an analog path starts with `C:\Src\PanelCleaner\`, the task may say "vendor/adapt". If it starts with `C:\Users\Stella\Downloads\MangaCleaner_GPU\`, the task may say "reimplement, patterned after" — never "copy".

## Critical Correction to Downstream Inputs (read before planning)

CONTEXT.md §Canonical References and RESEARCH.md §Code Examples both assert that PanelCleaner's `TextDetector.__call__` returns a **5-tuple** `(img, mask, mask_refined, blk_list, refine_mode)`. **This is incorrect.** Verified against source:

`C:\Src\PanelCleaner\pcleaner\comic_text_detector\inference.py` line 166 (signature) and line 210 (return):
```python
@torch.no_grad()
def __call__(self, img, refine_mode=REFINEMASK_INPAINT, keep_undetected_mask=False):
    ...
    return mask, mask_refined, blk_list   # 3-tuple: (mask, mask_refined, blk_list)
```

The `refine_mode` is an **input argument** (takes `REFINEMASK_INPAINT` / `REFINEMASK_ANNOTATION` constants from `comic_text_detector/utils/textmask.py`), not a return value. The planner MUST contract `adapters/torch_impl.py` `TorchCTDModel.detect()` against the **3-tuple**, and any test fixtures against 3 unpacking targets. RESEARCH.md's Code Example block at line ~722 and the inline comments at lines 320-329 unpack 5 values — those will raise `ValueError: too many values to unpack` if followed verbatim.

A second inaccuracy in CONTEXT.md/RESEARCH.md: both describe `Profile.save(path)` as the INI persistence entrypoint. Source shows the public write path is `Profile.safe_write(path)` → `Profile.unsafe_write(path)` (config.py:974, 998), which calls `self.bundle_config().write(file)`. `Profile.save` is not a method on `Profile`; the classmethod is `Profile.load(path)` (config.py:1015). The wrapper in `config/profile_manager.py` should call `profile.safe_write(path)` to write and `Profile.load(path)` to read.

## File Classification

| New File | Role | Data Flow | Closest Analog | Match | Regime |
|----------|------|-----------|----------------|-------|--------|
| `adapters/base.py` | provider (ABC) | request-response | PanelCleaner `inpainting.py:InpaintingModel` + RESEARCH Pattern 1 | role-match | V (shape) + design |
| `adapters/torch_impl.py` | provider | request-response | PanelCleaner `comic_text_detector/inference.py:TextDetector` + `inpainting.py:InpaintingModel` | exact | V |
| `adapters/onnx_impl.py` | provider (stub) | request-response | MangaCleaner_GPU `backend/onnx_engine.py:ONNXEngine` | role-match | R (reference only; Phase 1 = stub) |
| `panelcleaner/config.py` | config | file-I/O | PanelCleaner `config.py` (vendored) | exact (verbatim) | V |
| `panelcleaner/comic_text_detector/inference.py` | model | request-response | PanelCleaner `comic_text_detector/inference.py` (vendored) | exact (verbatim) | V |
| `panelcleaner/comic_text_detector/*` (basemodel, utils) | model support | request-response | PanelCleaner `comic_text_detector/` (vendored) | exact (verbatim) | V |
| `panelcleaner/inpainting.py` | service | request-response | PanelCleaner `inpainting.py` (vendored) | exact (verbatim) | V |
| `panelcleaner/masker.py` | service | batch / transform | PanelCleaner `masker.py` (vendored) | exact (verbatim) | V |
| `panelcleaner/image_ops.py` | utility | transform | PanelCleaner `image_ops.py` (vendored) | exact (verbatim) | V |
| `panelcleaner/structures.py` | model | file-I/O (JSON round-trip) | PanelCleaner `structures.py` (vendored) | exact (verbatim) | V |
| `panelcleaner/model_downloader.py` | utility | file-I/O / streaming | PanelCleaner `model_downloader.py` (vendored) | exact (verbatim) | V |
| `config/profile_manager.py` | service | file-I/O | PanelCleaner `config.py:Profile` + `Config` (wrapper) | exact (wraps vendored) | V |
| `gui/main_window.py` | controller | event-driven | PanelCleaner `gui/mainwindow_driver.py:MainWindow` (layout/theme) + MangaCleaner_GPU `frontend/main_window.py:MainWindow` (tool dispatch, shortcuts, worker wiring) | composite | V + R |
| `gui/canvas.py` | component | event-driven | MangaCleaner_GPU `frontend/canvas.py:MangaCanvas` + PanelCleaner `gui/image_viewer.py:ImageViewer` (pan/zoom mechanics) | composite | R (primary) + V (mechanics) |
| `gui/file_table.py` | component | event-driven | MangaCleaner_GPU `frontend/widgets.py:FileListWidget` (QListView pattern) + PanelCleaner `gui/file_table.py:FileTable` (thumbnail/icon-size reference) | composite | R + V |
| `gui/tools_panel.py` | component | event-driven | MangaCleaner_GPU `frontend/widgets.py:ToolGroup` + `BrushSlider` | role-match | R |
| `gui/worker_thread.py` | provider | event-driven (async) | PanelCleaner `gui/worker_thread.py:Worker`/`WorkerSignals` (preferred — proven, abortable, GPL) | exact | V |
| `core/image_file.py` | model | CRUD | PanelCleaner `gui/image_file.py:ImageFile` (path/thumb/state) | role-match | V |
| `core/mask_editor.py` | service | transform | MangaCleaner_GPU `frontend/canvas.py` paint helpers (`get_painter`, `paint_mask_stroke/rect/lasso`) + PanelCleaner `image_ops.py` mask conversions | composite | R + V |
| `core/history_manager.py` | service | event-driven (undo/redo) | MangaCleaner_GPU `utils/history.py:HistoryManager` (pattern) — reimplemented with 2 stacks per UI-SPEC surface 8 | role-match | R |
| `pyproject.toml` | config | n/a | (new — no analog; uv/pip standard) | none | — |
| `tests/conftest.py` + `tests/test_*` | test | n/a | (new — pytest standard; RESEARCH §Validation Architecture) | none | — |

---

## Pattern Assignments

### `adapters/base.py` (provider, request-response)

**Analogs:** PanelCleaner `inpainting.py` (concrete shape to abstract), RESEARCH.md Pattern 1 (already drafted).

**Imports pattern** — from PanelCleaner `inpainting.py:1-13`:
```python
import os
from collections import namedtuple
from pathlib import Path
from PIL import Image
from loguru import logger
from simple_lama_inpainting import SimpleLama
import pcleaner.config as cfg
```
Note the project convention: stdlib → third-party → `pcleaner.*` (alphabetical, one group each). Mirror this in `adapters/base.py` (replacing `pcleaner` with `panelcleaner` per D-10).

**Core pattern** — abstract base classes with full pipeline hooks per D-01. Use the shape already drafted in RESEARCH.md Pattern 1 (lines 237-296) — `DetectionModel`, `InpaintModel` (add `OCRModel` per D-01) each with `load()`, `detect()/recognize()/inpaint()`, `preprocess()`, `postprocess()`, `configure()`, `get_info()`. Use `abc.ABC` + `@abstractmethod`.

**Concrete-shape reference** — PanelCleaner `inpainting.py:16-40` (`InpaintingModel`):
```python
class InpaintingModel:
    def __init__(self, config: cfg.Config) -> None:
        self.model_path = md.get_inpainting_model_path(config)
        if not self.model_path.is_file():
            raise FileNotFoundError(f"Model not found: {self.model_path}")
        os.environ["LAMA_MODEL"] = str(self.model_path)
        self.simple_lama = SimpleLama()

    def __call__(self, image: Image, mask: Image) -> Image:
        inpainted_image = self.simple_lama(image, mask)
        if inpainted_image.size != image.size:
            width, height = image.size
            inpainted_image = inpainted_image.crop((0, 0, width, height))
        return inpainted_image
```
The `__init__` takes a `cfg.Config`, validates the model path exists, and exposes a single `__call__`. The adapter base classes should mirror this: `load()` validates and stores; the inference method does the work.

---

### `adapters/torch_impl.py` (provider, request-response)

**Analogs:** PanelCleaner `comic_text_detector/inference.py:TextDetector` (detection) + `inpainting.py:InpaintingModel` (inpainting).

**Detection — class instantiation pattern** from `inference.py:130-163`:
```python
class TextDetector:
    lang_list = ["eng", "ja", "unknown"]
    langcls2idx = {"eng": 0, "ja": 1, "unknown": 2}

    def __init__(self, model_path, input_size=1024, device="cpu", half=False,
                 nms_thresh=0.35, conf_thresh=0.4, mask_thresh=0.3, act="leaky"):
        super(TextDetector, self).__init__()
        cuda = device == "cuda"
        if Path(model_path).suffix == ".onnx":
            self.model = cv2.dnn.readNetFromONNX(model_path)
            self.net = TextDetBaseDNN(input_size, model_path)
            self.backend = "opencv"
        else:
            self.net = TextDetBase(model_path, device=device, act=act)
            self.backend = "torch"
        ...
```
Key points for `TorchCTDModel.load()`: device probe (`torch.cuda.is_available()`), default `input_size=1024`, `act="leaky"`, ONNX-vs-torch branch (relevant when ONNX backend lands later).

**Detection — inference call** from `inference.py:165-210` (CRITICAL — see correction above):
```python
@torch.no_grad()
def __call__(self, img, refine_mode=REFINEMASK_INPAINT, keep_undetected_mask=False):
    img_in, ratio, dw, dh = preprocess_img(img, input_size=self.input_size,
                                           device=self.device, half=self.half,
                                           to_tensor=self.backend == "torch")
    im_h, im_w = img.shape[:2]
    blks, mask, lines_map = self.net(img_in)
    ...
    return mask, mask_refined, blk_list   # <-- 3-tuple, NOT 5
```
`TorchCTDModel.detect()` must unpack 3 values: `mask, mask_refined, blk_list = self.detector(image, refine_mode=REFINEMASK_ANNOTATION, keep_undetected_mask=True)`. Import `REFINEMASK_ANNOTATION` from `panelcleaner.comic_text_detector.utils.textmask` (the vendored location), not from `inference` — `inference.py` imports it from `utils.textmask` (line 20) and re-exports; either import path works after vendoring.

**Inpainting** — directly wrap `InpaintingModel` (above). `TorchLamaModel.inpaint(image, mask)` converts numpy↔PIL and delegates:
```python
# Pattern from PanelCleaner inpainting.py:26-40 + RESEARCH lines 340-358
from PIL import Image
img_pil = Image.fromarray(image)
mask_pil = Image.fromarray((mask > 0).astype(np.uint8) * 255)
result = self.model(img_pil, mask_pil)
return np.array(result)
```

**Error handling:** PanelCleaner raises `FileNotFoundError` on missing model (`inpainting.py:21`). Propagate this from `load()` so the GUI can show the "Couldn't load the {detection | inpainting} model." copy (UI-SPEC §Copywriting).

---

### `adapters/onnx_impl.py` (provider stub, request-response)

**Analog (reference-only, DO NOT copy):** MangaCleaner_GPU `backend/onnx_engine.py:ONNXEngine`.

**Pattern to reimplement** (lines 9-46): provider auto-detection of CUDA vs CPU, sequential execution mode, `enable_mem_pattern = False`. Read for the shape; Phase 1 ships a stub class raising `NotImplementedError` per D-03/D-09 (ONNX is a future optional add-on).

```python
# Reference shape (reimplement, do not copy):
providers = ort.get_available_providers()
sess_opt = ort.SessionOptions()
sess_opt.enable_mem_pattern = False
sess_opt.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
if 'CUDAExecutionProvider' in providers:
    self.session = ort.InferenceSession(model_path, sess_options=sess_opt,
        providers=[('CUDAExecutionProvider', cuda_options), 'CPUExecutionProvider'])
else:
    self.session = ort.InferenceSession(model_path, sess_options=sess_opt,
        providers=['CPUExecutionProvider'])
```

**Phase 1 contract:** class `OnnxDetectionModel` / `OnnxInpaintModel` subclassing the `adapters/base.py` ABCs, with `load()` raising `NotImplementedError("ONNX backend lands in a future phase; use torch_impl.")`. This keeps the adapter interface honest for D-02 (`*_backend: onnx` config keys resolve to a real class) without pulling `onnxruntime` into Phase 1 deps.

---

### `panelcleaner/config.py` (config, file-I/O) — VENDORED

**Analog:** PanelCleaner `config.py` (vendored near-verbatim per D-04/D-12).

**Action:** Copy the file. Adjust only the import root if our package is named `panelcleaner` (it is — D-10), so imports like `from pcleaner.helpers import tr` become `from panelcleaner.helpers import tr`. The internal structure is left intact.

**Key contracts the rest of the codebase depends on** (verified line numbers):
- `Profile` class — `config.py:935-1064`. Fields: `general`, `text_detector`, `preprocessor`, `masker`, `denoiser`, `inpainter` (lines 941-946).
- `Profile.bundle_config(gui_mode=False) -> ConfigUpdater` — `config.py:948-962`. Chains each section's `export_to_conf`.
- `Profile.safe_write(path) -> bool` — `config.py:974-996` (temp-file + atomic move).
- `Profile.unsafe_write(path) -> bool` — `config.py:998-1012` (calls `bundle_config().write(file)`).
- `Profile.load(path) -> Profile` (classmethod) — `config.py:1014-1035`.
- `Config` class — `config.py:1066+`. Holds `current_profile`, `saved_profiles`, `default_*_model_path`, `cache_dir`, etc.
- `Config.from_config_updater(conf_updater) -> Config` (classmethod) — `config.py:1309-1374`.
- `Config.save(config_path=None) -> bool` — `config.py:1217-1307`.
- Per-section round-trip: `GeneralConfig.export_to_conf` (`config.py:132`) / `import_from_conf` (`config.py:227`). Same shape for `TextDetectorConfig`, `PreprocessorConfig`, `MaskerConfig`, `DenoiserConfig`, `InpainterConfig`.

**Imports pattern** — `config.py:1-18`: stdlib → `configupdater as cu` → `attrs` (`from attrs import define, field`) → `loguru` → `pcleaner.*` (→ rename to `panelcleaner.*`).

**Example INI round-trip excerpt** (`config.py:142-225`, `GeneralConfig.export_to_conf`):
```python
def export_to_conf(self, config_updater: cu.ConfigUpdater, gui_mode: bool = False) -> None:
    config_str = f"""\
    [General]
    # About this profile:
    notes = {escape_all(self.notes)}
    preferred_file_type = {self.preferred_file_type if self.preferred_file_type else ""}
    ...
    """
    config_updater.read_string(multi_left_strip(format_for_version(config_str, gui_mode)))
```

---

### `panelcleaner/comic_text_detector/*` (model + support) — VENDORED

**Analog:** PanelCleaner `pcleaner/comic_text_detector/` (vendored near-verbatim).

Files to vendor: `inference.py`, `basemodel.py`, `LICENSE` (GPL v3 — keep the upstream license file in the dir), `utils/` (`textmask.py` for `REFINEMASK_*` constants + `refine_mask`/`refine_undetected_mask`, `textblock.py` for `TextBlock`, `imgproc_utils.py`, `io_utils.py`, `db_utils.py`, `yolov5_utils.py`).

**Key excerpt already captured above** under `adapters/torch_impl.py` — the `TextDetector.__call__` 3-tuple contract is the load-bearing fact for the adapter and tests.

---

### `panelcleaner/inpainting.py`, `panelcleaner/masker.py`, `panelcleaner/image_ops.py`, `panelcleaner/structures.py`, `panelcleaner/model_downloader.py` — VENDORED

**Analogs:** PanelCleaner counterparts, vendored near-verbatim per D-12.

| Our file | Analog | Key pattern the rest of the codebase uses |
|----------|--------|--------------------------------------------|
| `panelcleaner/inpainting.py` | `pcleaner/inpainting.py` | `InpaintingModel(config)` wraps `SimpleLama`; `__call__(image, mask)` (lines 16-40). `inpaint_page(i_data, model)` is the batch entrypoint — not used in Phase 1 GUI flow but kept for parity. |
| `panelcleaner/masker.py` | `pcleaner/masker.py` | `mask_page(m_data) -> Sequence[MaskFittingAnalytic]` (lines 12-120). Box-mask intersection, best-mask ranking, combined-mask save. Used by detection→mask postprocessing. |
| `panelcleaner/image_ops.py` | `pcleaner/image_ops.py` | `convert_mask_to_rgba` (line 57+), `grow_mask`, `cut_out_box`, `mask_intersection`, `combine_best_masks`, `fade_mask_edges`. Pure-PIL image transforms. |
| `panelcleaner/structures.py` | `pcleaner/structures.py` | `PageData.to_json/from_json`, `MaskData`, `Box`, `InpainterData`, `MaskerData`. JSON round-trip for pipeline data (the ONLY JSON in PanelCleaner — settings are INI, pipeline data is JSON; see D-05). |
| `panelcleaner/model_downloader.py` | `pcleaner/model_downloader.py` | `download_file(url, save_dir, sha_hash)` (lines 36-89) with sha256 verification + partial-file cleanup; `download_torch_model`, `download_cv2_model`, `download_inpainting_model`, `get_inpainting_model_path(config)`. URLs and hashes pinned at lines 15-22. |

**Vendor action for each:** copy file, rewrite `pcleaner.` → `panelcleaner.` in imports. Do not refactor logic.

---

### `config/profile_manager.py` (service, file-I/O)

**Analogs:** PanelCleaner `config.py:Profile` + `Config` (wraps the vendored classes). RESEARCH.md Pattern 2 (lines 367-408) already drafts this — but its method names are slightly off; corrected below.

**Corrected wrapper shape** (per source verification above):
```python
from pathlib import Path
from panelcleaner.config import Config, Profile

class ProfileManager:
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.config = Config()  # defaults

    def save_profile(self, profile: Profile, name: str) -> Path:
        profile_path = self.config_dir / f"{name}.profile"
        profile.safe_write(profile_path)   # NOT profile.save() — safe_write is the real API
        return profile_path

    def load_profile(self, name: str) -> Profile:
        profile_path = self.config_dir / f"{name}.profile"
        return Profile.load(profile_path)  # classmethod at config.py:1015

    def profile_to_config(self, profile: Profile) -> Config:
        conf_updater = profile.bundle_config()           # -> ConfigUpdater
        return Config.from_config_updater(conf_updater)  # config.py:1310
```

**Error handling:** `Profile.load` swallows exceptions internally and returns a default `Profile()` on failure (logs + prints "Failed to load profile, using default profile." — config.py:1031-1034). `Profile.safe_write` returns `bool` — propagate `False` to the GUI as a "couldn't save profile" warning.

---

### `gui/main_window.py` (controller, event-driven) — COMPOSITE

**Primary analog (architecture, theme, layout):** PanelCleaner `gui/mainwindow_driver.py:MainWindow`.
**Secondary analog (tool dispatch, shortcuts, worker wiring):** MangaCleaner_GPU `frontend/main_window.py:MainWindow`.

**Theme/style application** — PanelCleaner `mainwindow_driver.py:191-217`:
```python
def set_theme(self, theme: str = None) -> None:
    if theme is None:
        palette = self.default_palette
        Qw.QApplication.setStyle(self.default_style)
    else:
        palette = gu.load_color_palette(theme)
        Qg.QIcon.setThemeName(theme)
        Qw.QApplication.setStyle("Fusion")        # <-- UI-SPEC locks Fusion
    self.setPalette(palette)
    Qw.QApplication.setPalette(self.palette())
    background_color = palette.color(Qg.QPalette.Window)
    self.theme_is_dark.set(background_color.lightness() < 128)
```
Per UI-SPEC, our version drops the theme-menu branch — single dark palette built from the tokens in UI-SPEC §Color, applied once at startup. `QApplication.setStyle("Fusion")` is mandatory (UI-SPEC §Design System).

**Init shape** — PanelCleaner `mainwindow_driver.py:111-165`:
```python
def __init__(self, config: cfg.Config, files_to_open: list[str], debug: bool) -> None:
    Qw.QMainWindow.__init__(self)
    self.setupUi(self)
    self.config = config
    ...
    self.threadpool = Qc.QThreadPool.globalInstance()           # GUI tasks (image load)
    self.thread_queue = Qc.QThreadPool(); self.thread_queue.setMaxThreadCount(1)  # serial processing queue
    self.file_table.set_config(self.config); ...                # share core objects
    self.initialize_ui()
    self.save_default_palette()
    self.load_config_theme()
```
Our `MainWindow.__init__` mirrors this: receives a `ProfileManager`/`Config`, sets up one `QThreadPool` for GUI work, shares state with `FileTable` and `EditorCanvas`. Per D-08 the model work goes to a backend subprocess, not `thread_queue` — but the in-frontend QThreadPool pattern (for image load, thumbnail gen) still applies.

**Tool dispatch + shortcuts** — MangaCleaner_GPU `main_window.py:159-198` (reference pattern, reimplement):
```python
def setup_shortcuts(self):
    QShortcut(QKeySequence("B"), self).activated.connect(lambda: self.set_tool("BRUSH"))
    QShortcut(QKeySequence("R"), self).activated.connect(lambda: self.set_tool("RECT"))
    QShortcut(QKeySequence("L"), self).activated.connect(lambda: self.set_tool("LASSO"))
    QShortcut(QKeySequence("D"), self).activated.connect(self.on_auto_scan)
    QShortcut(QKeySequence("C"), self).activated.connect(self.on_lama_clean)
    QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self.on_undo_image)
    QShortcut(QKeySequence("Ctrl+Shift+Z"), self).activated.connect(self.on_redo_image)
    QShortcut(QKeySequence("Alt+Z"), self).activated.connect(self.on_undo_mask)
    QShortcut(QKeySequence("Alt+Shift+Z"), self).activated.connect(self.on_redo_mask)

def set_tool(self, tool):
    self.canvas.current_tool = tool
    for btn in self.tools.buttons.values(): btn.setChecked(False)
    if tool == "NONE":
        self.canvas.setDragMode(QGraphicsView.ScrollHandDrag)
        ...
```
Use the **exact shortcut table** from UI-SPEC §Keyboard Shortcut Reference (it supersedes MangaCleaner_GPU — e.g., we add `E` for eraser as a first-class tool, `V` for Move, `M` for mask toggle, `P` for preview).

**Worker wiring** — MangaCleaner_GPU `main_window.py:273-298` (reference pattern):
```python
def run_thread(self, task, *args):
    self.setCursor(Qt.WaitCursor)
    self.worker_thread = QThread()
    self.worker = AIWorker()
    self.worker.moveToThread(self.worker_thread)
    if task == "ocr": self.worker_thread.started.connect(lambda: self.worker.run_ocr(args[0], "ENG"))
    else: self.worker_thread.started.connect(lambda: self.worker.run_clean(args[0], args[1], args[2]))
    self.worker.progress.connect(self.progress_bar.setValue)
    self.worker.finished.connect(self.on_task_finished)
    self.worker.error.connect(self.on_task_error)
    self.worker_thread.start()
```
Prefer the PanelCleaner `gui/worker_thread.py:Worker(QRunnable)` pattern instead (see `gui/worker_thread.py` below) — it is GPL-compat and more robust (abort flag, typed `WorkerError`, `finished`/`result`/`error`/`aborted` signals).

**OOM / error banner** — PanelCleaner `mainwindow_driver.py:2405-2427`:
```python
def init_oom_banner(self) -> None:
    self.widget_oom_banner.hide()
    self.label_oom_icon.setPixmap(Qg.QIcon.fromTheme("dialog-warning").pixmap(24, 24))
    self.widget_oom_banner.setStyleSheet(f"background-color: #550000; color: #ffffff;")
    ...
```
UI-SPEC §Color maps this to our error chip `#7a1f1f` bg / `#ffffff` text (slightly lightened from PanelCleaner's `#550000`). Same pattern: a persistent status-bar chip shown on model-load failure, dismissed on next successful op.

---

### `gui/canvas.py` (component, event-driven) — COMPOSITE, OUR OWN REIMPLEMENTATION

**Primary analog (reference-only — DO NOT copy):** MangaCleaner_GPU `frontend/canvas.py:MangaCanvas`.
**Secondary analog (mechanics, GPL):** PanelCleaner `gui/image_viewer.py:ImageViewer`.

**Scene/item stack** — MangaCleaner_GPU `canvas.py:14-47`:
```python
class MangaCanvas(QGraphicsView):
    mask_changed = Signal()
    tool_state_updated = Signal(bool)
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor(11, 11, 14)))      # canvas matte #0b0b0e
        self.image_item = QGraphicsPixmapItem()
        self.mask_item = QGraphicsPixmapItem()
        self.scene.addItem(self.image_item); self.scene.addItem(self.mask_item)
        self.cursor_item = QGraphicsEllipseItem()
        self.cursor_item.setZValue(1000)
        self.scene.addItem(self.cursor_item)
        self.current_tool = "NONE"
        self.brush_size = 40                                       # UI-SPEC default
        ...
```
Reimplement with: scene stack `image_item → mask_item → preview_item (QGraphicsPathItem, dashed cyan) → cursor_item (QGraphicsEllipseItem, z=1000)`. Background `#0b0b0e` (UI-SPEC canvas matte). Brush default 40 (UI-SPEC surface 6).

**Mask paint helpers** — MangaCleaner_GPU `canvas.py:121-149`:
```python
def get_painter(self):
    p = QPainter(self.mask)
    p.setRenderHint(QPainter.Antialiasing)
    if self.is_eraser:
        p.setCompositionMode(QPainter.CompositionMode_Clear)
        color = Qt.transparent
    else:
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        color = QColor(255, 0, 0, 160)                            # ~rgba(255,0,0,0.63)
    return p, color

def paint_mask_stroke(self, p1, p2):
    painter, color = self.get_painter()
    painter.setPen(QPen(color, self.brush_size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawLine(p1, p2); painter.end(); self.update_mask_display()
```
Use `QColor(255, 0, 0, 160)` for mask paint (160/255 ≈ 0.63, UI-SPEC §Color mask overlay token). Eraser via `CompositionMode_Clear`. Brush stroke uses `Qt.RoundCap, Qt.RoundJoin` (UI-SPEC surface 6 Brush behavior). **Note:** our `core/mask_editor.py` should host this logic, with `gui/canvas.py` calling into it (separation per D-10: `gui/` = Qt, `core/` = ops).

**Event handlers** — MangaCleaner_GPU `canvas.py:86-119` (mouse press/move/release dispatching on `current_tool`). Reimplement to route BRUSH/RECT/LASSO/ERASER per UI-SPEC surface 6, with `QPainterPath` dashed-cyan preview for RECT/LASSO (`canvas.py:40-42`: `QPen(QColor(0, 212, 255, 200), 2, Qt.DashLine)`).

**Pan/zoom mechanics — COPY FROM PanelCleaner (GPL, vendored shape):** `image_viewer.py:125-260`:
```python
ZOOM_TICK_FACTOR = 1.25

def wheelEvent(self, event):
    if Qt.ControlModifier & event.modifiers():
        if event.angleDelta().y() > 0: self.zoom_in(wheel=True)
        else: self.zoom_out(wheel=True)
    elif Qt.ShiftModifier & event.modifiers():
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() - event.angleDelta().y())
    else: super().wheelEvent(event)

def zoom_in(self, wheel=False):
    self.zoom(ZOOM_TICK_FACTOR**0.5 if wheel else ZOOM_TICK_FACTOR)   # half-step on wheel

def zoom(self, factor, *, suppress_signals=False):
    proposed_zoom_factor = min(self.zoom_factor * factor, 100)        # max 100x clamp
    ...
    if proposed_width < view_width / 2 and proposed_height < view_height / 2 and factor < 1:
        return                                                        # min = half viewport
    self.zoom_factor = proposed_zoom_factor
    self.update_smoothing()
    self.setTransform(Qg.QTransform().scale(self.zoom_factor, self.zoom_factor))

def update_smoothing(self):
    if self.zoom_factor > 1:
        self.setRenderHint(Qg.QPainter.SmoothPixmapTransform, False)  # pixel-accurate >1x
    else:
        self.setRenderHint(Qg.QPainter.SmoothPixmapTransform, True)
```
These mechanics (Ctrl+wheel half-step zoom, `√1.25` factor, 100× max, half-viewport min, `AnchorUnderMouse`, smoothing toggle at 1×, `QImageReader.setAllocationLimit(0)` at line 45 for large pages) are exactly UI-SPEC surface 2. Vendor this logic into our `gui/canvas.py` (GPL-compat) — only the mask painting needs to be reimplemented from MangaCleaner_GPU.

---

### `gui/file_table.py` (component, event-driven)

**Primary analog (reference pattern):** MangaCleaner_GPU `frontend/widgets.py:FileListWidget`.
**Secondary analog (thumbnail/icon-size reference):** PanelCleaner `gui/file_table.py:FileTable`.

UI-SPEC surface 3 specifies `QListView` in `ListMode` (NOT PanelCleaner's `QTableWidget` — PanelCleaner's table has analytics columns we don't need in Phase 1). So the primary structural analog is the simpler MangaCleaner_GPU `FileListWidget`:

```python
# widgets.py:11-19 (REFERENCE — reimplement)
class FileListWidget(QListWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background: {Config.COLOR_PANEL}; border: none;")
    def add_file(self, full_path: str):
        item = QListWidgetItem(os.path.basename(full_path))
        item.setData(Qt.UserRole, full_path)
        self.addItem(item)
```
Extend to UI-SPEC surface 3 contract: 80px row, 64×64 thumbnail (use `QListWidget.setIconSize(QSize(64, 64))` — cf. PanelCleaner `file_table.py:89` `setIconSize(Qc.QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE))`), filename + 1-indexed page number, natural-sort (`from natsort import natsorted` — PanelCleaner `file_table.py:12`), selected row bg `rgba(0,212,255,0.18)` + 2px accent left border (QSS, cf. MangaCleaner_GPU `styles.qss:97-100` `QListWidget::item:selected { border-left: 3px solid #00d4ff; }`).

**Signals to emit:** `file_clicked(Path)`, `files_dropped(list[Path])`, `folder_dropped(Path)`. MainWindow connects these to canvas-load and history-reset (cf. MangaCleaner_GPU `main_window.py:344-348` `on_file_clicked` which resets `self.history = HistoryManager(...)` on page change).

---

### `gui/tools_panel.py` (component, event-driven)

**Analog (reference):** MangaCleaner_GPU `frontend/widgets.py:ToolGroup` + `BrushSlider`.

**ToolGroup pattern** (`widgets.py:21-41`):
```python
class ToolGroup(QFrame):
    def __init__(self, title, button_configs):
        super().__init__()
        lay = QVBoxLayout(self); lay.setContentsMargins(5, 5, 5, 5); lay.setSpacing(4)
        lbl = QLabel(title.upper()); ...
        self.buttons = {}
        checkable = ["MOVE", "BRUSH", "RECT", "LASSO"]
        for name in button_configs:
            btn = QPushButton(name)
            if name in checkable:
                btn.setCheckable(True); btn.setAutoExclusive(True)
            self.buttons[name] = btn; lay.addWidget(btn)
```
Reimplement with `QActionGroup` for the 5 exclusive tools (Move/Brush/Rectangle/Lasso/Eraser) per UI-SPEC surface 6. Active tool highlighted with accent `#00d4ff` (QSS `:checked` — cf. MangaCleaner_GPU `styles.qss:44-48`).

**BrushSlider pattern** (`widgets.py:60-88`): `QSlider` + label. UI-SPEC surface 6 contracts `QSlider (1–300) + QSpinBox (1–300)` side by side, label "Brush size: {n} px", default 40. Reimplement with the spinbox added (MangaCleaner_GPU omits the spinbox).

---

### `gui/worker_thread.py` (provider, event-driven async) — VENDORED FROM PANELCLEANER

**Analog:** PanelCleaner `gui/worker_thread.py` (`Worker(QRunnable)`, `WorkerSignals`, `WorkerError`, `Abort`, `SharableFlag`).

**This is the single most important infrastructure file for Phase 1.** Vendor it near-verbatim (GPL-compat). It is more robust than MangaCleaner_GPU's inline `AIWorker(QObject)` pattern.

**Signals contract** (`worker_thread.py:29-56`):
```python
class WorkerSignals(QObject):
    finished = Signal(tuple)        # (args, kwargs) passed to the worker
    error = Signal(WorkerError)     # typed: exception_type, value, traceback
    result = Signal(object)         # the return value of fn
    progress = Signal(object)       # anything
    aborted = Signal(tuple)
```

**Run loop with abort + error capture** (`worker_thread.py:126-161`):
```python
@Slot()
def run(self) -> None:
    try:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Abort:
            self.signals.aborted.emit((self.args, self.kwargs))
        except Exception:
            exception_type, value, traceback = sys.exc_info()
            self.signals.error.emit(WorkerError(exception_type, value, traceback, self.args, self.kwargs))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit((self.args, self.kwargs))
    except RuntimeError:
        pass   # signals deleted during shutdown
```

**Auto-injection of progress + abort** (`worker_thread.py:97-124`): the constructor injects `progress_callback` and `abort_flag` into kwargs unless `no_progress_callback=True`. Task functions sign a contract: `def fn(..., progress_callback=None, abort_flag=None)`.

**Usage in MainWindow** — wire `gui/worker_thread.Worker` to the backend dispatch (D-08). The worker calls the adapter; the adapter talks to the subprocess; the worker's `progress_callback` relays backend progress. (Contrast: MangaCleaner_GPU `main_window.py:288-298` connects `worker.progress` directly to `progress_bar.setValue` — same shape, but our `progress` carries `(percent, message)` tuples per UI-SPEC status-bar contract.)

---

### `core/image_file.py` (model, CRUD)

**Analog:** PanelCleaner `gui/image_file.py:ImageFile`.

**PanelCleaner's `ImageFile`** holds path, thumbnail, analytics, split-children, processing state — far more than Phase 1 needs. Role-match: extract the path/thumb/state triad. Reference the thumbnail constant: PanelCleaner `file_table.py:89` uses `imf.THUMBNAIL_SIZE` — UI-SPEC overrides to 64 (PanelCleaner's is larger).

**Contract for our `ImageFile`:** `path: Path`, `thumbnail: QPixmap | None`, `mask: QImage | None`, `dirty: bool`. Methods: `load_thumbnail()`, `clear_mask()`. Keep it minimal; Phase 2+ can grow it.

---

### `core/mask_editor.py` (service, transform)

**Analogs:** MangaCleaner_GPU `frontend/canvas.py` paint helpers (reference) + PanelCleaner `image_ops.py` mask conversions (GPL).

**Logic to extract from `canvas.py`** (the painter/stroke/rect/lasso/eraser dispatch, lines 121-149): the *pure mask mutation* — given a `QImage` mask, a tool, two points, and a brush size, return a new mask. This is the testable core that `gui/canvas.py` calls; keeping it in `core/` lets `tests/test_mask_editor.py` (RESEARCH §Validation Architecture) exercise paint logic without instantiating Qt widgets.

**Mask conversion** — PanelCleaner `image_ops.py:57-60`:
```python
def convert_mask_to_rgba(mask: Image.Image,
    color: tuple[int, int, int] | tuple[int, int, int, int] = (255, 255, 255, 255)) -> Image.Image:
    ...
```
Use PanelCleaner's mask↔RGBA conversions as the canonical path (Pitfall 6 — centralize mask format to avoid ARGB32/RGB32 bugs).

**Backend mask format:** adapters take `np.ndarray (H,W)` binary masks (RESEARCH Pattern 1 `InpaintModel.inpaint(image, mask)`). So `core/mask_editor.py` also owns the QImage↔numpy conversion used before dispatching to the inpaint backend. Cf. MangaCleaner_GPU `main_window.py:265-267` for the (buggy — no `.copy()`) reference:
```python
ptr = self.canvas.mask.bits()
mask_np = np.frombuffer(ptr, np.uint8).reshape((h, w, 4))
mask_gray = mask_np[:, :, 3].copy()   # .copy() is MANDATORY (Pitfall 2 — QImage lifetime)
```
**Our version MUST `.copy()` the numpy buffer** (Pitfall 2 in RESEARCH §Common Pitfalls).

---

### `core/history_manager.py` (service, undo/redo)

**Analog (reference — reimplement with 2 stacks, not 4):** MangaCleaner_GPU `utils/history.py:HistoryManager`.

**MangaCleaner_GPU 4-stack pattern** (`history.py:8-52`):
```python
class HistoryManager:
    def __init__(self, limit=20):
        self.limit = 20
        self.img_undo = []; self.img_redo = []
        self.mask_undo = []; self.mask_redo = []

    def push_image_action(self, x, y, patch):
        self.img_undo.append((x, y, patch.copy()))
        self.img_redo.clear()
        if len(self.img_undo) > self.limit: self.img_undo.pop(0)

    def pop_image_undo(self, current_img):
        if not self.img_undo: return None
        x, y, patch = self.img_undo.pop()
        h, w = patch.shape[:2]
        redo_patch = current_img[y:y+h, x:x+w].copy()
        self.img_redo.append((x, y, redo_patch))
        return (x, y, patch)

    def push_mask_state(self, mask_qimage):
        self.mask_undo.append(mask_qimage.copy())
        self.mask_redo.clear()
        if len(self.mask_undo) > self.limit: self.mask_undo.pop(0)

    def pop_mask_undo(self, current_mask):
        if not self.mask_undo: return None
        self.mask_redo.append(current_mask.copy())
        return self.mask_undo.pop()
```

**Phase 1 contract (UI-SPEC surface 8):** two stacks — MASK (painting ops) + IMAGE (inpaint ops). Same `push_*/pop_*` shape as above. Snapshot strategy: **full `QImage`/mask per entry** for Phase 1 (RESEARCH Open Question 3 — optimize later). Image undo stores `(x, y, patch)` tiles (MangaCleaner_GPU pattern — patches are the inpainted regions); mask undo stores full mask snapshots (masks are cheap).

**Shortcut wiring** (UI-SPEC surface 8, supersedes MangaCleaner_GPU `main_window.py:168-171`): `Ctrl+Z`/`Ctrl+Shift+Z` → image undo/redo; `Alt+Z`/`Alt+Shift+Z` → mask undo/redo. Each toolbar button disabled when its stack is empty.

---

### `pyproject.toml` + `tests/` (config + test)

**No codebase analog** (greenfield). Follow standards:
- `pyproject.toml`: `[project]` with the deps from RESEARCH §Standard Stack split by env (D-07: `main_env` vs `torch_env`). Use `uv` for env management.
- `tests/conftest.py`: shared fixtures (sample manga page, default `Profile`, mock `DetectionModel`/`InpaintModel` for headless tests). Use `pytest-qt` for the GUI smoke tests listed in RESEARCH §Validation Architecture (Wave 0 gaps).

---

## Shared Patterns

### 1. Theme application (single dark QPalette at startup)

**Source:** PanelCleaner `mainwindow_driver.py:191-217`; UI-SPEC §Color.
**Apply to:** `gui/main_window.py` only (once, at startup — NOT per-widget).
```python
Qw.QApplication.setStyle("Fusion")
palette = build_dark_palette()   # from UI-SPEC §Color tokens
Qw.QApplication.setPalette(palette)
```
Tokens: dominant `#232328`, canvas matte `#0b0b0e`, secondary `#2d2d33`, divider `#3a3a42`, accent `#00d4ff`, text primary `#e8e8ea`, text muted `#9a9aa2`, error chip `#7a1f1f`/`#ffffff`.

### 2. Worker thread dispatch (QRunnable + typed signals)

**Source:** PanelCleaner `gui/worker_thread.py` (vendored).
**Apply to:** every async operation — detection (`D`), inpainting (`C`), thumbnail generation, image load.
```python
worker = Worker(my_task_func, arg1, arg2, abort_signal=some_abort_signal)
worker.signals.result.connect(on_success)
worker.signals.error.connect(on_error)       # receives WorkerError
worker.signals.progress.connect(on_progress) # receives (percent, message)
worker.signals.finished.connect(cleanup)
QThreadPool.globalInstance().start(worker)
```
**Pitfall guard (RESEARCH P3/P6):** workers touch only numpy/Python data and emit signals. Main thread does ALL Qt mutation in signal handlers. The adapter call inside the worker talks to the backend subprocess (D-08), never to Qt.

### 3. Model adapter invocation (the D-01 contract)

**Source:** `adapters/base.py` ABCs + `adapters/torch_impl.py` concrete.
**Apply to:** every place that does detection or inpainting. Never import `TextDetector` or `SimpleLama` directly outside `adapters/torch_impl.py`.
```python
# Resolution by config (D-02):
detection_model = backend_factory("detection", config.detection_backend)  # "torch" -> TorchCTDModel
mask, blocks = detection_model.detect(image)
```
Backend selection keys: `detection_backend`, `ocr_backend`, `inpainting_backend` (CONTEXT.md §Specific Ideas).

### 4. Config round-trip (ConfigUpdater INI, not JSON)

**Source:** `panelcleaner/config.py` (vendored).
**Apply to:** `config/profile_manager.py` and anywhere settings are read/written.
```python
profile.safe_write(path)                       # write INI
profile = Profile.load(path)                   # read INI (classmethod)
config = Config.from_config_updater(profile.bundle_config())   # materialize
general = profile.general                      # GeneralConfig (NOT profile.general_config)
```
**Never** introduce `to_json`/`from_json` for settings (D-05). JSON is reserved for pipeline data (`PageData.to_json`, `MaskData.to_json`).

### 5. Image/mask buffer lifetime safety

**Source:** RESEARCH §Common Pitfalls P2 + MangaCleaner_GPU `main_window.py:265-267` (the reference is buggy).
**Apply to:** every numpy↔QImage bridge (canvas display, mask→backend dispatch, backend→canvas result).
```python
# When creating QImage from numpy:
qimg = QImage(arr.data, w, h, stride, format).copy()   # .copy() breaks the buffer link

# When extracting numpy from QImage bits:
ptr = qimg.bits()
arr = np.frombuffer(ptr, np.uint8).reshape(h, w, 4).copy()   # .copy() before the buffer GCs
```

### 6. Logging

**Source:** PanelCleaner `inpainting.py:6`, `image_ops.py:13`, `config.py:12`.
**Apply to:** all modules.
```python
from loguru import logger
logger.info(f"Engine Ready | Device: {self.device}")   # structured-ish, level-aware
```
Use `loguru` consistently (PanelCleaner's choice; one less decision). Status-bar messages in the GUI are separate from loguru logs.

---

## No Analog Found

**None.** Every Phase 1 file has at least a role-match analog. Files with no *exact* analog (planner uses RESEARCH.md patterns + the analog shape):

| File | Closest analog | Why role-match only |
|------|----------------|----------------------|
| `adapters/base.py` | PanelCleaner `InpaintingModel` (concrete) | The ABCs are new; RESEARCH Pattern 1 is the design source. |
| `core/image_file.py` | PanelCleaner `gui/image_file.py:ImageFile` | PanelCleaner's class is heavier than Phase 1 needs — extract the minimal triad. |
| `pyproject.toml`, `tests/conftest.py` | (none) | Greenfield config/test scaffolding — use standards (uv, pytest, pytest-qt). |

---

## Metadata

**Analog search scope:**
- `C:\Src\PanelCleaner\pcleaner\` (full tree: `config.py`, `inpainting.py`, `masker.py`, `image_ops.py`, `structures.py`, `model_downloader.py`, `comic_text_detector/`, `gui/mainwindow_driver.py`, `gui/image_viewer.py`, `gui/file_table.py`, `gui/worker_thread.py`, `gui/image_file.py`)
- `C:\Users\Stella\Downloads\MangaCleaner_GPU\_internal\src\` (`frontend/canvas.py`, `frontend/main_window.py`, `frontend/widgets.py`, `frontend/styles.qss`, `backend/onnx_engine.py`, `backend/processor.py`, `backend/workers.py`, `utils/history.py`, `utils/config.py`)

**Files scanned:** 22 analog files (11 PanelCleaner + 9 MangaCleaner_GPU + 2 targeted `mainwindow_driver.py` ranges).
**Pattern extraction date:** 2026-07-12.
**Source verification:** line-number citations above were verified by direct Read of the source on 2026-07-12. Two inaccuracies in CONTEXT.md/RESEARCH.md flagged in the "Critical Correction" section (TextDetector 3-tuple, Profile.safe_write).
