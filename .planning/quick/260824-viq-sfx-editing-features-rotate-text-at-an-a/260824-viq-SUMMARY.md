---
phase: quick-260824-viq
plan: 01
subsystem: gui-typesetting
tags: [sfx, rotation, spacing, clipboard, text-style, renderer]
requires: [TextStyle serialization (D-07), boxes_modified/history push (CR-01), _replace_style commit machinery, TypesetOverlayItem pixmap cache]
provides: [rotation_deg + char_spacing_px + line_spacing_px on TextStyle (persisted, V5-clamped), RotationHandle + canvas rotate drag, Inspector Spacing H/V rows, canvas Ctrl+C/Ctrl+V box duplication]
affects: [manga_ai_studio/core/project_io.py (consumes new fields verbatim — zero changes needed), ocr_export style block (same)]
tech-stack:
  added: []
  patterns: [QFont.setLetterSpacing for measurement==render sharing, QTextBlockFormat top margins for line gaps, QPainter rotation about a scene pivot inside the shared paint path, pixmap-cache rotated-surface rendering with derived item offset]
key-files:
  created:
    - tests/test_core/test_text_renderer.py
    - tests/test_gui_sfx_editing.py
  modified:
    - manga_ai_studio/core/text_style.py
    - manga_ai_studio/gui/text_renderer.py
    - manga_ai_studio/gui/box_item.py
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/inspector_panel.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_core/test_text_style.py
decisions:
  - "Rotation is degrees CLOCKWISE (Qt painter.rotate convention), normalized into (-180, 180] by _normalize_rotation before any transform"
  - "paint() applies the rotation about LayoutResult.box_center as ONE transform before the origin translate — canvas and bake share the exact composition (D-01)"
  - "Rotated overlay: composed local coords are t0 + C + R(p+origin-C) (origin rotates WITH p); surface bounds from padded-ink corners through that expression; item pos P = min_g - t0; angle-0 reduces byte-exactly to the legacy path"
  - "Vertical (tategaki) placements measure with a letter-spacing-STRIPPED font — the explicit inter-column gap replaces QFont.AbsoluteSpacing there or every advance would double-count"
  - "Line spacing = QTextBlockFormat top margin per document block after the first — doc height grows, so overflow/auto-fit consume it with zero extra logic"
  - "_register_box_item extracted from set_boxes/_commit_create as the ONE BoxItem construction path; paste joins it (no forked construction logic)"
  - "box_clipboard is in-process Python state (never the OS clipboard — T-VIQ-02); pastes re-clone (Pitfall 8 twice) and reset fresh-box semantics while keeping text + full style"
  - "Multi-selection Spacing H/V loads the PRIMARY box's values with NO tri-state (deliberate simplification; align/effect mixed-sentinel machinery is the upgrade path)"
metrics:
  duration: ~20h wall (multi-session; active execution ~2.5h)
  completed: 2026-08-25
  tasks: 3
  commits: 3
status: complete
actuals:
  tokens: 16760   # chars/4 over the realized diff (1636 insertions / 40 deletions, 9 files)
  tasks: 3
  commits: 3
---

# Quick Task 260824-viq: SFX Editing Features — Rotate Text, Char/Line Spacing, Box Copy/Paste Summary

Free-angle text rotation via a corner-above drag handle, horizontal character / vertical line separation controls in the Inspector, and Ctrl+C/Ctrl+V duplication of styled text boxes — all persisted through the existing TextStyle/.mas pipeline and undoable in one Ctrl+Z.

## What Was Built

### Task 1 — Style model + renderer (`428bf6f`)
- `TextStyle` gains `rotation_deg` (-180..180), `char_spacing_px` (0..64), `line_spacing_px` (0..256) with module bound constants; `to_dict`/`from_dict` extended with `_clamp_float` coercions (bool rejected, non-numeric → default). `project_io`/`ocr_export` untouched — they consume the dict spelling verbatim, so all three fields persist with ZERO downstream changes.
- `LayoutResult.box_center` set at ALL THREE construction sites; `paint()` rotates effects+glyphs about it when rotation ≠ 0.
- `_style_font` applies `QFont.AbsoluteSpacing` so the line breaker's measurement and the document's render share one font construction.
- `_build_document` adds a block top margin after the first block for line spacing; vertical placements gain explicit inter-column pitch and per-char y-advance gaps.

