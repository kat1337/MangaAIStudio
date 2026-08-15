# Manga AI Studio

## What This Is

A PyQt/PySide desktop application for manga scanlators and preservationists that unifies three pipelines — page cleaning (PanelCleaner mask detection + LaMa inpainting), manga OCR (MangaOCR with auto-detect and manual draw-to-OCR), and a lightweight canvas editor — into a single workspace. Users can clean pages, hand-fix masks, run and correct OCR, and lay out translated text without juggling separate tools. Code is imported and adapted from existing open-source tools (PanelCleaner, mokuro, manga-ocr), falling back to isolated pyenvs only where Python-version or dependency conflicts make a single environment infeasible.

## Core Value

One app where a scanlator can clean pages, fix inpainting masks, run/correct OCR, and lay out translation text — instead of switching between PanelCleaner, mokuro, and an image editor.

## Current Milestone: v1.2 Masker & Selective Inpaint + UI Rework

**Goal:** Activate the deferred cleaning-track features (mask dilation + the Phase 3 D-15 std-deviation selective per-box inpaint seam + box-constrained inpainting + tool-behavior fixes), then rework the editor's panel/toolbar layout into a modular structure with a dedicated image-edit section.

**Target features:**
- Mask dilation: configurable detection-time radius so detected masks cover letter edges the conservative heatmap misses (`01-UAT.md` deferral)
- Std-deviation selective per-box inpaint (D-15): inpaint only inside boxes whose region is uniform enough, with per-box visibility/override — activates the Phase 3 `PageBox.mask`/`std_dev` seam via the vendored `masker.py` machinery
- Box-constrained inpainting (PanelCleaner model): only mask content inside text boxes is inpainted
- Tool behavior: paint tools (brush) can paint mask under text boxes — box items don't block strokes
- UI rework: modular side panel, inspector button moved to top, right-side toolbar, "Inspector"→"Typesetting" rename, new "Edit" section (curves, crop, image-edit tools) (`06-UAT.md` deferral)

## Requirements

### Validated

- [x] Clean manga pages: run PanelCleaner's mask detection + LaMa inpainting to remove text and restore artwork — *Validated in Phase 1: Cleaning Workspace*
- [x] Edit masks: brush paint/erase masks, fix auto-detect errors (missed sfx, false positives), set per-region LaMa params, preview mask overlay before committing — *Validated in Phase 1: Cleaning Workspace*
- [x] Export cleaned raws as PNG/JPG — *Validated in Phase 2: Cleaning Output & Batch (single-page Export via Ctrl+E)*
- [x] Dual-mode workflow: batch-process a whole chapter (clean + OCR), then open individual pages for per-page fixes, flipping freely — *Cleaning half validated in Phase 2 (Batch Detect / Batch Clean / Batch Detect+Clean + per-page mask persistence); OCR half pending later phases*
- [x] Basic image operations: crop, rotate, levels/curves, resize — *Validated in Phase 5 (crop/rotate/levels/resize) + Phase 6 (full curve editor replacing the Levels dialog, PROJ-04)*
- [x] Typeset translated text into the page with full styling controls (font selection incl. machine fonts, style, size + auto-fit, color, alignment, effects: outline/glow/shadow, vertical tategaki text, default font) with bake-to-image export — *Validated in Phase 7: Typesetting (TRAN-02)*
- [x] Detect text boxes as editable objects and select/move/resize/delete them — *Validated in Phase 3: Text Box Detection (TEXT-01, TEXT-03)*
- [x] Manual draw-to-OCR, edit recognized text inline, manual translation layer per box — *Validated in Phase 4: OCR Recognition & Text Editing (TEXT-02, TEXT-04, TEXT-05)*
- [x] Save/load projects as `.mas` files (boxes, masks, text, image state — resumable like a .psd) — *Validated in Phase 5: Project Persistence (PROJ-01)*
- [x] Export OCR/box JSON (mokuro-style `_ocr.json`) alongside pages for downstream tools — *Validated in Phase 5 (PROJ-03)*

### Active

<!-- v1.2 scope. Activating deferred cleaning-track features + UI rework. -->

