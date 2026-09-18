---
phase: 08-masker-selective-inpaint
plan: 07
subsystem: masking
tags: [detection-seam, pyside6, mask-planes, masker, selective-inpaint, live-controls, mas-persistence]

# Dependency graph
requires:
  - phase: 08-masker-selective-inpaint
    provides: derive_page_mask_state / compose_auto_binary / dilate_auto_mask / build_detected_pageboxes (08-03), three-plane canvas set_auto_binary/set_planes (08-02), PageBox.inpaint_state (08-01), BoxItem.set_inpaint_state (08-06), live dilation/std-dev slots (08-05), 08-04 plane .mas container entries
provides:
  - reordered detection seam: D-04 gate BEFORE any mask/box mutation (Cancel leaves the canvas byte-identical)
  - box-constrained composite (content can never exit a box, D-02/MASK-05) + pre-dilation raw retained in BOTH modes (D-08)
  - live dilation-radius re-derive + std-dev-threshold recomposition (D-08/D-12, no model calls)
  - move/resize/create refit against the retained raw (D-12 recompute-on-release)
  - .mas save-side plane entries (raw/auto/manual/erase) + load-side plane/per-box restore without re-detect
  - predictive border-state refresh wired on the §37 trigger set + per-box state carried through BOXES undo/save/re-detect
  - Inpaint tooltip + per-box completion copy (UI-SPEC surface 7)
affects: [08-08 (inpaint-override commit), 08-09 (batch loop consumer of build_detected_pageboxes), end-of-phase verification/UAT]

# Actuals (#2632) — chars/4 over the realized diff (estimateTokens scale)
actuals:
  tokens: 15700
  tasks: 3
  commits: 6

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Seam consumes the 08-03 extracted core (build_detected_pageboxes / derive_page_mask_state / compose_auto_binary / dilate_auto_mask) — one implementation for interactive and batch"
    - "Gate-before-mutation: the D-04 replace confirmation hoisted to the handler, before any set_auto_binary/set_boxes call"
    - "Live control slots recompute/recompose on the main thread from retained data (no worker, no model) and never push history (non-undoable preferences)"
    - "Recompute-on-commit (never per-mousemove) with geometry-diff guard, suppress-restore skip, and no-raw/no-stale-dims no-ops (T-08-13)"
    - "boxes_snapshot field-carry for the per-box D-15 seam (mask/std_dev/inpaint_override) — the fourth field-drop site 08-01 fixed"
    - "Plane-slot threading: ImageFile packed slots -> save-loop binary keys -> 08-04 parse keys, unpacked via mask_planes.unpack_binary"

key-files:
  created: []
  modified:
    - manga_ai_studio/gui/main_window.py
    - manga_ai_studio/gui/canvas.py
    - tests/test_gui_detection_boxes.py
    - tests/test_box_persistence.py

key-decisions:
  - "boxes_snapshot field-carry (mask/std_dev/inpaint_override) landed in Task 1 GREEN — the re-detect keep-user-state behavior requires it before Task 2's formal home (dependency-forward)"
  - "refresh_box_inpaint_states defined at Task 1 (its step 6 calls it); Task 3's wiring + slots build on that definition"
  - "Mode-ON composed auto saturates to the fitted box, so count-based radius grow/shrink is only deterministic in mode OFF — the live re-dilate test uses mode OFF for monotonicity and a spy+reference-equality for the mode-ON re-derive"
  - "_page_plane_keys helper is the single save-loop writer of the four plane container entries"
  - "_display_page_state restores planes at the embedded-image dims (a fresh project-open has no composite _mask yet)"
  - "A10: the stale 'undo is available via Ctrl+Z' sentence in the Replace Mask gate is deliberately dropped"

