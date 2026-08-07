---
status: testing
phase: 04-ocr-recognition-text-editing
source: [04-VERIFICATION.md]
started: "2026-08-07T21:30:00Z"
updated: "2026-08-07T22:05:00Z"
---

# Phase 4 UAT — OCR Recognition & Text Editing

## Current Test

number: 2
name: Real-model OCR end-to-end on a manga page
expected: |
  Draw a box with Alt+drag; confirm auto-OCR fires on draw-release (first run shows
  "Loading OCR model…" then fills the box with recognized Japanese text); run
  Text->Run OCR on a detected box; run OCR All (Ctrl+R) with mixed empty/edited boxes —
  confirm status-bar progress, the D-04 single + batch confirm dialogs on edited boxes
  (Cancel = no overwrite), and the error UX by breaking the model cache.
awaiting: user response

## Tests

### 1. Text overlay legibility on real artwork
expected: |
  On a real manga page, OCR several boxes (Ctrl+R), enable the text overlay, and judge
  legibility: white+outline text readable over varied artwork with art visible beneath;
  text scales legibly on zoom in/out. Translucent overlay (fill 232,232,234,0.85 /
  outline 11,11,14,0.92 2px) is legible over light and dark artwork at 100-800% zoom.
result: issue
reported: "Text detection works as expected, but the text is in one location on the image, i can't actually see if it's black or white because it just looks white, also doesn't seem to scale much, it does get closer and further with zoom but that's it, it doesn't seem to scale or move with the box when the box is moved either"
severity: major

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
issues: 1
pending: 6
skipped: 0
blocked: 0

## Gaps

- truth: "Text overlay follows box geometry: overlay text appears ON the box rect and moves/scales with the box on zoom and drag"
  status: failed
  reason: "User reported: text is in one location on the image (does not move with the box); does not scale with zoom (only gets closer/further); legibility unjudgeable (appears solid white, outline not visible)"
  severity: major
  test: 1
  artifacts: [manga_ai_studio/gui/box_item.py, manga_ai_studio/gui/canvas.py]
  missing: [refresh_text_overlay call in _sync_handles, zoom font clamp, zoom-scaled outline pen]
  diagnosis: |
    RC-1: overlay pos set ONLY inside refresh_text_overlay (box_item.py:477); _sync_handles
    (box_item.py:379-397) repositions handles+badge but never the overlay. Canvas moves boxes
    via setRect (canvas.py:1022) and syncs via _sync_handles on move/resize/zoom
    (1022-1023, 1597-1598, 1618-1619, 1445-1453). Measured: after setRect(150,150,...)+_sync_handles,
    overlay sceneBoundingRect (23,23,217,30) vs box (149,149,202,102) — intersection 0.0.
    RC-2: UI-SPEC §16 [10,28] viewport-px font clamp unimplemented — flat 14 scene px
    (box_item.py:104); default fit-to-window zoom ~0.3-0.5 (main_window.py:1009) renders
    text at 4-7 device px.
    RC-3: 2px outline pen in scene units scales down with zoom — dark pixels 2710@1.0 ->
    260@0.5 -> 0@0.25 (sub-pixel AA invisibility). Cosmetic pens not honored by outline
    renderer (ruled out). Fix: 2/zoom scene px outline.
    Test gap: test_text_overlay_uses_outlined_text_format asserts format only (never render);
    no test asserts overlay position after setRect move/resize/zoom.