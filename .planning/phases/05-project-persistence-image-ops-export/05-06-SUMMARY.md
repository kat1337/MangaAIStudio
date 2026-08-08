---
phase: 05-project-persistence-image-ops-export
plan: 06
subsystem: ui
tags: [pyqt, image-ops, rotate, levels, resize, undo, show-original]

# Dependency graph
requires:
  - phase: 05-02
    provides: core/image_ops pure transforms (rotate/crop/resize/levels) + the ONE rotation convention
  - phase: 05-04
    provides: push_geometry_state stamp-shared undo record + list-returning undo/redo
  - phase: 05-05
    provides: _snapshot_current_page save-side flush, original_verified flag, .mas load/verify
provides:
  - Tools-menu Image section (Rotate ▸ 90° CW/CCW/180°, Levels…, Resize…) wired end-to-end
  - _apply_geometry_op shared orchestration (gate → flush → pre-capture → transform → write-back → one undo entry → rebaseline → dirty → flash) — the plan 05-07 crop template
  - canvas.rebaseline_original() + set_image_from_numpy_preview() capture-suppressed display path
  - LevelsDialog live preview with exact Cancel restore / one-entry Apply (geometry-free, D-15)
  - ResizeDialog (dims/aspect lock/px-%/result label) + surface-29 Show Original gating
affects: [05-07 crop apply path reuses _apply_geometry_op, 05-08 exporter geometry_altered consumers]

# Actuals (#2632) — pairs with the plan's `estimate` (32000 tokens) on the SAME scale.
actuals:
  tokens: 16513    # chars/4 over the realized diff (8 files, 1324 insertions)
  tasks: 3
  commits: 4       # 3 task commits + the docs metadata commit

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "collector + preview driver dialogs (LoadTranslationsDialog template) — never mutate models, never push"
    - "_apply_geometry_op single orchestration seam for every synchronous image op"
    - "white>black cross-clamp as slider-range clamping (one mechanism, T-05-07)"
    - "full-frame geometry patch replace at (0,0) when frames differ — dims-changing undo restore"

key-files:
  created:
    - manga_ai_studio/gui/levels_dialog.py
    - manga_ai_studio/gui/resize_dialog.py
    - tests/test_gui_image_dialogs.py
  modified:
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/main_window.py
    - manga_ai_studio/core/history_manager.py
    - tests/test_gui_canvas.py
    - tests/test_gui_project.py

key-decisions:
  - "result_values (not `result`) on the dialogs — `result` shadows QDialog.result(); the LoadTranslationsDialog result_text/result_page_index precedent"
  - "set_mask/set_boxes skipped when the op did NOT transform that layer (levels returns None mask/boxes); the undo record mirrors it (image-only for levels)"
  - "Show Original gating reads _last_page_index (the D-11 seam rule) with a belt-and-suspenders bounds check"
  - "full-frame geometry patches at (0,0) with differing dims REPLACE the whole image on undo — the T-01-15 clip would truncate the pre-op frame"
  - "pop_image_undo/redo stash the FULL current image for dims-changing geometry records (the region slice would clip the redo frame)"

patterns-established:
  - "Pattern 1: _apply_geometry_op(op_name, geometry, transform_fn, flash) — one seam for gate/pre-capture/write-back/undo/rebaseline/dirty/flash"
  - "Pattern 2: transform_fn returns (image, mask_bin|None, boxes|None) — None = the layer is NOT part of the op (levels)"
  - "Pattern 3: dims-changing full-frame patch rule on the undo apply side (canvas) + stash side (history)"

requirements-completed: [PROJ-04]