requirements-completed: [MASK-01, MASK-02, MASK-05]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "Detection->mask seam reorder: D-04 gate before mutation, box-constrained composite, raw retention in both modes, non-undoable baseline + explicit dirty"
    requirement: MASK-02
    verification:
      - kind: unit
        ref: "tests/test_gui_detection_boxes.py#test_mode_on_composite_contains_only_in_box_content"
        status: pass
      - kind: unit
        ref: "tests/test_gui_detection_boxes.py#test_mode_on_cancel_aborts_before_any_mutation"
        status: pass
      - kind: unit
        ref: "tests/test_gui_detection_boxes.py#test_mode_off_full_heatmap_no_boxes_raw_retained"
        status: pass
      - kind: unit
        ref: "tests/test_gui_detection_boxes.py#test_detection_pushes_no_history_and_marks_dirty"
        status: pass
      - kind: unit
        ref: "tests/test_gui_detection_boxes.py#test_mode_on_stores_pre_dilation_raw_binary"
        status: pass
    human_judgment: false
  - id: D2
    description: "build_detected_boxes consumes the 08-03 core; move/resize/create commit re-fits against the retained raw"
    requirement: MASK-05
    verification:
      - kind: unit
        ref: "tests/test_gui_detection_boxes.py#test_move_commit_refits_box_and_border"
        status: pass
    human_judgment: false
  - id: D3
    description: "Live dilation-radius re-derive and std-dev threshold recomposition (pure, no model; no-raw silent no-op)"
    requirement: MASK-01
    verification:
      - kind: unit
        ref: "tests/test_gui_detection_boxes.py#test_dilation_live_redilate_grows_shrinks_keeps_strokes"
        status: pass
      - kind: unit
        ref: "tests/test_gui_detection_boxes.py#test_dilation_live_redilate_mode_on_rederives"
        status: pass
      - kind: unit
        ref: "tests/test_gui_detection_boxes.py#test_threshold_live_regate_flips_border_and_composite"
        status: pass
      - kind: unit
        ref: "tests/test_gui_detection_boxes.py#test_dilation_no_raw_is_silent_noop"
        status: pass
    human_judgment: false
  - id: D4
    description: ".mas plane save/restore wiring through the real Save Project path — planes + per-box fields restore without a detect, post-load radius re-dilates from the retained raw"
    verification:
      - kind: unit
        ref: "tests/test_gui_detection_boxes.py#test_mas_save_roundtrip_restores_planes_without_detect"
        status: pass
    human_judgment: false
  - id: D5
    description: "Inpaint tooltip copy + per-box completion copy (n box(es) inpainted, m skipped omitted when 0, exact flash with no boxes)"
    verification:
      - kind: unit
        ref: "tests/test_gui_detection_boxes.py#test_inpaint_completion_copy_no_boxes"
        status: pass
      - kind: unit
        ref: "tests/test_gui_detection_boxes.py#test_inpaint_completion_copy_box_counts"
        status: pass
      - kind: unit
        ref: "tests/test_gui_detection_boxes.py#test_inpaint_completion_copy_zero_skipped"
        status: pass
    human_judgment: false
  - id: D6
    description: "Predictive border-state refresh + per-box state carry (snapshot carry through BOXES undo and re-detect keep-user-state)"
    verification:
      - kind: unit
        ref: "tests/test_gui_detection_boxes.py#test_refresh_box_inpaint_states_iterates_and_derives"
        status: pass
      - kind: unit
        ref: "tests/test_gui_detection_boxes.py#test_boxes_undo_restores_per_box_mask_and_std_dev"
        status: pass
      - kind: unit
        ref: "tests/test_gui_detection_boxes.py#test_redetect_replaces_detected_keeps_user_state"
        status: pass
    human_judgment: false

# Metrics
duration: 1h 6m
completed: 2026-08-17
status: complete
---

# Phase 8 Plan 7: Detection→Mask Seam Rework Summary

**The detection seam reorder + constrained derivation: D-04 gates before any mutation, in-box-only auto content (D-02/MASK-05), raw retention for live re-dilate (D-08), move-commit refits, and the .mas save/restore plane wiring — all on the interactive path (batch lands in 08-09).**

## Performance

