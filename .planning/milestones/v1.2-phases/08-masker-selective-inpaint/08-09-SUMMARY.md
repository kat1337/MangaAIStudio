---
phase: 08-masker-selective-inpaint
plan: 09
subsystem: masking
tags: [batch, detection-seam, masker-config, constrained-mask, pyside6, d-04]

# Dependency graph
requires:
  - phase: 08-masker-selective-inpaint
    provides: build_detected_pageboxes / derive_page_mask_state / pack_binary + raw/auto plane slots (08-03, 08-02), refresh_box_inpaint_states + set_boxes-suppression + set_planes/set_auto_binary seam helpers (08-07), per-box inpaint_override honored by compose_auto_binary (08-08)
provides:
  - batch_runner constrained-detect path: per-page boxes built in the worker (build_detected_pageboxes) + box-constrained mask derivation (derive_page_mask_state) with masker_conf threading
  - ImageFile batch persistence: page.boxes + packed raw_detected_mask (D-08) + auto_mask + composite page.mask from the auto binary (D-02: out-of-box content never reaches the saved mask)
  - _dispatch_batch profile-masker supply (detect + detect_and_clean worker args)
  - mode-aware post-batch refresh extended to boxes/planes/border-states (02-04 Bug-D-family desync closed)
  - D-03 empty-mask passthrough extension: zero gate-passing boxes -> no LaMa call, original copied through
affects: [end-of-phase verification/UAT, 09-ui-rework, phase gate batch-quality UAT]

# Actuals (#2632) — chars/4 over the realized diff (estimateTokens scale)
actuals:
  tokens: 10900
  tasks: 2
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "One seam core, two consumers: the batch worker imports the SAME build_detected_pageboxes + derive_page_mask_state the interactive handler uses — no duplicate V5/derivation logic in the worker"
    - "Config threading mirrors the model-path threading: masker_conf rides the Worker args tuple positionally (progress_callback/abort_flag stay the last two kwargs per the Worker auto-injection contract)"
    - "Batch is headless: the D-04 replace gate does NOT apply to the post-batch restore (RESEARCH §5 item 5); the restore runs set_boxes under the _suppress_boxes_push guard (WR-05 discipline)"
    - "Empty-mask passthrough composes: zero boxes derives an empty auto binary, which trips the pre-existing D-03 has_mask_content gate — no new passthrough code"

key-files:
  created: []
  modified:
    - manga_ai_studio/core/batch_runner.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_core/test_batch_runner.py
    - tests/test_gui_batch.py
    - tests/test_core/conftest.py

key-decisions:
  - "masker_conf is a REQUIRED positional on batch_detect/batch_detect_and_clean (no default): the profile always supplies it; a missing conf in a detect mode raises TypeError inside _run_batch_task (a programming error must fail loudly, never silently derive with defaults)"
  - "Task 2's behavior tests live in tests/test_gui_batch.py, NOT the plan's listed test_core/test_batch_runner.py — _dispatch_batch and the canvas restore are Qt-dependent MainWindow behavior that cannot run headless in the core suite; the Task 2 verify runs both files (superset of the plan command)"
  - "The post-batch refresh passes EXPLICIT-EMPTY manual/erase planes (not None) for batch pages — the API distinguishes empty-from-absent and batch pages genuinely have no strokes; auto plane restored from the packed slot only when present (legacy flat-mask pages keep the existing set_mask restore)"

