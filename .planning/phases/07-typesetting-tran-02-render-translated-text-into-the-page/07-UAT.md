---
status: testing
phase: 07-typesetting-tran-02-render-translated-text-into-the-page
source: [07-VERIFICATION.md]
started: 2026-08-12T00:09:47Z
updated: 2026-08-12T00:09:47Z
---

## Current Test

number: 1
name: Real-CJK-font tategaki visual check (backstop BS1 - D-11/D-13)
expected: |
  A box with Vertical checked renders upright CJK glyphs in top-to-bottom columns flowing right-to-left from the box's top-right inner edge, with Latin letters and digits rotated 90° clockwise - on a REAL CJK font, not the Qt fallback the unit tests use
awaiting: user response

## Tests

### 1. Real-CJK-font tategaki visual check (backstop BS1 - D-11/D-13)
expected: A box with Vertical checked renders upright CJK glyphs in top-to-bottom columns flowing right-to-left from the box's top-right inner edge, with Latin letters and digits rotated 90° clockwise - on a REAL CJK font, not the Qt fallback the unit tests use
result: [pending]

### 2. Effects visual quality + canvas fluidity while dragging (backstop BS2 - D-14)
expected: Outline/glow/shadow render cleanly and legibly at 100%/150%/200% DPI, compose correctly with Auto-fit and vertical paths, and the canvas stays fluid while dragging a selected box (no per-mousemove re-layout - RC-1)
result: [pending]

### 3. Inspector styling session with a real font + color (07-05 end-of-phase human gate)
expected: Selecting a box shows its real style values; changing font/color/size/alignment/effects updates the canvas and bakes correctly; a multi-select shows Mixed until overridden; one Ctrl+Z reverses each commit ('Undo: style change' / 'Undo: font size' flashes)
result: [pending]

### 4. Bake WYSIWYG at 100% (07-05 end-of-phase human gate - D-01)
expected: File > Export Typeset... (Ctrl+Shift+B) produces a PNG sidecar whose styled text matches the canvas at zoom 100% exactly (position, font, size, color, effects, vertical mode)
result: [pending]

### 5. Prohibition review - 4 must_haves.prohibitions (descriptor-less, flagged unverified - human review recommended)
expected: LLM-judge verdicts (non-authoritative): P1 no setHtml/rich-text - SATISFIED (no setHtml call sites; only docstring mentions); P2 TextStyle never mutated in place / snapshots detach / Mixed sentinel never persists - SATISFIED (dataclasses.replace throughout, test_mixed_sentinel_never_persists passes, copy() detaches); P3 vertical never whole-block rotated / bake composites text only onto detached copy - SATISFIED (per-run rotate(90) only, bake_typeset_page works on .copy()); P4 group/style ops push exactly ONE BOXES snapshot / reposition setPos-only - SATISFIED (test_group_move_one_undo/test_group_delete_one_undo/test_style_commit_applies_to_all/test_group_move_no_relayout pass). Human confirms these are acceptable
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