- **Duration:** 1h 6m
- **Started:** 2026-08-17T22:47:56Z
- **Completed:** 2026-08-17T23:53:54Z
- **Tasks:** 3 (2 TDD tasks: RED+GREEN each; 1 standard)
- **Files modified:** 4

## Accomplishments

- **Reorder trap fixed (D-04):** the replace-detected confirmation now runs BEFORE any mask or box mutation — a cancelled re-detect leaves the canvas byte-identical (the old seam composited the full mask before the gate ran). Regression-locked by `test_mode_on_cancel_aborts_before_any_mutation`.
- **Box-constrained composite (D-02/MASK-05):** mode ON lands `derive_page_mask_state(...).auto_binary` — heatmap content outside every box never enters the mask (dilate-then-intersect from 08-03). Mode OFF keeps the full heatmap dilated by the profile radius (D-03). The pre-dilation raw binary is packed onto `ImageFile.raw_detected_mask` in BOTH modes (D-08).
- **Detection is a non-undoable baseline** (no MASK/BOXES pushes) **and marks the session dirty explicitly** (recompose is signal-silent).
- **Live controls (D-08/D-12):** the dilation-radius slot re-derives the current page from the retained raw (mode ON: re-fit, no model; mode OFF: `dilate_auto_mask`); the std-dev threshold slot recomposes purely from stored fits under the new gate (std_dev never re-fits) + refreshes borders.
- **Recompute-on-release (D-12):** box move/resize/create commit re-fits the changed boxes against the retained raw, rewrites the auto plane, and refreshes borders — the geometry-diff guard keeps Inspector/OCR/text/style commits from refitting (T-08-13).
- **`.mas` plane round-trip:** the save loop is now the sole writer of the four plane container entries (raw/auto/manual/erase unpacked from the ImageFile packed slots); the load side threads the parsed planes into the slots so borders + the auto plane restore and a post-load radius change re-dilates — all with NO detect call (verified through the REAL Save Project path).
- **Per-box state carried:** `boxes_snapshot` now forwards mask/std_dev/inpaint_override — BOXES undo, page-switch, and the D-03 re-detect user-box merge preserve a user's override + fit data.
- **Copy (UI-SPEC):** Replace Mask gate reworded per A10 (stale undo sentence dropped); Inpaint action tooltip teaches the D-01 origin rule; the completion flash reports `n box(es) inpainted · m skipped` per surface 7.
- **Full pinned-interpreter suite green: 847 passed, 0 failed** (the regression net the plan requires; baseline 838).

## Task Commits

Each task was committed atomically:

1. **Task 1: `_on_detection_finished` reorder + constrained derivation** (TDD)
   - `45e89d0` `test(08-07): add failing detection-seam reorder tests`
   - `89d81cf` `feat(08-07): reorder detection seam - gate first, constrained derivation`
2. **Task 2: `_build_detected_boxes` consumes the core; refit triggers** (standard)
   - `89a9d39` `feat(08-07): build-detected-boxes via 08-03 core + refit on move-commit`
3. **Task 3: refresh + live radius/threshold slots + .mas save/restore + inpaint copy** (TDD)
   - `360721b` `test(08-07): add failing live-control + restore + copy tests`
   - `379a425` `feat(08-07): live dilation/threshold slots + .mas plane round-trip + inpaint copy`

**Plan metadata:** (attached to the next docs commit)

## Files Created/Modified

