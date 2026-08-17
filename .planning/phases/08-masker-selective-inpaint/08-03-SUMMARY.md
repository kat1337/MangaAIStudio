---
phase: 08-masker-selective-inpaint
plan: 03
subsystem: core
tags: [detection-seam, masker-machinery, pure-functions, pick-best-mask, std-dev, dilation, gate-decoupling, headless, pagebox]

requires:
  - phase: 08-masker-selective-inpaint
    provides: plan 08-01 — PageBox D-15 mask/std_dev seam fields + inpaint_override, MaskerConfig.mask_dilation_radius
  - phase: 08-masker-selective-inpaint
    provides: plan 08-02 — canvas three-plane model (set_auto_binary consumes the (H,W) uint8 binary), ImageFile.raw_detected_mask D-08 slot
  - phase: 03-text-box-detection-interaction
    provides: the V5 box-build loop in _build_detected_boxes (the extraction source) + PageBox/DETECTED origin
provides:
  - core/detection_boxes.py — build_detected_pageboxes (headless V5 loop) consumed by 08-07 (GUI handler) and 08-09 (batch loop)
  - derive_page_mask_state — pure (image_rgb, heatmap, boxes, MaskerConfig, radius) -> PageMaskDerivation; gate-lifted per-box fits
  - compose_auto_binary — pure threshold/override recomposition (never re-fits)
  - dilate_auto_mask — mask-only-mode full-heatmap dilation (D-03 path)
  - tests/test_core/test_masker_machinery.py + tests/test_core/test_detection_boxes.py — the first real call-site suites for the vendored machinery
affects: [08-masker-selective-inpaint, 09-ui-rework]

tech-stack:
  added: []
  patterns:
    - "Pure-function extraction for headless reuse (the 05-08 precedent): the V5 loop and the vendored masker.py sequence live in ONE Qt-free module, consumed by both the GUI handler and the batch worker"
    - "Gate-decoupled fitting (P-5/Q1 Fork-A): pick_best_mask runs with attrs.evolve(mask_max_standard_deviation=1e9) so best_mask + the HONEST std are ALWAYS stored; the gate is a pure function of threshold + override applied downstream — threshold changes never re-fit"
    - "Dilate-then-intersect (MASK-05 literal): grow_mask FIRST, mask_intersection with the ALL-box union SECOND — auto content can never exit a box"

key-files:
  created:
    - manga_ai_studio/core/detection_boxes.py
    - tests/test_core/test_masker_machinery.py
    - tests/test_core/test_detection_boxes.py
  modified: []

key-decisions:
  - "derive_page_mask_state MUTATES the live PageBox list (writes pb.mask/pb.std_dev) and returns a fits dict keyed by id(pagebox); compose_auto_binary recomposes purely from the stored fields — derive calls it (not duplicated)"
  - "Reference-box padding uses the plan's prescribed formula pb.box.pad(mask_growth_step_pixels * mask_growth_steps, page_size); Pillow's FIND_EDGES copies border pixels, so a candidate that saturates its reference frame yields the frame-border ring (never a fabricated BlankMaskError) — probe-verified and encoded in the battery"
  - "border_std_deviation RGB path measures std of distances from the MEAN color — a symmetric two-color border split reads 0, so the battery's contrast fixture is deliberately asymmetric (probe-verified); the noise-failure fixture must reach the reference-frame border for the same reason"
  - "T-08-04 mitigation implemented as a strict int guard on img_w/img_h in build_detected_pageboxes (a float would leak float clamp bounds into the geometry) + a heatmap-vs-image shape ValueError in derive_page_mask_state"
  - "The headless purity lock runs a HERMETIC subprocess probe: the in-process sys.modules check is broken by any earlier GUI test module in the suite (order-dependent) — fixed in 1ab15b5"

requirements-completed: [MASK-01, MASK-02, MASK-05]

