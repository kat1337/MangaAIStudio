# Phase 7: Typesetting (TRAN-02) — render translated text into the page — Research

**Researched:** 2026-08-11
**Domain:** Qt text rendering (PySide6 6.10.1), true CJK vertical typesetting (tategaki), text effects (outline/glow/shadow), multi-select interaction, bake-to-image compositing
**Confidence:** HIGH (external conventions + in-repo seams verified; renderer mechanism is a researched recommendation)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** **Opaque canvas + bake export.** The canvas text switches from the Phase 4 translucent review style (rgba fill + fixed 2px outline) to final-quality **opaque** typeset rendering driven by per-box styling — AND a new export action bakes the typeset text into a copy of the page image. One visual truth: what you see on the canvas is what the export produces. — **Reversibility:** costly.
- **D-02:** **Bake = current page image + composited text, PNG/JPG.** The export renders the page's current image state (cleaned/edited — the same image the canvas shows, same coordinate space as `_ocr.json`) with typeset text composited per box. Sibling of the existing Ctrl+E clean export (PROJ-02), not a replacement.
- **D-03:** **Sidecar placement convention** (mirrors Phase 5 D-22): a `<name>_typeset.png`-style sidecar (exact suffix is planner detail) written **next to the source page** when the page is pristine, into **`cleaned/`** when geometry ops altered the page. — **Reversibility:** costly.
- **D-04:** **Bake content follows the current-focus rule** (Phase 4 D-10): translation when present, else recognized text. Boxes with neither render nothing. WYSIWYG — the bake renders exactly what the canvas shows (view toggles are view-state; whether a hidden text layer suppresses baking is planner discretion, default = bake regardless).
- **D-05:** **Styling controls live in the Inspector** — a styling section added below the existing text fields in `InspectorPanel` (the Inspector expansion; NOT a new dock, toolbar, or dialog). Font family, style, size, color, alignment, effects all set here. — **Reversibility:** reversible.
- **D-06:** **Flat per-box style — no inheritance hierarchy.** Every box stores its own complete style. "Per-page" is implemented as **Select All Boxes + apply** (D-09/D-10), not as page-level defaults that boxes inherit. Do NOT design a page-style cascade. — **Reversibility:** costly.
- **D-07:** **Full style persistence.** Per-box style serializes into the `.mas` page files (rides the existing `PageBox` serialization), AND `_ocr.json` gains a style block per block/line so downstream typesetting tools can reproduce the look. — **Reversibility:** one-way — the `_ocr.json` shape is a published contract (Phase 5 D-19); adding the style block extends it, but changing the block's shape later breaks consumers.
- **D-08:** **Shift+click toggles selection; clicking empty canvas clears; a "Select All Boxes" action (Ctrl+A — currently unbound) selects every box on the page.** No marquee rubber-band (offered, declined). Lifts Phase 3 D-08 single-select.
- **D-09:** **Multi-select enables styling + move + delete (grouped geometry).** Dragging any selected box moves the group; Delete removes all selected. **Resize stays single-box** (the corner-handle state machine is untouched). Grouped move/delete must push ONE BOXES snapshot (one Ctrl+Z reverses the whole group op — Phase 3 D-12 "silent + undo recovers"; delete stays silent, no confirm). — **Reversibility:** reversible.
- **D-10:** **Common-value inspector.** In multi-select the Inspector's text fields (recognized/translation/bubble) disable (per-box content), while the styling section edits ALL selected boxes; style fields showing differing values display a **"Mixed"** state until overridden. One style commit = one BOXES snapshot + one overlay refresh.
- **D-11:** **True tategaki rendering via a custom vertical layout path** for boxes flagged vertical (`payload.vertical`): glyphs upright, top-to-bottom, columns flowing right-to-left. NOT rotated-horizontal (`QPainter.rotate` on the block — rejected), NOT deferred. This is the phase's highest technical risk: Qt has no `writing-mode: vertical-rl` in its rich-text engine (04-RESEARCH Pitfall 5) — the renderer needs a custom layout approach (per-char/run painting or a custom document layout; exact mechanism is researcher/planner discretion). — **Reversibility:** costly.
- **D-12:** **Vertical render, horizontal edit.** Vertical applies to canvas rendering + bake only; the inline editor (04-05 `QGraphicsProxyWidget` editor) stays horizontal. Editing flow: type horizontally, canvas displays vertical.
- **D-13:** **The existing Inspector "Vertical text" checkbox becomes the live control.** Phase 4's D-06 no-op (metadata write + "Coming soon" tooltip) is replaced by real behavior: checked boxes render tategaki. CTD-detected vertical boxes arrive pre-flagged (`payload.vertical=True`); user boxes flip via the checkbox.
- **D-14:** **Effects = outline + outer glow + drop shadow** (the full common set). The existing 2px dark outline becomes a configurable effect (width + color); outer glow (soft halo) and drop shadow (offset soft shadow) are added. All per-box, set in the Inspector styling section. — **Reversibility:** reversible.
- **D-15:** **Manual font size wins; fit-in-box becomes an explicit per-box "Auto-fit" size option.** With a manual size, text wraps at the box width (Phase 4 `setTextWidth` behavior) and may overflow the box (overflow rendering/clipping policy at bake time is planner discretion). The 04-09 auto-shrink-to-fit remains available as an opt-in Auto-fit mode that preserves today's behavior for sized boxes. — **Reversibility:** reversible.
- **D-16:** **"Increase/decrease font size" = explicit actions** (e.g. a Ctrl+= / Ctrl+- pair) in addition to the Inspector size field, per the deferred list's "increase and decrease font size".

