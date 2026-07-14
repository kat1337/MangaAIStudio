---
phase: 01-cleaning-workspace
plan: 05
subsystem: ui
tags: [pyside6, lama, inpainting, torch, numpy, qimage, worker-thread, gpl-v3]

# Dependency graph
requires:
  - phase: 01-cleaning-workspace (plans 01-04)
    provides: backend_factory + InpaintModel ABC (plan 01), Worker(QRunnable) + QThreadPool dispatch (plan 03), mask_to_numpy_binary (plan 04), EditorCanvas image/mask stack (plans 01/04)
provides:
  - TorchLamaModel(InpaintModel) adapter wrapping vendored SimpleLama with size-reclamp + binary-mask contract
  - backend_factory('inpainting','torch') -> TorchLamaModel (was NotImplementedError in plan 03)
  - panelcleaner.inpainting.InpaintingModel vendored minimally (InpaintingModel class only; batch inpaint_page deferred to Phase 2)
  - panelcleaner.image_ops vendored (mask<->RGBA conversions; Pitfall 6 centralization)
  - EditorCanvas numpy bridge: get_image_numpy / set_image_from_numpy / show_original / has_inpaint_result / has_mask_content (all with MANDATORY .copy() at numpy<->QImage boundaries)
  - MainWindow.inpaint() async worker dispatch + result/error/progress handlers + history.push_image_action hook (plan 06) + Preview(hold) + sticky-P toggle
  - compute_mask_bbox(mask_binary) -> (x,y,w,h) pure-numpy helper
affects: [01-cleaning-workspace plan 06 (history/undo consumes push_image_action), Phase 2 FLOW-03 (batch inpaint_page)]

# Tech tracking
tech-stack:
  added: [simple_lama_inpainting (lazy-imported in TorchLamaModel.load only), scipy (already declared by plan 01; transitive dep of vendored image_ops.py)]
  patterns:
    - "Worker(QRunnable) dispatch: GUI thread extracts numpy arrays BEFORE dispatch; worker touches only numpy/PIL + adapter; all Qt mutation in main-thread signal handlers (Pitfall 3)"
    - "QImage .copy() buffer discipline at EVERY numpy<->QImage bridge (Pitfall 2; MangaCleaner_GPU main_window.py:245 is the buggy reference we do NOT copy)"
    - "Lazy import discipline: SimpleLama/torch imported inside TorchLamaModel.load() only; module importable without them (D-07)"
    - "Vendoring split: PanelCleaner (GPL v3) near-verbatim; MangaCleaner_GPU reference-only (no LICENSE)"

key-files:
  created:
    - panelcleaner/inpainting.py
    - panelcleaner/image_ops.py
    - panelcleaner/data/__init__.py
    - panelcleaner/structures.py
    - tests/test_inpainting/__init__.py
    - tests/test_inpainting/test_lama_adapter.py
    - tests/test_inpainting/test_inpaint_gui.py
  modified:
    - manga_ai_studio/adapters/torch_impl.py
    - manga_ai_studio/adapters/factory.py
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_detection/test_ctd_adapter.py

key-decisions:
  - "Vendored inpainting.py MINIMALLY: only the InpaintingModel class (load + __call__); the batch inpaint_page driver and its MaskData/PageData deps are deferred to Phase 2 (FLOW-03) per the plan's explicit prohibition."
  - "Vendored image_ops.py near-verbatim with from __future__ import annotations so the st.Box / st.MaskFittingResults annotations stay lazy strings (those structures are only referenced in deferred batch functions Phase 1 never calls)."
  - "Created empty panelcleaner/structures.py placeholder (Rule 3) so image_ops.py's lazy annotations resolve; same pattern as the mandated panelcleaner/data/__init__.py placeholder."
  - "compute_mask_bbox returns (x, y, w, h) — NOT (x1,y1,x2,y2) — because EditorCanvas.set_image_from_numpy unpacks bbox as (x, y, w, h) and composites only that region."
  - "Added has_mask_content() to canvas (distinct from has_mask()) for the Inpaint gate: running LaMa on an empty/transparent mask is a wasted model load. has_mask() stays True for an initialized transparent mask (existing plan 03/04 semantic preserved)."
  - "Wired canvas.mask_modified -> _refresh_action_states so the Inpaint (C) action refreshes after each brush/rect/lasso/erase stroke commits (plan explicitly mandated this re-evaluation)."
  - "Phase 1 in-process QThreadPool (D-09b fallback); the D-07/D-08 subprocess split is deferred until a dependency conflict forces it (same rationale as plan 03)."

