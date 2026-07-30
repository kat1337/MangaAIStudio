---
status: complete
phase: 03-text-box-detection-interaction
source: [03-VERIFICATION.md, 03-01..05-SUMMARY.md]
started: 2026-07-29T17:00:00Z
updated: 2026-07-29T18:30:00Z
mode: standard
note: "Goal is not in User-Story format; user opted for standard (non-MVP) UAT. 4 human-verification items sourced from 03-VERIFICATION.md. Result: 1 pass, 3 major issues (2 confirmed-diagnosed, 1 partial + 1 Phase-1 mask regression undiagnosed). All 4 tests have a definitive result."
---

## Current Test

[testing complete — 1 pass, 3 issues; proceeding to gap-closure]

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
result: issue
reported: "First Ctrl+Z inpainting undone. Second Ctrl+Z brush comes back. Third Ctrl+Z ALL boxes from automatic detection disappear including the one I moved."
severity: major
diagnosed: true
root_cause: "The unified-timeline ORDERING is actually correct (image -> boxes -> boxes), which matches the user's first two undos. The defect is the CONTENT of the third pop. Root cause reproduced live: detection pushes an EMPTY before-snapshot ([]), because at detect-time the layer genuinely had no boxes. With the before-state push convention (CR-01 fix), the BOXES stack after [detect, move] holds entries [0-boxes, 3-boxes]. Undo#2 pops the 3-box pre-move snapshot (correct — reverts the move). Undo#3 pops the 0-box pre-detection snapshot -> restores [] -> ALL detected boxes vanish. The before-state convention makes the INITIAL detection undoable, which is never desired mid-session and is what the user sees as 'my boxes disappeared.' A second contributing factor: the user also expected undo#2 to restore the brush (mask), but the box-move stamp (T) was newer than the mask-stroke stamp, so boxes correctly popped first — the user's mental model differed from the stamp ordering, but the ordering itself was right."
fix_direction: "Two-part fix. (1) Make detection a NON-undoable seeding event: in _build_detected_boxes, suppress the boxes_modified push hook around the detection set_boxes (it already has a _suppress_boxes_push guard for the restore path — extend it to the detection apply), so detection establishes the baseline WITHOUT pushing an empty entry; then the first user box edit pushes against that baseline. This mirrors how mask strokes are individually undoable but the initial mask presence is not. (2) Re-verify the cross-store stamp ordering against the user's mental model (inpaint > box-move > mask-stroke) — it matched here, but confirm status-bar labels say 'Undo: box move' etc. so the ordering is legible. Re-run UAT test 3 after fix."
artifacts: [manga_ai_studio/gui/main_window.py (_build_detected_boxes, _on_boxes_modified), manga_ai_studio/gui/canvas.py (set_boxes emit)]
verification: "Reproduced via throwaway probe simulating detect->move->inpaint then undo x3 with history.undo(); undo#3 returned a 0-box snapshot (the empty pre-detection entry), confirming the empty-push."

### 4. Per-page persistence round-trip + Ctrl+Z recover deleted box
expected: Detect boxes on page 1; Alt+drag a user box; delete a detected box. Switch to page 2, back to page 1. All box edits survive. Then delete a box and Ctrl+Z to confirm it recovers (D-12 safety).
result: issue
reported: "Pass on box EXISTENCE surviving the round-trip, BUT moving a box resets it to its original location — including drawn (user) boxes, not just detected ones. So positions don't persist; only presence does."
severity: major
diagnosed: partial
root_cause: "SUSPECTED, not yet live-confirmed (probe fixture tripped on on_page_selected's signature). Static read of the seam looks correct: on_page_selected Step 1b saves canvas.boxes_snapshot() (which reads each BoxItem.rect() live via current_box()), and the move path (canvas.py:918-931) calls setRect(new_rect) + _sync_handles(). So the moved rect SHOULD be captured at save-time. The user's symptom ('resets to original location including drawn boxes') implies the snapshot is capturing the ORIGINAL/CREATION position, not the moved one. Two candidate causes to confirm via a corrected probe or gap-closure diagnosis: (a) boxes_snapshot/ current_box is reading a cached PageBox.box rather than the live rect after a move; (b) the move-commit's before-state snapshot (CR-01 fix) is somehow being restored over the live state at page-switch. NOTE: this likely SHARES a root cause with Test 3's undo defect — both involve the before-state snapshot being treated as authoritative state. The user-box reset (not just detected) rules out a detection-only path."
fix_direction: "Diagnose in gap-closure: add a real probe that moves a BoxItem via the live move-commit path (not setRect directly), triggers on_page_selected round-trip, and inspects both the persisted ImageFile.boxes positions AND the restored canvas positions. Likely fix is on the snapshot-read side (ensure boxes_snapshot always materializes from live rect, never from a stored PageBox) OR the move-commit side (ensure the before-snapshot is push-only and never written back to canvas)."
artifacts: [manga_ai_studio/gui/main_window.py (on_page_selected Step 1b/4b), manga_ai_studio/gui/canvas.py (boxes_snapshot, move-commit), manga_ai_studio/gui/box_item.py (current_box)]
note_on_second_half: "The 'Ctrl+Z recovers a deleted box' half overlaps with Test 3's undo defect and was not separately verified."

