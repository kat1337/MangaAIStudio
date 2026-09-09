---
phase: quick-260909-nj9
plan: 01
status: complete
subsystem: ui
tags: [typesetting, alpha, transparency, qcolordialog, hexargb, textstyle, wysiwyg, pyside6]

# Dependency graph
requires:
  - phase: 07 (Typesetting)
    provides: TextStyle flat style model (D-06/D-07 serialization), the ONE shared render path (text_renderer layout/paint/bake_typeset_page, D-01), Inspector style section with WR-01 no-op guards
provides:
  - Alpha-capable glyph-fill Color picker (ShowAlphaChannel + DontUseNativeDialog) emitting Qt HexArgb (#AARRGGBB)
  - _norm_hex_a module helper — canonical HexArgb normalization used by the alpha-aware WR-01 guard
  - Honest transparency swatch (neutral checkerboard under sub-opaque fills)
  - Alpha pinning tests at every layer (model round-trip, render brush, bake pixel parity, .mas persistence, GUI picker/swatch seams)
affects: [typesetting system next steps (pattern fills / gradients), style model evolution, bake/export parity]

actuals:
  tokens: 5100 # chars/4 over the realized 483+/30- diff (plan estimated 35000 — the tracer found alpha already flowed, so production change was picker+swatch+guard only)
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Alpha in hex color strings rides Qt's native #AARRGGBB parsing end-to-end — model stores verbatim, render/bake share one fill path, persistence needs no change"
    - "WR-01 no-op guards normalize BOTH sides through a canonical spelling helper before comparing (alpha-aware equality)"

key-files:
  created: []
  modified:
    - manga_ai_studio/gui/inspector_panel.py
    - manga_ai_studio/core/text_style.py
    - tests/test_gui_inspector_styling.py
    - tests/test_gui_boxes.py
    - tests/test_core/test_text_style.py
    - tests/test_core/test_text_renderer.py
    - tests/test_core/test_typeset_bake.py
    - tests/test_core/test_project_io.py

key-decisions:
  - "Scope held: alpha applies to the glyph-fill Color row ONLY; effect (outline/glow/shadow) colors stay opaque because each effect dict already owns an opacity field — scope decision recorded in a code comment at _pick_effect_color plus a test pin"
  - "DontUseNativeDialog is REQUIRED on Windows: the native color dialog has no alpha control, so ShowAlphaChannel alone would silently show nothing"
  - "The picker emits the canonical HexArgb spelling via _emit_style_color_if_changed normalization — the model converges on one spelling WITHOUT a load-time rewrite (legacy projects load byte-compatibly; _loaded_style_color keeps verbatim spellings)"
  - "No hex validation added to TextStyle.from_dict — the V5 tolerance (any string accepted, invalid falls back at render time via _valid_color) is deliberate; the plan's tracer confirmed alpha already flowed the D-01 path, so Task 1 production change was docstrings only"

patterns-established:
  - "Range-based pixel assertions for alpha compositing (bake ~128 grey band 105..150; swatch blend 180..254) — platform/antialiasing-robust per project test lessons"
  - "QTextDocument char-format read-back must go through QTextCursor.charFormat(), not QTextBlock.charFormat() (the block format never reflects merged character formats)"

requirements-completed: [quick-260909-nj9]

coverage:
  - id: D1
    description: "Color picker offers transparency; a picked semi-transparent color stores #AARRGGBB on TextStyle.color"
    requirement: quick-260909-nj9
    verification:
      - kind: unit
        ref: "tests/test_gui_inspector_styling.py#test_pick_style_color_opens_alpha_dialog_and_emits_hexargb"
        status: pass
  - id: D2
    description: "Canvas overlay + bake render at the chosen opacity via the ONE shared fill path (50% white over black page ~ 50% grey ink)"
    requirement: quick-260909-nj9
    verification:
      - kind: unit
        ref: "tests/test_core/test_typeset_bake.py#test_bake_composites_alpha_fill_wysiwyg"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_text_renderer.py#test_build_document_fill_brush_carries_alpha_horizontal + test_valid_color_parses_argb_for_vertical_fill"
        status: pass
  - id: D3
    description: "Alpha round-trips .mas save/load verbatim; legacy #RRGGBB projects load opaque and unchanged"
    requirement: quick-260909-nj9
    verification:
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_alpha_color_round_trips_mas_verbatim + test_legacy_opaque_color_spelling_unchanged_by_persistence"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_text_style.py#test_alpha_color_round_trips_verbatim + test_legacy_opaque_color_spelling_preserved_as_is + test_default_color_spelling_unchanged"
        status: pass
  - id: D4
    description: "WR-01 no-op guard is alpha-aware; swatch shows sub-opaque colors over a checkerboard; effect rows stay opaque"
    requirement: quick-260909-nj9
    verification:
      - kind: unit
        ref: "tests/test_gui_inspector_styling.py#test_style_color_wr01_guard_is_alpha_normalized"
        status: pass
      - kind: unit
        ref: "tests/test_gui_inspector_styling.py#test_swatch_paints_transparent_fill_over_checkerboard + test_swatch_opaque_renders_exactly_as_legacy + test_swatch_mixed_split_unchanged + test_pick_effect_color_stays_opaque_hexrgb"
        status: pass
---

# Quick Task 260909-nj9: Typesetting color picker transparency (alpha) Summary

Alpha-capable glyph-fill Color picker (Qt HexArgb end-to-end): picker -> TextStyle.color -> canvas overlay -> .mas save/load -> baked/exported pages, with legacy opaque projects loading byte-compatibly and effect colors deliberately untouched.

## Accomplishments

- **Task 1 (tracer, 3259b0f)** — Alpha pins written FIRST and run against the current code: the tracer PASSED on first run exactly as the plan predicted (QColor natively parses #AARRGGBB and TextStyle passes the string through verbatim), proving alpha already flows the one shared D-01 render path. New pins: model round-trip verbatim + legacy spelling preserved + default unchanged (test_text_style); horizontal `_build_document` foreground brush alpha 128 + vertical `_valid_color` HexArgb parse (test_text_renderer); pixel-level bake WYSIWYG parity — 50%-alpha white over a black page bakes ~128 grey (assert band 105..150), opaque bakes >= 240 (test_typeset_bake). text_style.py updated docstrings-only (module header + color field document the #AARRGGBB spelling; zero behavior change; NO from_dict validation added — V5 tolerance preserved).
- **Task 2 (4075751)** — `_pick_style_color` opens QColorDialog with `ShowAlphaChannel | DontUseNativeDialog` (native Windows dialog has no alpha control) and emits the HexArgb spelling; the seed QColor parses #AARRGGBB so the dialog opens at the stored alpha with a live preview. New module-level `_norm_hex_a` helper; `_emit_style_color_if_changed` compares BOTH sides normalized and emits the canonical form — re-picking the loaded legacy color in opaque HexArgb spelling is a WR-01 no-op (never a spurious undo entry). `_ColorSwatchButton.paintEvent` paints a neutral 4x4 checkerboard (#cccccc/#8a8a8a) under sub-opaque ARGB fills; opaque/legacy/None-Mixed paths byte-identical. `_pick_effect_color` deliberately unchanged with a scope-decision comment + a test pin. Tooltip/docstrings updated.
- **Task 3 (9ed95ab)** — Persistence proof: `#80ff0000` round-trips pagebox_to_json -> json.dumps/loads -> json_to_pagebox byte-verbatim (no persistence change needed — the test IS the proof); legacy `#ff0000` reloads `#ff0000`, never rewritten to 9-char. One-word comment correction (ShowAlphaChannel is the real Qt enum name).

## Verification

- Task verifies green under the pinned interpreter (`C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe`): Task 1 — 54 passed (text_style + text_renderer + typeset_bake); Task 2 — 33 passed styling + 234 passed boxes (1 deselected, see below); Task 3 — 54 passed project_io.
- Grep gate: `HexArgb` present at both the emit site (inspector_panel.py:1645) and the normalization helper (:241); picker options at :1640.
- **Full suite: 1444 passed, 3 failed in 3:24** — 1447 = 1432 baseline + 15 new tests (3+2+1+7+2). All 3 failures triaged as environmental, none caused by this plan:
  1. `test_gui_ocr_grab.py::test_grab_history_click_recopies_older_entry` and `test_box_text_copy_handler_empty_rules` — the known clipboard flakes (same family as quick-260909-fa9's "clipboard flake passes in isolation"); both PASS in isolation.
  2. `test_gui_boxes.py::test_no_ghost_after_undo_and_scroll` — fails in isolation too AND fails at the pre-plan commit 72a02cf (reproduced in a clean temp worktree): a pre-existing environmental rendering failure (stroke pixel green 206 vs <200 threshold — antialiasing/DPI-dependent), untouched by this plan's color work. Pre-existing, out of scope per the deviation boundary.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Plan's `ShowAlphaButton` option does not exist in Qt**
- **Found during:** Task 2 (RED run)
- **Issue:** The plan prescribed `QColorDialog.ColorDialogOption.ShowAlphaButton`; Qt's real enum member is `ShowAlphaChannel` (verified: the ColorDialogOption members are ShowAlphaChannel / NoButtons / NoEyeDropperButton / DontUseNativeDialog). Literal use raised AttributeError.
- **Fix:** Used `ShowAlphaChannel` — the intent (an alpha control in the dialog) is preserved exactly. Noted in code comments and test docstrings.
- **Files modified:** manga_ai_studio/gui/inspector_panel.py, tests/test_gui_inspector_styling.py
- **Commit:** 4075751

**2. [Rule 3 - Blocking] Normalized emission ripples into two existing GUI test files**
- **Found during:** Task 2 (RED run)
- **Issue:** The plan's explicit prescription "emit the normalized form" changes the emitted spelling (#112233 -> #ff112233 etc.), which the plan's files list missed: existing assertions in tests/test_gui_inspector_styling.py (:253/:726/:764 families) AND tests/test_gui_boxes.py (:4888/:4947 UAF/graveyard tests — NOT in the plan's files_modified) assert the old 7-char spellings after `_commit_style_color`.
- **Fix:** Updated the affected expected spellings to the normalized forms (#ff112233 / #ff00ff00 / #ff123456). The test_gui_boxes assertions are incidental fixture values in UAF-regression tests — their regression value (one emission, one undo, graveyard lifetime) is untouched.
- **Files modified:** tests/test_gui_inspector_styling.py, tests/test_gui_boxes.py
- **Commit:** 4075751

**3. [Rule 1 - Test-side bug] Horizontal alpha pin read the wrong Qt format API**
- **Found during:** Task 1 (tracer pin run)
- **Issue:** The new pin read the merged fill brush via `QTextBlock.charFormat()` — that is the BLOCK format, which never reflects merged character formats (it returned the default black/255, a false failure). The bake pixel-parity pin passed simultaneously, proving alpha did reach the real render path.
- **Fix:** Read back through `QTextCursor(doc).charFormat()` at the text start (probe-verified: alpha 128, spelling #80ff0000). No production defect existed.
- **Files modified:** tests/test_core/test_text_renderer.py
- **Commit:** 3259b0f

## Known Stubs

None.

## Threat Model Check

T-nj9-01 (crafted .mas color string) — mitigated exactly as planned: any string still passes `_coerce_str`, invalid hex still falls back at render time via `_valid_color`; new persistence pins lock the contract. T-nj9-02/T-nj9-03 unchanged (accept). No new trust surface introduced.

## Needs Review (manual spot-check per plan verification)

Open a project, select a box, open the Color picker, drag alpha to ~50%, pick white — canvas text should be translucent; save + reopen — still translucent; Export Typeset Pages — sidecar PNG matches the canvas.

## Self-Check: PASSED

- Files: all 8 modified files exist in the working tree (committed).
- Commits verified: 3259b0f (Task 1), 4075751 (Task 2), 9ed95ab (Task 3) — all present in `git log`.
- Suite: 1447 collected = 1432 baseline + 15 new; 1444 passed; 3 environmental failures triaged (2 clipboard flakes pass in isolation; 1 pre-existing repro'd at the pre-plan commit).
