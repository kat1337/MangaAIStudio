---
phase: 05-project-persistence-image-ops-export
plan: 04
subsystem: gui-undo-history
tags: [undo, redo, history, geometry-ops, pyqt, numpy, proj-04]

# Dependency graph
requires:
  - phase: 03 (Text Box Detection & Interaction)
    provides: unified-timeline undo()/redo() with per-type pop methods (D-10/D-11), _materialize_snapshot
  - phase: 05-02 (Image Ops Core)
    provides: fresh-object transform API (rotate/crop/resize/levels) that is snapshot-push-safe
  - phase: 05-09 (Wave 1)
    provides: full-suite baseline 493/493 green (the pre-existing test_gui_boxes.py regression fix)
provides:
  - push_geometry_state(image_patch, mask_qimage=None, boxes=None) — the stamp-shared triple push every image-op plan pushes through
  - undo()/redo() pop-all-with-max-stamp returning list[(kind, value)] ([] when empty)
  - MainWindow list-apply (_apply_undo_result) + extended Undo/Redo flash op-name set (rotate|crop|levels|resize)
  - _record_geometry_op_name hook for the geometry apply path
affects: [05-06-rotate-levels-resize, 05-07-crop, 05-08-export, verify-work UAT]

# Actuals (#2632) — pairs with the plan's `estimate` (18000 tokens); same scale (chars/4 over the realized diff).
actuals:
  tokens: 9857
  tasks: 2
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Stamp-shared triple push: ONE monotonic stamp across IMAGE+MASK+BOXES; undo/redo pop every store whose tail stamp equals the max"
    - "Group-shared stash stamp: a multi-store pop stashes all popped stores with ONE fresh stamp so redo() restores the whole op in one press (symmetric mirror)"
    - "Additive optional stash_stamp param: default None keeps Phase 3 fresh-stamp behavior — per-type pops untouched for all existing callers"

key-files:
  created: []
  modified:
    - manga_ai_studio/core/history_manager.py (push_geometry_state + list-returning undo/redo + stash_stamp params)
    - manga_ai_studio/gui/main_window.py (_apply_undo_result list, _undo_op_label_for_result, _record_geometry_op_name)
    - tests/test_history.py (7 new regression tests + 2 return-shape updates)
    - tests/test_core/test_history_boxes.py (3 return-shape updates)

key-decisions:
  - "Group stash stamp via optional stash_stamp param on the 6 per-type pop methods (default None = exact Phase 3 behavior): the plan's 'pop methods untouched' is honored behaviorally — ordinary calls are byte-identical; the geometry group pop shares ONE fresh stamp so redo() restores all three in one press (test_geometry_redo_restores_all_three requires it)"
  - "Undo/Redo flash op name resolved MainWindow-side: _record_geometry_op_name(op_name) is the hook plan 05-06/05-07's _apply_geometry_op calls before push_geometry_state; a multi-kind pop result flashes the recorded name, single-kind pops keep the Phase 3 kind labels"
  - "undo()/redo() return [] for empty stacks (was None) — the on_undo/on_redo `not result` guard covers both"
  - "test_core/test_history_boxes.py consumers updated to the list-of-one shape (the plan named only tests/test_history.py, but the full-suite-green criterion covers the boxes file; return-shape assertions only)"

patterns-established:
  - "Pattern 2 (RESEARCH): one-press geometry undo — stamp-shared triple push + pop-all-with-max-stamp; levels pushes image-only (mask/boxes None)"
  - "Push-side detachment on the geometry path: image .copy(), mask .copy(), boxes _materialize_snapshot (T-05-11)"

requirements-completed: [PROJ-04]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "push_geometry_state stamp-shared triple push — ONE stamp across IMAGE+MASK+BOXES with push-side detachment, optional mask/boxes, redo-clear + limit cap per touched store"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_history.py#test_geometry_push_stamps_all_stores"
        status: pass
      - kind: unit
        ref: "tests/test_history.py#test_geometry_push_omits_none_stores"
        status: pass
      - kind: unit
        ref: "tests/test_history.py#test_geometry_push_clears_redo"
        status: pass
      - kind: unit
        ref: "tests/test_history.py#test_geometry_push_detaches_patch"
        status: pass
    human_judgment: false
  - id: D2
    description: "One-press geometry undo/redo — undo()/redo() pop every store whose tail stamp equals the max, returning list[(kind, value)] ([] when empty); MainWindow applies the list image→mask→boxes and flashes the extended op-name set"
    requirement: PROJ-04
    verification:
      - kind: unit
        ref: "tests/test_history.py#test_geometry_undo_reverses_all_three"
        status: pass
      - kind: unit
        ref: "tests/test_history.py#test_geometry_redo_restores_all_three"
        status: pass
      - kind: unit
        ref: "tests/test_history.py#test_undo_returns_single_element_list"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_boxes.py (full GUI undo/redo suite green after the list-apply contract change)"
        status: pass
    human_judgment: false