patterns-established:
  - "Worker dispatch contract: extract numpy on GUI thread (get_image_numpy + mask_to_numpy_binary, both .copy()-detached), pass plain numpy to the worker, return a plain numpy dict, mutate Qt only in main-thread handlers."
  - "QImage .copy() regression guard pattern: test mutates the source numpy after set_image_from_numpy and asserts the displayed image is unchanged (test_inpaint_result_display_uses_copy)."
  - "Non-destructive action pattern: inpaint() has NO confirmation dialog (unlike detect_text's Replace Mask confirmation); reversibility lives in the image-undo stack (plan 06)."
  - "History hook pattern: _on_inpaint_finished calls self.history.push_image_action(x, y, patch) only when self.history is not None; Phase 1 no-ops, plan 06 wires the real HistoryManager."

requirements-completed: [CLEAN-06]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "TorchLamaModel(InpaintModel) adapter wraps vendored SimpleLama with model-path validation, LAMA_MODEL env, binary-mask contract, and size-reclamp crop"
    requirement: "CLEAN-06"
    verification:
      - kind: unit
        ref: "tests/test_inpainting/test_lama_adapter.py#test_lama_load_missing_model_raises"
        status: pass
      - kind: unit
        ref: "tests/test_inpainting/test_lama_adapter.py#test_lama_inpaint_wraps_simple_lama"
        status: pass
      - kind: unit
        ref: "tests/test_inpainting/test_lama_adapter.py#test_lama_inpaint_crops_to_input_size"
        status: pass
      - kind: unit
        ref: "tests/test_inpainting/test_lama_adapter.py#test_lama_inpaint_passes_binary_mask"
        status: pass
      - kind: unit
        ref: "tests/test_inpainting/test_lama_adapter.py#test_lama_load_sets_env_var"
        status: pass
      - kind: unit
        ref: "tests/test_inpainting/test_lama_adapter.py#test_factory_inpainting_torch"
        status: pass
      - kind: unit
        ref: "tests/test_inpainting/test_lama_adapter.py#test_factory_inpainting_onnx_raises_on_load"
        status: pass
    human_judgment: false
  - id: D2
    description: "Async LaMa inpaint via Worker(QRunnable) without freezing UI; worker touches only numpy/PIL + adapter (no Qt in worker thread)"
    requirement: "CLEAN-06"
    verification:
      - kind: automated_ui
        ref: "tests/test_inpainting/test_inpaint_gui.py#test_inpaint_worker_dispatches_adapter"
        status: pass
      - kind: automated_ui
        ref: "tests/test_inpainting/test_inpaint_gui.py#test_inpaint_action_disabled_without_mask"
        status: pass
    human_judgment: false
  - id: D3
    description: "Result display with MANDATORY QImage .copy() at every numpy<->QImage bridge (Pitfall-2 regression guard)"
    requirement: "CLEAN-06"
    verification:
      - kind: automated_ui
        ref: "tests/test_inpainting/test_inpaint_gui.py#test_inpaint_result_display_uses_copy"
        status: pass
      - kind: automated_ui
        ref: "tests/test_inpainting/test_inpaint_gui.py#test_inpaint_replaces_image_layer"
        status: pass
    human_judgment: false
  - id: D4
    description: "Progress feedback (status bar 'Inpainting… N%' + 3px bar) and #7a1f1f error chip + critical dialog on model-load failure"
    requirement: "CLEAN-06"
    verification:
      - kind: automated_ui
        ref: "tests/test_inpainting/test_inpaint_gui.py#test_inpaint_progress_status_bar"
        status: pass
      - kind: automated_ui
        ref: "tests/test_inpainting/test_inpaint_gui.py#test_inpaint_error_chip"
        status: pass
    human_judgment: false
  - id: D5
    description: "Preview toggle: hold-to-preview toolbar button + sticky View -> Show Original (P); both swap original<->inpainted"
    requirement: "CLEAN-06"
    verification:
      - kind: automated_ui
        ref: "tests/test_inpainting/test_inpaint_gui.py#test_preview_hold_button"
        status: pass
      - kind: automated_ui
        ref: "tests/test_inpainting/test_inpaint_gui.py#test_preview_sticky_p"
        status: pass
    human_judgment: false
  - id: D6
    description: "Inpaint is non-destructive (no confirmation dialog) and pushes the image patch onto the history stack for plan 06 undo"
    requirement: "CLEAN-06"
    verification:
      - kind: automated_ui
        ref: "tests/test_inpainting/test_inpaint_gui.py#test_inpaint_no_confirmation_dialog"
        status: pass
      - kind: automated_ui
        ref: "tests/test_inpainting/test_inpaint_gui.py#test_inpaint_pushes_image_history"
        status: pass
    human_judgment: false
  - id: D7
    description: "End-to-end LaMa inpainting on a real mask removes text and restores artwork without freezing the UI; mask overlay stays visible; preview toggle swaps correctly"
    requirement: "CLEAN-06"
    verification:
      - kind: manual_procedural
        ref: ".planning/phases/01-cleaning-workspace/01-VALIDATION.md §Manual-Only — CLEAN-06"
        status: unknown
    human_judgment: true
    rationale: "Requires the real LaMa model weights (~200MB big-lama.pt download) and a visual judgment of inpainting quality on an actual manga page; cannot be automated without the model and a human aesthetic check."