- `manga_ai_studio/gui/main_window.py` - `_on_detection_finished` rework (D-04 first, constrained derivation, raw retention, dirty), `_build_detected_boxes` consuming `build_detected_pageboxes`, `refresh_box_inpaint_states`, `_refit_changed_boxes`, `_rederive_auto_layer`, live `_on_dilation_changed` / `_on_std_dev_threshold_changed`, `_page_plane_keys` save-loop plane writer, `_build_image_file_from_parsed` plane-slot threading, `_display_page_state` compose-from-boxes + refresh, `on_page_selected` border refresh, `_confirm_replace_mask` A10 copy, Inpaint tooltip + completion copy. Unused `Box`/`PageBox`/`textblock_to_box` imports removed.
- `manga_ai_studio/gui/canvas.py` - `boxes_snapshot` now carries `mask` (copy-detached) / `std_dev` / `inpaint_override`.
- `tests/test_gui_detection_boxes.py` - +~710 lines: harness data-model registration, six seam cases, move-commit refit, per-box undo carry, live slots, no-raw no-op, .mas round-trip via the real save path, completion-copy cases.
- `tests/test_box_persistence.py` - `test_orphaned_strings_fixed` re-based to the A10 copy (the 03-05-era assertion demanded the now-dropped undo sentence).

## Decisions Made

- **Dependency-forward (snapshot carry + refresh):** the `boxes_snapshot` field-carry and `refresh_box_inpaint_states` definition both landed in Task 1 GREEN because Task 1's own behavior (re-detect keep-user-state; refresh call) requires them — Task 2/3 formalize and extend.
- **Feedback path for the live controls:** the mode-ON composed auto saturates to the fitted box (vendored `pick_best_mask` growth) so count-based radius monotonicity is not observable there — the deterministic grow/shrink contract is tested on the mode-OFF dilate path, and the mode-ON path is pinned by a spy + reference-equality on the fresh derive.
- **Plane restore dims** in `_display_page_state` come from the embedded image, not `canvas.get_mask()` (a fresh project-open has re-seeded the planes but the composite `_mask` is still None).
- **A10 copy:** the stale undo sentence is gone (detection is a non-undoable baseline; re-detect replaces only the auto plane).
- **Delete-box refit is out of the plan's trigger set** (move/resize/create only) — the deleted box's auto content lingers until the next §37 trigger; logged to deferred-items.md.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test stale after A10] `test_orphaned_strings_fixed` asserted the old Replace Mask gate copy**
- **Found during:** Task 1 GREEN (rollback guard when the full suite ran after Task 1)
- **Issue:** The 03-05-era test required the literal "undo is available via Ctrl+Z" in `_confirm_replace_mask` — the sentence A10 (mandated by the plan) deliberately drops.
- **Fix:** Re-based the replace-mask assertions to the A10 body ("Your hand-painted strokes are kept.") + assert the stale sentence is ABSENT; also collapsed the A10 body into a contiguous string literal so `inspect.getsource` matches it.
- **Files modified:** tests/test_box_persistence.py, manga_ai_studio/gui/main_window.py
- **Verification:** pinned-interpreter pytest on test_box_persistence.py green; full suite green.
- **Committed in:** 89a9d39 (Task 2 commit; the reword itself was Task 1).

**2. [Rule 1 - Bug] `_refit_changed_boxes` compared stale pagebox geometry**
- **Found during:** Task 2 implementation (probe before writing the refit test)
- **Issue:** A moved box's `pagebox.box` stays birth-geometry; the live rect only materializes via `BoxItem.current_box()`. The first refit implementation compared the stale attribute so no geometry change was ever detected, and derived against the old geometry.
- **Fix:** `_refit_changed_boxes` now snapshots the CURRENT geometry via `boxes_snapshot()` for both the tuple diff and the `derive_page_mask_state` input, then writes the fresh fits back onto the live pageboxes (same iteration order).
- **Files modified:** manga_ai_studio/gui/main_window.py
- **Verification:** test_move_commit_refits_box_and_border (std 0.0 -> 35.3, solid -> dashed).
- **Committed in:** 89a9d39.

**3. [Rule 1 - Bug exposed by the new load path] `_display_page_state` crashed on fresh project-open with plane data**
- **Found during:** Task 3 GREEN — the new save-side plane entries made the planes-restore branch reachable for real project loads, where `canvas.get_mask()` is still None (set_image_from_numpy re-seeds the planes but not the composite `_mask`)
- **Fix:** dimension the plane unpacking from the embedded image (`imf.current_image.shape[:2]`) instead of the composite QImage.
- **Files modified:** manga_ai_studio/gui/main_window.py
- **Verification:** full pinned-interpreter suite green (test_open_project_restores_session restored).
- **Committed in:** 379a425.

