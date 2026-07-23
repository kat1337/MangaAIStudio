---
status: diagnosed
phase: 01-cleaning-workspace
source: [01-01-SUMMARY.md, 01-02-SUMMARY.md, 01-03-SUMMARY.md, 01-04-SUMMARY.md, 01-05-SUMMARY.md, 01-06-SUMMARY.md, 01-07-SUMMARY.md]
started: 2026-07-22T00:00:00Z
updated: 2026-07-22T12:00:00Z
---

## Current Test

[testing paused — 3 items outstanding (items 2, 3, 6); items 1, 4, 5 passed]

## Tests

### 1. CTD first-run detection (CLEAN-02 — unblocked by CR-01 fix)
expected: On a clean machine with no model cache, Tools -> Detect Text (D) downloads the CTD model from HuggingFace into `config.get_model_cache_dir()/comictextdetector.pt`, then produces a visible red mask overlay (rgba(255,0,0,0.63)) on text regions. Subsequent detect calls reuse the cached model (no re-download).
result: pass
note: CTD model was already cached at `C:\Users\Stella\AppData\Roaming\panelcleaner\cache\model\comictextdetector.pt` (76.2 MB) from a prior session, so the first-run download path was not re-exercised. Detection itself works and the mask overlay appeared. Resolver regression tests in 01-07 cover the first-run download path.

### 2. LaMa first-run inpainting (CLEAN-06 — unblocked by CR-02 fix)
expected: On the same clean machine, Tools -> Inpaint (C) downloads the LaMa model into `config.get_model_cache_dir()/anime-manga-big-lama.pt` and the inpainted region restores the underlying artwork.
result: issue
reported: "Does not work. Traceback (most recent call last): File manga_ai_studio/gui/main_window.py, line 1225, in inpaint — image_rgb = self.canvas.get_image_numpy(); File manga_ai_studio/gui/canvas.py, line 490, in get_image_numpy — arr = np.frombuffer(bytes(ptr), dtype=np.uint8).reshape(qimg.height(), qimg.width(), 3); ValueError: cannot reshape array of size 9347852 into shape (2081,1497,3)"
severity: blocker
test_page_size: 2081 x 1497

### 3. Image undo round-trip on a real page (FLOW-02 image half — unblocked by CR-03 fix)
expected: On a real manga page, paint a small mask, run inpaint, press Ctrl+Z. The inpainted bbox region reverts to its pre-inpaint state and NO surrounding region is corrupted. Ctrl+Shift+Z replays the inpaint.
result: blocked
blocked_by: prior-phase
reason: "Cannot test — blocked on item 2 (inpaint crashes before producing a result, so there is no inpaint op to undo)."

### 4. Pan/zoom responsiveness (VALIDATION §Manual-Only — CLEAN-01)
expected: Open a 2000x3000 page, ctrl+scroll to zoom 100% -> 800% -> 100%, drag to pan. Smooth pan/zoom at interactive framerates, no perceptible stutter.
result: pass

### 5. Brush stroke smoothness (VALIDATION §Manual-Only — CLEAN-03)
expected: Brush stroke follows cursor smoothly across the mask overlay at 30px brush size on a real page. Stroke tracks cursor with no gaps or lag.
result: pass

### 6. Undo/redo keyboard latency (VALIDATION §Manual-Only — FLOW-02)
expected: Paint 3 strokes, Ctrl+Z three times, Ctrl+Shift+Z three times. Each undo/redo step applies within one frame — perceptually instant.
result: issue
reported: "Ctrl+Z not doing anything but undo and redo mask buttons work. Toolbar buttons function correctly; only the keyboard shortcut is inert."
severity: major

## Summary

total: 6
passed: 3
issues: 2
pending: 0
skipped: 0
blocked: 1

## Gaps

