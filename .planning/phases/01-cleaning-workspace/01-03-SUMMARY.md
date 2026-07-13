---
phase: "01"
plan: "03"
subsystem: text-detection
tags: [ctd, torch, comic-text-detector, detection-adapter, worker-thread, async, mask-overlay, gpl]
requires:
  - "manga_ai_studio.adapters.base DetectionModel ABC (plan 01-01)"
  - "manga_ai_studio.adapters.onnx_impl OnnxDetectionModel stub (plan 01-01)"
  - "manga_ai_studio.gui.canvas.EditorCanvas (plan 01-02 image/mask item stack + zoom_changed)"
  - "manga_ai_studio.gui.main_window.MainWindow (plan 01-02 menu/shell shell + Detect Text D action stub)"
  - "C:\\Src\\PanelCleaner\\pcleaner\\comic_text_detector\\ (vendoring source, GPL v3)"
  - "C:\\Src\\PanelCleaner\\pcleaner\\gui\\worker_thread.py (vendoring source, GPL v3)"
provides:
  - "panelcleaner.comic_text_detector vendored package (GPL v3): inference.TextDetector (__call__ returns VERIFIED 3-tuple mask, mask_refined, blk_list at inference.py:210), basemodel, utils.textmask (REFINEMASK_ANNOTATION/INPAINT), utils.textblock.TextBlock, utils.imgproc_utils/io_utils/db_utils/yolov5_utils, models/yolov5/*"
  - "manga_ai_studio.adapters.torch_impl.TorchCTDModel(DetectionModel): load (lazy torch, FileNotFoundError on missing path T-01-04), detect (3-tuple unpack with refine_mode=REFINEMASK_ANNOTATION, keep_undetected_mask=True), preprocess/postprocess/configure/get_info"
  - "manga_ai_studio.adapters.factory.backend_factory(kind, backend) -> DetectionModel|OCRModel|InpaintModel (lazy concrete imports; detection/torch -> TorchCTDModel, detection/onnx -> OnnxDetectionModel)"
  - "manga_ai_studio.gui.worker_thread.Worker(QRunnable), WorkerSignals, WorkerError, SharableFlag, Abort (vendored from PanelCleaner GPL)"
  - "manga_ai_studio.gui.canvas.EditorCanvas (extended): set_mask(qimage) with rgba(255,0,0,0.63) tint + .copy() buffer discipline, toggle_mask_overlay, has_mask, clear_mask, _mask_visible state"
  - "manga_ai_studio.gui.main_window.MainWindow (extended): detect_text (D) async via Worker on QThreadPool, _run_detection_task, _on_detection_finished/progress/error/cleanup, _confirm_replace_mask, #7a1f1f error chip, 3px progress bar, _op_running flag, _refresh_action_states"
affects:
  - "plan 04 (mask editing) wires mask painting tools onto EditorCanvas; consumes the detected mask as the editing starting point; Clear Mask action now has a canvas.clear_mask target"
  - "plan 05 (inpaint) reuses the Worker(QRunnable) dispatch pattern and the _op_running/error-chip status-bar infrastructure for the Inpaint (C) action"
  - "plan 06 (undo/redo) wires mask undo (Alt+Z) which the replace-mask confirmation references"
tech-stack:
  added:
    - "torch 2.10.0+cu130 (lazy-imported inside TorchCTDModel.load only; adapter module importable without it per D-07)"
    - "cv2 4.13.0 (image read in _run_detection_task; already a PanelCleaner dep)"
  patterns:
    - "3-tuple contract enforcement: TorchCTDModel.detect unpacks EXACTLY 3 values (mask, mask_refined, blk_list) from TextDetector.__call__ (inference.py:210) — NOT the 5-tuple claimed in CONTEXT.md/RESEARCH.md; a regression guard test (test_3_tuple_unpack_contract) locks this"
    - "Lazy torch import inside load() (D-07): the adapter module imports cleanly without torch; torch is only pulled when a model is actually loaded"
    - "Worker(QRunnable) async dispatch (vendored PanelCleaner GPL): worker touches only numpy/Python + emits signals; ALL Qt mutation in main-thread signal handlers (T-01-07 thread-safety)"
    - "Backend factory with lazy concrete imports (D-02): backend_factory resolves (kind, backend) without importing torch/onnxruntime at factory-import time"
    - "QImage BGRA byte-order awareness: set_mask builds the tinted overlay array in BGRA order (Qt ARGB32 little-endian) so red = [0,0,255,160] not [255,0,0,160]; copy-detaches numpy buffers before pixmap attachment (Pitfall 2)"
