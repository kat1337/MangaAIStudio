# Roadmap: Manga AI Studio

## Overview

Manga AI Studio unifies manga page cleaning, mask editing, text-box OCR, and translation layout into one PySide6 desktop app. The journey starts by adapting PanelCleaner (GPL v3) as the foundation with a model adapter interface, reaching cleaning parity immediately, then builds the novel differentiator — editable text boxes with per-box manga-ocr and a translation layer — and finally lands the project system (save/resume, image ops, JSON export) that turns the editor into a resumable workspace. Each phase is a vertical slice delivering one complete, user-observable capability.

**Mode:** mvp
**Granularity:** standard (5 phases)
**Coverage:** 18/18 v1 requirements mapped; 10/10 v1.2 requirements mapped (Phases 8–9) ✓

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Cleaning Workspace** - Open/navigate pages, detect masks, edit masks, run LaMa inpainting, undo/redo (PanelCleaner + MangaCleaner_GPU foundation) (completed 2026-07-21)
- [x] **Phase 2: Cleaning Output & Batch** - Export cleaned pages as PNG/JPG and batch-process a chapter through cleaning (completed 2026-07-26)
- [x] **Phase 3: Text Box Detection & Interaction** - Detect text boxes as editable objects and select/move/resize/delete them (completed 2026-08-04)
- [x] **Phase 4: OCR Recognition & Text Editing** - Draw-to-OCR regions, correct recognized text, add manual translations (completed 2026-08-08)
- [x] **Phase 5: Project Persistence, Image Ops & Export** - Save/resume .mas projects, basic image operations, export _ocr.json (completed 2026-08-08)
- [x] **Phase 6: Refinement & Polish** - Deferred v1.1 fixes (empty-state overlay, toolbar active-tool highlight, stale hint copy, dialog typography) + full draggable curve editor replacing the Levels dialog (completed 2026-08-09)
- [x] **Phase 7: Typesetting (TRAN-02)** - Render translated text into the page with full styling controls (font, style, size, color, alignment, effects, tategaki) (completed 2026-08-09)
- [ ] **Phase 8: Masker & Selective Inpaint** - Mask dilation radius + box-constrained std-deviation selective per-box inpaint (Phase 3 D-15 seam) with per-box visibility and override + brush-paints-under-boxes tool behavior
- [ ] **Phase 9: UI Rework** - Modular side panel, inspector toggle at top, right-side tools toolbar, "Inspector"→"Typesetting" rename, new "Edit" section

## Phase Details

### Phase 1: Cleaning Workspace

**Goal**: User can clean manga pages interactively — open and navigate images, detect text masks, edit masks, run LaMa inpainting, and undo/redo — reaching cleaning parity using PanelCleaner as the foundation with a model adapter interface.
**Mode:** mvp
**Depends on**: Nothing (first phase — PanelCleaner-based foundation with model adapter interface design)
**Requirements**: CLEAN-01, CLEAN-02, CLEAN-03, CLEAN-04, CLEAN-05, CLEAN-06, FLOW-01, FLOW-02
**Success Criteria** (what must be TRUE):

  1. User can open a single image or a folder of images and view them on a pannable, zoomable canvas with a file-list sidebar to navigate between pages
  2. User can run heatmap text detection on a page and see an auto-generated mask of text regions
  3. User can paint masks with an adjustable brush, plus rectangle and lasso fill tools, and erase mask regions
  4. User can run LaMa inpainting on the mask to remove text and restore the underlying artwork
  5. User can undo and redo both mask (painting) and image (inpainting) operations via separate stacks

**Plans**: 7/7 plans executed

Plans:

- [x] 01-07-PLAN.md

**Wave 1**

- [x] 01-01-PLAN.md — Project scaffolding: Entry point, config system, model adapter base classes

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Image viewer: Canvas with pan/zoom, file list sidebar, navigation (CLEAN-01, FLOW-01)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — Text detection: CTD adapter, async detection worker, mask overlay display (CLEAN-02)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 01-04-PLAN.md — Mask editing: Brush, rectangle, lasso, eraser tools with tool panel (CLEAN-03, CLEAN-04, CLEAN-05)

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 01-05-PLAN.md — LaMa inpainting: Async inpainting worker, result display, preview toggle (CLEAN-06)

