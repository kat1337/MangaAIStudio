---
phase: 08-masker-selective-inpaint
plan: 10
subsystem: gui-core
tags: [pyside6, canvas, mask-planes, batch, gap-closure, selective-inpaint]

# Dependency graph
requires:
  - phase: 08 (08-01..08-09)
    provides: the Phase 8 detection-mask seam (derive_page_mask_state, compose_auto_binary, three-plane canvas, batch detect wiring)
provides:
  - "Correct composite mask for LaMa in reachable flows: moved-box recompose, no-wipe threshold guard, plane-clearing consumption (CR-01/03/04)"
  - "Hand-stroke survival on detect-mode batch restore + user-box preservation on batch detect (CR-02/WR-01)"
  - "Lossless close after detect-mode batch (WR-02) + WR-03 zero-boxes guard on the live re-derive"
  - "New GUI regression suite tests/test_gui_gap_closure.py (8 probes) + extended headless suites"
affects: [verify-work, 09-ui-rework, ship]

# Actuals (#2632) — chars/4 over the realized diff (40816 diff chars)
actuals:
  tokens: 10204
  tasks: 3
  commits: 7

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "snapshot-as-geometry: every recompose consumer reads canvas.boxes_snapshot() (lives rects + mask/std_dev/inpaint_override) over live pagebox.box (birth geometry)"
    - "sibling guard symmetry: no-fit guard + zero-boxes guard occupy the SAME relative position in every recompose slot"
    - "signal-silent consumption: consume_mask_display() clears planes without mask_modified (CR-16 2-stack contract)"

key-files:
  created:
    - tests/test_gui_gap_closure.py
  modified:
    - manga_ai_studio/gui/main_window.py
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/core/detection_boxes.py
    - manga_ai_studio/core/batch_runner.py
    - tests/test_core/test_detection_boxes.py
    - tests/test_core/test_batch_runner.py

key-decisions:
  - "Every recompose consumer composes from canvas.boxes_snapshot() (never writes .box back onto live pageboxes — Box identity safety for _on_ocr_finished id(it.pagebox.box) routing)"
  - "consume_mask_display() clears ALL THREE planes signal-silently at both consumption sites (CR-04), replacing the display-only fill"
  - "Detect-mode batch restore uses set_auto_binary (auto plane only) instead of set_planes with explicitly-empty manual/erase (CR-02)"
  - "merge_page_boxes_for_detect() is the headless D-03 merge: USER boxes survive batch detect, DETECTED replaced; page.boxes = merged (WR-01)"
  - "Detect/detect_and_clean batch completion dirties every touched ImageFile when ok > 0 (WR-02); clean-only unchanged"

patterns-established:
  - "Recompose consumers never read live pagebox.box — geometry materialization is exclusively boxes_snapshot() at call-time"
  - "Consumption is signal-silent: a consume helper + the 2-stack undo contract (no mask_modified emission)"

requirements-completed: [MASK-01, MASK-02, MASK-03, MASK-05]