key-files:
  created:
    - panelcleaner/comic_text_detector/__init__.py
    - panelcleaner/comic_text_detector/inference.py
    - panelcleaner/comic_text_detector/basemodel.py
    - panelcleaner/comic_text_detector/LICENSE
    - panelcleaner/comic_text_detector/models/__init__.py
    - panelcleaner/comic_text_detector/models/yolov5/__init__.py
    - panelcleaner/comic_text_detector/models/yolov5/common.py
    - panelcleaner/comic_text_detector/models/yolov5/yolo.py
    - panelcleaner/comic_text_detector/utils/__init__.py
    - panelcleaner/comic_text_detector/utils/textmask.py
    - panelcleaner/comic_text_detector/utils/textblock.py
    - panelcleaner/comic_text_detector/utils/imgproc_utils.py
    - panelcleaner/comic_text_detector/utils/io_utils.py
    - panelcleaner/comic_text_detector/utils/db_utils.py
    - panelcleaner/comic_text_detector/utils/yolov5_utils.py
    - panelcleaner/comic_text_detector/utils/weight_init.py
    - panelcleaner/comic_text_detector/utils/loss.py
    - panelcleaner/comic_text_detector/utils/export.py
    - panelcleaner/comic_text_detector/utils/general.py
    - panelcleaner/comic_text_detector/README.md
    - manga_ai_studio/adapters/torch_impl.py
    - manga_ai_studio/adapters/factory.py
    - manga_ai_studio/gui/worker_thread.py
    - tests/test_detection/__init__.py
    - tests/test_detection/test_ctd_adapter.py
  modified:
    - manga_ai_studio/adapters/__init__.py
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/main_window.py
    - pytest.ini
key-decisions:
  - "TextDetector.__call__ returns a VERIFIED 3-tuple (mask, mask_refined, blk_list) at inference.py:210, NOT the 5-tuple claimed in CONTEXT.md/RESEARCH.md — the orchestrator's pattern-mapper correction is authoritative; a 5-target unpack would raise ValueError"
  - "Vendored the FULL comic_text_detector tree (including models/yolov5/* and utils/weight_init.py, loss.py) even though the plan's files_modified listed a subset, because basemodel.py imports from .models.yolov5.common and .utils.weight_init — inference.py is unimportable without them (Rule 3 blocking fix; the plan's <action> text says 'Copy the full directory tree')"
  - "No pcleaner->panelcleaner rewrite was needed: the vendored tree uses relative imports exclusively (zero pcleaner references), so the copy is verbatim"
  - "set_mask composites the tint in numpy (BGRA byte order) rather than QPainter for speed on large pages; the red overlay is [0,0,255,160] in the array (B=0,G=0,R=255,A=160) because Qt ARGB32 stores BGRA on little-endian"
  - "Replace-mask confirmation uses custom QMessageBox buttons ([Cancel][Replace Mask]) because Qt's StandardButton enum has no Replace member; this preserves the UI-SPEC copy exactly"
  - "Detection runs in-process via QThreadPool (D-09b single-env fallback); the D-07/D-08 subprocess IPC split is deferred until a dependency conflict forces it"
patterns-established:
  - "3-tuple regression guard: test_3_tuple_unpack_contract uses a fake detector returning a 3-tuple to lock the unpack contract against the 5-tuple mistake"
  - "Worker signal ordering: progress -> result -> finished (tested in test_detection_worker_emits_result via qtbot.waitUntil)"
  - "Error chip pattern: _on_detection_error shows a persistent #7a1f1f QLabel in the status bar + a QMessageBox::Critical dialog; the full traceback goes to loguru only (T-01-08)"
  - "Action state refresh: _refresh_action_states gates Detect Text (page open + not _op_running) and Toggle Mask Overlay (canvas.has_mask) in one place"