coverage:
  - id: D1
    description: "Masker machinery battery — grow_mask, mask_intersection, border_std_deviation (incl. BlankMaskError), pick_best_mask (fit/None/failed), compose_masks; first real call-site tests for the vendored contracts"
    requirement: MASK-01
    verification:
      - kind: unit
        ref: tests/test_core/test_masker_machinery.py#test_grow_mask_grows_centered_square_by_exactly_n_pixels
        status: pass
      - kind: unit
        ref: tests/test_core/test_masker_machinery.py#test_mask_intersection_discards_outside_keeps_inside_exactly
        status: pass
      - kind: unit
        ref: tests/test_core/test_masker_machinery.py#test_border_std_deviation_uniform_page_returns_zero
        status: pass
      - kind: unit
        ref: tests/test_core/test_masker_machinery.py#test_border_std_deviation_blank_mask_raises
        status: pass
      - kind: unit
        ref: tests/test_core/test_masker_machinery.py#test_pick_best_mask_finds_fit_with_finite_std
        status: pass
      - kind: unit
        ref: tests/test_core/test_masker_machinery.py#test_pick_best_mask_blank_precise_mask_returns_none
        status: pass
      - kind: unit
        ref: tests/test_core/test_masker_machinery.py#test_pick_best_mask_noisy_page_low_threshold_fails
        status: pass
      - kind: unit
        ref: tests/test_core/test_masker_machinery.py#test_compose_masks_pastes_at_origins_and_unions_overlaps
        status: pass
    human_judgment: false
  - id: D2
    description: "build_detected_pageboxes — headless extraction of the V5 loop (int coercion, per-edge clamp, zero-area drop, DETECTED origin, default-style contract, strict int dims) + headless purity"
    requirement: MASK-05
    verification:
      - kind: unit
        ref: tests/test_core/test_detection_boxes.py#test_build_detected_pageboxes_clamps_drops_and_tags_detected
        status: pass
      - kind: unit
        ref: tests/test_core/test_detection_boxes.py#test_build_detected_pageboxes_style_follows_default_family
        status: pass
      - kind: unit
        ref: tests/test_core/test_detection_boxes.py#test_detection_boxes_module_is_headless
        status: pass
    human_judgment: false
  - id: D3
    description: "derive_page_mask_state — D-02 out-of-box discard, MASK-01 dilate-then-intersect clamp at the box border, gate-lifted per-box fits (uniform/empty/textured all store), raw pre-dilation binary retention (D-08), USER-origin certification, zero-boxes empty auto"
    requirement: MASK-01
    verification:
      - kind: unit
        ref: tests/test_core/test_detection_boxes.py#test_derive_discards_out_of_box_heatmap_content
        status: pass
      - kind: unit
        ref: tests/test_core/test_detection_boxes.py#test_derive_dilation_grows_but_never_exits_the_box
        status: pass
      - kind: unit
        ref: tests/test_core/test_detection_boxes.py#test_derive_per_box_fits_store_gate_lifted
        status: pass
      - kind: unit
        ref: tests/test_core/test_detection_boxes.py#test_derive_zero_boxes_empty_auto_and_dilate_auto_mask
        status: pass
      - kind: unit
        ref: tests/test_core/test_detection_boxes.py#test_derive_fits_user_origin_boxes_identically
        status: pass
    human_judgment: false
  - id: D4
    description: "compose_auto_binary gate matrix (Auto/under-threshold, always forces, never skips, mask-None skips) + threshold recomposition without re-fitting; dilate_auto_mask mask-only-mode full-heatmap dilation"
    requirement: MASK-02
    verification:
      - kind: unit
        ref: tests/test_core/test_detection_boxes.py#test_compose_auto_binary_gate_matrix
        status: pass
    human_judgment: false

duration: 42 min active (wall clock spans a provider usage-limit interruption; see Issues Encountered)
completed: 2026-08-17
status: complete
---

# Phase 08 Plan 03: Detection→Mask Seam Core Summary

**Pure-function detection→mask seam core — headless V5 box build, box-constrained dilated auto binary via gate-lifted per-box fits, threshold/override recomposition, and the first real call-site battery for the vendored masker machinery — 784 tests green**

## Performance

- **Duration:** ~42 min active work (wall clock 2026-08-17T00:18:26Z → 17:08:51Z spans a provider usage-limit interruption mid-Task-3; work resumed from the surviving tree)
- **Started:** 2026-08-17T00:18:26Z
- **Completed:** 2026-08-17T17:08:51Z
- **Tasks:** 3 (TDD: RED + GREEN each; plus a post-GREEN test fix)
- **Files modified:** 3 (1 created, 2 new test files)

## Accomplishments

