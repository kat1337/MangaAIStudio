---
phase: 07-typesetting-tran-02-render-translated-text-into-the-page
plan: 01
subsystem: typesetting (TRAN-02)
tags: [typesetting, text-renderer, bake-export, text-style, tracer]
requires: [phase-04-overlay, phase-05-export]
provides: [text-style-model, shared-renderer, opaque-overlay, typeset-bake]
affects: [box-model, canvas, main-window, ocr-export]
tech-stack:
  added: [core/text_style.py, gui/text_renderer.py]
  patterns: [QTextDocument plain-text render + QTextCharFormat.setTextOutline outline, pixmap-cached QGraphicsItem overlay, detached numpy<->QImage bridges]
key-files:
  created:
    - manga_ai_studio/core/text_style.py
    - manga_ai_studio/gui/text_renderer.py
    - tests/test_core/test_text_style.py
    - tests/test_core/test_typeset_layout.py
    - tests/test_core/test_typeset_bake.py
  modified:
    - manga_ai_studio/core/box_model.py
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/box_item.py
    - manga_ai_studio/gui/main_window.py
    - manga_ai_studio/core/ocr_export.py
    - tests/test_core/test_history_boxes.py
    - tests/test_gui_export.py
    - tests/test_gui_boxes.py
    - tests/test_gui_batch.py
decisions:
  - "Outline mechanism deviates from the plan letter: QPainterPath.addText + QTextLayout line machinery crash the interpreter on the pinned Python 3.14.2 / PySide6 6.10.1 stack (fast-fail 0xC0000409 / access violation, probed); the Phase 4 Pattern 3 QTextCharFormat.setTextOutline path is used instead — same LOOK, and the UI-SPEC locks the look, not the mechanism."
  - "QTextDocument document layout is FORCED (documentLayout().documentSize()) before any block-layout reads — lineAt() on an un-laid-out block access-violates on this stack."
  - "Vertical alignment rides the LayoutResult.origin (the paint translate), not the doc-local ink rect; horizontal alignment is engine-applied per line (verified by probe + pixel test)."
  - "Scene-px sizing supersedes the Phase 4 [10,28] viewport-px clamp and 2/zoom outline: apply_overlay_zoom stores zoom only, never re-layouts (WYSIWYG canvas ≡ bake); the Auto-fit base clamp [10,28] survives inside the renderer at scene px."
status: complete
metrics:
  duration: ~4h
  completed: 2026-08-10
actuals:
  tokens: 26600    # chars/4 over the realized diff (1971 added + 391 removed lines)
  tasks: 3
  commits: 4
---

# Phase 7 Plan 1: Typesetting tracer slice — TextStyle model, shared renderer, opaque canvas overlay, and the bake-to-disk export

**One-liner:** the phase's end-to-end tracer — a flat per-box `TextStyle` (defaults = the Phase 4 overlay look made opaque), a shared `gui/text_renderer.py` (layout/paint/bake — one code path for canvas and bake, D-01), an opaque pixmap-cached canvas overlay, and File ▸ Export Typeset… (Ctrl+Shift+B) baking a D-03-placed `{stem}_typeset.png` sidecar through the PROJ-02 writer.

## What Was Built