requirements-completed:
  - CLEAN-02
coverage:
  - id: D1
    description: "TorchCTDModel adapter unpacks the TextDetector 3-tuple return (mask, mask_refined, blk_list) with refine_mode=REFINEMASK_ANNOTATION, keep_undetected_mask=True"
    requirement: "CLEAN-02"
    verification:
      - kind: unit
        ref: "tests/test_detection/test_ctd_adapter.py#test_3_tuple_unpack_contract"
        status: pass
      - kind: unit
        ref: "tests/test_detection/test_ctd_adapter.py#test_detect_raises_when_not_loaded"
        status: pass
      - kind: unit
        ref: "tests/test_detection/test_ctd_adapter.py#test_get_info_defaults"
        status: pass
      - kind: unit
        ref: "tests/test_detection/test_ctd_adapter.py#test_postprocess_thresholds_mask"
        status: pass
    human_judgment: false
  - id: D2
    description: "backend_factory resolves detection/torch -> TorchCTDModel and detection/onnx -> OnnxDetectionModel; rejects unknown combos with ValueError"
    requirement: "CLEAN-02"
    verification:
      - kind: unit
        ref: "tests/test_detection/test_ctd_adapter.py#test_factory_torch_detection"
        status: pass
      - kind: unit
        ref: "tests/test_detection/test_ctd_adapter.py#test_factory_onnx_detection_raises_on_load"
        status: pass
      - kind: unit
        ref: "tests/test_detection/test_ctd_adapter.py#test_factory_unknown_raises"
        status: pass
      - kind: unit
        ref: "tests/test_detection/test_ctd_adapter.py#test_factory_ocr_not_implemented"
        status: pass
      - kind: unit
        ref: "tests/test_detection/test_ctd_adapter.py#test_factory_inpainting_torch_not_implemented"
        status: pass
    human_judgment: false
  - id: D3
    description: "Model-load failure raises FileNotFoundError before any torch import (T-01-04 model weight tampering mitigation)"
    requirement: "CLEAN-02"
    verification:
      - kind: unit
        ref: "tests/test_detection/test_ctd_adapter.py#test_load_missing_model_raises_file_not_found"
        status: pass
    human_judgment: false
  - id: D4
    description: "Detect Text (D) runs CTD detection asynchronously via Worker(QRunnable) without freezing the UI; mask composited as rgba(255,0,0,0.63) overlay"
    requirement: "CLEAN-02"
    verification:
      - kind: integration
        ref: "tests/test_detection/test_ctd_adapter.py#test_detect_text_action_enabled_with_page"
        status: pass
      - kind: integration
        ref: "tests/test_detection/test_ctd_adapter.py#test_detection_worker_emits_result"
        status: pass
      - kind: integration
        ref: "tests/test_detection/test_ctd_adapter.py#test_set_mask_composites_overlay"
        status: pass
      - kind: integration
        ref: "tests/test_detection/test_ctd_adapter.py#test_toggle_mask_overlay"
        status: pass
    human_judgment: true
    rationale: "Async non-blocking UI feel + actual CTD model inference on a real page (requires model weight download ~100-200MB) is a manual verification per VALIDATION.md; the unit/integration tests prove the wiring with a mock detector, not a real model run."
  - id: D5
    description: "Replace-mask confirmation dialog shown when a mask already exists; model-load error shows #7a1f1f error chip + critical dialog"
    requirement: "CLEAN-02"
    verification:
      - kind: integration
        ref: "tests/test_detection/test_ctd_adapter.py#test_replace_mask_confirmation"
        status: pass
      - kind: integration
        ref: "tests/test_detection/test_ctd_adapter.py#test_detection_error_shows_chip"
        status: pass
    human_judgment: false
metrics:
  duration: "39 min"
  completed: "2026-07-13"
  tasks: 2
  files: 29
  tests: 17
status: complete
---

# Phase 01 Plan 03: Text Detection Slice Summary