- `manga_ai_studio/core/detection_boxes.py` — the headless seam core (PIL/numpy/scipy only, no Qt, no torch). `build_detected_pageboxes` is the exact extraction of the `_build_detected_boxes` V5 loop (main_window.py:4085-4121) with a strict-int dims guard (T-08-04); the GUI handler (08-07) rewires to it while the batch loop (08-09) imports it off-thread
- `derive_page_mask_state` runs the vendored masker.py:63-104 sequence per RESEARCH §1.4: explicit-threshold binarize (`dither=Image.NONE`, Pitfall 13-7) with the pre-dilation binary retained as `raw_binary` (D-08); MASK-01 dilation on detected content only (D-07); dilate-then-intersect against the ALL-box union so auto content can never exit a box (D-02 + MASK-05 literal); per-box gate-lifted fits (`attrs.evolve(mask_max_standard_deviation=1e9)`) with BlankMaskError pre-checks (Pitfall 13-8) and the `best_mask` cropped back to the masking box (reference-coordinate offset math)
- `compose_auto_binary` is pure recomposition from stored masks/overrides — threshold changes and override flips never re-fit; `dilate_auto_mask` is the mask-only-mode path (D-03 keeps the full heatmap, MASK-01 still applies)
- Two new unit suites: `test_masker_machinery.py` (12 tests — the first real call-site battery for the vendored machinery, contracts probe-verified before being frozen) and `test_detection_boxes.py` (9 tests — clamp/drop/style/headless + the D-02/dilation/gate-decoupled/compose-matrix/zero-boxes/USER-certify behaviors 08-07 and 08-09 rely on)

## Task Commits

Each task was committed atomically (TDD: RED test commit → GREEN feat commit):

1. **Task 1: Masker machinery battery — first real call-site tests** - `2dd36e3` (test)
2. **Task 2: build_detected_pageboxes — headless extraction of the V5 loop** - `450a0b6` (test) + `632c716` (feat)
3. **Task 3: derive_page_mask_state + compose_auto_binary + dilate_auto_mask** - `992bef6` (test) + `ab3e19f` (feat)
4. **Post-GREEN fix: headless purity test order-independence** - `1ab15b5` (fix)

**Plan metadata:** final docs commit (below)

## Files Created/Modified

- `manga_ai_studio/core/detection_boxes.py` - NEW: `build_detected_pageboxes` (strict-int dims, V5 clamp/drop), `BoxMaskFit` + `PageMaskDerivation` dataclasses, `derive_page_mask_state` (+ `_fit_one_box` guard/ref-box/crop-back), `compose_auto_binary`, `dilate_auto_mask`; module docstring cites the extraction source and the 08-07/08-09 consumers
- `tests/test_core/test_masker_machinery.py` - NEW (Task 1): 12 unit tests across the five behavior groups — grow (param 0/2/5 + passthrough), intersection, std-dev (uniform/stripe/blank), pick_best_mask (fit offset-math / noise-None / failed), compose paste-union — pure PIL, no torch/Qt/gui imports
- `tests/test_core/test_detection_boxes.py` - NEW (Tasks 2-3): V5 clamp/style/headless (hermetic subprocess probe) + D-02 discard, dilation-clamp-at-border, gate-decoupled storage, compose gate matrix, zero-boxes empty auto, dilate_auto_mask, USER-origin certification

## Decisions Made

