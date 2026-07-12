# Phase 1: Cleaning Workspace - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning

## Phase Boundary

Adapt PanelCleaner (GPL v3) as the application foundation with a modular model adapter interface. Users can open and navigate manga pages, detect text masks via Comic Text Detector (CTD), edit masks with brush/rect/lasso tools, run LaMa inpainting to remove text, and undo/redo operations. This establishes the cleaning workspace core — the canvas, detection, and inpainting pipeline that all subsequent features build upon.

The model adapter interface enables modularity: PyTorch backends (PanelCleaner stack) are the v1 default, but ONNX Runtime backends (MangaCleaner_GPU stack) can be swapped in as user-installed modules. This isolation strategy uses proactive per-backend pyenvs to avoid dependency conflicts while maintaining a clean separation of concerns.

## Implementation Decisions

### Model Adapter Interface
- **D-01:** Type-specific base classes with full pipeline hooks — `DetectionModel`, `OCRModel`, `InpaintModel` each provide `load()`, `detect()/recognize()/inpaint()`, `preprocess()`, `postprocess()`, `configure()`, `get_info()` methods
- **D-02:** Per-model backend configuration — users can mix backends via config (e.g., `detection_backend: torch`, `inpainting_backend: onnx`). Phase 1 default: all PyTorch backends
- **D-03:** Interface enables modular swapping — PanelCleaner PyTorch models for v1, MangaCleaner_GPU ONNX models as optional add-ons

### Config System
- **D-04:** Full PanelCleaner config verbatim — adapt entire `config.py` system with `Config`, `Profile`, `MaskerConfig`, `DenoiserConfig`, `InpainterConfig` classes. Ensures 100% compatibility with existing pcleaner configs
- **D-05:** JSON export/import for PanelCleaner settings compatibility
- **D-06:** Profile switching UI can be simplified in v1 but schema exists for full feature parity

### pyenv Isolation Strategy
- **D-07:** Proactive per-backend envs — create isolated pyenvs during setup, not reactively when conflicts occur
- **D-08:** Complete backend isolation — each env contains only its backend dependencies:
  - `torch_env`: PyTorch, transformers, manga-ocr, CTD models
  - `onnx_env`: ONNX Runtime, opencv, numpy
  - `main_env`: PySide6, GUI, config, application logic
- **D-09:** Phase 1 default uses `torch_env` (PanelCleaner PyTorch stack). `onnx_env` available for MangaCleaner_GPU ONNX models

### Code Organization
- **D-10:** Adapters + adapted source layout — explicit organization showing what's adapted PanelCleaner code vs. original adapter interfaces:
  - `adapters/` — Model adapter interfaces
  - `panelcleaner/` — Adapted PanelCleaner source code
  - `gui/` — PySide6 interface
  - `core/` — Application logic
  - `config/` — PanelCleaner config system
- **D-11:** Adapter structure: `adapters/base.py` (base classes), `adapters/torch_impl.py` (PanelCleaner implementations), `adapters/onnx_impl.py` (MangaCleaner_GPU implementations)

### Claude's Discretion
- Package naming within submodules (e.g., `gui/widgets.py` vs `gui/components/widgets.py`) — follow PanelCleaner patterns where sensible
- Import organization within adapted PanelCleaner code — preserve original structure unless it conflicts with our layout
- Color scheme/theme — can adapt PanelCleaner's theme or create new branding; user hasn't specified preference

## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Foundation
- `.planning/PROJECT.md` — PanelCleaner (GPL v3) as primary codebase, model adapter interface modularity, pyenv isolation strategy
- `.planning/REQUIREMENTS.md` — CLEAN-01 through CLEAN-06 (cleaning capabilities), FLOW-01 (file-list sidebar navigation), FLOW-02 (undo/redo)

### Phase Scope
- `.planning/ROADMAP.md` §Phase 1 — Goal, success criteria, requirements mapping