Vendored PanelCleaner's `comic_text_detector/` (GPL v3) and wired async CTD text detection end-to-end: `TorchCTDModel(DetectionModel)` unpacks the VERIFIED 3-tuple `(mask, mask_refined, blk_list)` return (inference.py:210 — NOT the 5-tuple claimed in CONTEXT/RESEARCH), `backend_factory` resolves detection/torch vs detection/onnx, and Tools -> Detect Text (D) dispatches a `Worker(QRunnable)` that composites the detected mask as a `rgba(255,0,0,0.63)` overlay without freezing the UI, with a replace-mask confirmation and a persistent `#7a1f1f` error chip on model-load failure.

## Performance

- **Duration:** 39 min
- **Started:** 2026-07-13T02:27:02Z
- **Completed:** 2026-07-13T03:06:34Z
- **Tasks:** 2
- **Files modified:** 29 (25 created/modified in this plan + 4 test/config)

## Accomplishments

- Vendored the complete `panelcleaner/comic_text_detector/` tree (GPL v3, D-12) near-verbatim: `inference.py`, `basemodel.py`, `utils/*` (textmask, textblock, imgproc_utils, io_utils, db_utils, yolov5_utils, weight_init, loss), `models/yolov5/*`, and the LICENSE. Verified `TextDetector.__call__` returns the 3-tuple `(mask, mask_refined, blk_list)` at inference.py:210 — the load-bearing contract for the adapter.
- `TorchCTDModel(DetectionModel)` in `adapters/torch_impl.py`: `load()` validates the model path (FileNotFoundError, T-01-04) and imports torch lazily (D-07); `detect()` unpacks EXACTLY 3 values with `refine_mode=REFINEMASK_ANNOTATION, keep_undetected_mask=True`; plus `preprocess`/`postprocess`/`configure`/`get_info`.
- `backend_factory(kind, backend)` in `adapters/factory.py`: lazy concrete imports so the factory imports without torch; detection/torch -> TorchCTDModel, detection/onnx -> OnnxDetectionModel stub, ocr/inpainting-torch raise NotImplementedError (Phase 4 / plan 05); ValueError on unknown combos.
- Vendored `gui/worker_thread.py` (PanelCleaner GPL): `Worker(QRunnable)`, `WorkerSignals` (finished/error/result/progress/aborted), `WorkerError` (typed traceback), `SharableFlag`, `Abort`. Auto-injects `progress_callback`/`abort_flag`.
- `EditorCanvas.set_mask(qimage)`: tints non-zero mask pixels with `rgba(255,0,0,0.63)` (`QColor(255,0,0,160)`), copy-detaches numpy buffers (Pitfall 2); plus `toggle_mask_overlay`, `has_mask`, `clear_mask`, `_mask_visible` state.
- `MainWindow.detect_text` (D): async via `Worker` on `QThreadPool` (D-09b in-process fallback); replace-mask confirmation (`[Cancel][Replace Mask]`); `_on_detection_finished` composites the mask; `_on_detection_error` shows `QMessageBox::Critical` + persistent `#7a1f1f` error chip (traceback to loguru only, T-01-08); `_on_detection_progress` updates the status bar + 3px progress bar; Toggle Mask Overlay (M) wired.
- 17 detection tests green (11 adapter/factory unit tests + 6 GUI behavior tests); full suite 39 passed (22 prior + 17 new), no regressions.

## Task Commits

Each task was committed atomically:

1. **Task 1: Vendor comic_text_detector + TorchCTDModel adapter (3-tuple) + backend factory** - `5d78f17` (feat)
2. **Task 2: Async detection worker + mask overlay + Detect Text (D) wiring** - `c11e9ae` (feat)

## Files Created/Modified

