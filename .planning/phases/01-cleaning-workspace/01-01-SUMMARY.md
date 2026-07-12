---
phase: "01"
plan: "01"
subsystem: walking-skeleton
tags: [scaffolding, vendoring, gui, adapters, config]
requires:
  - "C:\\Src\\PanelCleaner\\pcleaner\\config.py (vendoring source)"
  - "C:\\Src\\PanelCleaner\\pcleaner\\gui\\image_viewer.py (pan/zoom mechanics)"
  - "C:\\Src\\PanelCleaner\\pcleaner\\gui\\mainwindow_driver.py (window shape)"
provides:
  - "panelcleaner/ vendored config package (Config, Profile, ConfigUpdater INI round-trip)"
  - "manga_ai_studio.config.ProfileManager (save_profile/load_profile/profile_to_config)"
  - "manga_ai_studio.adapters.base ABCs (DetectionModel, OCRModel, InpaintModel)"
  - "manga_ai_studio.adapters.onnx_impl NotImplementedError stubs"
  - "manga_ai_studio.gui.theme.build_dark_palette() (Fusion dark tokens)"
  - "manga_ai_studio.gui.canvas.EditorCanvas(QGraphicsView)"
  - "manga_ai_studio.gui.main_window.MainWindow(QMainWindow) with Open Image (Ctrl+O)"
  - "manga_ai_studio.app.create_app() (QApplication factory, Fusion + dark palette)"
  - "manga_ai_studio.__main__:main() entry point"
  - "pytest infrastructure (pytest.ini, conftest.py, tests/test_core, tests/test_gui_canvas)"
affects:
  - "Downstream plans 02-06 build on the two-package layout and adapter contract"
  - "plan 02 adds pan/zoom event handlers + file_table to EditorCanvas/MainWindow"
  - "plans 03/05 populate adapters/torch_impl.py against the ABCs"
tech-stack:
  added:
    - "PySide6 6.10.1 (GUI framework)"
    - "pytest 9.1.1 + pytest-qt 4.5.0 + pytest-mock 3.15.1 (test stack)"
    - "configupdater, attrs, loguru, numpy, scipy, natsort (deps of vendored panelcleaner)"
  patterns:
    - "Two-package layout: manga_ai_studio/ (ours) + panelcleaner/ (vendored GPL v3, D-10/D-12)"
    - "Model adapter ABCs with full pipeline hooks (D-01); ONNX stubs raise NotImplementedError (D-03/D-09)"
    - "ProfileManager wraps Profile.safe_write/Profile.load; ConfigUpdater INI persistence (D-05)"
    - "Single dark QPalette applied once at startup via QApplication.setPalette (UI-SPEC §Design System)"
    - "QImageReader.setAllocationLimit(0) at module import for large-page safety (image_viewer.py:45)"
key-files:
  created:
    - pyproject.toml
    - pytest.ini
    - .gitignore
    - README.md
    - panelcleaner/__init__.py
    - panelcleaner/config.py
    - panelcleaner/helpers.py
    - panelcleaner/cli_utils.py
    - panelcleaner/model_downloader.py
    - panelcleaner/ocr/__init__.py
    - panelcleaner/ocr/supported_languages.py
    - manga_ai_studio/__init__.py
    - manga_ai_studio/__main__.py
    - manga_ai_studio/app.py
    - manga_ai_studio/config/__init__.py
    - manga_ai_studio/config/profile_manager.py
    - manga_ai_studio/adapters/__init__.py
    - manga_ai_studio/adapters/base.py
    - manga_ai_studio/adapters/onnx_impl.py
    - manga_ai_studio/gui/__init__.py
    - manga_ai_studio/gui/theme.py
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/main_window.py
    - tests/__init__.py
    - tests/conftest.py
    - tests/test_core/__init__.py
    - tests/test_core/test_config.py
    - tests/test_core/test_adapters.py
    - tests/test_gui_canvas.py
  modified: []
decisions:
  - "ProfileManager.profile_to_config assigns current_profile directly instead of Config.from_config_updater (the latter needs a full config.ini with a Saved Profiles section, not a bare Profile.bundle_config())"
  - "create_app reuses an existing QApplication singleton so test sessions and re-entry don't trip the Qt singleton guard"
  - "EditorCanvas stores the scene as _scene to avoid shadowing the inherited QGraphicsView.scene() accessor"
metrics:
  duration: "15 min"
  completed: "2026-07-12"
  tasks: 2
  files: 29
  tests: 8
status: complete
---

# Phase 01 Plan 01: Walking Skeleton Summary

