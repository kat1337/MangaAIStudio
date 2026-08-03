---
status: complete
phase: 03-text-box-detection-interaction
source: [03-06-SUMMARY.md, 03-07-SUMMARY.md, 03-08-SUMMARY.md, 03-UAT.md]
started: 2026-08-03T00:00:00Z
updated: 2026-08-03T01:30:00Z
mode: standard
purpose: "Re-verification after gap-closure (plans 03-06/07/08). Confirms the 4 user-reported symptoms from the initial 03-UAT.md are resolved. Automated suite is 257 green; these are the human-judgment items only."
result: "2 pass (03-07 detection-baseline, 03-08 mask-undo), 2 issues (03-06 resize + re-test 4 persistence) — BOTH share a single root cause: BoxItem.ItemIsMovable. One fix closes both."
fixes_under_test:
  - "03-06: CornerHandle.shape()+boundingRect() return an 18px invisible hit rect (painted handle stays 8x8). Closes: 'clicking the corner and dragging does nothing'."
  - "03-07: Detection is a non-undoable baseline (removed empty pre-detection push). Closes: 'third Ctrl+Z makes all boxes disappear'. Also WR-04 (no-op select-click no longer seeds a spurious undo entry). NOTE: the position-persistence half was found to be a misdiagnosis — positions already persisted correctly; a regression guard was added instead."
  - "03-08: Mask side pushes BEFORE-state per stroke (consistent with boxes/image). Closes: 'brush mask comes back and won't go away'. Also WR-01 (null-mask .copy() crash guarded on all 4 pops)."
---

## Current Test

[testing complete — 2 pass, 2 issues (shared root cause); proceeding to gap-closure]

## Tests

### 1. Resize corner-drag now works (was: does nothing)
expected: Click+drag a corner handle resizes the box; opposite corner stays fixed; clamps at a small minimum. The visible handle stays the small 8x8 square (only the invisible hit area enlarged).
result: issue
reported: "box does not resize, fail"
severity: major
diagnosed: true
root_cause: "The 03-06 hit-target fix shipped correctly (_HANDLE_HIT_SIZE=18, shape()+boundingRect() both return the 18px rect; offscreen probe confirms itemAt now returns CornerHandle and _begin_resize arms _resizing_box). The handlers themselves are correct (_advance_resize recomputes rect with opposite corner anchored + MIN_BOX_SIZE clamp; _commit_resize finalizes). The REAL defect: BoxItem sets ItemIsMovable (box_item.py:30) — Qt's scene-level item-move machinery then steals the mouse-drag flow on the next mouseMoveEvent, preempting _advance_resize. The canvas implements its OWN move via _moving_box (canvas.py:925-935: computes delta, setRect), so ItemIsMovable is BOTH redundant AND harmful. When the user grabs a corner, _begin_resize arms _resizing_box, but Qt's built-in move on the parent BoxItem takes over the drag → the resize never advances → 'box does not resize.' The offscreen suite missed this because tests call _begin_resize/_advance_resize DIRECTLY, bypassing Qt's scene event delivery. This is why 03-06's fix (hit area) was necessary but not sufficient — it fixed the hit-test, but the move-vs-resize event conflict remained."
fix_direction: "Remove ItemIsMovable from BoxItem (box_item.py:30) — the canvas already owns move via _moving_box. Keep ItemIsSelectable (needed for selection/handles) and ItemSendsGeometryChanges. After removal, Qt's scene will no longer steal the drag, so _resizing_box (resize) and _moving_box (move) both receive the move events as the canvas's mouseMoveEvent intends. Add a regression test that synthesizes a REAL Qt press/move/release event sequence (not a direct _advance_resize call) on a corner handle and asserts the rect changed — this is the test gap that let the bug ship. Expect this same fix to resolve the live move path too (current move also competes with ItemIsMovable, though less visibly because both move the box). Re-run re-test 1 after fix."
artifacts: [manga_ai_studio/gui/box_item.py (line 30 ItemIsMovable), manga_ai_studio/gui/canvas.py (_select_and_begin_move, mouseMoveEvent, _advance_resize)]
verification: "Offscreen probe: itemAt returns CornerHandle at corner point; _begin_resize arms _resizing_box=True, corner=BR, start rect captured. Static read: handlers correct. Live failure explained by ItemIsMovable event interception (cannot reproduce offscreen because direct handler calls bypass Qt scene event delivery)."

### 2. 3rd undo no longer wipes all boxes (was: all detected boxes vanish)
expected: After detect + move a box + inpaint, Ctrl+Z undoes the inpaint, Ctrl+Z undoes the box move (box snaps back, detected boxes stay), further Ctrl+Z continues sensibly — NOT "all boxes disappear" on the 3rd press.
result: pass
note: 03-07 fix (detection non-undoable baseline) resolved the symptom. Confirmed by user.

### 3. Mask stroke fully undoes after inpaint (was: brush mask won't go away)
expected: Paint a mask stroke, inpaint, then Ctrl+Z repeatedly. The brush mask should fully undo (stroke disappears) and NOT get stuck "coming back" on repeated undo. Undo should terminate cleanly.
result: pass
note: 03-08 fix (mask before-state push + first-stroke baseline seed + WR-01 null guard) resolved the symptom. Confirmed by user.

