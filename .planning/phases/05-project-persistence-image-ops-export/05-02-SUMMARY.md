---
phase: 05-project-persistence-image-ops-export
plan: 02
subsystem: core
tags: [image-ops, numpy, pil, geometry, rotate, crop, resize, levels, proj-04]

# Dependency graph
requires:
  - phase: 03-text-box-detection-interaction
    provides: PageBox model (box_model.py) + vendored frozen Box + TextBlock payload with lines quads
  - phase: 04-ocr-recognition-text-editing
    provides: TextBlock payload fields (text/translation/vertical/language/font_size), edited/bubble_no/manual_override peer fields
provides:
  - core/image_ops.py — pure numpy+PIL rotate/crop/resize/levels pixel math + bbox AND TextBlock.lines geometry transforms (headless, no Qt)
  - The D-15/D-17 "geometry rides with the image" transform contract and the D-18 pixel-exact mask discipline for the GUI apply plans (05-06/05-07)
  - Fresh-object/no-mutation API shape that the stamp-shared triple-push undo plan (05-04) pushes onto the stacks
affects: [05-04-geometry-undo, 05-06-rotate-levels-resize, 05-07-crop, 05-03-ocr-export]

# Actuals (#2632) — chars/4 over the realized diff (both files, 3 commits)
actuals:
  tokens: 9608
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: [none — numpy 2.3.5 + Pillow 12.0.0 already installed; zero new deps per RESEARCH Package Legitimacy Audit]
  patterns:
    - "Pure numpy+PIL core module discipline: module docstring states the Qt EVENT DISPATCH lives in gui/canvas.py; no Qt imports; headless-testable (mirrors core/mask_editor.py)"
    - "One rotation convention for image AND mask AND geometry (np.rot90: k=-1 CW / 1 CCW / 2 180; box math mirrors it — RESEARCH Pitfall 4)"
    - "Fresh-object transform API: every box transform builds a NEW @frozen Box + fresh TextBlock + fresh lines list; inputs never mutated (Pitfall 3) — undo-snapshot-safe"
    - ".copy() detachment at every transform return (Pitfall 2), asserted via OWNDATA/shares_memory in tests"

key-files:
  created:
    - manga_ai_studio/core/image_ops.py — _rotate_point, transform_box, transform_lines, transform_box_payload, rotate_page, rotate_boxes, crop_page, _clip_quad, _clip_box, crop_boxes, crop_page_with_boxes, resize_page, resize_boxes, levels_lut, levels_page + _validate_image_mask helper
    - tests/test_core/test_image_ops.py — 8 unit tests (3 rotate + 3 crop + 2 resize/levels)
  modified: []

key-decisions:
  - "Crop geometry: bbox AND line quads are translated by (-x,-y) into POST-crop page coordinates (TextBlock.xyxy == new Box.as_tuple invariant) — the plan's literal 'bbox clamped to [2,1,6,4]' pre-translation shorthand would desync bbox from lines"
  - "levels_lut internally normalizes the range to [min(black, white), max(black, white)] — the T-05-07 clamp; with black==white the LUT degenerates to a single threshold (monotone), never an inversion"
  - "levels_page validates the image shape inline (no mask argument exists — geometry-free by design, D-15); _validate_image_mask is only for the image+mask pairs"
  - "int(round(coord*scale)) uses Python banker's rounding per the plan formula — test boxes were chosen tie-free so assertions stay deterministic"

patterns-established:
  - "Page-op seam: pixel op (image+mask) and geometry op (boxes) are separate functions plus a one-call apply entry (crop_page_with_boxes) the GUI apply path consumes"
  - "D-16 count rides the return tuple (kept_boxes, dropped_count) — the status-bar 'n box(es) were outside the crop' copy is data, not a re-count"

requirements-completed: [PROJ-04]

