<!-- GSD:project-start source:PROJECT.md -->

## Project

**Manga AI Studio**

A PyQt/PySide desktop application for manga scanlators and preservationists that unifies three pipelines — page cleaning (PanelCleaner mask detection + LaMa inpainting), manga OCR (MangaOCR with auto-detect and manual draw-to-OCR), and a lightweight canvas editor — into a single workspace. Users can clean pages, hand-fix masks, run and correct OCR, and lay out translated text without juggling separate tools. Code is imported and adapted from existing open-source tools (PanelCleaner, mokuro, manga-ocr), falling back to isolated pyenvs only where Python-version or dependency conflicts make a single environment infeasible.

**Core Value:** One app where a scanlator can clean pages, fix inpainting masks, run/correct OCR, and lay out translation text — instead of switching between PanelCleaner, mokuro, and an image editor.

### Constraints

- **Tech stack**: PyQt/PySide desktop GUI, Python backend — reuses PanelCleaner's Qt patterns directly. This is non-negotiable; it's the foundation for the canvas editor.
- **Platform**: Windows-first for v1. Architectural choices must not block Linux later — most of the Python stack is cross-platform given the right deps; avoid Windows-only APIs and hard-coded paths.
- **Dependencies**: PanelCleaner, mokuro, manga-ocr, LaMa, PyTorch — these have heavy and potentially conflicting dependencies. Dependency isolation (pyenv/per-tool venvs) is the fallback strategy, not the default. Single environment is preferred.
- **Compatibility**: Must reuse PanelCleaner's settings format so existing pcleaner configs carry over.
- **Python versions**: Source tools may target different Python versions — investigate during research; isolated envs are the escape hatch.
- **Models**: LaMa (inpainting) and manga-ocr (OCR) model weights are required at runtime — packaging/distribution strategy must account for large model files.

<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->