# Metrics
duration: ~35min
completed: 2026-07-12
status: complete
---

# Phase 01 Plan 05: LaMa Inpainting Slice Summary

**Async LaMa inpainting via Worker(QRunnable) with MANDATORY QImage .copy() buffer discipline at every numpy<->Qt bridge, a vendored minimal InpaintingModel, before/after preview toggle, and the plan-06 history hook — completing the detect -> edit mask -> inpaint cleaning loop.**

## Performance

- **Duration:** ~35 min
- **Tasks:** 2/2 complete
- **Files modified:** 12 (7 created, 5 modified)
- **Lines added:** ~2473

## Accomplishments
- Vendored `panelcleaner/inpainting.py` MINIMALLY (InpaintingModel class only; batch `inpaint_page` deferred to Phase 2) and `panelcleaner/image_ops.py` near-verbatim with `from __future__ import annotations` so the deferred-batch structures stay lazy.
- Implemented `TorchLamaModel(InpaintModel)` with model-path validation BEFORE SimpleLama import (T-01-04b), `os.environ["LAMA_MODEL"]` setter, binary-mask contract, and size-reclamp crop; wired `backend_factory('inpainting','torch')`.
- Built the EditorCanvas numpy bridge: `get_image_numpy`, `set_image_from_numpy` (with bbox-region compositing), `show_original`, `has_inpaint_result`, and `has_mask_content` — every numpy<->QImage crossing enforces `.copy()` detachment (the Pitfall-2 regression guard locks this).
- Wired async `MainWindow.inpaint()` via the plan-03 `Worker(QRunnable)`: GUI thread extracts numpy arrays, worker runs LaMa off-thread, main-thread handlers mutate Qt; progress status bar + 3px bar + `#7a1f1f` error chip on failure.
- Added the Preview(hold) toolbar button + sticky View -> Show Original (P) toggle for before/after compare; no confirmation dialog (inpaint is non-destructive); history.push_image_action hook for plan 06.

## Task Commits

Each task was committed atomically:

1. **Task 1: Vendor minimal inpainting.py + image_ops.py + TorchLamaModel + factory wiring** - `0184301` (feat)
2. **Task 2: Async inpaint worker + result display with .copy() discipline + preview toggle** - `4c19387` (feat)

## Files Created/Modified
- `panelcleaner/inpainting.py` - Vendored InpaintingModel class (load + __call__ with size-reclamp; GPL v3)
- `panelcleaner/image_ops.py` - Vendored mask<->RGBA conversions (GPL v3; scipy+cv2+PIL deps)
- `panelcleaner/data/__init__.py` - Empty placeholder satisfying image_ops.py:15 import
- `panelcleaner/structures.py` - Empty placeholder (Rule 3) for lazy annotations in image_ops
- `manga_ai_studio/adapters/torch_impl.py` - Added TorchLamaModel(InpaintModel) next to TorchCTDModel
- `manga_ai_studio/adapters/factory.py` - inpainting/torch -> TorchLamaModel (was NotImplementedError)
- `manga_ai_studio/gui/canvas.py` - numpy bridge methods + inpaint preview state + has_mask_content
- `manga_ai_studio/gui/main_window.py` - inpaint() + handlers + preview toggle + history hook
- `tests/test_inpainting/__init__.py` - package marker
- `tests/test_inpainting/test_lama_adapter.py` - 8 unit tests (mock SimpleLama; no torch in CI)
- `tests/test_inpainting/test_inpaint_gui.py` - 11 GUI tests incl. Pitfall-2 regression guard
- `tests/test_detection/test_ctd_adapter.py` - Updated stub test to assert TorchLamaModel (Rule 3)

