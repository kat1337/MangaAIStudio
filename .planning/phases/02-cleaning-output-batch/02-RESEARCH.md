# Phase 2: Cleaning Output & Batch - Research

**Researched:** 2026-07-23
**Domain:** PySide6 desktop batch processing + image export, reusing the Phase 1 LaMa/CTD pipeline
**Confidence:** HIGH (almost entirely grounded in the verified Phase 1 codebase this phase extends; PanelCleaner GPL v3 reference source read in-repo)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Batch Workflow Structure (three actions)**
- **D-01:** Three batch actions, all operating on the **currently-open folder** (the folder loaded in the Pages sidebar — no separate folder picker). The user opens the chapter (which they already do to preview), then runs one of:
  - **Batch Detect** — run text detection on every page, store the resulting mask per page in the workspace. No inpainting.
  - **Batch Clean** — run LaMa inpainting on every page using **its current mask** (the detected mask + any hand-edits), then save to `cleaned/`. Detection is NOT re-run.
  - **Batch Detect + Clean** — the one-shot flow: detect → inpaint → save on every page, no review gap.
- **D-02:** Review happens in between. After Batch Detect, the user flips through pages using Phase 1's mask-editing tools (brush/rect/lasso/eraser) to hand-fix masks before committing to inpaint. Their edits are sacred — Batch Clean uses the masks as-is.

**Batch Pipeline Behavior**
- **D-03:** Inpaint only pages with mask content. A page whose mask is empty (detection found no text, OR the user cleared the mask during review) skips LaMa and **copies the original page through unchanged** to `cleaned/`. Gated on mask content *after* detect + review.
- **D-04:** Per-page failure is non-fatal. A failed page is **skipped + logged**, the batch continues, and a summary is shown at the end (e.g. "2 of 30 pages failed — see log"). Failed pages are not written.
- **D-05:** Reuse the Phase 1 pipeline. Batch calls the same `backend_factory("detection"/"inpainting")` adapters (`TorchCTDModel` / `TorchLamaModel`) and the same `Worker(QRunnable)` + `WorkerSignals` + `SharableFlag` abort machinery. **One pipeline, three entry points** — no standalone decoupled batch class, no drift between interactive and batch results.

