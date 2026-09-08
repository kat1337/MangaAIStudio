---
phase: quick-260907-sni
plan: 01
status: complete
subsystem: gui-canvas + core-history
tags: [memory, oom, undo-history, allocation-churn, mask-planes, restore-tool]
requires:
  - "quick-260907-nfq landed (lazy ImageFiles, _materialize_page_state, source_mas) — verified intact"
  - "08-02 three-plane mask model + plane-aware MASK history"
provides:
  - "Packed MaskPlanesSnapshot: manual/erase stored as 1-bit packed arrays + dims — ~22x smaller history entries (13.1 MB vs 284.4 MB per entry @ 35 MP) (F3)"
  - "Restore-stroke persistent display pixmap with bbox-only per-move refresh — full-frame QImage+QPixmap conversion once per stroke boundary, not per mouse-move (F4 restore half)"
  - "recompose_mask per-plane binary cache with mutation AND replacement invalidation — one-plane conversion per stroke commit (F5)"
  - "core/mask_editor boundary helpers: mask_qimage_to_packed / packed_to_mask_qimage"
affects:
  - "Session RAM climb: worst-case per-page mask history ~11.4 GB -> ~0.5 GB (20 entries + redo stash @ 35 MP); restore per-move churn ~30 MB/event -> bbox-sized; stroke-commit recompose churn ~halved"
tech-stack:
  added: []
  patterns:
    - "1-bit packed snapshot values duck-typed through the history stack (.copy() contract)"
    - "Persistent display pixmap + bbox QPainter refresh with setPixmap re-sync (Qt implicit-sharing detach)"
    - "Per-plane derived-binary cache with per-mutation-plane invalidation and full clears at replacement sites"
key-files:
  created: []
  modified:
    - manga_ai_studio/core/mask_planes.py
    - manga_ai_studio/core/mask_editor.py
    - manga_ai_studio/core/history_manager.py
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_gui_mask_planes.py
    - tests/test_gui_canvas.py
    - tests/test_gui_boxes.py
decisions:
  - "Snapshot packing is lossless for manual/erase because both planes are binary (alpha>0 == painted); the packed_to_mask_qimage rebuild lands as MASK_PAINT_COLOR RGBA8888 — every plane consumer thresholds alpha"
  - "Bbox refresh paints into the persistent pixmap then re-syncs via setPixmap(same wrapper): painting detaches the item's implicit-sharing copy, and the re-sync is a shallow copy with no raster re-allocation — the plan's 'no per-move setPixmap' letter would have left the display stale (Rule 1)"
  - "_invalidate_plane_bin_cache takes an optional plane: in-stroke mutations drop only the mutated plane (so the commit recompose converts erase zero times), REPLACEMENT sites (set_image re-seed, clear, _set_image_from_numpy dims branch, set_planes, clear_mask/consume fills) drop both — the checker's blocker fix"
  - "Cache hits checked with 'is None' (an all-zero cached array is a valid hit; the plan's 'cache.get(k) or convert' pseudocode would raise on ambiguous array truth) plus a defensive shape backstop"
metrics:
  duration: ~1h 15m
  completed: 2026-09-08
  tasks: 3
  commits: 6
actuals:
  tokens: 9400
  tasks: 3
  commits: 6
---

# Quick Task 260907-sni — Slim mask-undo history snapshots and per-move churn — Summary

**Packed mask history + stroke-boundary display rebuilds + cached recompose:** the MASK undo stack now stores 1-bit packed planes (~22x smaller entries: 13.1 MB vs 284.4 MB per entry @ 35 MP; worst-case page history 11.4 GB -> 0.5 GB), Restore strokes rebuild the display once per stroke boundary with bbox-only QPainter refreshes per mouse-move, and stroke-commit recompose converts only the mutated plane from a per-plane binary cache that is invalidated at every mutation AND plane-replacement site.

## What Was Built

