# Project Research Summary

**Project:** Manga AI Studio
**Researched:** 2026-07-11
**Method:** Inline research (MCP research subagents unavailable — used WebSearch + direct source code inspection of locally-downloaded tools)

## Key Findings

### Stack: Decided, not open
The stack question is largely answered by a local asset: **MangaCleaner_GPU** (`~/Downloads/MangaCleaner_GPU/_internal/src/`) is a working PySide6 + ONNX Runtime + OpenCV manga cleaning app. It runs LaMa inpainting and text detection through ONNX models — **no PyTorch required** for the cleaning pipeline. We adopt its stack wholesale (PySide6, onnxruntime, opencv-python, numpy<2, Python 3.12) and extend it. The only remaining stack question is whether manga-ocr requires torch (transformers pipeline) or can run on ONNX (an export exists at `l0wgear/manga-ocr-2025-onnx`); validate in Phase 1.

### Table Stakes (reuse from MangaCleaner_GPU): cleaning works today
Folder import, canvas with pan/zoom, heatmap text detection → mask, brush/rect/lasso mask painting, eraser, LaMa tile inpainting, 4-stack undo/redo, batch processing, PNG/JPG export — all already implemented in MangaCleaner_GPU's ~600 lines of Python. Phase 1 is "lift and adapt," not "build from scratch."

### The differentiator: text boxes + manga-ocr + translation
What no existing tool does well: treat detected text as **editable box objects** with per-box manga-ocr recognition, manual text correction, and a translation layer. This is where Manga AI Studio adds value. It requires a new `TextBox` data model, box graphics items on the canvas, a box-detection pipeline (adapted from mokuro/PanelCleaner's Comic Text Detector), and manga-ocr integration (per-crop recognition).

### Competitor gap: interactive editor
BallonsTranslator and manga-image-translator are automation pipelines (detect → OCR → inpaint → translate → typeset). When they get it wrong, there's no way to fix it interactively. MangaCleaner_GPU and PanelCleaner are cleaning-only. mokuro is batch OCR with web overlay output, no editing. **Manga AI Studio sits in the gap: an interactive editor for masks, boxes, text, and translation.**

## Implications for Roadmap

### Build on MangaCleaner_GPU, don't start fresh
Phase 1 should establish the project by lifting MangaCleaner_GPU's `backend/` and `frontend/` code into our repo, fixing its latent QImage buffer bug (P5), and confirming the environment (torch + onnxruntime coexistence, P1). This delivers a working cleaning app almost immediately — the foundation for everything else.

### Two parallel capability branches after foundation
After the canvas foundation, there are two largely-independent capability tracks:
1. **Mask/cleaning track** (extend MangaCleaner_GPU): per-region LaMa params, mask preview toggle, batch→editor navigation
2. **Text/OCR track** (new): box detection, box interaction, manga-ocr, text editing, translation layer

The text/OCR track is the larger and more novel effort. The mask track is incremental improvements to working code.

### Persistence and batch come late
Project save/load (.mas) needs the data models (PageState with masks + boxes) to be stable — build it after the two capability tracks. Batch orchestration (extended to include OCR + JSON export) depends on all pipelines working. These are integration phases, not foundation phases.

### Packaging is a real phase, not an afterthought
Distributing to hobbyists (the stated audience) means solving model distribution (200MB+ LaMa, 400MB manga-ocr), PyInstaller + PySide6 + onnxruntime packaging (MangaCleaner_GPU is a working template), and Windows false-positive mitigation. Budget a real phase for this.

## Risks & Unknowns (research couldn't fully resolve)

| Risk | Impact | Mitigation |
|------|--------|------------|
| torch + onnxruntime can't coexist in one env | Medium — forces subprocess architecture | Validate in Phase 1; isolated pyenv fallback is documented |
| manga-ocr ONNX export accuracy vs transformers model | Low-Medium — may need torch for acceptable quality | A/B test both; choose based on results |
| Box detector model extraction from mokuro is hard | Medium — may need to swap to YOLO | Have YOLO + Roboflow datasets as backup; mokuro is MIT so adaptation is allowed |
| MangaCleaner_GPU license unknown | Low (it's on user's machine; possibly their own work) — but affects publishing | Clarify origin before any public release |
| PanelCleaner GPL v3 limits our licensing | Low — we adapt logic, not copy code | Confirm in Phase 1; likely fine if we open-source too |

## Sources

- **Local (primary):** `~/Downloads/MangaCleaner_GPU/_internal/src/` — all backend/frontend/utils Python files read. The foundational architecture reference.
- **Local:** `~/Downloads/MangaCleaner_GPU/models/` — ONNX model inventory (lama.onnx, ocr.onnx).
- **Local:** `~/Downloads/IOPaint-v1.1/installer_config.json` — LaMa + SAM2 config patterns.
- **Local:** `~/Downloads/Poricom-v1.2.0-offline/` — tesserocr-based viewer (UI reference).
- **Web:** https://github.com/kha-white/manga-ocr — MangaOcr API, transformers pipeline.
- **Web:** https://huggingface.co/l0wgear/manga-ocr-2025-onnx — ONNX manga-ocr export exists.
- **Web:** https://github.com/VoxelCubes/PanelCleaner — PyQt5 cleaning tool, GPL v3, uses LaMa + Comic Text Detector + MangaOCR.
- **Web:** https://github.com/dmMaze/BallonsTranslator — automated translation competitor.
- **Web:** https://github.com/zyddnys/manga-image-translator — automated translation competitor.
- **Web:** https://pypi.org/project/mokuro/ — box detection + OCR pipeline (MIT).

---
*Research summary for: Manga AI Studio*
*Researched: 2026-07-11*
