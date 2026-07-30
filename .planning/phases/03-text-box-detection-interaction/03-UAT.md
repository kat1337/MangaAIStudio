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

number: 1
name: Detect Text → editable green boxes on real artwork
expected: |
  Launch the app (start.bat or `python -m manga_ai_studio`), open a manga chapter
  folder containing a page with text, press **D** (Detect Text) with the
  **Detect Boxes** mode toggle ON.
  Green (#5fd068) BoxItems render over each detected text region; the box overlay
  action auto-toggles ON; the detection mask also appears (Phase 1 behavior).
awaiting: user response

## Tests

### 1. Detect Text → editable green boxes on real artwork
expected: Green (#5fd068) BoxItems render over each detected text region; box overlay auto-toggles on; mask also appears.
result: [pending]

### 2. Alt+drag create + move + resize + delete + Esc
expected: Amber (#f5a623) dashed preview during drag; amber border + 3px selected stroke + tinted fill + 4 corner handles (8x8 viewport px); fluent move; corner resize clamps at ~8x8 scene px; Delete removes instantly with no dialog (D-12); Esc deselects.
result: [pending]

### 3. Unified undo ordering (Ctrl+Z x3) + status feedback
expected: On a page with a mask stroke + a box move + an inpaint, Ctrl+Z three times reverses ops in chronological order (inpaint -> box move -> mask edit); status bar flashes "Undo: {op}" for ~3s each.
result: [pending]

### 4. Per-page persistence round-trip + Ctrl+Z recover deleted box
expected: Detect boxes on page 1; Alt+drag a user box; delete a detected box. Switch to page 2, back to page 1. All box edits survive. Then delete a box and Ctrl+Z to confirm it recovers (D-12 safety).
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0

## Gaps

[none yet]
