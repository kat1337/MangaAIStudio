---
phase: 08-masker-selective-inpaint
plan: 02
subsystem: gui
tags: [mask-planes, recompose, erase-ledger, undo, persistence, d11-seam, dispatch, pytest-qt]

requires:
  - phase: 08-masker-selective-inpaint
    provides: plan 08-01 — PageBox.inpaint_override/inpaint_state, MaskerConfig.mask_dilation_radius, geometry-op field-carry policy
  - phase: 03-text-box-detection-interaction
    provides: BoxItem/CornerHandle box layer + mousePressEvent dispatch, boxes_modified before-state convention
  - phase: 05-project-persistence-image-ops-export
    provides: D-11 on_page_selected seam, HistoryManager three-stack engine, .mas ImageFile slots
provides:
  - core/mask_planes.py — pack_binary/unpack_binary (T-08-02 length-validated) + MaskPlanesSnapshot (.copy()-detached)
  - EditorCanvas three-plane model (_mask_manual/_mask_erase/_auto_bin) with recompose_mask = (manual | auto) & ~erase
  - set_mask redefined to replace the AUTO plane only (strokes + erase ledger survive re-detection, UI-SPEC A10)
  - Eraser dual-write onto the erase ledger (Pitfall 13-11) — erased false positives never resurrect across re-dilates
  - Plane-aware MASK undo (before-state MaskPlanesSnapshot pushes, apply_undo_mask restores planes)
  - D-11 seam plane persistence (ImageFile packed slots; on_page_selected/_snapshot_current_page flush + restore)
  - MASK-06 paint-under-boxes dispatch carve-out (PAINT_TOOLS + Alt-gated box branch)
affects: [08-masker-selective-inpaint, 09-ui-rework]

tech-stack:
  added: []
  patterns:
    - "Three-plane mask composition ((manual | auto) & ~erase) with the composite kept as the sole display/LaMa/persistence surface — every existing get_mask consumer unchanged"
    - "Dual-write strokes: display composite mutated live for feedback, active plane (manual/ledger) painted with normal composition, recompose only at stroke-commit"
    - "Packed-bit plane persistence (~H*W/8 bytes, numpy-only slots) keeping the worker path Qt-free (Pitfall 13-12)"

key-files:
  created:
    - manga_ai_studio/core/mask_planes.py
    - tests/test_gui_mask_planes.py
  modified:
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/main_window.py
    - manga_ai_studio/core/image_file.py
    - manga_ai_studio/core/history_manager.py
    - tests/test_box_persistence.py

key-decisions:
  - "set_mask keeps Phase-1 any-size acceptance: a non-page-sized incoming heatmap is fitted onto the page grid top-left (the anchoring the Phase 1 pixmap displayed); set_auto_binary stays strict (page-dims mismatch = ValueError)"
  - "Geometry ops (rotate/crop/resize) collapse plane provenance into the AUTO plane: write-back rebuilds planes from the transformed composite via set_planes(None, None, new_bin) — display pixel-identical to Phase 5, consistent with 08-01's mask-invalidation stance; the undo record pushes the pre-op planes snapshot"
  - "apply_undo_mask hard-rejects non-MaskPlanesSnapshot values (TypeError) — the MASK stack value type widened; the three unified-pop/redo/status tests that pushed bare QImages were re-based to push planes_snapshot()"
  - "The 03-08 clean baseline generalized: first-stroke before-state = transparent manual/erase + the CURRENT auto packed (strokes never touch auto, so hook-time auto == pre-stroke auto)"
  - "Empty planes pack to None on the D-11 seam (a never-touched page stores nothing) and has_mask_planes() switches Step 4 between set_planes restore and the legacy composite->auto fallback (documented provenance loss for pre-Phase-8 pages)"
  - "Alt+Shift+click under paint tools follows RESEARCH §7.2 pseudo-code: select+move only, no Shift-toggle (the UI-SPEC §39 Shift row — Shift+click paints)"

patterns-established:
  - "recompose_mask is the single composite rebuild point: signal-silent, never called from mouseMoveEvent (Pitfall 13-14) — only at stroke-commit, plane changes, and restores"
  - "Plane-count-aware page-switch hygiene: any same-dims numpy image load must wipe or restore planes explicitly or the outgoing page's strokes bleed (the D-11 seam owns it; the dims-change reseed in _set_image_from_numpy is the backstop)"

requirements-completed: [MASK-01, MASK-02, MASK-05, MASK-06]

