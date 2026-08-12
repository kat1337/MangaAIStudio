---
status: complete
phase: 07-typesetting-tran-02-render-translated-text-into-the-page
source: [07-VERIFICATION.md]
started: 2026-08-12T00:09:47Z
updated: 2026-08-12T05:45:00Z
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
  status: resolved
  resolved_by: 07-07-PLAN.md
  resolved_at: 2026-08-12
  reason: "User reported: when vertical is enabled, roman text should render one letter above the other, not just rotated 90 degrees; rendering should be horizontal by default regardless of detected orientation"
  severity: major
  test: 1
  root_cause: "Two mechanisms: (1) render-vertical flag is `style.vertical OR payload.vertical` at box_item.py:673-680, text_renderer.py:981-988 (bake), main_window.py:3069-3076 — the detector's payload.vertical metadata auto-flips rendering; (2) `char_rotates` classifies ALL halfwidth ASCII as rotate=True (text_renderer.py:112-146, W3C convention the user overrides). Fix: render flag = `bool(style.vertical)` only (checkbox writes style.vertical not payload.vertical); flip Latin/digits to upright (rotate=False) — geometry already supports upright stacking"
  artifacts:
    - path: "manga_ai_studio/gui/box_item.py"
      issue: "D-13 OR expression auto-flips vertical"
    - path: "manga_ai_studio/gui/text_renderer.py"
      issue: "OR in bake + _ASCII_ROTATE classification"
    - path: "manga_ai_studio/gui/main_window.py"
      issue: "OR in _style_rendered_size; checkbox writes payload.vertical"
    - path: "manga_ai_studio/gui/inspector_panel.py"
      issue: "vertical read from payload"
  missing:
    - "render-flag contract: payload.vertical is metadata, not a render instruction"
    - "Latin-upright classification rule (user override of W3C rotated convention)"
  debug_session: ".planning/debug/phase7-typeset-gaps-a-e.md"
- gap_id: G-07-2
  truth: "Font dropdown search matches substring (INCLUDE) — typing part of a font name finds it (e.g. 'Wild Words' finds 'CC Wild Words')"
  status: resolved
  resolved_by: 07-12-PLAN.md
  resolved_at: 2026-08-12
  reason: "User reported (clarified): machine fonts ARE usable; the dropdown search is weird because it won't search 'CC Wild Words' for 'Wild Words' — a contains-match search option is the stopgap"
  severity: minor
  test: 1
  root_cause: "QFontComboBox built-in incremental search matches from the START of the family name only — 'CC Wild Words' is not found by 'Wild Words'. Stopgap: add a contains-match search to the font dropdown (e.g. a line-edit filter option or custom completer doing substring matching)"
  artifacts:
    - path: "manga_ai_studio/gui/inspector_panel.py"
      issue: "QFontComboBox start-of-name-only search"
  missing:
    - "contains/substring search option for the font dropdown"
  debug_session: ".planning/debug/phase7-typeset-gaps-a-e.md"
- gap_id: G-07-3
  truth: "User can select a default font (app-level default, applied to new boxes)"
  status: resolved
  resolved_by: 07-11-PLAN.md
  resolved_at: 2026-08-12
  reason: "User reported: it should let me select a default font"
  severity: major
  test: 1
  root_cause: "No app-level default font exists: TextStyle() hardcodes 'Liberation Sans' (text_style.py:32,131); new user boxes (canvas.py:2104-2108) and detected boxes (main_window.py:3903-3905) fall back to defaults. QSettings (_settings() helper, main_window.py:1873) is used only for recents. Fix: QSettings key 'defaultFontFamily' + default_style() factory in text_style.py + apply at the two new-box creation sites"
  artifacts:
    - path: "manga_ai_studio/core/text_style.py"
      issue: "hardcoded default family"
    - path: "manga_ai_studio/gui/canvas.py"
      issue: "_commit_create applies no style"
    - path: "manga_ai_studio/gui/main_window.py"
      issue: "_build_detected_boxes applies no style; QSettings convention exists for recents"
  missing:
    - "QSettings key + default-style factory + application at box-creation sites"
  debug_session: ".planning/debug/phase7-typeset-gaps-a-e.md"
- gap_id: G-07-4
  truth: "Auto-fit grows text to fit the box (big enough to fill, within bounds) — not tiny text in a large box"
  status: resolved
  resolved_by: 07-10-PLAN.md
  resolved_at: 2026-08-12
  reason: "User reported: Autofit should make the text big enough to fit not just tiny text in a massive box"
  severity: minor
  test: 2
  root_cause: "Auto-fit loops are shrink-only: base = 14*min(w,h)/100 clamped [10,28], loop only multiplies down 0.9 (text_renderer.py:536-556 horizontal; 463-486 vertical). The [10,28] base clamp acts as an unintended hard max — large boxes never grow text. Fix: add a grow phase (multiply up while fits, with a cap e.g. min(inner_w, inner_h)), keep 5px floor and iteration bound"
  artifacts:
    - path: "manga_ai_studio/gui/text_renderer.py"
      issue: "shrink-only auto-fit loop + clamp-as-max (horizontal + vertical)"
  missing:
    - "grow-to-fit phase with a growth cap in both loops"
  debug_session: ".planning/debug/phase7-typeset-gaps-a-e.md"
