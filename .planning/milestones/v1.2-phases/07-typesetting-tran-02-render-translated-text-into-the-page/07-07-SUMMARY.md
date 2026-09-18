---
phase: 07-typesetting-tran-02-render-translated-text-into-the-page
plan: 07
subsystem: ui
tags: [typesetting, vertical, tategaki, text-renderer, inspector, style]
requires:
  - phase: 07-typesetting-tran-02-render-translated-text-into-the-page
    provides: "plan 07-06 graveyard + paint-guard (teardown UAF fixes)"
provides:
  - "Render vertical flag = bool(style.vertical) ONLY at box_item.refresh_text_overlay, text_renderer.bake_typeset_page, main_window._style_rendered_size — detector payload orientation is metadata, never a render instruction"
  - "Inspector Vertical checkbox reads/writes style.vertical (single + multi select); never constructs payloads (payload stays None on never-OCR'd boxes)"
  - "Latin letters/digits stack UPRIGHT in vertical mode (user override of the W3C rotated-Latin convention); halfwidth ASCII punctuation + brackets/dashes still rotate"
  - "7 tests re-asserted to the new contract (never deleted): preflagged-box horizontal-by-default with bake spy, style-driven toggle/checkbox/live, style-seeded inspector loads"
affects: [07-08, 07-09, 07-10, 07-11, 07-12, verify-work, UAT]
actuals:
  tokens: 7807
  tasks: 3
  commits: 3
tech-stack:
  added: []
  patterns:
    - "Single-expression render flag: bool(style.vertical) at ALL render sites (canvas overlay, bake, size probe) — no divergence window"
    - "Dataclasses.replace style writes (_replace_style) for the vertical toggle — same Pitfall-1 discipline as the other style commits"
    - "Classification-set split: _ASCII_UPRIGHT subtracted from the rotate set so punctuation-only rotation survives"
key-files:
  created: []
  modified:
    - manga_ai_studio/gui/box_item.py
    - manga_ai_studio/gui/text_renderer.py
    - manga_ai_studio/gui/main_window.py
    - manga_ai_studio/gui/inspector_panel.py
    - tests/test_gui_boxes.py
    - tests/test_gui_inspector_styling.py
    - tests/test_core/test_typeset_layout.py
key-decisions:
  - "G-07-1 contract implemented as user-locked: payload vertical field is export metadata ONLY; rendering flips exclusively on style.vertical (horizontal by default for ALL boxes)"
  - "Vertical-mode roman text renders upright one letter above the other (_ASCII_UPRIGHT); halfwidth ASCII punctuation + _ROTATE_EXTRA keep rotating (typographic convention)"
  - "The checkbox toggle never touches the payload — _ensure_payload construction removed from _on_inspector_vertical_committed (WR-01 preserved)"
patterns-established:
  - "Render metadata vs render instruction separation: detector/export fields never cross into the render decision; regression-pinned by the preflagged-box horizontal-by-default test"
requirements-completed: [TRAN-02]
coverage:
  - id: D1
    description: "Render vertical flag is bool(style.vertical) ONLY at all three render sites; preflagged (payload vertical=True) boxes render horizontal by default"
    requirement: TRAN-02
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_preflagged_box_renders_horizontal_by_default"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_vertical_checkbox_live"
        status: pass
    human_judgment: false
  - id: D2
    description: "Inspector Vertical checkbox reads/writes style.vertical (single + multi select); a never-OCR'd box's payload stays None after the toggle; one Ctrl+Z restores the pre-toggle style"
    requirement: TRAN-02
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_vertical_toggle_writes_style_and_never_constructs_payload"
        status: pass
      - kind: unit
        ref: "tests/test_gui_inspector_styling.py#test_load_multi_selection_bare_payload_defensive"
        status: pass
    human_judgment: false
  - id: D3
    description: "Latin letters/digits stack upright in vertical mode (one letter above the other); ASCII punctuation + brackets still rotate; CJK unchanged"
    requirement: TRAN-02
    verification:
      - kind: unit
        ref: "tests/test_core/test_typeset_layout.py#test_vertical_classification"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_typeset_layout.py#test_vertical_rotated_advance"
        status: pass
    human_judgment: false
