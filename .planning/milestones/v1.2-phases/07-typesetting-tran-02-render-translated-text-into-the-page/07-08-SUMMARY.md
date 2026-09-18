---
phase: 07-typesetting-tran-02-render-translated-text-into-the-page
plan: 08
subsystem: typesetting (TRAN-02)
tags: [typesetting, gap-closure, align-v, canvas-overlay, d01-equivalence]
requires: [07-01, 07-07]
provides: [overlay-align-v-dy]
affects: [box-model, canvas, text-renderer]
tech-stack:
  added: []
  patterns: [box-relative origin delta re-added after the origin-cancel translate, overlay-level canvas≡bake pixel equivalence matrix]
key-files:
  created: []
  modified:
    - manga_ai_studio/gui/box_item.py
    - tests/test_gui_boxes.py
    - tests/test_core/test_typeset_bake.py
decisions:
  - "The dy reference is the renderer's OWN construct: dy = result.origin.y() - box_rect.y() - _OVERLAY_INSET — the inset is the renderer's constant (already imported), so the overlay re-adds exactly what layout() encoded."
  - "The dy rides the cached _ink_offset (setPos-only refresh_position) — reposition stays setPos-only (RC-1); no re-layout on the per-mousemove path (T-07-13 mitigation)."
status: complete
metrics:
  duration: ~35min
  completed: 2026-08-11
actuals:
  tokens: 3020    # chars/4 over the realized diff (12078 chars, 234 added / 2 removed lines)
  tasks: 2        # tasks completed
  commits: 3      # RED + GREEN + matrix commits
---

# Phase 7 Plan 8: align_v applies to horizontal text on the canvas (G-07-5)

**One-liner:** the align_v dy that `layout()` encodes in `result.origin.y` now survives `TypesetOverlayItem.set_content`'s origin-cancel — the canvas overlay sits at the same scene y the bake paints for top/middle/bottom — pinned by overlay-level canvas≡bake tests across the full 3x3 align matrix.

## What Was Built

- **`gui/box_item.py`** — `TypesetOverlayItem.set_content` re-adds the box-relative origin delta to the ink offset: `dy = result.origin.y() - box_rect.y() - _OVERLAY_INSET`; `_ink_offset = QPointF(ink.left() - pad, ink.top() - pad + dy)` (box_item.py:418). The origin-cancel translate (:398-401) is **byte-unchanged** (CR-01, b0cc53c preserved — the pixmap painter stays origin-cancelled). The vertical (tategaki) path's origin carries no dy (`_layout_vertical_result` returns `origin.y == box.y + inset`), so the dy term is exactly 0 there — no behavior change. The dy rides the cached `_ink_offset` through the setPos-only `refresh_position`, so every move/resize/zoom carries it without a re-layout (RC-1).
- **`tests/test_gui_boxes.py`** (12 new test cases) —
  - `test_overlay_align_v_preserves_dy`: unit contract — `_ink_offset.y() == ink.top() - pad + dy` for bottom/middle (non-zero dy), dy == 0 for top and for vertical mode. **RED-proven pre-fix** (bottom case: got 0.0, expected 40.0).
  - `test_overlay_align_v_bottom_and_middle_equals_bake_pixels`: overlay composite == bake region for the non-zero-dy cases (the top-only blind spot).
  - `test_overlay_align_v_matrix_equals_bake`: parametrized 3x3 align_v × align_h matrix at manual sizes (top×left/center/right = the historical dy=0 rows; middle/bottom = the new non-zero-dy rows).
- **`tests/test_core/test_typeset_bake.py`** — `test_bake_align_v_bottom_places_ink_below_top`: smoke guard that the bake itself carries the dy (a bake-side regression trips it even with green overlay tests).

All new tests use MANUAL sizes (`font_size_px` set, `auto_fit=False`) so the plan 07-10 grow-to-fit change (a later wave) cannot perturb the rendered geometry.

## Tasks Executed

| Task | Name | Result |
|------|------|--------|
| 1 (auto, tdd) | RED-GREEN — preserve the align_v dy in set_content | RED: bottom-case dy assertion failed with `_ink_offset.y()=0.0` vs expected `40.0` (a703f37); GREEN: dy term added, both new tests pass, full test_gui_boxes.py green (ef24afe) |
| 2 (auto) | Equivalence matrix sweep + full suite | 3x3 matrix + bake smoke added; affected modules 211 passed; full suite **701 passed, 0 failed** (4ebf00d) |

## Deviations from Plan

None — plan executed as written. (The plan's artifact note about `_OVERLAY_INSET` "joining the existing text_renderer import line" was already satisfied — the import has carried `_OVERLAY_INSET` since plan 07-01; only the dy term was added.)

## Key Decisions

- **dy reference = the renderer's own origin delta** (`result.origin.y() - box_rect.y() - _OVERLAY_INSET`), not a recomputation of `inner_h - block_h` — the overlay re-adds exactly what the layout encoded, so a future renderer-side alignment change cannot desync the two sides (single source of truth).
- **dy rides the cached `_ink_offset`** — `refresh_position` stays setPos-only; no re-layout on the per-mousemove path (T-07-13).
- **Overlay-level equivalence tests, not renderer-level** — the existing `test_canvas_style_paint_equals_bake_pixels` never instantiates the overlay, so it could not catch this defect class; the new tests go through `BoxItem.refresh_text_overlay` → `set_content` → pixmap → composite at `scenePos`.

## Verification

- RED gate: `pytest tests/test_gui_boxes.py -k "overlay_align_v or align_v" -x -q` → 1 failed pre-fix (bottom dy: 0.0 vs 40.0), 2 passed post-fix, 11 passed with the Task 2 matrix
- Affected modules: `pytest tests/test_gui_boxes.py tests/test_core/test_typeset_bake.py -x -q` → **211 passed**
- Full suite: `pytest -q` → **701 passed, 0 failed** (689 pre-plan baseline: 07-VERIFICATION.md's 687 count predates the 07-06/07-07 additions; +12 new test cases from this plan)
- Grep gate: `rg "ink.top() - pad \+ dy" manga_ai_studio/gui/box_item.py` → exactly 1 match (box_item.py:418)
- CR-01 preservation: `git diff` on the origin-cancel translate lines → no diff (byte-unchanged)
- Vertical path: dy == 0 asserted by test for `vertical=True` (tategaki geometry unchanged)
- All tests at manual sizes — plan 07-10 grow-to-fit cannot perturb them

## Threat Surface

The change maps 1:1 onto the plan's threat model — no new surface:
- T-07-12 (mitigate): the dy term is preserved in `_ink_offset`; overlay-level matrix tests pin canvas ≡ bake for every align_v × align_h combo (D-01 integrity).
- T-07-13 (mitigate): reposition stays setPos-only — the dy rides the cached `_ink_offset` (RC-1).
- T-07-SC (accept): zero new packages.

No threat flags.

## Known Stubs

None.

## Self-Check

- [x] `manga_ai_studio/gui/box_item.py` contains the dy term (grep gate 1 match)
- [x] Commits a703f37 (RED), ef24afe (GREEN), 4ebf00d (matrix) exist in `git log`
- [x] Full suite green — 701 passed, 0 failed

## Self-Check: PASSED