## Summary

total: 4
passed: 1
issues: 3
pending: 0
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

- truth: "Undo of box edits reverts the edit, not the initial detection (TEXT-03 + Surface 13)"
  status: failed
  reason: "User reported: third Ctrl+Z made ALL boxes from automatic detection disappear, including the one moved. First two undos (inpaint, then brush) were correct."
  severity: major
  test: 3
  diagnosed: true
  root_cause: "Before-state push convention (CR-01 fix) makes the INITIAL detection undoable. At detect-time the layer is empty, so the boxes_modified hook pushes an empty [] snapshot. After [detect, move], BOXES stack = [0-boxes, 3-boxes]. Undo#2 pops 3-box (reverts move — correct). Undo#3 pops 0-box (restores [] — all detected boxes vanish). The unified-timeline ORDERING is correct; the bug is that detection seeded an empty undo entry instead of establishing a non-undoable baseline. Reproduced live via history.undo() probe: undo#3 returned a 0-box snapshot."
  fix_direction: "Suppress the boxes_modified push hook during detection's set_boxes (extend the existing _suppress_boxes_push guard in _build_detected_boxes to the detection apply, not just the restore) so detection establishes the baseline WITHOUT pushing an empty entry; the first user box edit then pushes against that baseline. Mirrors how mask strokes are undoable but initial mask presence is not. Also confirm status-bar 'Undo: {op}' labels so the ordering is legible to the user."
  artifacts: [manga_ai_studio/gui/main_window.py, manga_ai_studio/gui/canvas.py]
  missing: []

- truth: "Mask brush stroke is fully undoable (Phase 1 FLOW-02 regression)"
  status: failed
  reason: "User reported (Test 3 addendum): after inpainting, the brush mask comes back on the 2nd Ctrl+Z, and no matter how many more times Ctrl+Z is pressed, the brush mask NEVER goes away again."
  severity: major
  test: 3
  diagnosed: false
  root_cause: "NOT YET DIAGNOSED. This is a Phase 1 mask-undo regression surfaced during Phase 3 UAT. Suspect: the pre-existing mask-side one-behind behavior (mask pushes AFTER-state with no baseline seed — established during CR-01 scrutiny) means once the mask stack reaches a state, repeated undo can re-push or stall. OR the unified timeline's cross-store pop is re-materializing the mask from a stale checkpoint. Needs targeted reproduction: paint one stroke, inpaint, undo repeatedly, inspect _mask_undo/_mask_redo lengths at each step."
  fix_direction: "Diagnose in gap-closure (or as a Phase 1 regression fix). Likely the mask side needs the same baseline-seeding discipline as the proposed boxes fix: the first stroke should push a pre-stroke (empty/clean) baseline so undo can return to it, rather than only pushing post-stroke states. May overlap with WR-01 (None.copy() crash in on_undo when canvas mask is null)."
  artifacts: [manga_ai_studio/gui/main_window.py (_on_mask_modified, on_undo), manga_ai_studio/core/history_manager.py (pop_mask_undo)]
  missing: []

- truth: "A moved box's POSITION persists across a page round-trip (TEXT-03 + D-11 box persistence)"
  status: failed
  reason: "User reported (Test 4): box existence survives the page-2-and-back round-trip, but moving a box resets it to its original location — including drawn (user) boxes, not just detected ones."
  severity: major
  test: 4
  diagnosed: partial
  root_cause: "SUSPECTED (not live-confirmed — probe fixture tripped on on_page_selected signature). The persistence seam static-reads correct (Step 1b saves canvas.boxes_snapshot() reading live rect via current_box(); move path setRect updates rect). The symptom (positions reset to original/creation, including user boxes) implies the snapshot captures pre-move geometry. Two candidates: (a) boxes_snapshot/current_box reads a cached PageBox.box not the live rect post-move; (b) the CR-01 before-state snapshot is written back as authoritative state at page-switch. LIKELY SHARES a root cause with the Test 3 undo defect (both treat the before-state snapshot as state)."
  fix_direction: "Diagnose in gap-closure with a corrected probe driving the LIVE move-commit path + real on_page_selected round-trip; inspect both persisted ImageFile.boxes positions and restored canvas positions. Fix on the snapshot-read side (always materialize from live rect) or move-commit side (before-snapshot is push-only, never written back)."
  artifacts: [manga_ai_studio/gui/main_window.py, manga_ai_studio/gui/canvas.py, manga_ai_studio/gui/box_item.py]
  missing: []
