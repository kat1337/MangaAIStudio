---
phase: quick-260826-u9m
plan: "01"
subsystem: gui
tags: [show-original, d06-original-reference, project-reopen, canvas-preview-state, page-navigation]
requires:
  - D-06 original.json verify at load (imf.original_verified + imf.path from _build_image_file_from_parsed)
  - EditorCanvas preview state trio (_original_image_numpy / _inpainted_qimage / _showing_original)
provides:
  - EditorCanvas.set_image_from_numpy_page(rgb, original_baseline=None) page-display seam
  - MainWindow._decode_original_reference(imf) lazy on-disk D-06 decode with dims guard
affects:
  - Show Original (P) pixel source after Save Project + reopen
  - cross-page baseline bleed via the numpy display paths
tech-stack:
  added: []
  patterns:
    - page displays FULLY redefine per-page preview state (capture-if-None retired for page switches; op write-backs keep it per D-14)
    - fail-graceful decode fallback family (OSError / ValueError / DecompressionBombError -> None), T-05-03 lineage
key-files:
  created: []
  modified:
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_gui_canvas.py
    - tests/test_gui_project.py
decisions:
  - Seam runs the shared display machinery once then explicitly rewrites all three preview slots — never capture-if-None; baseline falls back to the incoming page's OWN pixels so a foreign page can never bleed.
  - Dims guard in _decode_original_reference degrades geometry-altered pristine files to the embedded fallback instead of desyncing sceneRect/mask overlay dims mid-toggle.
  - sha256 NOT re-run at decode time — verify_original gated load; mid-session corruption surfaces as OSError -> graceful fallback.
metrics:
  duration: ~34 min
  completed: 2026-08-27
status: complete
actuals:
  tokens: 5600        # chars/4 over realized diff (~403 lines across 4 files); plan estimate 60000 was much larger than realized
  tasks: 2
  commits: 2
---

# Phase Quick Plan 01: Show Original (P) must reference the ORIGINAL FILE ON DISK Summary

**One-liner:** After Save Project + reopen, P now decodes the verified D-06 `original.json` reference from disk for its baseline (lazily, per displayed page, dims-guarded) while page switches fully redefine canvas preview state — killing both the saved-image-as-"original" defect and the cross-page stale-baseline bleed.

## What Was Done

### Task 1 — `EditorCanvas.set_image_from_numpy_page` seam + unit tests (commit 5d60510)

New public seam beside the other numpy display variants:

- Validates BOTH `rgb` and (when present) `original_baseline` against the same `(H,W,3) uint8` ValueError contract BEFORE any display mutation (a malformed baseline leaves the displayed pixmap untouched).
- Runs `_set_image_from_numpy(rgb, None, capture_original=False)` once — inherits the crop-state clear (05-07), different-dims plane re-seed (08-02), Pitfall-2 copy-detached pixmap, and empty-state refresh for free.
- Then EXPLICITLY redefines all three preview slots: `_original_image_numpy` = caller baseline `.copy()` else `rgb.copy()` (the page's own displayed pixels — never a foreign page's baseline, never None from the fresh-canvas-captures-None edge); `_inpainted_qimage` = the displayed QImage (`has_inpaint_result()` True so P gating works on freshly loaded pages); `_showing_original = False`.
- Docstring restricts callers to PAGE DISPLAYS ONLY; op write-backs and undo stay on `set_image_from_numpy` (D-14 governs those). The old methods' internals were NOT touched.

4 new unit tests in `tests/test_gui_canvas.py`: disk-baseline seeding + toggle round-trip; exact-bleed-state rebasing (foreign baseline + stale flag erased, no-baseline fallback = own pixels); invalid-baseline raises pre-mutation; fresh-canvas inpaint claim.

### Task 2 — MainWindow wires the D-06 disk reference into both page-display sites + GUI regressions (commit 1915859)

