# Phase 7: Typesetting (TRAN-02): render translated text into the page - Context

**Gathered:** 2026-08-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver **TRAN-02** — turn Phase 4's translucent review overlay into real typesetting: the canvas renders translated text with full styling controls (font selection, style, size, color, alignment, effects), and a new export action bakes the typeset page image to disk. The scope is the deferred feature list from 04-CONTEXT.md (decision 2026-08-04): font selection (per-box, per-selected-boxes, per-page), font style selector, font size selector, increase/decrease font size, font color, horizontal/vertical alignment, effects (outer glow, outline, etc.), plus the vertical-text (tategaki) seam.

**In scope (from ROADMAP §Phase 7):**
- Full styling controls: font selection (per-box / per-selected-boxes / per-page), font style, font size + increase/decrease, font color, horizontal alignment, vertical alignment, effects (outline, outer glow, drop shadow)
- Multi-select (lifting Phase 3 D-08 single-select) as the mechanism for "per selected boxes"
- Vertical text (tategaki) rendering for `payload.vertical` boxes
- Renderable output: opaque canvas rendering + a bake-to-image export action
- Seams to reuse: `set_translation()` (D-13), `payload.vertical` metadata, Phase 4 overlay zoom/geometry tracking (04-08/04-09), fit-in-box machinery (04-09)

**Explicitly NOT in scope (ROADMAP):**
- MT integration (TRAN-01 — separate v2 phase)
- Bubble re-sizing / auto-layout (BallonsTranslator territory)
- Vertical *editing* (the inline editor stays horizontal — RESEARCH Pitfall 5)

The central insight: **Phase 4 built the render surface; Phase 7 styles it and commits it.** `BoxItem._text_overlay` (`gui/box_item.py:487-565`) already renders the current-focus text (translation when present, else recognized — D-10) with a translucent fill, 2px outline, zoom clamp ([10,28] viewport px), and fit-in-box shrink-to-fit — all hardcoded. Phase 7 replaces the hardcoded style with per-box user-controlled styling, extends the renderer with effects + a true vertical (tategaki) path, lifts single-select to multi-select, persists style in `.mas`/`_ocr.json`, and adds the bake export that composites typeset text into a page image copy.

</domain>

<decisions>
## Implementation Decisions

### Render target & output (discussed — user-locked)
- **D-01:** **Opaque canvas + bake export.** The canvas text switches from the Phase 4 translucent review style (rgba fill + fixed 2px outline) to final-quality **opaque** typeset rendering driven by per-box styling — AND a new export action bakes the typeset text into a copy of the page image. One visual truth: what you see on the canvas is what the export produces. — **Reversibility:** costly — the canvas display contract changes (the translucent review look is superseded); the baked page is a new output artifact downstream tools/users will depend on.
- **D-02:** **Bake = current page image + composited text, PNG/JPG.** The export renders the page's current image state (cleaned/edited — the same image the canvas shows, same coordinate space as `_ocr.json`) with typeset text composited per box. Sibling of the existing Ctrl+E clean export (PROJ-02), not a replacement.
- **D-03:** **Sidecar placement convention** (mirrors Phase 5 D-22): a `<name>_typeset.png`-style sidecar (exact suffix is planner detail) written **next to the source page** when the page is pristine, into **`cleaned/`** when geometry ops altered the page. — **Reversibility:** costly — the placement rule is a convention downstream tooling will rely on (same rationale as D-22).
- **D-04:** **Bake content follows the current-focus rule** (Phase 4 D-10): translation when present, else recognized text. Boxes with neither render nothing. WYSIWYG — the bake renders exactly what the canvas shows (view toggles are view-state; whether a hidden text layer suppresses baking is planner discretion, default = bake regardless).

### Styling UI & persistence (discussed — user-locked)
- **D-05:** **Styling controls live in the Inspector** — a styling section added below the existing text fields in `InspectorPanel` (the Inspector expansion; NOT a new dock, toolbar, or dialog). Font family, style, size, color, alignment, effects all set here. — **Reversibility:** reversible.
- **D-06:** **Flat per-box style — no inheritance hierarchy.** Every box stores its own complete style. "Per-page" is implemented as **Select All Boxes + apply** (D-09/D-10), not as page-level defaults that boxes inherit. The user explicitly chose this over a page-default/inherit model — do NOT design a page-style cascade; per-page work = multi-select + apply. — **Reversibility:** costly — adding an inheritance layer later would restructure the style model; flat storage is the v1 contract.
- **D-07:** **Full style persistence.** Per-box style serializes into the `.mas` page files (rides the existing `PageBox` serialization), AND `_ocr.json` gains a style block per block/line so downstream typesetting tools can reproduce the look. — **Reversibility:** one-way — the `_ocr.json` shape is a published contract (Phase 5 D-19); adding the style block extends it, but changing the block's shape later breaks consumers.

