---
status: testing
phase: 03-text-box-detection-interaction
source: [03-06-SUMMARY.md, 03-07-SUMMARY.md, 03-08-SUMMARY.md, 03-UAT.md]
started: 2026-08-03T00:00:00Z
updated: 2026-08-03T00:00:00Z
mode: standard
purpose: "Re-verification after gap-closure (plans 03-06/07/08). Confirms the 4 user-reported symptoms from the initial 03-UAT.md are resolved. Automated suite is 257 green; these are the human-judgment items only."
fixes_under_test:
  - "03-06: CornerHandle.shape()+boundingRect() return an 18px invisible hit rect (painted handle stays 8x8). Closes: 'clicking the corner and dragging does nothing'."
  - "03-07: Detection is a non-undoable baseline (removed empty pre-detection push). Closes: 'third Ctrl+Z makes all boxes disappear'. Also WR-04 (no-op select-click no longer seeds a spurious undo entry). NOTE: the position-persistence half was found to be a misdiagnosis — positions already persisted correctly; a regression guard was added instead."
  - "03-08: Mask side pushes BEFORE-state per stroke (consistent with boxes/image). Closes: 'brush mask comes back and won't go away'. Also WR-01 (null-mask .copy() crash guarded on all 4 pops)."
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

number: 1
name: Resize corner-drag now works (was: does nothing)
expected: |
  Launch the app (start.bat or `python -m manga_ai_studio`), open a page with text,
  press D (Detect Text) with Detect Boxes on so boxes appear, click a box to select it
  (4 amber corner handles appear), then click+drag any corner handle.
  The box should RESIZE following the dragged corner (the opposite corner stays fixed),
  clamping at a small minimum. Before the fix, clicking a corner did nothing.
awaiting: user response

## Tests

### 1. Resize corner-drag now works (was: does nothing)
expected: Click+drag a corner handle resizes the box; opposite corner stays fixed; clamps at a small minimum. The visible handle stays the small 8x8 square (only the invisible hit area enlarged).
result: [pending]

### 2. 3rd undo no longer wipes all boxes (was: all detected boxes vanish)
expected: After detect + move a box + inpaint, Ctrl+Z undoes the inpaint, Ctrl+Z undoes the box move (box snaps back, detected boxes stay), further Ctrl+Z continues sensibly — NOT "all boxes disappear" on the 3rd press.
result: [pending]

### 3. Mask stroke fully undoes after inpaint (was: brush mask won't go away)
expected: Paint a mask stroke, inpaint, then Ctrl+Z repeatedly. The brush mask should fully undo (stroke disappears) and NOT get stuck "coming back" on repeated undo. Undo should terminate cleanly.
result: [pending]

### 4. Moved box position persists across page round-trip
expected: Move a box to a new position, switch to another page, switch back. The box should be at the MOVED position (not reset to original). Applies to both detected and user (Alt+drag) boxes. NOTE: the executor's probe found this already worked correctly pre-fix; confirm or report the actual behavior.
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0

## Gaps

[none yet]