- [ ] Mask dilation: configurable detection-time radius so detected masks cover letter edges the conservative CTD heatmap misses
- [ ] Std-deviation selective per-box inpaint (D-15): inpaint only inside boxes whose region is uniform enough, with per-box visibility and override — activates the Phase 3 `PageBox.mask`/`std_dev` seam
- [ ] Box-constrained inpainting: only mask content inside text boxes is inpainted (PanelCleaner's box-driven cleaning model)
- [ ] Paint tools can paint mask under text boxes (box items don't block brush strokes)
- [ ] UI rework: modular side panel, inspector button moved to top, right-side toolbar, "Inspector"→"Typesetting" rename, new "Edit" section (curves, crop, image-edit tools)

### Out of Scope

- Full-featured image editor (Photoshop-class retouching, layers, filters) — Manga AI Studio is an editor for masks + text + basic ops, not a paint program beyond mask editing
- Automatic / machine translation in v1 — manual translation only; MT is a v2 seam, not built now
- Cloud sync / collaboration — single-user desktop app
- Mobile app — desktop only
- Re-OCR of an existing mokuro `_ocr.json` without image reprocessing — out of v1, can be revisited
- Advanced typesetting beyond Phase 7's delivery (bubble auto-sizing / auto-layout, font management / bundled fonts, kumimoji-depth vertical typography, per-line styling, MT integration) — text is positioned in boxes and basic typesetting is delivered (Phase 7); the rest is v2+

## Context

**Primary codebase: PanelCleaner (GPL v3)**

**Source architecture:** https://github.com/VoxelCubes/PanelCleaner — cloned to `../PanelCleaner` (sibling directory). This is our primary foundation, not MangaCleaner_GPU. PanelCleaner's GPL v3 license ensures the tool remains open source for the scanlation community.

**What we lift from PanelCleaner:**
- **GUI framework**: PySide6 (`pcleaner/gui/` — verified in PanelCleaner `requirements.txt`, not PyQt5) — main window, image viewer, file table, profile system
- **Config system**: Profile-based settings (`pcleaner/config.py`) — uses **ConfigUpdater (INI)** persistence, not JSON. Supports PanelCleaner config compatibility.
- **Text detection**: Comic Text Detector (`pcleaner/comic_text_detector/`) — PyTorch-based heatmap detection
- **OCR integration**: manga-ocr wrapper (`pcleaner/ocr/ocr_mangaocr.py`) — recognition engine
- **Inpainting**: LaMa via `simple_lama_inpainting` package (`pcleaner/inpainting.py`)
- **Image operations**: crop, rotate, levels (`pcleaner/image_ops.py`)
- **Mask processing**: mask refinement and box handling (`pcleaner/masker.py`)

**Model adapter interface (modularity):**
- Design abstracted interfaces for: detection, OCR, inpainting models
- PanelCleaner's models (CTD, manga-ocr, LaMa) are the default v1 implementation
- MangaCleaner_GPU's ONNX models can be optional add-on modules later (user-installed)
- This allows advanced users to swap in better models without core changes

**Repository layout:**
- `../PanelCleaner` — Reference source (GPL v3)
- `C:\Src\Manga AI Studio` — Our fork/adaptation

**Integration strategy:** Import and adapt PanelCleaner's core modules, preserving the profile system and config compatibility. Fall back to isolated pyenv environments only when a tool requires an incompatible Python version — prefer a single environment.

**Environment:** Developer is on Windows (win32, Git Bash). PanelCleaner uses PySide6 + PyTorch + loguru.

**Audience:** Small group of hobbyist scanlators/preservationists. Needs to be installable by non-developers, with some documentation and tolerable UX — but not the packaging/onboarding investment of a broad public release.

## Constraints

- **Tech stack**: PyQt/PySide desktop GUI, Python backend — reuses PanelCleaner's Qt patterns directly. This is non-negotiable; it's the foundation for the canvas editor.
- **Platform**: Windows-first for v1. Architectural choices must not block Linux later — most of the Python stack is cross-platform given the right deps; avoid Windows-only APIs and hard-coded paths.
- **Dependencies**: PanelCleaner, mokuro, manga-ocr, LaMa, PyTorch — these have heavy and potentially conflicting dependencies. Dependency isolation (pyenv/per-tool venvs) is the fallback strategy, not the default. Single environment is preferred.
- **Compatibility**: Must reuse PanelCleaner's settings format so existing pcleaner configs carry over.
- **Python versions**: Source tools may target different Python versions — investigate during research; isolated envs are the escape hatch.
- **Models**: LaMa (inpainting) and manga-ocr (OCR) model weights are required at runtime — packaging/distribution strategy must account for large model files.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| PanelCleaner as base (GPL v3) | Better architecture, proven config system, GPL v3 keeps tool open source for scanlation community | — Active |
| PySide6 (Qt for Python) | PanelCleaner uses PySide6; LGPL licensing, actively maintained | — Active |
| Model adapter interface | Abstracted interfaces allow model swapping; PanelCleaner models default, MangaCleaner_GPU ONNX optional later | — Pending |
| Frontend/backend env split | Backend (model inference) isolated from frontend (GUI) whenever practical; ONNX backend isolated because it needs a newer Python; single-env proven fallback (PanelCleaner requirements.txt confirms PyTorch stack coexists) | — Active (rev. 2026-07-12) |
| Manual translation now, MT seam later | v1 ships manual entry; design text layer so MT can be plugged in later | — Pending |
| Windows-first, Linux-portable | Developer environment is Windows; cross-platform Python stack makes Linux feasible later | — Pending |
| GPL v3 license | PanelCleaner is GPL v3; derivative works must be GPL v3 — ensures tool stays open source | — Active |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-08-13 after milestone v1.2 start (Masker & Selective Inpaint + UI Rework)*