# Coverage metadata (#1602) — one entry per shipped deliverable
coverage:
  - id: D1
    description: "Rotate 90 CW/CCW/180 pixel-exact for image + binary mask with bbox AND TextBlock.lines geometry transforms (fresh objects, originals untouched)"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_core/test_image_ops.py#test_rotate_transforms_all"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_image_ops.py#test_rotate_composes_identity"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_image_ops.py#test_rotate_rejects_bad_shapes"
        status: pass
    human_judgment: false
  - id: D2
    description: "Crop exact slice with D-16 drop-fully-outside/clip-partial policy (bbox AND line quads, dropped count, post-crop coordinates)"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_core/test_image_ops.py#test_crop_drop_and_clip"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_image_ops.py#test_crop_rejects_bad_input"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_image_ops.py#test_crop_zero_area_dropped"
        status: pass
    human_judgment: false
  - id: D3
    description: "Resize LANCZOS image / NEAREST mask (no interpolated grays) with int box/line scaling"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_core/test_image_ops.py#test_resize_and_levels"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_image_ops.py#test_resize_rejects_bad_input"
        status: pass
    human_judgment: false
  - id: D4
    description: "Levels 256-entry numpy LUT with byte-exact math and the white>black monotone clamp; geometry-free"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_core/test_image_ops.py#test_resize_and_levels"
        status: pass
    human_judgment: false

# Metrics
duration: 25min
completed: 2026-08-08
status: complete
---

# Phase 5 Plan 2: Image Ops Core (rotate/crop/resize/levels + box/line geometry transforms) Summary

**Headless `core/image_ops.py`: pixel-exact rotate (np.rot90, one CW/CCW/180 convention), crop (exact slice + D-16 drop/clip with count), resize (LANCZOS image / NEAREST mask), levels (256-entry numpy LUT with monotone white>black clamp) — every op carrying `PageBox` bbox AND `TextBlock.lines` quads through fresh objects, zero Qt, zero new dependencies**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-08-08 ~13:52Z (first baseline run)
- **Completed:** 2026-08-08T14:17:50Z
- **Tasks:** 3 (1 tracer + 2 auto)
- **Files modified:** 2 (1 created module + 1 created test file)

## Accomplishments

- `core/image_ops.py` (new, 472 lines): 15 pure functions — rotate (`_rotate_point`, `transform_box`, `transform_lines`, `transform_box_payload`, `rotate_page`, `rotate_boxes`), crop (`crop_page`, `_clip_quad`, `_clip_box`, `crop_boxes`, `crop_page_with_boxes`), resize (`resize_page`, `resize_boxes`), levels (`levels_lut`, `levels_page`) + the shared `_validate_image_mask` pre-op boundary (image_io.py:65-72 discipline, T-05-06)
- One rotation convention for image + mask + geometry (np.rot90 k=-1/1/2; CW `(x,y)→(h-1-y,x)`, CCW `(y,w-1-x)`, 180 `(w-1-x,h-1-y)`) — RESEARCH Pitfall 4 locked; two 180° compose to identity (test-proven)
- D-16 crop policy: fully-outside boxes dropped with a returned `dropped_count` (status-bar data), partial boxes clipped — bbox AND line quads — into post-crop page coordinates; touching-the-edge zero-area boxes dropped and counted
- D-18 mask purity: NEAREST resize asserted to emit only 0/255 (no soft alpha drift); rotate/crop asserted pixel-exact against `np.rot90` / exact slices; every return `.copy()`-detached (OWNDATA + not-shares-memory asserted)
- T-05-07 levels clamp: `levels_lut` internally normalizes `[min, max]` — inverted inputs (`white<=black`, `black=200,white=50`) yield monotone non-decreasing LUTs (diff >= 0 asserted)
- Fresh-object invariant (Pitfall 3 / T-05-08): every box transform builds a NEW frozen `Box` + fresh `TextBlock` + fresh lines list; `_snapshot_boxes` byte-identity guards assert originals untouched after every op — the API shape plan 05-04's stamp-shared triple push consumes
- 8 new unit tests, all green; full suite 485 collected / 484 passed / 1 failed — the sole failure is the pre-existing `test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip` 1px regression, plan 05-09's target (unchanged from baseline behavior)

## Task Commits

Each task was committed atomically:

1. **Task 1 (TRACER): Rotate 90° CW/CCW/180° — image + mask + box/line geometry, one path end-to-end** - `8db54ef` (feat)
2. **Task 2: Crop — exact slice + drop-fully-outside/clip-partial policy (D-16) with dropped count** - `ed8b997` (feat)
3. **Task 3: Resize (LANCZOS/NEAREST + int box scaling) + Levels (numpy LUT + white>black clamp)** - `b4ef148` (feat)

