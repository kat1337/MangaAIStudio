# Phase 8: Masker & Selective Inpaint - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-15
**Phase:** 8-Masker & Selective Inpaint
**Areas discussed:** Selective inpaint entry & whole-page path, Knobs & settings surface, Per-box indicator & override, Paint-under-boxes dispatch

> **⚠ Provenance:** the interactive area-selection AskUserQuestion was dismissed by the user without
> input. Per harness guidance, the agent proceeded on best judgment: all four gray areas were
> auto-selected (the workflow's `--all` behavior) and each decision below is a **builder
> recommendation** derived from prior-phase contracts (Phase 3 D-15/D-07, Phase 2 D-02, Phase 4
> D-04), PanelCleaner parity, and the vendored machinery's semantics — NOT a user-locked choice.
> CONTEXT.md carries a matching provenance note; the user should review D-01…D-11 before planning.

---

## Selective inpaint entry & whole-page path (MASK-02 + MASK-05)

| Option | Description | Selected |
|--------|-------------|----------|
| New dedicated action (additive) | New "Selective Inpaint" action; legacy Inpaint (C) unchanged (CLEAN-06 validated behavior preserved; Phase 2 D-02 hand-edits honored on the legacy path) | ✓ |
| Rework Inpaint (C) into selective | Replace the whole-page semantics; simpler menu, but changes validated Phase 1 behavior and breaks deliberate out-of-box painting workflows | |
| Mode toggle on Inpaint | One action with a selectable mode; least menu churn, but conflates two contracts behind one shortcut | |

**User's choice:** *(auto)* New dedicated action — additive; ROADMAP phrasing ("still inpainted via legacy Inpaint action") implies the legacy path survives.
**Notes:** MASK-05's flagged sub-decision resolved as: out-of-box mask content stays inpainted on the legacy whole-page path; box-constraining applies only to the selective path (CONTEXT D-02). Hand-painted mask inside a qualifying box joins the selective input (CONTEXT D-03, Phase 2 D-02 at box granularity). Override tri-state semantics locked as Auto/Force/Skip (CONTEXT D-04).

---

## Knobs & settings surface (MASK-01 + masker thresholds)

| Option | Description | Selected | 
|--------|-------------|----------|
| Small "Cleaning Options…" dialog | Tools-menu dialog exposing dilation radius (default 2px), std threshold (15), off-white threshold (240); values persist to the PanelCleaner-compatible INI profile | ✓ |
| INI-only (no UI) | Zero UI work, but MASK-01 says "surfaced as a cleaning-profile parameter" and the app's audience is non-developer scanlators | |
| Full settings panel | Most discoverable, but is its own future phase (Phase 9 is reorganization only) — scope creep | |

**User's choice:** *(auto)* Small dialog; INI stays the source of truth (dialog is a view over it); remaining MaskerConfig knobs stay INI-only for advanced users.
**Notes:** Dilation is detection-time (ROADMAP-locked) — applies on the next Detect run (interactive + batch detect share the code path); no re-dilation of existing masks; changing the radius = re-detect to apply.

---

## Per-box indicator & override (MASK-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Box border treatment + Inspector tri-state | Border color/dash distinguishes inpainted / skipped-by-gate / force / skip (Phase 3 D-09 color-by-origin precedent); override via an Auto/Force/Skip control in InspectorPanel (Phase 4 D-04 follower pattern) | ✓ |
| Badge indicator | A second badge beside the bubble badge (z=140) — conflicts with the existing badge slot, clutters small boxes | |
| Inspector-only (no canvas indicator) | Simplest, but the user can't see outcomes at a glance across the page — MASK-03's "see, per box" implies canvas visibility | |

**User's choice:** *(auto)* Border treatment on canvas + Inspector tri-state; overrides persist on PageBox → `.mas`; re-detect resets overrides with the replaced boxes (Phase 3 D-03).
**Notes:** Indicator tokens are Claude's Discretion against `01-UI-SPEC.md`; must stay distinguishable from origin colors.

---

## Paint-under-boxes dispatch (MASK-06)

| Option | Description | Selected |
|--------|-------------|----------|
| Paint tools = pure paint; boxes interactive only in Move (V) | Box items transparent to mouse input while a paint tool is checked; select/move/resize/edit require V; Alt+drag create stays available (empty-canvas gesture); empty-canvas click still clears selection | ✓ |
| Modifier to select while painting (e.g. Alt/Shift+click on box with brush active) | Keeps some interaction without tool-switching, but hidden modifier complexity + collides with Alt-create | |
| Boxes always pass-through except handles | Handles still grab — resize possible while painting, but half-interactive boxes are surprising and handle hit-areas sit under strokes | |

**User's choice:** *(auto)* V-only box interaction; the carve-out applies exactly to the four paint tools (Brush/Rect/Lasso/Eraser); Crop unchanged (not a paint tool); Phase 3 D-07 superseded for paint tools only, as the ROADMAP prescribes.
**Notes:** This is one of the two decisions ROADMAP explicitly deferred to discuss-phase (resolved in CONTEXT D-10/D-11).

---

## Claude's Discretion

Selective action chrome (label/menu/shortcut — C taken); std-gate pipeline composition (pick_best_mask vs make_mask_steps_convolution; MaskerConfig plumbing; Worker threading + abort granularity); dilation implementation site (grow_mask post-detection vs cv2 dilate in TorchCTDModel.postprocess); dialog layout; indicator tokens; override field shape + `.mas` serialization format/version; per-box-fitted-mask display vs the M overlay; selective-run undo shape (likely one IMAGE entry per run); batch integration beyond free dilation pickup.

## Deferred Ideas

Batch selective clean (FLOW-03 extension, no MASK requirement asks for it); MASK-04 interactive grow/shrink brush (v2, explicit); FLOW-07 per-region LaMa params (v2, explicit); full settings UI panel; re-dilation of existing masks without re-detecting; the remaining 01-UAT detection-quality tuning knobs (threshold, min-area).