# Metrics
duration: 14min
completed: 2026-08-08
status: complete
---

# Phase 5 Plan 4: Geometry-Op Undo Record Summary

**Stamp-shared triple push (`push_geometry_state`) + pop-all-with-max-stamp `undo()`/`redo()` returning `list[(kind, value)]`, with the MainWindow list-apply contract — ONE Ctrl+Z now reverses an image op's image + mask + boxes together, redo mirrors it in one press, and the Undo/Redo flash names rotate|crop|levels|resize**

## Performance

- **Duration:** 14 min
- **Started:** 2026-08-08T14:44:00Z
- **Completed:** 2026-08-08T14:58:14Z
- **Tasks:** 2 (both TDD: RED→GREEN committed separately)
- **Files modified:** 4

## Accomplishments

- `push_geometry_state(image_patch, mask_qimage=None, boxes=None)` — the phase's undo record: ONE monotonic stamp across IMAGE+MASK+BOXES, full-frame `(0,0)` image patch, push-side `.copy()`/`_materialize_snapshot` detachment (T-05-11), per-touched-store redo-clear + `limit` cap (T-01-16/T-05-08); levels pushes image-only
- `undo()`/`redo()` rewritten to pop EVERY store whose tail stamp equals the max, returning `list[(kind, value)]` (empty `[]` instead of `None`); ordinary single-store edits pop as one-element lists — Phase 3 semantics unchanged
- Redo mirror fixed at the source: a multi-store pop stashes all popped stores with ONE fresh shared stamp (`stash_stamp`), so `redo()` restores the whole op with a single press; per-type pop methods keep exact Phase 3 behavior for ordinary calls (WR-01 null guards preserved)
- `MainWindow._apply_undo_result` consumes the list, applying image→mask→boxes with one refresh per canvas layer; `on_undo`/`on_redo` flash the extended op-name set (`rotate|crop|levels|resize` via `_record_geometry_op_name` — the hook plan 05-06/05-07's `_apply_geometry_op` calls at push time)
- Full suite re-measured at 500 collected / 500 passed, 0 failed (493 baseline from 05-09 + 7 new tests — strict superset)

## Task Commits

Each task was committed atomically with separate RED and GREEN gates:

1. **Task 1: push_geometry_state — stamp-shared triple push (TDD)**
   - `eb9a58e` (test): failing geometry push tests (4 cases)
   - `8bf36f7` (feat): push_geometry_state + docstring contract
2. **Task 2: undo()/redo() pop-all-with-max-stamp + MainWindow list-apply (TDD)**
   - `5b06fc0` (test): geometry undo/redo/single-list tests + return-shape updates
   - `8f8b3a4` (feat): list-returning undo/redo, stash_stamp params, MainWindow list-apply + flash op-name set

**Plan metadata:** (final docs commit follows)

## Files Created/Modified

- `manga_ai_studio/core/history_manager.py` — `push_geometry_state` (new, 49 lines); `undo()`/`redo()` rewritten (pop-all-with-max-stamp, returns `list[(kind, value)]`); the 6 per-type pop methods gain the additive optional `stash_stamp` param (default None = unchanged Phase 3 behavior)
- `manga_ai_studio/gui/main_window.py` — `_apply_undo_result(result)` list iteration in image→mask→boxes order; `on_undo`/`on_redo` passthrough with `_undo_op_label_for_result`; `_undo_op_label` extended with rotate/crop/levels/resize; `_record_geometry_op_name` hook + `_last_geometry_op_name` init
- `tests/test_history.py` — 7 new unit tests (4 geometry-push + 3 geometry-undo/redo/single-list); 2 existing consumers updated to the list-of-one shape
- `tests/test_core/test_history_boxes.py` — 3 return-shape updates (list-of-one; empty-stack `[]`)

## Decisions Made

1. **Group stash stamp via optional `stash_stamp` param** — the plan's test `test_geometry_redo_restores_all_three` cannot pass with untouched pop methods: each pop stashes with its own fresh stamp, so the three geometry redo stashes never share one and redo would need three presses. Solution: the 6 pop methods accept `stash_stamp: int | None = None`; `None` (all ordinary callers, all existing tests) behaves byte-identically to Phase 3; the group pop in `undo()`/`redo()` passes ONE fresh stamp to every matched store. The plan's "pop methods untouched" is honored behaviorally — additive parameter, zero behavior change for existing calls, WR-01 guards untouched.
2. **Flash op-name resolution is MainWindow-side** — `undo()` returns no op metadata (the record shape is fixed by the plan), so the geometry apply path records the name via `_record_geometry_op_name(op_name)` before `push_geometry_state`; a multi-kind pop result flashes the recorded name, single-kind pops keep the Phase 3 kind labels. Known nuance: a levels undo (image-only geometry entry) will flash "inpaint" until plan 05-06 wires the recorder — no plan test asserts the levels undo flash.
3. **Empty stacks return `[]` (was `None`)** — `on_undo`/`on_redo` use the falsy guard, so both shapes are safe; `test_unified_undo_all_empty_returns_none` renamed to `..._returns_empty_list`.
4. **`tests/test_core/test_history_boxes.py` updated to the list shape** — the plan's `files` named only `tests/test_history.py`, but its own acceptance criterion ("Full suite green") requires the boxes file's 3 tuple-shape consumers; assertion-only updates, exactly the plan's anticipated "list-of-one" change.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Redo mirror cannot group the geometry triple with untouched pop methods**
- **Found during:** Task 2 (GREEN design of `redo()`)
- **Issue:** RESEARCH Pattern 2's pop-all algorithm pops every store with the max stamp, but the three redo stashes are created by three separate pop calls, each allocating its OWN fresh stamp — so the redo entries never share a stamp and `redo()` would restore one store per press (3 presses), violating the one-press contract the plan's own `test_geometry_redo_restores_all_three` demands.
- **Fix:** Added the additive optional `stash_stamp` param to the 6 per-type pop methods; `undo()`/`redo()` pass ONE fresh shared stamp to every store in a multi-store (group) pop. Ordinary single-store pops pass `None` → exact Phase 3 behavior (all existing tests unchanged).
- **Files modified:** manga_ai_studio/core/history_manager.py
- **Verification:** test_geometry_redo_restores_all_three passes; test_unified_redo_mirrors_undo (Phase 3 redo ordering) passes unchanged; full suite 500/500
- **Committed in:** 8f8b3a4 (Task 2 GREEN)

**2. [Rule 3 - Blocking] test_core/test_history_boxes.py consumers break under the list return shape**
- **Found during:** Task 2 (RED run)
- **Issue:** The plan's `files` for Task 2 lists only `tests/test_history.py`, but `tests/test_core/test_history_boxes.py` has 3 tuple-shape consumers of `undo()`/`redo()`; the plan's own "Full suite green" acceptance criterion makes updating them mandatory.
- **Fix:** Updated the assertions to the list-of-one shape (and the empty-stack `[]` contract); no test semantics changed.
- **Files modified:** tests/test_core/test_history_boxes.py
- **Verification:** Full suite 500/500
- **Committed in:** 5b06fc0 (Task 2 RED)

---

**Total deviations:** 2 auto-fixed (both Rule 3 - Blocking)
**Impact on plan:** Both fixes are direct consequences of the plan's own contract and acceptance criteria. No scope creep; no packages installed (T-05-SC).

## Issues Encountered

- **Tooling slip (self-inflicted, no code impact):** an Edit replacing `self._suppress_boxes_push = False` matched the occurrence inside a `finally:` block in a page-load method instead of `__init__` (the 8-space oldString matched a substring of the 12-space line), producing a transient IndentationError. Detected by the first post-edit pytest run; repaired by restoring the 12-space indent, moving the `_last_geometry_op_name` init to `__init__`, and re-running the suite green. Net diff is exactly the intended change.

## Known Stubs

None — no placeholder values, empty data sources, or TODO markers introduced. `_last_geometry_op_name` defaults to `None` with an "edit" flash fallback until plan 05-06 wires the recorder (documented hook, not a stub).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **Plan 05-06 (rotate/levels/resize) and 05-07 (crop):** ready — `_apply_geometry_op(op_name, geometry, transform_fn)` records the op name via `_record_geometry_op_name` and pushes `push_geometry_state(pre_image, pre_mask, pre_boxes)`; one Ctrl+Z reverses image+mask+boxes; the flash names the op; levels pushes image-only (`mask_qimage=None, boxes=None`)
- **Memory bound:** full-frame image patches at (0,0) are capped by the existing `limit=20` per store (T-05-08)
- No blockers.

---
*Phase: 05-project-persistence-image-ops-export*
*Completed: 2026-08-08*

## Self-Check: PASSED

- SUMMARY.md exists at `.planning/phases/05-project-persistence-image-ops-export/05-04-SUMMARY.md`
- All 4 task commits found in git history: `eb9a58e` (RED T1), `8bf36f7` (GREEN T1), `5b06fc0` (RED T2), `8f8b3a4` (GREEN T2)
- Full suite re-run: 500 passed, 0 failed