- `derive_page_mask_state` writes the D-15 seam fields (`pb.mask`/`pb.std_dev`) on the live pageboxes it is handed; `compose_auto_binary` reads ONLY stored fields — derive calls compose (the plan's "call it — do not duplicate"): one gate definition
- Reference padding = `pb.box.pad(mask_growth_step_pixels * mask_growth_steps, page_size)` verbatim per PLAN; saturation-safe because Pillow's FIND_EDGES copies border pixels (frame-border ring instead of a fabricated BlankMaskError)
- T-08-04 mitigation as explicit guards: strict int `img_w`/`img_h` in the box build + heatmap/image shape ValueError in the derive (no allocation sized from unvalidated dims)
- Legacy-no-Qt runtime proof: a hermetic subprocess (not an in-process `sys.modules` sweep) locks the headless import graph regardless of test order

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Dilation fixture made deterministic via probe-derived selection**
- **Found during:** Task 3 (RED design of `test_derive_dilation_grows_but_never_exits_the_box`)
- **Issue:** With the default `mask_growth_steps=11` the outcome of a radius change is not observable the way the plan's test sentence ("grows the auto content by ~3 px") suggests — the winning candidate on a uniform page is the full-box mask candidate (std 0), so a radius delta changes nothing in the composed binary. Naive periodic stripes inside the box also failed to produce a `failed=True` in the machinery battery: grown candidates saturate the reference frame and their Pillow-copied border ring sits on clean pixels (std 0).
- **Fix:** The machinery test uses full-page fixed-seed noise (noise must reach the frame border); the dilation test uses `MaskerConfig(mask_growth_steps=1)` with a single growth candidate (dilated cut + min_thickness) and contrast ticks crossing only the box's right/bottom borders — probe-verified to yield radius 0 → page bbox (12,12)-(28,28) and radius 3 → (10,10)-(31,31) (grown by ~3, clipped exactly at the box border). Both fixtures are documented in-test with the probe rationale.
- **Files modified:** tests/test_core/test_masker_machinery.py, tests/test_core/test_detection_boxes.py
- **Verification:** both suites green; contract facts re-probed at implementation time
- **Committed in:** 2dd36e3, 992bef6 (test design), ab3e19f (implementation aligned)

**2. [Rule 1 - Bug] Headless purity test was order-dependent in the full suite**
- **Found during:** full-suite verification (Task 3 completion)
- **Issue:** The runtime `assert "manga_ai_studio.gui" not in sys.modules` check failed whenever any GUI test module imported the package earlier in the same process — a suite-order interaction, not a module defect.
- **Fix:** Replaced with a hermetic subprocess probe (pinned interpreter) importing the module cold and asserting nothing from the GUI layer enters `sys.modules`; source-token scan retained.
- **Files modified:** tests/test_core/test_detection_boxes.py
- **Verification:** test passes both at file isolation and in three consecutive full-suite runs
- **Committed in:** 1ab15b5

---

**Total deviations:** 2 auto-fixed (both Rule 1 test-construction bugs; the first also corrected an expectation the plan's wording could not hold deterministically)
**Impact on plan:** Both fixes keep the tests honest against the REAL vendored machinery (the plan's own gap-closure discipline). No production behavior changed by either fix.

## TDD Gate Compliance

All three tasks are `tdd="true"`; git log shows the RED→GREEN sequence for each:
- Task 1: `test(08-03)` 2dd36e3 — the machinery battery is a characterization/contract-lock suite over ALREADY-vendored functions, so it passed at RED (nothing new to implement; the RED = the battery itself, the same precedent as 08-01 Task 3's policy-lock half)
- Task 2: `test(08-03)` 450a0b6 → `feat(08-03)` 632c716 — RED failed with genuine ModuleNotFoundError (module absent)
- Task 3: `test(08-03)` 992bef6 → `feat(08-03)` ab3e19f — RED failed with ImportError on the four missing primitives

RED gates failed for the right reasons where implementation was missing; contract-lock tests (Task 1, plus Task 3's out-of-box-discard/certification locks) are genuine regression guards over the already-vendored surface. A post-GREEN `fix(08-03)` commit (1ab15b5) hardened the headless test's order dependence. No refactor commits needed.

## Issues Encountered

- A provider usage limit killed the session mid-Task-3; the surviving tree (Task 3 RED tests written, all earlier commits landed) was verified and execution resumed cleanly from the uncommitted RED state.
- **Pre-existing full-suite flake (out of plan scope, logged to deferred-items.md):** `tests/test_gui_boxes.py::test_run_ocr_selected_dispatches_worker_not_inline` fails intermittently in FULL-suite runs — reproduced with the plan-08-03 files excluded, passes in file isolation and in two consecutive full runs during this plan's verification. Timing/order sensitivity in the worker-dispatch + `qtbot.waitUntil(..., timeout=5000)` path, likely aggravated by the network-touching `test_run_ocr_selected_real_model_end_to_end` that runs just before it. Not caused by this plan; left untouched per the scope boundary.
- Three consecutive full-suite runs completed the plan's verification: **784 passed / 0 failed** (baseline 763 at 08-02 close + 21 new tests).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 08-07 (interactive seam) can wire `build_detected_pageboxes` + `derive_page_mask_state` into `_on_detection_finished` and feed `derivation.auto_binary` straight into `canvas.set_auto_binary` (the (H,W) uint8 contract 08-02 locked); the gate-lifted `pb.mask`/`pb.std_dev` fields are populated for every box, so `refresh_box_inpaint_states`/`inpaint_state(threshold)` work immediately
- 08-09 (batch loop) imports the same three functions off-thread without pulling Qt (locked by the hermetic headless test)
- 08-04 can now serialize the now-populated `std_dev`/`inpaint_override`/per-box mask (box-cropped mode-"1" PNG) and the `raw_binary` retention (D-08) — the storage conventions this plan established (content = non-zero pixels, getbbox emptiness probe) are the ones 08-01 anticipated
- No blockers.

## Self-Check: PASSED

All 3 created files exist on disk (core module + 2 test files); all 6 task commits found in `git log --grep="08-03"`; acceptance-criteria source assertions re-run and passing (`derive_page_mask_state`/`compose_auto_binary`/`dilate_auto_mask`/`BoxMaskFit`/`PageMaskDerivation` present; `dither=Image.NONE`, `mask_intersection`, `mask_max_standard_deviation=1e9` all present; no torch reference). Full suite re-verified green before SUMMARY — three consecutive runs of **784 passed / 0 failed** (pinned interpreter).

---
*Phase: 08-masker-selective-inpaint*
*Completed: 2026-08-17*