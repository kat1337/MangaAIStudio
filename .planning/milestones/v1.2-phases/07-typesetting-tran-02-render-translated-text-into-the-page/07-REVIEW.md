---
phase: 07-typesetting-tran-02-render-translated-text-into-the-page
reviewed: 2026-08-11T00:00:00Z
depth: standard
files_reviewed: 20
files_reviewed_list:
  - manga_ai_studio/core/text_style.py
  - manga_ai_studio/core/box_model.py
  - manga_ai_studio/gui/text_renderer.py
  - manga_ai_studio/gui/box_item.py
  - manga_ai_studio/gui/canvas.py
  - manga_ai_studio/gui/inspector_panel.py
  - manga_ai_studio/gui/main_window.py
  - manga_ai_studio/core/ocr_export.py
  - manga_ai_studio/core/project_io.py
  - tests/test_core/test_text_style.py
  - tests/test_core/test_typeset_layout.py
  - tests/test_core/test_typeset_bake.py
  - tests/test_core/test_typeset_effects.py
  - tests/test_core/test_history_boxes.py
  - tests/test_core/test_project_io.py
  - tests/test_core/test_ocr_export.py
  - tests/test_gui_boxes.py
  - tests/test_gui_export.py
  - tests/test_gui_inspector_styling.py
  - tests/test_gui_batch.py
findings:
  critical: 1
  warning: 3
  info: 3
  total: 7
status: clean
---

# Phase 7 (TRAN-02): Code Review Report

**Reviewed:** 2026-08-11T00:00:00Z
**Depth:** standard
**Files Reviewed:** 20
**Status:** issues_found

## Summary

The core model (TextStyle / PageBox.copy), the shared renderer (layout /
paint / bake_typeset_page), the persistence writers (project_io /
ocr_export), and the Inspector style-section wiring were reviewed at
standard depth, with empirical probes run on the pinned Python 3.14.2 /
PySide6 6.10.1 stack (offscreen).

The good: ASVS V5 plain-text discipline holds (no `setHtml` / rich-text path
anywhere — only `setPlainText`); the `QPainterPath.addText` crash path is
fully substituted by the QTextDocument mechanism (only docstring mentions
remain); `TextStyle.to_dict()` is the single serialization spelling used by
both writers; `OCR_JSON_VERSION "2"` is consistent and test-pinned;
`PageBox.copy()` style detachment (Pitfall 8) is correct and guarded by
tests; the Mixed sentinel never leaves the widget layer; the vertical flag
re-renders both canvas and bake through the same expression; and the
bounded-effect-allocation degrade path (T-07-07) works.

**However, the phase's central deliverable — the canvas overlay (D-01) — is
broken.** `TypesetOverlayItem.set_content` double-counts `result.origin` when
rendering into its cached pixmap, so the pixmap is **completely blank** for
any box at a non-trivial position (empirically verified: alpha channel is
all-zero). The canvas shows no typeset text at all; the bake is correct.
The D-01 equivalence test misses this because it compares `paint()` at image
coordinates directly, bypassing the overlay's pixmap path, and the overlay
position tests assert only bounding-rect deltas, never pixmap content.

## Critical Issues

### CR-01: Canvas overlay renders a blank pixmap — `set_content` double-counts `result.origin` (D-01 broken)

**File:** `manga_ai_studio/gui/box_item.py:372-387` (and `refresh_position` at 389-399)

**Issue:** `TypesetOverlayItem.set_content` translates the pixmap painter by
`(-ink.left() + pad, -ink.top() + pad)` and then calls `renderer_paint`
(`gui/text_renderer.paint`), which itself translates by `result.origin` —
where `origin = (box_rect.x() + inset, box_rect.y() + inset + dy)`. The ink
therefore lands at pixmap-local `(origin.x + pad, origin.y + pad)`, i.e.
offset by the box's scene position plus the inset, inside a pixmap that is
sized to the ink rect. Empirically verified on the pinned stack:

- Box at (40,30) rect 100x60, text "Hello": `result.origin = (42,32)`,
  `ink = (0,0,70,16)` → pixmap 70x16 → ink drawn at pixmap-local
  (42..112, 32..48), entirely **outside** the 70x16 pixmap → **alpha max 0,
  zero non-transparent pixels**. The canvas overlay renders nothing.
- A box at (0,0) renders only the sliver of ink that fits inside the pixmap
  (clipped + displaced by (inset, inset + dy)).

This breaks D-01 (canvas overlay ≡ bake) outright: the bake draws the text
correctly (verified), the canvas shows blank boxes. The position tests pass
because `test_text_overlay_tracks_box_after_setrect_move` / the containment
asserts check only bounding-rect *deltas*, and
`test_canvas_style_paint_equals_bake_pixels` calls `paint()` directly at
image coordinates — it never exercises `set_content`'s pixmap translation.
No test reads the overlay pixmap's pixels.

**Fix:** subtract `result.origin` in the `set_content` translate so
`renderer_paint`'s `translate(origin)` nets to zero and the ink lands at
`(pad, pad)` in the pixmap (verified: this restores scene ink at x 42..107
for the probe box, matching the bake):