### the agent's Discretion
- **Style data model** — the per-box style shape: a `TextStyle`-style dataclass composed on `PageBox` (composition, not subclassing — Phase 3 D-14 anti-pattern; the vendored `Box` and `TextBlock` stay untouched). Where it hangs (PageBox field vs payload extension), default style values (font/color/size matching today's overlay look is a sensible default), and how `PageBox.copy()` detaches it (Pitfall 8 discipline — snapshots must not alias the style).
- **Effect rendering implementation** — outline via the existing `QTextCharFormat.setTextOutline` (Phase 4 Pattern 3) vs paint-based; glow + shadow via `QPainter` effect passes vs Qt effect classes; how effects compose with the fit-in-box/vertical paths. Performance on the per-mousemove reposition path must not regress (04-08 RC-1 lesson).
- **Tategaki layout mechanism** — per-char paint vs custom `QAbstractTextDocumentLayout`; wrapping/column width rules inside the box; mixed CJK/Latin handling (Japanese convention: Latin/numbers rotate 90°); punctuation compression (kumimoji) depth. Scope to "renders correct upright vertical CJK"; deep typography beyond that can be noted.
- **Bake export details** — action placement (File/Text/Export menu), shortcut (Ctrl+E is taken by clean export; Ctrl+Shift+E by OCR JSON), exact sidecar suffix (`_typeset` vs other), threading (pure PIL/Qt compositing — inline vs Worker per the Phase 2 gate), and whether it follows the `_op_running` gate.
- **Grouped move/delete implementation** — canvas drag state machine extension for multiple items (drag any selected → all move; delta applied to all), one snapshot push, undo flash naming.
- **`_ocr.json` style block schema** — field spelling/placement (block-level vs line-level) consistent with the D-19/D-20 contract; `.mas` style serialization format.
- **"Mixed" state presentation** in the Inspector styling section (disabled/blank vs "Mixed" label).

### Deferred Ideas (OUT OF SCOPE)
- **Machine translation integration (TRAN-01)** — separate v2 phase (ROADMAP explicit). `set_translation()` stays the seam; Phase 7 typesets whatever the translation field holds.
- **Bubble re-sizing / auto-layout** (BallonsTranslator territory) — explicitly NOT in scope (ROADMAP).
- **Vertical editing (tategaki editor)** — D-12 defers it: the inline editor stays horizontal.
- **Marquee rubber-band multi-select** — declined by the user; Shift+click + Select All is the v1 mechanism (D-08).
- **Per-line styling** — styling is per-box flat (D-06); v1 styles the whole box.
- **Font management / bundled fonts** — font selection uses system fonts.
- **Full kumimoji/punctuation compression depth** in the tategaki renderer — render correct upright vertical CJK; deep typography refinements noted as future polish.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TRAN-02 | User can render translated text into the page (basic typesetting: font, size, color) | Promoted from the v2 REQUIREMENTS.md line ("User can render translated text into the page (basic typesetting: font, size, color)" — REQUIREMENTS.md:54) into this phase by the ROADMAP scope. Research support: the full styling feature list (D-05/D-06/D-14/D-15/D-16) maps onto (a) a `TextStyle` dataclass on `PageBox` (composition, `copy()` detachment), (b) a shared typeset renderer module (style→render functions used by canvas overlay AND bake — D-01 single visual truth), (c) the Inspector styling section with common-value/"Mixed" multi-select behavior (D-10), (d) persistence into `.mas` (`pagebox_to_json` extension) and `_ocr.json` (style block on D-19 shape), (e) a bake export compositing via the same renderer + `save_image_optimized`. The tategaki path (D-11/D-13) is the correctness-critical addition: upright CJK + rotated Latin/digits + RTL column flow (W3C convention), implemented as a per-char/run layout (see Pattern 2). |
</phase_requirements>

## Summary

Phase 7 converts Phase 4's translucent review overlay (`BoxItem._text_overlay`, box_item.py:487-608) into real typesetting: per-box styling (font family/style/size/color, H/V alignment, outline/glow/shadow effects), a true tategaki (vertical) rendering path for `payload.vertical` boxes, multi-select as the "per selected boxes / per page" mechanism, style persistence in `.mas` + `_ocr.json`, and a bake export that composites the typeset text into a copy of the page image. The phase's load-bearing discovery is that **the production open-source reference implementation — BallonsTranslator (dmMaze, GPL-3.0, PyQt6, ~5k stars) — already solved every hard problem this phase faces**: it renders manga text via a `QGraphicsTextItem` subclass whose document layout is swapped between `VerticalTextDocumentLayout` and `HorizontalTextDocumentLayout` (custom `QAbstractTextDocumentLayout` subclasses), strokes outlines via `setTextOutline` (horizontal) or alpha-mask dilation (vertical), renders shadows via a numpy-blurred silhouette composited *behind* the fill, caches effects in a background pixmap keyed by content/style, and re-renders the same live items at higher scale for export — the exact "single visual truth" contract D-01 states. This research uses BallonsTranslator's `text_engine/` (layout.py, effect_renderer.py, item.py) as the algorithmic reference **[CITED: github.com/dmMaze/BallonsTranslator]**, NOT as vendored code (GPL-3.0 → GPL-3.0 license-compatible, but the vendoring discipline from Phase 1 D-12 does not require copying 4k-line engines; our render-only scope is far smaller).

**The vertical renderer decision (D-11, the phase's highest risk):** since D-12 explicitly excludes vertical *editing* (no IME, no caret, no hit-test, no selection in the vertical path), the full `QAbstractTextDocumentLayout` machinery — which exists precisely to serve those editing features, and which BallonsTranslator needed for WYSIWYG vertical editing — is **not warranted**. The least-surprising path for a PySide6 render-only codebase is a **per-char/per-run custom layout painted through a shared renderer** (Pattern 2): classify each char (upright CJK/kana vs rotate-90 Latin/digits/ASCII-punct vs vertical-form punctuation), measure with `QFontMetricsF`, lay columns top-to-bottom flowing right-to-left inside the box (wrap at inner height), and paint with `painter.rotate(90)` per rotated run. This composes cleanly with the bake (same renderer paints into a `QPainter` on a page-image copy) and with effects (silhouette-based glow/shadow + glyph-path stroke outline — Pattern 3). It is also headless-testable: layout coordinates are pure functions; paint is verified by rendering to a QImage and asserting pixels (the established pytest-qt `qapp` fixture).

**Primary recommendation:** (1) Add a `TextStyle` dataclass to `PageBox` (composition; defaults mirror the Phase 4 overlay look — Liberation Sans, 2px `#0b0b0e` outline, light opaque fill — with outline ON, glow/shadow OFF); `PageBox.copy()` must detach it (`replace(self, payload=copy.copy(...), style=copy.copy(style))`) — Pitfall 8 discipline. (2) Build ONE shared typeset renderer module (`manga_ai_studio/gui/text_renderer.py` — Qt-dependent, headless-testable, NOT in core/ because text rendering needs QFontMetrics/QPainter; core/ stays pure per the project discipline) exposing `layout()` (pure geometry: horizontal wrap/align/auto-fit; vertical columns RTL) and `paint()` (fill + outline + glow + shadow passes). The canvas overlay becomes a lightweight custom-painted `QGraphicsItem` (or the renderer draws into a pixmap cache) and the bake paints through the same functions — the D-01 single-visual-truth contract with one code path. (3) Multi-select per D-08/D-09: extend `canvas._select_and_begin_move` (Shift+click toggle / plain click clears-others / empty canvas clears all / Ctrl+A selects all), group move = capture the selected set + start rects, apply the same delta, ONE pre-move snapshot (the existing `_boxes_interaction_start_snapshot` pattern); group delete loops `_remove_box`-style removal with ONE snapshot; resize stays single-box. (4) Inspector gains the styling section (D-05) with common-value/"Mixed" behavior (D-10) and the live vertical checkbox (D-13); one style commit → one BOXES push + one overlay refresh. (5) Bake = File menu "Export Typeset Page…" writing `<stem>_typeset.png` per the D-22-mirroring placement rule (D-03) through `save_image_optimized` (image_io.py:47-107 — the exact PROJ-02 writer contract), compositing via the shared renderer at 1:1. **Zero new dependencies** — everything rides PySide6 6.10.1 / PIL 12.0.0 / numpy 2.3.5 (verified in the working env) + stdlib.

## Project Constraints (from AGENTS.md)

- **Pinned Python interpreter (MANDATORY):** `python` on PATH resolves to an unrelated hermes venv (3.11.15). ALWAYS run the pinned interpreter from `start.bat`: `C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe`. Tests: `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest ...`. Baseline at Phase 7 research time: **600 tests collected / green suite** (measured 2026-08-11 via `--collect-only`).
- **PySide6 stack is non-negotiable:** Qt6 desktop GUI (`PySide6>=6.7`, installed 6.10.1). All new widgets use Qt6 standard widgets; no new UI library. [VERIFIED: pyproject.toml dependencies + local probe — PySide6 6.10.1 / PIL 12.0.0 / numpy 2.3.5]
- **GPL v3 licensing:** project is derivative of PanelCleaner. Phase 7 is our own code (styling, effects, tategaki renderer, bake); no new vendoring expected (CONTEXT canonical_refs Licensing). BallonsTranslator is a *reference* for algorithms — do not copy its code wholesale; if any code is adapted, preserve GPL attribution per Phase 1 D-12 discipline.
- **core/ module discipline:** `core/` modules import only stdlib + numpy + PIL (mirror `core/image_io.py`); the typeset renderer needs Qt text APIs, so it must NOT live in `core/` — recommended `manga_ai_studio/gui/text_renderer.py` (imports QtGui/QtWidgets only, no main-window/widget-state deps, testable under pytest-qt's `qapp`).
- **GSD workflow enforcement + ASVS V5 plain-text discipline** (Phase 4 Pattern 3 / 04-RESEARCH security table): styling must NOT introduce `setHtml`/rich-text injection — OCR/translation text is untrusted; keep plain-text rendering (see Security Domain).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Per-box style model (`TextStyle`) | Core (`PageBox` composition) | Persistence (`project_io`/`ocr_export` projections) | Pure dataclass, headless-testable; single source of truth consumed by GUI, undo (BOXES snapshots), `.mas`, `_ocr.json` |
| Style→render functions (layout + paint, horizontal + vertical + effects) | Renderer module (`gui/text_renderer.py` — Qt but not widget-bound) | Canvas overlay item + bake compositor both call it | D-01 single visual truth: one code path for canvas and bake; Qt text APIs required, so not in `core/` |
| Canvas typeset overlay display | GUI (`BoxItem` overlay child, custom-painted) | Renderer (paint) | Display object per Phase 4 D-09; reposition = setPos only (RC-1); layout cache keyed (text, style, rect, vertical) |
| Tategaki layout (D-11) | Renderer (per-char/run layout) | GUI (vertical flag from `payload.vertical`) | Pure geometry functions (columns RTL, wrap at height) headless-testable; paint rotates runs 90° |
| Effects (D-14) | Renderer (glyph-path stroke + silhouette blur passes) | GUI (Inspector effect controls) | Same paint path for canvas + bake; effect pixmap cache bounds allocation (T-01-16) |
| Multi-select (D-08/D-09) | GUI (canvas selection + drag state machine) | Core (BOXES snapshots already full-list) | Qt provides `ItemIsSelectable`/`selectedItems`; group ops emit ONE snapshot (already full-list shape) |
| Common-value/Mixed inspector (D-10) | GUI (`InspectorPanel` styling section) | MainWindow (apply-to-all commit → one BOXES push) | Panel is a follower (Phase 4 pattern); commits route through MainWindow callbacks |
| Bake export (D-01/D-02/D-03/D-04) | GUI (action + placement decision) + renderer (composite) | Core (`image_io.save_image_optimized` writer) | Compositing = renderer paint into QImage of the page copy; writing = existing PROJ-02 writer |
| Style persistence (D-07) | Core (`project_io.pagebox_to_json` + `ocr_export.build_page_ocr_json` extensions) | GUI (save/export triggers) | Pure projections; load-side V5 coercion mirrors existing `json_to_pagebox` |
| Undo for style/group ops | Core (`HistoryManager` BOXES stack, unchanged) | GUI (before-state push discipline) | One snapshot per style commit / group op (D-09/D-10); `PageBox.copy()` detaches style (Pitfall 8) |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PySide6 / Qt6 | 6.10.1 (installed) | ALL rendering + interaction: `QFont`/`QFontMetricsF`, `QTextLayout`, `QPainter`/`QPainterPath`, `QImage` compositing, `QGraphicsItem` overlay, `QFontComboBox`/`QColorDialog`/`QDoubleSpinBox`/`QButtonGroup` Inspector widgets | The project's non-negotiable GUI framework (inherited from Phase 1). Text rendering at glyph level requires Qt's font engine. `[VERIFIED: local probe — PySide6 6.10.1]` |
| numpy | 2.3.5 (installed) | Silhouette alpha extraction + blur for glow/shadow effect passes; bake pixel round-trips | Already installed and used everywhere; BallonsTranslator's shadow path (`apply_shadow_effect`) is numpy-based — the same approach fits our stack. `[VERIFIED: local probe]` |
| Pillow (PIL) | 12.0.0 (installed) | `save_image_optimized` bake writer (PNG `compress_level=9` / JPG `quality=95` `progressive=True`, DPI/mode preserved) | The PROJ-02 writer contract D-02 reuses verbatim; no new writer needed. `[VERIFIED: image_io.py:95-104 + local probe]` |
| Python stdlib (`dataclasses`, `copy`, `json`) | 3.14 stdlib | `TextStyle` dataclass + `replace`/`copy` detachment (Pitfall 8); `.mas`/`_ocr.json` style dicts | Zero-dep serialization; mirrors `PageBox`'s existing `dataclasses.replace` discipline (box_model.py:178). `[VERIFIED: box_model.py:166-178]` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `manga_ai_studio.gui.text_renderer` (NEW, in-repo) | — | Style→render functions: `layout()` (horizontal + vertical geometry) and `paint()` (fill/outline/glow/shadow) | The D-01 shared path used by the canvas overlay AND the bake. Qt-dependent → lives in `gui/`, not `core/` (core discipline) |
| `manga_ai_studio.core.image_io.save_image_optimized` | in-repo | Bake image writer | D-02: same writer as PROJ-02 (PNG/JPG + DPI preservation) |
| `manga_ai_studio.core.ocr_export.build_page_ocr_json` | in-repo | `_ocr.json` style block (D-07) | Extend the block dict with `"style"`; keep the D-19 shape otherwise |
| `manga_ai_studio.core.project_io.pagebox_to_json` / `json_to_pagebox` | in-repo | `.mas` style field (D-07) | Add `"style": pb.style.to_dict()`; load-side V5 coercion + defaults when absent (old `.mas` files lack it) |
| `pytest` + `pytest-qt` (dev extras) | 9.1.1 (dev) | Headless unit tests (qapp fixture for QFontMetrics/QImage) + GUI interaction tests | Already in `pyproject.toml` `[dev]`; `qt_api = pyside6` in pytest.ini |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Per-char/run custom layout for tategaki (RECOMMENDED) | Custom `QAbstractTextDocumentLayout` subclass (BallonsTranslator path) | The document-layout is production-proven (BallonsTranslator VerticalTextDocumentLayout) but exists to serve WYSIWYG vertical EDITING (hitTest, caret, IME, selection — Qt 6.11 doc confirms 6 pure virtuals incl. `hitTest`/`documentChanged`). D-12 excludes vertical editing, so the machinery is dead weight; per-char/run paint is render-only, smaller, and directly testable. `[CITED: doc.qt.io/qt-6/qabstracttextdocumentlayout.html, github.com/dmMaze/BallonsTranslator text_engine/layout.py]` |
| `QPainter.rotate(90)` on the whole block | (rejected by D-11) | Rotates the block as a picture — glyphs lie on their side and line flow is wrong; not tategaki. Only per-run rotation (Latin/digits inside upright columns) is correct. |
| `QGraphicsDropShadowEffect`/`QGraphicsBlurEffect` for shadow/glow | Paint-based silhouette passes (RECOMMENDED) | QGraphics effects apply to the WHOLE item (blurring the sharp text for glow; shadowing the item's full bounding box), work only in scenes (not directly in the bake painter), and are hard to make canvas≡bake identical. Silhouette+blur passes render identically on canvas and bake. `[CITED: BallonsTranslator effect_renderer.py]` |
| Keep `QGraphicsTextItem` + `setTextOutline` for horizontal, custom only for vertical | One unified custom-painted renderer for BOTH orientations (RECOMMENDED) | Two paths double the effect/paint code and the bake must reproduce both; one renderer with a horizontal mode (QTextLayout-based) + vertical mode (per-char) is less total code and guarantees canvas≡bake. The Phase 4 `setTextOutline` remains a valid fallback for outline-only horizontal if the planner prefers minimal churn (flagged in Open Questions). |
| PIL `ImageFilter.GaussianBlur` on the silhouette for glow/shadow | numpy stack blur on the alpha channel | Both work; numpy keeps the effect pass in-array (mirrors BallonsTranslator's `apply_shadow_effect`) and avoids PIL<->QImage round-trips on the canvas path. Planner picks; PIL is acceptable for the bake-only path. |

**Installation:** NONE. `pip install` is not needed — Phase 7 adds zero new packages (verified: PySide6 6.10.1, PIL 12.0.0, numpy 2.3.5, pytest-qt all present in the working env).

**Version verification (run before planning — already verified this session):**
```powershell
& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -c "import PySide6, PIL, numpy; print(PySide6.__version__, PIL.__version__, numpy.__version__)"
# -> PySide6 6.10.1, PIL 12.0.0, numpy 2.3.5
```

## Package Legitimacy Audit

> Phase 7 **installs no new external packages** — the entire feature rides PySide6/PIL/numpy already in the project env. The audit below covers the phase's dependency stack for completeness.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| PySide6 | PyPI | 11 yrs (v6.10.1 published 2026-05-13) | n/a (seam data gap) | code.qt.io (pyside/pyside-setup) | [SUS — unknown-downloads only] | Approved — already installed (Phases 1–6), no install step |
| pillow | PyPI | 14 yrs (v12.0.0) | n/a | github.com/python-pillow/Pillow | [SUS — unknown-downloads only] | Approved — already installed, no install step |
| numpy | PyPI | 20 yrs (v2.3.5) | n/a | (seam data gap; canonical array lib) | [SUS — unknown-downloads only] | Approved — already installed, no install step |
| pytest / pytest-qt | PyPI | 12+ yrs | n/a | github.com/pytest-dev | [SUS — unknown-downloads only] | Approved — already installed, dev extra |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** all four carry the seam's `unknown-downloads` data-gap reason (identical to the Phase 5 audit); none has a postinstall script of concern; all long-established and already exercised by the 600-test suite. **No `checkpoint:human-verify` tasks are needed because nothing is installed in this phase.** BallonsTranslator is NOT installed — it is a read-only algorithmic reference ([CITED: github.com/dmMaze/BallonsTranslator]).

## Architecture Patterns

### System Architecture Diagram

```
┌────────────────────────────── TYPESETTING (TRAN-02) ──────────────────────────────┐
│                                                                                     │
│  InspectorPanel (D-05 styling section, D-10 Mixed, D-13 live vertical checkbox)     │
│     │  commit signals (one per control)                                             │
│     ▼                                                                               │
│  MainWindow (apply style to ALL selected PageBoxes — D-06 flat, D-09/D-10)          │
│     │  ONE before-snapshot (boxes_snapshot) → mutate style → boxes_modified.emit    │
│     ▼                                                                               │
│  PageBox.style (TextStyle dataclass — composition; copy() detaches, Pitfall 8)      │
│     │                                                                               │
│     ├───────────────────────────► canvas BoxItem overlay (custom-painted item)      │
│     │                              renderer.layout(text, style, rect, vertical)     │
│     │                              renderer.paint(painter, ...)                     │
│     │                              per-mousemove: setPos only (RC-1 cache)          │
│     │                                                                               │
│     └───────────────────────────► Bake export (File menu, D-02)                     │
│                                    page QImage copy (Pitfall 2 .copy())             │
│                                    QPainter → renderer.paint per box at 1:1         │
│                                    → numpy → save_image_optimized (PROJ-02 writer)  │
│                                    D-03 placement: pristine→source dir;             │
│                                    geometry-altered→cleaned/ (mirror D-22)          │
│                                                                                     │
│  Tategaki branch (D-11): renderer.layout vertical mode — per-char classification    │
│     upright CJK/kana │ rotate-90 Latin/digits/ASCII-punct │ vertical-form punct     │
│     columns top→bottom, RTL flow, wrap at inner height, per-char centering          │
│                                                                                     │
│  Persistence (D-07): .mas via pagebox_to_json "style" field + _ocr.json block       │
│     "style" dict — both pure projections, load-side V5 coercion                     │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────── MULTI-SELECT (D-08/D-09) ────────────────────────────┐
│  mousePressEvent (canvas.py:979):                                                  │
│     Shift+click on box → toggle item selection (no clear)                          │
│     plain click on box → clear others + select + arm group move                    │
│     click empty canvas → clearSelection + fall through                             │
│  Ctrl+A (action, currently unbound) → select all BoxItems                          │
│  Group move: _move_anchor captures {item: start_rect} for every selected item;     │
│     per mousemove apply same delta to each rect; release emits ONE boxes_modified  │
│  Group delete: keyPressEvent Delete loops selected items, ONE snapshot push        │
│  Resize: unchanged (single-box corner-handle state machine)                        │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

The user enters via three surfaces: the Inspector styling section (per-box/per-selected/per-page via Select All), the canvas (selection + grouped move/delete), and the File menu (bake export). All paths converge on `PageBox.style` — the single source of truth fanned out to the renderer (canvas + bake), undo (BOXES snapshots with detached style), `.mas`, and `_ocr.json`.

### Recommended Project Structure (deltas on the existing tree)

```
manga_ai_studio/
├── core/
│   ├── box_model.py        # EXTEND — TextStyle dataclass (same module as PageBox, or a
│   │                       #   peer module core/text_style.py); PageBox.style field +
│   │                       #   copy() detachment (replace style=copy.copy(style))
│   ├── project_io.py       # EXTEND — pagebox_to_json "style" + json_to_pagebox V5
│   │                       #   coercion/defaults (backward-compat: old .mas has no style)
│   ├── ocr_export.py       # EXTEND — block dict gains "style" (D-07); version policy
│   │                       #   (Open Question: bump OCR_JSON_VERSION vs additive)
│   └── (unchanged: image_io.py, history_manager.py — BOXES snapshots already full-list)
├── gui/
│   ├── text_renderer.py    # NEW — the shared typeset renderer (Qt, headless-testable):
│   │                       #   TextStyle→layout()/paint(); horizontal (QTextLayout) +
│   │                       #   vertical (per-char/run) modes; effects passes; caches
│   ├── box_item.py         # EXTEND — overlay rework: custom-painted typeset child
│   │                       #   (or pixmap-cached paint) driven by pagebox.style;
│   │                       #   vertical mode switch; zoom clamp superseded (see Pattern 1)
│   ├── canvas.py           # EXTEND — multi-select (Shift+click/Ctrl+A), grouped move
│   │                       #   (delta applied to selected set), grouped delete (one push)
│   ├── inspector_panel.py  # EXTEND — styling section (D-05): font family/style/size/
│   │                       #   color/H+V alignment/effects controls; "Mixed" state (D-10);
│   │                       #   vertical checkbox live (D-13)
│   ├── main_window.py      # EXTEND — Select All Boxes (Ctrl+A), Size +/- actions (D-16),
│   │                       #   Export Typeset Page… action (D-02/D-03), style-commit
│   │                       #   routing → one BOXES push + overlay refresh, op-name flash
│   └── (existing: image_viewer.py etc. untouched)
└── tests/                  # Wave 0 — see Validation Architecture
```

### Pattern 1: The shared typeset renderer — ONE code path for canvas and bake (D-01)

**What:** A module owning style→render: `layout(text, style, box_rect, vertical) -> LayoutResult` (pure geometry: line/column rects, per-run glyph placement, ink bounds, overflow flag) and `paint(painter, layout_result, style)` (fill pass, then outline pass, then glow/shadow silhouette passes). The canvas overlay item and the bake compositor call the SAME functions; the only difference is the painter target and a scale (canvas may keep a zoom-independent scene-px size — see note; bake always 1:1).

**When to use:** Everywhere text is rendered — the Phase 4 `BoxItem.refresh_text_overlay` rework (box_item.py:487-565), the bake (D-02), and future consumers (vertical badge, MT preview). This is the D-01 "single visual truth" made structural: the bake cannot drift from the canvas because it is the same code.

**Scene-px sizing contract (supersedes the 04-08 zoom clamp for opaque text):** The Phase 4 overlay font clamp (`[10,28]` viewport px, box_item.py:108/530-535) exists for *review overlay legibility* (04-08 RC-2). D-01 replaces the review overlay with final-quality typesetting where WYSIWYG matters: the style's font size is specified in **scene px = image px**, and the overlay renders at that size, scaling naturally with the canvas zoom exactly like the baked image. The `2/zoom` viewport-px outline (box_item.py:552) likewise becomes the style's scene-px outline width. The 04-08/04-09 machinery (fit-in-box loop, constants `_OVERLAY_FIT_MAX_ITERS=12/_OVERLAY_FIT_STEP=0.9/_OVERLAY_FIT_FLOOR_VP=5.0`, box-adaptive base) is preserved as the **Auto-fit mode** (D-15): `auto_fit=True` runs the bounded shrink-to-fit loop at scene px; `auto_fit=False` renders at the manual size. This is a deliberate UI-SPEC §16 contract change — the `/gsd-ui-phase 7` pass must reconcile it (config `ui_phase: true`).
`[VERIFIED: box_item.py:102-122 (quote: `_OVERLAY_FONT_BASE = 14.0`, `_OVERLAY_BOX_REF_DIM = 100.0`, `_OVERLAY_FIT_MAX_ITERS = 12`, `_OVERLAY_FIT_STEP = 0.9`, `_OVERLAY_FIT_FLOOR_VP = 5.0`, `_OVERLAY_INSET = 2.0`), box_item.py:530-559]`

**Performance (04-08 RC-1 discipline):** `_reposition_text_overlay` is setPos-only (box_item.py:566-580) because `_sync_handles` runs on EVERY mousemove (canvas.py:1022-1023). The renderer preserves this: layout + effect pixmaps are cached keyed by `(text, style, box_rect, vertical)`; reposition never re-layouts. BallonsTranslator does exactly this — effects pre-rendered into `background_pixmap` and blitted per frame `[CITED: BallonsTranslator effect_renderer.py repaint_background/_draw_effects]`.

### Pattern 2: Tategaki — per-char/per-run vertical layout (D-11, the highest-risk decision)

**What:** A custom vertical layout path: split the plain text into runs by the W3C/Unicode orientation rules, lay columns top-to-bottom inside the box, flow columns right-to-left, and paint each run upright or rotated 90°.

**Orientation classification (the D-11 correctness contract):**
- **Upright:** Han/Kana/CJK punctuation with vertical forms — `。．，、：；！？・` (do NOT rotate; the font provides vertical forms) `[CITED: W3C vertical-text article — 'Han characters remain upright'; BallonsTranslator PUNSET_PAUSEORSTOP]`
- **Rotated 90° clockwise (reading top-to-bottom):** Latin letters, ASCII digits, halfwidth ASCII punctuation `[0x21..0x7E]`, dashes/ellipsis (`—…～`), brackets (`「」『』（）…`) `[CITED: W3C — 'Latin script text typically runs down the page, with the letters rotated clockwise'; BallonsTranslator PUNSET_VERNEEDROTATE]`
- **Column positioning:** each column width = max char advance in the column (+ letter spacing); chars centered in the column; columns advance leftward (RTL); wrap when the column exceeds the box INNER height (`box_h - 2*inset`); the column block is positioned within the box per the horizontal-alignment control (right→hug right edge, center→centered, left→hug left edge) and vertical-alignment controls the run's top/middle/bottom offset.
- **Out of scope (CONTEXT Deferred):** kumimoji punctuation compression, tate-chū-yoko digit combining (text-combine-upright), font vertical alternates beyond what the font provides, RTL-script runs bottom-to-top. Note them in the renderer docstring as future polish.

**Why per-char/run paint and not a custom `QAbstractTextDocumentLayout`:** The document-layout exists to serve editing (hitTest, caret, IME, selection) — Qt 6.11 documents 6 pure virtuals including `hitTest()`, `documentChanged()`, and `draw()` `[CITED: doc.qt.io/qt-6/qabstracttextdocumentlayout.html]`. BallonsTranslator needed it for WYSIWYG vertical EDITING; D-12 excludes vertical editing entirely (render-only, plain text, no IME). A per-char/run painter is the least-surprising path for a PySide6 render-only codebase: pure-Python geometry (headless-testable), `QPainter` draw calls, and it composes directly with the bake (Pattern 1). The rotated runs are painted with `painter.save(); painter.translate(x, y); painter.rotate(90); painter.drawText(0, 0, run)` — per-RUN rotation, which is true tategaki (D-11 explicitly rejects whole-block rotation).

**BallonsTranslator's algorithm as the reference** (NOT vendored; GPL-3.0): `VerticalTextDocumentLayout.layoutBlock` creates one `QTextLine` per column with `setNumColumns(1)` + `QTextOption.WrapAnywhere`, decrements `x_offset` per column (RTL), measures `tbr` (tight bounding rect) per char for centering, and in `draw()` rotates `PUNSET_VERNEEDROTATE` lines via `QTransform(0,1,0,-1,0,0,...)` while drawing upright lines with per-char offsets computed from the rasterized alpha bbox (`punc_actual_rect` — render the line, `cv2.boundingRect` the nonzero mask). Column wrapping: `out_of_vspace` when `char_bottom > available_height` → next column. This validates the conventions above against real manga output shipped since 2021. `[CITED: github.com/dmMaze/BallonsTranslator ballontranslator/ui/text_engine/layout.py]`

### Pattern 3: Effects — glyph-path stroke (outline) + silhouette blur (glow/shadow) (D-14)

**What:** Three paint passes around the fill pass, rendered by the shared renderer so canvas ≡ bake:
1. **Outline:** for each glyph run, build the glyph path with `QPainterPath.addText(0, 0, font, run)` and `painter.strokePath(path, QPen(color, width, RoundCap, RoundJoin))` — a crisp outline of any width, works identically for horizontal and vertical runs. (The Phase 4 `QTextCharFormat.setTextOutline` — box_item.py:552 — remains the correct mechanism for document-based text; the unified renderer's path stroke achieves the same look with one code path. BallonsTranslator horizontal strokes via `setTextOutline` on a cloned document and vertical strokes via alpha-mask dilation — `cv2.dilate` with an ellipse kernel `[CITED: BallonsTranslator effect_renderer.py _paint_cloned_document_stroke/_paint_vertical_stroke]`; either mechanism is acceptable for the outline effect, the visual contract is: outline width + color per box.)
2. **Outer glow:** render the glyph silhouette (the outline pass result, or the text alpha alone) into an offscreen `QImage`, blur the alpha channel (numpy stack blur — O(1)/px, mirrors BallonsTranslator's `apply_shadow_effect` — or PIL `GaussianBlur` for the bake), colorize with the glow color, and composite BEHIND the fill (`CompositionMode_DestinationOver`). Glow = shadow with zero offset.
3. **Drop shadow:** same silhouette-blur pass, translated by the style's offset `(dx, dy) * font_size` and composited `DestinationOver` with the shadow color/opacity.
`[CITED: BallonsTranslator effect_renderer.py _render_effect_surface (silhouette → apply_shadow_effect(radius, strength, color, offset) → DestinationOver composite)]`

**When to use:** Always for the three effects; the passes are skipped when disabled (the outline is ON by default at 2px `#0b0b0e` — the Phase 4 look; glow/shadow OFF). Effect geometry must EXPAND the item's bounding rect (effect padding = outline half-width + blur radius + |offset| — BallonsTranslator's `_conservative_effect_padding`), so the canvas overlay's `boundingRect()` accounts for halo/shadow and the bake draws the same passes into the page painter without clipping them.

**Performance:** effect pixmaps are cached keyed `(style, layout generation)`; a style/text/box change re-renders the cache, a move repositions only (RC-1). Allocation is BOUNDED (T-01-16): cap the effect surface dimension (e.g. 4096px) and pixel budget like BallonsTranslator's `EFFECT_CACHE_MAX_DIMENSION`/`EFFECT_CACHE_MAX_PIXELS`; out-of-bounds degrades to no-glow rather than OOM `[CITED: BallonsTranslator effect_renderer.py _new_effect_pixmap + EffectRasterAllocationError]`.

### Pattern 4: Multi-select — Qt primitives + ONE snapshot per group op (D-08/D-09)

**What:** Lift Phase 3 D-08 single-select using what Qt already gives: `BoxItem` has `ItemIsSelectable` (box_item.py:323), `QGraphicsScene` tracks `selectedItems()`, and `boxes_snapshot()` (canvas.py:1710-1746) already materializes the FULL page list — so group undo needs no stack changes, only before-state discipline.

- **Selection entry (canvas.py:1048-1051 `_select_and_begin_move`):** `Shift+click` on a box → toggle `item.setSelected(...)` WITHOUT clearing others; plain click → clear others + select + arm move (today's behavior); empty-canvas click → `clearSelection()` (extends `_deselect_box`, canvas.py:1804-1808). **Ctrl+A** → new MainWindow action (currently unbound — verified: no `Ctrl+A` in main_window.py shortcut map) selecting every `_box_items` entry.
- **Grouped move:** `_select_and_begin_move` records `{item: start_rect}` for EVERY selected item (today it records one: `_move_anchor_box_pos`/`_move_start_rect`, canvas.py:1855-1860); `mouseMoveEvent` applies the same delta to each selected rect (setRect + `_sync_handles` per item — reposition-only, no re-layout); release emits `boxes_modified(before)` ONCE with the pre-move snapshot (the existing `_boxes_interaction_start_snapshot` captured at arm time, canvas.py:1863). One Ctrl+Z reverses the whole group (the snapshot is already full-list).
- **Grouped delete:** the Delete/Backspace handler (canvas.py:1470-1475) loops `selectedItems()`, removing each (silent, no confirm — Phase 3 D-12), then emits ONE `boxes_modified(before)` with the pre-delete snapshot.
- **Resize:** untouched — corner-handle dispatch (`_begin_resize`, canvas.py:1869-1880) only arms when the hit item is a `CornerHandle`, and a multi-selection's handles render on every selected box per `_sync_handles`; if needed, the planner may gate resize to the single-selected case (recommended: resize requires exactly one selected box — a handle press on a multi-selection either resizes that one box or is ignored; simplest correct v1: resize only when exactly one box is selected).
- **Undo flash naming:** group/style ops need op names for the `_undo_op_label_for_result` pattern (06-WR-01) — e.g. "move 3 boxes" / "style 4 boxes" / "delete 2 boxes" (planner discretion on exact strings).

### Pattern 5: Bake export — renderer composite into the page copy + `save_image_optimized` (D-01/D-02/D-03/D-04)

**What:** "Export Typeset Page…" (File menu, sibling of Export Page Ctrl+E — main_window.py:382-383): (1) get the CURRENT page image exactly as the canvas shows it (detached `.copy()` — Pitfall 2 discipline; the `get_image_numpy`/`set_image_from_numpy` round-trip used by PROJ-02), (2) open a `QPainter` on that image's `QImage` form, (3) for each box in `boxes_snapshot()` order, run `renderer.paint(painter, renderer.layout(...))` at 1:1 using the D-04 current-focus text (`_current_focus_text`, box_item.py:720-746 — translation when present, else recognized; empty boxes render nothing), (4) close the painter, convert to numpy, write via `save_image_optimized(page_np, dest, original=page_path)` — the PROJ-02 writer contract (PNG `compress_level=9`; JPG `quality=95` + `progressive`; DPI/mode preserved, image_io.py:95-104). (5) **Placement per D-03 (mirror D-22):** pristine page → `page_path.parent / f"{stem}_typeset.png"`; geometry-altered page → `page_path.parent / "cleaned" / f"{stem}_typeset.png"` — reuse `ocr_export.ocr_json_target_dir`'s shape (ocr_export.py:199-212) or mirror it.

**When to use:** Always for the bake. **Threading:** single-page compositing is sub-second (pure Qt paint on one QImage); run INLINE on the GUI thread for v1, gated by `_op_running` (disabled during ops like other actions) — the Worker pattern is warranted only if a batch typeset export is added later (out of scope). The bake never touches the live canvas image (works on a detached copy) and never draws chrome (no box borders, handles, badges, mask overlay — the renderer paints text only).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tategaki layout algorithm | An ad-hoc "draw chars down then hope" loop | The BallonsTranslator vertical-layout conventions (per-char classification, per-column `QTextLine`-style metrics, RTL column flow, rotated-run transform) as the algorithmic reference | Production-proven since 2021 on real manga; the orientation/punctuation classification (PUNSET sets) encodes W3C/JLREQ behavior that is easy to get subtly wrong. Reference, don't vendor. `[CITED: BallonsTranslator layout.py; W3C vertical-text article]` |
| Text rendering pipeline | A custom QPainter-only glyph rasterizer | Qt's font engine: `QFontMetricsF` for advance/tight-rect measures, `QPainterPath.addText` for glyph outlines, `QPainter.drawText`/`QTextLayout` for fills | Qt does shaping, hinting, and fallback for free; a hand-rolled glyph pipeline is enormous scope with worse results. |
| Glow/shadow blur | A hand-written convolution | numpy stack blur on the alpha channel (or PIL `GaussianBlur` for the bake) | O(1)/px, deterministic, headless-testable; matches BallonsTranslator's proven `apply_shadow_effect` shape. |
| Bake image writer | A new encode path | `core/image_io.save_image_optimized` (image_io.py:47-107) | D-02 locks the PROJ-02 writer contract (compress_level=9 / quality=95 / DPI preserved); duplicating it would drift. |
| `.mas`/`_ocr.json` style serialization | Hand-rolled dict assembly at each call site | `TextStyle.to_dict()/from_dict()` + V5-coerced load, called from `pagebox_to_json` and `build_page_ocr_json` | One spelling under test (mirrors Phase 5's "the shape IS the contract" — D-19 one-way); load-side coercion mirrors `json_to_pagebox` (project_io.py:209-232). |
| Group undo | A new stack or per-box entries | ONE BOXES snapshot per group op (before-state, existing `_boxes_interaction_start_snapshot` discipline) | `boxes_snapshot()` is already full-list (canvas.py:1710-1746); one Ctrl+Z reverses the group (Phase 3 D-12 / 03-02). |
| Font picker | A raw `QComboBox` of font names | `QFontComboBox` | Standard Qt widget with native font preview + system-font enumeration; avoids hand-rolled family lists. |
| Color picker | A custom palette widget | `QColorDialog` (with a small swatch `QToolButton` precedent) | Standard Qt; the dark-QSS contract only needs the trigger button styled. |

**Key insight:** the phase's hard parts — tategaki correctness, effects, canvas≡bake fidelity — are all *solved problems in the open-source reference* (BallonsTranslator) and in the existing codebase (Phase 4 overlay machinery, PROJ-02 writer, full-list snapshots). The novel work is the *combination*: a flat per-box style model wired through one renderer into two outputs (canvas + bake) with multi-select as the bulk-edit mechanism. Resist building new infrastructure (no new undo stack, no new writer, no new layout engine from scratch).

## Runtime State Inventory

> Phase 7 is NOT a rename/refactor/migration phase — the section is included because D-03 adds a NEW on-disk output convention and D-07 extends two published formats; the planner must know what state exists today.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None in existing formats — `.mas` page files and `_ocr.json` exist WITHOUT style fields (old files must load with defaults). | Backward-compatible load: `json_to_pagebox`/`ocr_export` treat a missing style block as defaults (no migration of existing files — the style field is additive, D-07). |
| Live service config | None — no external services. | None. |
| OS-registered state | None. | None. |
| Secrets/env vars | None new. | None. |
| Build artifacts | None — no installed/renamed artifacts; the new `_typeset` sidecar is an OUTPUT artifact, not a rename. | None. |

**Canonical question answered:** after every file in the repo is updated, no runtime system holds an old string/name — this phase adds state (style fields, `_typeset` outputs), it does not rename anything. Verified: no renames in scope (CONTEXT decisions D-01..D-16 contain no rename).

## Common Pitfalls

### Pitfall 1: Style aliasing across undo snapshots (Pitfall 8 applied to `TextStyle`)
**What goes wrong:** A style edit commits, the user hits Ctrl+Z, and the style stays at the post-edit value (undo is a no-op) — or a group style commit restores only one box's style.
**Why it happens:** `PageBox.copy()` detaches ONLY the payload (`replace(self, payload=_copy.copy(self.payload))` — box_model.py:178). If `style` rides on the same dataclass and the snapshot shares the live `TextStyle` object, the in-place mutation aliases the pushed before-state (the exact 04-05 CR-01 lesson, mirrored for style).
**How to avoid:** `PageBox.copy()` becomes `replace(self, payload=_copy.copy(self.payload), style=_copy.copy(self.style))` (or `dataclasses.replace(self.style)`); never mutate a `TextStyle` in place — always assign a fresh instance via `dataclasses.replace`. Regression test: `test_style_undo_restores_previous_style` (mirror `tests/test_payload_aliasing.py`).
**Warning signs:** Ctrl+Z after a font/color change does nothing; a multi-box style commit undoes for some boxes only.
`[VERIFIED: box_model.py:166-178]`

### Pitfall 2: The bake and the canvas diverge (D-01 violation)
**What goes wrong:** The baked PNG looks different from the canvas: different font size (the 04-08 zoom clamp still applies on canvas), missing effects, or chrome (box borders/badges) baked into the image.
**Why it happens:** Two rendering paths (overlay doc-format vs a bake-only compositor) drift; or the bake reuses `QGraphicsScene.render` on the live scene, painting box borders/handles; or the overlay's viewport-px clamp (box_item.py:535) makes the canvas size differ from the 1:1 bake.
**How to avoid:** One renderer (Pattern 1) for both; the overlay renders scene-px style sizes (Pattern 1 note — the [10,28] clamp is superseded for opaque text, planner confirms in the UI-SPEC pass); the bake paints text ONLY (never scene.render of the whole scene). Regression guard: a bake-equivalence pixel test — render box text via `renderer.paint` into a QImage both at scale 1.0 and assert canvas-style output == bake output for the same (text, style, rect).
**Warning signs:** Export shows text at a different size than the canvas; exported image contains green/amber box borders or bubble badges.

### Pitfall 3: Vertical text that is NOT tategaki (D-11 correctness regression)
**What goes wrong:** Vertical boxes render rotated-horizontal (glyphs lying sideways, columns flowing the wrong way), Latin/numbers upright instead of rotated, or punctuation floating mis-centered.
**Why it happens:** Reaching for `QPainter.rotate(90)` on the whole block (D-11 explicitly rejected), or a per-char loop that rotates everything, or ignoring the orientation classification (W3C: Han upright / Latin+digits rotated / vertical-form punctuation upright).
**How to avoid:** Follow Pattern 2's classification + column rules; per-RUN rotation only for `[0x21..0x7E]` + brackets/dashes; per-char centering in the column; columns wrap at inner height and flow RTL. Regression tests: pure-layout tests — a known string's char positions (column x decreasing for later chars of a wrapped line), a Latin run's rotated advance (height not width), a CJK string's upright advance (width not height), punctuation set membership (which chars rotate).
**Warning signs:** A vertical box's first column sits at the LEFT edge; Latin letters stand upright in the column; whole-block rotation artifacts at box corners.

### Pitfall 4: Ctrl+-/Ctrl+= shortcut collisions (D-16 vs the locked shortcut map)
**What goes wrong:** Binding "Decrease Font Size" to Ctrl+- fires BOTH the zoom-out action and the size action (Qt Ambiguous shortcut overload — the CR-14 lesson from Phase 6), or the new bindings silently steal from existing actions.
**Why it happens:** `action_zoom_out` already owns `QKeySequence("Ctrl+-")` (main_window.py:499-500) and `action_zoom_in` owns `Ctrl++`; Ctrl+E (export page, main_window.py:383) and Ctrl+Shift+E (OCR JSON, main_window.py:657-658) are taken, so the bake action needs a distinct binding.
**How to avoid:** Verify every new binding against the map: **Ctrl+A is free** (verified — Select All Boxes), **Ctrl+= is free** (distinct from Ctrl++ — recommend for Increase Font Size), **Ctrl+Shift+- is free** (recommend for Decrease Font Size; plain Ctrl+- is taken by zoom-out — do NOT bind it). Bake export: recommend `Ctrl+Alt+E` or NO shortcut (menu-only) — the planner picks, but must assert a single binding per sequence (the 05 Pitfall 8 / CR-14 discipline: `grep` the map).
**Warning signs:** Zoom out also shrinks the font; two file dialogs/menus open on one keypress.
`[VERIFIED: main_window.py:382-383, 499-500, 657-658; no Ctrl+A binding anywhere in main_window.py]`

### Pitfall 5: Effect OOM / jank on the per-mousemove path (04-08 RC-1 + T-01-16)
**What goes wrong:** Dragging a box becomes laggy (full re-layout + effect re-blur per mousemove), or a huge glow radius on a big box allocates a gigantic pixmap and freezes/OOMs the app.
**Why it happens:** Naive wiring re-runs layout+paint on every `mouseMoveEvent` (canvas calls `_sync_handles` per mousemove, canvas.py:1022-1023), or effect surfaces are sized unbounded.
**How to avoid:** Layout + effect-pixmap caches keyed `(text, style, box_rect, vertical)` — reposition stays setPos-only; bounded effect allocation (max surface dimension + pixel budget; degrade to no-glow with a loguru warning rather than OOM — the BallonsTranslator `EffectRasterAllocationError` policy); radii/widths clamped in the Inspector spinboxes (V5 bounds). Warning sign test: a style-commit loop test asserting the layout cache is hit on reposition (mock the layout function, assert call count).
**Warning signs:** Drag latency grows with box count; a 300px glow radius on a full-page box freezes the UI; memory climbs on repeated style tweaks.

### Pitfall 6: `_ocr.json` style block breaks the published contract (D-07 one-way)
**What goes wrong:** The style block shape differs between the `.mas` field and the `_ocr.json` block (spelling drift), or the version string changes without a consumer decision, or the block is written at line-level where consumers expect block-level (D-19's `blocks[]`).
**Why it happens:** Two writers (project_io + ocr_export) hand-build dicts; the D-19 shape is a published one-way contract (05-CONTEXT D-19).
**How to avoid:** `TextStyle.to_dict()` is the SINGLE spelling used by both writers (one dict builder under test); the `_ocr.json` block gains `"style": {...}` at BLOCK level (per-box flat style, D-06); version policy is a planner decision (see Open Question 4 — recommended: bump `OCR_JSON_VERSION` to `"2"` with the additive block, or keep `"1"` and document that consumers must ignore unknown keys; pick once and pin in the plan).
**Warning signs:** `.mas` round-trip passes but `_ocr.json` omits style; two spellings of `font_family` across writers; downstream tool fails to parse the versioned file.
`[VERIFIED: ocr_export.py:69 OCR_JSON_VERSION = "1"; ocr_export.py:164-176 block dict; project_io.py:191-206 pagebox_to_json]`

### Pitfall 7: Inspector "Mixed" state corrupts boxes on commit (D-10)
**What goes wrong:** With differing styles selected, a user opens the color picker and the commit writes one box's color to ALL boxes — or the "Mixed" sentinel value itself (an empty string / sentinel enum) gets persisted into `TextStyle`.
**Why it happens:** The styling widgets populate from the FIRST box in the selection instead of tracking "differing values → Mixed", and the commit callback persists the widget's raw value.
**How to avoid:** The Inspector styling section computes the per-control value set across the selection: all-equal → show the value; differing → show a "Mixed" sentinel (e.g. empty `QFontComboBox` text + disabled-ish look or a "—" label — presentation is planner discretion per CONTEXT); a commit only fires when the user actively changes a control (WR-01 no-op-guard discipline already in the panel, inspector_panel.py:351-372); the commit applies the NEW value to every selected box and the sentinel never leaves the widget layer. Regression test: select two boxes with different colors → open panel → assert Mixed shown → change color → both boxes' styles update, one BOXES snapshot.
**Warning signs:** A no-op focus cycle on a Mixed field writes a stale value; after applying to a Mixed selection, some boxes revert to defaults.

### Pitfall 8: Old `.mas`/`_ocr.json` files break on load (backward compatibility)
**What goes wrong:** Opening a Phase 5-era `.mas` (no style key) raises ProjectFormatError, or `json_to_pagebox`'s required-key validation (project_io.py:224-232) rejects the file.
**Why it happens:** `json_to_pagebox` validates required keys strictly — a new required `"style"` key would break every existing project file.
**How to avoid:** `"style"` is OPTIONAL on load: `style_raw = d.get("style")` → `TextStyle.from_dict(style_raw)` or defaults when absent. Same for `_ocr.json` consumers (they ignore unknown keys). Regression test: `test_legacy_mas_without_style_loads_with_defaults` (build a Phase 5-shape pagebox dict, load, assert default style).
**Warning signs:** Opening a saved project from before this phase fails with "pagebox missing required key".

### Pitfall 9: The vertical flag writes but the canvas doesn't re-render (D-13)
**What goes wrong:** Toggling the Inspector "Vertical text" checkbox updates `payload.vertical` but the overlay stays horizontal until some unrelated refresh.
**Why it happens:** The current checkbox commit (inspector_panel.py:199-203, tooltip "Coming soon — preserves the vertical flag for export") writes metadata only; `refresh_text_overlay` doesn't read `payload.vertical` yet.
**How to avoid:** The vertical commit path: write `payload.vertical` AND call the box's overlay refresh with the vertical flag (the renderer switches layout mode); D-11/D-12 keep the inline editor horizontal — only the render path changes. Regression test: toggle the checkbox → the overlay item's layout mode flips (assert via the renderer's mode or a cached-mode marker).
**Warning signs:** Checkbox state changes in the panel but the canvas text orientation never changes; the tooltip still says "Coming soon".
`[VERIFIED: inspector_panel.py:199-203]`

## Code Examples

Verified patterns from official sources, the reference project, and the in-repo codebase:

### Common Operation 1: `TextStyle` dataclass + `PageBox.copy()` detachment (Pitfall 8 discipline)
```python
# Source: derived from PageBox.copy() [VERIFIED: box_model.py:166-178] and the
# Phase 4 dataclasses.replace pattern; serialization spellings are planner discretion
from dataclasses import dataclass, replace, field
import copy as _copy

@dataclass
class TextStyle:
    """Flat per-box style (D-06 — no inheritance). Scene-px font size (Pattern 1)."""
    font_family: str = "Liberation Sans"      # Phase 4 overlay default [VERIFIED: box_item.py:104]
    bold: bool = False
    italic: bool = False
    font_size_px: float | None = None         # None = Auto-fit (D-15)
    auto_fit: bool = True                     # opt-in fit-in-box preserves 04-09 behavior (D-15)
    color: str = "#e8e8ea"                    # opaque fill per D-01 (overlay fill rgba(232,232,234,0.85) [VERIFIED: box_item.py:102])
    align_h: str = "center"                   # "left" | "center" | "right"
    align_v: str = "middle"                   # "top" | "middle" | "bottom"
    vertical: bool = False                    # render tategaki (D-11) — mirrors payload.vertical (D-13)
    outline: dict = field(default_factory=lambda: {"enabled": True, "color": "#0b0b0e", "width_px": 2.0})
    glow: dict = field(default_factory=lambda: {"enabled": False, "color": "#ffffff", "radius_px": 6.0, "opacity": 0.8})
    shadow: dict = field(default_factory=lambda: {"enabled": False, "color": "#000000", "radius_px": 4.0, "dx": 0.0, "dy": 0.04, "opacity": 0.6})

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict | None) -> "TextStyle":
        # V5 discipline: type-check + clamp every numeric (size 1..1024, widths/radii
        # 0..256, opacity 0..1); unknown keys ignored; d=None -> defaults (Pitfall 8).
        ...

# PageBox gains the field; copy() detaches BOTH mutable members (Pitfall 1):
def copy(self) -> "PageBox":
    return replace(self, payload=_copy.copy(self.payload), style=_copy.copy(self.style))
```

### Common Operation 2: Vertical layout core — orientation classification + column flow (D-11)
```python
# Source: conventions from the W3C vertical-text article [CITED: w3c.github.io/i18n-drafts/
# articles/vertical-text/index.en] + BallonsTranslator PUNSET sets [CITED: layout.py];
# pure geometry — headless-testable

# Halfwidth ASCII (letters/digits/punct) rotates 90° in vertical text (W3C mixed default).
_ASCII_ROTATE = set(chr(i) for i in range(0x21, 0x7F))
# Brackets/dashes/ellipsis also rotate; vertical-form punctuation stays upright.
_ROTATE_EXTRA = {"「", "」", "『", "』", "（", "）", "《", "》", "〈", "〉", "【", "】", "—", "…", "～", "-", "(", ")"}
_ALIGN_CENTER = {"。", "．", "，", "、", "·", "：", "；", "！", "？"}  # upright + centered

def char_rotates(ch: str) -> bool:
    return ch in _ASCII_ROTATE or ch in _ROTATE_EXTRA

def layout_vertical(text: str, style, inner_w: float, inner_h: float) -> list[dict]:
    """Per-char placement: [{char, x, y, rotate, w, h}...].
    Columns top->bottom, flow right-to-left (first column at the right edge or per
    align_h); wrap when the column exceeds inner_h; column width = max char advance
    in the column (+ letter spacing). Measure via QFontMetricsF(style.font).
    """
    ...
```

### Common Operation 3: Rotated-run painting (per-RUN rotate — NOT whole-block)
```python
# Source: BallonsTranslator VerticalTextDocumentLayout.draw per-line QTransform [CITED]
# — per-run painter rotate produces the same result (D-11 rejects whole-block rotation)
painter.save()
painter.translate(x, y)           # column position
painter.rotate(90)                # clockwise: reads top-to-bottom (W3C mixed default)
painter.drawText(0, 0, latin_run) # drawn along the rotated axis
painter.restore()
```

### Common Operation 4: Outline via glyph path (unified horizontal + vertical)
```python
# Source: Qt QPainterPath.addText (Qt6 Gui) + BallonsTranslator stroke-pass concept [CITED]
path = QPainterPath()
path.addText(QPointF(0, 0), font, run_text)
painter.strokePath(path, QPen(QColor(style.outline["color"]), style.outline["width_px"],
                              Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
painter.fillPath(path, QBrush(QColor(style.color)))
```

### Common Operation 5: Shadow/glow silhouette pass (numpy blur, DestinationOver)
```python
# Source: BallonsTranslator apply_shadow_effect + _render_effect_surface [CITED];
# silhouette = the glyph alpha mask rendered offscreen; glow = shadow with dx=dy=0
alpha = silhouette_np[..., 3]
blurred = stack_blur_alpha(alpha, radius_px)          # O(1)/px numpy pass
shadow = np.zeros_like(silhouette_np)
shadow[..., 0], shadow[..., 1], shadow[..., 2] = rgb
shadow[..., 3] = (blurred * opacity).astype(np.uint8)
shadow_qimg = numpy_to_qimage(shadow).copy()          # Pitfall 2 .copy()
painter.save()
painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOver)
painter.drawImage(QPointF(x + dx_px, y + dy_px), shadow_qimg)
painter.restore()
```

### Common Operation 6: Grouped move — one snapshot, delta applied to the selected set (D-09)
```python
# Source: in-repo _select_and_begin_move / _advance_move pattern [VERIFIED: canvas.py:1841-1867]
# arm time (Shift NOT held — plain click cleared others first):
self._group_move = {item: QRectF(item.rect()) for item in self._box_items if item.isSelected()}
self._boxes_interaction_start_snapshot = self.boxes_snapshot()   # ONE before-state (full list)
# per mousemove (reposition-only — RC-1 discipline, no re-layout):
for item, start_rect in self._group_move.items():
    item.setRect(start_rect.translated(dx, dy))
    item._sync_handles()
# release: emit self.boxes_modified.emit(self._boxes_interaction_start_snapshot) ONCE
```

### Common Operation 7: Bake composite — renderer paint into the page copy (D-02/D-04)
```python
# Source: in-repo save_image_optimized [VERIFIED: image_io.py:47-107] + _current_focus_text
# [VERIFIED: box_item.py:720-746] + D-22 placement shape [VERIFIED: ocr_export.py:199-222]
def bake_typeset_page(page_np: np.ndarray, boxes: list[PageBox], renderer) -> np.ndarray:
    qimg = numpy_to_qimage(page_np).copy()          # Pitfall 2 — never the live canvas image
    painter = QPainter(qimg)
    for pb in boxes:
        text = current_focus_text(pb)               # D-04: translation else recognized
        if not text:
            continue
        vertical = pb.style.vertical or (pb.payload.vertical if pb.payload else False)  # D-13
        result = renderer.layout(text, pb.style, pb.box, vertical=vertical)
        renderer.paint(painter, result, pb.style)   # fill + outline + glow + shadow at 1:1
    painter.end()
    return qimage_to_numpy(qimg).copy()
# writer: save_image_optimized(result, dest, original=page_path)
# placement (D-03 mirror D-22): pristine -> page_path.parent / f"{stem}_typeset.png"
#   geometry-altered -> page_path.parent / "cleaned" / f"{stem}_typeset.png"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Translucent review overlay with hardcoded style (Phase 4 D-11, box_item.py:102-104) | Opaque per-box typesetting driven by `TextStyle` (D-01/D-06) | This phase | The canvas becomes the deliverable; WYSIWYG canvas ≡ bake (D-01) |
| `QPainter.rotate(90)` whole-block "vertical" (rejected in 04-RESEARCH Pitfall 5) | True tategaki via per-char/run layout (D-11): upright CJK, rotated Latin, RTL columns | This phase | Correct manga vertical typesetting — the phase's acceptance dimension |
| `setTextOutline`-only outline (Phase 4 Pattern 3) | Three effects (D-14): outline + glow + shadow via glyph-path stroke + silhouette blur | This phase | Reader-facing effects (the "artwork is the sole saturated surface" exception) |
| Single-select (Phase 3 D-08) | Multi-select: Shift+click toggle, Ctrl+A all, grouped move/delete (D-08/D-09) | This phase | Per-page styling = Select All + apply (D-06) |
| Hardcoded `_OVERLAY_*` constants + zoom clamp [10,28] vp (04-08/04-09) | Style-specified scene-px size; Auto-fit as the opt-in 04-09 loop (D-15) | This phase | Manual font size wins; zoom-independent typesetting |
| Qt rich-text has NO vertical layout (04-RESEARCH Pitfall 5 — forum.qt.io/topic/105181) | Custom per-char/run vertical layout; production-proven alternatives exist (BallonsTranslator VerticalTextDocumentLayout, since 2021) | This phase | The D-11 seam closes with a renderer instead of a document engine |

**Deprecated/outdated:**
- **The `[10,28]` viewport-px overlay font clamp + `2/zoom` viewport-px outline (04-08 RC-2/RC-3, box_item.py:108/535/552):** superseded for the OPAQUE typeset text by scene-px style sizes (Pattern 1 note). The clamp's review-legibility purpose dies with the translucent overlay (D-01). The UI-SPEC pass must reconcile §16.
- **The Inspector vertical checkbox "Coming soon" tooltip (inspector_panel.py:200-202):** D-13 makes it live — remove the tooltip.
- **`setTextOutline` as the ONLY effect mechanism:** still valid for document text; the unified renderer uses glyph-path stroke so horizontal and vertical share one code path (Pattern 3).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The per-char/per-run custom painter (Pattern 2) is the right tategaki mechanism for a RENDER-ONLY scope; the custom `QAbstractTextDocumentLayout` path is not warranted without vertical editing (D-12). | Patterns 2 | MEDIUM — if the user later wants WYSIWYG vertical editing or per-char selection, the renderer's layout must be re-exposed through a document layout. Mitigation: keep the vertical layout as pure geometry functions (not paint-inlined) so a future document-layout wrapper can reuse them. |
| A2 | Scene-px style sizing (Pattern 1 note) is the right D-01 interpretation; the 04-08 zoom clamp is superseded for opaque text. | Pattern 1 / State of the Art | MEDIUM — this changes the approved 04-UI-SPEC §16 contract; the `/gsd-ui-phase 7` pass + user check must confirm small text at low zoom (scaled with artwork) is acceptable. Fallback: keep a viewport-px floor for the canvas while the bake stays scene-px — but that reintroduces canvas≠bake divergence (Pitfall 2). |
| A3 | In the vertical path, the align_v control positions the column run top/middle/bottom within the box and align_h positions the column block right/center/left. | Pattern 2 | LOW — alternative readings exist (align along the column axis), but this is the least-surprising mapping; UI-SPEC pass can adjust copy. |
| A4 | The bake runs INLINE (no Worker) — single-page compositing is sub-second; `_op_running` gating applies like other actions. | Pattern 5 | LOW — if a batch typeset export appears (out of scope), the Worker pattern slots in unchanged (batch_runner contract). |
| A5 | `_ocr.json` version policy: bump `OCR_JSON_VERSION` to `"2"` (additive style block) is the recommended reading of D-07's "extend it, don't change its shape". | Open Question 4 | MEDIUM — keeping `"1"` is defensible (additive keys, consumers ignoring unknown keys); the planner must pick once and pin it, since D-19 is one-way. |
| A6 | `TextStyle` defaults (Liberation Sans / `#e8e8ea` opaque fill / 2px `#0b0b0e` outline / glow+shadow off / `auto_fit=True`) preserve today's look per CONTEXT discretion wording. | Code Example 1 | LOW — the UI-SPEC pass may adjust colors; defaults are data, not architecture. |
| A7 | The QFontComboBox/QColorDialog widget set satisfies the dark-QSS + D-05 Inspector contract without custom widgets. | Don't Hand-Roll | LOW — QFontComboBox popup styling under QSS is cosmetic; the panel's existing QSS pattern extends (inspector_panel.py:64-89). |

## Open Questions

1. **Tategaki mechanism — per-char/run painter vs custom document layout (D-11 discretion).**
   - What we know: render-only scope (D-12); BallonsTranslator uses a full `QAbstractTextDocumentLayout` because it edits vertically; Qt 6.11 API verified; per-char paint is smaller and headless-testable.
   - What's unclear: whether future phases will need vertical editing/hit-testing (the 04-RESEARCH Pitfall 5 flag stays for a future vertical-EDIT phase).
   - Recommendation: **per-char/run painter with pure-geometry layout functions** (A1). The planner should structure the layout functions so a future document-layout wrapper can consume them.

2. **Horizontal render mechanism inside the shared renderer — QTextLayout vs keeping the existing QGraphicsTextItem + setTextOutline.**
   - What we know: the existing document path is proven (box_item.py:487-565) but cannot do glow/shadow without silhouette passes, and the bake must reproduce it.
   - Recommendation: **unified custom renderer** for both orientations (Pattern 3); if the planner prefers minimal churn for horizontal, keep `QGraphicsTextItem` for horizontal + custom vertical, and implement glow/shadow as a silhouette pixmap drawn behind the text item — but then the bake needs the same two paths (Pitfall 2 risk). Pick ONE and pin it in the plan.

3. **Overflow policy for manual-size text that exceeds the box (D-15 planner discretion).**
   - What we know: manual size may overflow; auto-fit exists as opt-in.
   - Recommendation: **bake clips to the box rect** (painter clip — text stays inside its bubble); **canvas shows the overflow unclipped** (the user's visual cue to shrink/enable auto-fit). Document both in the plan; the UI-SPEC pass confirms the copy.

4. **`_ocr.json` version + style-block placement (D-07).**
   - What we know: `OCR_JSON_VERSION = "1"` is pinned (ocr_export.py:69); D-19 is one-way; D-06 style is per-box flat.
   - Recommendation: block-level `"style": TextStyle.to_dict()` (matching the block's existing `box`/`vertical`/`text` shape); version policy = bump to `"2"` (A5) unless the planner decides additive-with-"1"; pin the exact JSON in the plan (Phase 5 precedent: plan 05-03 pinned the shape under test).

5. **Bake action shortcut + menu placement (D-02/D-03 discretion).**
   - What we know: Ctrl+E (export page), Ctrl+Shift+E (OCR JSON), Ctrl+O/S/Shift+S/Q/R, M/Shift+M/T/P/D/C, Ctrl+0/1/+/- all taken; Ctrl+A free (Select All Boxes).
   - Recommendation: File menu "Export Typeset Page…" next to "Export Page…" (main_window.py:382); shortcut `Ctrl+Alt+E` or none (Pitfall 4); suffix `_typeset` (D-03's `_typeset.png`-style); follow the `_op_running` gate + `_refresh_action_states`.

6. **Grouped resize interaction (D-09: "Resize stays single-box").**
   - What we know: handles render on every selected box (box_item.py:429-432 `_sync_handles`); `_begin_resize` arms on any handle hit (canvas.py:1869).
   - Recommendation: gate resize to exactly-one-selected (a handle press with multiple selected = no-op or single-box resize; planner picks). Simplest v1: resize only when exactly one box is selected.

## Environment Availability

> Phase 7 adds NO new external dependencies — all required libraries are already installed in the working environment.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python (pyenv) | Runtime + tests | ✓ | 3.14.2 (pinned in start.bat — never bare `python`) | — |
| PySide6 | ALL rendering/interaction (QPainter, QFontMetricsF, widgets) | ✓ | 6.10.1 | — |
| Pillow | Bake writer (`save_image_optimized`) | ✓ | 12.0.0 | — |
| numpy | Effect blur passes, bake round-trips | ✓ | 2.3.5 | — |
| pytest / pytest-qt | Validation (qapp fixture for QFontMetrics/QImage tests) | ✓ | 9.1.1 (dev extra) | — |
| System CJK fonts | Tategaki glyph rendering (Japanese translation text) | ✓ (Windows ships Yu Gothic UI / MS Gothic; Liberation Sans has no CJK) | OS-provided | Default `Liberation Sans` renders CJK via Qt font fallback; the end-of-phase human gate picks/verifies a real CJK font |
| QFontComboBox font list | Inspector font picker | ✓ (system fonts) | OS-provided | — |

**Missing dependencies with no fallback:** none — the phase is fully covered by installed packages + OS fonts.
**Missing dependencies with fallback:** CJK font selection is a real-font human-gate item (font fallback works but the UI-SPEC should recommend a default CJK-capable family for the styling section, e.g. "Yu Gothic UI" on Windows); this does not block execution.

## Validation Architecture

> `workflow.nyquist_validation` is `true` in `.planning/config.json` (line 25) — this section applies and is the source for VALIDATION.md.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 + pytest-qt (`qt_api = pyside6` in pytest.ini; the `qapp` fixture provides the QGuiApplication QFontMetrics/QImage/QPainter tests need) |
| Config file | `pytest.ini` (testpaths=tests, markers `unit`/`gui`) |
| Quick run command | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_core/test_text_style.py tests/test_core/test_typeset_layout.py tests/test_core/test_typeset_effects.py -q` |
| Full suite command | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q` |

**Baseline measured 2026-08-11:** 600 tests collected (full suite green at Phase 6 close). Existing infrastructure: `tests/conftest.py` (PySide6 importorskip), `tests/test_core/` (17 files — extend `test_box_model.py`, `test_history_boxes.py`, `test_project_io.py`, `test_ocr_export.py`), GUI tests (`test_gui_boxes.py`, `test_gui_canvas.py`, `test_gui_project.py`, `test_gui_export.py`).

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRAN-02 | `TextStyle` dataclass: defaults, `to_dict`/`from_dict` round-trip, V5 clamping (size/width/radius/opacity bounds) | unit | `pytest tests/test_core/test_text_style.py -x` | ❌ Wave 0 |
| TRAN-02 | `PageBox.copy()` detaches style (Pitfall 8/1: style change → undo restores previous; snapshot does not alias) | unit | `pytest tests/test_core/test_text_style.py::test_style_copy_detaches -x` + extend `tests/test_core/test_history_boxes.py` | ❌ Wave 0 |
| TRAN-02 | `.mas` round-trip: style field survives save/load; legacy `.mas` WITHOUT style loads with defaults (Pitfall 8) | unit | `pytest tests/test_core/test_project_io.py::test_style_field_round_trip -x` | ❌ Wave 0 (extend) |
| TRAN-02 | `_ocr.json` block gains `"style"` (D-07 shape test, version policy pinned) | unit | `pytest tests/test_core/test_ocr_export.py::test_style_block_shape -x` | ❌ Wave 0 (extend) |
| TRAN-02 | Horizontal layout: wrap at inner width, alignment (H+V), manual size vs auto-fit (bounded loop), overflow flag | unit | `pytest tests/test_core/test_typeset_layout.py -x` | ❌ Wave 0 |
| TRAN-02 | Vertical layout (D-11): char classification (upright CJK / rotated ASCII+brackets / vertical-form punct), column RTL order (later columns at smaller x), wrap at inner height, per-char centering, Latin-run rotated advance (uses height not width) | unit | `pytest tests/test_core/test_typeset_layout.py::test_vertical_* -x` | ❌ Wave 0 |
| TRAN-02 | Effects (D-14) pixel tests: outline ring (stroke color present, fill color inside), glow halo (alpha > 0 outside glyph bbox within radius), shadow offset (silhouette present at +dx/+dy), effect padding expands rect | unit (QImage pixels) | `pytest tests/test_core/test_typeset_effects.py -x` | ❌ Wave 0 |
| TRAN-02 | Bake composite: text color present inside box rect, page color outside; boxes with neither text render nothing (D-04); bake ≡ canvas renderer at 1:1 (same inputs → same pixels) | unit (QImage pixels) | `pytest tests/test_core/test_typeset_bake.py -x` | ❌ Wave 0 |
| TRAN-02 | Bake placement (D-03 mirror D-22): pristine → source dir `<stem>_typeset.png`; geometry-altered → `cleaned/` (created if missing); writer = `save_image_optimized` contract (PNG/JPG kwargs + DPI) | unit | `pytest tests/test_core/test_typeset_bake.py::test_placement_rule -x` | ❌ Wave 0 |
| TRAN-02 | Multi-select: Shift+click toggles without clearing; plain click clears others; empty-canvas click clears all; Ctrl+A selects every box | gui | `pytest tests/test_gui_boxes.py::test_multi_select_* -x` | ❌ Wave 0 (extend) |
| TRAN-02 | Grouped move: drag one selected → ALL selected rects shift by the same delta; ONE BOXES entry (one Ctrl+Z restores the whole group); grouped delete: one snapshot, silent | gui | `pytest tests/test_gui_boxes.py::test_group_move_one_undo -x` | ❌ Wave 0 (extend) |
| TRAN-02 | Resize stays single-box (multi-selection handle press does not arm a group resize) | gui | `pytest tests/test_gui_boxes.py::test_resize_single_box_only -x` | ❌ Wave 0 (extend) |
| TRAN-02 | Inspector styling section (D-05): font/size/color/alignment/effects commits apply to ALL selected boxes; ONE BOXES snapshot + ONE overlay refresh per commit | gui | `pytest tests/test_gui_inspector_styling.py -x` | ❌ Wave 0 |
| TRAN-02 | Common-value/Mixed (D-10): differing styles → "Mixed" sentinel; text fields disabled in multi-select; commit overrides all; sentinel never persists (Pitfall 7) | gui | `pytest tests/test_gui_inspector_styling.py::test_mixed_state -x` | ❌ Wave 0 |
| TRAN-02 | Live vertical checkbox (D-13): toggling flips the overlay layout mode; tooltip removed; inline editor stays horizontal (D-12) | gui | `pytest tests/test_gui_boxes.py::test_vertical_checkbox_live -x` | ❌ Wave 0 (extend) |
| TRAN-02 | Size +/- actions (D-16): Ctrl+= / Ctrl+Shift+- adjust the selected box(es) size; no shortcut collision (Pitfall 4 — grep gate: each sequence bound once) | gui | `pytest tests/test_gui_boxes.py::test_size_plus_minus_actions -x` | ❌ Wave 0 (extend) |
| TRAN-02 | Bake action wiring: File menu action enabled per `_op_running` gate; writes the D-03 sidecar; status flash | gui | `pytest tests/test_gui_export.py::test_typeset_export_action -x` | ❌ Wave 0 (extend) |
| TRAN-02 | Overlay reposition stays setPos-only (RC-1 regression): mousemove during group move does NOT re-run layout (layout-cache hit asserted) | gui | `pytest tests/test_gui_boxes.py::test_group_move_no_relayout -x` | ❌ Wave 0 (extend) |

### Sampling Rate
- **Per task commit:** the affected module's test files: `pytest tests/test_core/test_text_style.py tests/test_core/test_typeset_layout.py tests/test_core/test_typeset_effects.py tests/test_core/test_typeset_bake.py -q`
- **Per wave merge:** `pytest -q` (full suite, ~1-2 min — 600-test baseline)
- **Phase gate:** Full suite green before `/gsd-verify-work`, plus the end-of-phase human gate (config `human_verify_mode: end-of-phase`): (1) real tategaki on a real manga page with a CJK font (upright glyphs, RTL columns, rotated Latin/numbers), (2) effects look on artwork (outline/glow/shadow), (3) bake WYSIWYG — the exported PNG matches the canvas at 100%, (4) Ctrl+A / Shift+click feel, (5) Inspector styling with a real font + color session.

### Wave 0 Gaps
- [ ] `tests/test_core/test_text_style.py` — TextStyle dataclass + serialization + copy detachment + V5 clamps (TRAN-02)
- [ ] `tests/test_core/test_typeset_layout.py` — horizontal wrap/align/auto-fit + vertical classification/columns/RTL/wrap/centering (TRAN-02, D-11)
- [ ] `tests/test_core/test_typeset_effects.py` — outline/glow/shadow pixel tests + effect padding + allocation bounds (TRAN-02, D-14)
- [ ] `tests/test_core/test_typeset_bake.py` — bake composite pixels + D-04 content rule + D-03 placement + writer contract (TRAN-02, D-01/D-02)
- [ ] Extend `tests/test_core/test_box_model.py` + `test_history_boxes.py` — PageBox.style field, copy() detachment, style undo regression (Pitfall 8/1)
- [ ] Extend `tests/test_core/test_project_io.py` — style field round-trip + legacy-file defaults (D-07, Pitfall 8)
- [ ] Extend `tests/test_core/test_ocr_export.py` — style block shape + version policy (D-07)
- [ ] `tests/test_gui_inspector_styling.py` — styling section, Mixed state, one-commit-one-snapshot (D-05/D-10)
- [ ] Extend `tests/test_gui_boxes.py` — multi-select, grouped move/delete, single resize, vertical checkbox live, size +/- actions, no-relayout regression (D-08/D-09/D-13/D-16)
- [ ] Extend `tests/test_gui_export.py` — typeset export action + sidecar placement (D-02/D-03)
- [ ] Framework: no new installs (pytest/pytest-qt already in `[dev]`)

## Security Domain

> `workflow.security_enforcement` is `true` (config.json:47, ASVS level 1) — this section applies.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — (single-user desktop app) |
| V3 Session Management | no | — (no sessions) |
| V4 Access Control | no | — (no multi-user model) |
| V5 Input Validation | **yes** | Styling MUST NOT introduce `setHtml`/rich-text rendering — OCR/translation text is untrusted; keep plain-text rendering (the Phase 4 Pattern 3 discipline; `QGraphicsTextItem.setPlainText`/QTextLayout plain runs only). Style values loaded from `.mas`/`_ocr.json` are untrusted-file boundaries: `TextStyle.from_dict` type-checks + clamps every numeric (font size 1..1024, outline width 0..256, glow/shadow radius 0..256, opacity 0..1), bounds the font-family string, and rejects unknown effect keys; `json_to_pagebox`-style coercion mirrors project_io.py:209-232. Inspector spinboxes/clamps bound the same ranges at the UI. |
| V6 Cryptography | no | — (no crypto; sha256 integrity is Phase 5's, unchanged) |
| V7 Error Handling | **yes** | Effect allocation failures degrade to no-glow + loguru warning, never crash (T-01-08 + BallonsTranslator EffectRasterAllocationError policy); corrupt style blocks on load → "Couldn't open '{filename}'." critical dialog per the Phase 5 corrupt-project copy, no partial session mutation. |
| V8 Data Protection | no | — (no sensitive data; style fields are not secrets) |
| V12 Files & Resources | **yes** | Bake writes via `save_image_optimized` with a user-chosen/derived path (atomic temp + os.replace where the writer supports it; sidecar name derives from the page stem — no user-supplied path components beyond the dialog). Effect pixmap allocation is BOUNDED (max dimension + pixel budget, T-01-16 analog) so a crafted style (huge radius) cannot OOM the app. |

### Known Threat Patterns for the Qt text-rendering stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Rich-text injection via OCR/translation text (HTML/script in the text field) | Tampering | Plain-text rendering ONLY: `setPlainText`/QTextLayout plain runs; NEVER `setHtml` on OCR/translation content (the ASVS V5 rule from Phase 4's security table, restated for the styled renderer). |
| Crafted `.mas`/`_ocr.json` style block (huge sizes/radii, wrong types, unknown keys) | DoS / Tampering | `TextStyle.from_dict` strict type-check + clamp (bounds above); unknown keys ignored; failure → corrupt-project dialog, session untouched (Phase 5 pattern). |
| Effect-allocation blowup (a full-page box with a 300px glow) | DoS | Bounded effect surface (max dimension + pixel budget); degrade to no-glow with a loguru warning instead of OOM (BallonsTranslator policy). |
| Log injection via crafted text | Tampering | Loguru logs page stems + error strings only, never raw OCR/translation text (Phase 2 batch-report discipline, unchanged). |
| Shortcut ambiguity (double-bound sequences, e.g. Ctrl+-) | Spoofing (UI) | Grep-gate each new binding once (Pitfall 4; the Phase 5 Ctrl+O / Phase 6 CR-14 lesson): Ctrl+A, Ctrl+=, Ctrl+Shift+- verified free this session. |

## Sources

### Primary (HIGH confidence)
- **In-repo source reads (this session):** `gui/box_item.py` (:102-122 constants, :487-608 overlay pipeline, :566-580 reposition, :720-746 `_current_focus_text`, :429-432 `_sync_handles`), `core/box_model.py` (:85-94 PageBox fields, :166-178 `copy()`), `core/project_io.py` (:182-206 `pagebox_to_json`, :209-232 `json_to_pagebox`), `core/ocr_export.py` (:69 version, :121-182 builder, :199-222 D-22 dirs), `core/image_io.py` (:47-107 `save_image_optimized`), `gui/canvas.py` (:979-1085 mouse dispatch, :1470-1475 Delete, :1599-1645 set_boxes, :1710-1746 boxes_snapshot, :1804-1815 deselect/selected, :1841-1880 move/resize arm, :2013-2027 `_remove_box`), `gui/inspector_panel.py` (:64-89 QSS, :199-203 vertical no-op, :220-307 load/clear, :320-372 commit guards), `gui/main_window.py` (:382-383 Ctrl+E, :499-500 Ctrl+-, :657-658 Ctrl+Shift+E), `pyproject.toml`, `pytest.ini`, `.planning/config.json` — all `[VERIFIED: path:lines + verbatim quotes]`.
- **Local probes (this session):** PySide6 6.10.1 / PIL 12.0.0 / numpy 2.3.5 on Python 3.14.2; suite baseline 600 collected.
- **`.planning` contracts:** 07-CONTEXT.md (D-01..D-16 + discretion + canonical refs), 04-RESEARCH.md (Pitfall 5, Pattern 3), 05-RESEARCH.md (Pitfall 8, D-19/D-22), ROADMAP.md §Phase 7, REQUIREMENTS.md TRAN-02 — `[VERIFIED: read this session]`.

### Secondary (MEDIUM confidence)
- **W3C "Styling vertical Chinese, Japanese, Korean and Mongolian text"** (w3c.github.io/i18n-drafts/articles/vertical-text/index.en) — `writing-mode: vertical-rl` (lines top-to-bottom, columns RTL), Han upright / Latin+digits rotated (text-orientation mixed), fullwidth upright, tate-chū-yoko (text-combine-upright) — the D-11 correctness contract. `[CITED]`
- **BallonsTranslator source (dmMaze, GPL-3.0)** — `ballontranslator/ui/text_engine/{item,layout,effect_renderer}.py` + README: custom `QAbstractTextDocumentLayout` per orientation (VerticalTextDocumentLayout: per-column QTextLine, `setNumColumns(1)`, WrapAnywhere, RTL x-decrement, per-line QTransform for rotated runs, per-char centering via rasterized alpha bbox), effects (setTextOutline cloned-doc stroke / alpha dilation; numpy-blurred silhouette shadow DestinationOver; background-pixmap caching; export render at higher scale), FontFormat dataclass, Ctrl+A multi-select, squeezeBoundingRect fit-to-box, headless `--ldpi` rendering. Fetched this session (raw files). `[CITED: github.com/dmMaze/BallonsTranslator]`
- **Qt 6.11 QAbstractTextDocumentLayout docs** (doc.qt.io/qt-6/qabstracttextdocumentlayout.html) — the 6 pure-virtual surface (documentChanged, draw, documentSize, blockBoundingRect, frameBoundingRect, hitTest, pageCount) + setDocumentLayout install point. `[CITED]`

### Tertiary (LOW confidence)
- Qt Forum vertical-text threads (forum.qt.io/topic/105181, qtcentre.org/threads/11231) — cited in 04-RESEARCH; not re-fetched this session (the BallonsTranslator evidence supersedes them for the mechanism decision). `[CITED via 04-RESEARCH]`
- Unicode/JLREQ kumimoji depth — deferred per CONTEXT; noted as future polish. `[ASSUMED — out of scope]`

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — zero new packages; all versions verified by local probes in the working env; every in-repo seam cited with verbatim quotes read this session.
- Architecture: **HIGH** — the D-11 vertical conventions and the D-14 effect mechanics are grounded in the W3C article + the production BallonsTranslator implementation (both fetched this session); the D-01 shared-renderer and D-09 one-snapshot patterns are grounded in verified in-repo seams. The renderer mechanism choice (per-char/run vs document layout) is a researched recommendation flagged as A1/Open Q1.
- Pitfalls: **HIGH** — every pitfall is grounded in this-session verification (copy() at box_model.py:178, the shortcut map, boxes_snapshot full-list shape, D-19/D-22 published shapes, inspector no-op guards) or in the reference implementation's failure modes (effect allocation bounds).
- Tategaki correctness: **MEDIUM** — the conventions are CITED (W3C/BallonsTranslator), not empirically verified in this repo; the real-font visual check is an end-of-phase human gate.

**Research date:** 2026-08-11
**Valid until:** 2026-09-10 (30 days — stable Qt 6.10/PIL/numpy API surface; the conventions and reference algorithms are version-stable)

---

*Phase: 7-Typesetting (TRAN-02): render translated text into the page*
*Research completed: 2026-08-11*