### Task 1 — Packed MaskPlanesSnapshot (RED 4ae3207, GREEN c5774b4)
- `core/mask_planes.py`: `MaskPlanesSnapshot` fields are now `manual_packed`/`erase_packed` (1-D uint8, `ceil(h*w/8)` bytes) + `auto_packed` + `dims: tuple[int, int]`; the QImage fields are gone; `copy()` detaches all arrays; the module is fully Qt-free at runtime.
- `core/mask_editor.py`: `mask_qimage_to_packed` (pack over `mask_to_numpy_binary`) and `packed_to_mask_qimage` (`unpack_binary` with its `ceil(h*w/8)` length backstop, T-08-02) boundary helpers.
- `gui/canvas.py`: `planes_snapshot()` emits the packed triple + dims; `apply_undo_mask()` rebuilds planes via `packed_to_mask_qimage` through the untouched `set_planes`, keeps the `isinstance` hard-reject (TypeError on a bare QImage), and documents the nfq lazy-open invariant (history entries only exist for visited/materialized pages).
- `gui/main_window.py`: `_clean_plane_seed()` builds zeros-packed arrays — no QImage allocation; the first-stroke undo still restores the clean baseline.
- `core/history_manager.py`: docstring/annotation sweep only — MASK-stack values remain duck-typed `.copy()` objects; stack mechanics untouched (verified by `test_history_manager_mask_stack_packed_round_trip`).
- One-press geometry undo preserved: `push_geometry_state(packed_snapshot)` + unified `undo()` pops IMAGE+MASK+BOXES in one press (new GUI test asserts the group pop and that the popped MASK value is the packed snapshot).

### Task 2 — Restore display: one pixmap per stroke, bbox-only refresh (RED 75ea328, GREEN 1f9c8a0)
- `gui/canvas.py`: `_restore_display_pixmap` slot; `_refresh_restore_display` (full-frame rebuild) now runs exactly twice per stroke — press seed + finish re-land (T-l3l-03 PERF CHOICE superseded in the docstring). `_restore_stamp` returns its clipped disc rect; `_advance_paint` unions ALL discs stamped during the move (`_union_stroke_rect`) and calls the new `_refresh_restore_display_bbox`: `np.ascontiguousarray` sub-rect -> RGB888 QImage -> QPainter draw into the persistent pixmap -> `setPixmap` re-sync + `update()`. A None slot falls back to the full rebuild.

### Task 3 — recompose_mask per-plane binary cache (RED db13baa, GREEN e6c4d3e)
- `gui/canvas.py`: `_plane_bin_cache` + `_invalidate_plane_bin_cache(plane=None|'manual'|'erase')`. `recompose_mask` serves manual/erase binaries from cache on hit (composite formula and all call sites unchanged; still signal-silent). Invalidation: per-plane at stroke mutations (`_dual_write_stroke`, rect, lasso — so a manual-only stroke commit converts manual 1x / erase 0x); full clear at every REPLACEMENT site — `set_image`'s fresh-plane re-seed (runs on EVERY page display; folder-session switches carry NO set_planes), `clear()`'s plane nulling, `_set_image_from_numpy`'s dims-change re-seed, `set_planes`, and `clear_mask`/`consume_mask_display` fills.
- The checker-blocker cross-page test proves page B's first stroke-commit recompose is byte-identical to a fresh uncached recompose after `set_image`-only page switch (stale page-A binaries can never serve).

## Test Results (pinned interpreter: `C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe`)