```python
painter.translate(
    -result.origin.x() - ink.left() + pad,
    -result.origin.y() - ink.top() + pad,
)
renderer_paint(painter, result, style)
```

`_ink_offset = QPointF(ink.left() - pad, ink.top() - pad)` and
`refresh_position` are then correct as written. Add a pixel-level test that
renders the overlay pixmap at its scene position and compares it against
`bake_typeset_page` output for a box at a non-zero position.

## Warnings

### WR-01: Vertical toggle is silently dropped on payload-None boxes (never-OCR'd user box)

**File:** `manga_ai_studio/gui/main_window.py:3238-3240`

**Issue:** `_on_inspector_vertical_committed` writes `payload.vertical` only
when `item.pagebox.payload is not None`. A user-drawn box that has never been
OCR'd has `payload=None`, so checking "Vertical text" writes nothing, yet the
handler still records the "style change" op name, refreshes overlays, and
emits `boxes_modified` — pushing a no-op BOXES undo entry. The renderer's
vertical flag reads `style.vertical OR payload.vertical` (both False here),
so the text stays horizontal while the checkbox appears checked until the
panel reloads and resets it — a silent no-op with a spurious undo entry.
Probe-confirmed.

**Fix:** ensure the payload exists before writing (the same lazy-construction
guard the text setters use):

```python
for item in selected:
    item.pagebox._ensure_payload()
    item.pagebox.payload.vertical = vertical
```

(or route through a `set_vertical`-style setter with the payload-None guard).

### WR-02: Mixed effect-row value commit silently enables the effect on all selected boxes

**File:** `manga_ai_studio/gui/inspector_panel.py:1206-1229` (`_effect_payload`)

**Issue:** When an effect row is Mixed (differing `enabled`/color/value across
the selection) and the user changes only the *value* spin, `_effect_payload`
falls back to the hardcoded `"enabled": True` for the untouched field (line
1222). So on a selection where the glow/shadow/outline enabled state differs
(e.g. box A glow on, box B glow off), changing the radius/width silently
turns the effect **on** for every box — including the ones the user had
disabled. The tri-state checkbox cannot express "leave enabled alone", and
the commit path doesn't either. The sentinel does not persist (Pitfall 7
holds), but the fallback *value* is a surprising semantic leak.

**Fix:** carry the enabled state explicitly in the commit when it is
observable (the widget is tri-state, so a value-only commit should preserve
each box's existing `enabled` per-box rather than force `True`), or make the
mixed fallback use the *style default* for the effect's enabled state
(`DEFAULT_OUTLINE/GLOW/SHADOW` `["enabled"]`) instead of `True`, and
document the behavior.

### WR-03: Export/Inspector paths assume a TextBlock payload; a bare-marker payload raises AttributeError

**File:** `manga_ai_studio/core/ocr_export.py:163-183`, `manga_ai_studio/gui/inspector_panel.py:697`

**Issue:** `build_page_ocr_json` accesses `payload.vertical`,
`payload.lines`, `payload.translation` and `load_multi_selection` accesses
`pb.payload.vertical` with plain attribute access, while
`gui/text_renderer.current_focus_text` defensively uses `getattr` for the
same contract ("a bare marker object has no .text/.translation -> empty").
`PageBox` accepts any payload object (the suite itself builds
`PageBox(payload="p")` in `tests/test_gui_boxes.py:563`). If a non-TextBlock
payload ever reaches the OCR export (worker thread) or a multi-selection
(GUI thread), the AttributeError crashes the export page / the selection
handler instead of degrading. The renderer sets the precedent that this
must not happen.

**Fix:** mirror the renderer's defensive access in both places, e.g.
`getattr(payload, "vertical", False)`, `getattr(payload, "lines", None)`,
`getattr(payload, "translation", "")`.

## Info

### IN-01: V5 font-size clamp bounds duplicated across modules

**File:** `manga_ai_studio/core/text_style.py:46-47` vs
`manga_ai_studio/gui/text_renderer.py:95-96`

`_FONT_SIZE_MIN/_FONT_SIZE_MAX` exist in both modules. The renderer's manual-
size clamp (text_renderer.py:533, 605) and `TextStyle.from_dict`'s clamp can
drift apart. Consider importing the single source from `text_style`.

### IN-02: Hardcoded 14.0 fallback in `_style_rendered_size`

**File:** `manga_ai_studio/gui/main_window.py:3059`

The "nothing renders — the size is moot" fallback returns a literal `14.0`,
duplicating the renderer's `_OVERLAY_FONT_BASE` (text_renderer.py:88). If the
base ever changes, the Auto-fit-uncheck starting size for empty boxes drifts.
Import the constant instead.

### IN-03: Self-alias re-export of `_OVERLAY_INSET`

**File:** `manga_ai_studio/gui/box_item.py:125`

`_OVERLAY_INSET = _OVERLAY_INSET` imports the renderer constant under the
same name via the `from ... import _OVERLAY_INSET` in the import block. It
works, but the roundabout re-export obscures intent; a direct
`from manga_ai_studio.gui.text_renderer import _OVERLAY_INSET` in the import
list (as done for `effect_padding`/`current_focus_text`) is clearer.

---

_Reviewed: 2026-08-11T00:00:00Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