requirements-completed: [MASK-01, MASK-02, MASK-05]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "batch_runner constrained detect path + masker_conf threading — boxes built in the worker, mask constrained to box interiors (D-02), raw/auto packed slots persisted, radius from the threaded conf (MASK-01 in batch)"
    requirement: MASK-01
    verification:
      - kind: unit
        ref: "tests/test_core/test_batch_runner.py#test_batch_detect_persists_boxes_and_constrained_masks"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_batch_runner.py#test_batch_detect_and_clean_inpaints_constrained_mask"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_batch_runner.py#test_batch_detect_dilation_radius_effect"
        status: pass
    human_judgment: false
  - id: D2
    description: "D-03 empty-mask passthrough extension — a page whose only box fails the std-dev gate produces an empty composite; the original is copied through and the inpaint model is never called"
    requirement: MASK-02
    verification:
      - kind: unit
        ref: "tests/test_core/test_batch_runner.py#test_batch_detect_and_clean_gate_fail_passthrough"
        status: pass
    human_judgment: false
  - id: D3
    description: "_dispatch_batch supplies the profile's MaskerConfig (current radius) to both detect-mode worker calls; abort still checked at the loop top only"
    verification:
      - kind: unit
        ref: "tests/test_gui_batch.py#test_batch_detect_dispatch_passes_profile_masker_conf"
        status: pass
      - kind: unit
        ref: "tests/test_gui_batch.py#test_batch_detect_and_clean_dispatch_passes_profile_masker_conf"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_batch_runner.py#test_abort_between_pages"
        status: pass
    human_judgment: false
  - id: D4
    description: "Mode-aware post-batch refresh extended to boxes/planes/states — after a detect-only batch the current page's canvas restores the persisted boxes (under the suppression guard, no history push), the composite equals the packed auto plane, and border states derive from the per-box fields; clean mode unchanged"
    requirement: MASK-05
    verification:
      - kind: unit
        ref: "tests/test_gui_batch.py#test_batch_detect_refresh_restores_boxes_auto_plane_and_borders"
        status: pass
      - kind: unit
        ref: "tests/test_gui_batch.py#test_batch_clean_refresh_branch_unchanged"
        status: pass
    human_judgment: false

# Metrics
duration: 35min
completed: 2026-08-18
status: complete
---

# Phase 8 Plan 9: Batch Adopts the Box-Constrained Rule (D-04) Summary

**The batch pipeline adopts the D-02 rule end-to-end: the worker builds per-page boxes from the same detect pass, constrains the saved mask to box interiors (dilation from the threaded profile MaskerConfig), persists reviewable boxes + packed raw/auto planes, and the post-batch refresh restores boxes/planes/border-states on the current page without desync — phase-closing full suite 869 green.**

## Performance

- **Duration:** 35 min (active execution burst; wall clock ~55 min incl. an interrupted first session)
- **Started:** 2026-08-18T05:30:00Z
- **Completed:** 2026-08-18T06:05:00Z
- **Tasks:** 2 (both TDD: RED + GREEN each)
- **Files modified:** 5

## Accomplishments

- **Constrained detect path in the worker (D-04):** the detect branch no longer discards `_blk_list` — it converts BGR→RGB once, builds per-page boxes via `build_detected_pageboxes` (dims from the decoded image — no canvas exists), derives the box-constrained mask via `derive_page_mask_state` (the SAME 08-03 seam core the interactive handler uses), and persists `page.boxes`, the packed `raw_detected_mask` (D-08 pre-dilation retention) and `auto_mask` slots, plus the composite `page.mask` from the auto binary. Manual/erase stay None — batch pages have no hand strokes.
- **`masker_conf` threading:** `batch_detect` / `batch_detect_and_clean` gain the required `masker_conf` parameter (mirroring the `det_model_path` flow); `_dispatch_batch` supplies the profile's live `MaskerConfig` into both detect-mode worker arg tuples, so `mask_dilation_radius` and every masker fit param reach the worker.
- **D-03 passthrough composes:** a page with zero gate-passing boxes (empty `blk_list`, or boxes whose honest std exceeds the gate with override None) derives an EMPTY auto binary → `has_mask_content()` False → the pre-existing D-03 gate copies the original through and LaMa is never called for that page.
- **Worker stays Qt-free in the new computation:** the derivation is PIL/numpy only (the 08-03 headless module, hermetic-locked); the one off-thread QImage construction (`numpy_binary_to_mask_qimage`) remains the existing precedented site. Tests assert the numpy/PIL outputs (packed slots + per-box mode-"1" PIL masks) before the QImage step.
- **Mode-aware post-batch refresh extended:** after a detect-only batch, the current page's canvas now restores the persisted boxes (set_boxes split by origin under the `_suppress_boxes_push` guard — batch is headless, no D-04 replace gate per RESEARCH §5 item 5), the packed auto plane (`set_planes` with explicit-empty manual/erase), and the per-box border states (`refresh_box_inpaint_states`) — closing the 02-04 Bug-D-family desync risk. Clean mode is unchanged (reload + clear).
- **Full suite:** 869 passed / 0 failed on the pinned interpreter (baseline 861 at 08-08 close + 8 new tests), verified across two consecutive full runs; the one previously-documented pre-existing OCR flake passed in isolation and both full runs.

