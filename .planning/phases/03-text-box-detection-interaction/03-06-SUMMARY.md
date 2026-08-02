---
phase: 03-text-box-detection-interaction
plan: 06
subsystem: gui (box-item hit-test geometry)
tags: [gui, box-item, d-06, d-08, hit-test, corner-handle, gap-closure, uat-test-2, pitfall-5]
requirements: [TEXT-03]
status: complete

dependency_graph:
  requires:
    - "03-03: BoxItem + CornerHandle (the component this plan patches — the 8x8 visible handle + corner reposition)"
  provides:
    - "manga_ai_studio.gui.box_item.py — CornerHandle.shape() + CornerHandle.boundingRect() overrides returning an 18px invisible hit rect centred on the corner; the visible 8x8 painted handle is unchanged"
    - "tests/test_gui_boxes.py::test_corner_handle_hit_target_covers_offset_zone — geometry regression reproducing UAT test 2's 'clicking the corner does nothing' symptom via the exact scene.itemAt path the canvas uses"
  affects:
    - "canvas.py mousePressEvent hit-test dispatch (lines 859-864) — UNCHANGED; it already called scene.itemAt in scene coords and now consults the larger shape()"

tech_stack:
  added: []
  patterns:
    - "QGraphicsItem hit-area enlargement via shape() + boundingRect() override (NOT shape() alone — itemAt uses boundingRect as a coarse BSP first-pass filter; both must match)"
    - "boundingRect() governs only the repaint region + hit-test index; paint() draws rect() independently, so enlarging boundingRect does NOT change the painted geometry"

key_files:
  created: []
  modified:
    - manga_ai_studio/gui/box_item.py
    - tests/test_gui_boxes.py

decisions:
  - "03-06: BOTH CornerHandle.shape() AND CornerHandle.boundingRect() must be overridden to enlarge the hit area. The plan's premise that shape() alone suffices is INCOMPLETE: QGraphicsScene.itemAt uses each item's boundingRect() as a coarse first-pass BSP filter and only consults shape() for items that survived — enlarging shape() alone has no effect (probe confirmed itemAt(305,305)->None even with shape() returning an 18px rect). Verified empirically (Cases C vs E in the throwaway probe)."
  - "03-06: Enlarging boundingRect() does NOT change the visible handle. QGraphicsRectItem.paint() draws rect() (the 8x8 set in __init__), NOT boundingRect(). The larger boundingRect only widens the scene's repaint region + hit-test index, so UI-SPEC §12b (visible 8x8 handle) is preserved. Verified: br.rect() reports (0,0,8,8) while boundingRect reports (-5,-5,18,18)."
  - "03-06: _HANDLE_HIT_SIZE = 18 (half = 9px radius > the +-5px probe in the regression test) chosen within the UAT fix_direction's '~16-20px' range. The offset zone (+-5px from the exact corner) — the region UAT test 2 found unhittable — is comfortably covered without swallowing the box body."
  - "03-06: No canvas.py change. The dispatch (canvas.py:859-864) was already correct in scene coords; the defect was purely handle hit-target geometry (D-06/D-08). The fix is localised entirely to CornerHandle."

metrics:
  duration: 5 min
  completed: 2026-07-31
  tasks: 2
  files: 2 (1 modified source + 1 modified test)
  tests-added: 1 (geometry regression)
---

# Phase 03 Plan 06: Corner-Handle Hit-Target Enlargement Summary

Closed UAT test 2 (MAJOR, diagnosed): the corner resize handle was practically unhittable on real artwork. The 8x8 viewport-px `CornerHandle` was centred ON the box corner, so ~half sat outside the box (read as background/pixmap -> no-op) and the inner half overlapped the `BoxItem` body (-> triggered a move, not a resize). After this plan a click within ~9 viewport px of a selected box's corner hits the `CornerHandle` and begins a resize — proven by a geometry regression test that exercises the exact `scene.itemAt` path the canvas uses. The visible handle stays 8x8 (UI-SPEC §12b preserved); only the invisible grab tolerance grew.

## What Was Built

### Task 1 (RED) — Hit-target regression test (`tests/test_gui_boxes.py`)

Added `test_corner_handle_hit_target_covers_offset_zone` (`@pytest.mark.gui`), reproducing the UAT test 2 symptom via the exact `scene.itemAt(scene_pos, QTransform())` path the canvas uses at 1:1 zoom (`canvas.py:860` — `self.transform()` is identity at zoom 1.0):