### Source References
- `../PanelCleaner/` — PanelCleaner reference source (GPL v3). Contains all modules to adapt:
  - `../PanelCleaner/pcleaner/config.py` — Profile-based config system (adapt verbatim per D-04)
  - `../PanelCleaner/pcleaner/gui/mainwindow_driver.py` — Main window architecture
  - `../PanelCleaner/pcleaner/gui/image_viewer.py` — Image display and navigation
  - `../PanelCleaner/pcleaner/gui/file_table.py` — File list sidebar
  - `../PanelCleaner/pcleaner/comic_text_detector/` — CTD text detection (PyTorch)
  - `../PanelCleaner/pcleaner/inpainting.py` — LaMa via `simple_lama_inpainting`
  - `../PanelCleaner/pcleaner/masker.py` — Mask processing and refinement
  - `../PanelCleaner/pcleaner/image_ops.py` — Image operations (crop, rotate, levels)
  - `../PanelCleaner/pcleaner/ocr/ocr_mangaocr.py` — manga-ocr wrapper (for Phase 4)

### Technology Stack
- `.claude/CLAUDE.md` §Technology Stack — PySide6, Python 3.12, PyTorch, ONNX Runtime, OpenCV, NumPy
- `.claude/CLAUDE.md` §Stack Patterns — Single environment preferred with isolated pyenv fallback

### Licensing
- `../PanelCleaner/LICENSE` — GPL v3 license. Our derivative works must also be GPL v3 (copyleft)

## Existing Code Insights

### Reusable Assets
- `pcleaner/config.py` — Complete profile-based settings system with JSON serialization. Provides PanelCleaner compatibility out of the box.
- `pcleaner/gui/mainwindow_driver.py` — Main window with profile system, worker thread pool, file table integration. Proven architecture.
- `pcleaner/comic_text_detector/` — PyTorch-based text detection with heatmap generation and TextBlock output structures.
- `pcleaner/inpainting.py` — LaMa inpainting via `simple_lama_inpainting` package with box-based inpainting logic.
- `pcleaner/ocr/ocr_mangaocr.py` — manga-ocr wrapper (Phase 4 OCR recognition).
- `pcleaner/masker.py` — Mask refinement, box handling, and processing utilities.
- `pcleaner/image_ops.py` — Image operations: crop, rotate, levels/curves adjustment.

### Established Patterns
- **Profile-driven config** — Settings are organized into profiles with JSON export/import. Changes trigger `profile_values_changed` signals.
- **Worker thread pool** — `QThreadPool` for async tasks without blocking GUI. Separate thread queue for sequential tasks.
- **Model lazy-loading** — Models are loaded on-demand and cached (e.g., `shared_ocr_model` in MainWindow).
- **Step-based processing** — Pipeline organized into steps (Masker → Denoiser → Inpainter) with analytics and progress tracking.

### Integration Points
- **Model adapter interface** — All model loading and inference flows through `DetectionModel`, `OCRModel`, `InpaintModel` base classes. Backend implementations (torch/onnx) are injected at runtime based on config.
- **Config system** — All settings read from adapted PanelCleaner config. Backend selection via `*_backend` config keys.
- **pyenv isolation** — Backend implementations run in their isolated environments. Main app (main_env) dispatches to torch_env or onnx_env as needed.

## Specific Ideas

- **Per-model backend config granularity** — Users can run CTD on PyTorch while using ONNX Runtime for LaMa inpainting if they prefer. Config keys: `detection_backend`, `ocr_backend`, `inpainting_backend`
- **Complete backend isolation** — No shared dependencies between torch_env and onnx_env. Clean separation prevents numpy version conflicts (numpy<2 for ONNX, numpy 1.x/2.x for PyTorch)
- **Explicit adapted source layout** — `panelcleaner/` directory makes it clear what code is adapted from PanelCleaner vs. our original adapters

## Deferred Ideas

None — discussion stayed within phase scope. All architectural decisions support Phase 1 cleaning parity goal.

---

*Phase: 1-Cleaning Workspace*
*Context gathered: 2026-07-11*
