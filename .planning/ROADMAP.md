# Roadmap: Manga AI Studio

## Overview

Manga AI Studio unifies manga page cleaning, mask editing, text-box OCR, and translation layout into one PySide6 desktop app. The journey starts by adapting PanelCleaner (GPL v3) as the foundation with a model adapter interface, reaching cleaning parity immediately, then builds the novel differentiator — editable text boxes with per-box manga-ocr and a translation layer — and finally lands the project system (save/resume, image ops, JSON export) that turns the editor into a resumable workspace. Each phase is a vertical slice delivering one complete, user-observable capability.

**Mode:** mvp
**Granularity:** standard (5 phases)
**Coverage:** 18/18 v1 requirements mapped ✓

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Cleaning Workspace** - Open/navigate pages, detect masks, edit masks, run LaMa inpainting, undo/redo (PanelCleaner + MangaCleaner_GPU foundation) (completed 2026-07-21)
- [ ] **Phase 2: Cleaning Output & Batch** - Export cleaned pages as PNG/JPG and batch-process a chapter through cleaning
- [ ] **Phase 3: Text Box Detection & Interaction** - Detect text boxes as editable objects and select/move/resize/delete them
- [ ] **Phase 4: OCR Recognition & Text Editing** - Draw-to-OCR regions, correct recognized text, add manual translations
- [ ] **Phase 5: Project Persistence, Image Ops & Export** - Save/resume .mas projects, basic image operations, export _ocr.json

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

**Plans**: TBD

Plans:

- [ ] TBD (defined during `/gsd:plan-phase 3`)

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

**Plans**: TBD

Plans:

- [ ] TBD (defined during `/gsd:plan-phase 4`)

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

**Plans**: TBD

Plans:

- [ ] TBD (defined during `/gsd:plan-phase 5`)

**UI hint**: yes

## Notes & Out-of-Band Concerns

- **Packaging / distribution** (PyInstaller + PySide6 + onnxruntime, model weight distribution ~600MB, Windows AV false positives) is emphasized by research as real work but has **no v1 requirement ID**. It is not a requirement-driven phase here. Recommend inserting it as a decimal phase (e.g., `Phase 5.1`) or a v1.1 milestone once a packaging requirement is formalized. Pitfalls P3, P15, P16, P17 capture the risks.
- **Environment validation** (torch + onnxruntime + numpy<2 coexistence, CUDA→CPU fallback) is a Phase 1 day-one gate (pitfalls P1, P2).
- **Latent QImage buffer bug** in MangaCleaner_GPU's `on_task_finished` must be fixed when lifting canvas code in Phase 1 (pitfall P5).

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Cleaning Workspace | 7/7 | Complete    | 2026-07-23 |
| 2. Cleaning Output & Batch | 4/4 | In Progress|  |
| 3. Text Box Detection & Interaction | 0/TBD | Not started | - |
| 4. OCR Recognition & Text Editing | 0/TBD | Not started | - |
| 5. Project Persistence, Image Ops & Export | 0/TBD | Not started | - |

---
*Roadmap created: 2026-07-11*