coverage:
  - id: D1
    description: "Rotate 90° CW/CCW/180° applies silently via the Tools menu — image + mask + boxes transform together, ONE geometry undo entry, Ctrl+Z restores all three, geometry_altered True, status flash, Show Original re-baselines to the post-op image"
    requirement: PROJ-04
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_image_dialogs.py#test_rotate_90cw_end_to_end"
        status: pass
      - kind: unit
        ref: "tests/test_gui_canvas.py#test_rebaseline_original_after_op"
        status: pass
    human_judgment: false
  - id: D2
    description: "Levels dialog — 0/255/1.00 defaults, white>black cross-clamp (no inverted map ever renders), live preview without undo pushes or baseline poisoning, Cancel restores byte-identical with zero entries, Apply pushes exactly one image-only geometry-free entry"
    requirement: PROJ-04
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_image_dialogs.py#test_levels_cancel_restores_exactly"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_image_dialogs.py#test_levels_apply_pushes_one_entry"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_image_dialogs.py#test_levels_defaults_and_clamp"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_image_dialogs.py#test_levels_preview_no_baseline_poison"
        status: pass
    human_judgment: false
  - id: D3
    description: "Resize dialog — current-dims init, aspect lock (rounded ≥1), px/% toggle with live Result label, ranges 1..100000; Apply = LANCZOS image / NEAREST binary-strict mask / int-scaled boxes, one geometry entry, geometry_altered, resized-dims flash"
    requirement: PROJ-04
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_image_dialogs.py#test_resize_dialog_contract"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_image_dialogs.py#test_resize_apply_end_to_end"
        status: pass
    human_judgment: false
  - id: D4
    description: "Show Original gating (surface 29, D-06): disabled + not-found tooltip when the current page's original is unverified (.mas-loaded); normal sessions keep the inherited gating; the _original_image_numpy cache re-baselines after every image op"
    requirement: PROJ-04
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_project.py#test_show_original_gating"
        status: pass
    human_judgment: false

# Metrics
duration: 42min
completed: 2026-08-08
status: complete
---

# Phase 05 Plan 06: Image-op GUI layer — Rotate/Levels/Resize with one-press undo and D-14 Show Original re-baseline

**Tools-menu Rotate actions + Levels/Resize dialogs wired end-to-end through one `_apply_geometry_op` seam: silent pixel+mask+box transforms via core/image_ops, ONE geometry undo entry per op (stamp-shared triple push), Show Original re-baseline after every op, geometry_altered set only by geometry ops (never levels), and the D-06 Show Original gating.**

## Performance

- **Duration:** 42 min
- **Started:** 2026-08-08T16:37:00Z
- **Completed:** 2026-08-08T17:19:17Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments
- **Rotate end-to-end (TRACER):** Tools ▸ Rotate ▸ 90° CW/CCW/180° applies silently — image `np.rot90`-exact, mask binary-exact, boxes + line quads rotated via `image_ops.rotate_boxes` — with ONE `push_geometry_state` record; a single Ctrl+Z restores image+mask+boxes together; `geometry_altered` marked; status flashes the rotate copy; Show Original re-baselines to the post-op image (D-14).
- **Levels dialog:** black 0 / white 255 / gamma 1.00 defaults with the white>black cross-clamp (white min = black+1, black max = white−1 — one mechanism, no inverted map ever renders); live in-place preview through the new capture-suppressed `set_image_from_numpy_preview` path (no pushes — Pitfall 9, no baseline poison — Pitfall 5); Cancel restores the pre-dialog image byte-identical with zero undo entries; Apply pushes exactly one image-only entry (geometry-free, D-15 — mask/boxes untouched, `geometry_altered` unchanged, A4).
- **Resize dialog + Show Original gating:** W/H spinboxes at current dims (1..100000 px), px/% toggle (percent applies to the current dimension), aspect lock checked by default (dominant field recomputes the other, rounded ≥1), live "Result: {w} × {h} px" label; Apply = LANCZOS image / NEAREST binary-strict mask / int-scaled boxes with one entry and the "Resized to {w} × {h}." flash; surface-29 gating disables Show Original with the "original file not found" tooltip when the current page's original is unverified.
- **Undo fix for dims-changing ops:** full-frame geometry patches now restore faithfully across frame changes (rotate/resize) on both the canvas apply side and the history stash side.

## Task Commits

Each task was committed atomically:

1. **Task 1: Rotate end-to-end (TRACER)** - `2af4e72` (feat)
2. **Task 2: Levels dialog — live preview + Cancel-restores-exactly + Apply-pushes-one** - `8e0070e` (feat)
3. **Task 3: Resize dialog + Show Original gating** - `e0a2cb1` (feat)

**Plan metadata:** (final docs commit)

