# Phase 6: Refinement & Polish — deferred fixes + full curve editor - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-09
**Phase:** 6-refinement-polish-deferred-fixes-full-curve-editor
**Areas discussed:** Curve vs Levels dialog, Curve interaction feel

---

## Curve vs Levels dialog

| Option | Description | Selected |
|--------|-------------|----------|
| Replace Levels entirely | One 'Curves…' dialog replaces 'Levels…' in the Tools menu. Black/white/gamma become draggable curve points. Matches ROADMAP wording; one fewer dialog. | |
| Both dialogs coexist | Keep the Levels dialog as-is and add a separate 'Curves…' dialog. Two Tools-menu entries. | |
| Curve dialog + point sliders | One Curves dialog, but the black/white point sliders stay as a quick-access row above the curve grid. | ✓ |

**User's choice:** Curve dialog + point sliders
**Notes:** The user wants one dialog that keeps the familiar black/white/gamma quick controls while adding the full curve.

| Option | Description | Selected |
|--------|-------------|----------|
| Bidirectional sync | The curve is the single source of truth. Slider drags move curve endpoints; curve-point drags update sliders. No divergence. | ✓ |
| Sliders seed, then curve takes over | Sliders set the curve shape once; curve dragging takes over after. | |
| Independent layered adjustments | Sliders apply as a separate adjustment layered on the curve (two stacked LUTs). | |

**User's choice:** Bidirectional sync
**Notes:** Mental model: sliders and curve are two views of one state.

| Option | Description | Selected |
|--------|-------------|----------|
| Keep gamma, sync to midpoint | Log-scaled gamma slider drives the curve's midpoint anchor; dragging the midpoint updates the slider. | ✓ |
| Drop gamma, midpoint drag only | Dragging the curve's midpoint is the gamma adjustment (Photoshop style). | |

**User's choice:** Keep gamma, sync to midpoint
**Notes:** Full parity with today's Levels controls.

| Option | Description | Selected |
|--------|-------------|----------|
| Rename to 'Curves…' | Menu action + window title 'Curves'; old 'Levels…' removed; Alt+T slot and placement stay. | ✓ |
| Keep 'Levels…' name | Black/white/gamma sliders remain, so the label stays. | |
| 'Curves & Levels' title | Menu action 'Curves…', window title 'Curves & Levels'. | |

**User's choice:** Rename to 'Curves…'

---

## Curve interaction feel

| Option | Description | Selected |
|--------|-------------|----------|
| Arbitrary points | Click to add, drag to move, double-click to delete; endpoints fixed, edge-draggable only. Photoshop convention. | ✓ |
| Fixed anchors only | Fixed editable anchors (shadows/midtones/highlights) that cannot be added or removed. | |
| Arbitrary + presets editable | Arbitrary points; presets are editable starting points. | |

**User's choice:** Arbitrary points

| Option | Description | Selected |
|--------|-------------|----------|
| Linear + a few presets | Linear (reset), S-curve (contrast), Brighten, Darken as one-click editable starting points. | ✓ |
| Linear reset only | Just a Linear reset button; pure manual workflow. | |
| Full preset library | A richer preset library like photo editors ship. | |

**User's choice:** Linear + a few presets

| Option | Description | Selected |
|--------|-------------|----------|
| RGB master only | Single master curve; manga art is mostly linework + flat tones. | |
| Master + per-channel | Master + R/G/B per-channel curves with a channel switcher; enables color grading. | ✓ |

**User's choice:** Master + per-channel
**Notes:** The user opted into the more powerful option — per-channel color grading is wanted.

| Option | Description | Selected |
|--------|-------------|----------|
| Numeric in/out fields | Input/output spinboxes for the selected point (Photoshop convention). | |
| Arrow-key nudge only | Arrow keys nudge the selected point 1 unit (Shift = 10); no numeric fields. | |
| Both | Numeric in/out fields PLUS arrow-key nudge with Tab/Shift+Tab point selection. | ✓ |

**User's choice:** Both
**Notes:** The keyboard-reachability contract is a real acceptance dimension; both paths accepted.

| Option | Description | Selected |
|--------|-------------|----------|
| Show page histogram | Luminance histogram computed once from the detached page image, rendered faintly behind the grid. | ✓ |
| No histogram | Just the grid + diagonal; minimal dialog. | |

**User's choice:** Show page histogram

---

## Claude's Discretion

- **Hint copy wording** (D-11) and **typography scope** (D-12) — the fix areas were not selected for discussion; the planner decides against the UI-SPEC contract and deferral docs.
- **Toolbar mechanism exact wiring** (D-10) — checkable-action duplication vs binding toolbar buttons to the panel's actions.
- **Curve widget implementation** — QPainter widget, curve→LUT math (256-point sampling, per-channel composition), preset math, histogram detail, channel-switcher form, numeric in/out layout.
- **Dialog lifecycle** — the Levels collector+preview-driver contract (Pitfall 9), one IMAGE-stack entry on Apply, restore-before-Apply ordering (b376f8a) must be preserved.

## Deferred Ideas

- **Typesetting styling toolbar (TRAN-02)** — Phase 7 scope (explicit ROADMAP exclusion).
- **Sibling-menu empty-state voice mismatch** ("No recent projects yet." vs "(empty)") — UI-REVIEW Minor, not in Phase 6 scope.
- **Per-channel curve presets / user-saved curves** — not requested; built-in presets only.
- **Curve serialization in `.mas`** — rejected by Phase 5 D-05.