## Task Commits

Each task was committed atomically (TDD: RED test commit → GREEN feat commit):

1. **Task 1: batch_runner — constrained detect path + masker_conf threading** (TDD)
   - `ab1d2b0` `test(08-09): add failing constrained-detect + masker_conf threading tests`
   - `9601cae` `feat(08-09): constrained detect path + masker_conf threading in batch loop`
2. **Task 2: MainWindow batch dispatch + mode-aware post-batch refresh** (TDD)
   - `1f40164` `test(08-09): add failing dispatch-masker-conf + post-batch restore tests`
   - `cc08807` `feat(08-09): dispatch profile masker conf + post-batch boxes/planes/state restore`

**Plan metadata:** final docs commit (below)

## Files Created/Modified

- `manga_ai_studio/core/batch_runner.py` - `masker_conf` required param on `batch_detect`/`batch_detect_and_clean` (passed into `_run_batch_task`, which raises `TypeError` when a detect mode lacks it); detect branch reworked: `build_detected_pageboxes` + `derive_page_mask_state` + per-page persistence (boxes / raw_detected_mask / auto_mask / composite mask); module docstring thread-safety note extended (the derivation is PIL/numpy only).
- `manga_ai_studio/gui/main_window.py` - `_dispatch_batch` threads `profile.masker` into the detect + detect_and_clean arg tuples; `_refresh_current_page_after_batch` detect branch extended to restore boxes (suppressed set_boxes, split by origin), the packed auto plane (set_planes with explicit-empty manual/erase), and `refresh_box_inpaint_states`; docstring updated.
- `tests/test_core/test_batch_runner.py` - +4 new tests (constrained persistence + composite equality, constrained mask reaching LaMa, gate-fail passthrough, radius effect) + `masker_conf` threaded through every detect-mode call site + `_FixtureDetector` helper + strokes/noise page fixtures.
- `tests/test_gui_batch.py` - +4 new tests (dispatch masker-conf for detect + detect_and_clean, detect-mode restore of boxes/auto/borders, clean-mode branch lock); existing four detect fakes updated to the 5-positional worker signature; the two direct `_run_batch_task` detectors now return a full-page blk (the loop derives boxes) and pass `masker_conf`.
- `tests/test_core/conftest.py` - `FakeDetectionModel.detect` now returns a full-page detected box alongside the mask (the loop no longer discards `blk_list`; an empty list would derive empty masks and gut the pre-Phase-8 batch behavior these contracts lock).

## Decisions Made

