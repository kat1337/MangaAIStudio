# Manga AI Studio

## What This Is

A PyQt/PySide desktop application for manga scanlators and preservationists that unifies three pipelines — page cleaning (PanelCleaner mask detection + LaMa inpainting), manga OCR (MangaOCR with auto-detect and manual draw-to-OCR), and a lightweight canvas editor — into a single workspace. Users can clean pages, hand-fix masks, run and correct OCR, and lay out translated text without juggling separate tools. Code is imported and adapted from existing open-source tools (PanelCleaner, mokuro, manga-ocr), falling back to isolated pyenvs only where Python-version or dependency conflicts make a single environment infeasible.

## Core Value

One app where a scanlator can clean pages, fix inpainting masks, run/correct OCR, and lay out translation text — instead of switching between PanelCleaner, mokuro, and an image editor.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Clean manga pages: run PanelCleaner's mask detection + LaMa inpainting to remove text and restore artwork
- [ ] Edit masks: brush paint/erase masks, fix auto-detect errors (missed sfx, false positives), set per-region LaMa params, preview mask overlay before committing
- [ ] Detect text boxes: run mokuro-style detection across a page, then add/remove/move boxes to correct it
- [ ] Manual OCR: draw a rectangle on the page and run MangaOCR on just that region to fill a box the detector missed
- [ ] Edit recognized text: correct OCR mistakes by typing into the box
- [ ] Translation layer: add a manual translation as a second text layer per box (clean seam for future MT integration)
- [ ] Dual-mode workflow: batch-process a whole chapter (clean + OCR), then open individual pages for per-page fixes, flipping freely
- [ ] Basic image operations: crop, rotate, levels/curves, resize
- [ ] Export cleaned raws as PNG/JPG
- [ ] Save/load projects as `.mas` files (boxes, masks, text, image state — resumable like a .psd)
- [ ] Export OCR/box JSON (mokuro-style `_ocr.json`) alongside pages for downstream tools

### Out of Scope

- Full-featured image editor (Photoshop-class retouching, layers, filters) — Manga AI Studio is an editor for masks + text + basic ops, not a paint program beyond mask editing
- Automatic / machine translation in v1 — manual translation only; MT is a v2 seam, not built now
- Cloud sync / collaboration — single-user desktop app
- Mobile app — desktop only
- Re-OCR of an existing mokuro `_ocr.json` without image reprocessing — out of v1, can be revisited
- Typesetting engine (auto-fit, vertical text, font management, bubble auto-sizing) — text is positioned in boxes; advanced typesetting is v2+

## Context

**Source tools to reuse (all open source):**

- **PanelCleaner (pcleaner)** — https://github.com/VoxelCubes/PanelCleaner — the foundation for the cleaning pipeline. Reuse its settings/parameters as-is, the mask auto-detection, the paint-like masking canvas, and the LaMa inpainting model integration. The masking canvas UI is the direct ancestor of this app's mask editor.
- **mokuro** — https://github.com/kha-white/mokuro — provides the text-box detection model and pipeline architecture. We adopt the box-detection approach but replace its OCR with MangaOCR.
- **manga-ocr** — the OCR model (mokuro uses it; we use it directly) for recognizing Japanese text in detected/drawn boxes.

**Repository layout:** PanelCleaner to be cloned to `../PanelCleaner` (sibling of this project) for reference and code reuse.

**Integration strategy:** Import and adapt the relevant source (LaMa pipeline, masking canvas, manga-ocr model) into one codebase where dependencies coexist. Fall back to isolated pyenv environments only when a tool requires an incompatible Python version or has hard dependency conflicts — prefer a single environment to minimize code rewriting.

**Environment:** Developer is on Windows (win32, Git Bash). Python ecosystem is the common ground (PanelCleaner is PyQt5, mokuro and manga-ocr are PyTorch-based).

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
| PyQt/PySide desktop over web UI | Reuses PanelCleaner's Qt patterns directly; best fit for a canvas-based image editor; avoids browser canvas performance concerns | — Pending |
| Import & adapt code, not subprocess orchestration | Minimizes rewriting; single environment is simpler than managing multiple isolated runtimes for a small hobbyist app | — Pending |
| Isolated pyenvs only on hard conflicts | Fallback for Python-version or dependency conflicts that can't be resolved in one env; default is one env | — Pending |
| Manual translation now, MT seam later | v1 ships manual entry; design the text layer so MT can be plugged in without rework | — Pending |
| Replace mokuro's OCR with MangaOCR | MangaOCR is purpose-built for manga and more accurate; keep mokuro's box detection | — Pending |
| Windows-first, Linux-portable | Developer environment is Windows; cross-platform Python stack makes Linux feasible later without redesign | — Pending |

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
*Last updated: 2026-07-11 after initialization*
