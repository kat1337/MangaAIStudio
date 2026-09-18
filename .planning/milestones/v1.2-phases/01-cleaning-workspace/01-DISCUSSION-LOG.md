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

## Verification-Driven Revision (2026-07-12)

Context was re-opened for verification ("used the wrong model for discussion"). Every load-bearing claim in CONTEXT/RESEARCH was checked against the PanelCleaner source at `../PanelCleaner`. Outcome: the discovery was factually accurate on the major claims (PySide6, config classes, TextDetector API, simple_lama, all referenced files, GPL v3). Revisions made:

### Environment isolation strategy (D-07/D-08/D-09) — REVISED

Prior decision: "Proactive per-backend pyenvs" (3 hard-isolated envs, no shared deps, precautionary).

Verification finding: contradicted the project's "single env preferred, isolation as fallback" constraint; PanelCleaner's own `requirements.txt` proves the full PyTorch stack coexists in one env; Phase 1 is all-PyTorch, so the cited torch-vs-onnx/numpy conflict does not manifest. The original discussion options also did not surface the cross-process communication cost of isolating envs.

| Option | Description | Selected |
|--------|-------------|----------|
| Keep 3-way hard isolation (original D-07/D-08) | torch_env / onnx_env / main_env, no shared deps, precautionary | |
| Pure single-env for Phase 1 | One env; isolation only as a fallback if a conflict actually appears | |
| Frontend/backend split, isolation "whenever practical" | main_env (frontend) + torch_env (backend subprocess) + onnx_env (isolated for newer Python); single-env fallback | ✓ |

**User's choice:** "Revise to single-env + fixes but we should aim to have the backend env isolated from the frontend env whenever possible, and obviously the onnx env will be isolated as it uses a newer version of python to run."
**Notes:** ONNX isolation is now justified by a concrete reason (newer Python version), not a precautionary split. The frontend↔backend subprocess boundary (IPC mechanism) is left to planning; assumption A5 updated to track this as the real risk.

### Config format (D-05) — CORRECTED

Verification finding: PanelCleaner persists profiles via `ConfigUpdater` (INI), NOT JSON. `Config.from_json` / `Profile.to_json` / `profile_parser.ProfileParser` / `profile_cli.write_config_file` referenced in RESEARCH do not exist. JSON in PanelCleaner is only for pipeline data (`PageData`, `#clean.json`). Intent (config compatibility) preserved; format corrected to INI/ConfigUpdater. RESEARCH Pattern 2 and the Config Loading example rewritten to the real API.

### Code organization (D-10) — CLARIFIED

Verification finding: PanelCleaner is a batch detector + review viewer (`image_viewer.py` is a QGraphicsView for reviewing OCR bubbles), with no freehand mask painting. Interactive brush/rect/lasso/eraser (CLEAN-03/04/05) comes from MangaCleaner_GPU. Added a `mangacleaner/` adapted-source dir to D-10 so MangaCleaner_GPU's canvas code has a home.

### Minor API corrections in RESEARCH.md
- `TextDetector.__call__` returns a 5-tuple `(img, mask, mask_refined, blk_list, refine_mode)`, not a 3-tuple; `refine_mode` uses the `REFINEMASK_ANNOTATION` constant (inference.py:166, 204-207).
- `Profile` field names are `general/text_detector/preprocessor/masker/denoiser/inpainter`, not `*_config` (config.py:941-946).

### Stale text reconciled
- ROADMAP Phase 1 line + STATE.md "lifts MangaCleaner_GPU ~60%" reframed to the PanelCleaner + MangaCleaner_GPU foundation.
- PROJECT.md env decision row updated to the frontend/backend split; PySide6 (not PyQt5) and INI (not JSON) noted in the Context section.

### Adaptation / licensing policy (D-12) — ADDED

User clarification: MangaCleaner_GPU is to be used as a **reference** for our own implementation, **not copied verbatim**. PanelCleaner remains near-verbatim (GPL v3 ↔ GPL v3, intended derivative).

Verification added a concrete legal reason this is the right call: MangaCleaner_GPU at `~/Downloads/MangaCleaner_GPU` is a PyInstaller **binary distribution with no LICENSE file** — absent a license its code is all-rights-reserved and cannot be vendored into a GPL v3 derivative. Readable source for reference lives at `_internal/src/` (`frontend/canvas.py`, `backend/onnx_engine.py`).

Code-org consequence (D-10): dropped the `mangacleaner/` adapted-source directory — the interactive mask-editing canvas is now our own code in `gui/`+`core/`, patterned after MangaCleaner_GPU. Only `panelcleaner/` holds vendored upstream source.

**User's choice:** "we are not copying the code verbatim from mangacleaner we can definitely base our implementation on that but not quite copy it verbatim."

---

*Phase: 1-Cleaning Workspace*
*Discussion date: 2026-07-11; revised 2026-07-12 after source verification*