**Wave 6** *(blocked on Wave 5 completion)*

- [x] 01-06-PLAN.md — Undo/redo: Separate mask and image stacks, buttons, keyboard shortcuts (FLOW-02)

**UI hint**: yes

### Phase 2: Cleaning Output & Batch

**Goal**: User can get cleaned results out of the app — export a single cleaned page or batch-process an entire chapter through the cleaning pipeline unattended.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: PROJ-02, FLOW-03
**Success Criteria** (what must be TRUE):

  1. User can export a cleaned (text-removed, inpainted) page as PNG or JPG
  2. User can select a chapter folder and batch-process it through the cleaning pipeline (detect → clean → save) with a visible progress indicator

**Plans**: 4/4 plans executed

Plans:
**Wave 1**

- [x] 02-01-PLAN.md — Image output writer: adapted save_optimized (PNG/JPG kwargs, DPI/mode) + D-03 empty-mask copy2 passthrough (PROJ-02, FLOW-03)
- [x] 02-02-PLAN.md — Per-page mask persistence (D-11): ImageFile.has_mask_content + on_page_selected save/restore seam + _last_page_index (FLOW-03)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-03-PLAN.md — Batch runner: batch_detect/batch_clean/batch_detect_and_clean on one Worker loop, abort-between-pages, load-once (FLOW-03)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 02-04-PLAN.md — MainWindow wiring: Export Page (Ctrl+E) + three batch actions + cancel + progress + nav-gate + manual smoke (PROJ-02, FLOW-03)

**UI hint**: yes

### Phase 3: Text Box Detection & Interaction

**Goal**: User can detect text boxes as first-class editable objects (not pixel masks) and correct detection errors by selecting, moving, resizing, and deleting boxes on the canvas.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: TEXT-01, TEXT-03
**Success Criteria** (what must be TRUE):

  1. User can run text-box detection across a page to create editable text-box objects (not a pixel mask)
  2. User can select, move, resize, and delete text boxes on the canvas to correct detection errors

**Plans**: 8/8 plans executed

Plans:

**Wave 1** (parallel — headless foundation, no Qt)

- [x] 03-01-PLAN.md — Vendor structures.py + masker.py (D-14) + PageBox model with D-15 seam + ImageFile.boxes slot + Wave 0 test stubs (TEXT-01)
- [x] 03-02-PLAN.md — HistoryManager BOXES stack + unified-timeline pop (D-10/D-11) + Pitfall-4 (stamp, value) entry-shape widen + test_history.py guard update (TEXT-03)

**Wave 2** *(blocked on Wave 1)*

- [x] 03-03-PLAN.md — BoxItem + CornerHandle + canvas box layer + hit-test dispatch + select/move/resize/delete/Alt+drag-create (TEXT-03)

**Wave 3** *(blocked on Wave 2)*

- [x] 03-04-PLAN.md — Detection seam: _on_detection_finished builds boxes from result["blocks"] (D-01/D-03/D-04) + V5 bounds-clamp (TEXT-01)

**Wave 4** *(blocked on Wave 2 + 3)*

- [x] 03-05-PLAN.md — Per-page box persistence (Phase 2 D-11 mirror) + Surface 13 undo collapse + legacy mask-undo shortcut removal + orphaned string fixes (TEXT-01, TEXT-03)

**Gap-closure waves** (UAT fixes — run via `/gsd-execute-phase 3 --gaps-only`)

- [x] 03-06-PLAN.md — *(Wave 1)* Enlarge CornerHandle hit shape (UAT test 2: resize handle unhittable) — TEXT-03
- [x] 03-07-PLAN.md — *(Wave 2, blocked on 06)* Detection non-undoable baseline (UAT test 3) + moved-box position persistence (UAT test 4) + WR-04 — TEXT-01, TEXT-03
- [x] 03-08-PLAN.md — *(Wave 3, blocked on 07)* Mask stroke baseline seeding (UAT test 3 addendum, Phase 1 FLOW-02 regression) + WR-01 null-mask crash guard — FLOW-02, TEXT-03

**UI hint**: yes

### Phase 4: OCR Recognition & Text Editing

