---
phase: 03-text-box-detection-interaction
plan: 03
subsystem: gui (box-interaction layer)
tags: [gui, box-item, d-05, d-06, d-07, d-08, d-09, d-12, d-13, qt-graphics-view, pitfall-3, pitfall-5, pitfall-6, tdd]
requirements: [TEXT-03]
status: complete

dependency_graph:
  requires:
    - "03-01: PageBox + Box.as_tuple_xywh (BoxItem composes PageBox for QRectF + origin/payload)"
    - "03-02: HistoryManager.push_boxes_state (the BOXES push hook canvas.boxes_snapshot() feeds in plan 03-05)"
  provides:
    - "manga_ai_studio.gui.box_item.BoxItem(QGraphicsRectItem) + CornerHandle(QGraphicsRectItem) — the component layer"
    - "EditorCanvas.box_layer + boxes_modified Signal + boxes_snapshot()/set_boxes()/set_box_overlay_visible()/has_boxes()/box_count()/box_origin_counts() — the canvas box API"
    - "EditorCanvas box hit-test dispatch (CornerHandle resize / BoxItem select+move / Alt+create / deselect+fall-through) — the D-07 no-new-tool contract"
  affects:
    - "03-04: detection seam builds BoxItems via set_boxes(detected_pageboxes=...)"
    - "03-05: persistence restore calls set_boxes; BOXES undo consumes boxes_snapshot(); status bar reads box_origin_counts()"

tech_stack:
  added: []
  patterns:
    - "QGraphicsRectItem subclass composes (not subclasses) a @frozen Box data model (D-14)"
    - "itemChange(ItemSelectedChange) drives pen/brush/handle sync instead of Qt's default dashed selection outline"
    - "CornerHandle: ItemIgnoresTransformations + zoom_changed subscription for constant 8x8 viewport-px grab target"
    - "parent-less scene items at z=100 (NOT children of a QGraphicsItemGroup) — parenting under a group blocks Qt selection (Rule 1 fix)"
    - "hit-test dispatch slotted between pan and mask-tool branches with fall-through (D-07 — no 6th tool)"
    - "fresh int-Box materialization at every QRectF<->Box boundary (Pitfall 6); snapshot detachment at call-time (Pitfall 3)"

key_files:
  created:
    - manga_ai_studio/gui/box_item.py
    - tests/test_gui_boxes.py
  modified:
    - manga_ai_studio/gui/canvas.py

decisions:
  - "03-03: BoxItem + corner handles are PARENT-LESS scene items (not children of box_layer) — parenting under a QGraphicsItemGroup blocks Qt setSelected on the child; UI-SPEC §11 explicitly allows the 'parent-less item set' form. box_layer stays as the logical-visibility sentinel the dispatch checks (box_layer.isVisible())."
  - "03-03: itemChange(ItemSelectedChange) applies the origin pen/brush + handle visibility directly against the prospective `value` (the flag has not flipped yet) via _apply_look_for/_sync_handles_for_state helpers — isSelected() reports the OLD state during the change."
  - "03-03: resize clamps during the drag (not just on release) — the opposite corner is held fixed and the moving edge is pinned at anchor +/- MIN_BOX_SIZE if the cursor crosses past it, so the box never inverts/collapses mid-drag; the 8x8 min is re-applied on release."
  - "03-03: Task 3 checkpoint auto-approved under auto_advance=true + human_verify_mode=end-of-phase (visual feel + colour legibility is deferred to the end-of-phase human-verify gate, not a per-plan gate; not a package-legitimacy blocking-human gate)."

metrics:
  duration: 10 min
  completed: 2026-07-28
  tasks: 3
  files: 3 (1 created source + 1 created test + 1 modified source)
  tests-added: 30 (15 component + 15 dispatch)
---

# Phase 03 Plan 03: BoxItem + Canvas Box Layer + Hit-Test Dispatch Summary

Built the TEXT-03 UI core: the `BoxItem` Qt Graphics View component (D-05) with four corner resize handles (D-06) and the `EditorCanvas` box layer + hit-test dispatch (D-07) wired with create/move/resize/delete (D-08/D-12/D-13). After this plan a user can Alt+drag to create a user box, select/move/resize/delete it, and toggle the layer — the full TEXT-03 correction workflow minus detection (plan 03-04). Hidden boxes do not intercept mask-paint clicks (Pitfall 5).

## What Was Built

### Task 1 — `BoxItem` + `CornerHandle` component (`manga_ai_studio/gui/box_item.py`)

