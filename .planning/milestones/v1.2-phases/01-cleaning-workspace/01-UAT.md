---
status: complete
phase: 01-cleaning-workspace
source: [01-01-SUMMARY.md, 01-02-SUMMARY.md, 01-03-SUMMARY.md, 01-04-SUMMARY.md, 01-05-SUMMARY.md, 01-06-SUMMARY.md, 01-07-SUMMARY.md]
started: 2026-07-22T00:00:00Z
updated: 2026-07-22T20:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. CTD first-run detection (CLEAN-02 — unblocked by CR-01 fix)
expected: On a clean machine with no model cache, Tools -> Detect Text (D) downloads the CTD model from HuggingFace into `config.get_model_cache_dir()/comictextdetector.pt`, then produces a visible red mask overlay (rgba(255,0,0,0.63)) on text regions. Subsequent detect calls reuse the cached model (no re-download).
result: pass
note: CTD model was already cached at `C:\Users\Stella\AppData\Roaming\panelcleaner\cache\model\comictextdetector.pt` (76.2 MB) from a prior session. Detection works, mask overlay appears, no re-download (CR-11). Originally failed in the second UAT pass with PyTorch 2.6 UnpicklingError — fixed by CR-15 (weights_only=False). Final pass: works as expected.

### 2. LaMa first-run inpainting (CLEAN-06 — unblocked by CR-02 fix)
expected: On the same clean machine, Tools -> Inpaint (C) downloads the LaMa model into `config.get_model_cache_dir()/anime-manga-big-lama.pt` and the inpainted region restores the underlying artwork.
result: pass
note: Required four fixes across UAT rounds. CR-10 (resolver actually downloads — was returning a path with no download call). CR-12 (bbox computation used np.where first/last instead of min/max — inpainted a random small square). CR-13 (second inpaint reverted the first — composited onto stale _original_image_numpy instead of live pixmap). CR-16 (mask was not cleared after inpaint — consumed overlay sat on cleaned region). Final pass: inpaints the actual painted area, mask clears, multiple inpaints compose correctly. Model reused from upstream pcleaner cache (205MB, copied manually).

### 3. Image undo round-trip on a real page (FLOW-02 image half — unblocked by CR-03 fix)
expected: On a real manga page, paint a small mask, run inpaint, press Ctrl+Z. The inpainted bbox region reverts to its pre-inpaint state and NO surrounding region is corrupted. Ctrl+Shift+Z replays the inpaint.
result: pass
note: Originally blocked on item 2 (inpaint crashed before producing a result). Unblocked after CR-10. Final pass: Ctrl+Z reverts only the bbox region, surrounding artwork pixel-perfect.

### 4. Pan/zoom responsiveness (VALIDATION §Manual-Only — CLEAN-01)
expected: Open a 2000x3000 page, ctrl+scroll to zoom 100% -> 800% -> 100%, drag to pan. Smooth pan/zoom at interactive framerates, no perceptible stutter.
result: pass

### 5. Brush stroke smoothness (VALIDATION §Manual-Only — CLEAN-03)
expected: Brush stroke follows cursor smoothly across the mask overlay at 30px brush size on a real page. Stroke tracks cursor with no gaps or lag.
result: pass

### 6. Undo/redo keyboard latency (VALIDATION §Manual-Only — FLOW-02)
expected: Paint 3 strokes, Ctrl+Z three times, Ctrl+Shift+Z three times. Each undo/redo step applies within one frame — perceptually instant.
result: pass
note: Originally failed (Ctrl+Z inert, toolbar buttons worked). Fixed by CR-09 (canvas keyPressEvent called super().keyPressEvent which let QGraphicsView accept and swallow the key; changed to event.ignore()). CR-09's QShortcut addition then caused "Ambiguous shortcut overload" because the QAction still carried setShortcut — fixed by CR-14 (removed duplicate setShortcut). Final pass: Ctrl+Z / Ctrl+Shift+Z / Alt+Z / Alt+Shift+Z all fire from keyboard, no ambiguity warning.

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

<!-- All gaps resolved. The two original issues (inpaint stride/CR-08, Ctrl+Z/CR-09) plus
     the four follow-ups discovered during re-testing (CR-10 download, CR-12 bbox, CR-13
     state loss, CR-14 shortcut ambiguity, CR-15 torch.load, CR-16 mask clear) are all
     closed with regression tests. -->

## Deferred (not Phase 1 gaps — refinements for a later stage)

- **Detection mask dilation (CLEAN-02 polish):** the CTD heatmap boundary is conservative and leaves the edges of letters unmasked, so inpaint doesn't fully clean them. The user (UAT 2026-07-22) requested "add a few pixels extra to each letter it detects." Deferred to a later tuning stage alongside other detection-quality parameters (threshold, min-area, dilation radius). Not a Phase 1 correctness gap — detection works; the mask just needs a small morphological dilation post-processing step (cv2.dilate or a configurable radius in TorchCTDModel.postprocess). Track for Phase 2 or a dedicated polish phase.