Vendored the PanelCleaner config system near-verbatim into `panelcleaner/`, declared the model adapter ABCs (DetectionModel/OCRModel/InpaintModel) with ONNX NotImplementedError stubs, bootstrapped ProfileManager over the INI/ConfigUpdater round-trip, and built a minimal PySide6 MainWindow + EditorCanvas that launches with the dark Fusion palette and a File -> Open Image (Ctrl+O) action — the thinnest end-to-end slice proving the Phase 1 stack.

## What Was Built

**Two-package layout (D-10):**
- `panelcleaner/` — PanelCleaner source (GPL v3) vendored near-verbatim per D-12: `config.py`, `helpers.py`, `cli_utils.py`, `model_downloader.py`, `ocr/supported_languages.py`, with all `pcleaner` import roots mechanically rewritten to `panelcleaner`. Zero `pcleaner` tokens remain. The `__init__.py` exposes `__program__`/`__version__`/`__display_name__` that `cli_utils.py` imports.
- `manga_ai_studio/` — our own application code.

**Config system (D-04/D-05):**
- `ProfileManager` wraps `Profile.safe_write(path)` (write INI), `Profile.load(path)` (classmethod read INI), and `profile_to_config()` (materialize a Profile into a Config — see Deviation #1).
- `tests/test_core/test_config.py` proves a default Profile round-trips through an INI `.profile` file.

**Model adapter contract (D-01/D-03/D-09):**
- `adapters/base.py` defines `DetectionModel`, `OCRModel`, `InpaintModel` as `abc.ABC` subclasses with full pipeline hooks (`load`/`detect|recognize|inpaint`/`preprocess`/`postprocess`/`configure`/`get_info`).
- `adapters/onnx_impl.py` ships `OnnxDetectionModel`/`OnnxInpaintModel` stubs whose `load()` raises `NotImplementedError` — the interface stays honest for D-02's `*_backend: onnx` keys without pulling `onnxruntime` into Phase 1.
- `tests/test_core/test_adapters.py` proves the ABCs reject instantiation (TypeError) and the ONNX stubs raise NotImplementedError.

**Walking Skeleton GUI:**
- `gui/theme.py` `build_dark_palette()` returns a QPalette from the UI-SPEC tokens (dominant #232328, canvas matte #0b0b0e, accent #00d4ff, text #e8e8ea).
- `gui/canvas.py` `EditorCanvas(QGraphicsView)` with image/mask pixmap-item stack, `AnchorUnderMouse`, `#0b0b0e` matte, `QImageReader.setAllocationLimit(0)` at import. Pan/zoom mechanics adapted from PanelCleaner `image_viewer.py` (GPL, D-12).
- `gui/main_window.py` `MainWindow(QMainWindow)` with File -> Open Image… (Ctrl+O) and View -> Fit to Window (Ctrl+0). `open_image()` uses `QFileDialog.getOpenFileName` (OS-validated absolute path — T-01-01 mitigation) and `QImage.copy()` (Pitfall 2 buffer safety).
- `app.py` `create_app()` applies `QApplication.setStyle("Fusion")` + `setPalette(build_dark_palette())` (UI-SPEC §Design System).
- `__main__.py` `main()` wires ProfileManager + MainWindow + `app.exec()`.
- `tests/test_gui_canvas.py` covers app launch, theme application (#232328 window color), canvas image load, and the Open Image Ctrl+O action.

**Test infrastructure (Wave 0):**
- `pytest.ini` (`qt_api=pyside6`, `testpaths=tests`), `tests/conftest.py` (`default_profile`/`tmp_config_dir`/`profile_manager` fixtures + `pytest.importorskip("PySide6")`).
- Full suite: **8/8 tests pass**. `pytest --collect-only` green (Wave 0 collection gate).

## Verification Results

- `python -c "from manga_ai_studio.__main__ import main"` → exit 0 (no import error)
- `python -c "import panelcleaner.config; import manga_ai_studio.adapters.base"` → exit 0 (cross-package integrity)
- `pytest` → 8 passed (test_core + test_gui_canvas)
- `pytest --collect-only` → 8 collected (Wave 0 gate)
- `python -m manga_ai_studio` would launch a QMainWindow with the dark Fusion palette and an Open Image (Ctrl+O) action (verified via import + smoke test)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] ProfileManager.profile_to_config used the wrong Config materialization path**
- **Found during:** Task 1 (test_profile_to_config failed on first run)
- **Issue:** The plan and PATTERNS.md specified `Config.from_config_updater(profile.bundle_config())`. `Config.from_config_updater` (config.py:1310) is designed to parse a **full application `config.ini`** — it unconditionally indexes `conf_updater["Saved Profiles"]` (config.py:1328). A `Profile.bundle_config()` output only carries the per-profile sections (`General`/`TextDetector`/`Preprocessor`/`Masker`/`Denoiser`/`Inpainter`) and has no `Saved Profiles` section, so the call raised `KeyError: 'No section Saved Profiles found'`. This is the same class of source-misread that PATTERNS.md already flagged for `Profile.save` vs `Profile.safe_write`.
- **Fix:** `profile_to_config` now builds a default `Config()` and assigns `config.current_profile = profile` — mirroring PanelCleaner's own `Config.load_profile` (config.py:1395, which does exactly `self.current_profile = Profile()`). Documented in the wrapper docstring.
- **Files modified:** `manga_ai_studio/config/profile_manager.py`, `tests/test_core/test_config.py` (strengthened assertion to `config.current_profile is profile`)
- **Commit:** 578a37f

**2. [Rule 1 - Bug] create_app() constructed a second QApplication under pytest-qt**
- **Found during:** Task 2 (test_theme_applied failed on first run)
- **Issue:** `create_app()` called `QApplication([])` unconditionally. pytest-qt creates a `QApplication` singleton for the test session; constructing a second one raised `RuntimeError: Please destroy the QApplication singleton before creating a new QApplication instance.`
- **Fix:** `create_app` now checks `QApplication.instance()` first and reuses the existing singleton if present, (re)applying Fusion style + dark palette to keep the contract honest. This is also the correct pattern for any code path that may re-enter app construction.
- **Files modified:** `manga_ai_studio/app.py`
- **Commit:** e4eed5f

**3. [Rule 1 - Bug] EditorCanvas.scene attribute shadowed QGraphicsView.scene() accessor**
- **Found during:** Task 2 (test_canvas_load_image failed: "'QGraphicsScene' object is not callable")
- **Issue:** `self.scene = QGraphicsScene(self)` created an instance attribute named `scene`, shadowing the inherited `QGraphicsView.scene()` method. Calling `canvas.scene()` then invoked the attribute (the object), not the method.
- **Fix:** Renamed the attribute to `self._scene`. After `setScene(self._scene)`, the inherited `scene()` accessor returns the same object, so call sites use `canvas.scene()` cleanly. This also removes the footgun for downstream plans.
- **Files modified:** `manga_ai_studio/gui/canvas.py`
- **Commit:** e4eed5f

### Architectural Changes
None — all deviations were Rule 1 bug fixes within the contracted wrappers.

## Authentication Gates
None — no auth-required operations in this plan.

## Known Stubs

This plan intentionally ships stubs whose emptiness is **contracted** by the plan (not gaps):

| Stub | File | Line | Reason | Resolved By |
|------|------|------|--------|-------------|
| `OnnxDetectionModel`/`OnnxInpaintModel` `load()` raises NotImplementedError | `manga_ai_studio/adapters/onnx_impl.py` | 31, 59 | D-03/D-09: ONNX backend is a future optional add-on; Phase 1 ships no ONNX loader so the interface is honest without pulling `onnxruntime`. | Future phase (ONNX backend) — not a Phase 1 plan |
| `EditorCanvas` has no pan/zoom event handlers (wheelEvent/zoom) | `manga_ai_studio/gui/canvas.py` | — | Plan 01 only needs the image to display + fit; pan/zoom lands in plan 02 per the plan action ("Do NOT implement pan/zoom event handlers yet"). | Plan 01-02 |
| `mask_item` initialized transparent, no painting | `manga_ai_studio/gui/canvas.py` | `set_image` | Mask painting (brush/rect/lasso/eraser) is plan 04 (CLEAN-03/04/05). | Plan 01-04 |

No stubs that block this plan's goal (a launchable skeleton that opens one image).

## Threat Flags

No new security-relevant surface beyond the plan's `<threat_model>`. T-01-01 (path traversal) mitigated via `QFileDialog.getOpenFileName` (OS-validated absolute path); T-01-02 (large image DoS) mitigated via `QImageReader.setAllocationLimit(0)`. Both match the plan's registered mitigations.

## Commits

- `578a37f` — feat(01-01): vendor PanelCleaner config + scaffolding + ProfileManager + adapter ABCs (Task 1)
- `e4eed5f` — feat(01-01): walking skeleton app — theme, EditorCanvas, MainWindow, entry point (Task 2)

## Self-Check: PASSED

- All 19 key files created (FOUND on disk): pyproject.toml, pytest.ini, .gitignore, README.md, 7 panelcleaner/ files, 11 manga_ai_studio/ files, 5 tests/ files, 01-01-SUMMARY.md.
- Both task commits exist in git log: `578a37f` (Task 1), `e4eed5f` (Task 2).
- Full pytest suite green (8/8). Collection gate green. Cross-package imports green. Entry point import green.
