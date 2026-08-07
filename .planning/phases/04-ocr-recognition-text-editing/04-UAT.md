---
status: testing
phase: 04-ocr-recognition-text-editing
source: [04-VERIFICATION.md]
started: "2026-08-07T21:30:00Z"
updated: "2026-08-07T21:30:00Z"
---

# Phase 4 UAT — OCR Recognition & Text Editing

## Current Test

number: 1
name: Text overlay legibility on real artwork
expected: |
  On a real manga page, OCR several boxes (Ctrl+R), enable the text overlay, and judge
  legibility: white+outline text readable over varied artwork with art visible beneath;
  text scales legibly on zoom in/out. Translucent overlay (fill 232,232,234,0.85 /
  outline 11,11,14,0.92 2px) is legible over light and dark artwork at 100-800% zoom.
awaiting: user response

## Tests

### 1. Text overlay legibility on real artwork
expected: |
  On a real manga page, OCR several boxes (Ctrl+R), enable the text overlay, and judge
  legibility: white+outline text readable over varied artwork with art visible beneath;
  text scales legibly on zoom in/out. Translucent overlay (fill 232,232,234,0.85 /
  outline 11,11,14,0.92 2px) is legible over light and dark artwork at 100-800% zoom.
result: [pending]

### 2. Real-model OCR end-to-end on a manga page
expected: |
  Draw a box with Alt+drag; confirm auto-OCR fires on draw-release (first run shows
  "Loading OCR model…" then fills the box with recognized Japanese text); run
  Text->Run OCR on a detected box; run OCR All (Ctrl+R) with mixed empty/edited boxes —
  confirm status-bar progress, the D-04 single + batch confirm dialogs on edited boxes
  (Cancel = no overwrite), and the error UX by breaking the model cache.
result: [pending]

### 3. Inline editor on real artwork + Japanese IME
expected: |
  Double-click a box with text: confirm a QTextEdit overlay appears on the box rect
  (inset, focused, current text populated); type a correction, Enter commits (canvas
  overlay updates, Ctrl+Z restores), Esc cancels and the box stays selected, click-away
  commits; drag during edit does NOT move the box; F2 opens the editor; with a
  translation present the editor shows the translation (focus rule); with a JP IME
  active, confirm candidates appear and text commits correctly.
result: [pending]

### 4. Inspector + badge on real artwork
expected: |
  Select a box, inspect the Inspector dock (tabbed with Tools): confirm both text fields
  + bubble # + origin/language/vertical metadata populate, empty-state copy when nothing
  selected, focus-cycle with no typing commits nothing (no spurious edited=True /
  manual-override pin), Bubble # edit shows the amber manual-override badge, and the
  Inspector refreshes after an inline-edit commit.
result: [pending]

### 5. Auto-Number RTL/LTR + preserve-manual + batch undo
expected: |
  On a multi-bubble manga page: Text->Auto-Number->RTL (Manga) assigns 1..N
  right-to-left top-to-bottom with badges at TL-outside corners; undo clears in one batch
  entry, redo restores; a manually-set Bubble # (amber border) survives re-auto
  (preserve-manual) with gaps left in the sequence; LTR (Manhwa) orders left-to-right;
  zoom keeps badges constant viewport-px while text scales.
result: [pending]

### 6. Load Translations paste + file + report + error UX
expected: |
  Text->Load Translations…: paste `[1]: first translation\n[2]: second translation\n[99]:
  no match\n[SFX -3]: *bang*`, Apply — boxes 1 and 2 fill (overlay switches to
  translation), the report shows applied + skipped counts; undo reverts in one batch
  entry; Load from File… reads a .txt into the paste area; a corrupt/non-UTF-8 file
  shows the "Couldn't read" dialog without crashing.
result: [pending]

### 7. Vertical-metadata toggle fallback
expected: |
  Toggle the Vertical checkbox in the Inspector: confirm it checks, the editor stays
  horizontal (v1 fallback), payload.vertical is preserved without crash or visual change.
result: [pending]

## Summary

total: 7
passed: 0
issues: 0
pending: 7
skipped: 0
blocked: 0

## Gaps
