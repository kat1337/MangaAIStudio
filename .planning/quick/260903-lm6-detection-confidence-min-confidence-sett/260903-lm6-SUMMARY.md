---
status: complete
phase: quick-260903-lm6
plan: 01
subsystem: detection-confidence
tags: [detection, confidence, gui, persistence, vendored-deviation]
requires: []
provides:
  - "PageBox.confidence (per-box detector confidence, [0,1] or None)"
  - "MaskerConfig.detection_conf_thresh (user-facing Min confidence, 0.05..0.95)"
  - "configure(conf_thresh=...) at all three det-model creation sites"
affects:
  - manga_ai_studio/core/box_model.py
  - manga_ai_studio/core/detection_boxes.py
  - manga_ai_studio/core/project_io.py
  - panelcleaner/config.py
  - manga_ai_studio/gui/tools_panel.py
  - manga_ai_studio/gui/inspector_panel.py
tech-stack:
  added: []
  patterns:
    - "getattr-with-default tolerance for legacy configs (max_inpaint_resolution precedent)"
    - "optional-key .mas persistence (std_dev precedent)"
key-files:
  created: []
  modified:
    - panelcleaner/comic_text_detector/utils/textblock.py
    - manga_ai_studio/core/box_model.py
    - manga_ai_studio/core/detection_boxes.py
    - manga_ai_studio/core/project_io.py
    - panelcleaner/config.py
    - manga_ai_studio/core/batch_runner.py
    - manga_ai_studio/gui/main_window.py
    - manga_ai_studio/gui/tools_panel.py
    - manga_ai_studio/gui/inspector_panel.py
    - tests/test_core/conftest.py
    - tests/test_gui_detection_boxes.py
decisions:
  - "Confidence normalization range rule locked: 0..1 passes through; -1.0 scattered sentinel and missing attr normalize to None; upstream prob=1 default would land as 1.0 (documented, unreachable through our group_output deviation sites)"
  - "Scattered-line blocks carry a -1.0 prob sentinel in the vendored group_output so unknown never masquerades as the upstream prob=1 default"
  - "Min confidence joins the shared masker_params_changed persistence fate; key detection_conf_thresh equals the MaskerConfig field name so MainWindow's setattr loop picks it up unchanged"
  - "Inspector Confidence row is a pure Std-dev mirror: muted QSS label, em dash when unknown, reset on clear() and on multi-selection"
metrics:
  duration: ~55 min
  completed: 2026-09-03
  tasks: 3
  commits: 3
---

# Quick Task 260903-lm6: Detection confidence — Min-confidence setting + per-box Inspector value Summary

Min-confidence spinbox (0.05-0.95) drives the CTD detector's conf_thresh on the next Detect Text (interactive + batch); every detected box carries its YOLO confidence through PageBox/.mas and shows it as a percentage in the Inspector (em dash when unknown).

## Per-Task Outcomes

### Task 1: Capture per-box confidence (commit 713293e)

- Vendored `group_output` (panelcleaner/comic_text_detector/utils/textblock.py): YOLO blocks now get `blk.prob = float(conf)`; the fresh scattered-line block gets the `-1.0` "unknown" sentinel — both with the specified `# Manga AI Studio deviation (quick-260903-lm6)` comments. `TextBlock.__init__` default untouched.
- `PageBox.confidence: Optional[float] = None` added after `fill_color` (copy() survival free via dataclasses.replace).
- `build_detected_pageboxes` normalizes `blk.prob` under the locked range rule (0..1 passes; -1.0/missing -> None) with a documenting comment.
- `pagebox_to_json`/`json_to_pagebox`: additive "confidence" key both directions; float-coerced on load with `ProjectFormatError("confidence must be a number")` on garbage; legacy files without the key load None.
- Verify: tests/test_core/test_detection_boxes.py + test_project_io.py + test_box_persistence.py — 70 passed.

### Task 2: Min-confidence plumbing (commit 655f09e)

- `MaskerConfig.detection_conf_thresh: float = 0.4` (marked vendoring addition), INI export comment + `try_to_load` import, `fix()` float-coerce (fallback 0.4) + clamp 0.05..0.95 — all mirroring the `max_inpaint_resolution` precedent.
- `batch_detect` and `batch_detect_and_clean` call `det_model.configure(conf_thresh=float(getattr(masker_conf, "detection_conf_thresh", 0.4)))` immediately before `det_model.load(...)`.
- Interactive `detect_text()` configures the fresh adapter after `backend_factory(...)` and before the Worker spawn (load happens inside the worker).
- ONNX untouched (stub, out of scope).
- Verify: test_masker_config_roundtrip.py + test_batch_runner.py + test_adapters.py — 33 passed.