duration: 68min
completed: 2026-08-11
status: complete
---

# Phase 07 Plan 7: Vertical Render Contract — Horizontal-by-Default, Upright-Stacked Roman Summary

**G-07-1 closure: the render vertical flag is `bool(style.vertical)` ONLY at all three render sites (canvas overlay, bake, size probe), the Inspector checkbox reads/writes `style.vertical` without ever touching payloads, and Latin letters/digits stack upright one above the other in vertical mode — with 7 tests re-asserted to the new contract.**

## Performance

- **Duration:** 68 min
- **Started:** 2026-08-11T22:30:00Z
- **Completed:** 2026-08-11T23:38:00Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- **Render flag contract enforced:** `vertical = bool(style.vertical)` at `refresh_text_overlay` (box_item.py), `bake_typeset_page` (text_renderer.py), and `_style_rendered_size` (main_window.py) — the D-13 OR with the payload field is deleted everywhere (including its divergence-window comments). A CTD pre-flagged box (`payload.vertical=True`, style None) renders HORIZONTAL by default, pinned by `test_preflagged_box_renders_horizontal_by_default` (renamed + re-asserted) with a bake spy capturing `vertical=False`.
- **Style-driven checkbox:** `_on_inspector_vertical_committed` writes `style.vertical` via `_replace_style` (dataclasses.replace, Pitfall 1) and no longer calls `_ensure_payload()` — a never-OCR'd box's payload stays None (pinned by `test_vertical_toggle_writes_style_and_never_constructs_payload`, renamed). Inspector single-select (:545) and multi-select (:698-703) loads read `style.vertical` with a style-None → False fallback; tooltip refreshed (keeps 'tategaki', no 'Coming soon').
- **Upright-Roman classification:** `_ASCII_UPRIGHT` (0-9, A-Z, a-z) split from `_ASCII_ROTATE` (halfwidth ASCII punctuation minus letters/digits keeps rotating); `_ROTATE_EXTRA` unchanged. Module/char_rotates/layout_vertical docstrings state the upright-Roman rule (user override of the W3C rotated-Latin convention). Geometry untouched — upright stacking already works via the width-based column extent.
- **Export-metadata sites byte-unchanged:** project_io.py:201 ('vertical' key), ocr_export.py:177 (block 'vertical'), image_ops.py:150/277/407 (transform preservation) — the payload vertical field remains the detector/export metadata.
- **Full suite:** 689 passed, 0 failed with the pinned interpreter (post-07-06 baseline; all changes are updates, zero new tests).

## Task Commits

Each task was committed atomically:

1. **Task 1: render flag = bool(style.vertical) ONLY at all three render sites** - `d91ccdd` (feat; includes the RED test rename/re-assert + GREEN three-site edit in one task commit)
2. **Task 2: Inspector checkbox reads/writes style.vertical (single + multi)** - `22a7a1b` (feat)
3. **Task 3: Latin letters/digits upright in vertical mode** - `2717dbb` (feat)

## Files Created/Modified

- `manga_ai_studio/gui/box_item.py` - `refresh_text_overlay`: OR → `bool(style.vertical)` with G-07-1 comment (payload field = export metadata only)
- `manga_ai_studio/gui/text_renderer.py` - `bake_typeset_page` OR → `bool(style.vertical)`; `_ASCII_UPRIGHT`/`_ASCII_ROTATE` split; char_rotates + module + layout_vertical docstrings updated
- `manga_ai_studio/gui/main_window.py` - `_style_rendered_size` OR → `bool(style.vertical)`; `_on_inspector_vertical_committed` writes style via `_replace_style`, payload write + `_ensure_payload` removed
- `manga_ai_studio/gui/inspector_panel.py` - single/multi vertical loads read `style.vertical`; tooltip + module docstring refreshed
- `tests/test_gui_boxes.py` - `test_preflagged_box_renders_horizontal_by_default` (renamed, + bake spy), `test_vertical_toggle_writes_style_and_never_constructs_payload` (renamed), `test_vertical_checkbox_live` (style-driven), `test_inspector_load_box_populates_fields` (style-seeded)
- `tests/test_gui_inspector_styling.py` - `test_load_multi_selection_bare_payload_defensive` builds the differing box via `TextStyle(vertical=True)`
- `tests/test_core/test_typeset_layout.py` - `test_vertical_classification` + `test_vertical_rotated_advance` re-asserted to the upright-Latin contract