# Coverage (#1602) — one deliverable per verified defect
coverage:
  - id: D1
    description: "CR-01 — after Detect + a box move, the next threshold/override recompose uses the box's CURRENT (moved) position, never the birth origin"
    requirement: MASK-02
    verification:
      - kind: unit
        ref: "tests/test_gui_gap_closure.py#test_recompose_after_move_uses_live_geometry"
        status: pass
    human_judgment: false
  - id: D2
    description: "CR-03 — a std-dev threshold tweak after a geometry op (all per-box masks invalidated) leaves the auto plane untouched — no silent whole-plane wipe"
    requirement: MASK-02
    verification:
      - kind: unit
        ref: "tests/test_gui_gap_closure.py#test_threshold_tweak_after_invalidation_does_not_wipe_auto_plane"
        status: pass
    human_judgment: false
  - id: D3
    description: "WR-03 — the mode-ON live re-derive gained the zero-boxes guard so a radius/dilation nudge on a zero-box page cannot wipe a mode-OFF full-heatmap layer after a mode switch"
    verification:
      - kind: other
        ref: "source assertion: main_window.py:_rederive_auto_layer 'if not boxes: return' before derive_page_mask_state"
        status: pass
    human_judgment: true
    rationale: "Guard is source-asserted per the plan (not probe-covered) — the acceptance criterion greps for the guard placement; no test drives a zero-box mode-switch wipe fixture."
  - id: D4
    description: "CR-04 — inpaint/batch-clean consumption clears manual, erase AND auto planes signal-silently so the consumed overlay cannot resurrect on the next recompose and a re-run cannot re-process the cleaned region"
    requirement: MASK-02
    verification:
      - kind: unit
        ref: "tests/test_gui_gap_closure.py#test_consume_mask_display_clears_planes_and_no_resurrection"
        status: pass
      - kind: unit
        ref: "tests/test_gui_gap_closure.py#test_batch_clean_refresh_clears_planes"
        status: pass
    human_judgment: false
  - id: D5
    description: "CR-02 — a detect-mode batch refresh replaces ONLY the auto plane; the current page's live manual/erase planes (hand strokes + erase ledger) survive the restore"
    requirement: MASK-03
    verification:
      - kind: unit
        ref: "tests/test_gui_gap_closure.py#test_detect_batch_refresh_preserves_manual_and_erase"
        status: pass
    human_judgment: false
  - id: D6
    description: "WR-01 — batch detect applies the D-03 merge: persisted USER boxes survive with state intact and every box on the merged set gets a refreshed mask/std_dev"
    requirement: MASK-03
    verification:
      - kind: unit
        ref: "tests/test_core/test_detection_boxes.py#test_merge_page_boxes_keeps_user_replaces_detected"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_batch_runner.py#test_batch_detect_preserves_user_boxes"
        status: pass
    human_judgment: false
  - id: D7
    description: "WR-02 — a detect-mode batch completion marks every touched page dirty (Close prompts save); clean-only mode stays clean"
    requirement: MASK-05
    verification:
      - kind: unit
        ref: "tests/test_gui_gap_closure.py#test_detect_batch_marks_pages_dirty"
        status: pass
    human_judgment: false

# Metrics
duration: 23min
completed: 2026-08-18
status: complete
---

# Phase 08 Plan 10: Gap-Closure Fixes (CR-01..CR-04, WR-01..WR-03) Summary

**All six verified Phase 8 defects closed with per-defect RED→GREEN probe evidence: recompose consumers now read live snapshot geometry (moved-box masks land where the box sits), the threshold slot gained the no-fit guard, consumption clears all three planes signal-silently, detect-batch refresh keeps hand strokes, the batch worker merges (D-03) instead of overwriting user boxes, and detect batches mark pages dirty for lossless close.**

## Performance

- **Duration:** 23 min
- **Started:** 2026-08-18T22:21:26Z
- **Completed:** 2026-08-18T22:44:29Z
- **Tasks:** 3
- **Files modified:** 7 (4 source, 3 test)
- **Full suite result:** 877 passed, 0 failed (baseline 869 + 8 new probes)

## Accomplishments

