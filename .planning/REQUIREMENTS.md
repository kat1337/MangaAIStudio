# Requirements: Manga AI Studio

**Defined:** 2026-07-11
**Core Value:** One app where a scanlator can clean pages, fix inpainting masks, run/correct OCR, and lay out translation text — instead of switching between PanelCleaner, mokuro, and an image editor.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Cleaning

- [x] **CLEAN-01**: User can open a single image or a folder of images and view them on a pannable, zoomable canvas
- [x] **CLEAN-02**: User can run heatmap text detection on a page to auto-generate a mask of text regions
- [x] **CLEAN-03**: User can paint a mask freehand with a brush tool (adjustable brush size)
- [x] **CLEAN-04**: User can paint a mask with rectangle and lasso fill tools
- [x] **CLEAN-05**: User can erase parts of the mask (eraser toggle)
- [x] **CLEAN-06**: User can run LaMa inpainting on the mask to remove text and restore the underlying artwork

### Text/OCR

- [x] **TEXT-01**: User can run text-box detection across a page to create editable text-box objects (not a pixel mask)
- [x] **TEXT-02**: User can draw a rectangle on the page and run manga-ocr on just that region to create a box with recognized text (for boxes the auto-detector missed)
- [x] **TEXT-03**: User can select, move, resize, and delete text boxes on the canvas to correct detection errors
- [x] **TEXT-04**: User can edit the recognized OCR text inline in a box to correct recognition mistakes
- [x] **TEXT-05**: User can add a manual translation as a second text field per box (clean seam for future machine translation)

### Project/Export

- [x] **PROJ-01**: User can save the full page state (image, masks, boxes, text, translation) as a `.mas` project file and reopen it to resume work
- [x] **PROJ-02**: User can export the cleaned (text-removed, inpainted) page as PNG or JPG
- [x] **PROJ-03**: User can export OCR/box data as a mokuro-style `_ocr.json` file per page for use in downstream tools
- [x] **PROJ-04**: User can apply basic image operations to a page: crop, rotate, levels/curves adjustment, resize

### Workflow

- [x] **FLOW-01**: User can import a folder of images and navigate between pages via a file-list sidebar (following the PanelCleaner/Poricom sidebar layout approach)
- [x] **FLOW-02**: User can undo/redo image (inpainting) and mask (painting) operations via separate stacks, each with redo
- [x] **FLOW-03**: User can batch-process a chapter folder through the cleaning pipeline (detect → clean → save) with a progress indicator

## v1.2 Requirements

Requirements for milestone v1.2 (Masker & Selective Inpaint + UI Rework). Each maps to a roadmap phase. Activates deferred cleaning-track seams documented in earlier phases (`01-UAT.md` dilation, Phase 3 decision D-15 selective per-box inpaint) and the deferred `06-UAT.md` sidebar revamp.

### Masker & Selective Inpaint

- [ ] **MASK-01**: User can set a mask dilation radius so auto-detected text masks are grown by N pixels, covering letter edges the conservative CTD heatmap leaves unmasked
- [ ] **MASK-02**: User can run selective per-box inpainting that inpaints only the detected text masks *inside* boxes whose region is uniform enough (low std-deviation), preserving complex artwork regions instead of inpainting whole box regions (activates the Phase 3 D-15 seam — `PageBox.mask`/`std_dev` fields filled via the vendored `masker.py` machinery)
- [ ] **MASK-03**: User can see per-box whether it was selectively inpainted (indicator) and override the auto-decision (force inpaint / skip)

### UI Rework

- [ ] **UI-01**: The side panel is modular — composed of discrete, independently collapsible sections (Typesetting, Edit, etc.) rather than one monolithic panel
- [ ] **UI-02**: The inspector toggle button is moved to the top of the side panel
- [ ] **UI-03**: The tools toolbar is relocated from beside the file explorer to a small vertical toolbar on the right side of the canvas
- [ ] **UI-04**: The former "Inspector" panel section is renamed to "Typesetting"
- [ ] **UI-05**: A new "Edit" panel section houses the image-editing tools (curves, crop, rotate, resize, levels) currently scattered across menus/dialogs

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Batch & Workflow

