# Phase 2: Cleaning Output & Batch - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-23
**Phase:** 2-Cleaning Output & Batch
**Areas discussed:** Batch pipeline behavior, Batch run control & UX

---

## Batch pipeline behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Always detect + inpaint | Every page runs full pipeline: CTD detect → LaMa inpaint → save. Heaviest; LaMa runs even on text-light pages. Matches PanelCleaner batch `clean` default. | |
| Inpaint only if text found (Recommended) | Detect first; skip LaMa on pages where detection finds no text, copying original through. Saves time on text-light pages. | ✓ |
| Detect-only vs full — user picks at run time | Batch dialog offers 'Masks only' or 'Full clean'. More flexible, more UI surface. | |

**User's choice:** Inpaint only if text found (Recommended). *(Later superseded by the two/three-stage workflow — inpaint is gated on mask content after detect + review.)*

| Option | Description | Selected |
|--------|-------------|----------|
| Copy original as-is (Recommended) | Write original page bytes unchanged so the cleaned chapter is complete. | ✓ |
| Skip the page entirely | Output only contains actually-cleaned pages; sparse. | |

**User's choice:** Copy original as-is (Recommended).

| Option | Description | Selected |
|--------|-------------|----------|
| Skip + continue, log the page (Recommended) | Mark failed page in log, skip, continue; summary at end ("2 of 30 failed"). Matches PanelCleaner resilience. | ✓ |
| Abort the whole batch | First error stops the run. Stricter, loses remaining progress. | |
| Prompt per failure | Stop on each error, ask whether to continue. Blocks unattended runs. | |

**User's choice:** Skip + continue, log the page (Recommended).

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse Phase 1 adapters + Worker (Recommended) | Batch calls same `backend_factory` detect/inpaint + Worker(QRunnable)/signals/abort. One pipeline, two entry points; no drift. | ✓ |
| Standalone batch pipeline | Separate headless class closer to PanelCleaner `processing.generate_output`. More code, decoupled. | |

**User's choice:** Reuse Phase 1 adapters + Worker (Recommended).

---

## Batch run control & UX

| Option | Description | Selected |
|--------|-------------|----------|
| Menu action → dialog (Recommended) | File → Batch Clean Chapter… opens dialog: source folder, output location, format. | |
| Batch the currently-open folder | 'Batch Clean Current Folder' on the sidebar's folder — no folder picker, just output location. | ✓ |
| Both | Menu offers both folder-picker and current-folder actions. | |

**User's choice:** Batch the currently-open folder. *(Refined later: output location settled to `cleaned/` subfolder, removing the output-location dialog.)*

| Option | Description | Selected |
|--------|-------------|----------|
| `cleaned/` subfolder next to source (Recommended) | e.g. `chapter-01/cleaned/*.png`. PanelCleaner default; no overwrite risk; grouped. | ✓ |
| Ask for output dir each run | QFileDialog pick at launch. Full control, one extra click. | |
| Flat alongside originals | `page-01_cleaned.png` next to `page-01.png`. Mixes cleaned + raw. | |

**User's choice:** `cleaned/` subfolder next to source (Recommended).

| Option | Description | Selected |
|--------|-------------|----------|
| Block the editor until done (Recommended) | Batch sets `_op_running`, disables detect/inpaint/batch actions (Phase 1 gate). One pipeline at a time. | ✓ |
| Let editing continue (batch in background) | Batch fully backgrounded; requires separate worker pool + state isolation; contention risk. | |

**User's choice:** Block the editor until done (Recommended).

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — Cancel button, finishes current page (Recommended) | Cancel sets SharableFlag (Phase 1 infra); worker checks between pages, stops after current page. Written pages stay. | ✓ |
| Yes — Cancel stops immediately | Interrupts mid-page. Faster stop, half-written file risk. | |
| No cancel — run to completion | Always runs every page. | |

**User's choice:** Yes — Cancel button, finishes current page (Recommended).

| Option | Description | Selected |
|--------|-------------|----------|
| Page count + current page name (Recommended) | Status bar "Cleaning page 12/30 — chapter-01-012.jpg" + 3px progress bar. No new widgets. | ✓ |
| Page count + per-stage breakdown | Also show within-page stage ("Detecting…/Inpainting…"). Reuses progress_callback. | |
| Separate batch progress window | Dedicated modal/overlay with progress + Cancel + per-page list. Most UI surface. | |

**User's choice:** Page count + current page name (Recommended).

| Option | Description | Selected |
|--------|-------------|----------|
| Use existing masks as-is (Recommended) | Batch Clean reads each page's current mask (detect + edits) and inpaints exactly that. Never re-detects; edits are sacred. | ✓ |
| Re-detect, then inpaint | Batch Clean re-runs detection before inpainting. Overwrites manual edits — defeats review purpose. | |

**User's choice:** Use existing masks as-is (Recommended).

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — two separate actions (Recommended) | Batch Detect + Batch Clean, review in between. | |
| One action with stages | Single 'Batch Clean Chapter' detect → inpaint → save, no review gap. | |
| Other | Three actions: Batch Detect, Batch Clean, and one that does both (the original). | ✓ |

**User's choice:** Three actions — Batch Detect (detect masks, load into workspace), Batch Clean (inpaint using current masks, save to `cleaned/`), Batch Detect+Clean (one-shot original flow). "It's about flexibility." This became the central design decision (D-01).

**Notes:** The user's free-text response to the "done?" prompt reshaped the phase: rather than a single batch run, they want a reviewable two-stage workflow with detect-only and clean-only as first-class actions, plus the combined convenience action. This requires per-page mask persistence across navigation (D-11/CONTEXT code_context) — the central data-model change for Phase 2.

---

## Claude's Discretion

- **Single-page export (PROJ-02) mechanics** — not discussed in depth; defaulted to: `File → Export Page…` / Ctrl+E, Save As dialog (reusing Phase 1 patterns), exports the current canvas result (original + applied inpaints, not a fresh re-clean), preserves original format / falls back to PNG, JPG quality 95 (PanelCleaner `save_optimized`).
- **Batch output file format** — default preserve each original's format; re-encode via `save_optimized` kwargs.
- **Re-running batch over existing `cleaned/`** — overwrite by default; skip-if-exists optional.
- **Completion behavior** — status-bar summary message; no auto-open folder / notification.
- **Where batch actions live in UI** — File menu / Batch submenu + optional toolbar buttons; researcher/planner place them.
- **Per-stage progress text** — optional polish beyond D-10's required page-count behavior.

## Deferred Ideas

- Per-page LaMa params / tile size (FLOW-07) — v2.
- Batch→editor round-trip / batch-results browser (FLOW-05) — v2.
- Image operations on export crop/rotate/levels/resize (PROJ-04) — Phase 5.
- `_ocr.json` / `.mas` export (PROJ-03 / PROJ-01) — Phase 5.
- System notification / auto-open output folder on completion — optional polish.
