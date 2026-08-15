# Phase 8: Masker & Selective Inpaint - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-15
**Phase:** 8-masker-selective-inpaint
**Areas discussed:** Selective inpaint entry, Dilation & threshold UI, Indicator & override, Paint-under-boxes

---

## Area selection

All four gray areas were selected for discussion (multiSelect).

## Selective inpaint entry

**Q1: How does the user invoke selective per-box inpainting?**

| Option | Description | Selected |
|--------|-------------|----------|
| New separate action | A separate 'Selective Inpaint' action joins the menu; Inpaint (C) keeps whole-page behavior | |
| Rework Inpaint (C) | The existing Inpaint (C) becomes box-aware | ✓ (via freeform) |
| You decide | Claude picks the entry-point design | |

**User's choice:** Freeform — "manually painted masks should always be inpainted on, but because the OCR can have false positives, just like panelcleaner, we only inpaint/mask things that are inside a text box (they're actual text), what the user choses to inpaint by hand gets inpainted anyways"
**Notes:** The user's rule is mask-ORIGIN-based, not action-based. Follow-up (plain text) asked whether one path or two; answer: "C simply becomes this rule, in fact, let's add a bit of a processing step to make this simpler and not have to make changes to the inpainter, text detected by the detector that is outside of a box simply doesn't get added to the mask layer, simpler and nicer" — one path; constraint enforced at the detection→mask seam; the inpainter is untouched.

**Q2: What happens to out-of-box mask content on the existing whole-page path? (the flagged MASK-05 decision)**

**User's choice:** "Refer to answer one" — resolved by the seam-level discard rule (out-of-box detected text never enters the mask layer).

**Q3: What happens to the existing 'Detect Boxes' mode toggle?**

| Option | Description | Selected |
|--------|-------------|----------|
| Always constrained | Detection always builds boxes + discards; the toggle retires | |
| Toggle keeps Phase 1 | Mask-only mode keeps the FULL heatmap, unconstrained | ✓ |
| You decide | Claude picks | |

**User's choice:** Toggle keeps Phase 1.

**Q4: Does the batch pipeline adopt the same box-constrained rule?**

| Option | Description | Selected |
|--------|-------------|----------|
| Batch follows rule | Batch detect/clean builds boxes from the same pass, constrains masks | ✓ |
| Batch unchanged | Batch keeps whole-heatmap behavior | |
| You decide | Claude picks | |

**User's choice:** Batch follows rule.

## Dilation & threshold UI

**Q1: Where does the mask dilation radius (MASK-01) live in the UI?**

| Option | Description | Selected |
|--------|-------------|----------|
| Tools panel row | Spinbox in the existing ToolsPanel near brush size | |
| Settings dialog | Dedicated cleaning-settings dialog | |
| Profile-only | INI-only, no UI | |
| You decide | Claude picks | |

**User's choice:** Freeform — "Let's add it to the right bar under detection settings along with detect boxes, and this dilation should only affect auto-detected masks, not user hand drawn masks"
**Notes:** A detection-settings section in the right-side Tools dock, holding the Detect Boxes toggle (moved from the Tools menu) + the dilation radius. Dilation never touches hand-drawn strokes.

**Q2: When does changing the dilation radius take effect on an already-detected page?**

| Option | Description | Selected |
|--------|-------------|----------|
| Detection-time only | Radius read when Detect runs; next detect only | |
| Live re-dilate | Raw pre-dilation mask retained; radius change re-dilates instantly | ✓ |
| You decide | Claude picks | |

**User's choice:** Live re-dilate.

**Q3: Is the std-deviation threshold fixed or user-tunable?**

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed default (15) | Vendored PanelCleaner default, no UI | |
| User-tunable | Slider/spinbox in the same section | ✓ |
| You decide | Claude picks | |

**User's choice:** Freeform — "User tunable, and we can look at how panelcleaner does it, it supports color too, so let's also add that allow color masks check to this"
**Notes:** The allow-color checkbox (MaskerConfig.allow_colored_masks) joins the section.

**Q4: Which masker parameters get UI exposure?**

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal set | Radius + threshold + allow-color only | |
| Full masker set | The entire vendored MaskerConfig parameter set | ✓ |
| You decide | Claude picks | |

**User's choice:** Full masker set.

**Q5: What's the out-of-box default for the dilation radius?**

| Option | Description | Selected |
|--------|-------------|----------|
| 0 (off) default | Today's behavior until opted in | |
| Small default (~2px) | Detection covers letter edges out of the box | ✓ |
| | | |