**Goal**: User can recognize text in boxes (auto-detected regions or manually drawn), correct OCR mistakes, and add manual translations — the core differentiator no existing tool offers interactively.
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: TEXT-02, TEXT-04, TEXT-05
**Success Criteria** (what must be TRUE):

  1. User can draw a rectangle on the page and run manga-ocr on just that region to create a box with recognized text (for boxes the auto-detector missed)
  2. User can edit the recognized OCR text inline in a box to correct recognition mistakes
  3. User can add a manual translation as a second text field per box (clean seam for future machine translation)

**Plans**: 10/10 plans executed

Plans:

**Wave 1** (parallel — headless foundation: PageBox model fields + Pitfall 1/8 regression tests; translation parser + reading-order algorithm; OCR adapter + vendored MangaOcr)

- [x] 04-01-PLAN.md — PageBox Phase 4 fields + setters + copy() + boxes_snapshot fix + Pitfall 1/8 regression tests (TEXT-04, TEXT-05)
- [x] 04-02-PLAN.md — translation_parser.py + reading_order.py pure-Python modules (XY-Cut RTL/LTR + preserve-manual) (TEXT-05)
- [x] 04-03-PLAN.md — TorchOCRModel adapter + vendored MangaOcr singleton + backend_factory("ocr") fix (TEXT-02)

**Wave 2** *(blocked on 01)*

- [x] 04-04-PLAN.md — BoxItem text overlay (z=120) + bubble badge (z=140) + InspectorPanel dock + Toggle Text Overlay (T) (TEXT-04, TEXT-05)

**Wave 3** *(blocked on 04)*

- [x] 04-05-PLAN.md — InlineEditor (QGraphicsProxyWidget+QTextEdit) + double-click dispatch + commit/cancel + F2 (TEXT-04)

**Wave 4** *(blocked on 03 + 05)*

- [x] 04-06-PLAN.md — OCR dispatcher (Worker+_op_running+progress) + Text menu (Run OCR / OCR All Ctrl+R) + auto-OCR on draw (D-01) + D-04 gate (TEXT-02)

**Wave 5** *(blocked on 02 + 06)*

- [x] 04-07-PLAN.md — LoadTranslationsDialog (paste + file-import) + parser apply + Auto-Number menu (RTL/LTR) (TEXT-05)
- [x] 04-08-PLAN.md — *(UAT test 1 gap closure)* Overlay geometry tracking on move/resize (RC-1) + zoom font clamp [10,28] viewport px + 2-viewport-px outline (RC-2/RC-3) (TEXT-04)

**Gap-closure waves** (UAT test 1 round 2 — run via `/gsd-execute-phase 4 --gaps-only`)

- [x] 04-09-PLAN.md — *(Wave 1)* Overlay fit-in-box (wrap + box-adaptive font + shrink-to-fit) + menu-bar structure (Recent/Batch = File submenus) + toolbar Open Folder — TEXT-04

**Gap-closure waves** (UAT round 3 — run via `/gsd-execute-phase 4 --gaps-only`)

- [x] 04-10-PLAN.md — *(Wave 1)* Badge sized to its number (digit measurement + re-center + actual-size placement) + bubble # 1 manually assignable (0-sentinel) — TEXT-05

**UI hint**: yes

### Phase 5: Project Persistence, Image Ops & Export

**Goal**: User can save and resume full project state, apply basic image operations, and export OCR/box data for downstream tools — turning the editor into a resumable, interoperable workspace.
**Mode:** mvp
**Depends on**: Phase 1, Phase 4
**Requirements**: PROJ-01, PROJ-03, PROJ-04
**Success Criteria** (what must be TRUE):

  1. User can save the full page state (image, masks, boxes, text, translation) as a `.mas` project file and reopen it to resume work
  2. User can export OCR/box data as a mokuro-style `_ocr.json` file per page for use in downstream tools
  3. User can apply basic image operations to a page: crop, rotate, levels/curves adjustment, resize

**Plans**: 10 plans (9 executed + 1 gap closure)

Plans:

**Wave 1** (parallel — headless core, no Qt)

