# Features Research

**Domain:** Manga scanlation/cleaning/OCR desktop tool
**Researched:** 2026-07-11
**Confidence:** HIGH (validated against MangaCleaner_GPU source, PanelCleaner README, competitor analysis)

## Table Stakes (must have)

These are features scanlators expect from ANY cleaning/OCR tool. Missing them means users go back to their old workflow.

| Feature | Complexity | Dependencies | Notes |
|---------|------------|--------------|-------|
| **Open/import image folder** | Low | None | Browse folder → file list sidebar. MangaCleaner_GPU `FileListWidget` already does this. |
| **Canvas with pan/zoom** | Low | Canvas foundation | QGraphicsView + wheel-to-zoom. MangaCleaner_GPU `MangaCanvas` has this. |
| **Auto text-detection (heatmap)** | Medium | ONNX text-detector model | PanelCleaner/MangaCleaner_GPU run a detector producing a binary mask of text regions. The "DETECTION SCAN [D]" button. |
| **Mask brush painting** | Low | Canvas | Brush tool with adjustable size. MangaCleaner_GPU `paint_mask_stroke`. |
| **Mask eraser** | Low | Canvas | Toggle eraser (Shift key in MangaCleaner_GPU). CompositionMode_Clear. |
| **Mask rect/lasso tools** | Low | Canvas | Rectangle and freeform lasso fill. MangaCleaner_GPU has both. |
| **LaMa inpainting (clean)** | Medium | LaMa ONNX model | Tile-based inpainting with progress. MangaCleaner_GPU `run_clean_logic`. |
| **Undo/redo (image + mask)** | Medium | History stack | Separate undo for image patches and mask states. MangaCleaner_GPU `HistoryManager` (4-stack). |
| **Export cleaned image (PNG/JPG)** | Low | None | File dialog save. MangaCleaner_GPU `on_export`. |
| **Batch process folder** | Medium | Batch engine | Process all images: detect → clean → save. MangaCleaner_GPU `BatchEngine` + `AIManager.set_persistence`. |
| **Open single page** | Low | None | Click file in list → load into canvas. MangaCleaner_GPU `on_file_clicked`. |

## Differentiators (competitive advantage)

These are what make Manga AI Studio distinct from running MangaCleaner_GPU or PanelCleaner alone. This is the project's reason to exist.

| Feature | Complexity | Dependencies | Notes |
|---------|------------|--------------|-------|
| **manga-ocr on detected/drawn boxes** | High | manga-ocr model | Run OCR *per text box* to extract recognized Japanese text — neither MangaCleaner_GPU nor PanelCleaner's heatmap detector does per-box OCR with a manga-specialized model. This is the mokuro/manga-ocr integration. |
| **Editable text boxes (move/resize/delete)** | High | Canvas box layer | Boxes are persistent objects, not just masks. User corrects detection by adding/removing/repositioning. This is the core differentiator vs. pure cleaning tools. |
| **Manual draw-to-OCR** | Medium | Canvas box tool + OCR | Draw a rectangle → manga-ocr runs on that region → creates a text box with recognized text. For boxes the auto-detector missed. |
| **Edit recognized text** | Medium | Text-box UI | Correct OCR mistakes by typing into the box. Inline text editing. |
| **Translation text layer** | Medium | Text-box data model | Second text field per box for manual translation. Clean seam for future MT. The scanlation value — this turns a cleaning tool into a translation prep tool. |
| **Mask preview overlay (toggle)** | Low | Canvas | Show/hide the mask layer before committing to inpaint. MangaCleaner_GPU has the mask as a QGraphicsPixmapItem — toggle visibility is trivial. |
| **Per-region LaMa params** | Medium | Processor + UI | Different inpainting strength/tile size for different mask regions. Goes beyond MangaCleaner_GPU's single global tile size. |
| **Project save/load (.mas)** | High | Persistence format | Save image state + masks + boxes + text + translation, resume later. Like a .psd. No reference impl — we design the format. |
| **OCR/box JSON export** | Low | Serialization | mokuro-style `_ocr.json` for downstream tools. Straightforward once box model exists. |
| **Basic image ops (crop/rotate/levels/resize)** | Medium | OpenCV | crop (numpy slice), rotate (cv2.warpAffine), levels (LUT), resize (cv2.resize). Modest effort. |
| **Dual-mode (batch + editor)** | Medium | Batch + editor integration | Batch a chapter through detect+clean+OCR, then open any page in the editor for fixes. Flipping freely. MangaCleaner_GPU has batch but no editor-returns-from-batch. |