- **`core/text_style.py` (NEW)** — the flat per-box `TextStyle` dataclass (D-06): UI-SPEC A1 defaults (Liberation Sans / `#e8e8ea` opaque fill / 2px `#0b0b0e` outline / glow+shadow off / Auto-fit on / center/middle / horizontal), `to_dict()` hand-picked projection, `from_dict()` V5 coercion (size 1..1024, widths/radii 0..256, opacity 0..1; unknown keys ignored; non-numeric → defaults without raising; `None` → defaults — Pitfall 8 backward compat).
- **`core/box_model.py`** — `PageBox.style: Optional[TextStyle]` field; `copy()` now detaches payload AND style (`replace(self, payload=copy, style=copy)` — Pitfall 8/1). **`gui/canvas.py`** — `boxes_snapshot()` forwards `style` into rebuilt PageBoxes (style survives every undo/page-switch round-trip).
- **`gui/text_renderer.py` (NEW)** — the D-01 shared renderer (QtGui/QtCore + numpy only, headless-testable): `current_focus_text()` (D-04 rule shared with the canvas), `layout()` (plain QTextDocument wrap at the inner width, engine H-alignment, origin-based V-alignment, manual-size vs the Auto-fit bounded loop at scene px — box-adaptive base `14×min(w,h)/100`, [10,28] clamp, 12×0.9 iterations, 5px floor checked at loop top), `paint()` (opaque fill + `setTextOutline` outline, never clips — UI-SPEC A6), `bake_typeset_page()` (detached composite, D-04 content rule, 1:1), detached numpy↔QImage bridges.
- **`gui/box_item.py`** — `TypesetOverlayItem` replaces the translucent Phase 4 `QGraphicsTextItem` (surface 34 supersedes 16): cached QPixmap from the shared renderer (canvas ≡ bake), opaque per-box style (defaults when `None`), setPos-only `refresh_position` (RC-1 — never re-layouts on mousemove), T-toggle and box-visibility inheritance preserved, scene-px zoom-independent sizing. `_OVERLAY_FILL/_OVERLAY_OUTLINE/_OVERLAY_FONT` removed (grep gate clean); the `_OVERLAY_FIT_*`/`_OVERLAY_INSET` constants kept as the Auto-fit record.
- **`gui/main_window.py`** — `action_export_typeset` (File ▸ Export Typeset…, Ctrl+Shift+B, after Export Page; the Export OCR JSON action lives in the Text menu), `_on_export_typeset` (op-running gate → `_snapshot_current_page()` flush → detached `get_image_numpy()` → D-03-defaulted Save As dialog → `bake_typeset_page` → `save_image_optimized` (PNG 9 / JPG 95, DPI preserved) → "Typeset exported → {filename}" flash or the "Couldn't save '{filename}'." critical dialog), `_refresh_action_states` gate.
- **`core/ocr_export.py`** — `default_typeset_path()` (D-03 mirror of D-22: pristine → `{stem}_typeset.png` beside the source; geometry-altered → `cleaned/`, created by the writer).

## Tasks Executed

| Task | Name | Result |
|------|------|--------|
| 1 (tracer, tdd) | TextStyle model + shared renderer + bake pipeline | RED (3 collection errors on missing modules) → GREEN (42 tests pass); tracer verify re-ran end-to-end (auto gate): PASSED |
| 2 (auto) | Opaque canvas overlay rework + Export Typeset… action | 11-task verify green; all 206 box/canvas GUI tests green; grep gate clean |
| 3 (auto, tdd) | D-01 fidelity locks | 5 locks written; all passed immediately — the equivalence probe found NO divergence (GREEN no-op: the single-path contract held) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1/3 - Mechanism] `QPainterPath.addText` and `QTextLayout` line machinery crash the interpreter on this stack**
- **Found during:** Task 1 GREEN (probe before implementing the plan-prescribed mechanism)
- **Issue:** The plan's letter prescribed `QPainterPath.addText` + `strokePath` for the outline and QTextLayout-based layout. Both crash the pinned interpreter (Python 3.14.2 / PySide6 6.10.1): addText → fast-fail 0xC0000409; `QTextLayout`/`QTextLine.setLineWidth` → access violation; even `lineAt()` on an un-laid-out block access-violates. (Also probed: numpy loaded before the QGuiApplication makes the text engine crash at shutdown — an environment init-order instability the pytest `qapp` fixture and the real app's QApplication avoid.)
- **Fix:** Layout + outline ride `QTextDocument` (plain-text — ASVS V5) with a merged `QTextCharFormat`: opaque fill via the foreground brush, outline via `setTextOutline` (Phase 4 Pattern 3 — the research-endorsed "single clean API for outlined glyphs"; UI-SPEC locks the LOOK, not the mechanism). The document layout is FORCED (`documentLayout().documentSize()`) before any block-layout read. The renderer still exposes exactly the plan's public contract: `layout()/paint()/bake_typeset_page()/current_focus_text()`.
- **Files modified:** `manga_ai_studio/gui/text_renderer.py` (module docstring documents the deviation and the forced-layout requirement)
- **Commit:** 3ae2a72

