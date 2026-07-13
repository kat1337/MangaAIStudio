# Requirements: Manga AI Studio

**Defined:** 2026-07-11
**Core Value:** One app where a scanlator can clean pages, fix inpainting masks, run/correct OCR, and lay out translation text — instead of switching between PanelCleaner, mokuro, and an image editor.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Cleaning

- [x] **CLEAN-01**: User can open a single image or a folder of images and view them on a pannable, zoomable canvas
- [x] **CLEAN-02**: User can run heatmap text detection on a page to auto-generate a mask of text regions
- [ ] **CLEAN-03**: User can paint a mask freehand with a brush tool (adjustable brush size)
- [ ] **CLEAN-04**: User can paint a mask with rectangle and lasso fill tools
- [ ] **CLEAN-05**: User can erase parts of the mask (eraser toggle)
- [ ] **CLEAN-06**: User can run LaMa inpainting on the mask to remove text and restore the underlying artwork

### Text/OCR

- [ ] **TEXT-01**: User can run text-box detection across a page to create editable text-box objects (not a pixel mask)
- [ ] **TEXT-02**: User can draw a rectangle on the page and run manga-ocr on just that region to create a box with recognized text (for boxes the auto-detector missed)
- [ ] **TEXT-03**: User can select, move, resize, and delete text boxes on the canvas to correct detection errors
- [ ] **TEXT-04**: User can edit the recognized OCR text inline in a box to correct recognition mistakes
- [ ] **TEXT-05**: User can add a manual translation as a second text field per box (clean seam for future machine translation)

### Project/Export

- [ ] **PROJ-01**: User can save the full page state (image, masks, boxes, text, translation) as a `.mas` project file and reopen it to resume work
- [ ] **PROJ-02**: User can export the cleaned (text-removed, inpainted) page as PNG or JPG
- [ ] **PROJ-03**: User can export OCR/box data as a mokuro-style `_ocr.json` file per page for use in downstream tools
- [ ] **PROJ-04**: User can apply basic image operations to a page: crop, rotate, levels/curves adjustment, resize

### Workflow

- [x] **FLOW-01**: User can import a folder of images and navigate between pages via a file-list sidebar (following the PanelCleaner/Poricom sidebar layout approach)
- [ ] **FLOW-02**: User can undo/redo image (inpainting) and mask (painting) operations via separate stacks, each with redo
- [ ] **FLOW-03**: User can batch-process a chapter folder through the cleaning pipeline (detect → clean → save) with a progress indicator

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Batch & Workflow

- **FLOW-04**: User can batch-process a chapter through the full pipeline (detect → clean → box-detect → OCR → save) in one run
- **FLOW-05**: User can open any page from batch results in the editor to fix masks/boxes/text, then return to batch (batch→editor navigation)
- **FLOW-06**: User can toggle the mask overlay on/off to preview what will be inpainted before committing
- **FLOW-07**: User can set different LaMa inpainting strength or tile size per mask region, not just one global setting

### Translation

- **TRAN-01**: User can connect a machine translation service/API to pre-fill translation fields for manual correction
- **TRAN-02**: User can render translated text into the page (basic typesetting: font, size, color)

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
| CLEAN-03 | Phase 1 | Pending |
| CLEAN-04 | Phase 1 | Pending |
| CLEAN-05 | Phase 1 | Pending |
| CLEAN-06 | Phase 1 | Pending |
| TEXT-01 | Phase 3 | Pending |
| TEXT-02 | Phase 4 | Pending |
| TEXT-03 | Phase 3 | Pending |
| TEXT-04 | Phase 4 | Pending |
| TEXT-05 | Phase 4 | Pending |
| PROJ-01 | Phase 5 | Pending |
| PROJ-02 | Phase 2 | Pending |
| PROJ-03 | Phase 5 | Pending |
| PROJ-04 | Phase 5 | Pending |
| FLOW-01 | Phase 1 | Complete |
| FLOW-02 | Phase 1 | Pending |
| FLOW-03 | Phase 2 | Pending |

**Coverage:**

- v1 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0 ✓

---
*Requirements defined: 2026-07-11*
*Last updated: 2026-07-11 after roadmap creation (traceability assigned)*