- [x] 05-01-PLAN.md — .mas serialization core: LZMA2 container + manifest + PageBox mapping + D-06 checksum + D-09 climb + validation (PROJ-01)
- [x] 05-02-PLAN.md — core/image_ops.py: rotate/crop/resize/levels + box/line geometry transforms (PROJ-04)
- [x] 05-03-PLAN.md — core/ocr_export.py: D-19 shape + D-20 \n-split + D-22 location + batch loop (PROJ-03)
- [x] 05-09-PLAN.md — [gap closure] remediate pre-existing tests/test_gui_boxes.py move-round-trip 1px regression (test-side QTest int-truncation; no production change; separate commit) (PROJ-04)

**Wave 2** *(blocked on 05-02)*

- [x] 05-04-PLAN.md — HistoryManager stamp-shared geometry undo (one Ctrl+Z reverses image+mask+boxes) + MainWindow list-apply (PROJ-04)

**Wave 3** *(blocked on 05-01 + 05-04 — main_window.py owned by 05-04's list-apply contract change)*

- [x] 05-05-PLAN.md — Save/Open Project session: dirty tracking, Unsaved Changes prompt, Recent Projects, chapter-climb (PROJ-01)

**Wave 4** *(blocked on 05-05)*

- [x] 05-06-PLAN.md — Image-op GUI apply path: Rotate actions, Levels/Resize dialogs, Show Original gating + re-baseline (PROJ-04)

**Wave 5** *(blocked on 05-06)*

- [x] 05-07-PLAN.md — Crop surface: 6th tool + armed-rect/dim-out + numeric Crop… dialog (PROJ-04)

**Wave 6** *(blocked on 05-03 + 05-07)*

- [x] 05-08-PLAN.md — Export OCR JSON… single + Batch Export OCR JSON (Worker + progress + Cancel) (PROJ-03)

**Gap-closure waves** (UAT fixes — run via `/gsd-execute-phase 5 --gaps-only`)

- [x] 05-10-PLAN.md — *(Wave 1)* Open Project… triggered-bool crash (G-05-1) + Save Project As… default .mas-project folder pre-creation (G-05-2) — PROJ-01

**UI hint**: yes

## Notes & Out-of-Band Concerns

- **Packaging / distribution** (PyInstaller + PySide6 + onnxruntime, model weight distribution ~600MB, Windows AV false positives) is emphasized by research as real work but has **no v1 requirement ID**. It is not a requirement-driven phase here. Recommend inserting it as a decimal phase (e.g., `Phase 5.1`) or a v1.1 milestone once a packaging requirement is formalized. Pitfalls P3, P15, P16, P17 capture the risks.
- **Environment validation** (torch + onnxruntime + numpy<2 coexistence, CUDA→CPU fallback) is a Phase 1 day-one gate (pitfalls P1, P2).
- **Latent QImage buffer bug** in MangaCleaner_GPU's `on_task_finished` must be fixed when lifting canvas code in Phase 1 (pitfall P5).

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Cleaning Workspace | 7/7 | Complete    | 2026-07-23 |
| 2. Cleaning Output & Batch | 4/4 | Complete    | 2026-07-26 |
| 3. Text Box Detection & Interaction | 8/8 | Complete    | 2026-08-04 |
| 4. OCR Recognition & Text Editing | 10/10 | Complete    | 2026-08-08 |
| 5. Project Persistence, Image Ops & Export | 10/10 | Complete    | 2026-08-08 |
| 6. Refinement & Polish | 8/8 | Complete | 2026-08-09 |
| 7. Typesetting (TRAN-02) | 12/12 | Complete | 2026-08-09 |
| 8. Masker & Selective Inpaint | 8/9 | In Progress|  |
| 9. UI Rework | 0/0 | Not started | - |

### Phase 6: Refinement & Polish: deferred fixes + full curve editor

**Goal:** User gets a polished, consistent editor — deferred v1.1 bugs fixed (empty-state overlay on project open, toolbar active-tool highlight, stale Ctrl+O hint copy, dialog typography) and a full draggable curve editor replacing the Levels dialog's fixed black/white/gamma controls.

**Scope (inherited deferrals):**

- Deferred fixes: empty-state overlay persists after project open (`_update_empty_state()` in `_set_image_from_numpy`, canvas.py:710-767 — 05-UAT.md deferred follow-up 2026-08-08); toolbar tool buttons never highlight active tool (window actions not checkable / not in ToolsPanel QActionGroup, deferred-items.md 2026-08-08); empty-state hint advertises stale Ctrl+O binding (canvas.py:278, remapped to Open Project in 05); dialog field values at Qt default ~12px not contracted 14px Body (05-UI-REVIEW.md Pillar 3).
- Full curve editor (05-CONTEXT.md/05-DISCUSSION-LOG.md deferred idea — Levels dialog D-12 is the v1 fallback): draggable curve control for tones adjustment, replacing/upgrading the Levels dialog.
- Explicitly NOT in scope: typesetting styling toolbar (TRAN-02 → Phase 7).

**Requirements**: PROJ-04 (curves), plus tracked deferrals without REQ-IDs (fixes)
**Depends on:** Phase 5
**Plans:** 8/8 plans complete

Plans:

**Wave 1** (parallel)

- [x] 06-01-PLAN.md — Curve math core: `curve_lut` + `curves_page` (master→channel composition, T-05-07 backstop, idempotency probe) in core/image_ops.py (PROJ-04)
- [x] 06-02-PLAN.md — Canvas fixes: D-09 empty-state overlay cleared on the numpy display path + D-11 hint copy references Open Folder (Ctrl+Shift+O)
- [x] 06-03-PLAN.md — Chrome fixes: D-10 toolbar active-tool highlight (checkable window actions in the exclusive group) + D-12 dialog typography 14px Body

**Wave 2** *(blocked on 06-01)*

- [x] 06-04-PLAN.md — Curves dialog surface: CurveWidget (QPainter grid/diagonal/histogram/points) + CurvesDialog collector (presets, RGB/R/G/B channels, black/white/gamma quick rows, In/Out spins, keyboard) (PROJ-04)

**Wave 3** *(blocked on 06-03 + 06-04)*

- [x] 06-05-PLAN.md — MainWindow wiring: `action_curves`/`_on_curves` rename, `_apply_geometry_op("curves", geometry=False)` + b376f8a ordering, `_undo_op_label` curves, delete levels_dialog.py + migrate tests (PROJ-04)

**Gap-closure waves** (verification gaps CR-01/WR-01/WR-02 — run via `/gsd-execute-phase 6 --gaps-only`)

- [x] 06-06-PLAN.md — *(Wave 1)* CR-01: fresh-page Cancel no longer poisons the Show Original baseline (capture-suppressed restores + `_inpainted_qimage` gate + no-pre-baseline regression test) — PROJ-04
- [x] 06-07-PLAN.md — *(Wave 2, blocked on 06-06)* WR-01: curves undo flashes 'Undo: curves'/'Redo: curves' (single-entry `_undo_op_label_for_result` op-name override + flash assertions + scoping guard) — PROJ-04
- [x] 06-08-PLAN.md — *(Wave 3, blocked on 06-07)* WR-02: dock tool-button clicks sync dock/toolbar (window actions out of the panel's exclusive group + explicit set_active_tool sync + dock-click regression test) — PROJ-04

### Phase 7: Typesetting (TRAN-02): render translated text into the page

**Goal:** User can typeset translated text into the page with full styling controls — font selection, style, size, color, alignment, and effects — producing renderable output rather than Phase 4's translucent review overlay.

**Scope (inherited from 04-CONTEXT.md Deferred Ideas, decision 2026-08-04):**

- Font selection (per-box, per-selected-boxes, per-page) — implies multi-select (Phase 3 D-08 single-select must be lifted)
- Font style selector, font size selector, increase/decrease font size
- Font color, horizontal alignment, vertical alignment
- Effects: outer glow, outline, etc.
- Vertical text (tategaki) seam: Phase 4 `vertical` toggle is a v1 no-op; RESEARCH (04-RESEARCH.md Pitfall) flags custom vertical-text widget or `QPainter.rotate` as TRAN-02 work
- Seams to reuse: `set_translation()` (D-13), `payload.vertical` metadata, Phase 4 overlay zoom/geometry tracking (04-08/04-09), fit-in-box machinery (04-09)
- Explicitly NOT in scope: MT integration (TRAN-01 — separate v2 phase), bubble re-sizing/auto-layout (BallonsTranslator territory)

**Requirements**: TRAN-02 (currently deferred v2 line in REQUIREMENTS.md)
**Depends on:** Phase 4, Phase 5
**Plans:** 12/12 plans complete

Plans:

- [x] 07-06-PLAN.md
- [x] 07-07-PLAN.md
- [x] 07-08-PLAN.md
- [x] 07-09-PLAN.md
- [x] 07-10-PLAN.md
- [x] 07-11-PLAN.md
- [x] 07-12-PLAN.md

**Wave 1**

- [x] 07-01-PLAN.md — Tracer slice: TextStyle model + shared renderer (horizontal) + opaque canvas overlay + Export Typeset… bake (D-01/D-02/D-03/D-04/D-06/D-15)

**Wave 2** *(blocked on 07-01; parallel — no file overlap)*

- [x] 07-02-PLAN.md — Multi-select: Shift+click/Ctrl+A, grouped move/delete, one snapshot per group op, primary handles, single-box resize (D-08/D-09)
- [x] 07-03-PLAN.md — Renderer depth: tategaki vertical layout + glow/shadow effects, pixel tests (D-11/D-14)
- [x] 07-04-PLAN.md — Persistence: .mas style field + _ocr.json style block + version checkpoint (D-07, one-way decision)

**Wave 3** *(blocked on 07-02 + 07-03)*

- [x] 07-05-PLAN.md — Inspector Style section + Mixed common-value + live vertical checkbox + Size +/- actions (D-05/D-10/D-13/D-16)

### Phase 8: Masker & Selective Inpaint

**Goal:** User can grow auto-detected masks to cover letter edges the conservative CTD heatmap leaves unmasked, and selectively inpaint only the text masks inside boxes whose region is uniform enough (low std-deviation) — preserving complex artwork instead of inpainting whole boxes — with per-box visibility and override. This activates the deferred cleaning-track seams (01-UAT dilation + Phase 3 decision D-15).

**Scope (inherited deferrals):**

- MASK-01 mask dilation: `phases/01-cleaning-workspace/01-UAT.md` deferred follow-up — "the CTD heatmap boundary is conservative and leaves the edges of letters unmasked... a small morphological dilation post-processing step (cv2.dilate or a configurable radius in TorchCTDModel.postprocess)." A detection-time configurable radius that grows auto-detected masks so letter edges get covered; surfaced as a cleaning-profile parameter.
- MASK-02 / MASK-03 selective per-box inpaint: Phase 3 decision D-15 (`phases/03-text-box-detection-interaction/03-CONTEXT.md`, `03-RESEARCH.md`). Goal: inpaint ONLY the detected masks inside a box when the box's std deviation is low enough (uniform-enough region), rather than masking/inpainting the whole box. The machinery is ALREADY vendored (Phase 3 vendored `panelcleaner/masker.py` + `structures.py` per D-14) and the data-model seam is open: `PageBox.mask` and `PageBox.std_dev` currently default to `None` (the D-15 seam). Functions to use: `border_std_deviation(base_image, mask_1bit, off_white_threshold, allow_color) -> (std_dev, median_color)` and `pick_best_mask(...)` in `panelcleaner/image_ops.py`. MASK-03 adds per-box visibility (an indicator showing which boxes are selectively inpainted) and override (force inpaint / skip).
- MASK-05 box-constrained inpainting: like PanelCleaner, only mask content inside text boxes is inpainted — the clean path intersects the mask with box interiors. Exact behavior of out-of-box mask content on the existing whole-page inpaint path (ignored vs. still inpainted via legacy Inpaint action) is a discuss-phase decision.
- MASK-06 tool behavior: when a paint tool is active, text boxes do not block painting — the brush can paint mask under box items. Phase 3 D-07 ("boxes always interactive, no new tool mode") gains a paint-tool carve-out; the exact select-vs-paint event dispatch (e.g. boxes pass-through while a paint tool is checked) is a discuss-phase decision.
- Reused seams: cleaning/inpaint foundation (Phase 1), box model + masker vendoring (Phase 3), OCR box context (Phase 4), `.mas` persistence (Phase 5).
- Explicitly NOT in scope: interactive mask grow/shrink brush (MASK-04 — v2), per-region LaMa params (FLOW-07 — v2).

**Requirements:** MASK-01, MASK-02, MASK-03, MASK-05, MASK-06
**Depends on:** Phase 1, Phase 3, Phase 4
**Success Criteria** (what must be TRUE):

  1. User can set a mask dilation radius (N pixels) that grows auto-detected text masks so letter edges the conservative CTD heatmap leaves unmasked get covered
  2. User can run selective per-box inpainting that inpaints only the detected text masks inside boxes — box-constrained (nothing outside a text box is inpainted, matching PanelCleaner) and std-deviation-gated (only in uniform-enough box regions), preserving complex artwork instead of inpainting whole box regions
  3. User can see, per box, whether it was selectively inpainted (indicator) and override the auto decision — force inpaint the whole box, or skip inpainting it
  4. User can paint mask under text boxes — when a paint tool is active, box items do not block brush strokes in box-overlapped regions
  5. The Phase 3 D-15 seam (`PageBox.mask` / `PageBox.std_dev`) is populated by the vendored `masker.py` machinery and round-trips through `.mas` project save/load

**Plans:** 8/9 plans executed

- [x] 08-01-PLAN.md
- [x] 08-02-PLAN.md
- [x] 08-03-PLAN.md
- [x] 08-04-PLAN.md
- [x] 08-05-PLAN.md
- [x] 08-06-PLAN.md
- [x] 08-07-PLAN.md
- [x] 08-08-PLAN.md
- [ ] 08-09-PLAN.md

**UI hint**: yes

### Phase 9: UI Rework

**Goal:** User works in a reorganized editor — a modular side panel of discrete independently-collapsible sections, a relocated right-side tools toolbar, a renamed "Typesetting" section, and a new "Edit" section consolidating the image-editing tools — replacing the monolithic panel and scattered menu/dialog access without removing any existing functionality. This activates the deferred 06-UAT sidebar revamp.

**Scope (inherited deferral):**

- Activates `phases/06-refinement-polish-deferred-fixes-full-curve-editor/06-UAT.md`: "Consider adding Curves (and possibly other tools) to the sidebar — user plans a later phase to revamp the sidebar a bit."
- UI-01 modular side panel: discrete, independently collapsible sections (Typesetting, Edit, etc.) rather than one monolithic panel.
- UI-02 inspector toggle button moved to the top of the side panel.
- UI-03 tools toolbar relocated from beside the file explorer to a small vertical toolbar on the right side of the canvas.
- UI-04 the former "Inspector" panel section is renamed to "Typesetting".
- UI-05 a new "Edit" panel section houses curves, crop, rotate, resize, levels — the image ops already delivered in Phases 5/6, reorganized into a panel section rather than scattered across menus/dialogs.
- Internal PySide6 refactor touching `gui/main_window.py`, `gui/tools_panel.py`, the `gui/inspector` panel (Phases 4/7), and the canvas toolbar wiring (Phase 6 D-10 checkable-actions group). It does NOT remove existing functionality.
- Explicitly NOT in scope: new image-edit operations (the ops already exist from Phases 5/6 — this only reorganizes their entry points), MT integration (TRAN-01 — v2).

**Requirements:** UI-01, UI-02, UI-03, UI-04, UI-05
**Depends on:** Phase 8 (the user explicitly sequenced the masker first, so the new masker affordances land in the final reworked layout)
**Success Criteria** (what must be TRUE):

  1. The side panel is modular — composed of discrete, independently collapsible sections (Typesetting, Edit, etc.) rather than one monolithic panel
  2. The inspector toggle button sits at the top of the side panel
  3. The tools toolbar is a small vertical toolbar on the right side of the canvas, relocated from beside the file explorer
  4. The former "Inspector" panel section is labeled "Typesetting"
  5. A new "Edit" panel section houses the image-editing tools (curves, crop, rotate, resize, levels) previously scattered across menus/dialogs

**Plans:** TBD
**UI hint**: yes

---
*Roadmap created: 2026-07-11; v1.2 Phases 8–9 appended: 2026-08-13*