- `panelcleaner/comic_text_detector/inference.py` - CTD TextDetector (PyTorch); `__call__` returns 3-tuple at :210
- `panelcleaner/comic_text_detector/utils/textmask.py` - REFINEMASK_ANNOTATION/INPAINT constants + refine_mask/refine_undetected_mask
- `panelcleaner/comic_text_detector/basemodel.py` + `models/yolov5/*` - model architecture (required by inference.py imports)
- `manga_ai_studio/adapters/torch_impl.py` - TorchCTDModel(DetectionModel) with the 3-tuple unpack
- `manga_ai_studio/adapters/factory.py` - backend_factory(kind, backend) lazy resolver
- `manga_ai_studio/adapters/__init__.py` - re-exports backend_factory
- `manga_ai_studio/gui/worker_thread.py` - vendored Worker(QRunnable)/WorkerSignals/WorkerError/Abort
- `manga_ai_studio/gui/canvas.py` - set_mask/toggle_mask_overlay/has_mask/clear_mask + _mask_visible
- `manga_ai_studio/gui/main_window.py` - detect_text (D) async dispatch + handlers + error chip + progress bar
- `tests/test_detection/test_ctd_adapter.py` - 17 tests (3-tuple guard, factory, GUI behaviors)
- `pytest.ini` - registered unit/gui markers

## Decisions Made