- **CR-01 (root cause of SC-2/SC-3 failures):** all three recompose consumers (`_on_std_dev_threshold_changed`, `_rederive_auto_layer` mode-ON, `_recompose_boxes_auto_plane`) now compose from `canvas.boxes_snapshot()` (materializes CURRENT rects + carries `mask`/`std_dev`/`inpaint_override`) instead of live `pagebox.box` (birth geometry after a move/resize). After Detect → move → threshold change, the auto mask stays at the moved rect (25,15,49,44); the mode-ON re-derive writes fresh fits back onto the LIVE pageboxes so borders render from current data. No `.box` write anywhere → `_on_ocr_finished`'s `id(it.pagebox.box)` routing stays safe.
- **CR-03:** the threshold slot now carries the byte-identical no-fit guard of its sibling `_recompose_boxes_auto_plane` (same relative position: zero-boxes → no-fit → image → compose); a threshold tweak after a geometry op can no longer compose an all-mask-None empty binary and wipe the auto plane.
- **WR-03 (bonus):** the mode-ON re-derive gained the zero-boxes guard immediately after the snapshot read and before `derive_page_mask_state` — a dilation/radius nudge on a zero-box page can no longer wipe a previously mode-OFF full-heatmap auto layer after a mode switch (source-asserted per plan).
- **CR-04:** new `canvas.consume_mask_display()` clears ALL THREE planes (manual + erase via transparent fill, `_auto_bin = None`) signal-silently (never emits `mask_modified` — no mask-undo corruption, CR-16 2-stack contract) and recomposes to a transparent composite; both consumption sites (inpaint finish, batch-clean refresh) now call it — the consumed overlay cannot resurrect and a re-run cannot re-process the cleaned region.
- **CR-02:** the detect-mode batch restore replaces only the AUTO plane (`set_auto_binary` from the unpacked `imf.auto_mask`) — the current page's live manual/erase planes (hand strokes + the erase ledger, which the dispatch flush persists only as the flat composite) survive the restore, honoring the D-01 "hand strokes always survive re-detection" contract.
- **WR-01:** headless `merge_page_boxes_for_detect()` applies the interactive D-03 replace-detected-keep-user rule in the batch worker — USER boxes (with payload/style/override/geometry) survive `batch_detect`, the stale DETECTED box is replaced, and the derivation runs over the MERGED set (`page.boxes = merged`).
- **WR-02:** `_on_batch_finished` marks every touched `ImageFile.dirty` when a detect/detect_and_clean batch completes with `ok > 0` and refreshes the title — Close prompts save instead of silently dropping the detected boxes; clean-only mode unchanged.

## Task Commits

Each task was committed atomically (RED probe commit → GREEN fix commit):

1. **Task 1: CR-01 + CR-03 + WR-03 — recompose consumers read live geometry** -
   `ec66804` (test) / `808e479` (feat)
2. **Task 2: CR-04 + CR-02 — consume_mask_display + detect-batch auto-only restore** -
   `d5e7056` (test) / `d47078f` (feat)
3. **Task 3: WR-01 + WR-02 — batch D-03 merge + detect-batch dirty marking** -
   `097505a` (test) / `ed710b1` (feat)

**Plan metadata:** (final docs commit below)

## Files Created/Modified

- `tests/test_gui_gap_closure.py` (created) - the new GUI regression suite: 8 probes (moved-box recompose, no-fit wipe guard, consume clears planes + no resurrection, detect-batch preserves manual/erase, clean refresh clears planes, detect-batch marks dirty)
- `manga_ai_studio/gui/main_window.py` - three recompose consumers read `boxes_snapshot()`; threshold slot no-fit guard; re-derive zero-boxes guard + live write-back; two consumption sites call `consume_mask_display()`; detect-batch restore via `set_auto_binary`; `_on_batch_finished` dirty loop
- `manga_ai_studio/gui/canvas.py` - new `consume_mask_display()`
- `manga_ai_studio/core/detection_boxes.py` - new `merge_page_boxes_for_detect()`
- `manga_ai_studio/core/batch_runner.py` - detect branch derives over the merged list, persists `page.boxes = merged`
- `tests/test_core/test_detection_boxes.py` - `test_merge_page_boxes_keeps_user_replaces_detected`
- `tests/test_core/test_batch_runner.py` - `test_batch_detect_preserves_user_boxes`

## Probe RED→GREEN Evidence

