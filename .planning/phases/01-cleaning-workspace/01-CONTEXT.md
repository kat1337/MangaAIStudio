# Phase 1: Cleaning Workspace - Context

**Gathered:** 2026-07-11
**Revised:** 2026-07-12 (source verification — env strategy D-07/D-08/D-09, config format D-05, code org D-10)
**Status:** Ready for planning

## Phase Boundary

Adapt PanelCleaner (GPL v3) as the application foundation with a modular model adapter interface. Users can open and navigate manga pages, detect text masks via Comic Text Detector (CTD), edit masks with brush/rect/lasso tools, run LaMa inpainting to remove text, and undo/redo operations. This establishes the cleaning workspace core — the canvas, detection, and inpainting pipeline that all subsequent features build upon.

The model adapter interface enables modularity: PyTorch backends (PanelCleaner stack) are the v1 default, but ONNX Runtime backends (MangaCleaner_GPU stack) can be swapped in as user-installed modules. Isolation follows a frontend/backend split (see D-07) — the GUI and the model-inference backends live in separate environments, with ONNX further isolated because it requires a newer Python than the PyTorch stack.

## Implementation Decisions

### Model Adapter Interface
- **D-01:** Type-specific base classes with full pipeline hooks — `DetectionModel`, `OCRModel`, `InpaintModel` each provide `load()`, `detect()/recognize()/inpaint()`, `preprocess()`, `postprocess()`, `configure()`, `get_info()` methods
- **D-02:** Per-model backend configuration — users can mix backends via config (e.g., `detection_backend: torch`, `inpainting_backend: onnx`). Phase 1 default: all PyTorch backends
- **D-03:** Interface enables modular swapping — PanelCleaner PyTorch models for v1, MangaCleaner_GPU ONNX models as optional add-ons

### Config System
- **D-04:** Full PanelCleaner config verbatim — adapt entire `config.py` system with `GeneralConfig`, `TextDetectorConfig`, `PreprocessorConfig`, `Profile`, `MaskerConfig`, `DenoiserConfig`, `InpainterConfig`, `Config` classes. Ensures 100% compatibility with existing pcleaner configs
- **D-05:** ConfigUpdater/INI export/import for PanelCleaner settings compatibility. **PanelCleaner persists profiles via `ConfigUpdater` (INI-style), NOT JSON** — verified against `config.py`: `Profile.save(path)` / `Profile.load(path)` (config.py:1015, 1217), `Config.from_config_updater(...)` (config.py:1310), and per-section `export_to_conf(config_updater)` / `import_from_conf(config_updater)`. JSON appears in PanelCleaner only for pipeline data (`PageData.to_json/from_json`, `#clean.json`, `#mask_data.json`), never for settings. (Corrected 2026-07-12: the prior "JSON export/import" premise was a misread of the source.)
- **D-06:** Profile switching UI can be simplified in v1 but schema exists for full feature parity

### Environment Isolation Strategy
- **D-07:** Frontend/backend environment split — aim to isolate the backend (model inference) from the frontend (GUI) **whenever practical**. Two primary envs:
  - `main_env` (frontend): PySide6, GUI, PanelCleaner config system, application logic
  - `torch_env` (backend): PyTorch, transformers, manga-ocr, CTD + LaMa models — runs model inference