- **FLOW-04**: User can batch-process a chapter through the full pipeline (detect → clean → box-detect → OCR → save) in one run
- **FLOW-05**: User can open any page from batch results in the editor to fix masks/boxes/text, then return to batch (batch→editor navigation)
- **FLOW-06**: User can toggle the mask overlay on/off to preview what will be inpainted before committing
- **FLOW-07**: User can set different LaMa inpainting strength or tile size per mask region, not just one global setting

### Translation

- **TRAN-01**: User can connect a machine translation service/API to pre-fill translation fields for manual correction

<!-- TRAN-02 (render translated text into the page) was delivered in Phase 7 — moved to validated. -->

### Masker

- **MASK-04**: User can manually grow/shrink a painted or auto-detected mask region interactively on the canvas (a mask-editing brush variant), complementing the detection-time dilation slider (MASK-01)

### Integrations

- **INTG-01**: User can send cleaned pages to Photoshop via a bridge (from MangaCleaner_GPU's PS Bridge)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Full typesetting engine (auto-fit, vertical text rendering, font management, bubble auto-sizing) | Enormous scope; BallonsTranslator covers this. We position text in boxes; actual typesetting is out-of-app or v2+. |
| Automatic / machine translation in v1 | Manual translation now; MT is a v2 seam. Build the seam, not the feature. |
| Dewarping / panel flattening | Niche; PanelCleaner doesn't do it. High effort, low payoff for hobbyists. |
| Upscaling (Real-ESRGAN) | Separate concern; users can upscale before importing. IOPaint supports it standalone. |
| NSFW detection / content filtering | Unnecessary for a scanlation tool; adds model weight and false positives. |
| Background removal / anime segmentation | IOPaint feature; not core to cleaning/OCR/translation. |
| Cloud sync / collaboration | Single-user desktop app. |
| Mobile app | Desktop only. |
| Full-featured image editor (layers, filters, advanced retouching) | Editor is for masks + text + basic ops, not a Photoshop replacement. |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CLEAN-01 | Phase 1 | Complete |
| CLEAN-02 | Phase 1 | Complete |
| CLEAN-03 | Phase 1 | Complete |
| CLEAN-04 | Phase 1 | Complete |
| CLEAN-05 | Phase 1 | Complete |
| CLEAN-06 | Phase 1 | Complete |
| TEXT-01 | Phase 3 | Complete |
| TEXT-02 | Phase 4 | Complete |
| TEXT-03 | Phase 3 | Complete |
| TEXT-04 | Phase 4 | Complete |
| TEXT-05 | Phase 4 | Complete |
| PROJ-01 | Phase 5 | Complete |
| PROJ-02 | Phase 2 | Complete |
| PROJ-03 | Phase 5 | Complete |
| PROJ-04 | Phase 5 | Complete |
| FLOW-01 | Phase 1 | Complete |
| FLOW-02 | Phase 1 | Complete |
| FLOW-03 | Phase 2 | Complete |
| MASK-01 | Phase 8 | Pending |
| MASK-02 | Phase 8 | Pending |
| MASK-03 | Phase 8 | Pending |
| UI-01 | Phase 9 | Pending |
| UI-02 | Phase 9 | Pending |
| UI-03 | Phase 9 | Pending |
| UI-04 | Phase 9 | Pending |
| UI-05 | Phase 9 | Pending |

**Coverage:**

- v1 requirements: 18 total — 18 mapped, 0 unmapped ✓
- v1.2 requirements: 8 total — 8 mapped (Phase 8–9), 0 unmapped ✓

---
*Requirements defined: 2026-07-11*
*Last updated: 2026-08-13 after milestone v1.2 requirement definition*