| Defect | Probe | Pre-fix failure (RED signature) | Post-fix |
|--------|-------|--------------------------------|----------|
| CR-01 | `test_recompose_after_move_uses_live_geometry` | content bbox jumped back to (5,5,29,34) after one threshold change (08-VERIFICATION.md probe reproduced) | content stays at moved rect (25,15,49,44) |
| CR-03 | `test_threshold_tweak_after_invalidation_does_not_wipe_auto_plane` | auto plane wiped to all-zero after one tweak (08-VERIFICATION.md probe reproduced) | plane byte-unchanged |
| CR-04 | `test_consume_mask_display_clears_planes_and_no_resurrection` | AttributeError (method absent) | all planes cleared, no `mask_modified`, no resurrection on recompose |
| CR-04 (batch) | `test_batch_clean_refresh_clears_planes` | clean-path consume left planes holding content | three planes cleared |
| CR-02 | `test_detect_batch_refresh_preserves_manual_and_erase` | seeded manual/erase wiped by set_planes(empty, empty, ...) | manual/erase preserved, auto == batch result |
| WR-01 | `test_merge_page_boxes_keeps_user_replaces_detected` | ImportError (helper absent) | USER box kept identity + override, stale DETECTED replaced |
| WR-01 | `test_batch_detect_preserves_user_boxes` | user box absent from page.boxes (page.boxes = boxes) | user box survives (override intact) + refreshed mask/std_dev on merged set |
| WR-02 | `test_detect_batch_marks_pages_dirty` | dirty stays False after detect batch | every page dirty + title `*`; clean mode stays clean |

## Decisions Made

- Snapshot-as-geometry is the sole geometry fiction with `boxes_snapshot()` and never writing `.box` back (Box identity safety for OCR routing, per the plan's locked D-02/D-12/D-14 decisions).
- Consumption lives on the canvas as a signal-silent `consume_mask_display()` (not `clear_mask()`, which would emit `mask_modified` and corrupt the mask-undo stack).
- The detect-batch restore used `set_auto_binary` (auto-only replace) exactly like the interactive detection path; the flat-mask legacy restore above was untouched.

## Deviations from Plan

None - plan executed exactly as written. All six headline defects plus the WR-03 bonus guard closed per the plan's locked decisions; the acceptance-criterion grep string for the threshold no-fit guard is satisfied as the byte-identical sibling shape (`if not any(pb.mask is not None for pb in current_boxes):` + a following `return` line, the same shape as `_recompose_boxes_auto_plane`), not the one-line transcription.

## Issues Encountered

- **Test-fixture bbox semantics (probe authoring, not a product defect):** the fitted mask for a full-page-content binary fills the box, but `np.nonzero` reports the max content index as `(y2-1, x2-1)` under the vendored EXCLUSIVE-max `Box` semantics. The probes encode this with a `_box_content_bbox(x1,y1,x2,y2) -> (y1, x1, y2-1, x2-1)` helper so the assertions match the box coordinates in the 08-VERIFICATION.md probe table ((25,15,49,44) == np bbox (25,15,48,43)).
- Full-suite warnings (3) are pre-existing HuggingFace deprecation warnings, unrelated to this plan's changes.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All 4 Critical + 2 Warning verified defects are closed with per-defect RED→GREEN evidence; no 08-01..08-09 behavior regressed (877/877 pass).
- Legacy open ledger item (unchanged, out of this plan's scope): deleting a detected box does not recompose (08-VERIFICATION.md deferred-items; same recompose-trigger family as gap 1, logged earlier commit adbd44e).
- Ready for Phase 8 verification re-run and subsequent phases (09-ui-rework).

## Self-Check: PASSED

- All 7 created/modified files exist on disk (verified with `Test-Path`).
- All 6 task commits present in `git log` (ec66804, 808e479, d5e7056, d47078f, 097505a, ed710b1).
- Full suite: 877 passed, 0 failed (baseline 869 + 8 new probes).

---

*Phase: 08-masker-selective-inpaint*
*Completed: 2026-08-18*