- **D-08:** Backend runs as a worker subprocess of the frontend. Separate envs require separate processes, so the frontend dispatches model work (detect/inpaint/OCR) to a backend process rather than calling models in-process (PanelCleaner's in-process `QThreadPool` pattern assumes a single env and does not transfer directly). The exact IPC/transport (stdin/stdout framing, local socket, or job-queue with shared files) is left to planning.
- **D-09:** ONNX backend (`onnx_env`) is isolated because it requires a **newer Python version** than the PyTorch stack — a concrete, unavoidable reason, not a precautionary split. ONNX backends are a future optional add-on (MangaCleaner_GPU models); Phase 1 default is the PyTorch backend (`torch_env`).
- **D-09b:** Single-env is the proven fallback. PanelCleaner's own `requirements.txt` confirms the full PyTorch stack (torch + PySide6 + manga_ocr + simple_lama_inpainting + opencv + numpy) coexists in one environment today. "Whenever possible" means: isolation is the goal, not an absolute — if the subprocess split blocks progress for a given backend, that backend may run in-process.

### Code Organization
- **D-10:** Adapters + adapted source layout — explicit organization distinguishing vendored PanelCleaner source from our own code:
  - `adapters/` — Model adapter interfaces (our own)
  - `panelcleaner/` — Adapted PanelCleaner source, **vendored near-verbatim per D-12** (config, CTD detection, LaMa inpainting, masker, image ops, file table, image viewer). PanelCleaner is a batch detector + review viewer — it has no freehand mask painting.
  - `gui/` — PySide6 interface (our own). Includes the interactive mask-editing canvas (`canvas.py`: brush/rectangle/lasso/eraser) for CLEAN-03/04/05 — **our own reimplementation patterned after MangaCleaner_GPU, NOT vendored source** (PanelCleaner has no freehand painting; MangaCleaner_GPU is reference-only per D-12).
  - `core/` — Application logic (our own), including mask-editing ops and the history/undo manager (patterned after MangaCleaner_GPU, reimplemented).
  - `config/` — PanelCleaner config system
- **D-11:** Adapter structure: `adapters/base.py` (base classes), `adapters/torch_impl.py` (PanelCleaner PyTorch implementations), `adapters/onnx_impl.py` (ONNX implementations — written against the ONNX Runtime API, referencing MangaCleaner_GPU's approach but not copying its source)

### Adaptation / Licensing Policy
- **D-12:** PanelCleaner source is adapted **near-verbatim** — it is GPL v3 and we are GPL v3, so derivative copying is intended and license-compatible. MangaCleaner_GPU is **reference-only**: read it for patterns and re-implement in our own code; do **not** copy its source into the repo. Two reasons: (1) MangaCleaner_GPU ships as a binary distribution at `~/Downloads/MangaCleaner_GPU` (`.exe` + `_internal/`) with **no LICENSE file** — absent a license, the code is all-rights-reserved and cannot be vendored into a GPL v3 derivative; (2) the user's explicit policy: base the implementation on it, don't copy verbatim. Readable source for reference lives at `~/Downloads/MangaCleaner_GPU/_internal/src/` (`frontend/canvas.py`, `backend/onnx_engine.py`, etc.).

### Claude's Discretion
- Package naming within submodules (e.g., `gui/widgets.py` vs `gui/components/widgets.py`) — follow PanelCleaner patterns where sensible
- Import organization within adapted PanelCleaner code — preserve original structure unless it conflicts with our layout
- Color scheme/theme — can adapt PanelCleaner's theme or create new branding; user hasn't specified preference

## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Foundation
- `.planning/PROJECT.md` — PanelCleaner (GPL v3) as primary codebase, model adapter interface modularity, frontend/backend env split
- `.planning/REQUIREMENTS.md` — CLEAN-01 through CLEAN-06 (cleaning capabilities), FLOW-01 (file-list sidebar navigation), FLOW-02 (undo/redo)

### Phase Scope
- `.planning/ROADMAP.md` §Phase 1 — Goal, success criteria, requirements mapping

### Source References
- `../PanelCleaner/` — PanelCleaner reference source (GPL v3, uses **PySide6** per `requirements.txt`). Contains all modules to adapt:
  - `../PanelCleaner/pcleaner/config.py` — Profile-based config system. Uses **ConfigUpdater (INI)** for persistence (`Profile.save/load`, `export_to_conf`/`import_from_conf`), NOT JSON. Adapt per D-04/D-05.
  - `../PanelCleaner/pcleaner/gui/mainwindow_driver.py` — Main window architecture
  - `../PanelCleaner/pcleaner/gui/image_viewer.py` — Image display/review (`QGraphicsView`-based viewer; NOT a freehand mask canvas)
  - `../PanelCleaner/pcleaner/gui/file_table.py` — File list sidebar
  - `../PanelCleaner/pcleaner/comic_text_detector/inference.py` — CTD `TextDetector` (PyTorch). Note: `__call__` returns a **5-tuple** `(img, mask, mask_refined, blk_list, refine_mode)` and `refine_mode` takes the `REFINEMASK_*` constants.
  - `../PanelCleaner/pcleaner/inpainting.py` — LaMa via `simple_lama_inpainting` (`InpaintingModel`)
  - `../PanelCleaner/pcleaner/masker.py` — Mask processing and refinement
  - `../PanelCleaner/pcleaner/image_ops.py` — Image operations (crop, rotate, levels)
  - `../PanelCleaner/pcleaner/ocr/ocr_mangaocr.py` — manga-ocr wrapper (for Phase 4)
  - `../PanelCleaner/pcleaner/model_downloader.py` — Model fetch logic (HuggingFace)
- `~/Downloads/MangaCleaner_GPU/_internal/src/` — MangaCleaner_GPU readable source (ONNX stack; bundled inside the PyInstaller binary distribution at `~/Downloads/MangaCleaner_GPU`). **Reference-only per D-12 — do NOT copy verbatim** (the distribution carries no LICENSE, so its code is all-rights-reserved). Use as a pattern reference for the interactive mask-editing canvas (`frontend/canvas.py`), QThread worker pattern, and ONNX model loading (`backend/onnx_engine.py`); re-implement in our own code. See `.planning/research/ARCHITECTURE.md` for the component map.

### Technology Stack
- `.claude/CLAUDE.md` §Technology Stack — PySide6, Python 3.12, PyTorch, ONNX Runtime, OpenCV, NumPy. (Note: CLAUDE.md's claim that "PanelCleaner uses PyQt5" is **stale** — the cloned source at `../PanelCleaner` uses PySide6; verified 2026-07-12.)
- `.claude/CLAUDE.md` §Stack Patterns — Single environment preferred with isolated pyenv fallback (refined by D-07/D-09b into a frontend/backend split)

### Licensing
- `../PanelCleaner/LICENSE` — GPL v3 license. Our derivative works must also be GPL v3 (copyleft)

## Existing Code Insights

### Reusable Assets
- `pcleaner/config.py` — Complete profile-based settings system with ConfigUpdater (INI) serialization. Provides PanelCleaner compatibility out of the box.
- `pcleaner/gui/mainwindow_driver.py` — Main window with profile system, worker thread pool, file table integration. Proven architecture.
- `pcleaner/comic_text_detector/inference.py` — PyTorch-based text detection (`TextDetector`) with heatmap generation and TextBlock output structures.
- `pcleaner/inpainting.py` — LaMa inpainting via `simple_lama_inpainting` package (`InpaintingModel`).
- `pcleaner/ocr/ocr_mangaocr.py` — manga-ocr wrapper (Phase 4 OCR recognition).
- `pcleaner/masker.py` — Mask refinement, box handling, and processing utilities (batch-oriented).
- `pcleaner/image_ops.py` — Image operations: crop, rotate, levels/curves adjustment.
- MangaCleaner_GPU `frontend/canvas.py` (ONNX stack, at `~/Downloads/MangaCleaner_GPU/_internal/src/`) — Interactive mask-editing canvas (brush/rect/lasso/eraser) and history manager. **Reference-only (D-12)** — a pattern for our *own reimplementation* of CLEAN-03/04/05, since PanelCleaner has no freehand painting. Do not vendor.

### Established Patterns
- **Profile-driven config** — Settings organized into profiles with ConfigUpdater (INI) export/import. Changes trigger `profile_values_changed` signals.
- **Worker thread pool** — `QThreadPool` for async tasks without blocking GUI (PanelCleaner, single-env). Under our frontend/backend split this becomes a worker **subprocess** (D-08); the QThreadPool pattern still applies within the frontend env for non-model work.
- **Model lazy-loading** — Models loaded on-demand and cached.
- **Step-based processing** — Pipeline organized into steps (Masker → Denoiser → Inpainter) with analytics and progress tracking.

### Integration Points
- **Model adapter interface** — All model loading and inference flows through `DetectionModel`, `OCRModel`, `InpaintModel` base classes. Backend implementations (torch/onnx) are injected at runtime based on config.
- **Config system** — All settings read from adapted PanelCleaner config (INI/ConfigUpdater). Backend selection via `*_backend` config keys.
- **Frontend/backend process boundary** — Frontend (`main_env`) dispatches model calls to backend (`torch_env`/`onnx_env`) subprocesses; results return via the chosen IPC mechanism (TBD in planning).

## Specific Ideas

- **Per-model backend config granularity** — Users can run CTD on PyTorch while using ONNX Runtime for LaMa inpainting if they prefer. Config keys: `detection_backend`, `ocr_backend`, `inpainting_backend`
- **Frontend/backend env isolation** — Backend model inference runs in a separate env (and process) from the GUI whenever practical; ONNX backend is isolated specifically because it needs a newer Python than the PyTorch stack. Single-env remains the proven fallback (PanelCleaner's `requirements.txt` confirms the full PyTorch stack coexists).
- **Explicit vendored-vs-original layout** — a `panelcleaner/` directory holds near-verbatim PanelCleaner source (GPL v3, vendored per D-12); our own mask-editing canvas lives in `gui/`/`core/`, patterned after MangaCleaner_GPU but **not** vendored (D-12 — no license on the MangaCleaner_GPU distribution).

## Deferred Ideas

None — discussion stayed within phase scope. All architectural decisions support Phase 1 cleaning parity goal.

---

*Phase: 1-Cleaning Workspace*
*Context gathered: 2026-07-11; revised 2026-07-12 after source verification*