### Multi-select (discussed — user-locked)
- **D-08:** **Shift+click toggles selection; clicking empty canvas clears; a "Select All Boxes" action (Ctrl+A — currently unbound) selects every box on the page.** No marquee rubber-band (offered, declined). Lifts Phase 3 D-08 single-select.
- **D-09:** **Multi-select enables styling + move + delete (grouped geometry).** Dragging any selected box moves the group; Delete removes all selected. **Resize stays single-box** (the corner-handle state machine is untouched). Grouped move/delete must push ONE BOXES snapshot (one Ctrl+Z reverses the whole group op — Phase 3 D-12 "silent + undo recovers"; delete stays silent, no confirm). — **Reversibility:** reversible.
- **D-10:** **Common-value inspector.** In multi-select the Inspector's text fields (recognized/translation/bubble) disable (per-box content), while the styling section edits ALL selected boxes; style fields showing differing values display a **"Mixed"** state until overridden. One style commit = one BOXES snapshot + one overlay refresh.

### Vertical text / tategaki (discussed — user-locked)
- **D-11:** **True tategaki rendering via a custom vertical layout path** for boxes flagged vertical (`payload.vertical`): glyphs upright, top-to-bottom, columns flowing right-to-left. NOT rotated-horizontal (`QPainter.rotate` on the block — rejected), NOT deferred. This is the phase's highest technical risk: Qt has no `writing-mode: vertical-rl` in its rich-text engine (04-RESEARCH Pitfall 5) — the renderer needs a custom layout approach (per-char/run painting or a custom document layout; exact mechanism is researcher/planner discretion). — **Reversibility:** costly — a fallback to rotated text or horizontal would discard real vertical typography work; the custom layout is a bespoke renderer.
- **D-12:** **Vertical render, horizontal edit.** Vertical applies to canvas rendering + bake only; the inline editor (04-05 `QGraphicsProxyWidget` editor) stays horizontal (RESEARCH Pitfall 5 — no vertical QTextEdit). Editing flow: type horizontally, canvas displays vertical.
- **D-13:** **The existing Inspector "Vertical text" checkbox becomes the live control.** Phase 4's D-06 no-op (metadata write + "Coming soon" tooltip) is replaced by real behavior: checked boxes render tategaki. CTD-detected vertical boxes arrive pre-flagged (`payload.vertical=True`); user boxes flip via the checkbox.

### Effects & text sizing (discussed — user-locked)
- **D-14:** **Effects = outline + outer glow + drop shadow** (the full common set). The existing 2px dark outline becomes a configurable effect (width + color); outer glow (soft halo) and drop shadow (offset soft shadow) are added. All per-box, set in the Inspector styling section. — **Reversibility:** reversible.
- **D-15:** **Manual font size wins; fit-in-box becomes an explicit per-box "Auto-fit" size option.** With a manual size, text wraps at the box width (Phase 4 `setTextWidth` behavior) and may overflow the box (overflow rendering/clipping policy at bake time is planner discretion). The 04-09 auto-shrink-to-fit remains available as an opt-in Auto-fit mode that preserves today's behavior for sized boxes. — **Reversibility:** reversible.
- **D-16:** **"Increase/decrease font size" = explicit actions** (e.g. a Ctrl+= / Ctrl+- pair) in addition to the Inspector size field, per the deferred list's "increase and decrease font size".

