# Phase 2: Cleaning Output & Batch - Context

**Gathered:** 2026-07-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Get cleaned results **out** of the app. Two requirements:

1. **PROJ-02** — Export a single cleaned (text-removed, inpainted) page as PNG or JPG.
2. **FLOW-03** — Batch-process a chapter folder through the cleaning pipeline (detect → clean → save) with a visible progress indicator.

This phase delivers the **output** half of the cleaning workflow. The core insight from discussion: the user wants a **three-action batch workflow** built on top of the Phase 1 pipeline, not a single monolithic "clean everything" run. The user can run detect-only, clean-only (against reviewed masks), or the one-shot full run — review masks page-by-page between detect and clean when they want control.

**In scope:** single-page export (PNG/JPG), the three batch actions, per-page mask persistence across navigation (required to make Batch Clean work against reviewed masks), batch progress + cancel, `cleaned/` output subfolder.

**Out of scope (later phases):** OCR batch (FLOW-04 — Phase 4), batch→editor round-trip navigation (FLOW-05), image operations crop/rotate/levels/resize (PROJ-04 — Phase 5), `.mas` project save/load (PROJ-01 — Phase 5), `_ocr.json` export (PROJ-03 — Phase 5), per-region LaMa params (FLOW-07 — v2).

</domain>

<decisions>
## Implementation Decisions

### Batch Workflow Structure (three actions)
- **D-01:** **Three batch actions**, all operating on the **currently-open folder** (the folder loaded in the Pages sidebar — no separate folder picker). The user opens the chapter (which they already do to preview), then runs one of:
  - **Batch Detect** — run text detection on every page, store the resulting mask per page in the workspace. No inpainting. This is the "set up masks for review" stage.
  - **Batch Clean** — run LaMa inpainting on every page using **its current mask** (the detected mask + any hand-edits), then save to `cleaned/`. Detection is NOT re-run in this stage.
  - **Batch Detect + Clean** — the one-shot original flow: detect → inpaint → save on every page, no review gap. The convenience path.
- **D-02:** Review happens in between. After Batch Detect, the user flips through pages using Phase 1's mask-editing tools (brush/rect/lasso/eraser) to hand-fix masks before committing to inpaint. Their edits are sacred — Batch Clean uses the masks as-is.

### Batch Pipeline Behavior
- **D-03:** **Inpaint only pages with mask content.** A page whose mask is empty (detection found no text, OR the user cleared the mask during review) **skips LaMa** and copies the original page through unchanged to `cleaned/`. (Supersedes the simpler "inpaint only if text found" framing — now gated on mask content *after* detect + review.)
- **D-04:** **Per-page failure is non-fatal.** If a page fails (unreadable file, detection error, inpaint OOM), it is **skipped + logged**, the batch continues, and a summary is shown at the end (e.g. "2 of 30 pages failed — see log"). Failed pages are not written. Matches PanelCleaner's per-image resilience.
- **D-05:** **Reuse the Phase 1 pipeline.** Batch calls the same `backend_factory("detection"/"inpainting")` adapters (`TorchCTDModel` / `TorchLamaModel`) and the same `Worker(QRunnable)` + `WorkerSignals` + `SharableFlag` abort machinery already proven in Phase 1. **One pipeline, three entry points** (Batch Detect, Batch Clean, Batch Detect+Clean) — no standalone decoupled batch class, no drift between interactive and batch results.