coverage:
  - id: D1
    description: "core/mask_planes.py pack/unpack round-trip with T-08-02 mismatched-length ValueError + MaskPlanesSnapshot.copy() detachment"
    requirement: MASK-05
    verification:
      - kind: unit
        ref: "tests/test_gui_mask_planes.py#test_pack_binary_round_trips_through_unpack_binary"
        status: pass
      - kind: unit
        ref: "tests/test_gui_mask_planes.py#test_unpack_binary_rejects_mismatched_length"
        status: pass
      - kind: unit
        ref: "tests/test_gui_mask_planes.py#test_snapshot_copy_detaches_planes"
        status: pass
    human_judgment: false
  - id: D2
    description: "Canvas three-plane model: composite == (manual | auto) & ~erase, the erase-ledger survives re-dilate (the phase's load-bearing invariant), set_mask replaces the auto plane only, clear_mask empties all planes with one emission, recompose is signal-silent, strokes dual-write manual/ledger planes"
    requirement: MASK-05
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_composite_equals_manual_or_auto_minus_erase"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_erase_ledger_survives_redilate"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_set_mask_replaces_auto_plane_only"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_clear_mask_empties_all_planes_and_emits_once"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_recompose_mask_does_not_emit"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_brush_stroke_dual_writes_manual_plane"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_eraser_stroke_dual_writes_ledger_plane"
        status: pass
    human_judgment: false
  - id: D3
    description: "Plane-aware MASK undo: undo removes a stroke's manual contribution but keeps auto, redo restores; first stroke seeds a clean baseline with auto untouched; undo never re-pushes; erase-stroke undo returns erased pixels; clear_mask undo restores all three planes"
    requirement: MASK-05
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_undo_removes_stroke_keeps_auto_and_redo_restores"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_first_stroke_seeds_clean_baseline_auto_untouched"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_undo_does_not_repush_planes"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_undo_erase_stroke_returns_erased_pixels"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_undo_clear_mask_restores_all_three_planes"
        status: pass
    human_judgment: false
  - id: D4
    description: "D-11 per-page plane persistence: page A planes round-trip to B and back via on_page_selected with an identical composite; packed ImageFile slots are detached copies (boundary-copy semantics on the plane path)"
    requirement: MASK-05
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_planes_round_trip_across_page_switch"
        status: pass
      - kind: automated_ui
        ref: "tests/test_box_persistence.py#test_mask_persistence_uses_copy"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_project.py (save/reopen mask round-trip suite, 59-test verify run green)"
        status: pass
    human_judgment: false
  - id: D5
    description: "MASK-06 paint-under-boxes dispatch carve-out: Brush presses on box bodies AND handles paint (no selection, no resize); Alt+click/drag selects/moves/creates; Alt+handle keeps the sole-selection gate; Crop and Move/Pan behave exactly as today; Shift+click under Brush paints; double-click opens the inline editor under any tool"
    requirement: MASK-06
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_brush_press_on_box_body_paints_not_selects"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_brush_press_on_corner_handle_paints_not_resizes"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_shift_click_on_box_under_brush_paints"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_alt_click_on_box_selects_under_brush"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_alt_drag_on_box_moves_it_under_brush"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_alt_drag_empty_canvas_creates_box_under_brush"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_alt_handle_resizes_only_when_sole_selection"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_crop_tool_press_on_box_still_selects"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_move_tool_press_on_box_behaves_as_today"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_mask_planes.py#test_double_click_box_under_brush_opens_inline_editor"
        status: pass
    human_judgment: false

duration: 6h 1min
completed: 2026-08-17
status: complete
---

# Phase 08 Plan 02: Canvas Three-Plane Mask Model Summary

**Option-B three-plane canvas mask ((manual | auto) & ~erase) with the erase-ledger invariant, plane-aware undo/persistence through the D-11 seam, and the Alt-gated MASK-06 paint-under-boxes dispatch — 763 tests green**

## Performance

- **Duration:** 6h 1min wall clock (includes a provider usage-limit interruption mid-Task-2; work resumed and completed from the surviving tree)
- **Started:** 2026-08-16T18:03:25Z
- **Completed:** 2026-08-17T00:04:08Z
- **Tasks:** 3 (TDD: 3 RED + 3 GREEN commits)
- **Files modified:** 7 (2 created, 5 modified)