- **3-tuple over 5-tuple (authoritative correction):** `TextDetector.__call__` at inference.py:210 returns `return mask, mask_refined, blk_list` (3 values). CONTEXT.md/RESEARCH.md claim a 5-tuple `(img, mask, mask_refined, blk_list, refine_mode)` — that is incorrect; `img`/`refine_mode` are INPUTS, not returns. The orchestrator's pattern-mapper correction is binding. `TorchCTDModel.detect` unpacks exactly 3 targets; `test_3_tuple_unpack_contract` is the regression guard.
- **Full tree vendoring (Rule 3):** The plan's `files_modified` listed a subset of `comic_text_detector/` files, but `basemodel.py` imports `from .models.yolov5.common import C3, Conv` and `from .utils.weight_init import init_weights`. `inference.py` imports `basemodel`, so it is unimportable without `models/` and `utils/weight_init.py`. Vendored the complete tree (the plan's `<action>` text says "Copy the full directory tree" — the intent was always the full closure).
- **No import rewrite needed:** The vendored tree uses relative imports exclusively (zero `pcleaner` references), so the `pcleaner.->panelcleaner.` rewrite is a no-op; the copy is verbatim.
- **BGRA byte order for mask tint:** Qt ARGB32 on little-endian stores pixels in BGRA byte order, so the numpy overlay array uses `[0, 0, 255, 160]` for red (B=0, G=0, R=255, A=160), not `[255, 0, 0, 160]`.
- **Custom confirmation buttons:** Qt's `StandardButton` enum has no `Replace` member, so the replace-mask dialog uses `addButton("Replace Mask", AcceptRole)` + `addButton("Cancel", RejectRole)` to preserve the UI-SPEC `[Cancel] [Replace Mask]` copy.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Vendored the full comic_text_detector tree, not the subset in files_modified**
- **Found during:** Task 1 (vendoring — `inference.py` imports `basemodel.py` which imports `.models.yolov5.common` and `.utils.weight_init`)
- **Issue:** The plan's `files_modified` frontmatter lists `inference.py`, `basemodel.py`, `LICENSE`, and `utils/{__init__,textmask,textblock,imgproc_utils,io_utils,db_utils,yolov5_utils}.py` — but omits `models/yolov5/{common,yolo}.py`, `utils/weight_init.py`, `utils/loss.py`, `utils/export.py`, `utils/general.py`, `README.md`. `basemodel.py:7` imports `from .models.yolov5.common import C3, Conv` and `:9` `from .utils.weight_init import init_weights`; `inference.py:11` imports `from .basemodel import TextDetBase`. Without `models/` and `utils/weight_init.py`, `inference.py` is unimportable (acceptance criterion: "the verify command's 3-tuple assertion passes").
- **Fix:** Copied the complete `comic_text_detector/` directory tree from PanelCleaner (the plan's `<action>` text says "Copy the full directory tree from `C:\Src\PanelCleaner\pcleaner\comic_text_detector\`" — the full closure was always the intent).
- **Files modified:** `panelcleaner/comic_text_detector/models/__init__.py`, `models/yolov5/{__init__,common,yolo}.py`, `utils/{weight_init,loss,export,general}.py`, `README.md` (added beyond the files_modified list)
- **Verification:** `python -c "from panelcleaner.comic_text_detector.inference import TextDetector"` exits 0; the 3-tuple assertion passes.
- **Committed in:** `5d78f17` (Task 1 commit)

**2. [Rule 1 - Bug] set_mask used constBits().setsize() which does not exist on PySide6 memoryview**
- **Found during:** Task 2 (`test_set_mask_composites_overlay` failed: `AttributeError: 'memoryview' object has no attribute 'setsize'`)
- **Issue:** The first `set_mask` implementation called `ptr = src.constBits(); ptr.setsize(h*w*4)` — in PySide6, `constBits()` returns a `memoryview`, not the `sip.voidptr` it returns in PyQt5, so `.setsize()` does not exist.
- **Fix:** Changed to `np.frombuffer(bytes(src.constBits()), dtype=np.uint8).reshape(h, w, 4)` — materializing the memoryview to bytes before numpy consumes it (the source QImage is already `.copy()`-detached above, so the buffer is safe).
- **Files modified:** `manga_ai_studio/gui/canvas.py`
- **Verification:** `test_set_mask_composites_overlay` passes; the red tint pixel (R=255, A=160) is verified.
- **Committed in:** `c11e9ae` (Task 2 commit)

**3. [Rule 1 - Bug] set_mask tint array used RGB byte order instead of BGRA**
- **Found during:** Task 2 (`test_set_mask_composites_overlay` failed: `assert px.red() == 255` got `0` — pixel was blue, not red)
- **Issue:** The tinted overlay array set `out[mask_pixels] = [255, 0, 0, 160]` assuming RGB byte order. Qt ARGB32 on little-endian stores BGRA, so `[255, 0, 0, 160]` renders as blue (B=255). The mask-pixel detection also indexed `arr[:,:,2]` (R) correctly but the output was wrong.
- **Fix:** Output array now uses `[0, 0, 255, 160]` (B=0, G=0, R=255, A=160) for the red overlay in BGRA byte order.
- **Files modified:** `manga_ai_studio/gui/canvas.py`
- **Verification:** `test_set_mask_composites_overlay` passes; `px.red()==255`, `px.alpha()==160`.
- **Committed in:** `c11e9ae` (Task 2 commit)

**4. [Rule 1 - Bug] _confirm_replace_mask used QMessageBox.StandardButton.Replace which does not exist**
- **Found during:** Task 2 (`test_replace_mask_confirmation` failed: `AttributeError: type object 'StandardButton' has no attribute 'Replace'`)
- **Issue:** Qt's `QMessageBox.StandardButton` enum has no `Replace` member — the UI-SPEC `[Cancel] [Replace Mask]` copy cannot be rendered with standard buttons.
- **Fix:** Replaced `QMessageBox.question` with a custom `QMessageBox` using `addButton("Replace Mask", AcceptRole)` + `addButton("Cancel", RejectRole)`; returns True iff the clicked button is the replace button.
- **Files modified:** `manga_ai_studio/gui/main_window.py`, `tests/test_detection/test_ctd_adapter.py` (test updated to monkeypatch `QMessageBox.exec` instead of `question`)
- **Verification:** `test_replace_mask_confirmation` passes (True on Replace, False on Cancel, no dialog when no mask).
- **Committed in:** `c11e9ae` (Task 2 commit)

---

**Total deviations:** 4 auto-fixed (1 Rule 3 blocking, 3 Rule 1 bugs)
**Impact on plan:** All auto-fixes necessary for correctness (the full tree is required for importability; the PySide6 memoryview/BGRA/StandardButton fixes are PySide6-vs-PyQt5 API differences). No scope creep.

## Authentication Gates

None — no auth-required operations in this plan. The model weight download (user_setup in frontmatter) is triggered automatically by `panelcleaner.model_downloader` on first detection run; it is not an auth gate.

## Known Stubs

This plan intentionally ships stubs whose backing logic lands in later plans (contracted placeholders, not gaps):

| Stub | File | Line | Reason | Resolved By |
|------|------|------|--------|-------------|
| `TorchLamaModel(InpaintModel)` not implemented | `manga_ai_studio/adapters/torch_impl.py` | module comment | LaMa inpainting is plan 05 (CLEAN-06). A `# TorchLamaModel(InpaintModel) is implemented in plan 05` comment marks the slot. | Plan 01-05 |
| `backend_factory("inpainting", "torch")` raises NotImplementedError | `manga_ai_studio/adapters/factory.py` | inpainting branch | Inpainting torch adapter lands in plan 05. | Plan 01-05 |
| `backend_factory("ocr", ...)` raises NotImplementedError | `manga_ai_studio/adapters/factory.py` | ocr branch | OCR adapter lands in Phase 4. | Phase 4 |
| Tools menu Inpaint (C) + mask tools (V/B/R/L/E) still `setEnabled(False)` | `manga_ai_studio/gui/main_window.py` | `_build_tools_menu` | Inpaint is plan 05; mask editing tools are plan 04. The Detect Text (D) action is now enabled (this plan). | Plans 01-04, 01-05 |
| `dock_tools` still holds the placeholder QLabel | `manga_ai_studio/gui/main_window.py` | `_build_docks` | The real Tools panel (brush size slider, tool buttons) is plan 04. | Plan 01-04 |
| `EditorCanvas` has no mask painting (brush/rect/lasso/eraser) | `manga_ai_studio/gui/canvas.py` | — | Mask painting is plan 04; this plan only adds set_mask (detection overlay display). | Plan 01-04 |

No stubs that block this plan's goal (run CTD detection and see the mask overlay).

## Threat Flags

No new security-relevant surface beyond the plan's `<threat_model>`. All three registered threats mitigated as specified:

- **T-01-04 (model weight tampering):** `TorchCTDModel.load` validates `model_path.is_file()` and raises `FileNotFoundError` BEFORE constructing `TextDetector` (the PanelCleaner `inpainting.py:21` pattern). `test_load_missing_model_raises_file_not_found` is the guard. The vendored `model_downloader.fetch` uses sha256 verification on download (PATTERNS.md §model_downloader).
- **T-01-07 (thread-safety crash):** The worker (`_run_detection_task`) touches only numpy/Python + the adapter and emits signals; ALL Qt mutation happens in main-thread signal handlers (`_on_detection_finished`/`_on_detection_error`/`_on_detection_progress`). `detect()` returns plain numpy arrays, never QImage/QPixmap. Verified by `test_detection_worker_emits_result`.
- **T-01-08 (traceback leakage):** `WorkerError` carries the full traceback but `_on_detection_error` shows only user-friendly copy ("Couldn't load the detection model.") in the `QMessageBox`; the full traceback goes to `loguru` (`logger.error`). Verified by the error-chip test (the dialog is monkeypatched, confirming the handler path).

## Commits

- `5d78f17` — feat(01-03): vendor comic_text_detector + TorchCTDModel adapter (3-tuple) + backend factory (Task 1)
- `c11e9ae` — feat(01-03): async detection worker + mask overlay + Detect Text (D) wiring (Task 2)

## Self-Check: PASSED

- All 29 key files FOUND on disk: 20 `panelcleaner/comic_text_detector/` files, `adapters/torch_impl.py`, `adapters/factory.py`, `adapters/__init__.py` (modified), `gui/worker_thread.py`, `gui/canvas.py` (modified), `gui/main_window.py` (modified), `tests/test_detection/{__init__,test_ctd_adapter}.py`, `pytest.ini` (modified).
- Both task commits FOUND in git log: `5d78f17` (Task 1), `c11e9ae` (Task 2).
- Plan `<verification>`: `pytest tests/test_detection/ -x` exits 0 (17 passed).
- 3-tuple regression guard PASSED (vendored `inference.py` still returns `mask, mask_refined, blk_list`).
- No 5-target unpack of `self.detector(` in `torch_impl.py` (grep confirms only the 3-target line).
- Full suite 39 passed (22 prior + 17 new). No regressions vs plans 01-01/01-02.