- **`CornerHandle(QGraphicsRectItem)`** (UI-SPEC §12b): one of four corner resize handles (TL/TR/BL/BR), a child of its parent `BoxItem`. 8x8 viewport px via `ItemIgnoresTransformations` (constant grab target at any zoom), z=150 (above the box border). Solid origin-hue fill + 1px `#0b0b0e` matte outline. Cursor `SizeFDiagCursor` (TL/BR) / `SizeBDiagCursor` (TR/BL). `reposition(parent_rect)` re-places the handle at its corner in scene coords (offset -4,-4 to centre the 8x8 square on the corner point).
- **`BoxItem(QGraphicsRectItem)`** (UI-SPEC §12a, D-05): composes a `PageBox` (D-14 — does NOT subclass the vendored `@frozen Box`). Constructs `QRectF` from `Box.as_tuple_xywh`. z=100. Flags `ItemIsSelectable | ItemIsMovable | ItemSendsGeometryChanges`. `SizeAllCursor` over the body (move affordance). `itemChange(ItemSelectedChange)` drives the look directly against the prospective value: 2px unselected / 3px selected origin hue (green `#5fd068` detected / amber `#f5a623` user, D-09) + `NoBrush` unselected / `rgba(hue, 0.12)` tint selected (alpha 31). This suppresses Qt's default dashed selection outline — the origin-coloured solid border is the sole selection signal plus the handles + tint.
- **`BoxItem.current_box()`**: materializes a fresh `Box(int(x), int(y), int(r.right()), int(r.bottom()))` from the live `rect()` (Pitfall 6 — int at every `Box`<->`QRectF` boundary; the on-canvas rect stays float-precise for smooth dragging, snapshots/persistence materialize ints).
- **`origin_hue(origin)`** module helper: returns the hex hue for an origin (single source for component + canvas create-preview).

### Task 2 — `EditorCanvas` box layer + dispatch (`manga_ai_studio/gui/canvas.py`)

- **Constructor additions**: `box_layer` (`QGraphicsItemGroup` z=100 — used as the logical-visibility sentinel), `empty_box_hint` (`QGraphicsTextItem` z=850, the §12f copy in 12px muted `#9a9aa2`), `_box_items: list[BoxItem]` membership, `boxes_modified = Signal()` (mirrors `mask_modified`), and the interaction-state flags (`_resizing_box`, `_resize_corner`, `_resize_start_rect`, `_box_drag_anchor`, `_moving_box`, `_move_anchor_box_pos`, `_creating_box`, `_create_anchor`). `zoom_changed` connected to `_on_zoom_changed_reposition_handles`.
- **Public API**: `set_boxes(user_pageboxes, detected_pageboxes)` (rebuilds the layer — plan 03-04 seam), `set_box_overlay_visible(bool)` (`setVisible` + `setEnabled` belt-and-suspenders — Pitfall 5), `has_boxes()`, `box_count()`, `box_origin_counts() -> (detected, user)`, `boxes_snapshot() -> list[PageBox]` (fresh int-Box materialization per item, detached — Pitfall 3).
- **`mousePressEvent` dispatch (D-07 — the load-bearing change)**: AFTER the pan branch and BEFORE the mask-tool branch, the box hit-test runs only when `box_layer.isVisible()` and button is Left: `itemAt(scene_pos, transform())` → `CornerHandle` (begin resize) / `BoxItem` (select + begin move) / `Alt`+empty (begin create) / empty-no-Alt (deselect + FALL THROUGH to the mask-tool branch so mask painting still works with the layer visible). The fall-through is critical (UI-SPEC §12d step 2 last bullet).
- **`mouseMoveEvent`**: resize advances (drag corner, clamp opposite corner to keep >= 8x8 during the drag) + amber-dashed create preview on `preview_item` + move delta (reposition box by scene-delta + `_sync_handles`). **`mouseReleaseEvent`**: resize commit (clamp final rect to >= 8x8, `_sync_handles`, emit `boxes_modified`) + create commit (>= 8x8 builds a user PageBox + selects + emits; else no-op) + move commit (emit `boxes_modified`) + preview pen restored to cyan.
- **`keyPressEvent`**: `Delete`/`Backspace` on the selected box removes it silently (D-12 — no dialog; the BOXES undo in plan 03-05 recovers it); `Esc` deselects. Both consume the event only when a box is the target, placed BEFORE the `event.ignore()` fall-through (CR-09 intact — undo shortcuts still reach MainWindow).
- **Private helpers**: `_begin_resize`, `_select_and_begin_move`, `_begin_create_box`, `_advance_resize`, `_commit_resize`, `_advance_create`, `_commit_create`, `_deselect_box`, `_selected_box`, `_remove_box`, `_refresh_empty_box_hint`, `_restore_preview_pen`, `_on_zoom_changed_reposition_handles`.

