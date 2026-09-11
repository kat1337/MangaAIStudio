---
phase: quick-260910-vej
plan: 01
subsystem: typesetting
tags: [text-fill, gradient, pattern, qbrush, inspector, persistence]
requires: [quick-260909-nj9-alpha-colors]
provides: [TextStyle fill framework, shared gradient/pattern fill brushes, Inspector Fill row, embedded tile persistence]
affects: [canvas typeset overlay, bake export, .mas projects]
tech-stack:
  added: []
  patterns: [shared QBrush fill path (D-01 structural), bounded LRU tile decode cache, whitelist-forwarded commit dicts (T-vej-04)]
key-files:
  created:
    - tests/test_core/test_typeset_fill.py
  modified:
    - manga_ai_studio/core/text_style.py
    - manga_ai_studio/gui/text_renderer.py
    - manga_ai_studio/gui/inspector_panel.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_core/test_text_style.py
    - tests/test_core/test_project_io.py
    - tests/test_gui_inspector_styling.py
decisions:
  - "Fill anchor offset semantic: doc-local gradient start/end translate by MINUS the doc draw origin R_p (and the texture brush by QTransform.fromTranslate(-ox,-oy)) — the plan's `offset=R_p` wording shifts the ramp the wrong way; the vertical-continuity pixel test pins the correct direction"
  - "Swatch preview angle reuses the renderer's _gradient_start_end (one angle implementation, preview == render by construction)"
  - "style_fill_changed emitters emit the class-scope signal; connect_commit_handlers connects the signal to the MainWindow callback (declared-signal design, test-drivable)"
  - "Oversized-tile decode guard tested with a monkeypatched 8192px threshold (a real >8192px decode would allocate ~268 MB in-test); the 4 MB byte cap is tested with a REAL >4 MB noise PNG"
  - "No size clamp on pattern_tile_b64 at LOAD (load robustness per plan) — the pick-time dialog cap and the renderer decode guard are the two enforcement points"
metrics:
  duration: 52 min
  completed: 2026-09-11
status: complete
actuals:
  tokens: 21000
  tasks: 3
  commits: 3
---

# Quick Task 260910-vej: Advanced typesetting — gradient and pattern text fills Summary

Linear 2-stop gradient and user-image pattern glyph fills on the ONE shared QBrush path (canvas overlay ≡ bake, pixel-test-proven), with full .mas round-trip of embedded tiles and an Inspector Fill row whose swatch previews the real fill.

## What Was Built

### Task 1 — TextStyle fill framework (commit 9f8f86e)
- Five additive fields on `TextStyle` (manga_ai_studio/core/text_style.py): `fill_type` ("solid"/"gradient"/"pattern"), `fill_color_b` ("#ffffff"), `fill_angle_deg` (90.0, clockwise, 0°=left→right, 90°=top→bottom), `pattern_scale` (1.0), `pattern_tile_b64` (None). Every default legacy-identical.
- Public shared constants `FILL_TYPES`, `FILL_TILE_MAX_BYTES` (4 MB pick-time cap), `PATTERN_SCALE_MIN/MAX` (0.1..10.0) — the UI imports them so UI range == model clamp by construction (EFFECT_GEOM_MAX precedent).
- V5 coercion: `fill_type` allowed-values fallback (anything else → "solid"), numerics via `_clamp_float`, non-str tile → None. No load-time size clamp (load robustness).
- Persistence needed ZERO project_io changes (`to_dict`/`from_dict` seam) — proven by the .mas-mapping round-trip test (gradient angle 37 + alpha colors; pattern with a REAL PNG tile; legacy dicts load Solid).

