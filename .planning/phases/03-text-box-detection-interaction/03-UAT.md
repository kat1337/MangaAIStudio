---
status: testing
phase: 03-text-box-detection-interaction
source: [03-VERIFICATION.md, 03-01..05-SUMMARY.md]
started: 2026-07-29T17:00:00Z
updated: 2026-07-29T17:00:00Z
mode: standard
note: "Goal is not in User-Story format; user opted for standard (non-MVP) UAT. 4 human-verification items sourced from 03-VERIFICATION.md (the automated suite + CR-01 regression already pass; these are the perception/runtime items tests cannot judge)."
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

number: 3
name: Unified undo ordering (Ctrl+Z x3) + status feedback
expected: |
  On a page where you've done a mask stroke + a box move + an inpaint, press
  Ctrl+Z three times. The ops should reverse in chronological order (inpaint,
  then box move, then mask edit), and the status bar should flash
  "Undo: inpaint" / "Undo: box move" / "Undo: mask edit" for ~3s each.
awaiting: user response

> Note: Test 2 (resize) was logged as a major issue — the 8x8 corner handle is
> practically unhittable. It does not block this test: move/delete/Esc can still
> be checked, and undo of a box MOVE (not resize) is the relevant case here.

## Tests

### 1. Detect Text → editable green boxes on real artwork
expected: Green (#5fd068) BoxItems render over each detected text region; box overlay auto-toggles on; mask also appears.
result: pass
note: Detection + green boxes work; box overlay toggles on. (Separate observation: detector merges joint-bubble regions into one box — see Issue A below; not a Phase 3 defect.)

### 2. Alt+drag create + move + resize + delete + Esc
expected: Amber (#f5a623) dashed preview during drag; amber border + 3px selected stroke + tinted fill + 4 corner handles (8x8 viewport px); fluent move; corner resize clamps at ~8x8 scene px; Delete removes instantly with no dialog (D-12); Esc deselects.
result: issue
reported: "boxes cannot be resized either, clicking on the corner and dragging does nothing"
severity: major
diagnosed: true
root_cause: "Corner resize hit-target is too small / mis-positioned. The CornerHandle is an 8x8 viewport-px square centered ON the box corner, so ~half of it sits outside the box (reads as background/pixmap -> no-op) and the inner half overlaps the BoxItem body (-> triggers a move, not a resize). A grid probe of `scene.itemAt` around the BR handle at 1:1 zoom returns CornerHandle only for a ~6x6 central region and BoxItem/pixmap for everything at +-6px offset. The dispatch logic (canvas.py:859-864) is correct in scene coords; the problem is that an 8px affordance centered on a corner is practically unhittable on real artwork at production zoom. GUI tests pass because they synthesize clicks at the exact computed handle centre. NOT a CR-01 regression."
fix_direction: "Enlarge the effective hit area without enlarging the visual handle — e.g. give CornerHandle a larger invisible hit rect (a child QGraphicsRectItem with no pen/brush, or override shape() to return a ~16-20px rect), or apply a small-radius tolerance in the canvas hit-test (itemAt with a 3-4px margin / check handle brect explicitly before falling to BoxItem). Re-run UAT test 2 after fix."
artifacts: [manga_ai_studio/gui/box_item.py (CornerHandle), manga_ai_studio/gui/canvas.py:853-876 (hit-test dispatch)]

### 3. Unified undo ordering (Ctrl+Z x3) + status feedback
expected: On a page with a mask stroke + a box move + an inpaint, Ctrl+Z three times reverses ops in chronological order (inpaint -> box move -> mask edit); status bar flashes "Undo: {op}" for ~3s each.
result: [pending]

### 4. Per-page persistence round-trip + Ctrl+Z recover deleted box
expected: Detect boxes on page 1; Alt+drag a user box; delete a detected box. Switch to page 2, back to page 1. All box edits survive. Then delete a box and Ctrl+Z to confirm it recovers (D-12 safety).
result: [pending]

## Summary

total: 4
passed: 1
issues: 1
pending: 2
skipped: 0

## Gaps

- truth: "User can resize a text box by dragging its corner handles (TEXT-03)"
  status: failed
  reason: "User reported: boxes cannot be resized either, clicking on the corner and dragging does nothing"
  severity: major
  test: 2
  diagnosed: true
  root_cause: "8x8 viewport-px CornerHandle centered on the box corner is practically unhittable — ~half sits outside the box (background/pixmap -> no-op) and the inner half overlaps the BoxItem body (-> move instead of resize). scene.itemAt grid probe around the BR handle at 1:1 zoom returns CornerHandle only in a ~6x6 central region; BoxItem/pixmap for +-6px offsets. GUI tests pass because they click the exact computed centre. Dispatch logic (canvas.py:853-876) is correct; the fix is the hit-target geometry, not the dispatch."
  fix_direction: "Enlarge effective hit area without enlarging the visual handle: override CornerHandle.shape() to return a ~16-20px rect, OR apply a 3-4px tolerance/margin in the canvas hit-test (explicit handle brect check before falling through to BoxItem)."
  artifacts: [manga_ai_studio/gui/box_item.py, manga_ai_studio/gui/canvas.py]
  missing: []

- truth: "Detected boxes map cleanly to individual text regions (TEXT-01 quality)"
  status: info
  reason: "User observed: detector merges boxes for joint bubbles (one box covers two joined speech bubbles)."
  severity: info
  test: 1
  diagnosed: true
  root_cause: "This is CTD MODEL output, not a Phase 3 defect. grep confirms Phase 3 has NO box-merge/group/union logic — plan 03-04 only consumes result['blocks'] from the Phase 1 worker (main_window.py:1559 'D-03 merge' refers to preserving USER boxes across re-detect, not merging detected boxes). If the comic_text_detector model returns one block for a joint bubble, Phase 3 draws one box. The bounds-clamp + zero-area-drop (V5) are the only post-processing applied."
  fix_direction: "Out of Phase 3 scope. If clean per-bubble splitting is desired, options: (a) tune CTD detection threshold / use a different model checkpoint; (b) user splits the merged box via Alt+drag + Delete (the manual-correction workflow this phase builds) — which is exactly the TEXT-03 escape hatch; (c) post-process blk_list with a heuristics splitter (future). Log as a known model limitation; do NOT gap-close in Phase 3."
  artifacts: []
  missing: []