**4. [Rule 3 - Blocking] `_page_plane_keys` invoked without `self.`**
- **Found during:** Task 3 GREEN (NameError in `_save_project`)
- **Fix:** `**self._page_plane_keys(...)` in the `build_page_entries` call.
- **Files modified:** manga_ai_studio/gui/main_window.py
- **Committed in:** 379a425.

**5. [Rule 1 - Test fixture] duck-typed `_blk` payload crashed the .mas serializer**
- **Found during:** Task 3 RED->GREEN (the .mas round-trip test's save step)
- **Issue:** `pagebox_to_json` reads `payload.lines/vertical/language/font_size/text/translation`; the `SimpleNamespace(xyxy=...)` fake lacks them. Real detection uses real `TextBlock`s — a fixture gap, not production.
- **Fix:** the .mas round-trip test drives a real `TextBlock([5,5,35,35])` as the detected payload.
- **Files modified:** tests/test_gui_detection_boxes.py
- **Committed in:** 379a425.

**6. [Rule 1 - Test fixture] mode-ON composed auto is radius-insensitive (fit saturation)**
- **Found during:** Task 3 RED->GREEN (dilation live-re-dilate + .mas post-load radius asserts)
- **Issue:** the vendored per-box fit saturates the composed mask to the box, so count/bbox monotonicity in radius is not observable for the boxed path.
- **Fix:** grow/shrink asserted on the deterministic mode-OFF `dilate_auto_mask` path; the mode-ON path pinned by a `_rederive_auto_layer` spy + reference-equality against the fresh derive at the emitted radius; the .mas post-load re-dilate asserted by flipping to mode OFF.
- **Files modified:** tests/test_gui_detection_boxes.py
- **Committed in:** 379a425.

---

**Total deviations:** 6 auto-fixed (4 Rule 1, 1 Rule 3 in production code/root-caused, plus 2 test/fixture adjustments under Rule 1 discipline).
**Impact on plan:** All fixes were necessary for correctness or to satisfy the mandated behavior/copy. No scope creep; two of them (`.lines` payload, fit saturation) adjusted test fixtures to honest production shapes.

## Issues Encountered

- The `loguru "I/O operation on closed file"` teardown noise is a pre-existing pytest/loguru teardown artifact, observed in this run too — unrelated to the changes (also present in the baseline run).
- The plan's source assertions (gate order, A10 body) were verified by the new tests + `test_orphaned_strings_fixed`; the `_page_plane_keys` write path is verified end-to-end by the real-save .mas round-trip test.

## Known Stubs

None — no stub patterns introduced. The plan's goal (interactive detection seam behavior) is fully wired; no data source is left unwired.

## User Setup Required

None — no external service configuration required.

## Self-Check

Verified after writing this summary:
- `08-07-SUMMARY.md` exists on disk ✓
- All 5 per-task commits present in `git log --oneline --all`: `45e89d0`, `89d81cf`, `89a9d39`, `360721b`, `379a425` ✓
- Full pinned-interpreter suite: 847 passed / 0 failed ✓

## Self-Check: PASSED

## Next Phase Readiness

- The interactive detection seam is complete; `refresh_box_inpaint_states` is already called at detection finish / threshold / radius / move-commit / page-restore, with an explicit extension point for 08-08's override commit signal.
- The save loop now writes the 08-04 plane entries; batch (08-09) can consume `build_detected_pageboxes` + the same derivation core.
- Logged to `deferred-items.md`: deleting a detected box does not yet recompose the auto plane (out of the plan's trigger set).
- End-of-phase UAT should visually confirm the border-state rendering and the mode-ON live-dilation responsiveness on real page images.

---
*Phase: 08-masker-selective-inpaint*
*Completed: 2026-08-17*
