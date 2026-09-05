---
phase: quick-260904-wn0
plan: 01
status: complete
subsystem: core-detection/inpaint-compose
tags: [bugfix, inpaint, fill, compose, stale-fit-data, tdd]
requires:
  - PageBox._has_auto_mask_content (single derivation site, box_model.py)
  - project_io.py mask_stale save-side invariant (quick-260825-u9q) as precedent
provides:
  - Fit-freshness contract in _has_auto_mask_content (mask.size == (box_w, box_h))
  - Resize-stale boxes contribute nothing to fill specs, fill binary, LaMa auto binary, or inpaint_count
affects:
  - gui C (inpaint) and F (fill boxes) flows
  - batch clean parity (core/batch_runner.py calls the same compose functions — inherits the fix unchanged)
tech-stack:
  added: []
  patterns:
    - single-predicate gating (compose functions consume PageBox._has_auto_mask_content cross-module within manga_ai_studio.core)
key-files:
  created: []
  modified:
    - manga_ai_studio/core/box_model.py
    - manga_ai_studio/core/detection_boxes.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_core/test_detection_boxes.py
    - tests/test_gui/test_inpaint_flow.py
    - tests/test_core/test_box_model.py
decisions:
  - "Skip, do not substitute: a resize-stale box contributes NOTHING (gate_skipped semantics, matching its own post-save/reload state) — no rect-LaMa substitution, no forced_fill/override semantic changes, no UI vocabulary changes."
  - "Pure MOVE (dims unchanged) keeps today's fill-follows-box behavior — the freshness check is dims-based only, regression-guarded at compose level and worker level."
  - "Predicate swap is the whole production change: one method in box_model.py + four call-site swaps (3 compose functions + worker auto_contrib loop); F-gate/pens/Inspector follow automatically via inpaint_state."
metrics:
  duration: "~2 sessions (PC sleep interrupted the first; resumed from uncommitted tests, no work lost)"
  completed: 2026-09-05
  tasks: 2
  commits: 2
actuals:
  tokens: 46000
  tasks: 2
  commits: 2
requirements: [quick-260904-wn0]
---

# Quick Task 260904-wn0 — Fix intermittent flat-white corner fill when cleaning (C) after resizing a box — Summary

**One-liner:** Resized boxes' stale fit-time masks are now excluded from every fill/LaMa compose path via a fit-freshness dims check in the single `PageBox._has_auto_mask_content` predicate — no more flat median-color corner patches on C, and no misaligned stale LaMa binary either.

## Execution Note: Interruption + Resume

The first execution session was interrupted by PC sleep after writing and RED-verifying the Task 1 tests (nothing committed). The resume session verified the uncommitted tests survived intact, completed the Task 1 contract (one test renamed to match the plan's `-k "resized or moved"` verify filter — the pure-move compose guard's stem said "move", not "moved"), and proceeded normally. No work was lost or redone.

## Root Cause (confirmed by code read, per plan)

A per-box mask is box-cropped at FIT time (`_fit_one_box` → `ops.cut_out_mask`), but `Canvas._commit_resize` commits nothing to fit data, and `boxes_snapshot()` forwards the fit-time mask verbatim with CURRENT geometry. The fill pass pasted the fit-time mask at the CURRENT box origin (`compose_fill_specs` → worker `alpha_composite` at `(pb.box.x1, pb.box.y1)`); after a resize that moved the origin, the old mask landed offset from the text as a flat median-color (usually white) patch, and `std_dev <= threshold` still routed the box to FILL so LaMa never ran. The same stale-mask-at-current-origin paste existed in `compose_auto_binary` / `compose_fill_binary` (LaMa plane) and the worker's `auto_contrib` count loop.

## What Was Done

### Task 1 — RED (commit 3802811)

New regression tests, all verified failing on current code for the asserted reasons:

- `tests/test_core/test_detection_boxes.py` (compose level):
  - `test_compose_fill_specs_skips_resized_stale_mask_box` — FAIL (stale spec returned)
  - `test_compose_binaries_resized_box_contributes_zero_pixels` — FAIL (stale mask pasted; covers fill-routed, inpaint-routed, and "always"-override boxes)
  - `test_inpaint_state_resized_gate_skipped_moved_will_fill` — FAIL (resized reported `will_fill`)
  - `test_compose_fill_specs_pure_moved_box_composes_at_new_origin` — PASS (anti-over-fix guard)
- `tests/test_gui/test_inpaint_flow.py` (worker level, mirroring `test_fill_only_worker_path_skips_model`):
  - `test_fill_only_worker_skips_resized_stale_box` — FAIL (`fill_count == 1`, white patch painted)
  - `test_fill_only_worker_moved_box_still_fills` — PASS (moved control still fills at the new origin)

