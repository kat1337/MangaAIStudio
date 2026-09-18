---
status: complete
phase: 03-text-box-detection-interaction
source: [03-06-SUMMARY.md, 03-07-SUMMARY.md, 03-08-SUMMARY.md, 03-UAT.md, .planning/debug/resolved/box-resize-move.md]
started: 2026-08-03T00:00:00Z
updated: 2026-08-04T03:50:00Z
mode: standard
purpose: "Re-verification after gap-closure (plans 03-06/07/08) + final fix for the two live-only box-interaction bugs. Confirms the 4 user-reported symptoms from the initial 03-UAT.md are resolved. Automated suite is 263 green; these are the human-judgment items only."
result: "4 pass (all symptoms resolved). Re-tests 1 (resize) and 4 (move-persistence) were re-opened after gap-closure, then resolved by a final fix (brush cursor overlay swallowed the box hit-test — see .planning/debug/resolved/box-resize-move.md) and confirmed by user live UAT 2026-08-04. The earlier 'ItemIsMovable is the shared root cause' diagnosis recorded here was WRONG (it was a contributing factor, not the root cause); it has been superseded."
fixes_under_test:
  - "03-06: CornerHandle.shape()+boundingRect() return an 18px invisible hit rect (painted handle stays 8x8). Closes: 'clicking the corner and dragging does nothing'."
  - "03-07: Detection is a non-undoable baseline (removed empty pre-detection push). Closes: 'third Ctrl+Z makes all boxes disappear'. Also WR-04 (no-op select-click no longer seeds a spurious undo entry). NOTE: the position-persistence half was found to be a misdiagnosis — positions already persisted correctly; a regression guard was added instead."
  - "03-08: Mask side pushes BEFORE-state per stroke (consistent with boxes/image). Closes: 'brush mask comes back and won't go away'. Also WR-01 (null-mask .copy() crash guarded on all 4 pops)."
  - "Post-gap-closure fix (2026-08-04): brush cursor overlay (cursor_item, z=1000) swallowed the box hit-test in mousePressEvent, so neither _moving_box nor _resizing_box ever armed. Fix: new _box_item_at() filters scene hits to CornerHandle/BoxItem only; ItemIsMovable removed (canvas-owned setRect is now the sole geometry channel). Closes BOTH re-test 1 (resize) and re-test 4 (move-persistence). Confirmed by user live UAT."
---

## Current Test

[testing complete — 4 pass, 0 issues; phase ready to verify]

## Tests

### 1. Resize corner-drag now works (was: does nothing)
expected: Click+drag a corner handle resizes the box; opposite corner stays fixed; clamps at a small minimum. The visible handle stays the small 8x8 square (only the invisible hit area enlarged).
result: pass
reported: "box does not resize, fail"
severity: major
diagnosed: true
root_cause: "FINAL ROOT CAUSE (supersedes the earlier ItemIsMovable theory recorded here): EditorCanvas.mousePressEvent used a generic scene.itemAt(scene_pos, ...) to dispatch resize-vs-move. The brush cursor (cursor_item, a QGraphicsEllipseItem, z=1000) follows the mouse on every mouseMoveEvent and sits above boxes (z=100) and handles (z=150), so itemAt() returned cursor_item at the click point instead of the underlying CornerHandle. The dispatch handled only CornerHandle/BoxItem, so _resizing_box was never armed — drag had nothing to advance. The offscreen suite missed it because existing tests did not position cursor_item at the click point before pressing (no preceding mouseMoveEvent at the same coords), so itemAt() returned the handle correctly; the bug only manifested under real mouse movement. ItemIsMovable (the earlier theory) was a CONTRIBUTING factor, not the root cause — removing it alone (commit 2eae32e) broke move because the cursor swallow still prevented arming. Full RCA: .planning/debug/resolved/box-resize-move.md."
fix_direction: "APPLIED 2026-08-04: (1) new _box_item_at(scene_pos) in canvas.py iterates scene.items() z-descending and returns the first visible+enabled CornerHandle (resize priority) or BoxItem, ignoring cursor_item/preview_item, using identity QTransform() (preserves the high-zoom fix); (2) removed ItemIsMovable from BoxItem so canvas-owned setRect is the sole geometry channel. Regression test test_resize_drag_ignores_brush_cursor_overlay positions cursor_item at the click point before pressing and asserts _resizing_box arms + rect grows — FAILS on pre-fix, PASSES after."
artifacts: [manga_ai_studio/gui/canvas.py (_box_item_at + mousePressEvent call site), manga_ai_studio/gui/box_item.py (ItemIsMovable removed)]
verification: "User live UAT 2026-08-04: CONFIRMED — corner-drag resizes the box correctly. Regression test (real Qt event delivery, TRAP-compliant) passes. Full suite 263 green."

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
result: pass
reported: "fail — moved box resets to its original location across the page round-trip"
severity: major
diagnosed: true
root_cause: "FINAL ROOT CAUSE (supersedes the earlier ItemIsMovable theory recorded here): SAME as re-test 1 — the brush cursor overlay (cursor_item, z=1000) swallowed the box hit-test in mousePressEvent, so the press returned cursor_item instead of the BoxItem and _moving_box was NEVER armed. With no move armed, _moving_box.setRect never ran, boxes_modified never fired, and the moved position was never snapshotted — so on page round-trip the box restored to its original position. The earlier 'ItemIsMovable pos()/rect() divergence' theory was valid Qt mechanics but was NOT the live failure mode: it assumed the move reached Qt's ItemIsMovable machinery, but the cursor swallow meant the move never started at all. Full RCA: .planning/debug/resolved/box-resize-move.md."
fix_direction: "APPLIED 2026-08-04 (same fix as re-test 1): new _box_item_at() filters scene hits to CornerHandle/BoxItem only (ignores cursor_item); ItemIsMovable removed so canvas-owned setRect is the sole geometry channel. Now the press arms _moving_box, setRect updates rect(), boxes_modified fires on release, and the persistence seam snapshots the moved rect. Regression test test_box_drag_ignores_brush_cursor_overlay positions cursor_item at the click point before pressing and asserts the box moved — FAILS on pre-fix, PASSES after."
artifacts: [manga_ai_studio/gui/canvas.py (_box_item_at + mousePressEvent call site), manga_ai_studio/gui/box_item.py (ItemIsMovable removed)]
verification: "User live UAT 2026-08-04: CONFIRMED — moved box persists across page round-trip at the moved position. Regression test (real Qt event delivery, TRAP-compliant) passes. Full suite 263 green."