## Technology Stack

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Python** | 3.12 | Application runtime | MangaCleaner_GPU (our primary architecture reference) compiles to cpython-3.12; PySide6 + onnxruntime + opencv all stable on 3.12. Avoids 3.13 breakage with torch/onnx. |
| **PySide6** | 6.7+ | Qt GUI framework | **Decisive finding**: MangaCleaner_GPU (local, in `~/Downloads/MangaCleaner_GPU`) already uses PySide6 — NOT PyQt5. PanelCleaner (the GitHub project) uses PyQt5, but we are adapting its *pipeline logic*, not its GUI. PySide6 is the Qt-for-Python official binding (LGPL, more permissive than PyQt5's GPL). The canvas, QGraphicsView/QGraphicsScene mask painting, QThread worker pattern, and signal/slot architecture are all directly reusable from MangaCleaner_GPU's `frontend/canvas.py`. |
| **ONNX Runtime** | 1.17+ | ML inference engine (LaMa + OCR) | **Second decisive finding**: MangaCleaner_GPU runs BOTH LaMa inpainting AND text detection via ONNX (`models/lama.onnx` 197MB, `models/ocr.onnx` 4.6MB) — NOT PyTorch. This eliminates the heaviest dependency conflict (PyTorch). ONNX Runtime is a single wheel, CPU+CUDA providers auto-selected at runtime (see `backend/onnx_engine.py`). This is the key to a single-environment app. |
| **OpenCV (cv2)** | 4.9+ | Image I/O + processing | Used for `imread`/`imwrite`, color conversion, mask dilation, connected-components blob analysis. Already in MangaCleaner_GPU. |
| **NumPy** | 1.26+ | Array operations | Universal across all image/ML ops. Pin to <2.0 to avoid ABI breakage with onnxruntime/opencv wheels built against numpy 1.x (see Version Compatibility). |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **Pillow (PIL)** | 10+ | Image format handling | When OpenCV isn't enough (e.g., WebP metadata, some PNG modes). Optional — OpenCV covers most needs. |
| **manga-ocr** | 0.1.x | Japanese text OCR (the source tool) | **Library to adapt, not a hard dependency.** Its `MangaOcr` class wraps a HuggingFace transformers pipeline (`kha-white/manga-ocr-base`, Vision Encoder-Decoder). Two integration paths: (a) call `from manga_ocr.ocr import MangaOcr; ocr=MangaOcr(); text=ocr(img)` — requires `transformers` + `torch`, heavy; (b) use the ONNX export `l0wgear/manga-ocr-2025-onnx` and run via our existing ONNXEngine — lightweight, consistent with MangaCleaner_GPU. **Recommendation: start with path (a) for correctness, plan migration to (b) ONNX for distribution.** |
| **transformers + torch** | transformers 4.40+, torch 2.2+ | manga-ocr model runtime (path a only) | Only if using manga-ocr via transformers pipeline. Adds ~2GB to the environment. This is the one genuine "heavy dep" — candidate for isolated pyenv if it conflicts. |
| **ultralytics (YOLO)** | 8.1+ | Text-box detection model (optional mokuro alternative) | mokuro uses a custom CNN for box detection. If we want ONNX-exportable, well-maintained box detection, a YOLOv8 model trained on manga text (datasets exist on Roboflow) is the modern path. Defer unless mokuro's detector proves hard to extract. |
| **pyenv / uv** | latest | Environment isolation (fallback only) | Per PROJECT.md decision: single env preferred. Only create isolated envs if manga-ocr's torch version hard-conflicts with onnxruntime's numpy requirements. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| **uv** | Dependency + venv management | Fast (Rust-based) replacement for pip/poetry/venv. Handles pyenv-style version management too. Recommended for both dev and for the "isolated env" fallback. |
| **PyInstaller** | Windows packaging into single .exe | Exactly what MangaCleaner_GPU uses (`_internal/` + `.exe` layout). `--onedir` mode (not `--onefile`) for fast startup with large ONNX models. |
| **pytest** | Test runner | Standard. Test the processor/pipeline logic headlessly (no Qt needed for `backend/`). |

## Installation

# Create environment with uv (recommended)

# For manga-ocr via transformers (path a — heavier)

# Dev dependencies

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| **PySide6** | PyQt6 / PyQt5 | Use PyQt5 ONLY if directly vendoring PanelCleaner GUI widgets unmodified. We're adapting logic, not GUI, so PySide6 wins (LGPL licensing, matches MangaCleaner_GPU). |
| **ONNX Runtime** | PyTorch | Use PyTorch only during model development/fine-tuning. For the shipped app, ONNX is faster, smaller, and dependency-lighter. MangaCleaner_GPU proves this works for LaMa + OCR. |
| **manga-ocr (transformers)** | Tesseract / Poricom's tesserocr | Tesseract is for printed text, poor on stylized manga fonts. manga-ocr is purpose-trained. (Poricom in Downloads is a tesserocr-based viewer — useful as a UI reference, not an OCR source.) |
| **YOLOv8 (ultralytics)** | mokuro's built-in CNN detector | Use mokuro's detector if it extracts cleanly. YOLO if we need ONNX export or better-maintained model. Research in phase 1. |
| **uv** | poetry / pip+venv | uv is faster and handles Python versions. poetry is fine if already familiar. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **PyTorch in the shipped app** | 2GB+ dependency, CUDA installer headaches for hobbyists, version-fragile. | ONNX Runtime — single wheel, ~50MB, auto GPU/CPU. MangaCleaner_GPU proves LaMa+OCR run on ONNX. |
| **PyQt5 for new code** | GPL-licensed (viral for any linking code), superseded by Qt6 bindings. | PySide6 (LGPL, Qt6, actively maintained). |
| **mokuro as a subprocess** | Heavy, produces `.mokuro` files (web overlay) not editable boxes. We want box detection *logic*, not mokuro's output format. | Extract mokuro's detection model; or replace with YOLO; drive it from our app directly. |
| **numpy 2.0** (until wheels catch up) | ABI breakage: onnxruntime and opencv wheels built against numpy 1.x can crash on import. | Pin `numpy<2` until all deps ship 2.0-compatible wheels. |
| **Qt WebEngine** | Adds 100MB+, unnecessary for a canvas editor. | QGraphicsView/QGraphicsScene (what MangaCleaner_GPU uses) — native, fast, no web bloat. |

## Stack Patterns by Variant

- One uv venv with PySide6 + onnxruntime + transformers + torch
- Simplest dev experience, one `pyinstaller` spec
- Test this FIRST in Phase 1 — if `import torch; import onnxruntime; import cv2` all succeed on Python 3.12, stay here.
- Main app env: PySide6 + onnxruntime + opencv (the MangaCleaner_GPU stack)
- Isolated pyenv (via uv): transformers + torch + manga-ocr, run OCR as a subprocess/worker
- This is the fallback documented in PROJECT.md, not the default.
- Single env, no torch at all — pure ONNX app like MangaCleaner_GPU
- Best distribution story (smallest .exe, no CUDA installer needed for CPU users)
- Validate OCR accuracy vs. the transformers model before committing.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| onnxruntime 1.17+ | numpy <2.0 | ORT 1.17-1.19 have issues with numpy 2.0 on some platforms. Pin numpy<2. |
| PySide6 6.7+ | Python 3.9–3.12 | 3.13 support landed in PySide 6.8 but other deps (torch) lag. Stay on 3.12. |
| torch 2.2+ | Python 3.12 | Verified. torch 2.2 drops 3.8. CUDA wheels exist for Windows. |
| opencv-python 4.9+ | numpy <2.0 | Same ABI concern. 4.10+ may support numpy 2. |
| transformers 4.40+ | torch 2.x, numpy 1.x | Standard HF stack. `kha-white/manga-ocr-base` is a SwinVS encoder-decoder — needs transformers ≥4.25. |

## Sources

- **Local source (HIGHEST confidence):** `~/Downloads/MangaCleaner_GPU/_internal/src/` — read all backend/frontend/utils Python. Confirms PySide6 + ONNX + OpenCV architecture is proven for this exact use case.
- **Local source:** `~/Downloads/MangaCleaner_GPU/models/` — `lama.onnx` (197MB), `ocr.onnx` (4.6MB) prove ONNX distribution is viable.
- **Local source:** `~/Downloads/IOPaint-v1.1/` — LaMa-focused inpainting server config; confirms LaMa + SAM2 segmentation patterns.
- **Local source:** `~/Downloads/Poricom-v1.2.0-offline/` — tesserocr-based manga OCR viewer (UI reference, not OCR source).
- **Web:** https://github.com/kha-white/manga-ocr — `MangaOcr` class API, transformers pipeline usage.
- **Web:** https://huggingface.co/l0wgear/manga-ocr-2025-onnx — ONNX export of manga-ocr exists.
- **Web:** https://github.com/VoxelCubes/PanelCleaner — PyQt5, uses Simple LaMa (dreMaz) + Comic Text Detector + MangaOCR; GPL v3.
- **Web:** https://pypi.org/project/mokuro/ — pipeline tool, Python 3.9+.

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
