# Pitfalls Research

**Domain:** Manga scanlation desktop application (PySide6 + ONNX, reusing code from PanelCleaner, mokuro, manga-ocr, MangaCleaner_GPU)
**Researched:** 2026-07-11
**Confidence:** HIGH (many pitfalls observed directly in MangaCleaner_GPU source code)

## Dependency & Environment Pitfalls

### P1: torch + onnxruntime numpy version conflict
**Warning signs:** `import onnxruntime` then `import torch` crashes with numpy ABI error ("numpy.dtype size changed") or segfault on first inference.
**Prevention:** Pin `numpy<2.0` at project start. Test `import torch, onnxruntime, cv2, PySide6` together in Phase 1 BEFORE building features. If conflict is unfixable, this triggers the isolated-pyenv fallback strategy from PROJECT.md — run manga-ocr (torch) as a subprocess from the main app (onnxruntime).
**Phase:** Phase 1 (validate environment first).

### P2: CUDA provider mismatch on user machines
**Warning signs:** App works on dev machine (has CUDA), crashes or falls back silently on hobbyist machines (no NVIDIA GPU, or wrong CUDA version).
**Prevention:** MangaCleaner_GPU's `ONNXEngine` already handles this correctly: tries `CUDAExecutionProvider`, catches failure, falls back to `CPUExecutionProvider`. Keep this pattern. Never *assume* GPU. Log which provider is active (MangaCleaner_GPU does: `Engine Ready | Device: GPU/CPU`).
**Phase:** Phase 1 (inherit the pattern from ONNXEngine).