- **Required `masker_conf`:** no default on the detect-mode entry points — the profile always supplies it; a missing conf raises `TypeError` in the worker (loud programming-error contract, same discipline as the strict-int dims guard in 08-03).
- **Task 2 test placement:** the plan's `files_modified` listed `test_core/test_batch_runner.py` for the GUI task, but `_dispatch_batch` and the canvas restore are Qt-dependent MainWindow behavior that cannot run headless — the tests land in `tests/test_gui_batch.py` (the established GUI batch suite) and the Task 2 verify runs both files (a superset of the plan's command).
- **Explicit-empty planes on restore:** batch pages genuinely have empty manual/erase planes, so the refresh passes explicit empty QImages (the API distinguishes empty-from-absent); the auto plane restores from the packed slot only when present, so legacy flat-mask pages keep the existing `set_mask` restore.
- **Worker fixture honesty:** both the shared `FakeDetectionModel` and the GUI fakes return a full-page detected box, mirroring the real CTD contract (heatmap + blk_list) so the constrained derivation actually runs in every existing batch test.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Test placement] Task 2 behavior tests live in test_gui_batch.py, not the plan's listed test_core file**
- **Found during:** Task 2 test authoring (RED design)
- **Issue:** The plan's `<files>`/`<verify>` point Task 2's dispatch-args and current-page-restore tests at the headless `tests/test_core/test_batch_runner.py`, but `_dispatch_batch` and `_refresh_current_page_after_batch` are Qt-dependent `MainWindow` methods that cannot be exercised in a core (no-GUI) suite.
- **Fix:** Task 2 tests written in `tests/test_gui_batch.py` (the existing GUI batch-dispatch suite); the Task 2 verify runs `test_gui_batch.py` + `test_batch_runner.py` together (superset of the plan's command), and the phase-closing full suite covers both.
- **Files modified:** tests/test_gui_batch.py (new tests + fake updates)
- **Verification:** 33/33 green on the two-file run; full suite 869 green.
- **Committed in:** 1f40164 (RED), cc08807 (GREEN).

**2. [Rule 3 - Blocking] Existing GUI batch tests broke on the new worker signature**
- **Found during:** Task 2 RED (after Task 1's GREEN changed `batch_detect`'s signature)
- **Issue:** `_dispatch_batch`'s detect-mode fakes and the two direct `_run_batch_task` calls in test_gui_batch.py declared the pre-Phase-8 4-positional worker signature; the new 5-positional contract (and the mandatory `masker_conf` in detect mode) made them fail with `TypeError`.
- **Fix:** All four detect fakes updated to the 5-positional signature with `masker_conf`; the two `_run_batch_task` detectors now pass `masker_conf` and return a full-page blk (`SimpleNamespace(xyxy=[0,0,w,h])`) so the constrained derivation keeps content — mirroring the shared `FakeDetectionModel` change in conftest.
- **Files modified:** tests/test_gui_batch.py, tests/test_core/conftest.py
- **Verification:** 33/33 green on the two-file run; full suite 869 green.
- **Committed in:** 1f40164 (RED, fakes), cc08807 (GREEN).

---

**Total deviations:** 2 auto-fixed (both Rule 3 — no production behavior deviation; both keep tests honest against the new worker contract).
**Impact on plan:** All fixes were required for the plan's own contract change (the required `masker_conf` parameter and the constrained derivation). No scope creep; no production code changed beyond the plan's prescribed edits.

## Issues Encountered

- **Known pre-existing full-suite flake (out of scope, previously logged in 08-03-SUMMARY):** `tests/test_gui_boxes.py::test_run_ocr_selected_dispatches_worker_not_inline` failed in the FIRST full-suite run (timing/order sensitivity in the OCR worker-dispatch + waitUntil path, aggravated by the network-touching OCR end-to-end test that runs just before it). It passed in isolation (2.2s) and in BOTH subsequent full runs (869 passed ×2). Not caused by this plan's changes; left untouched per the scope boundary.

## Known Stubs

None — no stub patterns introduced. The plan's goal (D-04 batch adoption) is fully wired; batch pages persist real boxes/masks and the current page restores them.

## User Setup Required

None - no external service configuration required.

## Self-Check

Verified after writing this summary:
- `08-09-SUMMARY.md` exists on disk ✓
- All 4 task commits present in `git log --oneline --grep="08-09"`: `ab1d2b0`, `9601cae`, `1f40164`, `cc08807` ✓
- Source assertions re-run: `batch_detect`/`batch_detect_and_clean` declare `masker_conf` ✓; the detect branch calls `build_detected_pageboxes` + `derive_page_mask_state` and writes `page.boxes`/`raw_detected_mask`/`auto_mask` ✓; `_dispatch_batch` supplies the profile conf to both detect-mode tuples ✓; the detect-mode refresh calls `set_boxes` under `_suppress_boxes_push` + `refresh_box_inpaint_states` ✓
- Full pinned-interpreter suite: 869 passed / 0 failed (two consecutive runs) ✓

## Self-Check: PASSED

## Next Phase Readiness

- The full automated surface of Phase 8 is closed: interactive seam (08-07), inspector override (08-08), and the batch pipeline (08-09) all consume the single 08-03 derivation core and honor the box-constrained rule.
- The two-stage batch workflow is now selective-aware: Batch Detect persists reviewable per-page boxes with per-box mask/std state; Batch Clean inpaints only the constrained composite; a page with zero gate-passing boxes passes through untouched.
- Remaining for the phase gate (08-VALIDATION.md Layer 3, manual UAT): batch output quality on a real chapter, re-dilate slider latency, border legibility on real artwork.

---
*Phase: 08-masker-selective-inpaint*
*Completed: 2026-08-18*