### Task 2 — Shared-renderer gradient + pattern brushes (commit 104fe2e)
- `style_fill_brush(style, rect, offset)` factory in manga_ai_studio/gui/text_renderer.py: linear `QLinearGradient` (2 alpha-carrying stops, corner-to-corner span via `_gradient_start_end`, center-symmetric at every angle) and `TexturePattern` tile brush (Color A alpha × tile alpha — the LOCKED single-opacity rule).
- Bounded LRU tile cache (8 entries, md5+scale keyed) holding decoded+SCALED tiles PRE-alpha-modulation; 8192px decode guard + solid fallback + loguru warning (T-vej-01/02), never an exception.
- Wiring rides the EXISTING `setForeground` sites: horizontal merges the brush over the doc after the forced layout (`_build_document`); vertical builds per-char brushes anchored by the doc draw origin so ONE continuous ramp/tiling spans the column (`_paint_fill_pass` → `_paint_vertical`/`_char_document`, additive params defaulting to today's solid path). Outline silhouettes (`_formatted_clone`) and effect passes untouched; `bake_typeset_page` needs ZERO changes (D-01 structural).
- tests/test_core/test_typeset_fill.py (14 tests): solid regression, gradient math (0/45/90/270 center symmetry + corner projections), 90°/0°/270° renders, alpha-stop fade-out, vertical continuity (top char ≈ A, bottom ≈ B), pattern tiling period + scale + alpha modulation + glyph presence, cache identity + bound, fallbacks (garbage/None/oversized), bake parity (byte-equal direct render for gradient + pattern boxes).

### Task 3 — Inspector Fill row + MainWindow wiring (commit 1c6e1c3)
- Fill combo row (Solid | Gradient | Pattern + non-editable "Mixed" sentinel) above Color; conditional sub-rows: Color B (alpha-capable swatch, `ShowAlphaChannel | DontUseNativeDialog`) + Angle (0..359, "°") for gradient; Image… (file picker) + Scale (0.10..10.00, "×", step 0.05) for pattern — shown/hidden with their QFormLayout labels.
- `style_fill_changed = Signal(dict)` carries only the fields the user changed (per-key WR-01 memories: `_loaded_style_fill_display/color_b/angle/scale/pattern_tile`); tile picker reads bytes in-panel, enforces the real 4 MB cap with the LOCKED `QMessageBox` warning and commits NOTHING on reject/oversize; re-picking the same bytes is a WR-01 no-op.
- MAIN Color swatch previews the REAL fill (LOCKED UI decision): `_ColorSwatchButton` gained a preview state — gradient mode paints the ramp via the shared `_gradient_start_end` over the checkerboard when either stop is sub-opaque; pattern mode tiles the decoded tile at Color A's alpha. Color B stays a solid swatch.
- Multi-selection (D-10): Mixed sentinel when fill TYPES differ (sub-rows hidden, never commits); per-widget Mixed (spin special text / split swatch) for differing angle/scale/Color B under a uniform type; `clear()` resets to Solid defaults.
- MainWindow `_on_inspector_style_fill_committed` forwards only the `_STYLE_FILL_KEYS` whitelist (T-vej-04) through `_inspector_style_commit` → `_replace_style` (dataclasses.replace, one BOXES snapshot, one Ctrl+Z per commit); a commit without `pattern_tile_b64` never clobbers an existing tile.

## Verification
- Task verifies (pinned interpreter per AGENTS.md): 88 → 81 → 90 passed at each task boundary.
- Full affected suite at close: 175 passed (text_style, project_io, typeset_fill, text_renderer, typeset_bake, gui_inspector_styling).
- Full-suite regression: **1492 passed, 2 failed** — the 2 are the known baseline flakes (`test_gui_boxes.py::test_no_ghost_after_undo_and_scroll` viewport-grab timing; `test_gui_ocr_grab.py::test_canvas_copy_text_requested_wired_to_handler` clipboard); BOTH pass in isolation on this code (re-ran 2/2 green). 1458 baseline + 34 new tests = 1492 — strict superset, 0 new failures.
- Manual smoke (offscreen): gradient (angle 37, alpha Color A) + pattern (embedded PNG tile) boxes survive the REAL `save_page_file`/`load_page_file` container round-trip field-for-field; a legacy Phase-7-era box dict loads Solid with `TextStyle()` defaults.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Clarification] Fill-anchor offset direction (Task 2)**
- **Found during:** Task 2 implementation
- **Issue:** The plan's "`offset=R_p` translates start/end" is ambiguous in sign; translating by +R_p would shift each per-char ramp the wrong way (2·R_p off), breaking column continuity.
- **Fix:** Doc-local gradient start/end translate by −offset (and the texture brush by `QTransform.fromTranslate(-ox, -oy)`), documented on `style_fill_brush`; the vertical-continuity pixel test (top char ≈ Color A, bottom ≈ Color B) pins the correct direction.
- **Files modified:** manga_ai_studio/gui/text_renderer.py
- **Commit:** 104fe2e

**2. [Rule 3 - Test infrastructure] Signal emission path (Task 3)**
- **Found during:** Task 3 tests
- **Issue:** The emitters initially called the commit callback directly, leaving the declared `style_fill_changed` signal unconnected — a direct `panel.style_fill_changed.emit(...)` (and the declared-signal contract) did nothing.
- **Fix:** Emitters emit the class-scope signal; `connect_commit_handlers` connects the signal to the MainWindow callback. All 11 new GUI tests + 33 pre-existing ones green.
- **Files modified:** manga_ai_studio/gui/inspector_panel.py
- **Commit:** 1c6e1c3

### Plan Deviations (documented, not defects)
- The plan-time probe's wording "gradient coordinates span the doc" needed one refinement: `documentSize()` spans the textWidth (inner box), and the ramp's PadSpread covers the glyphs — render tests sample ink pixels, not doc corners, so the contract is pinned where it is observable.
- The plan's "pattern_scale=2 render differs from scale=1 at the same point" is pinned via a deterministic `fillRect` brush probe (exact pixel equality/period assertions) PLUS a glyph-presence render test — more robust than glyph-pixel sampling alone.

## Known Stubs

None. No placeholders, no unwired data paths, no skipped tests.

## Auth Gates

None occurred.

## Self-Check: PASSED
- All 8 created/modified files exist on disk (checked).
- All 3 task commits exist in git log: 9f8f86e, 104fe2e, 1c6e1c3.
- Full-suite result reproduced above; both flake failures pass in isolation on this code.