## Files Created/Modified
- `manga_ai_studio/gui/levels_dialog.py` (NEW) - `LevelsDialog` collector+preview driver: black/white/gamma controls, white>black cross-clamp, preview callback, result collector; never pushes (Pitfall 9)
- `manga_ai_studio/gui/resize_dialog.py` (NEW) - `ResizeDialog`: W/H spinboxes (1..100000), px/% toggle with stable result conversion, aspect lock, live result label, result collector
- `tests/test_gui_image_dialogs.py` (NEW) - rotate end-to-end + levels contract + resize contract tests (10 tests)
- `manga_ai_studio/gui/canvas.py` - `rebaseline_original()` (D-14), `set_image_from_numpy_preview(capture_original)`, `_set_image_from_numpy` refactor, full-frame geometry patch replace in `apply_undo_image`
- `manga_ai_studio/gui/main_window.py` - Tools-menu Image section, `_apply_geometry_op`, `_rotate_page`, `_on_levels`, `_on_resize`, image-op gating, Show Original gating
- `manga_ai_studio/core/history_manager.py` - full-frame stash in `pop_image_undo`/`pop_image_redo` for dims-changing records
- `tests/test_gui_canvas.py` - `test_rebaseline_original_after_op`, `test_preview_path_does_not_capture_original`
- `tests/test_gui_project.py` - `test_show_original_gating`

## Decisions Made
- **`result_values` instead of the plan's literal `self.result` on both dialogs** — `result` shadows `QDialog.result()` (the LoadTranslationsDialog precedent: `result_text`/`result_page_index`); the collector contract is unchanged.
- **Layer transforms are explicit:** `transform_fn` returns `(image, mask_bin|None, boxes|None)`; `None` means the op does NOT touch that layer — levels passes `(img, None, None)` so `set_mask`/`set_boxes` are skipped and the undo record is image-only (`push_geometry_state(mask_qimage=None, boxes=None)`).
- **Show Original gating reads `_last_page_index`** (the plan's literal contract; the D-11 seam rule) with a bounds check instead of `_current_page_index()`.
- **Full-frame geometry patches at (0,0) with differing dims replace the whole image on undo** — the T-01-15 clip path assumes same-frame patches and would truncate the pre-op frame; region patches (non-origin) keep the clip.
- **`pop_image_undo`/`pop_image_redo` stash the full current image** for dims-changing records — the region slice would clip the redo stash and break one-press redo after rotate/resize.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Geometry undo could not restore dims-changing ops (rotate/resize)**
- **Found during:** Task 1 (test_rotate_90cw_end_to_end — the tracer's own Ctrl+Z assertion)
- **Issue:** `canvas.apply_undo_image`'s T-01-15 bounds clip assumes the patch and the current image share a frame. A geometry record is a full-frame PRE-op patch at (0,0); after rotate the post-op frame differs, so the clip truncated the restore to a sub-rect and the image never returned to the pre-op state (mask/boxes restored fine — image did not). Symmetrically, `pop_image_undo`/`pop_image_redo` stashed `current_img[y:y+h, x:x+w]` — a dims-clipped slice that would corrupt redo.
- **Fix:** `apply_undo_image` replaces the whole image when the patch is at (0,0) with dims differing from the current frame (a full-frame geometry record); non-origin patches keep the T-01-15 clip. `pop_image_undo`/`pop_image_redo` stash the full current image for the same records.
- **Files modified:** `manga_ai_studio/gui/canvas.py`, `manga_ai_studio/core/history_manager.py`
- **Verification:** the tracer's Ctrl+Z assertion now passes (image+mask+boxes restored together); full suite green
- **Committed in:** 2af4e72 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary for the plan's core truth — "ONE Ctrl+Z restores image+mask+boxes together" was unachievable without it for dims-changing ops. No scope creep.

## Issues Encountered

- **`test_levels_preview_no_baseline_poison` initial write asserted the preview mutation persists after Cancel** — wrong expectation: the cancel path restores the base exactly (that IS the contract). Reworked to capture the canvas mid-dialog (proving previews ran) and assert the baseline/cancel state after.
- **Qt tooltip fallback:** `QAction.toolTip()` returns the action text when the tooltip is empty, so the normal-state assertion uses "not-found copy absent" rather than an empty string.

## User Setup Required

None - no external service configuration required.

## Self-Check: PASSED

- Files verified on disk: levels_dialog.py, resize_dialog.py, test_gui_image_dialogs.py
- Commits verified in git log: 2af4e72 (Task 1), 8e0070e (Task 2), e0a2cb1 (Task 3)
- Full suite at completion: 525 passed / 0 failed

## Next Phase Readiness
- `_apply_geometry_op` is the ready-made template for plan 05-07's crop apply path (both the canvas tool and the numeric dialog funnel through it).
- `geometry_altered` per page is now maintained by geometry ops only — plan 05-08's exporter can read it for the D-22 `_ocr.json` location rule.
- The dims-changing full-frame undo fix de-risks crop (another dims-changing op) for free.

---
*Phase: 05-project-persistence-image-ops-export*
*Completed: 2026-08-08*