## Decisions Made

- **G-07-1 contract implemented per the user override (UAT-locked):** the payload vertical field is pure export metadata; rendering is horizontal by default for every box; vertical mode renders roman text upright, one letter above the other. D-11's W3C rotated-Latin convention is NOT re-litigated — the override is recorded in the UAT.
- **The checkbox is a style control:** it reads/writes `style.vertical` and never constructs payloads — WR-01's lazy-construction side effect removed from the toggle (the `_ensure_payload` call is gone from main_window entirely).
- **Classification split by subtraction:** `_ASCII_ROTATE = 0x21..0x7F - _ASCII_UPRIGHT` keeps the punctuation set exact without hand-listing 84 code points.

## Deviations from Plan

### Auto-fixed Issues

**1. [Test-contract adjustment during GREEN — upright-Latin geometry assertion]**
- **Found during:** Task 3 (`test_vertical_rotated_advance`)
- **Issue:** The plan's literal assertion "A1 place upright (rotate False, square-ish w >= h - tolerance)" cannot hold on the real font stack: probed with the renderer's own `_style_font` path, Latin line-box height (15.62 px) exceeds the advance width (A: 9.33 px, 1: 7.78 px) at 14 px — upright Latin is NEVER square-ish (CJK 14×14 is the only square geometry). Same class of metrics mismatch 07-03 documented for CJK.
- **Fix:** Replaced the square-ish assertion with the observable that actually distinguishes upright from rotated in this geometry: the column EXTENT. Upright chars contribute their WIDTH (extent=w → placed box flush at the column's left edge, x≈0 with align_h left); rotated chars contribute their HEIGHT (extent=h → centered with x offset beyond the glyph's own width, x > w). Kept the height>width + height-based-advance assertions on the rotated '!' sample and the unchanged CJK square assertion. Documented the reasoning in the test docstring.
- **Files modified:** tests/test_core/test_typeset_layout.py
- **Verification:** RED failed pre-fix at the rotate assertions; GREEN passes; full layout module 18/18; full suite 689/0
- **Committed in:** 2717dbb (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 test-contract adjustment)
**Impact on plan:** No scope creep — the fix is an assertion-metrics correction, not a behavior change. All plan intent (upright flags, rotated punctuation, height-based advance, CJK unchanged) is preserved and covered.

## Issues Encountered

- **Task 1 → Task 2 transitional state:** after the three render sites flipped to `bool(style.vertical)` (Task 1), `test_vertical_checkbox_live` failed until Task 2 converted the toggle to write `style.vertical` — an expected intermediate incompatibility (the test locked the old payload-driven toggle; the plan's Task 1 verify filter includes tests Task 2 re-asserts). Resolved by completing Task 2; all plan verify filters pass at the end state.
- **Windows cp1252 console:** the pinned interpreter's default stdout encoding choked on CJK characters in one probe script — used `$env:PYTHONIOENCODING="utf-8"` for CJK-bearing test runs (no code impact).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The three render sites + checkbox now speak one contract (`style.vertical`); the `payload.vertical` metadata surface is reduced to the exporter/detector (project_io, ocr_export, image_ops) — G-07-2 (font dropdown contains-search) and G-07-3 (default font) can proceed without touching the vertical render path.
- The upright-Roman rule is documented in the module docstring for any future kumimoji/tate-chu-yoko polish (CONTEXT Deferred).
- No blockers; the paint-guard/graveyard work from 07-06 is untouched and remains green.

---
*Phase: 07-typesetting-tran-02-render-translated-text-into-the-page*
*Completed: 2026-08-11*