### Batch Run Control & UX
- **D-06:** **Launch = actions on the open folder.** No batch dialog, no folder picker, no output-dir picker. The three actions operate on the Pages sidebar's current folder. (Single-page Export, separately, uses a Save As dialog — see Claude's Discretion.)
- **D-07:** **Output location = `cleaned/` subfolder next to the source folder** (PanelCleaner's default). e.g. source `chapter-01/` → `chapter-01/cleaned/*.png`. No overwrite risk to originals, no dialog needed, source and output grouped.
- **D-08:** **Batch blocks the editor while running.** It sets the existing `_op_running` flag (Phase 1's concurrency gate), which disables Detect/Inpaint and all three batch actions for the duration. One model pipeline at a time, no contention. Navigation/viewing the canvas can stay enabled (read-only) — researcher/planner decide.
- **D-09:** **Cancel is supported** via the existing Phase 1 `SharableFlag` abort. A Cancel control sets the flag; the worker checks it **between pages** and stops cleanly **after the current page completes**. Pages already written stay written. (Does not interrupt mid-page — no half-written output file.)
- **D-10:** **Progress = page count + current page name** in the existing status bar (e.g. "Cleaning page 12/30 — chapter-01-012.jpg") + the existing 3px `progress_bar`. **No new widgets.** Reuses Phase 1's `status_bar_left` text + `progress_bar` fields. Per-stage breakdown ("Detecting… / Inpainting…") is optional polish, not required.

### Claude's Discretion
- **Single-page export (PROJ-02) mechanics** — not discussed in depth. Sensible default: a `File → Export Page…` / `Ctrl+E` action that opens a `QFileDialog.getSaveFileName` (reusing Phase 1's dialog patterns) and writes the **current canvas result** (the page as it stands now: original + any mask edits applied via inpaint — NOT a fresh re-clean). Default format preserves the original's extension; fall back to PNG. JPG quality ~95 (PanelCleaner `image_export.py:save_optimized` uses `quality=95, progressive=True`; PNG `compress_level=9`). If the user wants something different, they'll say so at planning. Export writes the *displayed* page (the inpainted result), not the mask.
- **Batch output file format** — default to preserving each original's format (`.png`→`.png`, `.jpg`→`.jpg`); re-encode via the `save_optimized` kwargs pattern. A global "prefer PNG" toggle is optional polish, not required.
- **Re-running a batch over an existing `cleaned/` folder** — overwrite existing outputs by default (simplest); a "skip if exists" is optional. Researcher/planner decide unless the user flags it.
- **Completion behavior** — after a batch finishes, a status-bar message ("Cleaned 28/30 pages — 2 failed, see log") suffices; no auto-open-output-folder or system notification unless the user wants it.
- **Where the three batch actions live in the UI** — most likely the File menu (or a Batch submenu) + optionally toolbar buttons. Follow Phase 1's menu/toolbar structure; researcher/planner place them.
- **Batch progress per-stage text** — D-10 settles the required behavior; whether the status text also cycles through "Detecting…/Inpainting…/Saving…" per page (reusing the `progress_callback` Phase 1 already emits) is implementer polish.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Foundation
- `.planning/PROJECT.md` — PanelCleaner (GPL v3) foundation; model adapter interface; frontend/backend env split (D-07/D-09b — Phase 1 uses the in-process QThreadPool fallback; batch does too)
- `.planning/REQUIREMENTS.md` — **PROJ-02** (export cleaned page as PNG/JPG), **FLOW-03** (batch-process a chapter folder through detect → clean → save with progress)

### Phase Scope
- `.planning/ROADMAP.md` §Phase 2 — Goal, success criteria, requirements mapping, "UI hint: yes"
- `.planning/phases/01-cleaning-workspace/01-CONTEXT.md` — Phase 1 context: the Worker pattern, adapter contract, config system, vendored-vs-original layout (D-12), frontend/backend split. **Batch builds directly on these.**

### Source References (PanelCleaner — GPL v3, the reference to adapt)
- `../PanelCleaner/pcleaner/image_export.py` — **`save_optimized(image, path, original)`** is the direct reference for PROJ-02 export: suffix→format map (`.jpg`→JPEG, `.png`→PNG), PNG `compress_level=9`, JPG `quality=95, progressive=True`, preserves original DPI/mode/compression. Adapt per D-12.
- `../PanelCleaner/pcleaner/gui/processing.py` — **`generate_output(...)`** (lines 1-80 visible) is the reference for batch orchestration: step-based pipeline, per-image abort checking (`check_abortion()`), `progress_callback` + `abort_flag` threading, `output_dir=None` → cache-only intermediate writes. PanelCleaner uses `multiprocessing.Pool`; **our batch reuses the Phase 1 `Worker(QRunnable)` + QThreadPool instead** (D-05, D-09b in-process fallback) — do NOT adopt the multiprocessing.Pool model.
- `../PanelCleaner/pcleaner/main.py` — the `clean` CLI command (docstring at top) defines the step pipeline (text-detection → pre-processing → masking → denoising → inpainting) and the `cleaned/` output-subfolder convention. Our batch runs only detect → inpaint (no preprocessor/denoiser in v1).
- `../PanelCleaner/pcleaner/inpainting.py` — `InpaintingModel` (load + `__call__` with size-reclamp); the batch `inpaint_page` driver is referenced but **not yet vendored** (see Vendored Stub below).

### Vendored Stub (deferred-to-Phase-2 marker)
- `panelcleaner/inpainting.py` (our vendored copy) — lines 49-51 explicitly note: *"The batch `inpaint_page` driver and its MaskData/PageData dependencies (`masker.py`, `structures.py`, `output_structures.py`) are deferred to Phase 2 (FLOW-03)."* The researcher/planner must decide whether to vendor `inpaint_page` or implement batch inpainting directly on the Phase 1 `TorchLamaModel.inpaint` adapter (D-05 favors the latter — reuse the adapter, don't vendor the PanelCleaner batch driver).

### Existing Code (Phase 1 — what batch builds on)
- `manga_ai_studio/gui/main_window.py` — `MainWindow`: `_op_running` gate, `_build_status_bar` (progress_bar + status_bar_left + error_chip), `Worker` dispatch pattern (`detect_text`/`inpaint`), `_resolve_detection_model_path`/`_resolve_inpainting_model_path`, `compute_mask_bbox`. Batch actions wire here.
- `manga_ai_studio/gui/worker_thread.py` — `Worker(QRunnable)`, `WorkerSignals` (progress/result/error/finished/aborted), `SharableFlag`, `Abort`. **The cancel mechanism (D-09) reuses `SharableFlag` + `Abort` directly.**
- `manga_ai_studio/adapters/factory.py` — `backend_factory("detection"/"inpainting", backend)` — batch resolves adapters the same way interactive does (D-05).
- `manga_ai_studio/adapters/torch_impl.py` — `TorchCTDModel.detect(image) → (mask_refined, blk_list)`, `TorchLamaModel.inpaint(image_rgb, mask_binary) → result_rgb`. Both return plain numpy, safe off-GUI-thread.
- `manga_ai_studio/core/image_file.py` — `ImageFile(path, thumbnail, mask, dirty)`. **The `mask` slot and `dirty` flag exist but are per-page-on-canvas; D-11 below requires multi-page mask state.**

### Technology Stack
- `.claude/CLAUDE.md` §Technology Stack — PySide6, Python 3.12, PyTorch, OpenCV, NumPy. (Note: CLAUDE.md's "PanelCleaner uses PyQt5" is stale — verified PySide6.)

### Licensing
- `../PanelCleaner/LICENSE` — GPL v3. Derivative works must be GPL v3 (copyleft); vendored PanelCleaner code per Phase 1 D-12.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`Worker(QRunnable)` + `WorkerSignals` + `SharableFlag`** (`gui/worker_thread.py`) — the entire async + abort infrastructure batch needs. Phase 1's `detect_text`/`inpaint` already demonstrate the dispatch pattern (build worker, connect signals, set `_op_running`, start on `QThreadPool.globalInstance()`). Batch workers follow the same shape; the difference is looping over pages and emitting per-page progress.
- **`backend_factory`** (`adapters/factory.py`) — single resolution point for detection/inpainting adapters. Batch calls it exactly as Phase 1 does.
- **`TorchCTDModel` / `TorchLamaModel`** (`adapters/torch_impl.py`) — the model calls. `detect` returns `(mask_refined, blk_list)`; `inpaint` takes `(image_rgb, mask_binary)` and returns `result_rgb`. Both pure-numpy, thread-safe.
- **Status bar progress UI** (`main_window.py:_build_status_bar`) — `progress_bar` (3px determinate), `status_bar_left` (text), `error_chip` (`#7a1f1f`). Batch progress (D-10) writes here — no new widgets.
- **`_resolve_detection_model_path` / `_resolve_inpainting_model_path`** (`main_window.py`) — first-run model download + cache-check logic. Batch must reuse these (CR-10/CR-11 gap-closure discipline) so a batch run doesn't re-download 80MB/200MB models.
- **`compute_mask_bbox`** (`main_window.py`) — bbox for region compositing; batch inpaint per page can reuse the same bbox-driven `set_image_from_numpy` compositing, or write the full-page result (no bbox needed for file output).

### Established Patterns
- **In-process QThreadPool (D-09b fallback)** — Phase 1 chose the in-process `QThreadPool` over the D-07/D-08 subprocess split. Batch follows the same choice: one env, `QThreadPool`, model adapters called off the GUI thread. Do not introduce `multiprocessing.Pool` (PanelCleaner's CLI model) — it conflicts with the Qt event loop and the adapter architecture.
- **`.copy()` buffer discipline (Pitfall 2)** — every numpy↔QImage / numpy↔history bridge detaches with `.copy()`. Batch output writing (numpy → PIL/cv2 → file) must preserve this when compositing.
- **Thread-safety contract (T-01-07)** — worker tasks touch only numpy/Python + emit signals; all Qt mutation happens in main-thread signal handlers. Batch workers must not touch Qt.
- **Model-load error UX (T-01-08)** — tracebacks to loguru, user-friendly copy in the dialog/error chip. Batch failure summary (D-04) extends this.

### Integration Points
- **`MainWindow`** — the three batch actions wire into the menu/toolbar here, alongside the existing File/Edit/View/Tools menus. `_op_running` already gates concurrent model ops; batch sets it too.
- **Per-page mask state (NEW — D-11 critical)** — Phase 1's canvas holds one mask for the *current* page; switching pages (via `on_page_selected` → `reset_history`) discards it. **The two-stage batch workflow (Batch Detect → review → Batch Clean) requires masks to persist per-page across navigation** so Batch Clean can read every page's mask. This is the central data-model change for Phase 2: the workspace must hold a mask per page (likely on `ImageFile.mask`, which already exists but is currently unused for persistence, or in a new page-state structure). The researcher/planner must design this; it's the dependency that makes Batch Clean possible.
- **`cleaned/` output** — new; write cleaned pages next to the source folder. No existing output-writing code in our tree yet (PanelCleaner's `image_export.save_optimized` is the reference to adapt).

</code_context>

<specifics>
## Specific Ideas

- **The three-action workflow is the user's explicit design**, not a default: "batch detect, batch clean, and then another one that does both (the original one) — it's about flexibility." Review-in-between is the point of splitting them.
- **Batch operates on the open folder**, not a picked one: "when a folder is loaded (and we're only allowing batch with a folder loaded)". Loading the chapter to preview *is* selecting the batch input.
- **Hand-edits before inpaint are sacred** — the whole reason for the split workflow: "load the masks onto the app and then batch clean the existing masks, so the user can check everything before committing to inpaint."

</specifics>

<deferred>
## Deferred Ideas

- **Per-page LaMa params / tile size (FLOW-07)** — v2; out of scope.
- **Batch→editor round-trip / open any page from batch results (FLOW-05)** — v2; the three-action workflow gives review-in-between within the editor, but a dedicated batch-results browser is later.
- **Image operations on export (crop/rotate/levels/resize, PROJ-04)** — Phase 5. PROJ-02 exports the cleaned page as-is.
- **`_ocr.json` / `.mas` export** — Phase 5.
- **System notification / auto-open output folder on batch completion** — noted as optional polish; default is a status-bar summary only.

</deferred>

---

*Phase: 2-Cleaning Output & Batch*
*Context gathered: 2026-07-23*
