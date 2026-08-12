---
status: complete
phase: 07-typesetting-tran-02-render-translated-text-into-the-page
source: [07-VERIFICATION.md]
started: 2026-08-12T00:09:47Z
updated: 2026-08-12T00:40:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Real-CJK-font tategaki visual check (backstop BS1 - D-11/D-13)
expected: A box with Vertical checked renders upright CJK glyphs in top-to-bottom columns flowing right-to-left from the box's top-right inner edge, with Latin letters and digits rotated 90° clockwise - on a REAL CJK font, not the Qt fallback the unit tests use
result: issue
reported: "Okay, it's a pass but it's not what i expected for roman text, no matter if the detected text is vertical or horizontal, the rendering should be horizontal by default, and when it is enabled as vertical, it should render roman text in vertical one letter above the other, not just rotated 90 degrees, it should also let me use the fonts in my machine, and it should let me select a default font, this is a gap"
severity: major

### 2. Effects visual quality + canvas fluidity while dragging (backstop BS2 - D-14)
expected: Outline/glow/shadow render cleanly and legibly at 100%/150%/200% DPI, compose correctly with Auto-fit and vertical paths, and the canvas stays fluid while dragging a selected box (no per-mousemove re-layout - RC-1)
result: issue
reported: "Pass but it's weird, Autofit should make the text... well big enough to fit not just tiny text in a massive box, align V also doesn't work with horizontal text, legibility is good, and zoom works well"
severity: major

### 3. Inspector styling session with a real font + color (07-05 end-of-phase human gate)
expected: Selecting a box shows its real style values; changing font/color/size/alignment/effects updates the canvas and bakes correctly; a multi-select shows Mixed until overridden; one Ctrl+Z reverses each commit ('Undo: style change' / 'Undo: font size' flashes)
result: issue
reported: "The app crashed when pressing ctrl z, other than that it works except align V doesn't allow me to override, it just says mixed, selected all horizontal boxes."
severity: blocker

### 4. Bake WYSIWYG at 100% (07-05 end-of-phase human gate - D-01)
expected: File > Export Typeset... (Ctrl+Shift+B) produces a PNG sidecar whose styled text matches the canvas at zoom 100% exactly (position, font, size, color, effects, vertical mode)
result: pass

### 5. Prohibition review - 4 must_haves.prohibitions (descriptor-less, flagged unverified - human review recommended)
expected: LLM-judge verdicts (non-authoritative): P1 no setHtml/rich-text - SATISFIED (no setHtml call sites; only docstring mentions); P2 TextStyle never mutated in place / snapshots detach / Mixed sentinel never persists - SATISFIED (dataclasses.replace throughout, test_mixed_sentinel_never_persists passes, copy() detaches); P3 vertical never whole-block rotated / bake composites text only onto detached copy - SATISFIED (per-run rotate(90) only, bake_typeset_page works on .copy()); P4 group/style ops push exactly ONE BOXES snapshot / reposition setPos-only - SATISFIED (test_group_move_one_undo/test_group_delete_one_undo/test_style_commit_applies_to_all/test_group_move_no_relayout pass). Human confirms these are acceptable
result: pass

## Summary

total: 5
passed: 2
issues: 3
pending: 0
skipped: 0
blocked: 0

## Gaps

- gap_id: G-07-1
  truth: "Vertical mode renders Roman text upright, one letter above the other (not rotated 90°); detected-vertical or detected-horizontal text renders horizontally by default"
  status: failed
  reason: "User reported: when vertical is enabled, roman text should render one letter above the other, not just rotated 90 degrees; rendering should be horizontal by default regardless of detected orientation"
  severity: major
  test: 1
  artifacts: []
  missing: []
- gap_id: G-07-2
  truth: "Font selection exposes the machine's installed fonts"
  status: failed
  reason: "User reported: it should let me use the fonts in my machine"
  severity: major
  test: 1
  artifacts: []
  missing: []
- gap_id: G-07-3
  truth: "User can select a default font (app-level default, applied to new boxes)"
  status: failed
  reason: "User reported: it should let me select a default font"
  severity: major
  test: 1
  artifacts: []
  missing: []
- gap_id: G-07-4
  truth: "Auto-fit grows text to fit the box (big enough to fill, within bounds) — not tiny text in a large box"
  status: failed
  reason: "User reported: Autofit should make the text big enough to fit not just tiny text in a massive box"
  severity: minor
  test: 2
  artifacts: []
  missing: []
- gap_id: G-07-5
  truth: "Vertical alignment (align V) applies to horizontal text"
  status: failed
  reason: "User reported: align V doesn't work with horizontal text"
  severity: major
  test: 2
  artifacts: []
  missing: []
- gap_id: G-07-6
  truth: "Ctrl+Z (undo) never crashes the app"
  status: failed
  reason: "User reported: the app crashed when pressing ctrl z"
  severity: blocker
  test: 3
  artifacts: []
  missing: []
- gap_id: G-07-7
  truth: "Mixed align V state can be overridden in multi-select (commit applies the override to all selected)"
  status: failed
  reason: "User reported: align V doesn't allow me to override, it just says mixed, selected all horizontal boxes"
  severity: major
  test: 3
  artifacts: []
  missing: []