## Decisions Made
- Vendored inpainting.py MINIMALLY (InpaintingModel class only); the batch driver is Phase 2 scope per the plan's explicit prohibition.
- compute_mask_bbox returns (x, y, w, h) to match set_image_from_numpy's bbox unpacking (region compositing).
- Added has_mask_content() distinct from has_mask() so the Inpaint gate requires actual painted content (not just an initialized transparent mask).
- Created panelcleaner/structures.py as an empty placeholder (Rule 3) so image_ops.py's lazy annotations resolve.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Vendored panelcleaner/structures.py placeholder**
- **Found during:** Task 1 (vendoring image_ops.py)
- **Issue:** image_ops.py references `panelcleaner.structures` (st.Box, st.MaskFittingResults) in annotations; without the module the import fails. The structures.py module is Phase 2 batch scope (not in files_modified).
- **Fix:** Created an empty panelcleaner/structures.py placeholder (same pattern as the mandated panelcleaner/data/__init__.py); `from __future__ import annotations` keeps the type names as lazy strings never resolved at def-time. Runtime uses only happen in batch functions Phase 1 never calls.
- **Files modified:** panelcleaner/structures.py (created)
- **Verification:** `import panelcleaner.image_ops` succeeds; all 19 inpaint tests pass.
- **Committed in:** 0184301 (Task 1 commit)

**2. [Rule 3 - Blocking] Updated test_factory_inpainting_torch_not_implemented**
- **Found during:** Task 1 (factory wiring)
- **Issue:** tests/test_detection/test_ctd_adapter.py had a test encoding the plan-03 stub behavior (`backend_factory('inpainting','torch') raises NotImplementedError`) that this plan replaces.
- **Fix:** Renamed to test_factory_inpainting_torch_returns_lama_model and asserted `isinstance(model, TorchLamaModel)`.
- **Files modified:** tests/test_detection/test_ctd_adapter.py
- **Verification:** pytest tests/test_detection/ passes (17 tests).
- **Committed in:** 0184301 (Task 1 commit)

**3. [Rule 2 - Missing Critical] Added has_mask_content() + mask_modified -> _refresh_action_states wiring**
- **Found during:** Task 2 (Inpaint action gating)
- **Issue:** The plan's Task 2 behavior test 1 requires Inpaint disabled "when no mask exists", but canvas.has_mask() returns True for a freshly-initialized transparent mask (set_image creates one). Running LaMa on an empty mask is a wasted model load. Separately, the plan mandated re-evaluating action states on canvas.mask_modified, but that signal wasn't connected.
- **Fix:** (a) Added canvas.has_mask_content() that scans the alpha channel for non-zero pixels; (b) gated Inpaint on has_mask_content (not has_mask); (c) connected canvas.mask_modified -> _refresh_action_states so the action refreshes after each stroke commits.
- **Files modified:** manga_ai_studio/gui/canvas.py, manga_ai_studio/gui/main_window.py
- **Verification:** test_inpaint_action_disabled_without_mask passes; full suite (88 tests) green.
- **Committed in:** 4c19387 (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (2 blocking, 1 missing critical)
**Impact on plan:** All auto-fixes necessary for correctness (module imports resolve, replaced stub test encodes new behavior, Inpaint gate matches plan intent). No scope creep.

## Issues Encountered
- Git Bash on Windows mangles `python -c` heredocs with `goto :error`; resolved by using `python -m pytest` (which works) and avoiding standalone script execution in the project directory (sandboxed). No impact on deliverables.
- Discovered `python script.py` returns exit 127 in the project directory (sandbox restriction) while `python -m pytest` works; worked around by running all verification through pytest.

## User Setup Required

The LaMa model weights (~200MB, big-lama.pt) are fetched automatically by `panelcleaner.model_downloader` on first Tools -> Inpaint (C) run. If behind a proxy, set the HuggingFace endpoint env vars per model_downloader.py. This is a one-time download cached in the model cache dir.

## Next Phase Readiness
- Plan 06 (history/undo) can wire `MainWindow.history = HistoryManager(...)`; the call site `self.history.push_image_action(x, y, patch)` in `_on_inpaint_finished` is already in place and no-ops until then.
- Phase 2 FLOW-03 (batch inpaint_page) can vendor the full `inpaint_page` driver + its MaskData/PageData deps; the minimal InpaintingModel vendored here is the building block.
- The 7 manual-procedural verification items in VALIDATION.md §Manual-Only (CLEAN-06) require the real LaMa model + a visual quality check on an actual manga page.

## Known Stubs
- `MainWindow.history = None` (Phase 1): `_on_inpaint_finished` calls `self.history.push_image_action(...)` only when `self.history is not None`. This is the intentional plan-06 hook (not a data stub); the history manager lands in plan 06. No UI renders placeholder data.
- `panelcleaner/structures.py` and `panelcleaner/data/__init__.py` are empty placeholders (Rule 3) satisfying vendored image_ops.py imports; they carry no runtime data and are not rendered anywhere.

---
*Phase: 01-cleaning-workspace*
*Completed: 2026-07-12*

## Self-Check: PASSED

All 12 declared files exist on disk; both task commits (`0184301`, `4c19387`) found in git log. Full test suite (88 tests) green with zero regressions.