**Batch Run Control & UX**
- **D-06:** Launch = actions on the open folder. No batch dialog, no folder picker, no output-dir picker. The three actions operate on the Pages sidebar's current folder.
- **D-07:** Output location = `cleaned/` subfolder next to the source folder (PanelCleaner's default). e.g. source `chapter-01/` → `chapter-01/cleaned/*.png`. No overwrite risk to originals.
- **D-08:** Batch blocks the editor while running. It sets the existing `_op_running` flag (Phase 1's concurrency gate), disabling Detect/Inpaint and all three batch actions for the duration. Navigation/viewing the canvas can stay enabled (read-only) — researcher/planner decide.
- **D-09:** Cancel is supported via the existing Phase 1 `SharableFlag` abort. A Cancel control sets the flag; the worker checks it **between pages** and stops cleanly **after the current page completes**. Pages already written stay written.
- **D-10:** Progress = page count + current page name in the existing status bar + the existing 3px `progress_bar`. **No new widgets.** Reuses Phase 1's `status_bar_left` text + `progress_bar`.

### Claude's Discretion
- **Single-page export (PROJ-02) mechanics** — `File → Export Page…` / `Ctrl+E` opening `QFileDialog.getSaveFileName`, writing the **current canvas result** (displayed image, NOT a fresh re-clean). Default format preserves the original's extension; fall back to PNG. JPG quality ~95, PNG compress_level=9 (PanelCleaner `image_export.py:save_optimized`). Export writes the inpainted result, not the mask.
- **Batch output file format** — preserve each original's format (`.png`→`.png`, `.jpg`→`.jpg`); re-encode via the `save_optimized` kwargs pattern. A global "prefer PNG" toggle is optional polish.
- **Re-running a batch over an existing `cleaned/` folder** — overwrite existing outputs by default; "skip if exists" optional.
- **Completion behavior** — status-bar summary ("Cleaned 28/30 pages — 2 failed, see log") suffices.
- **Where the three batch actions live in the UI** — most likely the File menu (or a Batch submenu) + optionally toolbar buttons. Follow Phase 1's menu/toolbar structure; researcher/planner place them.
- **Batch progress per-stage text** — optional polish to reuse the existing `progress_callback`.

### Deferred Ideas (OUT OF SCOPE)
- Per-page LaMa params / tile size (FLOW-07) — v2.
- Batch→editor round-trip / open any page from batch results (FLOW-05) — v2.
- Image operations on export (crop/rotate/levels/resize, PROJ-04) — Phase 5.
- `_ocr.json` / `.mas` export — Phase 5.
- System notification / auto-open output folder on batch completion — optional polish, default is status-bar summary only.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PROJ-02 | Export a single cleaned (text-removed, inpainted) page as PNG or JPG | §Code Examples → Single-page Export; §Focus Area 3 (output writing). The displayed canvas image (`canvas.get_image_numpy`) is the export source; `QFileDialog.getSaveFileName` (Phase 1 already uses the open variant) + adapted `save_optimized` (PanelCleaner `image_export.py`, read in-repo) is the write path. |
| FLOW-03 | Batch-process a chapter folder through the cleaning pipeline (detect → clean → save) with a progress indicator | §Focus Areas 1–8. The three-action batch workflow (D-01), a single looping `Worker(QRunnable)` reusing Phase 1's `_run_detection_task`/`_run_inpaint_task` shape (D-05), per-page progress on the existing status bar (D-10), and `cleaned/` output writing (D-07). |
</phase_requirements>

## Summary

Phase 2 is an **integration phase**, not a new-pipeline phase. It adds three batch entry points and one export action that reuse — verbatim, via the existing `backend_factory` adapters and `Worker(QRunnable)` infrastructure — the exact detection and inpainting code paths Phase 1 already proved. There is no new model code, no new concurrency primitive, and no new external dependency. The work is: (1) a per-page mask-persistence data-model change so the two-stage "detect → review → clean" workflow is possible, (2) a batch driver function that loops over the open folder's pages dispatching the Phase 1 per-page tasks, (3) a thin output-writer adapted from PanelCleaner's `save_optimized`, and (4) the UI wiring (a File menu's worth of actions + a Cancel affordance).

The single load-bearing dependency that makes the whole three-action design work is **per-page mask persistence (D-11)**. Phase 1's canvas holds one mask for the *current* page in `EditorCanvas._mask`, and `MainWindow.on_page_selected → reset_history` discards canvas/inpaint state on every page switch. Without persistence, a "Batch Detect" that runs detection on every page has nowhere to store 30 masks, and a subsequent "Batch Clean" cannot read them back. The fix is to lift mask state out of the canvas into the per-page `ImageFile` model (whose `mask: QImage | None` slot already exists but is currently unused for persistence — verified at `core/image_file.py:69`), and to populate/restore it at the `on_page_selected` boundary. This is the central data-model change and must land first.

**Primary recommendation:** Build Phase 2 in dependency order — (A) per-page mask persistence on `ImageFile` + `on_page_selected` save/restore, (B) a `batch_runner` module exposing three thin functions (`batch_detect`, `batch_clean`, `batch_detect_and_clean`) each returning a `Worker(QRunnable)` built on the existing `_run_detection_task`/`_run_inpaint_task` shape with a page loop + abort-between-pages + per-page try/except, (C) a `save_optimized`-adapted output writer (`core/image_io.py`), (D) MainWindow wiring (File menu batch actions + Export Page action + Cancel control) reusing `_op_running`, the status bar, and the existing error chip. Do not introduce `multiprocessing.Pool` (PanelCleaner's CLI model) — it conflicts with the Qt event loop and the in-process adapter architecture (D-09b).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Per-page mask state (D-11) | Core data model (`ImageFile.mask`) | Canvas (displays it) | Mask must outlive a single canvas view; the page model is the natural owner. Canvas reads/restores via `set_mask`/`get_mask` it already has. |
| Batch orchestration (loop + abort + per-page try/except) | GUI worker (`Worker(QRunnable)` task fn) | Adapters (called per page) | Same tier Phase 1 uses — the worker runs off the GUI thread, touches only numpy/Python, emits signals. Loop logic lives in the task function, not a new class. |
| Detect / inpaint execution (per page) | Backend adapters (`TorchCTDModel` / `TorchLamaModel`) | — | Already the owners; batch calls them identically to interactive. No new owner. |
| Image output writing (PROJ-02 + cleaned/) | Core I/O (`core/image_io.py`) | — | Pure numpy→PIL→file; no Qt, thread-safe, unit-testable without a GUI. |
| Output path derivation (cleaned/ next to source) | Core I/O | — | `ImageFile.path.parent / "cleaned"`; mkdir handled here. |
| Progress + cancel UI | MainWindow (status bar + Cancel control) | — | Reuses `_op_running`, `status_bar_left`, `progress_bar`, `error_chip`. No new widgets. |
| Export single page (Ctrl+E) | MainWindow (action) | Core I/O (`save_optimized`) | Action opens `QFileDialog.getSaveFileName`; writer does the bytes. |
| Concurrency gate | MainWindow (`_op_running` + `_refresh_action_states`) | — | Already the Phase 1 owner; batch sets the same flag. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PySide6 | 6.7+ (pinned in pyproject) | `Worker(QRunnable)`, `QThreadPool`, `QFileDialog`, status bar widgets | Already the Phase 1 GUI framework. Batch workers are `QRunnable`s on `QThreadPool.globalInstance()` — the proven dispatch path (`main_window.py:996`, `main_window.py:1298`). `[VERIFIED: pyproject.toml + main_window.py]` |
| Pillow (PIL) | 10+ (pinned in pyproject) | numpy→PIL→file output writing; DPI/mode preservation | Already the Phase 1 dep (used in `TorchLamaModel.inpaint` for the numpy↔PIL round-trip). PanelCleaner `image_export.py:save_optimized` is built on it. `[VERIFIED: pyproject.toml + torch_impl.py:245]` |
| OpenCV (cv2) | 4.9+ (pinned in pyproject) | `cv2.imdecode(np.fromfile(...))` for non-ASCII-safe image reads in the batch worker | Already the Phase 1 pattern (`main_window.py:1027-1030`) — batch must use the same read path, NOT `cv2.imread`, for Windows non-ASCII-path safety. `[VERIFIED: main_window.py:_run_detection_task]` |
| NumPy | <2.0 (pinned in pyproject) | Mask serialization (QImage↔numpy), binary mask content checks | Phase 1's bridge discipline (Pitfall 2) is built on numpy. `[VERIFIED: pyproject.toml]` |
| loguru | latest (pinned in pyproject) | Per-page failure logging (D-04) to the same sink Phase 1 uses | Phase 1 already routes `WorkerError` tracebacks to loguru (`main_window.py:1144, 1420`). `[VERIFIED: main_window.py:_on_detection_error/_on_inpaint_error]` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `shutil` (stdlib) | — | `copy2` for the D-03 empty-mask passthrough (copy original page bytes unchanged) | Only when a page's mask is empty after detect+review — preserves original bytes/metadata exactly without a re-encode. `[CITED: python stdlib docs]` |
| `unittest.mock` (stdlib) | — | `FakeSimpleLama` / fake-adapter fixtures for batch-worker tests | Established Phase 1 test pattern (`tests/test_inpainting/test_lama_adapter.py:FakeSimpleLama`). `[VERIFIED: tests/test_inpainting/]` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| One `Worker` looping pages (D-05) | `multiprocessing.Pool` (PanelCleaner CLI) | **Rejected.** Pool workers can't share the loaded model across pages (re-load 200MB LaMa per page), fight the Qt event loop, and the adapters are not pickleable across process boundaries. D-09b explicitly chose the in-process QThreadPool. `[VERIFIED: 01-CONTEXT.md D-09b; main_window.py detect_text/inpaint]` |
| Vendoring PanelCleaner `inpaint_page` batch driver | Reimplement directly on `TorchLamaModel.inpaint` | **Reimplement (D-05 favors).** `inpaint_page` depends on `MaskData`/`PageData`/`masker.py`/`output_structures.py` — a heavy vendoring surface. Phase 1's `inpainting.py:49-51` explicitly defers this; the adapter's `inpaint(image_rgb, mask_binary)` is the lean path. `[VERIFIED: panelcleaner/inpainting.py:49-51 + torch_impl.py:TorchLamaModel.inpaint]` |
| Persisting masks as `.npy`/`.png` files on disk | In-memory `ImageFile.mask: QImage` | **In-memory for v1.** Disk persistence is PROJ-01 `.mas` save/load (Phase 5, deferred). The 8 chapters × ~30 pages × mask-in-memory footprint is bounded by the history limit pattern Phase 1 already uses. `[VERIFIED: image_file.py:ImageFile mask slot; 02-CONTEXT.md defers .mas]` |

**Installation:**
```bash
# Phase 2 adds NO new dependencies. The existing Phase 1 stack is sufficient:
#   PySide6, pillow, opencv-python, numpy<2, loguru, natsort, scipy, attrs, configupdater
# (all already in pyproject.toml [project.dependencies])
# Dev: pytest, pytest-qt, pytest-mock (already in [project.optional-dependencies.dev])
```

**Version verification:** No new packages to verify. All listed packages are confirmed present in `pyproject.toml` (read this session) and are the Phase 1 runtime. `[VERIFIED: pyproject.toml]`

## Package Legitimacy Audit

> Phase 2 installs **no new external packages**. The audit below covers the already-declared Phase 1 dependencies this phase reuses; none are introduced by Phase 2.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| PySide6 | PyPI | active (Qt-for-Python official) | unknown¹ | pyside.org (Qt Group) | OK (existing) | Approved — Phase 1 dep, no Phase 2 change |
| pillow | PyPI | active | unknown¹ | github.com/python-pillow/Pillow | OK (existing) | Approved — Phase 1 dep |
| opencv-python | PyPI | active | unknown¹ | github.com/opencv/opencv-python | OK (existing) | Approved — Phase 1 dep |
| numpy | PyPI | active (<2 pin) | unknown¹ | github.com/numpy/numpy | OK (existing) | Approved — Phase 1 dep |
| loguru | PyPI | active | unknown¹ | github.com/Delgan/loguru | OK (existing) | Approved — Phase 1 dep |

¹ The `gsd-tools query package-legitimacy check` seam reported `SUS` with reasons `too-new`/`unknown-downloads` for these packages — but that is a **false positive from the seam's pypi-download-signal gap**, not a legitimacy concern. All five are canonical, long-established packages with authoritative source repos, already declared in `pyproject.toml` from Phase 1, and verified in-repo this session. `unknown-downloads` reflects the seam's inability to fetch pypi weekly-download counts in this environment, not a real trust signal. Each has a clear, well-known authoritative maintainer (Qt Group, python-pillow org, OpenCV team, NumPy team, Delgan). `[VERIFIED: pyproject.toml + upstream source URLs above]`

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none (the seam's SUS verdicts above are false positives on already-approved Phase 1 deps — no action)

*Phase 2 introduces zero new packages, so the "tag each new install `[ASSUMED]` until verified" rule does not apply. Every package used is already Phase-1-approved.*

## Architecture Patterns

### System Architecture Diagram

```
                         USER
                          │
            ┌─────────────┴──────────────┐
            ▼                            ▼
   [Pages sidebar: open folder]   [File menu]
            │                     │
            │             ┌───────┼───────────────┐───────────┐
            │             ▼       ▼               ▼           ▼
            │      Batch Detect  Batch Clean  Batch D+C   Export Page (Ctrl+E)
            │             │       │               │           │
            │             └───────┴───────┬───────┘           │
            │                             │                   │
            ▼                             ▼                   ▼
   MainWindow._op_running = True    MainWindow builds     canvas.get_image_numpy()
   (D-08 gate; disables            ONE Worker(QRunnable)  → numpy RGB of displayed
    batch + detect + inpaint)      on QThreadPool         page (NOT a re-clean)
                                   with: page_list,
                                   models, abort_flag ──────────┐
                                            │                   │
                                            ▼                   │
                              ┌── batch task fn (loop) ─┐        │
                              │  for i, page in pages:  │        │
                              │    emit progress(i/N,   │        │
                              │         page.name)      │        │
                              │    if abort_flag.get(): │        │
                              │        raise Abort ─────┼──► worker.signals.aborted
                              │    try:                 │        (between pages; D-09)
                              │      ── detect? ──      │        │
                              │        cv2.imdecode     │        │
                              │         (np.fromfile)   │        ▼
                              │        TorchCTDModel    │   save_optimized(numpy, path,
                              │         .detect ──┐     │     original)  → cleaned/<name>
                              │      ── inpaint? ──     │   (PNG compress_level=9 /
                              │        (if mask    │   │    JPG quality=95 progressive)
                              │         content)   │   │   D-03: empty mask → shutil.copy2
                              │        TorchLamaModel│   │        original through unchanged
                              │         .inpaint ──┐│   │
                              │      ── save? ──   ││   │
                              │        save to     ││   │
                              │        cleaned/    ││   │
                              │    except: log +   ││   │
                              │      append to     ││   │
                              │      failed[]      ││   │
                              │      (D-04: skip)  ││   │
                              │  return summary ───┼┼──► worker.signals.result
                              └────────────────────┘┘        │
                                            │                 │
                                            ▼                 │
                          [main-thread signal handlers]       │
                          progress → status_bar_left +         │
                                     progress_bar             │
                          result   → summary dialog/           │
                                     status ("28/30, 2 failed")│
                          error    → error_chip + loguru       │
                          finished → _op_running = False       │
                                                            │
   [D-11 PER-PAGE MASK PERSISTENCE — the cross-cutting dep]  │
   ┌──────────────────────────────────────────────────────────┘
   │ ImageFile.mask: QImage | None  (per page; already a slot)
   │ on_page_selected:  save canvas._mask → current ImageFile.mask
   │                    restore target ImageFile.mask → canvas.set_mask
   │ reset_history stays (undo is per-page); only mask is lifted out.
   └────────────────────────────────────────────────────────────
```

A reader can trace the primary use case (Batch Detect+Clean): open folder → pick action → `_op_running` set → one Worker loops pages → detect→inpaint→save per page (try/except around each) → progress emitted to status bar → summary on finish → `_op_running` cleared. The D-11 mask-persistence box is reached by the "Batch Detect then review then Batch Clean" path: Batch Detect writes a mask per page into `ImageFile.mask`, the user navigates (save/restore at the `on_page_selected` boundary) editing masks, then Batch Clean reads each page's `ImageFile.mask`.

### Recommended Project Structure
```
manga_ai_studio/
├── core/
│   ├── image_file.py        # MODIFY: mask persistence semantics (D-11)
│   ├── image_io.py          # NEW: save_optimized-adapted output writer (PROJ-02 + cleaned/)
│   └── batch_runner.py      # NEW: batch_detect / batch_clean / batch_detect_and_clean
│                            #       task fns (page loop + abort + try/except)
├── adapters/
│   ├── factory.py           # UNCHANGED: backend_factory("detection"/"inpainting")
│   └── torch_impl.py        # UNCHANGED: TorchCTDModel.detect / TorchLamaModel.inpaint
├── gui/
│   ├── main_window.py       # MODIFY: batch menu actions + Export Page action +
│   │                        #       Cancel control + per-page mask save/restore in
│   │                        #       on_page_selected (D-11); _op_running gate reuse
│   ├── worker_thread.py     # UNCHANGED: Worker / WorkerSignals / SharableFlag / Abort
│   └── canvas.py            # UNCHANGED (the mask bridge methods it exposes are reused)
└── panelcleaner/            # UNCHANGED: vendored reference (save_optimized adapted, not vendored)
tests/
├── test_core/
│   ├── test_image_io.py     # NEW: save_optimized round-trips (PNG/JPG/DPI/mode)
│   └── test_batch_runner.py # NEW: fake-adapter batch loop, abort-between-pages, D-03/D-04
└── test_gui_batch.py        # NEW: MainWindow batch wiring + Export Page (pytest-qt)
```

### Pattern 1: The Phase 1 Worker Dispatch (replicate for batch)
**What:** Build a `Worker(QRunnable)` whose task function does the heavy work off the GUI thread, connect its `WorkerSignals` to main-thread handlers, set `_op_running`, and start on `QThreadPool.globalInstance()`.
**When to use:** Every async model op — detect, inpaint, and now all three batch actions. This is THE concurrency pattern (T-01-07).
**Example:**
```python
# Source: manga_ai_studio/gui/main_window.py:982-996 (detect_text dispatch, VERIFIED)
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
The batch variant is the same shape with a different task function (`_run_batch_task`) and a `result` payload carrying the summary dict (`{ok, failed, total}`). The `abort_flag` is passed via the `abort_signal` constructor param (see Pattern 2). `[VERIFIED: main_window.py:detect_text + inpaint]`

### Pattern 2: Abort via SharableFlag (D-09) — check between pages
**What:** The `Worker` constructor accepts `abort_signal: Signal`. When provided, it injects `abort_flag=self.aborted` (a `SharableFlag`) into the task function's kwargs and connects the signal to `Worker.abort` (which sets the flag). The task function polls `abort_flag.get()` between units of work and raises `Abort` — which the `Worker.run` try/except catches and converts to `signals.aborted`.
**When to use:** Batch (between pages — D-09 says never interrupt mid-page). Phase 1's interactive detect/inpaint don't wire abort (single-image ops), but the infra is fully present.
**Example:**
```python
# Source: manga_ai_studio/gui/worker_thread.py:113-141 + 142-174 (VERIFIED)
# Dispatch with an abort signal:
self._batch_abort_signal = Signal()  # a QObject on the MainWindow, or reuse a QShortcut
worker = Worker(
    self._run_batch_task, pages, mode, det_model_path, inp_model_path,
    abort_signal=self._batch_abort_signal,   # injects abort_flag into kwargs
)
worker.signals.aborted.connect(self._on_batch_aborted)

# Inside the task fn (runs on the worker thread):
def _run_batch_task(self, pages, mode, ..., progress_callback=None, abort_flag=None):
    for i, page in enumerate(pages):
        # D-09: check BETWEEN pages, never mid-page
        if abort_flag is not None and abort_flag.get():
            raise Abort()  # worker_thread.py:155 catches -> signals.aborted
        progress_callback.emit((int(i/len(pages)*100), page.name))
        try:
            ...  # detect/inpaint/save for this page
        except Exception as exc:  # D-04: per-page failure non-fatal
            logger.error(f"Batch: page {page.name} failed: {exc}")
            failed.append((page.path, str(exc)))
            continue
    return {"ok": len(pages) - len(failed), "failed": failed, "total": len(pages)}
```
The Cancel control (a status-bar button or a menu/shortcut) emits `self._batch_abort_signal` → `Worker.abort()` sets the flag → the next page boundary raises `Abort`. Pages already written stay written. `[VERIFIED: worker_thread.py:Worker.__init__ abort_signal param + run() Abort branch]`

### Pattern 3: numpy↔QImage buffer discipline (.copy()) at every boundary (Pitfall 2)
**What:** Every time a numpy array and a QImage share a buffer, the QImage must be `.copy()`-detached before storage (and the numpy returned to a worker must `.copy()` away from the QImage buffer). Without this, GC of one corrupts the other → intermittent segfaults.
**When to use:** At every mask save/restore (D-11), at every batch result → canvas composite, at every export.
**Example:**
```python
# Source: manga_ai_studio/gui/canvas.py:563 + mask_editor.py:206-207 (VERIFIED)
# numpy -> QImage: ALWAYS .copy() before storage
qimg = QImage(rgba.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
return qimg.copy()   # MANDATORY — detaches from the numpy buffer

# QImage -> numpy: ALWAYS .copy() the result (the trailing .copy() in mask_to_numpy_binary)
arr = np.frombuffer(bytes(src.constBits()), dtype=np.uint8).reshape(h, w, 4)
...
return binary.copy().astype(np.uint8)
```
Phase 1 already enforces this on the mask bridge (`set_mask`, `get_mask`, `apply_undo_mask`, `mask_to_numpy_binary`, `numpy_binary_to_mask_qimage`). The D-11 per-page persistence MUST reuse these exact helpers — do NOT write a new QImage↔numpy conversion. `[VERIFIED: canvas.py:set_mask + mask_editor.py:mask_to_numpy_binary/numpy_binary_to_mask_qimage]`

### Pattern 4: Image output via adapted save_optimized (PROJ-02 + cleaned/)
**What:** Convert the result numpy (RGB uint8) to a PIL `Image`, then save with format-specific kwargs (PNG `compress_level=9 optimize=True`; JPG `quality=95 progressive=True`), preserving the original's mode + DPI when the format matches.
**When to use:** Single-page Export (writes the displayed canvas image) AND batch `cleaned/` writes.
**Example:**
```python
# Adapted from ../PanelCleaner/pcleaner/image_export.py:32-80 (save_optimized, VERIFIED in-repo, GPL v3)
from PIL import Image
SUFFIX_TO_FORMAT = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG",
                    ".webp": "WEBP", ".bmp": "BMP"}

def save_optimized(image_rgb: np.ndarray, path: Path, original: Path | None = None) -> None:
    pil = Image.fromarray(image_rgb, mode="RGB")
    mode = fmt = dpi = None
    if original is not None:
        with Image.open(original) as orig:
            fmt = SUFFIX_TO_FORMAT.get(original.suffix.lower())
            if fmt == orig.format:
                mode = orig.mode
                dpi = orig.info.get("dpi")
    if mode is not None:
        pil = pil.convert(mode)
    kwargs = {"optimize": True}
    suf = path.suffix.lower()
    if suf == ".png":
        kwargs["compress_level"] = 9
    elif suf in (".jpg", ".jpeg"):
        kwargs["quality"] = 95
        kwargs["progressive"] = True
    if dpi is not None:
        kwargs["dpi"] = dpi
    pil.save(path, **kwargs)
```
**Why adapt rather than vendor:** PanelCleaner's `save_optimized` accepts `Path | Image.Image` for `image` (opens from disk) and pulls in `psd_tools`/`output_structures` transitively via the module's other functions. Phase 2 needs only the numpy→PIL→kwargs→save core (~30 lines). Adapting (not vendoring the whole module) keeps the dependency surface clean and matches D-12's "adapt logic, don't drag in unrelated deps." `[VERIFIED: ../PanelCleaner/pcleaner/image_export.py:32-80 read this session]`

### Anti-Patterns to Avoid
- **Don't use `multiprocessing.Pool` for batch** (PanelCleaner CLI's model). Pool re-imports the module in each worker → re-loads LaMa (200MB) per page, can't pickle the PySide6-coupled MainWindow, and forks a process that fights the Qt event loop. D-05/D-09b lock the in-process QThreadPool. `[VERIFIED: ../PanelCleaner/pcleaner/gui/processing.py:5 `from multiprocessing import Pool`; 01-CONTEXT.md D-09b rejects it]`
- **Don't vendor PanelCleaner's `inpaint_page` batch driver.** It depends on `MaskData`/`PageData` (`structures.py`, `output_structures.py`, `masker.py`) — a large vendoring surface. The adapter's `TorchLamaModel.inpaint(image_rgb, mask_binary)` is the lean equivalent. `[VERIFIED: panelcleaner/inpainting.py:49-51 deferral note; torch_impl.py:TorchLamaModel.inpaint]`
- **Don't re-download models per page.** A 30-page batch would re-fetch 80MB CTD / 200MB LaMa 30×. Batch MUST reuse `_resolve_detection_model_path` / `_resolve_inpainting_model_path` (which short-circuit on cache presence, CR-10/CR-11) AND load each model ONCE before the loop (not per page). `[VERIFIED: main_window.py:_resolve_detection_model_path cache check at line 1087]`
- **Don't write the displayed QImage directly to disk for export.** Export writes the *numpy* of the displayed image (`canvas.get_image_numpy`), converted via PIL — not a raw QImage blit. This sidesteps QImage format/buffer issues and gives DPI/mode control. `[VERIFIED: canvas.py:get_image_numpy returns RGB numpy .copy()]`
- **Don't clear/reset the canvas mask when navigating during a Batch Detect.** The mask being persisted must be preserved; only the undo history resets per page (Phase 1 contract). `[VERIFIED: main_window.py:on_page_selected calls reset_history — mask persistence is additive, not a replacement]`
- **Don't interrupt a batch mid-page.** D-09 is explicit: check abort *between* pages so no output file is half-written. A `try/finally` around the per-page inpaint+save, or an abort check only at the loop top, satisfies this. `[VERIFIED: 02-CONTEXT.md D-09]`

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async batch execution | A new `QThread` subclass / thread manager | The existing `Worker(QRunnable)` + `QThreadPool.globalInstance()` (Phase 1) | Proven, carries `WorkerError`/`Abort`/`SharableFlag`, auto-injects progress/abort. Already in `gui/worker_thread.py`. `[VERIFIED]` |
| Image format-specific save kwargs | Manual `if png: ... if jpg: ...` guesswork | Adapted `save_optimized` from PanelCleaner `image_export.py` | Handles DPI, mode, compression-method preservation — all edge cases a hand-roll misses. `[VERIFIED: image_export.py:48-80]` |
| Empty-mask page passthrough (D-03) | Re-encode the original through PIL "to be safe" | `shutil.copy2(original, cleaned/original.name)` | `copy2` preserves bytes AND metadata (mtime, Windows ACLs) exactly; a PIL re-encode risks quality loss and metadata stripping. `[CITED: python stdlib shutil docs]` |
| Per-page mask content check | A new "is this mask empty?" scan | `canvas.has_mask_content()` (Phase 1) — or `mask_to_numpy_binary(mask).any()` on the persisted QImage | Already implemented + regression-guarded. `[VERIFIED: canvas.py:has_mask_content]` |
| Non-ASCII image read | `cv2.imread(path)` | `cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)` | `cv2.imread` fails on non-ASCII Windows paths AND some codecs (webp). Phase 1's `_run_detection_task` already uses this. `[VERIFIED: main_window.py:1027-1030]` |
| Progress reporting | A custom progress dialog/window | The existing `status_bar_left` + `progress_bar` (D-10) | CONTEXT explicitly forbids new widgets. `[VERIFIED: 02-CONTEXT.md D-10]` |

**Key insight:** This phase's entire value is *not building* — it's wiring the three batch entry points to machinery that already exists. Every "hard" subproblem (async, abort, mask conversion, model loading, image read) has a Phase 1 solution. The genuinely new code is small: a page-loop task function, an `ImageFile.mask` persistence seam, and a ~30-line output writer.

## Runtime State Inventory

> Phase 2 is **not** a rename/refactor/migration phase. It adds features on top of Phase 1. This section is included for completeness; the only "state" concern is in-memory (no persisted data migration).

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None on disk (Phase 1 has no `.mas`/project persistence; `.mas` is Phase 5 deferred). Mask state is in-memory only. | None — D-11 persistence is in-memory on `ImageFile.mask`, not a disk migration. |
| Live service config | None. No external services (n8n, datadog, etc.) in this desktop app. | None. |
| OS-registered state | None. No Task Scheduler / launchd / pm2 registrations. | None. |
| Secrets/env vars | None new. Batch reuses `LAMA_MODEL` env var set by `TorchLamaModel.load` (Phase 1). | None — env var unchanged. `[VERIFIED: torch_impl.py:216]` |
| Build artifacts | None affected. `pyproject.toml` package list unchanged (no new deps). `egg-info`/dist unaffected. | None. |

**Nothing found requiring migration.** The only state change is the in-memory per-page mask on `ImageFile` (D-11), which is additive — existing single-page behavior is unaffected because an `ImageFile.mask` that stays `None` behaves exactly as today.

## Common Pitfalls

### Pitfall 1: Mask lost on page navigation (the D-11 failure mode — CRITICAL)
**What goes wrong:** Phase 1's `on_page_selected → reset_history` discards canvas state, and the canvas mask (`EditorCanvas._mask`) is the *only* mask store. Run Batch Detect over 30 pages, navigate away, and 29 masks are gone — Batch Clean then has nothing to read.
**Why it happens:** `reset_history` (`main_window.py:766`) replaces the HistoryManager; the canvas mask survives navigation only by accident (it's overwritten on the next `set_image_from_path` → `set_image` which reinitializes `_mask` to transparent at `canvas.py:235`).
**How to avoid:** Persist the canvas mask into `ImageFile.mask` *before* switching pages, and restore it *after* loading the new page's image. Concretely: in `on_page_selected`, capture the *current* page's `canvas.get_mask()` into its `ImageFile.mask` (if the canvas has a mask), THEN load the target page, THEN if the target `ImageFile.mask` is non-None, `canvas.set_mask(target.mask.copy())`. Keep `reset_history` (undo is correctly per-page). `[VERIFIED: main_window.py:on_page_selected + canvas.py:set_image mask reinit + image_file.py:mask slot]`
**Warning signs:** After Batch Detect, the canvas shows no mask on a previously-detected page. A unit test: detect on page 1, navigate to page 2 and back, assert page 1's `ImageFile.mask` is non-None and `canvas.has_mask()` is True after restore.

### Pitfall 2: numpy/QImage shared-buffer segfault (Phase 1 Pitfall 2, carries forward)
**What goes wrong:** A QImage built over a numpy buffer (via `QImage(arr.data, ...)`) without `.copy()` references memory that gets GC'd → intermittent segfault when the QImage is later painted. Conversely, a numpy view over a QImage buffer (`np.frombuffer(qimg.constBits())`) without `.copy()` becomes garbage when the QImage is freed.
**Why it happens:** PySide6 QImages do not own the numpy buffer; numpy views do not own the QImage buffer.
**How to avoid:** Reuse the Phase 1 helpers verbatim — `mask_to_numpy_binary` and `numpy_binary_to_mask_qimage` both enforce the trailing `.copy()`. In the D-11 persistence seam, store `canvas.get_mask().copy()` into `ImageFile.mask` and pass `image_file.mask.copy()` to `canvas.set_mask`/`apply_undo_mask` (which `.copy()` internally too, but belt-and-suspenders at the boundary is correct). `[VERIFIED: mask_editor.py:mask_to_numpy_binary/numpy_binary_to_mask_qimage; canvas.py:set_mask:305 .copy()]`
**Warning signs:** Random crashes during batch or after navigating several pages. `test_inpaint_result_display_uses_copy` (Phase 1) is the regression template — write `test_mask_persistence_uses_copy` for D-11.

### Pitfall 3: Re-loading the model per page (perf cliff)
**What goes wrong:** A naive batch that calls `backend_factory(...).load(model_path)` inside the page loop re-loads LaMa (200MB) on every page → a 30-page batch takes 30× the model-load time instead of 1×.
**Why it happens:** Phase 1's interactive `_run_detection_task`/`_run_inpaint_task` load once per *worker* (each click = one worker = one load). A batch worker that loops must load once *before* the loop, not inside it.
**How to avoid:** In the batch task function, resolve + load each model ONCE (before the `for page in pages` loop), then call `.detect`/`.inpaint` per page. Reuse `_resolve_detection_model_path`/`_resolve_inpainting_model_path` (they short-circuit on cache presence). `[VERIFIED: main_window.py:_run_inpaint_task loads model once at line 1318; _resolve_*_model_path cache check]`
**Warning signs:** Batch of 30 pages takes >2 min even on a fast GPU; log shows repeated "Loading model…" progress emits.

### Pitfall 4: Half-written output file on cancel (D-09 violation)
**What goes wrong:** If the abort check is placed *after* starting the inpaint but *before* the save, a cancel could leave no output (acceptable) — but if it's placed mid-write, a partial file appears in `cleaned/`.
**Why it happens:** Misplacing the abort check inside the per-page inpaint/save sequence.
**How to avoid:** Check `abort_flag.get()` ONLY at the top of the page loop (before any work for that page). Once a page's work starts, let it finish (inpaint + save) before the next check. Pages already written stay written; a canceled page is simply not started. `[VERIFIED: 02-CONTEXT.md D-09 "stops cleanly after the current page completes"]`
**Warning signs:** Corrupt/truncated images in `cleaned/` after a cancel.

### Pitfall 5: Export writes a re-cleaned image instead of the displayed one
**What goes wrong:** Export is specced (Claude's Discretion) to write the *current canvas result* (what the user sees: original + applied inpaints). If Export instead re-runs detection+inpaint, the output differs from what the user reviewed (different mask, different inpaint), violating the user's mental model.
**Why it happens:** Tempting to reuse the batch/inpaint path for "consistency."
**How to avoid:** Export calls `canvas.get_image_numpy()` (the displayed image as RGB numpy) and writes that via `save_optimized`. Do NOT call any model. `[VERIFIED: 02-CONTEXT.md Claude's Discretion "NOT a fresh re-clean"; canvas.py:get_image_numpy]`
**Warning signs:** Exported file differs from the canvas display.

### Pitfall 6: Windows non-ASCII path failure on read/write
**What goes wrong:** Manga chapter folders with Japanese/Unicode names fail to read (`cv2.imread`) or write (PIL on some codecs) on Windows.
**Why it happens:** Path-based codecs use the system code page, not UTF-8, on Windows.
**How to avoid:** Read via `cv2.imdecode(np.fromfile(path))` (Phase 1 pattern). For PIL writes, `Image.save(str(path))` is generally UTF-8-safe on Pillow 10+, but if a write fails, fall back to writing to a temp ASCII path + `shutil.move`. The empty-mask `copy2` passthrough is already path-safe. `[VERIFIED: main_window.py:1027-1030 read pattern]`
**Warning signs:** `FileNotFoundError` or corrupt output on a Unicode-named chapter.

### Pitfall 7: `_op_running` not cleared on batch error/abort (editor stuck disabled)
**What goes wrong:** If the batch worker raises and the `finished` signal doesn't fire (or the handler doesn't reset `_op_running`), all model actions stay disabled forever.
**Why it happens:** Forgetting that `Worker.run`'s `finally` always emits `finished` — the cleanup handler must reset `_op_running` unconditionally (as Phase 1's `_on_detection_cleanup`/`_on_inpaint_cleanup` do).
**How to avoid:** Mirror Phase 1's cleanup handlers exactly: `_on_batch_cleanup` sets `_op_running = False`, hides `progress_bar`, refreshes action states — unconditionally, in the `finished` slot. `[VERIFIED: main_window.py:_on_detection_cleanup:1155-1159 + worker_thread.py:run finally:164-165]`
**Warning signs:** After a batch error, the Detect/Inpaint menu items stay greyed out.

## Code Examples

Verified patterns/signatures to replicate (all from the Phase 1 codebase read this session unless noted):

### The per-page task shape (detect) — batch loop body reuses this
```python
# Source: manga_ai_studio/gui/main_window.py:998-1050 (_run_detection_task, VERIFIED)
# The batch detect-loop body is this minus the model.load (load once before the loop):
def _detect_one_page(image_path, model, progress_callback=None):
    import cv2, numpy as np
    image = cv2.imdecode(
        np.fromfile(str(image_path), dtype=np.uint8), cv2.IMREAD_COLOR
    )
    if image is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")
    mask_refined, blk_list = model.detect(image)  # adapter contract: (mask, blocks)
    return mask_refined  # (H, W) uint8 heatmap
```
`[VERIFIED: main_window.py:_run_detection_task + torch_impl.py:TorchCTDModel.detect returns (mask_refined, blk_list)]`

### The per-page task shape (inpaint) — batch loop body reuses this
```python
# Source: manga_ai_studio/gui/main_window.py:1300-1327 (_run_inpaint_task, VERIFIED)
def _inpaint_one_page(image_rgb, mask_binary, model, progress_callback=None):
    result_rgb = model.inpaint(image_rgb, mask_binary)  # (H,W,3) uint8 RGB
    return result_rgb
# Adapter contract: image_rgb is (H,W,3) uint8 RGB; mask_binary is (H,W) uint8 0/255.
# size-reclamp crop is handled inside TorchLamaModel.inpaint (torch_impl.py:251-253).
```
`[VERIFIED: main_window.py:_run_inpaint_task + torch_impl.py:TorchLamaModel.inpaint]`

### Mask content check (D-03 gate) — reuse the Phase 1 helper
```python
# Source: manga_ai_studio/gui/canvas.py:348-365 (has_mask_content, VERIFIED)
# For a persisted ImageFile.mask (QImage), the same logic applies:
from manga_ai_studio.core.mask_editor import mask_to_numpy_binary
def _mask_has_content(mask_qimage) -> bool:
    if mask_qimage is None or mask_qimage.isNull():
        return False
    return bool(mask_to_numpy_binary(mask_qimage).any())
```
`[VERIFIED: canvas.py:has_mask_content uses the same alpha-channel scan; mask_to_numpy_binary at mask_editor.py:162]`

### D-11 persistence seam (the central change)
```python
# Adapted into on_page_selected (VERIFIED signatures: main_window.py:on_page_selected,
# canvas.py:get_mask/set_mask, image_file.py:ImageFile.mask slot)
def on_page_selected(self, path):
    # 1. Persist the OUTGOING page's canvas mask (if any) before switching.
    current_idx = self._current_page_index()
    if current_idx is not None and self.canvas.has_mask():
        # .copy() mandatory (Pitfall 2) — detach from the canvas buffer.
        self.image_files[current_idx].mask = self.canvas.get_mask().copy()
    # 2. Existing per-page undo reset (unchanged from Phase 1).
    self.reset_history()
    # 3. Load the new page image (unchanged).
    if not self.canvas.set_image_from_path(path):
        ...  # unreadable dialog
        return
    # 4. Restore the INCOMING page's persisted mask (if any).
    target = self._image_file_for_path(path)
    if target is not None and target.mask is not None and not target.mask.isNull():
        self.canvas.set_mask(target.mask.copy())  # .copy() at the boundary
    ...  # title, fit, recent, status (unchanged)
```
`[VERIFIED: main_window.py:on_page_selected:561-580 + canvas.py:set_mask accepts a QImage; image_file.py:69 mask slot exists]`

### Output writer (adapted save_optimized)
```python
# Source: ../PanelCleaner/pcleaner/image_export.py:32-80 (save_optimized, VERIFIED in-repo, GPL v3)
# Adapted: input is a numpy RGB array (not a Path); ~30-line core, no psd_tools.
from pathlib import Path
import numpy as np
from PIL import Image

_SUFFIX_TO_FORMAT = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG",
                     ".webp": "WEBP", ".bmp": "BMP"}

def save_image_optimized(image_rgb: np.ndarray, path: Path,
                         original: Path | None = None) -> None:
    if image_rgb.ndim != 3 or image_rgb.shape[2] != 3 or image_rgb.dtype != np.uint8:
        raise ValueError("expected (H,W,3) uint8 RGB")
    pil = Image.fromarray(image_rgb, mode="RGB")
    mode = dpi = None
    if original is not None and _SUFFIX_TO_FORMAT.get(original.suffix.lower()):
        try:
            with Image.open(original) as orig:
                if _SUFFIX_TO_FORMAT[original.suffix.lower()] == orig.format:
                    mode = orig.mode
                    dpi = orig.info.get("dpi")
        except (OSError, ValueError):
            pass  # unreadable original — save without metadata preservation
    if mode is not None:
        pil = pil.convert(mode)
    kwargs = {"optimize": True}
    suf = path.suffix.lower()
    if suf == ".png":
        kwargs["compress_level"] = 9
    elif suf in (".jpg", ".jpeg"):
        kwargs["quality"] = 95
        kwargs["progressive"] = True
    if dpi is not None:
        kwargs["dpi"] = dpi
    path.parent.mkdir(parents=True, exist_ok=True)
    pil.save(path, **kwargs)
```
`[VERIFIED: ../PanelCleaner/pcleaner/image_export.py:32-80 — suffix_to_format, compress_level=9, quality=95 progressive=True, mode/dpi preservation all confirmed]`

### Empty-mask passthrough (D-03)
```python
# Source: python stdlib shutil.copy2 (CITED) — preserves bytes + metadata exactly.
import shutil
def _passthrough_original(original: Path, cleaned_dir: Path) -> Path:
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    dest = cleaned_dir / original.name
    shutil.copy2(original, dest)  # bytes + mtime + metadata identical
    return dest
```
`[CITED: docs.python.org/3/library/shutil.html#shutil.copy2]`

### Export Page action (PROJ-02, Claude's Discretion)
```python
# Source: main_window.py:open_image (QFileDialog pattern, VERIFIED) + canvas.py:get_image_numpy
from PySide6.QtWidgets import QFileDialog

def export_page(self):
    if self._op_running:
        return
    current = self.file_table.current_path()
    if current is None:
        return
    image_rgb = self.canvas.get_image_numpy()  # the DISPLAYED image (not a re-clean)
    if image_rgb is None:
        return
    default_name = current.name  # preserve original name + extension
    suffix = current.suffix.lower()
    filt = "PNG (*.png)" if suffix == ".png" else "JPEG (*.jpg *.jpeg)"
    path, _ = QFileDialog.getSaveFileName(
        self, "Export Page", default_name, filt,
    )
    if not path:
        return
    save_image_optimized(image_rgb, Path(path), original=current)
```
`[VERIFIED: main_window.py:open_image uses QFileDialog.getOpenFileName (same family); canvas.py:get_image_numpy:468]`

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `cv2.imread(path)` for image read | `cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)` | Phase 1 (CR-17) | Non-ASCII Windows paths + webp now work. Batch must use the same. `[VERIFIED: main_window.py:1027-1030]` |
| `mask_to_numpy_binary` thresholding raw alpha | Threshold alpha>0 → 0/255 binary | Phase 1 (01-05) | Crisp binary mask for LaMa; the 160-alpha overlay is display-only. Batch reuses this. `[VERIFIED: mask_editor.py:162-187]` |
| `multiprocessing.Pool` batch (PanelCleaner CLI) | In-process `QThreadPool` Worker (D-09b) | Phase 1 decision | No process fork, model shared across pages, Qt-safe. `[VERIFIED: 01-CONTEXT.md D-09b]` |

**Deprecated/outdated:**
- PanelCleaner's `generate_output` `multiprocessing.Pool` model (`../PanelCleaner/pcleaner/gui/processing.py:5`): the reference for *orchestration shape* (per-step pipeline, `check_abortion()` between steps, `progress_callback` + `abort_flag`) but NOT for the execution mechanism. Adopt the abort-between-units + per-unit-progress + summary patterns; reject the Pool. `[VERIFIED: processing.py:1-120 read this session]`

## Assumptions Log

> Claims tagged `[ASSUMED]` in this research. The planner/discuss-phase should confirm these before locking.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | In-memory `ImageFile.mask` per page is sufficient for v1 (no disk persistence needed this phase) | Alternatives Considered; Runtime State | If the user opens a 500-page volume, memory could balloon (each mask is ~image-WxH×4 bytes). Mitigation: bound to the open folder; `.mas` disk persistence is Phase 5. `[ASSUMED — based on typical chapter size ~30-60 pages]` |
| A2 | `QFileDialog.getSaveFileName` default-suffix handling preserves the chosen extension without manual fixup | Code Examples (Export) | Some Qt versions don't append the suffix if the user omits it; a `path = Path(path).with_suffix(...)` guard may be needed. Low risk — verifiable in Wave 0 test. `[ASSUMED — PySide6 6.7 behavior]` |
| A3 | Pillow 10+ `Image.save` is UTF-8-safe for Windows non-ASCII write paths | Pitfall 6 | If not, fall back to temp-ASCII-path + `shutil.move`. Low risk. `[ASSUMED]` |
| A4 | A status-bar Cancel button (or a menu Cancel action) is an acceptable "Cancel affordance" within the "no new widgets" constraint (D-10) | Open Questions Q1 | D-10 forbids new *progress* widgets; a Cancel control is arguably a control, not a progress widget. Needs user/planner confirmation. `[ASSUMED]` |
| A5 | Navigation stays enabled (read-only) during a batch (D-08 leaves this to researcher/planner) | Open Questions Q2 | If disabled, the user can't preview progress on other pages; if enabled, `on_page_selected`'s D-11 save-restore must be safe during a running batch (it touches `ImageFile.mask`, which the batch worker may also be writing — a potential race). Recommendation: disable page-switch during batch to avoid the race. `[ASSUMED]` |

## Open Questions

1. **Where does the Cancel control live, and is it "a new widget" (D-10)?**
   - What we know: D-09 requires cancel via `SharableFlag`; D-10 says "no new widgets" for *progress*. A Cancel button is a control, not progress UI.
   - What's unclear: Is a status-bar Cancel button acceptable, or must it be a menu action / keyboard shortcut (Esc) to honor D-10 strictly?
   - Recommendation: A `Tools → Cancel Batch` menu action (disabled unless a batch is running) + an Esc `QShortcut` is the safest read of D-10 (no new visible widget, reuses menu/shortcut infrastructure). Flag for planner/user. `[ASSUMED A4]`

2. **Is page navigation enabled during a batch (D-08 open question)?**
   - What we know: D-08 sets `_op_running` (disables model actions) and says navigation/viewing "can stay enabled (read-only)" but defers to researcher/planner.
   - What's unclear: The D-11 persistence seam writes `ImageFile.mask` on `on_page_selected`. If a batch worker is concurrently writing `ImageFile.mask` (per-page detect result), there's a write/write race on the same dict entry.
   - Recommendation: Disable page-switch during a batch (set the FileTable non-interactive while `_op_running` is True for a batch). This avoids the race entirely and matches "blocks the editor." The canvas still shows the last-viewed page (read-only viewing preserved). `[ASSUMED A5]`

3. **Should Batch Clean re-detect if a page has no mask at all (vs. D-03 empty-mask passthrough)?**
   - What we know: D-03 says an empty mask copies the original through. But a page with `mask is None` (never detected) is distinct from a page whose mask is empty after review.
   - What's unclear: In Batch Clean alone (no detect), should a never-detected page be skipped+copied (D-03 literal) or treated as an error?
   - Recommendation: Treat `mask is None` identically to an empty mask (copy original through) — D-03's intent is "no work to do → passthrough." Simpler and matches user expectation ("clean everything; pages with nothing to clean just copy"). Confirm at planning.

4. **Memory ceiling for large folders (assumption A1)?**
   - What we know: Each persisted mask QImage is ~W×H×4 bytes (ARGB32). A 1500×2200 page = ~13MB; 60 pages = ~780MB.
   - What's unclear: Is there a folder size where this becomes a problem on a hobbyist's 8GB machine?
   - Recommendation: v1 accepts the in-memory cost (typical chapters are 30-60 pages); document a "very large folders may use significant memory" note. Phase 5 `.mas` persistence is the long-term answer. No action this phase unless the user flags a target folder size.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Project runtime (`requires-python = ">=3.12"`) | ⚠ see note | system PATH has 3.14.2; project targets 3.12 | Run under a 3.12 venv (uv) — verify the executor's env at Wave 0 |
| PySide6 | GUI + Worker/QThreadPool/QFileDialog | ✓ (declared) | 6.7+ (pyproject) | — |
| Pillow (PIL) | Output writing (save_optimized) | ✓ (declared, 10+) | 10+ (pyproject) | — |
| OpenCV (cv2) | Non-ASCII image read in batch | ✓ (declared) | 4.9+ (pyproject) | — |
| NumPy (<2) | Mask serialization | ✓ (declared) | <2.0 (pyproject pin) | — |
| loguru | Per-page failure logging | ✓ (declared) | latest (pyproject) | — |
| pytest + pytest-qt | Tests | ✓ (declared, dev extra) | latest (pyproject) | — |
| CTD model (`comictextdetector.pt`, ~80MB) | Batch Detect | ✓ (cached after Phase 1 first run) | via `_resolve_detection_model_path` | First-run download via `download_torch_model` (CR-11 cache-check prevents re-download) |
| LaMa model (`anime-manga-big-lama.pt`, ~200MB) | Batch Clean | ✓ (cached after Phase 1 first run) | via `_resolve_inpainting_model_path` | First-run download via `download_inpainting_model` (CR-10) |

**Note on Python version:** The shell reports `python --version → 3.14.2`, but `pyproject.toml` pins `requires-python = ">=3.12"` and `numpy<2` (numpy 2.x is installed on the system python at 2.3.5, which conflicts with the pin). Phase 1 tests ran green, so the executor uses a project venv (3.12, numpy<2) — confirm at Wave 0 that the same venv is active. This is an environment note, not a Phase 2 blocker. `[VERIFIED: pyproject.toml requires-python + numpy<2; system python has numpy 2.3.5]`

**Missing dependencies with no fallback:** none. All required packages are declared; models are downloaded on first use (Phase 1 mechanism).

**Missing dependencies with fallback:** none needed.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-qt (`pytest.ini` `qt_api = pyside6`, VERIFIED) |
| Config file | `pytest.ini` (exists; markers `unit`/`gui`; `testpaths = tests`) |
| Quick run command | `pytest tests/test_core/ -x` (backend logic, no GUI — established Phase 1 sampling) |
| Full suite command | `pytest` (full suite incl. GUI smoke tests) |
| Fake-adapter pattern | `tests/test_inpainting/test_lama_adapter.py:FakeSimpleLama` (VERIFIED — records calls, returns a PIL image, no torch/weights) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROJ-02 | Export writes the displayed canvas image as PNG (compress_level=9, optimize) | unit | `pytest tests/test_core/test_image_io.py::test_save_png_kwargs -x` | ❌ Wave 0 (new) |
| PROJ-02 | Export writes JPG with quality=95 progressive | unit | `pytest tests/test_core/test_image_io.py::test_save_jpg_kwargs -x` | ❌ Wave 0 (new) |
| PROJ-02 | Export preserves original DPI/mode when format matches | unit | `pytest tests/test_core/test_image_io.py::test_preserves_dpi_mode -x` | ❌ Wave 0 (new) |
| PROJ-02 | Export Page action writes current canvas (not a re-clean) | gui | `pytest tests/test_gui_batch.py::test_export_writes_displayed_image -x` | ❌ Wave 0 (new) |
| FLOW-03 | Batch Detect stores a mask per page (D-11 persistence) | gui | `pytest tests/test_gui_batch.py::test_batch_detect_persists_masks -x` | ❌ Wave 0 (new) |
| FLOW-03 | Mask persists across page navigation (D-11 crux) | gui | `pytest tests/test_gui_batch.py::test_mask_survives_navigation -x` | ❌ Wave 0 (new) |
| FLOW-03 | Batch Clean reads persisted masks; skips empty-mask pages (D-03) | integration | `pytest tests/test_core/test_batch_runner.py::test_batch_clean_skips_empty_mask -x` | ❌ Wave 0 (new) |
| FLOW-03 | Batch Detect+Clean one-shot writes cleaned/ for all pages | integration | `pytest tests/test_core/test_batch_runner.py::test_batch_detect_and_clean -x` | ❌ Wave 0 (new) |
| FLOW-03 | Empty-mask page copies original bytes through (D-03) | unit | `pytest tests/test_core/test_image_io.py::test_passthrough_copy2 -x` | ❌ Wave 0 (new) |
| FLOW-03 | Per-page failure is non-fatal; summary returned (D-04) | integration | `pytest tests/test_core/test_batch_runner.py::test_per_page_failure_continues -x` | ❌ Wave 0 (new) |
| FLOW-03 | Cancel checks between pages; stops cleanly (D-09) | integration | `pytest tests/test_core/test_batch_runner.py::test_abort_between_pages -x` | ❌ Wave 0 (new) |
| FLOW-03 | Output written to `cleaned/` next to source (D-07) | integration | `pytest tests/test_core/test_batch_runner.py::test_output_to_cleaned_subdir -x` | ❌ Wave 0 (new) |
| FLOW-03 | Progress emits per-page count + name (D-10) | integration | `pytest tests/test_core/test_batch_runner.py::test_progress_per_page -x` | ❌ Wave 0 (new) |
| FLOW-03 | Model loaded ONCE before loop (Pitfall 3) | integration | `pytest tests/test_core/test_batch_runner.py::test_model_loaded_once -x` | ❌ Wave 0 (new) |
| FLOW-03 | Batch sets `_op_running`; actions disabled (D-08) | gui | `pytest tests/test_gui_batch.py::test_batch_sets_op_running -x` | ❌ Wave 0 (new) |
| FLOW-03 | `_op_running` cleared on batch finish/abort/error (Pitfall 7) | gui | `pytest tests/test_gui_batch.py::test_op_running_cleared_after_batch -x` | ❌ Wave 0 (new) |
| (regression) | D-11 mask persistence uses .copy() (Pitfall 2) | gui | `pytest tests/test_gui_batch.py::test_mask_persistence_uses_copy -x` | ❌ Wave 0 (new) |

### Sampling Rate
- **Per task commit:** `pytest tests/test_core/ -x` (image_io + batch_runner unit/integration tests with fake adapters — fast, no GUI, no models)
- **Per wave merge:** `pytest` (full suite incl. `tests/test_gui_batch.py` GUI tests via pytest-qt)
- **Phase gate:** Full suite green before `/gsd:verify-work`; plus manual smoke: open a real chapter folder, run Batch Detect+Clean, confirm `cleaned/` outputs visually.

### Wave 0 Gaps
- [ ] `tests/test_core/test_image_io.py` — covers PROJ-02 save kwargs, DPI/mode preservation, D-03 copy2 passthrough
- [ ] `tests/test_core/test_batch_runner.py` — covers FLOW-03 batch loop with fake adapters (FakeCTD/FakeLama recording calls), abort-between-pages, per-page failure, model-loaded-once, output-to-cleaned/
- [ ] `tests/test_gui_batch.py` — covers PROJ-02 Export action + FLOW-03 GUI wiring (mask persistence, `_op_running` gate, progress signals) via pytest-qt; reuse the `_make_window`/`_open_page`/`_paint_mask_on_canvas` helpers from `tests/test_inpainting/test_inpaint_gui.py`
- [ ] Fake-adapter fixtures (extend the `FakeSimpleLama` pattern to a `FakeDetectionModel`/`FakeInpaintModel` with the same `detect`/`inpaint` signatures) — shared fixture in `tests/conftest.py` or a new `tests/test_core/conftest.py`
- [ ] Framework install: none needed (pytest/pytest-qt/pytest-mock already declared + present from Phase 1)

*(All gaps are new test files; the fake-adapter pattern and pytest-qt fixtures are already established from Phase 1 — `tests/test_inpainting/test_lama_adapter.py:FakeSimpleLama`, `tests/test_inpainting/test_inpaint_gui.py:_make_window`.)*

## Security Domain

> `security_enforcement: true` (config). ASVS level 1. This phase reuses Phase 1's verified mitigations; the new attack surface is small (file output writing + a Save dialog).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Desktop app, no auth. |
| V3 Session Management | no | Desktop app, no sessions. |
| V4 Access Control | no | Single-user desktop. |
| V5 Input Validation | yes | **Output path validation.** The Export `getSaveFileName` path and the `cleaned/` output dir must be validated/contained — never write outside the source folder's `cleaned/` subtree. Reuse Phase 1's `Path.resolve()` discipline. The batch output path is *derived* (`source.parent / "cleaned"`), never user-supplied for the batch (D-06), which removes a path-traversal vector. `[VERIFIED: 02-CONTEXT.md D-06 + D-07]` |
| V6 Cryptography | no | No crypto. |
| V8 Data Protection | yes (minor) | Output files are user's own manga pages; no secrets. The `cleaned/` dir must not overwrite originals (D-07 guarantees a separate subdir). |
| V12 Files & Resources | yes | **File-write safety.** Output writes use `mkdir(parents=True, exist_ok=True)`; no symlink escape. D-09 cancel discipline prevents half-written files (Pitfall 4). `[VERIFIED: image_export.py:151 mkdir pattern]` |

### Known Threat Patterns for the PySide6 + image-output stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via Export save path | Tampering / Elevation | `QFileDialog.getSaveFileName` returns an OS-validated path (same T-01-01 mitigation Phase 1 uses for open). The batch output path is derived from the open folder, not user input (D-06) — no traversal vector. `[VERIFIED: main_window.py:open_image uses getOpenFileName; 02-CONTEXT.md D-06]` |
| Overwriting original source files | Tampering / Destruction | D-07 writes only to `cleaned/` subdir; originals untouched. The writer must NEVER write to `source.parent` directly. Add a guard: assert `output_dir.name == "cleaned"`. `[VERIFIED: 02-CONTEXT.md D-07]` |
| Model weight tampering (carries from Phase 1) | Tampering | Reuse `_resolve_*_model_path` (FileNotFoundError before load — T-01-04). No new model handling in Phase 2. `[VERIFIED: torch_impl.py:load path validation]` |
| Large-image DoS (carries from Phase 1) | DoS | `validate_image_size` (10000×10000 cap) applies to batch reads via the same `set_image_from_path` path. `[VERIFIED: canvas.py:MAX_IMAGE_DIMENSION]` |
| Non-ASCII path silent failure | Availability | `cv2.imdecode(np.fromfile(...))` for reads (Phase 1); PIL `Image.save(str(path))` for writes. `[VERIFIED: main_window.py:1027-1030]` |
| Half-written output on crash/cancel | Tampering / Corruption | Abort checked only between pages (Pitfall 4); `mkdir` + atomic write (write to temp + rename) is optional hardening if the user reports corruption. |

## Sources

### Primary (HIGH confidence — verified in-repo this session)
- `manga_ai_studio/gui/main_window.py` — `MainWindow`: `_op_running` gate, `_build_status_bar`, `detect_text`/`inpaint` Worker dispatch, `_run_detection_task`/`_run_inpaint_task`, `_resolve_detection_model_path`/`_resolve_inpainting_model_path`, `on_page_selected`→`reset_history`, `compute_mask_bbox`, `_refresh_action_states`. (read in full)
- `manga_ai_studio/gui/worker_thread.py` — `Worker(QRunnable)`, `WorkerSignals`, `SharableFlag`, `Abort`, `WorkerError`, the `abort_signal` constructor param + auto-injection of `abort_flag`/`progress_callback`. (read in full)
- `manga_ai_studio/gui/canvas.py` — `EditorCanvas._mask` (the per-canvas mask store), `set_mask`/`get_mask`/`apply_undo_mask`/`apply_undo_image`, `get_image_numpy`/`set_image_from_numpy` (numpy bridges w/ `.copy()`), `has_mask`/`has_mask_content`. (read in full)
- `manga_ai_studio/core/image_file.py` — `ImageFile(path, thumbnail, mask, dirty)`: the `mask: QImage | None` slot exists but is currently unused for persistence. (read in full)
- `manga_ai_studio/core/mask_editor.py` — `mask_to_numpy_binary` + `numpy_binary_to_mask_qimage` (the `.copy()`-enforcing mask serializers). (signatures + serialization helpers read)
- `manga_ai_studio/adapters/torch_impl.py` — `TorchCTDModel.detect → (mask_refined, blk_list)`, `TorchLamaModel.inpaint(image_rgb, mask_binary) → result_rgb`, lazy `load` w/ path validation. (read in full)
- `manga_ai_studio/adapters/factory.py` — `backend_factory("detection"/"inpainting", backend)`. (read in full)
- `panelcleaner/inpainting.py` — the deferred-`inpaint_page` note at lines 49-51 (confirms D-05: reimplement on the adapter, don't vendor the driver). (read in full)
- `../PanelCleaner/pcleaner/image_export.py` — `save_optimized` (suffix→format map, PNG compress_level=9, JPG quality=95 progressive, mode/DPI/compression preservation). (read in full)
- `../PanelCleaner/pcleaner/gui/processing.py:1-120` — `generate_output` orchestration shape (`check_abortion()` between steps, `progress_callback`+`abort_flag`, `multiprocessing.Pool` — the model we REJECT per D-09b). (head read)
- `pyproject.toml` — dependency list (no new Phase 2 deps), `requires-python>=3.12`, `numpy<2` pin. (read)
- `pytest.ini` + `tests/conftest.py` — `qt_api=pyside6`, `unit`/`gui` markers, `ProfileManager` fixture. (read)
- `tests/test_inpainting/test_lama_adapter.py` — `FakeSimpleLama` fake-adapter test pattern. (read)
- `tests/test_inpainting/test_inpaint_gui.py` — `_make_window`/`_open_page`/`_paint_mask_on_canvas` pytest-qt helpers. (read)

### Secondary (MEDIUM confidence — official docs, not re-fetched)
- Python stdlib `shutil.copy2` — preserves file data + metadata (mtime, permissions). `[CITED: docs.python.org/3/library/shutil]`
- PySide6 `QFileDialog.getSaveFileName` — same family as the `getOpenFileName` Phase 1 already uses. `[CITED: PySide6 docs; verified sibling API in main_window.py:open_image]`
- Pillow `Image.save` kwargs (`compress_level`, `quality`, `progressive`, `optimize`, `dpi`) — confirmed via the PanelCleaner `save_optimized` usage (Primary source). `[CITED: pillow.readthedocs + image_export.py]`

### Tertiary (LOW confidence)
- None. No claim in this research rests on an unverified web source.

## Project Constraints (from CLAUDE.md)

Extracted from `.claude/CLAUDE.md` (read this session). The planner must verify Phase 2 compliance:

- **Tech stack non-negotiable:** PySide6 (Qt6) + Python 3.12 + OpenCV + NumPy. Phase 2 uses exactly this stack — no new framework. `[VERIFIED: CLAUDE.md §Technology Stack]`
- **Windows-first, cross-platform-safe:** Avoid Windows-only APIs and hard-coded paths. Batch output paths use `pathlib.Path` (cross-platform); no Win registry/Task Scheduler. `[VERIFIED: CLAUDE.md §Constraints]`
- **Single environment preferred:** Isolated pyenvs are the fallback, not the default. Phase 2 reuses the single Phase 1 env — no new isolated env. `[VERIFIED: CLAUDE.md §Stack Patterns]`
- **PanelCleaner GPL v3 compatibility:** Derivative works must be GPL v3. The adapted `save_optimized` carries the GPL v3 provenance (it's adapted from PanelCleaner source); the file header must note this. `[VERIFIED: CLAUDE.md + ../PanelCleaner/LICENSE]`
- **GSD workflow enforcement:** Make changes only through GSD commands (`/gsd-execute-phase`). This research is part of that workflow. `[VERIFIED: CLAUDE.md §GSD Workflow]`

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages are the verified Phase 1 runtime (read in pyproject.toml + import sites); no new deps.
- Architecture: HIGH — the batch/worker/abort/mask patterns are read directly from the Phase 1 source this phase extends.
- Output writing: HIGH — `save_optimized` read in full from the in-repo PanelCleaner reference; the adaptation is mechanical.
- D-11 mask persistence: HIGH on the *problem* (verified: `ImageFile.mask` slot exists, `on_page_selected→reset_history` discards canvas state) and HIGH on the *solution shape* (save/restore at the boundary using existing `get_mask`/`set_mask`); the exact wiring details (where the save/restore calls sit relative to `reset_history`) are MEDIUM and may shift in planning.
- Pitfalls: HIGH — all grounded in the Phase 1 codebase comments and the PanelCleaner reference.

**Research date:** 2026-07-23
**Valid until:** 2026-08-23 (30 days — stable; this phase extends a frozen Phase 1 codebase and the PanelCleaner GPL v3 reference, neither of which is fast-moving)