### Task 2 — RotationHandle + canvas rotate drag (`a4741e0`)
- `RotationHandle`: ItemIgnoresTransformations 10×10 circle at z=155, centered 18 px above the TL corner (clear of the TL CornerHandle hit zone), owns its left-press via a canvas-installed callback (RedetectHandle precedent).
- BoxItem integrates the handle into the selected&&primary visibility machinery + edit-mode acceptance stripping; `preview_rotation`/`clear_preview_rotation` are pure overlay transforms (RC-1).
- `TypesetOverlayItem._render_rotated` sizes the cached pixmap to the rotated padded-ink bounds and derives the item position analytically; the unrotated path is untouched (byte-compat guard test locks this).
- Canvas state machine mirrors resize: pre-mutation snapshot at arm (CR-01), live preview on move, commit beyond a 0.05° deadband assigns a fresh TextStyle and emits `boxes_modified` once ("rotate" op name → transient status).

### Task 3 — Inspector spacing rows + copy/paste (`b38f7c1`)
- "Spacing H" / "Spacing V" QSpinBox rows mirror the Size-row mechanics (WR-01 emit-if-changed, load/clear discipline, multi-select primary-value load).
- MainWindow handlers route through the EXISTING `_inspector_style_commit`/`_replace_style` — no new undo plumbing.
- Canvas Ctrl+C stashes detached clones into `canvas.box_clipboard`; Ctrl+V re-clones, offsets +16/+16 (page-clamped), resets fresh-box semantics (USER origin, bubble cleared, mask/std-dev/override dropped, edited=True) keeping text + full style, inserts via the extracted `_register_box_item`, emits one `boxes_modified` with the pre-insert snapshot.

## Verification
- Task verify commands green: core style/renderer suites (32 tests), GUI SFX suite + test_gui_boxes, inspector styling + box persistence.
- Full suite: **1138 passed, 0 failed** under the pinned interpreter (`C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe -m pytest -q`) — strict superset of the Phase-5 baseline (552).
- Zero-rotation/zero-spacing regression: every pre-existing renderer/overlay/bake/boxes test passes UNMODIFIED.

## Deviations from Plan

**1. [Rule 3] Extracted `_register_box_item` from `set_boxes`/`_commit_create`**
- **Found during:** Task 3
- **Issue:** No shared BoxItem-construction helper existed; the plan required paste to ride the same path ("if none exists extract one").
- **Fix:** Extracted the registration sequence (weakref owner, redetect+rotation hooks, scene add, layer/text-overlay sync, membership) into one method used by all three creation sites.
- **Files:** manga_ai_studio/gui/canvas.py

**2. [Documented deviation] Rotated canvas≡bake parity asserted with bounded deltas, not exact pixel equality**
- **Found during:** Task 2 testing
- **Issue:** At angle ≠ 0 every glyph pixel is an AA edge; the pixmap-cache round-trip (render into premultiplied cache → blit at a fractional scene position) double-resamples vs the bake's direct draw. Measured envelope for a correctly-placed 45° overlay: 241 changed px, max channel delta 16, p90 12. Exact equality is unattainable BY DESIGN (the same sub-pixel-phase exclusion the angle-0 equivalence tests document for edge pixels).
- **Fix:** Parity contract = p90 ≤ 24 AND max ≤ 48 — a displaced overlay lights up whole glyph bodies at near-full contrast (100+), so the bounds still carry the D-01 guarantee.
- **Files:** tests/test_gui_sfx_editing.py

**3. [Documented deviation] Vertical placements measure with a spacing-stripped font**
- **Issue:** Applying `_style_font`'s AbsoluteSpacing in the tategaki measurement inflated every per-char advance, double-counting with the explicit inter-column gap.
- **Fix:** `_vertical_placements` strips the letter-spacing term from its measuring font; explicit gaps remain the single source of vertical spacing.

**4. [Deliberate deferral — plan-mandated]** Edit-menu Copy/Paste actions, paste-at-cursor positioning, cross-page clipboard, and a numeric Inspector rotation field are NOT built; handle-drag rotation, fixed 16px offsets, and canvas-scoped shortcuts cover the stated workflow.

## Pre-existing Issues Encountered (out of scope)
- `tests/test_gui_boxes.py::test_no_ghost_after_undo_and_scroll` failed once mid-session AND on clean HEAD (viewport-grab timing flake); passed in the final full-suite run. Not touched.

## Auth Gates
None.

## Known Stubs
None — every feature is wired end-to-end (model → renderer → canvas → inspector → persistence).

## Threat Flags
None — no new trust-boundary surface. T-VIQ-01 mitigated (V5 clamps, tested); T-VIQ-02 accepted (in-process clipboard attribute); T-VIQ-03 inherited (plain-text-only rendering unchanged).

## Self-Check: PASSED
- Files: all 9 files in the three commits exist on disk; `git diff --shortstat 223a1d9..HEAD` = 9 files changed, 1636 insertions(+), 40 deletions(-).
- Commits verified in log: `428bf6f`, `a4741e0`, `b38f7c1`.
