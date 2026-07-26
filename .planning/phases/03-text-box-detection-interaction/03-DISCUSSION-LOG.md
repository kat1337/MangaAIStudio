# Phase 3: Text Box Detection & Interaction - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-25
**Phase:** 3-Text Box Detection & Interaction
**Areas discussed:** Detection entry point, Box object & interaction model, Box edits & undo

*Area offered but not selected:* Box persistence & per-page state (folded into Claude's Discretion in CONTEXT.md — the `ImageFile` extension is the obvious path, mirroring Phase 2 D-11; no user decision needed).

---

## Detection entry point

### Q1 — How should detection work in Phase 3?

| Option | Description | Selected |
|--------|-------------|----------|
| One unified action | One "Detect Text" action produces BOTH mask AND boxes in one pass; re-running refreshes both. | |
| Separate Detect Boxes | Keep Phase 1 mask-Detect; add a new "Detect Boxes" action (second model pass unless cached). | |
| One action, toggle | One action with a mode/toggle: "mask + boxes" vs "mask only". | ✓ |

**User's choice:** One action, toggle
**Notes:** CTD's single pass already returns mask AND `blk_list`; a toggle reuses that one pass without a second model run.

### Q2 — How do detected boxes relate to the mask layer?

| Option | Description | Selected |
|--------|-------------|----------|
| Boxes = separate layer | Boxes are their own overlay layer, toggleable independently; mask and boxes coexist. | ✓ |
| Boxes replace mask | Detecting boxes replaces the mask workflow for that page. | |
| You decide | Let researcher/planner propose based on PanelCleaner/mokuro modeling. | |

**User's choice:** Boxes = separate layer

### Q3 — Re-running detection over a page that already has boxes?

| Option | Description | Selected |
|--------|-------------|----------|
| Replace detected, keep user | Refresh the auto-detected set; preserve user-drawn/moved boxes (mirrors Phase 2 D-02). | ✓ |
| Always replace all | Re-detect replaces all boxes including user edits. | |
| Merge new + existing | New detected boxes added alongside existing (dedup by overlap). | |

**User's choice:** Replace detected, keep user
**Notes:** Requires an `origin` flag on each box ("detected" vs "user") so re-detect knows what to replace. Drives the D-09 color-by-origin decision later (user must see which is which).

### Q4 — Confirm gate on running detection?

| Option | Description | Selected |
|--------|-------------|----------|
| Per-page, with confirm | Confirm before replacing existing boxes (mirrors Phase 1 mask-detect). | ✓ |
| Per-page, no confirm | Detection just runs and shows boxes. | |
| You decide | Defer confirm-dialog details to planner. | |

**User's choice:** Per-page, with confirm

---

## Box object & interaction model

### Q1 — How should a text box be represented on the canvas?

| Option | Description | Selected |
|--------|-------------|----------|
| QGraphicsRectItem + handles | Subclass QGraphicsRectItem; native Qt selection/move; resize via 4 corner child handles. | ✓ |
| Custom QGraphicsObject | Custom paint() for full rendering control; reimplements selection/move. | |
| You decide | Researcher compares against PanelCleaner review viewers + MangaCleaner_GPU canvas. | |

**User's choice:** QGraphicsRectItem + handles
**Notes:** Resize-by-corner was locked by the user up front ("allow modifying the box size by dragging the corner to resize them").

### Q2 — How do box interactions coexist with the 5 mask tools?

| Option | Description | Selected |
|--------|-------------|----------|
| Add SELECT tool mode | 6th tool mode in the existing QActionGroup. | |
| Always interactive | Boxes always interactive when box layer visible; click-on-box selects/moves, click-empty paints mask. | ✓ |
| You decide | Defer to planner. | |

**User's choice:** Always interactive
**Notes:** Keeps the `ToolMode` enum and `ToolsPanel` unchanged for v1.

### Q3 — Single-select or multi-select?

| Option | Description | Selected |
|--------|-------------|----------|
| Single-select | One box at a time (matches TEXT-03 singular). | ✓ |
| Multi-select | Shift/cmd-click + marquee. | |
| You decide | Start single for v1. | |

**User's choice:** Single-select

### Q4 — Should detected vs user-added boxes look different?

| Option | Description | Selected |
|--------|-------------|----------|
| Color by origin | Distinct border styles so user sees what re-detect would replace vs keep. | ✓ |
| Uniform style | All boxes identical. | |
| You decide | Researcher picks a UI-SPEC-consistent style. | |

**User's choice:** Color by origin
**Notes:** Functional, not decorative — required for the Q3 "replace detected, keep user" rule to be predictable.

---

## Box edits & undo

### Q1 — Where do box edits go in the undo system?

| Option | Description | Selected |
|--------|-------------|----------|
| 3rd stack: BOXES | Add BOXES alongside MASK + IMAGE; box ops push snapshots. | ✓ |
| No box undo (v1) | Box edits live/immediate; Delete confirms. | |
| You decide | Researcher weighs HistoryManager shape vs box-edit granularity. | |

**User's choice:** 3rd stack: BOXES

### Q2 — How should Delete box behave?

| Option | Description | Selected |
|--------|-------------|----------|
| Confirm or undoable | Confirm dialog, or undoable if box undo in scope. | |
| Immediate, silent | No friction; deleting false-positives is the common case. | ✓ |
| You decide | Planner picks based on the box-undo decision. | |

**User's choice:** Immediate, silent
**Notes:** Safe because Q1 put box ops on an undo stack — Ctrl+Z recovers a deleted box.

### Q3 — Is creating a new empty box in Phase 3 scope?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — draw-to-create box | Click-drag to create a user-origin empty box; re-detect preserves it. | ✓ |
| No — Phase 4 (draw-to-OCR) | Phase 3 = detect + correct only; creating boxes waits for TEXT-02. | |
| You decide | Researcher checks whether TEXT-03 "add" requires free creation. | |

**User's choice:** Yes — draw-to-create box
**Notes:** Makes TEXT-03's correction workflow complete; gives the "user boxes survive re-detect" rule something to preserve.

### Q4 — With a 3rd BOXES stack, how do shortcuts work?

| Option | Description | Selected |
|--------|-------------|----------|
| Separate shortcuts | Box undo on its own shortcut (e.g. Ctrl+Alt+Z). | |
| Unified Ctrl+Z | One shortcut pops most-recent across all three stacks chronologically. | ✓ |
| You decide | Planner maps against Phase 1 UI-SPEC. | |

**User's choice:** Unified Ctrl+Z

### Q5 (reconciliation) — "3rd BOXES stack" + "unified Ctrl+Z" pull different directions. Which model?

| Option | Description | Selected |
|--------|-------------|----------|
| 3 stacks + merged timeline | Keep 3 underlying stacks; Ctrl+Z pops most-recent-by-timestamp across all three. | ✓ |
| Truly single stack | Collapse to one timeline; rewrites Phase 1 HistoryManager + UI-SPEC 2-stack contract. | |
| Revisit: separate shortcuts | 3 fully separate stacks with separate shortcuts. | |

**User's choice:** 3 stacks + merged timeline
**Notes:** Honors both prior answers — three stores preserve Phase 1's per-type shape; one merged pop order gives the user a single undo. This reconciliation is documented in CONTEXT.md D-11 because it is the detail the planner most needs to be unambiguous about.

---

## Claude's Discretion

Captured in CONTEXT.md §Claude's Discretion:
- Exact color/style pair for detected-vs-user boxes (from UI-SPEC tokens)
- The draw-to-create gesture (modifier+drag vs transient mode vs button)
- Whether to wrap `TextBlock` in our own `Box` class (likely yes, for `origin` flag + stable undo identity)
- Box-data persistence shape (`ImageFile.boxes` slot recommended, mirroring Phase 2 D-11)
- Box-undo record granularity (full per-page boxes snapshot recommended — cheap, matches Phase 1 shape)
- Re-detect confirm-gate copy

---

## Deferred Ideas

- OCR text recognition / inline text edit / translation field (TEXT-02/04/05) — Phase 4
- Batch box-detection across a chapter — future batch extension
- `.mas` save/load of boxes (PROJ-01) and `_ocr.json` export (PROJ-03) — Phase 5
- Multi-select / marquee selection — optional polish (Phase 3 is single-select)
- Edge handles, rotated/vertical box rendering, bubble auto-sizing — Out of Scope (v2+ typesetting)
- Inline text rendering/typesetting inside boxes — Out of Scope (BallonsTranslator territory)
