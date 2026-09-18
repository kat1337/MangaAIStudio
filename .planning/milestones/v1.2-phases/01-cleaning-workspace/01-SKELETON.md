# Walking Skeleton — Manga AI Studio

**Phase:** 1
**Generated:** 2026-07-12
**Mode:** MVP + Walking Skeleton (Phase 01, new project, zero prior summaries)

## Capability Proven End-to-End

A user can launch the application, open one manga page via File → Open Image (Ctrl+O), see it
rendered on the dark canvas matte inside a PySide6 `QGraphicsView`, fit it to the window, and
close the window. This exercises the full Phase 1 stack — the `manga_ai_studio` package entry
point, the vendored `panelcleaner` config system (Profile load), the `adapters/base.py` ABC
contract, the `Fusion` dark palette application, and the `QGraphicsView` canvas — proving the
frontend environment and package layout are correct before feature plans (02–06) add detection,
mask editing, inpainting, and undo/redo.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| GUI framework | **PySide6 6.7+** (Qt6, LGPL), `QApplication.setStyle("Fusion")` | Official Qt-for-Python binding, LGPL (more permissive than PyQt5 GPL). PanelCleaner's cloned source at `C:\Src\PanelCleaner\pcleaner\` uses PySide6 (verified 2026-07-12; CLAUDE.md's "PyQt5" claim is stale). Fusion guarantees identical dark rendering on Windows and later Linux. (D-10, UI-SPEC §Design System) |
| Package layout | **Two top-level packages in one distribution.** `manga_ai_studio/` (our code: entry, `adapters/`, `gui/`, `core/`, `config/`) + `panelcleaner/` (vendored PanelCleaner, GPL v3, near-verbatim per D-12). Tests at repo-root `tests/`. | Lets vendored PanelCleaner code keep its bare `from panelcleaner.X import ...` imports (mechanical `pcleaner.` → `panelcleaner.` rewrite only — D-12) while our code lives under one namespace. (D-10, D-12) |
| Entry point | `python -m manga_ai_studio` → `manga_ai_studio/__main__.py::main()`; also `[project.scripts] manga-ai-studio = "manga_ai_studio.__main__:main"` | Standard `-m` invocation the skeleton smoke test calls; console_script for packaged runs. |
| Config system | **Vendored PanelCleaner config (INI/ConfigUpdater), verbatim** — `panelcleaner/config.py` + transitive deps (`helpers.py`, `cli_utils.py`, `model_downloader.py`, `ocr/supported_languages.py`). Wrapper: `manga_ai_studio/config/profile_manager.py::ProfileManager`. | 100% compatibility with existing pcleaner `.profile` files (D-04, D-05). Settings persist via `Profile.safe_write(path)` / `Profile.load(path)` (classmethod, `config.py:1015`); `Config.from_config_updater` materializes at `config.py:1310`. JSON is reserved for pipeline data (`PageData.to_json`) only — never for settings. |
| Model interface | **`adapters/base.py` ABCs** — `DetectionModel`, `OCRModel`, `InpaintModel`, each with `load()`, `detect()`/`recognize()`/`inpaint()`, `preprocess()`, `postprocess()`, `configure()`, `get_info()`. `adapters/onnx_impl.py` ships `NotImplementedError` stubs (ONNX is a future optional add-on). | D-01/D-02/D-03. Phase 1 default backend = `torch` (PanelCleaner stack); `adapters/torch_impl.py` concrete impls land in plans 03 (CTD) and 05 (LaMa). |
| Environment strategy | **Frontend/backend split as a goal, single-env as the proven fallback.** `main_env` (PySide6 + GUI + config) hosts the process; model inference is dispatched to a backend worker. PanelCleaner's `requirements.txt` proves the full PyTorch stack coexists in one env, so in-process fallback is always available. | D-07/D-08/D-09/D-09b. The exact IPC/transport (stdin/stdout framing vs subprocess job) is a plan-03/05 implementation detail; the skeleton runs in-process. |
| Adaptation / licensing | **PanelCleaner (`C:\Src\PanelCleaner\pcleaner\`): vendor near-verbatim** (GPL v3, license-compatible, D-12). **MangaCleaner_GPU (`~/Downloads/MangaCleaner_GPU/_internal/src/`): reference-only reimplementation** (binary distribution carries no LICENSE → all-rights-reserved → must NOT be copied; D-12). | Keeps our GPL v3 obligations clean and the user's "base on it, don't copy" policy honored. Every `gui/canvas.py`, `gui/worker_thread.py` (if reimplemented), `core/mask_editor.py`, `core/history_manager.py` task says "reimplement patterned after" MangaCleaner_GPU, never "vendor"/"copy". |
| Python / runtime | **Python 3.12**, deps managed by **uv** (fallback: pip+venv). `numpy<2.0` pin where onnxruntime/opencv ABI matters (deferred to ONNX backend). | PanelCleaner compiles to cpython-3.12; torch + PySide6 stable on 3.12. (RESEARCH §Standard Stack) |
| Test framework | **pytest + pytest-qt + pytest-mock**; `pytest.ini` created in skeleton (Wave 0); GUI smoke tests use `pytest-qt` fixtures; headless core tests run without a display. | RESEARCH §Validation Architecture; VALIDATION.md §Wave 0 Requirements. |
| Theme | **Single dark `QPalette` applied once at startup** (tokens: dominant `#232328`, canvas matte `#0b0b0e`, secondary `#2d2d33`, divider `#3a3a42`, accent `#00d4ff`, text primary `#e8e8ea`, text muted `#9a9aa2`). | UI-SPEC §Color. Applied via one `QApplication.setPalette()` call, not per-widget QSS. |

## Stack Touched in Phase 1 (Skeleton)

- [x] Project scaffold — `pyproject.toml`, `pytest.ini`, `.gitignore`, package `__init__.py` files, `manga_ai_studio/__main__.py` entry point
- [x] Routing / launch — `python -m manga_ai_studio` builds `QApplication`, loads the default `Profile`, shows `MainWindow`
- [x] Config — one real Profile read (default profile → `Config` materialization via `Config.from_config_updater`) AND one real write (`Profile.safe_write` round-trip in `tests/test_core/test_config.py`)
- [x] UI — one real interactive element wired end-to-end: File → Open Image (Ctrl+O) loads a PNG/JPG into `EditorCanvas`
- [x] Run command — `python -m manga_ai_studio` launches the window; `pytest` exits 0; `pytest --collect-only` exits 0

## Out of Scope (Deferred to Later Slices)

- **Pan/zoom, file-list sidebar, folder open, drag-drop, recent files** → Plan 02 (full canvas + sidebar)
- **CTD text detection, mask overlay, async worker subprocess** → Plan 03
- **Mask painting (brush/rectangle/lasso/eraser), tool panel** → Plan 04
- **LaMa inpainting, preview toggle** → Plan 05
- **Undo/redo (mask + image stacks)** → Plan 06
- ONNX backend concrete impl, packaging (PyInstaller), model-download wizard, OCR (Phase 4), text boxes (Phase 3), project save/export (Phase 5)

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering its architectural decisions:

- **Phase 1, Plans 02–06:** complete the cleaning workspace (full viewer → detection → mask editing → inpainting → undo/redo).
- **Phase 2:** export cleaned page (PNG/JPG) + batch chapter processing.
- **Phase 3:** text-box detection + select/move/resize/delete.
- **Phase 4:** manga-ocr recognition + inline text editing + manual translation.
- **Phase 5:** `.mas` project save/resume, image operations, `_ocr.json` export.

## Wave Constraint (shared-file serialization)

Plans 02–06 all modify the same two central files (`manga_ai_studio/gui/canvas.py` and
`manga_ai_studio/gui/main_window.py`). The GSD "zero `files_modified` overlap within a wave"
rule therefore forces **sequential waves** (01 → 02 → 03 → 04 → 05 → 06), not the parallel
Wave 2 originally sketched in ROADMAP. This is an inherent property of incrementally building
a single-canvas GUI, not a planning deficiency. Each plan's `wave` and `depends_on` reflect
this. Parallelism returns in later phases where features own distinct files.