### Wave 0 test file (`tests/test_gui_boxes.py`)

30 `@pytest.mark.gui` tests (pytest-qt, offscreen-capable) mirroring the `test_gui_canvas.py` header (`pytest.importorskip("PySide6")`, `qtbot`, scene→viewport coord mapping via `mapFromScene`):
- **Component (15)**: detected/user pen hues, rect-from-xywh, z=100, 2px/3px selection, NoBrush/tint fill, 4 handles TL/TR/BL/BR, 8x8 + ItemIgnoresTransformations, z=150, diagonal cursors, handles-visible-only-on-selected (D-08), `current_box()` int materialization + detachment (Pitfall 6), composes-not-subclasses Box (D-14).
- **Dispatch (15)**: box_layer + hint presence/z-order, empty-hint visibility, select-single (D-08), move, resize corner clamp (D-06), delete silent + boxes_modified (D-12), Alt+drag create (D-13) + too-small no-op, amber dashed create-preview (§12e), hidden-layer no-hit → mask fall-through (Pitfall 5) + setEnabled, boxes_snapshot detached (Pitfall 3) + returns PageBox (D-15 seam), box_origin_counts, Esc deselect, mask-paint regression with layer visible.

## TDD Gate Compliance

Both implementation tasks were `tdd="true"`. RED/GREEN cycle with separate commits:

| Task | RED commit (test) | GREEN commit (feat) | Gate |
|------|-------------------|---------------------|------|
| 1 | `bb30350` (15 failing — module missing) | `3464e92` (15/15 passing) | RED before GREEN ✓ |
| 2 | `43d6d69` (15 failing — canvas has no box_layer) | `9a540d5` (30/30 passing) | RED before GREEN ✓ |

Both RED phases confirmed the tests genuinely failed before implementation (fail-fast rule held — no test passed unexpectedly during RED). The Task 1 RED failed at import (module missing); the Task 2 RED failed 15/15 with `AttributeError: 'EditorCanvas' object has no attribute 'box_layer'` (and one assertion for the amber-preview-on-cyan). Both GREEN phases confirmed minimal implementation made all tests pass. No separate REFACTOR gate — the helper extraction (`_apply_look_for`/`_sync_handles_for_state`) was done inline during GREEN.

## Verification

All plan `<verification>` block commands pass:

- `python -m pytest tests/test_gui_boxes.py -q -m gui` → **30 passed** (component + dispatch green)
- `python -m pytest tests/test_gui_canvas.py -q` → **28 passed** (no Phase 1 canvas regression — mask painting, pan, zoom, CR-08/CR-09 intact)
- `python -m pytest tests/ -q` → **221 passed** (full suite green at the plan boundary; plans 03-04/05 not yet merged)
- Checkpoint automated verify (`test_gui_boxes.py + test_gui_canvas.py`) → **58 passed**

All `<acceptance_criteria>` for both tasks met: `class BoxItem(QGraphicsRectItem)` + `class CornerHandle(QGraphicsRectItem)` present; `ItemIgnoresTransformations` (5 occurrences); both origin hues (`#5fd068`/`#f5a623`, 6 lines); `setZValue(100)` + handle z=150 (`_HANDLE_Z = 150`); `SizeFDiagCursor`/`SizeBDiagCursor` (6); `def current_box` == 1; `class BoxItem(Box)` anti-pattern == 0; `box_layer` + `QGraphicsItemGroup` + `empty_box_hint` + `boxes_modified = Signal`; 4 public API defs; both isinstance hit-test branches; `AltModifier`; `Key_Delete` + `Key_Escape`; `setEnabled` (Pitfall 5); amber create-preview `245, 166, 35`. The dispatch ordering verified by line inspection: pan branch (line 832) precedes box hit-test (843) precedes mask-tool branch (867) — the load-bearing D-07 order.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] BoxItem + handles must be PARENT-LESS scene items, not children of the QGraphicsItemGroup**
- **Found during:** Task 2 GREEN phase (first run: 4 dispatch tests failed — `setSelected(True)` did not stick on boxes)
- **Issue:** The plan's action (and the UI-SPEC §11 z-order stack) described the box layer as a `QGraphicsItemGroup` holding the `BoxItem` children (`addToGroup`). Parenting a selectable item under a `QGraphicsItemGroup` **blocks Qt selection on the child** — `item.setSelected(True)` is a no-op on a group child (verified: a parent-less BoxItem selected True; the same BoxItem as a group child selected False). This broke select/move/delete/esc (all depend on the selected flag) and the hit-test-then-select path.
- **Fix:** `BoxItem`s are now PARENT-LESS top-level scene items at z=100 (the UI-SPEC §11 explicitly allows the "QGraphicsItemGroup (or parent-less item set) at z=100" form — the parenthetical is the sanctioned alternative). `box_layer` stays as a `QGraphicsItemGroup` object but serves only as the **logical-visibility sentinel** the dispatch checks (`box_layer.isVisible()`) + the object the empty hint's z-order is anchored against. `set_boxes`/`set_box_overlay_visible`/`_remove_box`/`_commit_create` use `scene.addItem`/`removeItem` (not `addToGroup`/`removeFromGroup`) and toggle per-item `setVisible`/`setEnabled` to mirror the layer state. This preserves every UI-SPEC contract (z-order, toggle, Pitfall 5 disable) while making selection work.
- **Files modified:** manga_ai_studio/gui/canvas.py
- **Commit:** 9a540d5