**User's choice:** Small default (~2px).

**Q6: Where do the detection-settings values persist?**

| Option | Description | Selected |
|--------|-------------|----------|
| Profile INI | PanelCleaner-compatible profile via ProfileManager | ✓ |
| App settings | QSettings/JSON decoupled from profiles | |
| You decide | Claude picks | |

**User's choice:** Profile INI.

## Indicator & override

**Q1: How does the user SEE per-box inpaint state (MASK-03)?**

| Option | Description | Selected |
|--------|-------------|----------|
| Border color states | Border color/style encodes inpaint state | ✓ |
| Badge | Small badge like the Phase 4 bubble badge | |
| You decide | Claude picks | |

**User's choice:** Border color states.

**Q2: When does the indicator compute — predictive or outcome?**

| Option | Description | Selected |
|--------|-------------|----------|
| Predictive (live) | std-dev at detect time; border previews the next run; live updates | ✓ |
| Outcome only | Border shows state only after an inpaint run | |
| You decide | Claude picks | |

**User's choice:** Predictive (live).

**Q3: Where does the per-box override live?**

| Option | Description | Selected |
|--------|-------------|----------|
| Inspector field | A field in the existing InspectorPanel | ✓ |
| Context menu | Right-click menu entries | |
| Both | Inspector + context menu | |
| You decide | Claude picks | |

**User's choice:** Inspector field.

**Q4: What's the override state model per box?**

| Option | Description | Selected |
|--------|-------------|----------|
| Tri-state Auto/Always/Never | Auto (gate) / Always (force) / Never (skip); .mas round-trip | ✓ |
| Simple exclude toggle | Single checkbox; no true force | |
| You decide | Claude picks | |

**User's choice:** Tri-state Auto/Always/Never.

## Paint-under-boxes

**Q1: When a paint tool is active, how do clicks on boxes dispatch?**

| Option | Description | Selected |
|--------|-------------|----------|
| Full pass-through | Boxes fully pass through; selection only in Move tool | |
| Pass-through + Alt select | Paint through; Alt+click selects a box | ✓ |
| You decide | Claude picks | |

**User's choice:** Pass-through + Alt select.

**Q2: How does Alt interact with drag on a box body?**

| Option | Description | Selected |
|--------|-------------|----------|
| Alt+drag moves box | Alt+click selects; Alt+drag on box moves; create stays empty-canvas-only | ✓ |
| Select is click-only | Alt+click selects only; Alt+drag always creates | |
| | | |

**User's choice:** Alt+drag moves box.

**Q3: Does double-click still open the inline editor while a paint tool is active?**

| Option | Description | Selected |
|--------|-------------|----------|
| Editor still opens | Inline editor opens regardless of active tool | ✓ |
| Move tool only | Editor only from Move tool | |
| | | |

**User's choice:** Editor still opens.

**Q4: Does the Crop tool also pass through boxes?**

| Option | Description | Selected |
|--------|-------------|----------|
| Paint tools only | Carve-out covers Brush/Rect/Lasso/Eraser; Crop unchanged | ✓ |
| All non-Move tools | Crop also passes through | |
| | | |

**User's choice:** Paint tools only.

**Q5: Should boxes visually signal pass-through while a paint tool is active?**

| Option | Description | Selected |
|--------|-------------|----------|
| De-emphasize boxes | Dim boxes while paint tool active | |
| No visual change | Boxes render identically regardless of tool | ✓ |
| | | |

**User's choice:** No visual change.

## Claude's Discretion

Areas deferred to research/planning (recorded in CONTEXT.md): raw-mask retention shape, mask-layer composition model (composite vs tracked sub-layers; per-box mask storage format/coordinates), whether user-origin boxes certify like detected ones, std-dev recomputation triggers/debouncing, `.mas` version impact + per-box mask serialization, Inspector override widget form + multi-select common-value behavior, batch integration details (where boxes build, batch per-box state), undo granularity confirmation, re-detect interplay with overrides/std_dev, detection-settings keyboard story, exact border state colors (UI-spec pass).

## Deferred Ideas

- MASK-04 interactive mask grow/shrink brush — v2 (ROADMAP).
- FLOW-07 per-region LaMa params — v2 (ROADMAP).
- Sidebar/toolbar layout rework — Phase 9 (detection-settings builds into the current Tools dock; Phase 9 reorganizes later).

No scope-creep ideas surfaced during discussion.