**Plan metadata:** (pending final docs commit)

## Files Created/Modified

- `manga_ai_studio/core/image_ops.py` (NEW) - pure numpy+PIL pixel + geometry math: rotate/crop/resize/levels page ops + box/line transforms; module docstring states the gui/canvas.py event-dispatch separation; `_validate_image_mask` pre-op validation; constants `MIN_RESIZE_DIM`/`MAX_RESIZE_DIM` (1..100000, UI-SPEC surface 26)
- `tests/test_core/test_image_ops.py` (NEW) - 8 unit tests: `test_rotate_transforms_all`, `test_rotate_composes_identity`, `test_rotate_rejects_bad_shapes`, `test_crop_drop_and_clip`, `test_crop_rejects_bad_input`, `test_crop_zero_area_dropped`, `test_resize_and_levels`, `test_resize_rejects_bad_input`; independent in-test copies of the rotation math (`_rotate_point_expected`) so module transcription errors surface

## Decisions Made

- **Post-crop coordinate frame:** bbox AND line quads are translated by `(-x, -y)` into post-crop page coordinates, keeping `TextBlock.xyxy == PageBox.box.as_tuple` — the plan's literal pre-translation shorthand ("bbox clamped to [2,1,6,4]") would desync the bbox from the line polygons (D-17 "no stale-lines shortcut"). The acceptance contract "post-crop coordinates" + "fully inside → translated bbox" settles it.
- **`levels_lut` clamp shape:** `[min(black, white), max(black, white)]` normalization before the formula — with `black == white` the LUT degenerates to a monotone threshold map; with inverted input it flips to the ascending range. Never an inverted render (T-05-07).
- **`levels_page` validation:** inline `(H,W,3)` check rather than `_validate_image_mask` — levels is geometry-free by design (D-15), the signature has no mask argument.
- **Tie-free test geometry:** `int(round(...))` is Python banker's rounding per the plan formula; test boxes were chosen so no coordinate lands on a `.5` tie (deterministic assertions).

## Deviations from Plan

None - plan executed exactly as written (one implementation-level correction of the plan's crop-coordinate shorthand documented above as a decision, not a deviation; behavior matches the plan's acceptance criteria and D-16/D-17 contract).

---

**Total deviations:** 0 auto-fixed (0 bug, 0 missing critical, 0 blocking)
**Impact on plan:** None — plan executed as written.

## Issues Encountered

- **numpy 2.x strict scalar promotion** (Rule 1 - test-only): `np.arange(240, dtype=np.uint8) % 256` raised `OverflowError: Python integer 256 out of bounds for uint8` — the modulo was unnecessary (240 < 256); dropped it. Test-only fix, no production impact.
- **Transient GUI-suite flake** (not a defect): one full-suite run showed `test_run_ocr_selected_dispatches_worker_not_inline` failing after a C-stack crash in a prior run; it passes in isolation and in every subsequent full run. Pre-existing Qt-test teardown flakiness, unrelated to this plan's headless module.
- **Crop `OverflowError` investigation** consumed one extra full-suite run — resolved as above.

## User Setup Required

None - no external service configuration required (zero new dependencies).

## Next Phase Readiness

- Ready for plan 05-04 (geometry-op undo): `rotate_boxes`/`crop_boxes`/`resize_boxes` return fresh PageBox lists — snapshot-push-safe; `levels_page` is geometry-free so it pushes image-only
- Ready for the GUI apply plans 05-06/05-07: `crop_page_with_boxes` is the single-seam crop apply; `rotate_page`/`resize_page` return `(image, mask)` pairs matching `mask_to_numpy_binary`/`numpy_binary_to_mask_qimage` boundaries
- Baseline re-measured at execution: 485 collected / 484 passed / 1 failed (pre-existing 05-09 regression unchanged; plan-time baseline was 462/461/1 — delta is 05-01's added tests + this plan's 8)

---
*Phase: 05-project-persistence-image-ops-export*
*Completed: 2026-08-08*