- Builds a `BoxItem` for `PageBox(box=Box(100,100,300,300), origin=DETECTED)` (BR corner at scene `(300,300)`), selects it so the `CornerHandle` children are visible/hittable (D-08), and grabs `br = item.handles["BR"]`.
- Asserts the painted visible handle is still 8x8 (`br.rect()` width/height == 8) — the fix must NOT change the painted geometry.
- Asserts the exact centre (`itemAt((300,300))`) still returns a `CornerHandle` (no regression on the central pocket).
- Asserts the OFFSET zone — `(305,305)`, `(295,295)`, `(305,295)`, `(295,305)` (each +-5px from the exact corner) — returns a `CornerHandle`. Before the fix these returned `None` (background) / `BoxItem`.
- Asserts the box BODY (`itemAt((200,200))`, ~100px from any corner) returns a `BoxItem` and NOT a `CornerHandle` — bounding the hit enlargement to the corner zone so move/select is not starved (T-03-06-02 mitigation).

RED confirmed before implementation: the offset probe at `(305,305)` returned `None`.

### Task 2 (GREEN) — Enlarged hit shape (`manga_ai_studio/gui/box_item.py`)

- Added module constant `_HANDLE_HIT_SIZE = 18` (within the UAT fix_direction's "~16-20px" range; half = 9px radius > the +-5px probe) and a derived `_HANDLE_HIT_HALF`.
- Added module helpers `_handle_hit_rect()` (returns a `QRectF` centred on local `(4,4)` — the handle's corner point) and `_handle_hit_path()` (a `QPainterPath` wrapping that rect), so both overridden methods share one geometry definition.
- Overrode `CornerHandle.shape()` to return `_handle_hit_path()` and `CornerHandle.boundingRect()` to return `_handle_hit_rect()` (see Deviation 1 for why both are required).
- The inherited `paint()` draws `rect()` (the 8x8 from `__init__`), NOT `boundingRect()` — the VISIBLE handle stays 8x8 (UI-SPEC §12b preserved). Verified: `br.rect()` reports `(0,0,8,8)`; `boundingRect()` reports `(-5,-5,18,18)`.
- `canvas.py` dispatch (lines 859-864) was NOT touched — already correct in scene coords; it now consults the larger `shape()` via `scene.itemAt`.

## TDD Gate Compliance

Both tasks were `tdd="true"`. RED/GREEN cycle with separate commits:

| Task | RED commit (test) | GREEN commit (fix) | Gate |
|------|-------------------|--------------------|------|
| 1 | `a60ba1b` (1 failing — offset probe returned None) | — | RED before GREEN ✓ |
| 2 | — | `df6e1a5` (31/31 passing in test_gui_boxes.py) | GREEN ✓ |

The RED phase confirmed the test genuinely failed before implementation (fail-fast rule held): `AssertionError: offset probe 305.0,305.0 did not hit a CornerHandle (got NoneType)`. The GREEN phase confirmed the minimal `shape()` + `boundingRect()` override made the test pass without touching any other code. No separate REFACTOR gate — the helper extraction (`_handle_hit_rect`/`_handle_hit_path` shared by both methods) was done inline during GREEN.

## Verification

All plan `<verification>` block commands pass:

- `python -m pytest tests/test_gui_boxes.py -q -m gui` → **31 passed** (30 pre-existing component + dispatch + 1 new hit-target regression; no visible-geometry regression — the 8x8 visible handle, z=150, cursors, and visibility gating are unchanged)
- `python -m pytest tests/ -q` → **249 passed** (was 248 baseline + 1 new; no regression to the existing suite)
- Visible-handle sanity check: `br.rect()` reports `(0,0,8,8)` while `boundingRect()` reports `(-5,-5,18,18)` — the painted handle is unchanged (UI-SPEC §12b preserved), only the invisible grab tolerance grew.

The full-suite count moved from 248 (baseline) to 249 because exactly one new test was added (the RED regression); no pre-existing test was modified semantically (only the `QTransform` import was added to the test module header).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] `shape()` override alone does NOT enlarge the hit area — `boundingRect()` must also be overridden**
- **Found during:** Task 2 GREEN phase (first run: the new test STILL failed after implementing only `shape()` — `itemAt((305,305))` returned `None`)
- **Issue:** The plan's action said: "Mechanism: `QGraphicsScene.itemAt` uses each item's `shape()` (a QPainterPath) for collision — NOT `boundingRect`. The default `QGraphicsRectItem.shape()` returns the 8x8 rect plus the pen width. Overriding `shape()` to return a larger QPainterPath rect enlarges ONLY the hit area." This premise is INCOMPLETE for this flag combination. `QGraphicsScene.itemAt` uses the scene's BSP index keyed on each item's `boundingRect()` as a COARSE first-pass filter, and only consults `shape()` for items whose `boundingRect()` already contains the probe point. Enlarging `shape()` alone has no effect — the probe point is filtered out by the coarse pass before the fine `shape()` test ever runs.
- **Empirical proof (throwaway probes, since deleted):**
  - Case C (`ItemIgnoresTransformations` + `shape()` returning 18px on local (4,4), `boundingRect()` stays 8x8): `itemAt((305,305))` → `None`. FAILS.
  - Case E (both `shape()` AND `boundingRect()` returning 18px): `itemAt((305,305))` → the handle. WORKS.
  - Case F (no `ItemIgnoresTransformations`, `shape()` override only): also FAILS — so the limitation is not specific to the `ItemIgnoresTransformations` flag; it is fundamental to `QGraphicsScene.itemAt`'s two-pass hit-test.
  - Case D call-counting: confirmed `shape()` IS called for the surviving candidate at `(300,300)` (the exact centre, inside the default 8x8 `boundingRect`), but never called for `(305,305)` (outside the 8x8 `boundingRect`, filtered out by the coarse pass).
- **Fix:** Override BOTH `CornerHandle.shape()` AND `CornerHandle.boundingRect()` to return the same 18px rect (`_handle_hit_rect()` / `_handle_hit_path()` share the geometry so they cannot drift apart). Crucially, enlarging `boundingRect()` does NOT change the visible handle: `QGraphicsRectItem.paint()` draws `rect()` (the 8x8 from `__init__`), NOT `boundingRect()` — the larger `boundingRect` only widens the scene's repaint region + hit-test index. Verified post-fix: `br.rect()` reports `(0,0,8,8)` (painted) while `boundingRect()` reports `(-5,-5,18,18)` (hit area). The UI-SPEC §12b "visible handle stays 8x8" contract is preserved.
- **Files modified:** manga_ai_studio/gui/box_item.py
- **Commit:** df6e1a5

This deviation is documented as a Rule 3 (blocking issue — the documented technique prevented completing the task). It is NOT a Rule 4 architectural change: it is the same Qt Graphics View technique the plan prescribed (enlarge the invisible hit area without changing the painted handle), just with the additional `boundingRect()` override the plan's mechanism description omitted. No new boundary, no structural change — the fix is localised to two methods on `CornerHandle`.

## Known Stubs

None. The hit-target geometry fix is complete end-to-end: a click within ~9 viewport px of a selected box's corner now hits the `CornerHandle` and begins a resize (proven by the regression test exercising the exact `scene.itemAt` path). No downstream seam is left unwired.

## Threat Flags

None. The threat register in the plan is fully mitigated in-plan:

- **T-03-06-01** (Tampering — input-routing integrity): the `shape()`/`boundingRect()` override makes the resize affordance reliably reachable, restoring the D-06/D-08 input contract. No new boundary crossed; the mouse-event path is unchanged.
- **T-03-06-02** (DoS — enlarged hit shape swallowing box-body clicks): Task 1's test explicitly asserts the box BODY (`itemAt((200,200))`) still returns a `BoxItem`, bounding the hit enlargement to the corner zone so move/select is not starved.

No new network/auth/file-access surface introduced (single-user offline desktop app; the fix is purely local hit-test geometry on an existing item).

## Self-Check: PASSED

Modified files present:
- FOUND: manga_ai_studio/gui/box_item.py (shape() + boundingRect() overrides + _HANDLE_HIT_SIZE constant + _handle_hit_rect/_handle_hit_path helpers)
- FOUND: tests/test_gui_boxes.py (test_corner_handle_hit_target_covers_offset_zone + QTransform import)

Commits exist:
- FOUND: a60ba1b (test RED Task 1)
- FOUND: df6e1a5 (fix GREEN Task 2)
