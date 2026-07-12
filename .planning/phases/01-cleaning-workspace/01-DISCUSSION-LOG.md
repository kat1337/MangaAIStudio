# Phase 1: Cleaning Workspace - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-11
**Phase:** 1-Cleaning Workspace
**Areas discussed:** Model adapter interface design, Config/profile system adaptation, pyenv isolation strategy, Code organization & package structure

---

## Model adapter interface design

| Option | Description | Selected |
|--------|-------------|----------|
| Type-specific base classes | One base interface per model type (DetectionModel, OCRModel, InpaintModel) with standardized methods. Simple, clear separation. | ✓ |
| Generic unified interface | Generic ModelBackend interface with type hints and model_type enum. More complex but handles all models uniformly. | |
| Pipeline-step abstraction | Abstract the pipeline step (DetectText, RunOCR, InpaintImage) not the model. Each step has a run() that dispatches to configured backend. | |

**Methods for DetectionModel:**

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal: load + detect + info | load(model_path), detect(img) → mask/bboxes, get_info() → metadata. Minimal, covers detection use case. | |
| Full pipeline with hooks | load(), detect(img), preprocess(img), postprocess(result), configure(options). Full pipeline control for advanced users. | ✓ |
| Rich detection with classification | DetectModel detects AND classifies (text/sfx bubble). Returns structured TextBlock objects. Richer output. | |

**Backend switching:**

| Option | Description | Selected |
|--------|-------------|----------|
| Global config switch | Config file setting (model_backend: torch|onnx) switches all models. Simple, global. | |
| Per-model config | Per-model config (detection_backend: torch, inpainting_backend: onnx). Granular, users can mix backends. | ✓ |
| Auto-detect from file extension | Backend is inferred from model file extension (.pt → torch, .onnx → onnx). | |

**User's choice:** Type-specific base classes with full pipeline hooks and per-model backend configuration.
**Notes:** Enables maximum flexibility — users can run CTD on PyTorch while using ONNX Runtime for LaMa if they prefer.

---

## Config/profile system adaptation

| Option | Description | Selected |
|--------|-------------|----------|
| Full PanelCleaner config verbatim | Adapt PanelCleaner's config system verbatim. All features, same structure. Ensures 100% compatibility. | ✓ |
| Single-profile v1, compatible schema | Simplify to single-profile system for v1, keep JSON schema for compatibility. | |
| Core verbatim, Phase 1 subset exposed | Hybrid: Core config system verbatim, but only expose Phase 1 settings. | |

**User's choice:** Full PanelCleaner config verbatim.
**Notes:** Ensures 100% compatibility with existing pcleaner configs. All Phase 1 settings map to PanelCleaner equivalents.

---

## pyenv isolation strategy

**When to create isolated pyenvs:**

| Option | Description | Selected |
|--------|-------------|----------|
| Import failure → isolate | Create isolated pyenv only if import fails in main env. Lazy, just-in-time isolation. | |
| Proactive per-backend envs | Create isolated pyenvs proactively for each backend type (torch_env, onnx_env). More predictable setup. | ✓ |
| Conflict-aware setup with recommendations | Start with single env. If backend has known conflicts, auto-recommend isolation at setup. | |

**What goes in each env:**

| Option | Description | Selected |
|--------|-------------|----------|
| Complete backend isolation | torch_env: PyTorch, transformers, manga-ocr, CTD. onnx_env: ONNX Runtime, opencv, numpy. main_env: PySide6, GUI, config. | ✓ |
| Shared base deps, isolated models | torch_env: PyTorch + torch-only models. onnx_env: ONNX Runtime + ONNX models. Both share opencv/numpy. | |
| Single env, optional isolation | Single env with both PyTorch and ONNX Runtime. Isolated envs only if user requests. | |

**User's choice:** Proactive per-backend envs with complete backend isolation.
**Notes:** Clean separation prevents dependency conflicts. torch_env (PyTorch), onnx_env (ONNX Runtime), main_env (PySide6/GUI). Phase 1 uses torch_env.

---

## Code organization & package structure

**Package structure:**

| Option | Description | Selected |
|--------|-------------|----------|
| manga_ai_studio/gui/core/models | manga_ai_studio top-level with gui/, core/, models/ subpackages. Mirrors PanelCleaner. | |
| Adapters + adapted source layout | manga_ai_studio/adapters/ for interfaces, panelcleaner/ for adapted code. Explicit about adapted vs original. | ✓ |
| Flat v1, reorganize later | Flat structure: mainwindow.py, canvas.py, detection.py. Simple for v1. | |

**Adapter organization:**

| Option | Description | Selected |
|--------|-------------|----------|
| base.py + backend implementations | adapters/base.py (base classes), adapters/torch_impl.py, adapters/onnx_impl.py. Clean module boundaries. | ✓ |
| Per-model files with all backends | adapters/models/detection.py with base + torch/onnx in each file. | |
| Backend-first organization | adapters/torch/ and adapters/onnx/ directories. | |

**User's choice:** Adapters + adapted source layout with base.py + backend implementations.
**Notes:** Explicit organization shows what's adapted PanelCleaner code vs. original adapter interfaces. Clean module boundaries.

---

## Claude's Discretion

- Package naming within submodules — follow PanelCleaner patterns where sensible
- Import organization within adapted PanelCleaner code — preserve original structure unless conflicts
- Color scheme/theme — can adapt PanelCleaner's theme or create new branding (user hasn't specified)

## Deferred Ideas

None — discussion stayed within phase scope. All decisions support Phase 1 cleaning parity goal.

---

*Phase: 1-Cleaning Workspace*
*Discussion date: 2026-07-11*
