---
status: testing
phase: 01-cleaning-workspace
source: [01-01-SUMMARY.md, 01-02-SUMMARY.md, 01-03-SUMMARY.md, 01-04-SUMMARY.md, 01-05-SUMMARY.md, 01-06-SUMMARY.md, 01-07-SUMMARY.md]
started: 2026-07-22T00:00:00Z
updated: 2026-07-22T00:00:00Z
---

## Current Test

<!-- OVERWRITE each test - shows where we are -->

number: 1
name: CTD first-run detection (CLEAN-02 — unblocked by CR-01 fix)
expected: |
  On a clean machine with no model cache, run the app, open a manga page, trigger
  Tools -> Detect Text (D). The CTD model downloads from HuggingFace into
  config.get_model_cache_dir()/comictextdetector.pt and detection produces a
  visible red mask overlay on text regions. Subsequent detect calls reuse the
  cached model (no re-download).
awaiting: user response

## Tests

### 1. CTD first-run detection (CLEAN-02 — unblocked by CR-01 fix)
expected: On a clean machine with no model cache, Tools -> Detect Text (D) downloads the CTD model from HuggingFace into `config.get_model_cache_dir()/comictextdetector.pt`, then produces a visible red mask overlay (rgba(255,0,0,0.63)) on text regions. Subsequent detect calls reuse the cached model (no re-download). The 4 regression tests `test_resolve_detection_model_path_*` prove the resolver code path works with the REAL vendored `download_torch_model`; this end-to-end run proves the full first-run user experience.
result: [pending]
gated_on: CR-01 fix (closed in 01-07 commit c97198b)

### 2. LaMa first-run inpainting (CLEAN-06 — unblocked by CR-02 fix)
expected: On the same clean machine, Tools -> Inpaint (C) downloads the LaMa model into `config.get_model_cache_dir()/anime-manga-big-lama.pt` and the inpainted region restores the underlying artwork. The result replaces the image layer in the bbox region; mask overlay remains visible; Preview (hold) and View -> Show Original (P) show the pre-inpaint image. The 4 regression tests `test_resolve_inpainting_model_path_*` prove the resolver code path works with the REAL vendored `get_inpainting_model_path`; this end-to-end run proves the full first-run experience.
result: [pending]
gated_on: CR-02 fix (closed in 01-07 commit 8e17f73)

### 3. Image undo round-trip on a real page (FLOW-02 image half — unblocked by CR-03 fix)
expected: On a real manga page, paint a small mask, run inpaint, press Ctrl+Z. The inpainted bbox region reverts to its pre-inpaint state and NO surrounding region is corrupted. Ctrl+Shift+Z replays the inpaint. The widened `test_inpaint_pushes_image_history`, `test_inpaint_undo_roundtrip_preserves_surrounding_region`, and `test_inpaint_finished_push_uses_bbox_slice` prove the patch shape and round-trip invariant on a synthetic 16x16 page; this run confirms perceptual correctness at realistic page sizes (2000x3000).
result: [pending]
gated_on: CR-03 fix (closed in 01-07 commit 83f1337)

### 4. Pan/zoom responsiveness (VALIDATION §Manual-Only — CLEAN-01)
expected: Open a 2000x3000 page, ctrl+scroll to zoom 100% -> 800% -> 100%, drag to pan. Smooth pan/zoom at interactive framerates, no perceptible stutter.
result: [pending]
source: 01-VALIDATION.md §Manual-Only

### 5. Brush stroke smoothness (VALIDATION §Manual-Only — CLEAN-03)
expected: Brush stroke follows cursor smoothly across the mask overlay at 30px brush size on a real page. Stroke tracks cursor with no gaps or lag.
result: [pending]
source: 01-VALIDATION.md §Manual-Only

### 6. Undo/redo keyboard latency (VALIDATION §Manual-Only — FLOW-02)
expected: Paint 3 strokes, Ctrl+Z three times, Ctrl+Shift+Z three times. Each undo/redo step applies within one frame — perceptually instant.
result: [pending]
source: 01-VALIDATION.md §Manual-Only

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps

<!-- YAML format for plan-phase --gaps consumption -->
<!-- Append only when a test returns an issue. After diagnosis, fill root_cause/artifacts/missing/debug_session. -->