### Task 2 — GREEN (commit 9860048)

1. `manga_ai_studio/core/box_model.py` — `_has_auto_mask_content` additionally requires `self.mask.size == (box_w, box_h)`; docstring states the fit-freshness contract and its equivalence to the `project_io.py` save-side `mask_stale` invariant (quick-260825-u9q). This single change makes `inpaint_state` return `gate_skipped` for resized boxes, so pens, Inspector, and the F-gate (`_has_pending_fill_work`) follow automatically through the single derivation site.
2. `manga_ai_studio/core/detection_boxes.py` — the inline `if pb.mask is None or pb.mask.getbbox() is None: continue` checks replaced with `if not pb._has_auto_mask_content(): continue` in `compose_auto_binary`, `compose_fill_binary`, and `compose_fill_specs` (intentional cross-module use within `manga_ai_studio.core` so the predicate lives in ONE place; comments say so).
3. `manga_ai_studio/gui/main_window.py` — `_run_inpaint_task`'s `auto_contrib` count loop uses the same predicate, keeping `inpaint_count` consistent with the composed binary.

Paste-origin audit (per plan action): the only remaining `pb.box.x1/y1` paste sites are the three compose functions (all now predicate-gated), `_fit_one_box`'s reference-frame translation (fit time — produces the fresh mask), and `project_io`'s save-side guard itself. `core/batch_runner.py` calls the same compose functions and inherits the fix unchanged.

## Deviations from Plan

**1. [Rule 1 - Test fixture alignment] `tests/test_core/test_box_model.py::test_inpaint_state_matrix`**
- **Found during:** Task 2 targeted verify
- **Issue:** The state-matrix fixture built a 4x4 content mask for a 2x2 box (`make()` uses `Box(1, 2, 3, 4)`). Under the new freshness-aware predicate that fixture is — correctly — resize-stale, so the `will_fill` row returned `gate_skipped`. The old test encoded the dims-agnostic predicate.
- **Fix:** Matrix masks sized to the box (2x2) so each row tests the std-dev routing it claims (docstring unchanged in intent). The other `_mask_with_content` consumer (`test_pagebox_copy_detaches_mask_and_preserves_seam_fields`) tests mask detachment only and is unaffected.
- **Commit:** 9860048 (kept with the production change so the commit is green/bisectable)

**2. [Plan-conformance] Pure-move compose test renamed** `...pure_move_composes_at_new_origin` → `...pure_moved_box_composes_at_new_origin` — the plan's verify command filters `-k "resized or moved"` and the original stem was deselected by it. No behavioral change.

Otherwise: none — plan executed as written; no production code beyond the three named files.

## Verification Results

- Task 1 RED run: 4 failed / 2 passed, exactly as the plan's done-criteria require (resize cases fail on stale fill spec / painted white pixels / `will_fill` state; move cases pass).
- Task 2 GREEN: targeted suites `test_detection_boxes.py + test_inpaint_flow.py + test_box_model.py + test_batch_inpaint_parity.py` → **58 passed, 0 failed**; `-k "resized or moved"` → **6 passed**.
- Full suite (pinned interpreter): **1278 passed, 1 failed** — the single failure is `tests/test_gui_ocr_grab.py::test_grab_history_click_recopies_older_entry`, a pre-existing environmental flake (see Deferred Issues). Suite baseline cited in the plan (1246) predates 260903-lm6's additions; the bar "Task 1 tests green + moved/fresh behavior preserved + no new failures" is met.
- Plan-level verification: resize-then-C box produces zero fill specs, zero fill binary, zero auto binary, `gate_skipped` state, and a pixel-identical page from the fill_only worker; move-then-C composes at the new origin; in-session behavior now matches post-save/reload behavior (same `mask.size != (box_w, box_h)` rule both paths).

## Deferred Issues

- `tests/test_gui_ocr_grab.py::test_grab_history_click_recopies_older_entry` (from quick-260901-wmn, unrelated module): intermittently fails under suite load with Qt's "Unable to obtain clipboard" — the real-OS-clipboard polling starves while another process holds the clipboard. Verified flip-flopping pass/fail across runs with zero code change (passed in isolation, failed at file level, passed again in isolation). Out of scope for this task (scope boundary: pre-existing flake in an unrelated file; no clipboard code touched here). Worth a follow-up: mock the clipboard or widen `_clipboard_text_eventually`'s backoff.

## Known Stubs

None — no stubs, placeholders, or unwired data paths introduced.

## Self-Check: PASSED

- Commit 3802811 (Task 1 RED) present: yes
- Commit 9860048 (Task 2 GREEN) present: yes
- All 6 modified/created files exist on disk: yes
- SUMMARY frontmatter carries `status: complete`: yes