## Summary

total: 4
passed: 4
issues: 0
pending: 0
skipped: 0

## Gaps

[all resolved 2026-08-04 — both gaps shared a single root cause (brush cursor overlay swallowed the box hit-test). Fix applied; user live UAT confirmed. Full RCA in .planning/debug/resolved/box-resize-move.md. Entries below retained for traceability.]

- truth: "User can resize a text box by dragging its corner handle (TEXT-03) — persists after 03-06 fix"
  status: resolved
  resolved_at: 2026-08-04
  reason: "User reported (re-test 1): box does not resize, fail. The 03-06 hit-target fix was necessary but not sufficient."
  severity: major
  test: 1
  diagnosed: true
  root_cause: "FINAL: brush cursor overlay (cursor_item, z=1000) swallowed the box hit-test in mousePressEvent -> _resizing_box never armed. (Earlier ItemIsMovable theory was a contributing factor, not the root cause.)"
  fix_direction: "APPLIED: new _box_item_at() filters scene hits to CornerHandle/BoxItem only; ItemIsMovable removed. See test 1 above and .planning/debug/resolved/box-resize-move.md."
  artifacts: [manga_ai_studio/gui/canvas.py, manga_ai_studio/gui/box_item.py]
  missing: []
  verification: "User live UAT 2026-08-04 CONFIRMED + regression test test_resize_drag_ignores_brush_cursor_overlay passes."

- truth: "A moved box's POSITION persists across a page round-trip (TEXT-03 + D-11 box persistence) — persists after 03-07 fix"
  status: resolved
  resolved_at: 2026-08-04
  reason: "User reported (re-test 4): fail — moved box resets to original location across the page round-trip. The 03-07 executor's 'misdiagnosis' conclusion was itself wrong."
  severity: major
  test: 4
  diagnosed: true
  root_cause: "FINAL: SAME as test 1 — brush cursor overlay swallowed the box hit-test -> _moving_box never armed -> boxes_modified never fired -> moved position never snapshotted. (Earlier pos()/rect() divergence theory was valid Qt mechanics but not the live failure mode.)"
  fix_direction: "APPLIED: same fix as test 1 (_box_item_at + ItemIsMovable removed). See test 4 above and .planning/debug/resolved/box-resize-move.md."
  artifacts: [manga_ai_studio/gui/canvas.py, manga_ai_studio/gui/box_item.py]
  missing: []
  verification: "User live UAT 2026-08-04 CONFIRMED + regression test test_box_drag_ignores_brush_cursor_overlay passes."
