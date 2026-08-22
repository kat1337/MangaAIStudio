# Roadmap: Manga AI Studio

## Overview

Manga AI Studio unifies manga page cleaning, mask editing, text-box OCR, and translation layout into one PySide6 desktop app. The journey starts by adapting PanelCleaner (GPL v3) as the foundation with a model adapter interface, reaching cleaning parity immediately, then builds the novel differentiator — editable text boxes with per-box manga-ocr and a translation layer — and finally lands the project system (save/resume, image ops, JSON export) that turns the editor into a resumable workspace. Each phase is a vertical slice delivering one complete, user-observable capability.

**Mode:** mvp
**Granularity:** standard

## Milestones

- ✅ **v1.2 Masker & Selective Inpaint + UI Rework** — Phases 1–9 incl. 08.1 (shipped 2026-08-22) → [milestones/v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md)

## Phases

<details>
<summary>✅ v1.2 Masker & Selective Inpaint + UI Rework (Phases 1–9) — SHIPPED 2026-08-22</summary>

- [x] Phase 1: Cleaning Workspace (7/7 plans) — completed 2026-07-21
- [x] Phase 2: Cleaning Output & Batch (4/4 plans) — completed 2026-07-26
- [x] Phase 3: Text Box Detection & Interaction (8/8 plans) — completed 2026-08-04
- [x] Phase 4: OCR Recognition & Text Editing (10/10 plans) — completed 2026-08-08
- [x] Phase 5: Project Persistence, Image Ops & Export (10/10 plans) — completed 2026-08-08
- [x] Phase 6: Refinement & Polish (8/8 plans) — completed 2026-08-09
- [x] Phase 7: Typesetting TRAN-02 (12/12 plans) — completed 2026-08-09
- [x] Phase 8: Masker & Selective Inpaint (10/10 plans) — completed 2026-08-19
- [x] Phase 08.1: Inpaint correction & OOM-safe patching (4/4 plans, INSERTED)
- [x] Phase 9: UI Rework (3/3 plans) — completed 2026-08-22

Full phase details: [milestones/v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md)

</details>

## Notes & Out-of-Band Concerns

- **Packaging / distribution** (PyInstaller + PySide6 + onnxruntime, model weight distribution ~600MB, Windows AV false positives) is emphasized by research as real work but has **no v1 requirement ID**. It is not a requirement-driven phase here. Recommend inserting it as a decimal phase or a future milestone once a packaging requirement is formalized.
- **Environment validation** (torch + onnxruntime + numpy<2 coexistence, CUDA→CPU fallback) was a Phase 1 day-one gate (pitfalls P1, P2).
- **Latent QImage buffer bug** in MangaCleaner_GPU's `on_task_finished` was fixed when lifting canvas code in Phase 1 (pitfall P5).

## Progress

**Execution Order:**
Phases executed in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 08.1 → 9

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Cleaning Workspace | 7/7 | Complete | 2026-07-23 |
| 2. Cleaning Output & Batch | 4/4 | Complete | 2026-07-26 |
| 3. Text Box Detection & Interaction | 8/8 | Complete | 2026-08-04 |
| 4. OCR Recognition & Text Editing | 10/10 | Complete | 2026-08-08 |
| 5. Project Persistence, Image Ops & Export | 10/10 | Complete | 2026-08-08 |
| 6. Refinement & Polish | 8/8 | Complete | 2026-08-09 |
| 7. Typesetting (TRAN-02) | 12/12 | Complete | 2026-08-09 |
| 8. Masker & Selective Inpaint | 10/10 | Complete | 2026-08-19 |
| 08.1 Inpaint correction & OOM-safe patching | 4/4 | Complete | 2026-08-20 |
| 9. UI Rework | 3/3 | Complete | 2026-08-22 |

---
*Roadmap created: 2026-07-11; v1.2 shipped and archived: 2026-08-22*
