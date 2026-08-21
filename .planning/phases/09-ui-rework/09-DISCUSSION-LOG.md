# Phase 9: UI Rework - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-21
**Phase:** 9-UI Rework
**Areas discussed:** Side-panel structure, Vertical toolbar contents, Edit section behavior

---

## Side-panel structure

| Option | Description | Selected |
|--------|-------------|----------|
| One panel, many sections | One right-side dock whose body is a stack of independently collapsible sections (Detection settings, Typesetting, Edit). Replaces today's tabified Tools+Inspector docks. | ✓ |
| Separate docks, sectioned | Keep Tools/Inspector as separate QDockWidgets but restyle each with collapsible sections inside. | |

**User's choice:** One panel, many sections
**Notes:** Matches the roadmap's "modular side panel" reading.

| Option | Description | Selected |
|--------|-------------|----------|
| Both move out of the panel | Detection settings become a collapsible section; brush size moves with the tools onto the canvas toolbar area. | |
| Brush stays in panel | Detection settings AND brush size each become collapsible side-panel sections; the vertical canvas toolbar holds only the 6 tool buttons. | ✓ |
| You decide | Planner places brush size and detection settings based on space/ergonomics. | |

**User's choice:** Brush stays in panel

| Option | Description | Selected |
|--------|-------------|----------|
| 4 sections, workflow order | Detection settings → Brush → Typesetting → Edit; each independently collapsible; collapse state persists across sessions. | ✓ |
| 4 sections, my order | Same four sections but user-specified order. | |
| You decide | Planner picks the order; contract is only "these four collapsible sections exist". | |

**User's choice:** 4 sections, workflow order

| Option | Description | Selected |
|--------|-------------|----------|
| Independent, any open | Any number of sections open at once; each header toggles independently; defaults planner discretion. | ✓ |
| Accordion (one open) | Opening one section collapses the others. | |
| You decide | Mechanism planner discretion as long as sections are independently collapsible per UI-01. | |

**User's choice:** Independent, any open

---

## Vertical toolbar contents

| Option | Description | Selected |
|--------|-------------|----------|
| 6 tools only | Strip holds Move/Brush/Rectangle/Lasso/Eraser/Crop; Detect, Inpaint, Undo/Redo, zoom stay in the top toolbar. | |
| Tools + Detect/Inpaint | The 6 tools plus Detect Text and Inpaint move to the strip. | ✓ |
| Full top-toolbar dissolution | Top toolbar removed entirely; everything redistributes into menus/panel. | |

**User's choice:** Tools + Detect/Inpaint (8 strip buttons)

| Option | Description | Selected |
|--------|-------------|----------|
| Top toolbar shrinks | Keeps Open Folder, zoom, Undo/Redo, Mask Overlay toggle, Preview (hold); Detect/Inpaint + tools leave for the strip. | ✓ |
| Remove top toolbar | Toolbar dissolved; actions live in menus + shortcuts only. | |

**User's choice:** Top toolbar shrinks

| Option | Description | Selected |
|--------|-------------|----------|
| Strip between canvas and panel | Layout: canvas, vertical tool strip, side panel (right of canvas — matches UI-03 literal wording). | |
| Overlay inside canvas | Strip floats INSIDE the canvas viewport as an overlay palette. | |
| (free text) | "strip between image list and canvas" | ✓ |

**User's choice:** Left of canvas, between the Pages file list and the canvas.
**Notes:** Flagged as conflicting with UI-03's "small vertical toolbar on the right side of the canvas". A confirming question offered left vs right explicitly; user chose **Left of canvas (as you typed)**. Recorded as decision D-05 with a planning instruction to update UI-03's wording.

| Option | Description | Selected |
|--------|-------------|----------|
| Text labels + divider | Current state (no icon assets exist); strip as wide as its longest label; divider before Detect/Inpaint. | |
| Icons (new assets) | Icon-only buttons with tooltips — requires creating/bundling ~8 icons this phase. | ✓ |
| You decide | Planner picks label style; divider + button set is the contract. | |

**User's choice:** Icons (new assets)

| Option | Description | Selected |
|--------|-------------|----------|
| New bundled icons, strip only | Custom SVG/PNG icons in a new assets dir for the 8 strip buttons; shrunken top toolbar keeps text labels. | ✓ |
| Icons everywhere | Same set plus icons on all remaining top-toolbar buttons. | |
| Qt standard icons | Qt built-in themed icons (no new assets) — poor fit for tools like Lasso. | |

**User's choice:** New bundled icons, strip only

---

## Edit section behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Buttons, same dialogs | Edit section holds buttons opening existing dialogs (Curves…, Crop…, Resize…) plus instant Rotate actions. Same behavior, new location. | ✓ |
| Inline controls | Some ops become inline panel controls instead of dialogs — bigger rework of proven dialog code. | |

**User's choice:** Buttons, same dialogs

| Option | Description | Selected |
|--------|-------------|----------|
| Menus slim down | Rotate/Curves/Resize leave the Tools menu and Crop… leaves the Edit menu — the section is the single mouse-driven home; shortcuts survive unchanged. | ✓ |
| Keep menus + add section | Menu entries stay AND the Edit section is added — duplicate entry points. | |

**User's choice:** Menus slim down

| Option | Description | Selected |
|--------|-------------|----------|
| 5 ops + crop tool on strip | Edit section = Curves…, Crop…, Rotate ×3, Resize…; Crop TOOL (G) stays a strip button; no separate Levels entry (superseded by Curves, Phase 6 D-01). | ✓ |
| Crop tool inside Edit too | Crop tool moves into the section and off the strip. | |

**User's choice:** 5 ops + crop tool on strip

---

## Agent's Discretion

- UI-02 inspector-toggle semantics and UI-04 rename reach (user declined to discuss; sensible defaults recorded in CONTEXT.md).
- Collapse mechanism implementation, default open/collapsed states.
- Icon art style/format/drawing approach.
- Active-tool highlight wiring through the strip (must preserve 06 D-10 / WR-02 sync contract).
- Section enablement mirroring `_refresh_action_states`.
- ToolsPanel/InspectorPanel refactor shape (section bodies vs wrapping widgets).

## Deferred Ideas

- Icons on the shrunken top toolbar ("Icons everywhere") — declined this phase; future polish candidate.