### Task 3: GUI surfaces (commit 0760f4f)

- `DetectionSettingsBody`: "Min confidence" QDoubleSpinBox (0.05..0.95, step 0.05, 2 decimals, default 0.40, no wrapping) with the specified tooltip, wired into `_on_fit_param_changed`; `masker_values()` emits the `detection_conf_thresh` key; `set_masker_values()` populates under blockSignals with the getattr-0.4 tolerance; "seven" -> "eight" docstrings updated.
- `InspectorPanel`: `QLabel#confidenceLabel` QSS token, read-only "Confidence" row after Std dev with tooltip, `_set_confidence_text` (`f"{v:.0%}"` / em dash), loaded in `load_box`, reset in `clear()` and multi-selection, joined the std_dev_label enable/disable list.
- Verify: test_gui_detection_settings.py + test_gui/test_inspector_override.py + test_detection_settings_tooltip.py + test_tools_panel_masker.py — 50 passed.

## Test Results

- Task-targeted suites: 70 / 33 / 50 passed (Tasks 1/2/3).
- Full suite: **1273 passed, 0 failed** (~3m40s) with the pinned interpreter. All new tests green; nothing pre-existing broke.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fake detection adapters gained configure()**
- **Found during:** Task 2
- **Issue:** batch_runner now calls `det_model.configure(...)` unconditionally, but the test fakes lacked the method — every existing batch test would raise AttributeError.
- **Fix:** Added a kwargs-recording `configure(**kwargs)` to `FakeDetectionModel` (tests/test_core/conftest.py — the plan's specified home) and to `_FixtureDetector` (tests/test_core/test_batch_runner.py) which the plan's list did not name but which also flows through batch_detect.
- **Files modified:** tests/test_core/conftest.py, tests/test_core/test_batch_runner.py
- **Commit:** 655f09e

**2. [Rule 3 - Blocking] backend_factory stub in test_detection_dispatch_stamps_target_page**
- **Found during:** Task 2
- **Issue:** tests/test_gui_detection_boxes.py monkeypatched `backend_factory` to return `None`; interactive detect_text() now calls `model.configure(...)` before the worker spawn, breaking this test.
- **Fix:** The stub now returns a `SimpleNamespace(configure=..., load=...)`; test intent (Worker fully faked, dispatch stamping) unchanged.
- **Files modified:** tests/test_gui_detection_boxes.py
- **Commit:** 655f09e

**3. [Rule 1 - Correctness] Confidence resets on multi-selection**
- **Found during:** Task 3
- **Issue:** The plan listed load_box/clear() resets; the multi-selection path (which sets Std dev to the em dash) would have left a stale single-box confidence displayed.
- **Fix:** `_set_confidence_text(None)` added to the multi-selection population, mirroring the Std dev precedent exactly; covered by test_confidence_row_multiselect_shows_em_dash.
- **Files modified:** manga_ai_studio/gui/inspector_panel.py, tests/test_gui/test_inspector_override.py
- **Commit:** 0760f4f

## Vendored-File Discipline

- panelcleaner/comic_text_detector/utils/textblock.py: exactly the two prob assignments in group_output, each with the required deviation comment; no other vendored behavior change.
- panelcleaner/config.py: only the MaskerConfig field + export_to_conf template line + import_from_conf try_to_load + fix() clamp, matching the max_inpaint_resolution vendoring pattern.

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | 713293e | feat(quick-260903-lm6): capture per-box detector confidence on PageBox + .mas persistence |
| 2 | 655f09e | feat(quick-260903-lm6): wire Min confidence setting into MaskerConfig and all detect paths |
| 3 | 0760f4f | feat(quick-260903-lm6): Min confidence spinbox + Inspector Confidence row |

## Self-Check: PASSED

- All modified files committed; `git log` confirms 713293e / 655f09e / 0760f4f on master.
- Full suite 1273 passed / 0 failed after Task 3.
- Grep sanity: detection_conf_thresh defined in panelcleaner/config.py, exported/imported/clamped, configured at batch_runner.py:433/:520 and main_window.py:5313, keyed in tools_panel.py masker_values.