- gap_id: G-07-5
  truth: "Vertical alignment (align V) applies to horizontal text"
  status: resolved
  resolved_by: 07-08-PLAN.md
  resolved_at: 2026-08-12
  reason: "User reported: align V doesn't work with horizontal text"
  severity: major
  test: 2
  root_cause: "Renderer computes align_v dy correctly (text_renderer.py:560-565, 580-583) but TypesetOverlayItem.set_content (box_item.py:388-395) cancels result.origin IN FULL and re-derives position from the document-local ink rect — the dy is dropped on canvas (bake keeps it → canvas≠bake for align_v != top). Fix: add the box-relative origin delta to _ink_offset.y (dy = origin.y - box.y - inset); vertical path yields dy=0 → unchanged"
  artifacts:
    - path: "manga_ai_studio/gui/box_item.py"
      issue: "set_content origin-cancel drops align_v dy"
  missing:
    - "align_v dy term in overlay ink-offset geometry"
    - "overlay-level canvas≡bake test with align_v middle/bottom (all current equivalence tests use top → blind spot)"
  debug_session: ".planning/debug/phase7-typeset-gaps-a-e.md"
- gap_id: G-07-6
  truth: "Ctrl+Z (undo) never crashes the app"
  status: resolved
  resolved_by: 07-06-PLAN.md
  resolved_at: 2026-08-12
  reason: "User reported: the app crashed when pressing ctrl z"
  severity: blocker
  test: 3
  root_cause: "NATIVE crash — the known latent text-overlay teardown UAF (deferred-items.md) manifesting via the undo-rebuild path: style commits queue scene updates holding pointers to overlay items (box_item.py:396 update()), then Ctrl+Z → on_undo → apply_undo_boxes → canvas.set_boxes (canvas.py:1622) removes every BoxItem and drops the last Python refs (1650-1656) → shiboken synchronously deletes the C++ BoxItems mid-event-loop while pending updates still reference them → next event-loop flush dispatches paint() to a freed TypesetOverlayItem (box_item.py:331-334 drawPixmap) → pure-virtual call → abort() 0xC0000409. Heap-layout dependent (real app heap: torch/cudnn/QColorDialog/font DB). No test reproduces it (test helpers hold wrappers alive). Fix: retire removed wrappers to a graveyard released via QTimer.singleShot(0) (after UpdateRequest flush) + Shiboken.isValid guard in paint; add a refs-dropped-before-undo regression test"
  artifacts:
    - path: "manga_ai_studio/gui/canvas.py"
      issue: "set_boxes removes items + drops last refs mid-event-loop (1650-1663)"
    - path: "manga_ai_studio/gui/box_item.py"
      issue: "TypesetOverlayItem.paint drawPixmap on freed item (331-334); update() queues stale updates (396)"
    - path: "manga_ai_studio/gui/main_window.py"
      issue: "on_undo → apply_undo_boxes → set_boxes (3382, 3455)"
  missing:
    - "graveyard/delayed-deletion pattern for removed BoxItems (QTimer.singleShot(0))"
    - "Shiboken.isValid guard in TypesetOverlayItem.paint"
    - "regression test that drops item refs before on_undo()"
  debug_session: ".planning/debug/phase7-ctrl-z-crash.md"
- gap_id: G-07-7
  truth: "Mixed align V state can be overridden in multi-select (commit applies the override to all selected)"
  status: resolved
  resolved_by: 07-09-PLAN.md
  resolved_at: 2026-08-12
  reason: "User reported: align V doesn't allow me to override, it just says mixed, selected all horizontal boxes"
  severity: major
  test: 3
  root_cause: "Three stacked defects: (1) load_multi_selection replaces the combo items with only ['Mixed'] (inspector_panel.py:686-688 via _select_combo 870-877) — no Bottom/Middle/Top to pick; (2) _emit_style_align_if_changed (1163-1169) returns if EITHER axis is 'Mixed' — a real change on one combo is discarded; (3) consumer _on_inspector_style_align_committed (main_window.py:3129-3132) overwrites both axes on every box. Fix: mirror the WR-02 effect pattern — keep real items + leading 'Mixed' entry, map 'Mixed'→None on commit, per-axis _replace_align preserving untouched axes"
  artifacts:
    - path: "manga_ai_studio/gui/inspector_panel.py"
      issue: "Mixed replaces combo items; commit guard swallows sentinel (668-688, 870-877, 1163-1169)"
    - path: "manga_ai_studio/gui/main_window.py"
      issue: "both-axes overwrite (3129-3132)"
    - path: "manga_ai_studio/gui/inspector_panel.py"
      issue: "WR-02 _effect_payload None-sentinel is the working model (1210-1242)"
  missing:
    - "item-preserving Mixed presentation for align combos"
    - "sentinel→override translation on commit (Mixed→None)"
    - "per-axis _replace_align consumer (equivalent of _replace_effect)"
  debug_session: ".planning/debug/phase7-typeset-gaps-a-e.md"