**2. [Plan-driven test contract update] Overlay-probe tests asserted the SUPERSEDED Phase 4 document internals**
- **Found during:** Task 2 (full suite run)
- **Issue:** The plan supersedes the translucent overlay (surface 16 → 34) and mandates removing the hardcoded constants; ~10 existing tests in `test_gui_boxes.py` probed `QGraphicsTextItem` internals (`toPlainText()`, `textCursor()`, `document()`, `textWidth()`, the [10,28] viewport-px clamp, the `2/zoom` outline) that no longer exist by design, and `test_file_menu_internal_order` pinned the pre-export File-menu sequence.
- **Fix:** Rewrote the probes to the new contract (overlay `text()`/`layout_result`/`pixmap()` probes; scene-px zoom independence; delta-based geometry tracking; layout-result font-size assertions) and extended the menu-order test with Export Typeset…. Behavior contracts the plan preserves (T toggle, box visibility, setPos-only reposition, wrap/fit/floor) are asserted unchanged.
- **Files modified:** `tests/test_gui_boxes.py`, `tests/test_gui_batch.py`
- **Commit:** df36585

## Key Decisions

- **Outline mechanism = QTextCharFormat.setTextOutline** (Pattern 3), not addText+strokePath — the plan's prescribed API crashes this stack (see Deviation 1).
- **Vertical alignment rides the layout origin**, horizontal rides the document engine — verified by pixel probes; the layout result exposes both (`origin` + engine-aligned `line_rects`).
- **Scene-px sizing**: `apply_overlay_zoom` stores zoom only (never re-layouts); the [10,28] clamp survives only inside the renderer's Auto-fit base computation at scene px (UI-SPEC A2) — the canvas at zoom 1 ≡ the bake by construction.
- **Overlay position inset = the renderer's `_OVERLAY_INSET` (2.0)** — the canvas sits exactly where the bake paints (D-01); the old pen-half+2 inset (box chrome) no longer shifts the text.
- **`default_typeset_path` suffix `_typeset`** (D-03), placement mirrors `ocr_json_target_dir` verbatim.

## Verification

- `pytest tests/test_core/test_text_style.py tests/test_core/test_typeset_layout.py tests/test_core/test_typeset_bake.py tests/test_core/test_history_boxes.py tests/test_gui_export.py -q` → **60 passed**
- Full suite `pytest -q` → **634 passed, 0 failed** (600-test phase-start baseline; +34 new/extended)
- Grep gates: `rg "setHtml" manga_ai_studio/gui/text_renderer.py` → nothing; `rg "_OVERLAY_FILL|_OVERLAY_OUTLINE|_OVERLAY_FONT\b" manga_ai_studio/gui/box_item.py` → nothing

## Threat Surface

The files changed map 1:1 onto the plan's threat model (T-07-01 text paths, T-07-02 `TextStyle.from_dict`) — no NEW surface beyond it: plain-text rendering only (the renderer never rich-texts content), `from_dict` is the single V5 coercion boundary, the bake logs stems/error strings only. No threat flags.

## Known Stubs

None. (`layout(vertical=True)` falls back to the horizontal path until plan 07-03 lands the tategaki layout — documented in the renderer docstring; the default style is horizontal so no production path reaches it. This is a plan-scheduled seam, not a stub.)

## Self-Check

- [x] `manga_ai_studio/core/text_style.py`, `manga_ai_studio/gui/text_renderer.py` exist
- [x] `tests/test_core/test_text_style.py`, `test_typeset_layout.py`, `test_typeset_bake.py` exist
- [x] Commits b3dcefe, 3ae2a72, df36585, 445a88a exist (`git log --oneline -5`)
- [x] Full suite green (634 passed)

## Self-Check: PASSED
