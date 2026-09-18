# Retrospective

## Cross-Milestone Trends

| Milestone | Phases | Plans | Recurring Theme |
|-----------|--------|-------|-----------------|
| v1.2 | 10 (incl. 08.1) | 76 | Vendored-code discipline; undo-stack stamp-sharing; probe-before-plan |

## Milestone: v1.2 — Masker & Selective Inpaint + UI Rework

**Shipped:** 2026-08-22
**Phases:** 10 | **Plans:** 76 | **Tasks:** 132

### What Was Built
- Cleaning parity on the PanelCleaner foundation: heatmap detection, mask painting, LaMa inpainting, dual undo stacks, single + batch export
- Editable text boxes with draw-to-OCR, manga-ocr integration, manual translation layer, and LoadTranslations batch apply
- `.mas` project persistence (LZMA2 container), image ops (rotate/crop/resize/levels→curves), `_ocr.json` export
- Full typesetting: TextStyle model, shared renderer (horizontal + tategaki vertical), outline/glow/shadow effects, Inspector Style section, Export Typeset bake
- Masker & selective inpaint: dilation radius, box-constrained std-deviation gate (corrected to PanelCleaner semantics in 08.1), per-box override, OOM-safe patched inpainting, batch parity
- UI Rework: vertical icon tools strip left of canvas, unified collapsible Panel dock (Detection settings → Brush → Typesetting → Edit), Typesetting rename, QSettings collapse persistence, menu slimming with zero shortcut loss

### What Worked
- Probe-first discipline: live probes before planning caught several plan-literal prescriptions that did not match real Qt/PIL semantics
- Stamp-shared triple-push undo records — one Ctrl+Z reversing image+mask+boxes became a durable cross-phase contract
- Tracer-first plans: each phase's wave 1 proved an end-to-end slice before expansion
- Full-suite re-baselining at every plan close (552 → 1018 tests, always a strict superset)

### What Was Inefficient
- Verification debt accumulated at milestone end (Phase 7 stale, Phase 08.1 missing) — verify immediately after execute instead of batching
- Three debug sessions left open across phases; diagnose-and-close within the same phase would avoid carry-over
- Plan-time requirement wording drift (UI-03 "right side" vs D-05 left-of-canvas) required ROADMAP/REQUIREMENTS corrections during planning

### Patterns Established
- blockSignals mirror pairs for slider↔spinbox and action↔button sync
- Tolerant QSettings bool parse (true/1/yes/on, fail-open to default)
- Module-relative resource loading for bundled assets
- snapshot-as-geometry recompose contract for canvas mask planes
- Pinned interpreter rule for all test commands (pyenv 3.14.2)

### Key Lessons
- QActionGroup exclusivity is suppressed under blockSignals — compensate with explicit uncheck loops
- QGraphicsItem children of an item group cannot be individually selected — use parent-less scene items
- QTest int-truncation at fractional fit scales makes pixel-exact move assertions fragile — anchor on delivered positions
- Deletion of scene items must be deferred past the paint flush (QTimer.singleShot graveyard) to avoid native aborts

### Cost Observations
- Model mix: orchestrator-inherit throughout (no explicit overrides)
- Sessions: continuous auto-advance chains discuss→plan→execute per phase
- Notable: Phase 9 planned → executed → verified → UAT → security-cleared in one session
