---
phase: quick-260827-0id
plan: 01
subsystem: gui-typeset-renderer
tags: [text-rendering, outline, sfx, qtextdocument, pixel-tests]
requires: [quick-260826-vhh (256px effect bounds), quick-260826-09m (measured-crop window consuming effect_padding)]
provides: [outward-ring outline semantics (two-pass silhouette-under-fill), full-width effect_padding contract]
affects: [canvas overlay, bake, export, glow/shadow halos, TypesetOverlayItem measured crop]
tech-stack:
  added: []
  patterns: [two-pass under-fill compositing (silhouette document cloned via QTextDocument.clone + Document-selection format merge)]
key-files:
  created: []
  modified:
    - manga_ai_studio/gui/text_renderer.py
    - manga_ai_studio/gui/box_item.py
    - tests/test_core/test_typeset_effects.py
decisions:
  - "Two-pass under-fill (silhouette dilated by full W via doubled-width round stroke, then pure fill on top) instead of setTextOutline — kills the inline effect and the vertical neighbor-chew with one global ordering"
  - "_paint_vertical parameterized per pass (fill_color, pen) instead of a second code path — one vertical painter serves silhouette and fill"
  - "Pure-numpy shift-min erosion in tests (no scipy dependency added)"
metrics:
  duration: ~15 min
  completed: 2026-08-27
  tasks: 2
  commits: 2
actuals:
  tokens: 5600
  tasks: 2
  commits: 2
status: complete
---

# Quick Task 260827-0id: Outline Renders Outward (grows into glyphs fixed) Summary

**One-liner:** Text outline switched from Qt's centered `setTextOutline` stroke (half the band inside the letterforms) to a two-pass silhouette-under-fill that grows the ring strictly OUTWARD by the full width, with `effect_padding` reserving the full width for canvas/bake/export parity.

## What Was Built

**Task 1 (RED, `4035d2c`) — pixel-probe regression tests** (`tests/test_core/test_typeset_effects.py`):
- `test_outline_ring_extends_outward_horizontal` — the `[ceil(0.6W)+1 .. floor(0.9W)]` = 6..7 px band past each cardinal side of the plain-fill bbox must hold outline pixels (W=8). RED on unfixed code: 0 px (legacy reach ~W/2=4).
- `test_outline_never_eats_glyph_interior` ("AAA") — zero outline-colored px inside the plain-fill mask eroded by 3 px (`_eroded_mask`, pure-numpy shift-min, no scipy). RED: 2 contaminated px.
- `test_outline_vertical_stack_keeps_neighbor_fill_pure` ("あA", tategaki) — same purity contract; locks global silhouette-before-fill ordering. RED: 9 contaminated px.
- All 6 pre-existing tests in the file stayed green during RED; stale mechanism prose rewritten to outward semantics.

**Task 2 (GREEN, `5d83655`) — renderer switch** (`manga_ai_studio/gui/text_renderer.py`, `manga_ai_studio/gui/box_item.py`):
- `_paint_outline_pass`: outline-color SILHOUETTE of the whole run (outline color as fill + doubled-width round cap/join stroke == true Minkowski dilation by W); `None` pen short-circuits before any cloning (width 0/disabled byte-equivalent).
- `_formatted_clone`: `QTextDocument.clone()` + Document-selection merge of ONLY foreground+outline — fonts/alignment/wrap/block margins ride along untouched.
- `_build_document` fill-canonical (both former centered-stroke sites accounted for: builder pen removed; `_char_document` retained as the generic variant factory); `_paint_vertical` parameterized `(painter, result, style, fill_color, pen)` and driven twice.
- `_paint_fill_pass` is the ordered composite (ALL silhouettes before ANY fill) — `paint()` and `_draw_effects` call sites unchanged, so canvas, glow/shadow halos, bake, and export move together (D-01).
- `effect_padding` reserves the FULL `width_px` (was half) — still the ONE shared function behind `TypesetOverlayItem.set_content`'s measured-crop window and `_draw_effects`' surface rect; 256px outlines stay clip-free (T-Q01-01 bounded-allocation guards remain upstream and engaged).
- `box_item.py`: docstring-only "outline half-width" -> full width fix.

## Verification

- Task-level: `test_typeset_effects.py` 6 passed RED -> 9 passed GREEN; targeted `test_gui_boxes.py` + `test_gui_sfx_editing.py` + `test_gui_export.py` 275 passed.
- Full pinned suite (`C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe -m pytest -q`): **1188 passed, 0 failed** (baseline 1184 + 3 new probes; strictly net-positive).
- Source-consistency greps: `_outline_pen` confined to definition + `_paint_outline_pass`; `_build_document` body has 0 pen references; no stale "half-width" prose anywhere.
- T-Q01-02 defensive parses unchanged (`_outline_pen`/`effect_padding` still coerce; the clone path consumes only validated values). T-Q01-03: no package installs.

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Notes

- `test_no_ghost_after_undo_and_scroll` failed during the targeted GUI run; **proven pre-existing** by running it at baseline commit `1e16c41` in a detached temp worktree (failed identically — mask-canvas viewport-grab timing, no text-renderer involvement; documented as the known flake in the plan and STATE.md). It passed in the final full-suite run. Temp worktree removed; no repo state touched (no stash/clean/reset used).

## Threat Flags

None — no new security-relevant surface; the only trust-boundary change (style dict -> effect_padding/clone path) consumes exclusively values `_outline_pen` already validated (T-Q01-02 disposition kept).

## Self-Check: PASSED

- Files modified exist: `manga_ai_studio/gui/text_renderer.py`, `manga_ai_studio/gui/box_item.py`, `tests/test_core/test_typeset_effects.py` — FOUND.
- Commits exist: `4035d2c` (test RED), `5d83655` (fix GREEN) — both FOUND in `git log`.