- New private helper `MainWindow._decode_original_reference(imf)` near `_build_image_file_from_parsed`: returns None unless `original_verified` AND `current_image` present; resolves `imf.path` inside try(OSError, ValueError); PIL-decodes like the embedded blob (`.convert("RGB")`, `.copy()` detach, catching OSError/ValueError/Image.DecompressionBombError); **dims guard** compares decoded vs `current_image` shape[:2] -> None on mismatch (a geometry-altered page's pristine file legitimately differs; swapping sizes during a toggle would desync sceneRect/mask dims). No sha256 re-run — load-time `verify_original` is the gate.
- Site 1 wired: `on_page_selected` Step 3 (~line 2096) now calls `set_image_from_numpy_page(imf.current_image.copy(), baseline)` with the extended CR-01/D-06 comment block (pristine-ref seeding + fallback rationale + gating-contract unchanged).
- Site 2 wired: `_display_page_state` (~line 2967) identical replacement plus a docstring sentence pointing at the D-06 seeding. Intended semantic upgrade documented inline: after reopen + a NEW inpaint, P shows the PRISTINE disk original by design; only `_apply_geometry_op`'s tail `rebaseline_original()` may move the baseline mid-session (D-14 unchanged).
- Line :1486 (geometry-op write-back) and :6022 (inpaint bbox composite; formerly ~:5958 before insertions) verified untouched.

3 new GUI regression tests in `tests/test_gui_project.py` driving REAL save/reopen/navigation flows through stubbed dialogs: `test_show_original_uses_persisted_original_after_reopen` (baseline = pristine disk pixels, display = edited embed, toggle round-trip, action enabled), `test_show_original_dims_mismatch_falls_back_to_embedded` (60x40 crop vs square pristine file — dims guard rejects, fallback = cropped embed, open/navigation raise nothing), `test_page_switch_seeds_baseline_per_page_no_bleed` (end-to-end nav to page 2 seeds page 2's own pristine baseline, no stale toggle, display = page 2's edit).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Missing dims guard in the first cut of `_decode_original_reference`**
- **Found during:** Task 2 (by the plan's own regression test)
- **Issue:** The initial edit returned the decoded array directly from the try block, omitting the decoded-vs-current_image shape[:2] comparison entirely.
- **Fix:** Decode into a variable, guard, then return. Commit includes the corrected version.
- **Commit:** 1915859

**2. [Test-fixture correction] Solid-color pages made the planned flip edits pixel identities**
- **Found during:** Task 2
- **Issue:** The plan's test recipes build pages via `_make_pages` (solid constant colors). On solid images `np.flipud(pristine)` == `pristine`, so the mandated assertion "baseline equals pristine (and NOT the flipped embed)" is mathematically unsatisfiable and the no-bleed navigation asserts degenerate.
- **Fix:** Added `_seed_two_tone` helper that overwrites pages with deterministic two-band non-uniform PNGs (row split => flipud is a real change; distinct bands per page).
- **Files modified:** tests/test_gui_project.py
- **Commit:** 1915859

**3. [Recipe hardening] Direct `current_image` mutation alone would be clobbered at save time**
- **Found during:** Task 2 planning of test A/C
- **Issue:** `_snapshot_current_page` refreshes the CURRENT page's `current_image` from the live canvas during save; mutating the slot without displaying the edit would either be overwritten or leave embed/flush inconsistent.
- **Fix:** Tests set the slot AND display the edited array through the real seam (`set_image_from_numpy` pre-save; `recompose_mask()` after the crop re-seeds planes so validate_meta's mask-dims==image-dims rule holds).

**4. [Cosmetic] Navigation uses the sibling-test pattern** `select_path(path)` followed by explicit `on_page_selected(path)` (as `test_page_navigation_uses_embedded_image_for_missing_original` does) rather than relying on signal delivery timing.

No authentication gates occurred. No known stubs introduced.

## Threat Model Compliance

- T-u9m-01 (accept): guards mirror the embedded-blob decode family exactly.
- T-u9m-02 (mitigate): `Image.DecompressionBombError` caught -> None fallback; decode is lazy per displayed page, never eager over all pages. Implemented as specified.
- No new trust surface beyond the plan's register; no package installs.

## Verification Results

| Check | Command | Result |
|-------|---------|--------|
| Task 1 | pinned pytest `tests/test_gui_canvas.py -x -q` | 40 passed (36 pre-existing + 4 new) |
| Task 2 part 1 | pinned pytest `tests/test_gui_project.py tests/test_gui_canvas.py -q` | 71 passed (31 project incl. 3 new + 40 canvas) |
| Full suite | pinned pytest `-q` | **1169 passed, 0 failed** (142s; strict superset of the 1161-passing baseline) |
| Static sanity | grep call sites | only main_window.py:2096 + :2967 use `set_image_from_numpy_page`; :1486 + :6022 still call `set_image_from_numpy` |

## Self-Check: PASSED

- manga_ai_studio/gui/canvas.py — EXISTS (seam at ~line 993)
- manga_ai_studio/gui/main_window.py — EXISTS (`_decode_original_reference`; sites :2096, :2967)
- tests/test_gui_canvas.py — EXISTS (4 new tests passing)
- tests/test_gui_project.py — EXISTS (3 new tests passing)
- Commit 5d60510 — FOUND
- Commit 1915859 — FOUND