**2. [Rule 2 - Completeness] Resize clamps during the drag, not only on release**
- **Found during:** Task 2 GREEN phase
- **Issue:** The plan's action said "min 8x8 scene px enforced on release (D-06 clamp, not cancel)". Enforcing only on release lets the box invert (the dragged corner crossing past the anchor) during the drag, producing a visually jarring flip before the release clamp fixes it. A mid-drag clamp keeps the box stable.
- **Fix:** `_advance_resize` holds the opposite corner fixed and pins the moving edge at `anchor +/- MIN_BOX_SIZE` if the cursor crosses past the anchor + min, so the box never inverts or collapses below 8x8 mid-drag. The final 8x8 clamp is re-applied on release in `_commit_resize` (unchanged from the plan). Behaviour matches D-06 (clamp, not cancel) and is more robust than release-only clamping.
- **Files modified:** manga_ai_studio/gui/canvas.py
- **Commit:** 9a540d5

### Checkpoint Handling

**Task 3 `checkpoint:human-verify` — auto-approved under auto_advance + end-of-phase verify mode.**
- The checkpoint verifies tactile feel + colour legibility on real manga artwork (8 manual checks). Per `config.json`: `auto_advance: true` AND `human_verify_mode: "end-of-phase"`. The per-plan visual checkpoint is auto-approved (it is NOT a package-legitimacy `gate="blocking-human"` — it is a `gate="blocking"` visual/feel gate), and the actual manual verification is deferred to the end-of-phase human-verify gate. The automated portion (`test_gui_boxes.py + test_gui_canvas.py` = 58 tests) passes. The end-of-phase checkpoint (after plans 03-04/05) will run the 8 manual checks against the full integrated app (with detection wired in).

## Known Stubs

None. The full box-interaction loop is implemented end-to-end: create (Alt+drag), select (single, D-08), move, resize (corner + 8x8 clamp, D-06), delete (silent, D-12), Esc deselect, layer toggle (Pitfall 5). The only thing not wired in this plan is **detection output** (plan 03-04's `set_boxes(detected_pageboxes=...)`) and **persistence + undo UI** (plan 03-05's restore path + Ctrl+Z collapse) — both are explicit downstream seams, not stubs. The `boxes_snapshot()` API is ready for plan 03-02's `push_boxes_state` and plan 03-05's restore.

## Threat Flags

None. The threat register (T-03-04 Tampering on `boxes_snapshot`, T-03-05 DoS on resize/create) is fully mitigated in-plan:
- **T-03-04**: `boxes_snapshot()` materializes a fresh `PageBox(box=item.current_box(), ...)` per item at call-time — no live-item aliasing (Pitfall 3). Regression guard: `test_boxes_snapshot_detached`.
- **T-03-05**: min 8x8 scene px enforced on create-release and resize-release + during the drag (Deviation 2). Regression guards: `test_alt_drag_too_small_is_noop`, `test_resize_corner_clamps_to_min`.

No new network/auth/file-access surface introduced (single-user offline desktop app; box input is trusted user mouse/keyboard via Alt+drag).

## Self-Check: PASSED

Created files exist:
- FOUND: manga_ai_studio/gui/box_item.py
- FOUND: tests/test_gui_boxes.py

Modified files present:
- FOUND: manga_ai_studio/gui/canvas.py (box layer + dispatch + 460+ lines added)

Commits exist:
- FOUND: bb30350 (test RED Task 1)
- FOUND: 3464e92 (feat GREEN Task 1)
- FOUND: 43d6d69 (test RED Task 2)
- FOUND: 9a540d5 (feat GREEN Task 2)