### 4. Moved box position persists across page round-trip
expected: Move a box to a new position, switch to another page, switch back. The box should be at the MOVED position (not reset to original). Applies to both detected and user (Alt+drag) boxes. NOTE: the executor's probe found this already worked correctly pre-fix; confirm or report the actual behavior.
result: issue
reported: "fail — moved box resets to its original location across the page round-trip"
severity: major
diagnosed: true
root_cause: "SAME ROOT CAUSE as re-test 1 (resize): BoxItem.ItemIsMovable (box_item.py:30). With ItemIsMovable set, Qt's scene performs the live move by changing the item's pos(), NOT by calling setRect(). For a QGraphicsRectItem, pos() and rect() are independent geometry channels. But boxes_snapshot() -> current_box() reads rect() (box_item.py current_box does `r = self.rect()`). So the moved position lives in pos() (visible on screen) while rect() stays at the original — the snapshot materializes the STALE rect, and the persisted ImageFile.boxes carry the original position. On restore (set_boxes), the box rebuilds from the stale rect -> 'resets to original location.' PROVEN: a BoxItem at rect (10,10,30,30) + pos(0,0); after setPos(40,40) (what Qt's ItemIsMovable does), pos()=(40,40) but rect() still (10,10,30,30), and current_box() returns (10,10,40,40) — the move is geometrically visible on screen but invisible to the snapshot. The 03-07 executor's 'misdiagnosis' conclusion was itself wrong: their probe simulated the move via item.setRect() (the custom path), which DOES update rect() — so their probe passed. They never drove the move through Qt's ItemIsMovable machinery, which is what the live app does. Same test gap as re-test 1: tests call the custom handlers directly, bypassing Qt scene event delivery."
fix_direction: "SAME FIX as re-test 1: remove ItemIsMovable from BoxItem. The canvas already owns move via _moving_box (which calls setRect, keeping rect() authoritative). Once ItemIsMovable is gone, Qt stops moving via pos(); the custom _moving_box path (setRect) becomes the sole geometry channel; current_box()/boxes_snapshot() then read the moved rect correctly; persistence saves and restores the moved position. Add a regression test that (a) drives the move through REAL Qt event delivery (synthesize press/move/release, NOT setRect), (b) round-trips the page, (c) asserts the restored position is the moved one. This is the test gap that let the bug survive two fix rounds."
artifacts: [manga_ai_studio/gui/box_item.py (line 30 ItemIsMovable + current_box reads rect), manga_ai_studio/gui/canvas.py (_moving_box uses setRect; persistence seam uses boxes_snapshot)]
verification: "Offscreen proof: BoxItem rect (10,10,30,30) + setPos(40,40) leaves rect() unchanged at (10,10,30,30); current_box() returns stale (10,10,40,40). The 03-07 probe (setRect-based) falsely passed; the live app (Qt ItemIsMovable, pos-based) fails."

## Summary

total: 4
passed: 2
issues: 2
pending: 0
skipped: 0

## Gaps

- truth: "User can resize a text box by dragging its corner handle (TEXT-03) — persists after 03-06 fix"
  status: failed
  reason: "User reported (re-test 1): box does not resize, fail. The 03-06 hit-target fix was necessary but not sufficient."
  severity: major
  test: 1
  diagnosed: true
  root_cause: "BoxItem sets ItemIsMovable (box_item.py:30). Qt's scene-level item-move machinery then steals the mouse-drag on the next mouseMoveEvent, preempting _advance_resize. The canvas implements its OWN move via _moving_box (canvas.py:925-935), so ItemIsMovable is both redundant and harmful. The 03-06 fix enlarged the hit area (so the press now correctly arms _resizing_box), but Qt's built-in move on the parent BoxItem takes over the drag, so the resize never advances. Offscreen tests missed it because they call _begin_resize/_advance_resize directly, bypassing Qt scene event delivery."
  fix_direction: "Remove ItemIsMovable from BoxItem. Keep ItemIsSelectable + ItemSendsGeometryChanges. Add a REAL-event regression test (synthesize press/move/release via Qt event delivery, not direct handler calls) asserting a corner-drag changes the rect. Likely also clarifies the live move path."
  artifacts: [manga_ai_studio/gui/box_item.py, manga_ai_studio/gui/canvas.py]
  missing: []

- truth: "A moved box's POSITION persists across a page round-trip (TEXT-03 + D-11 box persistence) — persists after 03-07 fix"
  status: failed
  reason: "User reported (re-test 4): fail — moved box resets to original location across the page round-trip. The 03-07 executor's 'misdiagnosis' conclusion was itself wrong."
  severity: major
  test: 4
  diagnosed: true
  root_cause: "SAME ROOT CAUSE as re-test 1: BoxItem.ItemIsMovable (box_item.py:30). Qt moves the live item via pos(), but current_box()/boxes_snapshot() read rect(). pos() and rect() are independent on QGraphicsRectItem. The move is visible on screen (Qt draws at pos+rect) but the snapshot materializes the stale rect -> persisted boxes carry the original position -> restore rebuilds at the original. The 03-07 probe passed because it simulated the move via setRect (updates rect); the live app moves via Qt's ItemIsMovable (updates pos). PROVEN offscreen: rect (10,10,30,30) + setPos(40,40) leaves rect() unchanged; current_box() returns stale (10,10,40,40)."
  fix_direction: "SAME FIX as re-test 1: remove ItemIsMovable from BoxItem so _moving_box (setRect) becomes the sole geometry channel. Add a regression test that drives the move via REAL Qt event delivery, round-trips the page, and asserts the restored position is the moved one. Gaps 1 and 4 share one fix."
  artifacts: [manga_ai_studio/gui/box_item.py, manga_ai_studio/gui/canvas.py]
  missing: []