- truth: "LaMa inpainting runs end-to-end and restores artwork in the masked bbox region (CLEAN-06)"
  status: failed
  reason: "User reported: ValueError: cannot reshape array of size 9347852 into shape (2081,1497,3) in canvas.py:490 get_image_numpy(). The QImage RGB888 buffer includes per-row 4-byte-alignment stride padding (1497*3=4491 bytes/row, padded to 4492; 4492*2081=9,347,852 actual vs 9,342,891 assumed). np.frombuffer(...).reshape(H,W,3) assumes contiguous unpadded bytes and fails for any image whose width*3 is not a multiple of 4. Tests missed it because synthetic test images (e.g. 16x16) have widths that are multiples of 4, so no padding is added."
  severity: blocker
  test: 2
  root_cause: "canvas.py:484-494 get_image_numpy() reshapes the raw QImage bits buffer as (H,W,3) without accounting for Qt's per-scanline 4-byte alignment padding (qimg.bytesPerLine() >= width*3). Same bug class likely affects set_image_from_numpy() and any other numpy<->QImage bridge that reshapes without stride handling."
  artifacts:
    - path: "manga_ai_studio/gui/canvas.py"
      issue: "get_image_numpy (line 484-494) and likely set_image_from_numpy — reshape assumes unpadded buffer; must slice per-row using qimg.bytesPerLine() stride, or convert to a contiguous format first"
  missing:
    - "Fix get_image_numpy to respect qimg.bytesPerLine() stride (slice width*3 bytes per row, skip the padding tail)"
    - "Audit set_image_from_numpy and mask_to_numpy_binary/numpy_binary_to_mask_qimage for the same stride bug"
    - "Add regression test with a non-4-aligned width (e.g. 1497, 501, 33) asserting reshape succeeds and pixel values are correct"
  debug_session: ""

- truth: "Ctrl+Z / Ctrl+Shift+Z / Alt+Z / Alt+Shift+Z keyboard shortcuts fire the undo/redo handlers (FLOW-02 keyboard path)"
  status: failed
  reason: "User reported: Ctrl+Z not doing anything, but the Undo/Redo toolbar buttons work. The handlers are wired correctly (action_undo_image.triggered.connect(self.on_undo_image) AND QShortcut(QKeySequence('Ctrl+Z'), self).activated.connect(self.on_undo_image) at main_window.py:746-762), so the failure is an event-dispatch/focus issue: either the canvas's keyPressEvent is consuming Ctrl+Z before the QShortcut fires, or a QShortcut context setting prevents it from reaching the handler when the canvas has focus. The toolbar button path does not depend on keyboard focus, which is why it works."
  severity: major
  test: 6
  root_cause: "Likely canvas QGraphicsView keyPressEvent shadowing Ctrl+Z, OR QShortcut default context (Qt.WindowShortcut) not firing when a child QGraphicsView has focus. Toolbar actions work because they're triggered by mouse, not keyboard. Code at main_window.py:751-762 sets QShortcut(keys, self) without explicitly setting Qt.ApplicationShortcut context — on some platforms the canvas's focus eats the shortcut."
  artifacts:
    - path: "manga_ai_studio/gui/main_window.py"
      issue: "_wire_history_actions lines 755-762 — QShortcut context may need Qt.ApplicationShortcut, OR canvas keyPressEvent needs to ignore() Ctrl+Z so it propagates"
    - path: "manga_ai_studio/gui/canvas.py"
      issue: "keyPressEvent may be consuming Ctrl+Z instead of calling event.ignore() to let the QShortcut handle it — needs investigation"
  missing:
    - "Reproduce in a pytest-qt test: focus the canvas, send QKeyEvent for Ctrl+Z, assert on_undo_image is called"
    - "Fix: either set QShortcut context to Qt.ApplicationShortcut, OR ensure canvas keyPressEvent calls event.ignore() for unhandled key combos so the shortcut propagates"
  debug_session: ""

## Deferred (not Phase 1 gaps — refinements for a later stage)

- **Detection mask dilation (CLEAN-02 polish):** the CTD heatmap boundary is conservative and leaves the edges of letters unmasked, so inpaint doesn't fully clean them. The user (UAT 2026-07-22) requested "add a few pixels extra to each letter it detects." Deferred to a later tuning stage alongside other detection-quality parameters (threshold, min-area, dilation radius). Not a Phase 1 correctness gap — detection works; the mask just needs a small morphological dilation post-processing step (cv2.dilate or a configurable radius in TorchCTDModel.postprocess). Track for Phase 2 or a dedicated polish phase.