### Claude's Discretion
- **Style data model** — the per-box style shape: a `TextStyle`-style dataclass composed on `PageBox` (composition, not subclassing — Phase 3 D-14 anti-pattern; the vendored `Box` and `TextBlock` stay untouched). Where it hangs (PageBox field vs payload extension), default style values (font/color/size matching today's overlay look is a sensible default), and how `PageBox.copy()` detaches it (Pitfall 8 discipline — snapshots must not alias the style).
- **Effect rendering implementation** — outline via the existing `QTextCharFormat.setTextOutline` (Phase 4 Pattern 3) vs paint-based; glow + shadow via `QPainter` effect passes vs Qt effect classes; how effects compose with the fit-in-box/vertical paths. Performance on the per-mousemove reposition path must not regress (04-08 RC-1 lesson).
- **Tategaki layout mechanism** — per-char paint vs custom `QAbstractTextDocumentLayout`; wrapping/column width rules inside the box; mixed CJK/Latin handling (Japanese convention: Latin/numbers rotate 90°); punctuation compression (kumimoji) depth. Scope to "renders correct upright vertical CJK"; deep typography beyond that can be noted.
- **Bake export details** — action placement (File/Text/Export menu), shortcut (Ctrl+E is taken by clean export; Ctrl+Shift+E by OCR JSON), exact sidecar suffix (`_typeset` vs other), threading (pure PIL/Qt compositing — inline vs Worker per the Phase 2 gate), and whether it follows the `_op_running` gate.
- **Grouped move/delete implementation** — canvas drag state machine extension for multiple items (drag any selected → all move; delta applied to all), one snapshot push, undo flash naming.
- **`_ocr.json` style block schema** — field spelling/placement (block-level vs line-level) consistent with the D-19/D-20 contract; `.mas` style serialization format.
- **"Mixed" state presentation** in the Inspector styling section (disabled/blank vs "Mixed" label).

### Folded Todos
None — no pending todos matched this phase (todo.match-phase returned 0 matches).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase Scope
- `.planning/ROADMAP.md` §Phase 7 — **THE scope anchor.** Goal ("User can typeset translated text into the page with full styling controls — font selection, style, size, color, alignment, and effects — producing renderable output rather than Phase 4's translucent review overlay"), the inherited scope list (multi-select implication, tategaki seam, seams to reuse, explicitly-NOT-in-scope), requirement TRAN-02 (deferred v2 line in REQUIREMENTS.md), Depends on Phase 4 + Phase 5, 0 plans.
- `.planning/REQUIREMENTS.md` — **TRAN-02** ("User can render translated text into the page (basic typesetting: font, size, color)" — v2 line being promoted into the roadmap by this phase).

### Prior Phase Context (the contracts Phase 7 inherits)
- `.planning/phases/04-ocr-recognition-text-editing/04-CONTEXT.md` — **THE most important ref.** D-10 (current-focus rule — canvas shows translation when present, else recognized; D-04 bake content rule inherits it), D-11 (translucent overlay treatment — superseded by D-01 opaque rendering), D-12 (Toggle Text Overlay `T` — stays), D-06 (vertical toggle v1 no-op + tooltip — D-13 makes it live), D-13 (`set_translation()` seam), the deferred typesetting list (decision 2026-08-04 — the styling feature list this phase inherits, incl. "font selection (per box, per selected boxes and per page)", size +/-, effects).
- `.planning/phases/04-ocr-recognition-text-editing/04-RESEARCH.md` — **Pitfall 5** (vertical text: Qt has no `writing-mode: vertical-rl`; custom `QAbstractTextDocumentLayout` or per-char paint are the real paths; `QPainter.rotate` rotates the block, not true tategaki — D-11 rejects it), **Pattern 3** (`QTextCharFormat.setTextOutline` — the single clean API for outlined glyphs; the outline effect builds on it).
- `.planning/phases/04-ocr-recognition-text-editing/04-UI-SPEC.md` — §15 (inline editor), §16 (text overlay contract: font clamp [10,28] viewport px, box-adaptive base, translucent fill + 2px outline), §17 (badge), §18 (Inspector layout — the styling section extends it), typography table, color tokens, "artwork is the sole saturated surface" principle.
- `.planning/phases/04-ocr-recognition-text-editing/04-04-PLAN.md` / `04-04-SUMMARY.md` — **InspectorPanel structure** (QWidget + QFormLayout, class-scope Signals, `connect_commit_handlers`, vertical checkbox no-op with tooltip).
- `.planning/phases/04-ocr-recognition-text-editing/04-08-SUMMARY.md` / `04-09-PLAN.md` — the zoom-clamp (`apply_overlay_zoom`, viewport-px outline) and fit-in-box (bounded shrink-to-fit loop, floor) machinery D-15 turns into the explicit Auto-fit option.
- `.planning/phases/03-text-box-detection-interaction/03-CONTEXT.md` — **D-08 (single-select — D-08 here lifts it)**, D-12 ("silent + undo recovers" — group move/delete and style commits honor it), BOXES undo stack + unified Ctrl+Z, D-14 composition anti-pattern (style model must not subclass vendored types).
- `.planning/phases/05-project-persistence-image-ops-export/05-CONTEXT.md` — **D-22** (state-dependent output placement — the `_typeset` sidecar rule D-03 mirrors it), **D-19/D-20** (the `_ocr.json` published shape with `lines[]` — the D-07 style block extends it; D-20's `\n`-split line mapping).
- `.planning/phases/05-project-persistence-image-ops-export/05-RESEARCH.md` — Pitfall 8 (payload aliasing — style snapshots must detach), Pitfall 9 (collector dialogs), the .mas container/serialization mechanics the style field joins.
- `.planning/phases/01-cleaning-workspace/01-CONTEXT.md` — Pitfall-2 `.copy()` buffer discipline, thread-safety contract T-01-07, model-load error UX, worker patterns.
- `.planning/phases/06-refinement-polish-deferred-fixes-full-curve-editor/06-CONTEXT.md` — Deferred Ideas explicitly names the typesetting styling toolbar as **Phase 7's** inheritance ("Font/style/size/color/alignment/effects for rendered translation text").

### Existing Code (the build surfaces)
- `manga_ai_studio/gui/box_item.py` — **`BoxItem._text_overlay` + `refresh_text_overlay` (`:487-565`)** — the render surface D-01/D-14/D-15 rebuild: plain-text document, `QTextCharFormat` outline+fill, fit-in-box loop (`_OVERLAY_*` constants `:108-122`), `_reposition_text_overlay` (`:566-580`), `apply_overlay_zoom` (`:591-608`), `_current_focus_text` (`:720-746`), `set_text_overlay_visible` (T toggle `:670-686`). The tategaki path (D-11) and effect rendering (D-14) extend this item.
- `manga_ai_studio/core/box_model.py` — **`PageBox`** (`:53-178`): the style field (D-07/Claude's Discretion) layers on via composition; `copy()` (`:166-178`) must detach it (Pitfall 8); setters (`set_recognized_text`, `set_translation`) unchanged. `payload` = vendored `TextBlock` (`.vertical`/`.language` metadata — D-13 reads `.vertical`).
- `manga_ai_studio/gui/inspector_panel.py` — **`InspectorPanel`** (QFormLayout: bubble/origin/recognized/translation/language/vertical checkbox; class-scope Signals; `connect_commit_handlers`; "Mixed" state pattern target). The D-05 styling section + D-10 common-value behavior + D-13 live vertical checkbox live here.
- `manga_ai_studio/gui/canvas.py` — multi-select surface: `set_boxes` (`:1599`), `boxes_snapshot` (`:1710`), `_selected_box`/`_deselect_box` (`:1804-1815`), selection + move/resize state machine (`:1841-1960`, grouped move/delete per D-09), `_remove_box` (`:2013`), text overlay toggle (`:1669-1691`), `_on_zoom_changed_reposition_handles` (`:1773`).
- `manga_ai_studio/gui/main_window.py` — action wiring: menu builders (`_build_*_menu`), `_op_running` gate, `_on_boxes_modified` → BOXES push + overlay refresh, undo/redo flash naming, shortcut map (Ctrl+A free; Ctrl+E = export page, Ctrl+Shift+E = export OCR JSON — the bake action needs a distinct binding), `_refresh_action_states`.
- `manga_ai_studio/core/ocr_export.py` — the `_ocr.json` writer the D-07 style block extends (per-line `box`+`text` from D-20 `\n`-split).
- `manga_ai_studio/core/project_io.py` — the `.mas` container the style field serializes into (per-page files; manifest).
- `manga_ai_studio/core/image_io.py` — `save_image_optimized` (PNG/JPG writer) — the bake export's image writer (D-02).
- `manga_ai_studio/core/image_file.py` — `ImageFile` (`boxes` slot carrying `PageBox` list — persistence path for style).
- `manga_ai_studio/gui/worker_thread.py` + `core/batch_runner.py` — if the bake export or grouped ops need the Worker pattern.

### UI / Design contract
- `.planning/phases/01-cleaning-workspace/01-UI-SPEC.md` — the design contract: color tokens, spacing, dark QSS, "artwork is the sole saturated surface" (typeset text is reader-facing and CAN be saturated — this is the deliberate exception the typesetting phase makes; planner confirms the UI-SPEC pass). Phase 7 is UI-heavy — a `/gsd-ui-phase 7` pass after planning is expected (config `ui_phase: true`).

### Licensing
- `../PanelCleaner/LICENSE` — GPL v3. Phase 7 is our own code (styling, effects, tategaki renderer, bake export); no new vendoring expected. `TextBlock`/`Box` consumed read-only.

### External References (researcher must fetch)
- True CJK vertical typesetting conventions (upright glyphs, RTL column flow, Latin/numeral rotation, punctuation compression/kumimoji) — the D-11 tategaki renderer's correctness contract.
- Qt vertical-text approaches (custom `QAbstractTextDocumentLayout` vs per-char paint; existing open implementations) — 04-RESEARCH Pitfall 5 flagged this as non-trivial; the researcher confirms the least-surprising path.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`BoxItem._text_overlay` + `refresh_text_overlay`** (`box_item.py:340-565`) — the complete render pipeline Phase 7 restyles: plain-text `QGraphicsTextItem`, `QTextCharFormat.setTextOutline` merge, wrap at inner width, zoom clamp, bounded fit loop. The style-driven version (D-15) replaces the hardcoded constants; the outline effect (D-14) extends the existing `setTextOutline` merge.
- **`_current_focus_text`** (`box_item.py:720-746`) — the D-10 rule D-04 reuses verbatim for the bake.
- **`InspectorPanel`** (`inspector_panel.py`) — the QFormLayout + class-scope Signal + `connect_commit_handlers` pattern the D-05 styling section extends; the vertical checkbox (`vertical_check`, "Coming soon" tooltip) is D-13's live-control site.
- **`PageBox`** (`box_model.py`) — composition-ready dataclass; the style field + its `copy()` detachment slot in cleanly (Pitfall 8 discipline already in place).
- **BOXES undo stack + unified Ctrl+Z** (`history_manager.py`, canvas `_on_boxes_modified`) — style commits and grouped move/delete push ONE snapshot (D-09/D-10); the existing before-state discipline (04-05 CR-01) applies.
- **`save_image_optimized`** (`core/image_io.py`) — the bake export's writer (PNG compress_level=9 / JPG quality=95, DPI preserved — same contract as PROJ-02).
- **`ocr_export.py` / `project_io.py`** — the D-07 persistence targets: the `_ocr.json` lines[] shape (style block rides it) and the `.mas` per-page serialization (style field joins the existing PageBox projection).
- **Qt multi-select primitives** — `QGraphicsItem.ItemIsSelectable` is already set on `BoxItem`; `setSelectionArea`/`selectedItems()` give group selection for free; the canvas drag state machine extends for grouped move (D-09).

### Established Patterns
- **Pitfall 8 (payload aliasing)** — `PageBox.copy()` detaches via `copy.copy`; the style field must detach the same way or undo restores post-edit styles (the 04-REVIEW no-op-undo lesson).
- **Pitfall 2 (`.copy()` discipline)** — every numpy↔QImage bridge detaches; the bake compositor works on a detached page copy (never the live canvas image).
- **Silent + undo recovers** (Phase 3 D-12) — multi-delete stays silent (one Ctrl+Z restores the group); style edits are BOXES-undoable, never confirm-gated.
- **ASVS V5 plain-text** — styling must NOT introduce `setHtml`/rich-text injection (OCR/translation text is untrusted); keep the `QTextCharFormat`-merge approach (Phase 4 Pattern 3), effects included.
- **Single visual truth** (D-01) — the canvas and the bake share one renderer path; the bake must not drift from the canvas look.
- **Thread-safety contract (T-01-07)** — style application is Qt-main-thread; the bake compositor (pure PIL/Qt) is fast and can run inline or via Worker (planner discretion, Phase 2 gate if used).
- **D-14 composition anti-pattern** — the style dataclass composes; vendored `Box`/`TextBlock` stay untouched (never subclass, never add fields to vendored types).
- **Group-op undo naming** — the 05-06/06-WR-01 geometry-op-name pattern for the flash label; grouped move/delete/style commits need consistent op names.

### Integration Points
- **`BoxItem.refresh_text_overlay`** — the style-driven rework: per-box style (D-05/D-06), effects (D-14), manual-size/Auto-fit modes (D-15), tategaki branch (D-11/D-13).
- **`InspectorPanel`** — styling section (D-05), common-value/Mixed behavior (D-10), live vertical checkbox (D-13).
- **`EditorCanvas`** — multi-select: selection change propagation, grouped move/delete in the drag state machine (D-09), `boxes_snapshot` unchanged (full list snapshots already carry the group).
- **`MainWindow`** — Select All Boxes (Ctrl+A) action, Size +/- actions (D-16), the bake export action (D-02/D-03), wiring style commits → `boxes_modified` → BOXES push + overlay refresh.
- **`core/box_model.py`** — the style dataclass + `copy()` detachment + (if chosen) style-aware setters.
- **`core/ocr_export.py` / `core/project_io.py`** — style block in `_ocr.json`, style field in `.mas` (D-07).
- **New: `core/` typeset renderer module (planner discretion)** — the style→render functions (opaque fill, effects, tategaki layout) shared by canvas overlay and bake export (D-01 single-visual-truth), pure-Python headless-testable like `image_ops.py`.

</code_context>

<specifics>
## Specific Ideas

- **"Opaque canvas + bake export"** (user, D-01) — the canvas itself becomes the typeset deliverable; the export is the same rendering written to disk. The user's mental model: no separation between preview and output.
- **Flat per-box style, no cascade** (user, D-06) — the user deliberately rejected the page-default/inherit hierarchy when offered. "Per-page" means selecting all boxes and applying — the ROADMAP's literal "per-page" reading is satisfied by Select All + apply, not by a style-inheritance system.
- **True tategaki chosen knowingly** (user, D-11) — the user picked the custom-layout path over the cheap rotated-block and over deferring, aware it's the risky one (04-RESEARCH Pitfall 5). Downstream agents should treat vertical correctness (upright glyphs, RTL columns) as a real acceptance dimension, not a stretch goal.
- **Vertical render, horizontal edit** (user, D-12) — a pragmatic split: the display does the hard typography; the editor stays the proven horizontal `QGraphicsProxyWidget` (04-05).
- **"The text editor for a manga editor will need font selection (per box, per selected boxes and per page), font style selector, font size selector, increase and decrease font size, font color, horizontal and vertical alignment, ... effects like outer glow, outline, etc"** (user, 04-DISCUSSION-LOG, 2026-08-04) — the verbatim deferred list this phase inherits; D-14 (outline+glow+shadow) and D-16 (size +/-) are its direct readings.
- **WYSIWYG principle** (D-01/D-04) — what the canvas shows bakes, verbatim. The existing view toggles (mask `M`, box `Shift+M`, text `T`) are review-state; the bake reflects the page's styled state.

</specifics>

<deferred>
## Deferred Ideas

- **Machine translation integration (TRAN-01)** — separate v2 phase (ROADMAP explicit). `set_translation()` stays the seam; Phase 7 typesets whatever the translation field holds.
- **Bubble re-sizing / auto-layout** (BallonsTranslator territory) — explicitly NOT in scope (ROADMAP). Boxes are the container; Phase 7 does not auto-size bubbles.
- **Vertical editing (tategaki editor)** — D-12 defers it: the inline editor stays horizontal; a future phase could build a vertical edit widget (04-RESEARCH Pitfall 5 remains the flag).
- **Marquee rubber-band multi-select** — offered during discussion, declined by the user; Shift+click + Select All is the v1 mechanism (D-08). Easy additive later.
- **Per-line styling** — styling is per-box flat (D-06); `_ocr.json` has `lines[]` and the style block could grow per-line, but v1 styles the whole box. A future phase could add line-level overrides.
- **Font management / bundled fonts** — font selection uses system fonts; bundling/installing manga fonts is font-management territory (BallonsTranslator class), not v1.
- **Full kumimoji/punctuation compression depth** in the tategaki renderer — the D-11 renderer should render correct upright vertical CJK; the deep typography refinements (proportional punctuation squeezing, kumimoji) can be noted as future polish if the researcher finds them non-trivial.

</deferred>

---

*Phase: 7-Typesetting (TRAN-02): render translated text into the page*
*Context gathered: 2026-08-10*