## Anti-features (deliberately NOT build)

| Feature | Why NOT | Risk if built |
|---------|---------|---------------|
| **Full typesetting engine** (auto-fit text, vertical text rendering, font management, bubble auto-sizing) | Enormous scope; BallonsTranslator already does this. We position text in boxes; actual typesetting is out-of-app. | Months of work, derails core cleaning/OCR value. |
| **Automatic/machine translation** | PROJECT.md defers to v2. Manual translation now. | Heavy (API keys, model serving), distracts from editor quality. Build the seam, not the feature. |
| **Dewarping / panel flattening** | Niche; PanelCleaner doesn't do it either. High effort, low payoff for hobbyists. | Complex CV work for small audience gain. |
| **Upscaling (Real-ESRGAN)** | IOPaint supports it but it's a separate concern. Users can upscale before importing. | Adds model weight, UI complexity. |
| **NSFW detection / content filtering** | IOPaint has `disable_nsfw_checker`. Unnecessary for a scanlation tool. | Model weight, false positives, off-putting. |
| **Background removal / anime segmentation** | IOPaint feature. Not core to cleaning/OCR/translation. | Scope creep. |
| **Cloud sync / collaboration** | Single-user desktop app per PROJECT.md. | Massive infra, wrong product shape. |
| **Photoshop bridge** | MangaCleaner_GPU has a `PS BRIDGE`. Nice but not core; defer to v2. | Platform-specific (Windows COM), fragile. |

## Competitor Landscape

| Tool | What it does | What it Lacks (our opening) |
|------|--------------|------------------------------|
| **MangaCleaner_GPU** (local, `~/Downloads/`) | PySide6 cleaning: heatmap detection → mask paint → LaMa inpaint → batch. | No per-box OCR, no text boxes, no translation layer, no project save, no image ops. Pure cleaning. **This is our starting codebase.** |
| **PanelCleaner (pcleaner)** | PyQt5 cleaning with MangaOCR + Comic Text Detector + LaMa. Settings-rich. | No interactive mask editing beyond its built-in painter, no translation, no project save. CLI/batch oriented. **We reuse its pipeline patterns and settings.** |
| **mokuro** | Box detection + manga-ocr across a volume → `.mokuro` web overlay. | No cleaning, no inpainting, no editing of boxes (it's a batch processor), web-overlay output not an editor. **We reuse its detection approach.** |
| **BallonsTranslator** | Fully automated: detect → OCR → inpaint → translate → typeset. | Automation-focused, not editor-focused. Hard to manually fix when auto-translation fails. No mask editing. **Our differentiator: interactive editor.** |
| **manga-image-translator** | Similar automated pipeline to BallonsTranslator. | Same — automation, not editing. Server-based. |
| **Poricom** (local) | Tesseract-based manga OCR viewer. | Tesseract (poor on manga), viewer not editor, no cleaning. **UI reference only.** |
| **IOPaint** (local) | LaMa + SAM2 inpainting server with web UI. | No OCR, no text boxes, web-based, general-purpose not manga-specific. **Architecture reference for inpainting + segmentation.** |

**The gap Manga AI Studio fills:** No existing tool combines *interactive mask editing* + *per-box manga-ocr with manual correction* + *translation text layer* + *project save/resume* in a single desktop editor. Cleaning tools don't do text; OCR tools don't do cleaning; automation tools don't let you fix things by hand. We sit in the middle.

## Feature Dependencies (build order signal)

```
Canvas foundation (pan/zoom/image-load)
  ├── Mask painting tools (brush/erase/rect/lasso)
  │     ├── Mask preview overlay
  │     └── LaMa inpainting (clean)
  │           ├── Undo/redo (image)
  │           └── Per-region params
  ├── Text-box layer (objects, not pixels)
  │     ├── Box detection → auto-create boxes
  │     ├── Box move/resize/delete
  │     ├── Draw-to-OCR (manual box → manga-ocr)
  │     ├── Edit recognized text
  │     └── Translation text layer
  ├── Project persistence (.mas) — needs BOTH mask + box state
  ├── Export (PNG / JSON)
  └── Batch orchestrator — needs clean + detect + OCR working
```

The canvas is the root. Mask editing and text-box editing are parallel branches off it. Persistence and batch come last because they depend on the data models being stable.

---
*Features research for: manga scanlation desktop application*
*Researched: 2026-07-11*