### P3: Model weight distribution for hobbyist install
**Warning signs:** .exe is 500MB+, or app crashes on first run trying to download models with no internet, or users hit HuggingFace rate limits.
**Prevention:** Do NOT bundle models in the PyInstaller binary. Ship them as separate downloads in a `models/` directory (MangaCleaner_GPU's layout). Options: (a) bundle in installer, (b) first-run download with progress bar, (c) document manual download. manga-ocr base model is ~400MB; LaMa ONNX is ~197MB. Offer a "download models" first-run wizard.
**Phase:** Phase: packaging (late), but design `Paths.get_model()` to handle missing models gracefully (MangaCleaner_GPU's AIManager logs `[X] Model Missing` — extend to prompt download).

## Qt / Canvas Pitfalls

### P4: QGraphicsView performance with large manga pages
**Warning signs:** Laggy panning/zooming on 3000×4000px pages; mask painting stutters.
**Prevention:** Manga pages are large. QGraphicsView handles this well *if* you don't force full repaints. MangaCleaner_GPU sets `SmoothPixmapTransform` — keep it. Avoid creating new QPixmap on every mouse move during brush strokes; instead, paint onto the existing QImage and call `update_mask_display()` (MangaCleaner_GPU's pattern). If still slow, consider downscaling the display pixmap while keeping full-res for processing.
**Phase:** Phase 1 (canvas foundation).

### P5: QImage memory lifetime / buffer crashes
**Warning signs:** Random segfaults when displaying images, especially after garbage collection.
**Prevention:** `QImage(buffer, ...)` does NOT copy the buffer — if the numpy array is GC'd, QImage points to freed memory. MangaCleaner_GPU's `set_image` does `QImage(cv_img.data, ...)` where `cv_img` is stored on `self` — safe because it's held. But `on_task_finished` (main_window.py:250) does `QImage(rgba.data, ...)` without `.copy()` on a local array — **this is a latent bug in MangaCleaner_GPU**. Always call `.copy()` on QImage created from transient buffers, or keep the buffer referenced.
**Phase:** Phase 1 (when lifting canvas code — fix this).

### P6: Threading violations — touching Qt objects from worker thread
**Warning signs:** Random crashes, "QObject::setParent: Parent must be in same thread", corrupted UI state.
**Prevention:** MangaCleaner_GPU's pattern is correct: `AIWorker` only touches numpy arrays and emits signals; it NEVER touches QGraphicsItems or widgets. The GUI updates happen in signal handlers on the main thread. Maintain this discipline strictly. If manga-ocr or detection needs Qt types, convert to numpy/plain data at the worker boundary.
**Phase:** Every phase that adds AI work.

### P7: Mask ↔ QImage conversion correctness
**Warning signs:** Mask appears in wrong color, wrong position, or is offset from where the user painted.
**Prevention:** MangaCleaner_GPU reads the mask back via `self.canvas.mask.bits()` → numpy → `mask_np[:,:,3]` (alpha channel as grayscale). This assumes ARGB32 format with paint in the alpha channel. When we add box-based masks or change formats, this conversion is fragile. Centralize mask ↔ numpy conversion in one tested function.
**Phase:** Phase 1–2 (mask operations).

## ML / Inference Pitfalls

### P8: LaMa tile boundary artifacts
**Warning signs:** Visible seams or color shifts at tile boundaries in cleaned images.
**Prevention:** MangaCleaner_GPU's `run_clean_logic` processes each connected blob in a tile centered on the blob, with snap-to-8 padding. This avoids most seams because each blob is inpainted in one tile. However, blobs larger than `max_tile_size` get truncated. For per-region params (our differentiator), ensure overlapping regions blend — consider feathering tile edges or using the blob-centric approach exclusively.
**Phase:** Phase 1 (cleaning) and the per-region-params phase.

### P9: manga-ocr cold-start latency
**Warning signs:** First OCR call takes 10–30 seconds (model loading); user thinks app froze.
**Prevention:** manga-ocr's `MangaOcr()` loads the transformers pipeline on construction — heavy. Pre-load the model on app startup (in a background thread) or on first page load, with a visible "loading OCR engine" indicator. MangaCleaner_GPU's `AIManager` lazy-loads and has `set_persistence` to keep models hot during batch — reuse this for OCR too. Show progress, don't freeze.
**Phase:** Phase 3–4 (OCR integration).

### P10: manga-ocr accuracy on small / curved / stylized text
**Warning signs:** OCR returns garbage or empty strings for small text, vertical text, or heavily stylized fonts.
**Prevention:** manga-ocr is trained on manga but isn't perfect. (1) This is *why* we have manual text editing — never present OCR as final. (2) For vertical text, check if manga-ocr handles it or needs image rotation pre-processing. (3) Consider OCR confidence display (if the model exposes it) to flag low-confidence boxes for user review.
**Phase:** Phase 4 (text editing).

## Project / Persistence Pitfalls

### P11: .mas format breakage on version changes
**Warning signs:** Old projects won't open after an app update; silent data loss.
**Prevention:** Put a `schema_version` in `manifest.json`. Write a migration path for each version bump. Never silently overwrite — if format changes, offer "save as new version" keeping the original. Reference how Krita/PSD handle versioned formats.
**Phase:** Phase 6 (persistence) — design versioning from day one.

### P12: Embedding vs. referencing source images
**Warning signs:** .mas files are enormous (multi-GB for a chapter) OR projects break when source images are moved/deleted.
**Prevention:** Offer two modes: (a) "reference" — store path to source image, .mas is small but breaks if image moves; (b) "embed" — copy image into .mas, large but self-contained. Default to reference for a chapter (images stay in place), embed for sharing a single page. Document this clearly.
**Phase:** Phase 6 (persistence).

## Reuse / Licensing Pitfalls

### P13: GPL contamination from PanelCleaner
**Warning signs:** PanelCleaner is GPL v3. If we copy its code verbatim into our app, our app must also be GPL v3.
**Prevention:** Check PanelCleaner's LICENSE before copying any file. If GPL, either (a) make Manga AI Studio GPL v3 too (acceptable for open source), or (b) adapt the *approach* (clean-room) without copying source. MangaCleaner_GPU's license is unknown (bundled, no LICENSE visible in `src/`) — investigate before assuming we can reuse/publish it. **mokuro is MIT**, **manga-ocr is MIT** — safe to adapt.
**Phase:** Phase 1 (decide licensing before first code copy).

### P14: Tightly-coupled source code doesn't extract cleanly
**Warning signs:** Pulling out mokuro's detector requires importing half the package; PanelCleaner's settings system is entangled with its CLI.
**Prevention:** Expect to *rewrite adapters* rather than vendor whole modules. The ARCHITECTURE.md "import and adapt" strategy means we study the source, understand the model I/O contract (input tensor shape, output format), and write our own thin wrapper around the ONNX model. Don't try to `pip install mokuro` and call into it — that drags in its whole dependency tree.
**Phase:** Phase 3 (detection integration).

## Windows-Specific Pitfalls

### P15: PyInstaller + PySide6 + onnxruntime packaging
**Warning signs:** App works in dev, packaged .exe crashes with "failed to load Qt plugin" or "onnxruntime not found" or missing DLLs.
**Prevention:** MangaCleaner_GPU is *already* a successfully packaged PySide6 + onnxruntime app (`_internal/` layout). Study its structure as the packaging template. Use `--onedir` not `--onefile` (faster startup, avoids temp-dir extraction for 200MB models). Explicitly `--collect-all onnxruntime --collect-all PySide6`. Test the packaged build on a clean Windows VM without Python installed.
**Phase:** Packaging phase (late).

### P16: Windows path length limits with model files
**Warning signs:** File not found errors on deeply nested user directories; HuggingFace cache (`~/.cache/huggingface/hub/models--kha-white--manga-ocr-base/...`) exceeds 260 chars.
**Prevention:** Enable long path support in the PyInstaller manifest. Store models in a predictable short path (MangaCleaner_GPU uses `BASE_DIR/models/`). Avoid HuggingFace's deep cache for distributed models — download to our own `models/` dir.
**Phase:** Packaging phase.

### P17: Antivirus false positives on packaged Python apps
**Warning signs:** Users report the .exe is quarantined or flagged as malware.
**Prevention:** Common with PyInstaller + Python. (1) Code-sign the binary if budget allows. (2) Document the false positive in install instructions. (3) Consider submitting to Microsoft Defender for analysis. This affects hobbyist distribution materially.
**Phase:** Packaging / release.

---
*Pitfalls research for: manga scanlation desktop application*
*Researched: 2026-07-11*