| Suite | Result |
|---|---|
| Task 1 RED: `tests/test_gui_mask_planes.py` | 5 failed / 28 passed (packed-contract failures) |
| Task 1 verify: mask_planes + history + canvas + gap_closure | 121 passed |
| Task 1 adjacent: box_persistence + inpaint_gui + history_boxes | 50 passed; ghost test 1 passed in isolation |
| Task 2 RED: canvas restore battery | 4 failed (per-move rebuild / missing slot / missing method) |
| Task 2 verify: `tests/test_gui_canvas.py` + `tests/test_gui_tools_strip.py` | 64 passed |
| Task 3 RED: cache battery | 3 failed / 1 guard passed (missing cache API, erase converted) |
| Task 3 verify: mask_planes + canvas | 87 passed; adjacent gap_closure + inpaint_flow + box_persistence + history: 75 passed |
| Full suite run 1 | 1332 passed, 4 failed (5:21) — all 4 verified passing in isolation |
| Full suite run 2 | 1334 passed, 2 failed (4:56) — both verified passing in isolation |

Baseline: 1322 passed post-nfq; +14 new tests = 1336 collected. Both full-suite runs are consistent with that; zero failures attributable to the changes.

**Full-suite flake adjudication (per the orchestrator's protocol):** run 1 failures were `test_gui_boxes.py::test_no_ghost_after_undo_and_scroll` (the pre-authorized Qt viewport-grab flake — also passed standalone), 2x `test_gui_ocr_grab.py`, 1x `test_gui_sfx_editing.py`. Run 2 failed a different membership (`test_gui_boxes.py::test_run_ocr_selected_dispatches_worker_not_inline` + `test_gui_ocr_grab.py::test_grab_history_click_recopies_older_entry`) with `QtWarningMsg: Unable to obtain clipboard` in the log — the Windows OS-clipboard starvation the ocr_grab module itself documents. Decisive check: a temp worktree at the pre-change baseline commit (52252e7) fails the SAME ocr_grab tests (with a different second failure), and every failing test passes in isolation afterward. Pre-existing environment flakes, not regressions.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Bbox refresh must re-sync the item via setPixmap (Task 2)**
- **Found during:** Task 2 design probing (before implementation)
- **Issue:** The plan's "QPainter-draw into the persistent pixmap, then image_item.update(); do NOT call setPixmap per move" leaves the display stale: painting on a QPixmap detaches it from the QGraphicsPixmapItem's implicit-sharing copy (verified empirically — the item's cacheKey stays on the old buffer), so mid-stroke strokes would never appear.
- **Fix:** bbox QPainter draw into the persistent pixmap followed by `setPixmap(same wrapper)` — a shallow copy with no raster re-allocation and no QImage conversion; the fromImage full-frame rebuild remains exactly twice per stroke. The plan's "pixmap() is the SAME object" behavior is asserted as Python-object identity of the persistent slot + cacheKey sharing between item and slot: `QGraphicsPixmapItem.pixmap()` returns a fresh PySide6 wrapper per call, so literal wrapper identity is unobservable (also verified by probe).
- **Files modified:** manga_ai_studio/gui/canvas.py
- **Commit:** 1f9c8a0

**2. [Rule 1 - Bug] Cache-hit check must be `is None`, not truthiness (Task 3)**
- **Found during:** Task 3 implementation
- **Issue:** The plan's pseudocode `cache.get("manual") or mask_to_numpy_binary(...)` raises `ValueError: The truth value of an array...` for any cached multi-element array (a fully-transparent plane is a legitimate all-zero cache entry).
- **Fix:** explicit `if manual_bin is None or manual_bin.shape != (h, w)` miss check with a defensive shape backstop.
- **Files modified:** manga_ai_studio/gui/canvas.py
- **Commit:** e6c4d3e

**3. [Rule 3 - Blocking] Per-plane invalidation granularity (Task 3)**
- **Found during:** Task 3 implementation
- **Issue:** The plan specified `_invalidate_plane_bin_cache()` "clears it" (whole dict); whole-dict clears at the in-stroke mutation sites would invalidate the untouched erase plane too, making the required "manual converts once, erase ZERO times" behavior impossible.
- **Fix:** optional `plane` argument — stroke mutations drop only the mutated plane; all REPLACEMENT sites (the checker's blocker list: set_image re-seed, clear, _set_image_from_numpy dims branch, set_planes, clear_mask/consume fills) pass None for a full clear.
- **Files modified:** manga_ai_studio/gui/canvas.py
- **Commit:** e6c4d3e

### Execution Notes

4. **[Test-fidelity migration, Task 3]** `test_erase_ledger_survives_redilate` assigned `canvas._mask_erase` directly before recomposing — exactly the private-slot bypass the new cache makes unsafe. Migrated to the `set_planes` API with identical assertions (tests/test_gui_mask_planes.py, commit e6c4d3e).
5. **[Test-design notes]** `packed_to_mask_qimage` is imported inside the round-trip test so the RED run fails on assertions rather than collection (Task 1); the Task 2 mid-stroke union-rect test samples ~8 scene px past the previous endpoint — the literal "first disc of the move" is always within the previous endpoint's disc radius (step = brush/4 < radius), so the sampled point is provably stamped only by the move's early discs; `QPixmap.fromImage` monkeypatch counting was dropped in favor of the `_refresh_restore_display` call counter + slot-identity/cacheKey assertions (monkeypatching static methods on PySide6 classes is fragile).

No authentication gates. No CLAUDE.md/AGENTS.md conflicts (the pinned interpreter was used for every pytest run; the GUI was never launched; every bash command stayed well under the 4-minute guard).

## TDD Gate Compliance

Each task is a `test(...)` RED commit followed by a `feat(...)` GREEN commit, with the RED failures verified in-session for the right reasons: 4ae3207 -> c5774b4 (Task 1), 75ea328 -> 1f9c8a0 (Task 2), db13baa -> e6c4d3e (Task 3).

## Threat Model Follow-Through

- T-sni-01 (mitigate): snapshot dims + `ceil(h*w/8)` length validation retained — `packed_to_mask_qimage` routes through `unpack_binary`'s ValueError backstop; nothing new crosses persistence (the .mas loader keeps its own meta-dims cross-check; the D-11 flush still packs from the live planes directly).
- T-sni-02 (accept): the bbox QPainter is confined to mouse-event (GUI-thread) code with clamped rects (same clamps as `_restore_stamp`) and a None-slot defensive fallback (regression-tested).
- No new trust surface outside the plan's register.

## Byte-Math Spot Check (per plan verification, no GUI launch)

At 35 MP (5000x7000): one packed entry = 3 x ceil(HW/8) = 13.1 MB (was 2x ARGB32 planes + packed auto = 284.4 MB, 21.7x); 20 entries + redo stash on ONE page: 11.4 GB -> 0.525 GB. The must-haves byte-size tests encode the ratio at fixture scale (`test_planes_snapshot_packed_representation`: 40x30 -> 150 bytes/plane, not QImages).

## Out of Scope (untouched, per plan)

F2 (LRU eviction), F4's other half (`update_mask_display` per-move pixmap refresh on the brush path — pre-existing churn, explicitly deferred), F6 (vhh save payload double), S4/S6/S7, F7 (RSS instrumentation). nfq seams (`_materialize_page_state`, D-11 outgoing flush, `source_mas`) untouched and green.

## Self-Check: PASSED

- Files exist and are committed: mask_planes.py, mask_editor.py, history_manager.py, canvas.py, main_window.py + 3 test files (git diff 4de491c..HEAD = 8 files, +871/-114).
- Commits verified in `git log`: 4ae3207, c5774b4, 75ea328, 1f9c8a0, db13baa, e6c4d3e.
- Full suite run twice with the pinned interpreter; every non-baseline failure verified passing in isolation (pre-existing Windows clipboard/viewport-grab flake class; baseline worktree reproduces the same class at the pre-change commit).
- SUMMARY.md written but NOT committed, per orchestrator constraint; STATE.md/ROADMAP.md untouched (orchestrator-owned).