## Accomplishments
- The canvas mask is now composed from three planes — a derived auto binary, a manual-stroke QImage, and an erase-ledger QImage — with `_mask` kept as the displayed/LaMa/persisted composite, so `get_mask`/`has_mask`/`has_mask_content`/`mask_to_numpy_binary(canvas.get_mask())` consumers (including the untouched LaMa dispatch) are unchanged
- The erase-ledger invariant holds: erasing auto content is permanent across re-dilations — a differently-grown auto plane still misses the erased pixel (the phase's load-bearing regression per RESEARCH §10)
- `set_mask` now replaces ONLY the auto plane (UI-SPEC A10): re-detection keeps hand strokes and the erase ledger; non-page-sized heatmaps still load (top-left fitted)
- MASK undo is plane-aware: each stroke pushes a before-state `MaskPlanesSnapshot`, `apply_undo_mask` restores planes + recomposes with no re-push; the 03-08 clean baseline generalizes to "transparent manual/erase + current auto"
- Planes survive page switches and the save-side flush via packed numpy slots on `ImageFile` (Qt-free worker path), with the legacy composite->auto fallback for pre-Phase-8 pages; `.mas` container write intentionally left to 08-07 Task 3 (the plan that owns the load side)
- MASK-06: paint tools paint under box bodies AND handles; Alt gates box interaction (select/move/create, sole-selection resize gate); Crop, Move/Pan, double-click, and `_box_item_at` are byte-identical to before

## Task Commits

Each task was committed atomically (TDD: RED test commit → GREEN feat commit):

1. **Task 1: Canvas three-plane mask model + recompose + eraser dual-write** - `808ed46` (test) + `e893095` (feat)
2. **Task 2: Plane-aware MASK undo + D-11 per-page persistence** - `0151b41` (test) + `42ab4f0` (feat)
3. **Task 3: MASK-06 paint-under-boxes dispatch carve-out** - `a546fa5` (test) + `46035e9` (feat)

**Plan metadata:** final docs commit (below)

## Files Created/Modified
- `manga_ai_studio/core/mask_planes.py` - NEW: pack_binary/unpack_binary (bit-packed, length-validated) + MaskPlanesSnapshot dataclass (Qt-free at runtime)
- `manga_ai_studio/gui/canvas.py` - three plane attributes, recompose_mask/set_auto_binary/planes_snapshot/set_planes, set_mask auto-plane routing, clear_mask plane wipe, dual-write stroke path, PAINT_TOOLS + Alt-gated box branch
- `manga_ai_studio/gui/main_window.py` - _pre_stroke_planes + _clean_plane_seed + snapshot-pushing _on_mask_modified, _current_undo_state planes, D-11 plane flush/restore (Step 1/Step 3/Step 4, _snapshot_current_page, _display_page_state), geometry pre-planes push + set_planes write-back
- `manga_ai_studio/core/image_file.py` - raw_detected_mask/auto_mask/mask_manual/mask_erase packed slots + has_mask_planes()
- `manga_ai_studio/core/history_manager.py` - MASK stack value-type widening documented (no behavioral change)
- `tests/test_gui_mask_planes.py` - NEW: 27 tests across the three tasks (3 unit + 24 gui)
- `tests/test_box_persistence.py` - three unified-pop/redo/status tests re-based to push plane snapshots

## Decisions Made
- Geometry ops collapse plane provenance into the auto plane (display pixel-identical; undo restores the pre-op planes exactly) — consistent with 08-01's invalidate-don't-transform stance for per-box masks
- `apply_undo_mask` raises TypeError on a bare QImage — the type widening is enforced at the apply boundary rather than silently mis-restoring
- Empty planes pack to `None` on the seam (never-touched pages store nothing; `has_mask_planes()` gates the restore-vs-legacy branch)
- Alt+Shift+click under paint tools does NOT Shift-toggle (RESEARCH §7.2 pseudo-code; the UI-SPEC §39 Shift row paints) — selection toggling requires Move/Pan
- `ImageFile.raw_detected_mask` exists as the D-08 retention slot but is populated by plan 08-03's detection seam, not this plan

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Geometry write-back + pre-op undo record made plane-aware**
- **Found during:** Task 1 (full-suite run; rotate/resize/crop mask assertions failed)
- **Issue:** The plan redefines `set_mask` to replace only the auto plane, but `_apply_geometry_op` wrote the transformed composite back via `set_mask` and pushed the flat `pre_mask` QImage onto the MASK stack — stale same-dims manual/erase planes corrupted the recompose (a rotate-180's stale ledger erased the wrong pixels), and the flat push would hit the redefined `apply_undo_mask`
- **Fix:** Write-back rebuilds ALL planes from the transformed composite via `canvas.set_planes(None, None, new_mask_bin)` (provenance collapses into auto; `set_planes` derives the size from the incoming auto binary so changed dims rebuild correctly); the undo record pushes `canvas.planes_snapshot()` captured pre-op
- **Files modified:** manga_ai_studio/gui/canvas.py (set_planes size derivation), manga_ai_studio/gui/main_window.py (_apply_geometry_op)
- **Verification:** tests/test_gui_image_dialogs.py + tests/test_gui_crop_tool.py green; full suite 763 passed
- **Committed in:** e893095 (write-back), 42ab4f0 (pre-op planes push)

**2. [Rule 1 - Bug] Same-dims numpy page-switch plane bleed**
- **Found during:** Task 2 (analysis of the seam; pre-empted before it could surface as a live bug)
- **Issue:** `set_image_from_numpy` (the project-open / Step-3 display path) never re-seeds planes on a same-dims page switch, and `set_mask` replaces only auto — the outgoing page's manual/erase planes would bleed into the incoming page's composite
- **Fix:** `_set_image_from_numpy` re-seeds planes when the page dims change; Step 3's empty-mask branch, Step 4's legacy branch, and `_display_page_state` explicitly wipe planes (`set_planes(None, None, None)`) before routing the composite
- **Files modified:** manga_ai_studio/gui/canvas.py, manga_ai_studio/gui/main_window.py
- **Verification:** test_planes_round_trip_across_page_switch's no-bleed assertion; test_gui_project.py suite green
- **Committed in:** e893095 (canvas reseed), 42ab4f0 (seam wipes)

**3. [Rule 2 - Missing Critical] set_mask keeps Phase-1 any-size acceptance**
- **Found during:** Task 1 (three test_box_persistence tests pass an 8x8 mask onto a 64x64 page)
- **Issue:** The strict page-dims guard in `set_auto_binary` rejected the historical any-size masks Phase 1 accepted
- **Fix:** `set_mask` fits the thresholded binary onto the page grid top-left (the anchoring the Phase 1 pixmap displayed at the scene origin); the strict ValueError stays in `set_auto_binary` (the derived-plane contract)
- **Files modified:** manga_ai_studio/gui/canvas.py
- **Verification:** test_box_persistence.py green (753/763 full suite)
- **Committed in:** e893095

---

**Total deviations:** 3 auto-fixed (2 bugs, 1 missing critical)
**Impact on plan:** All three are correctness requirements of the plane model itself (the plan's own set_mask/undo redefinitions made the old callers inconsistent). No scope creep — fixes stayed inside the plan's files_modified set plus the prescribed re-basing.

## TDD Gate Compliance

All three tasks are `tdd="true"`; git log shows the RED→GREEN sequence for each:
- Task 1: `test(08-02)` 808ed46 → `feat(08-02)` e893095
- Task 2: `test(08-02)` 0151b41 → `feat(08-02)` 42ab4f0
- Task 3: `test(08-02)` a546fa5 → `feat(08-02)` 46035e9

RED gates failed for the right reasons (missing module; flat-QImage undo semantics; box branch intercepting paint presses). Task 2's `test_undo_does_not_repush_planes` and Task 3's four "unchanged behavior" locks (Alt+click, crop, move, double-click) passed at RED — they are regression locks for behavior the carve-out must preserve, the same pattern as 08-01 Task 3's invalidation half.

## Issues Encountered
- Two test-harness bugs in my own new tests were fixed before their GREEN commits: the page-switch round-trip test needed the real navigation sequence (`file_table.select_path` before `on_page_selected` — the outgoing-index rule), and the `_release` event helper must pass `LeftButton` as `button` (the repo's QMouseEvent release shape; `NoButton`-as-button never reaches the commit guards — confirmed by probe against the passing test_gui_boxes analog)
- A provider usage limit killed the session mid-Task-2; the uncommitted Task-2 work was verified against the surviving tree and completed without rework

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Every surface 08-03+ needs is in place: `set_auto_binary`/`recompose_mask` for the detection seam, `ImageFile.raw_detected_mask` for D-08 retention, `planes_snapshot`/`set_planes` for the seam, `PAINT_TOOLS` for dispatch consumers
- 08-03 owns populating the auto plane from the vendored masker machinery (heatmap ∩ boxes ∪ overrides, dilated) — today `set_mask` routes the full heatmap there, which is the correct Phase-8-compatible interim
- 08-07 Task 3 owns the `.mas` container write for the four plane keys (in-memory slots already flushed)
- No blockers.

## Self-Check: PASSED

All 7 created/modified files exist on disk; all 6 task commits found in git log (`git log --grep="08-02"` returns 6: 3 test + 3 feat). Full suite re-verified green before SUMMARY (763 passed / 0 failed; baseline 747 at plan start + 27 new tests − 11 superseded expectations re-based). Done-criteria source assertions re-run and passing (plane symbols present; set_mask routes through set_auto_binary; _end_paint recomposes before the emit; _pre_stroke_planes pushed; four ImageFile slots declared; PAINT_TOOLS contains exactly the four paint tools; crop branch/mouseDoubleClickEvent/_box_item_at untouched per git diff).

---
*Phase: 08-masker-selective-inpaint*
*Completed: 2026-08-17*
