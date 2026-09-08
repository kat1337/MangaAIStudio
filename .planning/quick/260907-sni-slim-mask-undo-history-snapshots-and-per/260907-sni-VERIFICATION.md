---
phase: quick-260907-sni
verified: 2026-09-08T03:13:29Z
status: human_needed
score: 6/6 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Real-session RAM spot check on a large project (the goal-level outcome). Open the 25-page ~35MP project (or any large project), perform normal editing — mask strokes + undos/redos on a page, Restore-tool strokes, page switches, a stroke after each page switch — while watching Task Manager / process RSS."
    expected: "No steady per-stroke/per-move climb toward the old 6→18 GB ratchet: mask-heavy work on one page adds tens of MB to ~0.5 GB worst case (20 undo + 20 redo packed entries @ 35 MP), not multi-GB; no OOM in a session that previously OOM'd."
    why_human: "End-to-end RSS over a real editing session needs the real project, a launched GUI, and minutes of interaction — the plan explicitly scopes programmatic verification to packed byte math ('asserted by packed-array byte math in tests, not RSS') and defers RSS measurement to a human spot-check (F7 out of scope)."
  - test: "Visual Restore-stroke check: with the Restore tool, drag a fast stroke across a region with wrong pixels and watch the display DURING the drag."
    expected: "The whole drag path shows restored (baseline) pixels live mid-stroke — no gaps between interpolated discs, no stale bands, no flicker from the bbox-only refresh; after release the image is fully restored and one Ctrl+Z undoes the stroke."
    why_human: "The mid-stroke pixel content of the persistent pixmap is programmatically proven (test_restore_midstroke_move_shows_all_interpolated_discs samples the pixmap mid-stroke), but on-screen compositing/repaint smoothness of the bbox + setPixmap re-sync path is visual."
---

# Quick Task 260907-sni — Slim mask-undo history snapshots and per-move churn — Verification Report

**Task Goal:** Fix the RAM climb during editing — slim mask-undo history snapshots (packed 1-bit planes, lossless for binary planes) and cut per-operation allocation churn (Restore tool persistent pixmap with bbox-only per-move refresh; recompose_mask cached per-plane binaries with complete invalidation incl. plane-REPLACEMENT sites). Symptom: 25-page ~35MP project climbed 6→18 GB while working, then OOM.
**Verified:** 2026-09-08T03:13:29Z
**Status:** human_needed (all 6 code-level must-haves verified with passing behavioral tests; 2 goal-level items need a human — real-session RAM + on-screen restore display)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | History entries retain packed-array bytes (was ~2x ARGB32 planes/entry), asserted by byte math in tests, not RSS | ✓ VERIFIED | `MaskPlanesSnapshot.manual_packed/erase_packed` are 1-D uint8 `ceil(h*w/8)` + `dims` (`manga_ai_studio/core/mask_planes.py:106-109`); `test_planes_snapshot_packed_representation` asserts nbytes == ceil(hw/8), dims == (h, w), and `not isinstance(..., QImage)`. Independent numeric check @ 5000x7000 (35 MP): entry 13.1 MB vs 284.4 MB (21.7x). Note: the must-have's "tens of MB" phrasing holds per-entry (13.1 MB); the 40-entry worst-case stash is 0.53 GB (11.38 GB before) — exactly what the SUMMARY reports (11.4 GB → 0.5 GB), so the operative ~22x reduction contract is met; the loose total-size wording is not a missed goal. |
| 2 | Ctrl+Z restores the exact pre-stroke composite; Ctrl+Shift+Z the post-stroke composite (round-trip pixel-equal) | ✓ VERIFIED | `test_packed_snapshot_round_trips_through_apply_undo_mask` (snapshot → wipe → apply_undo_mask → `np.testing.assert_array_equal` on `mask_to_numpy_binary`, auto plane intact), `test_undo_removes_stroke_keeps_auto_and_redo_restores`, `test_history_manager_mask_stack_packed_round_trip` — all pass. Restore path `canvas.apply_undo_mask` → `packed_to_mask_qimage` (unpack_binary ceil backstop) → untouched `set_planes` (`canvas.py:956-996`). |
| 3 | Geometry op undoes in ONE press across IMAGE+MASK+BOXES with the packed snapshot as the MASK value; apply_undo_mask hard-rejects bare QImages | ✓ VERIFIED | `test_geometry_group_undo_with_packed_mask_value` (unified pop returns kinds {boxes, image, mask}, popped value is a `MaskPlanesSnapshot`, applies cleanly) + `test_apply_undo_mask_hard_rejects_bare_qimage` (TypeError on QImage and on str). Production wiring confirmed: `main_window.py:1719` pushes `pre_planes` (packed) via `push_geometry_state`. |
| 4 | Restore stroke reuses ONE display pixmap across moves; full-frame rebuild exactly at stroke start + finish; committed pixels restore the baseline | ✓ VERIFIED | `test_restore_stroke_rebuilds_display_exactly_twice` (counter: press=1, moves=0, total=2), `test_restore_stroke_persistent_pixmap_built_once_and_propagates` (slot object identity across moves + cacheKey equality item↔slot), `test_restore_midstroke_move_shows_all_interpolated_discs` (union-rect refresh sampled mid-stroke), `test_restore_stamps_original_pixels`, `test_restore_emits_once_per_stroke` (single restore_committed). Code: persistent slot (`canvas.py:515`), press seed (`:1927`), union-of-move-rects (`:2115-2140`), bbox QPainter + `np.ascontiguousarray` + setPixmap re-sync + update() (`:2034-2073`), finish re-land + slot clear (`:2085-2089`). P-preview suppression preserved (`test_restore_suppressed_during_show_original`); restore_committed → `_on_restore_committed` → `push_image_action` wiring intact (`main_window.py:4066, 1963`). |
| 5 | Stroke-commit recompose converts at most the mutated plane(s); unmutated plane served from cache; composite byte-identical to the uncached path | ✓ VERIFIED | `test_recompose_cache_manual_only_stroke_converts_one_plane` (manual=1, erase=0 via call-count monkeypatch on the canvas module namespace), `test_recompose_cache_equivalence_across_mutation_sequences` (byte-equality after strokes, set_planes, clear_mask, consume_mask_display), `test_recompose_cache_cross_page_set_image_equivalence` (the adversarial folder-session case: set_image with NO set_planes → page B stroke commit is byte-identical to a fresh uncached recompose). |
| 6 | Lazy-open invariants intact: history entries only for visited/materialized pages; _materialize_page_state + D-11 flush untouched | ✓ VERIFIED | `git diff 4de491c..HEAD -- manga_ai_studio/gui/main_window.py` = the `_clean_plane_seed` change only (18 lines); `history_manager.py` diff is annotation/docstring renames only (`QImage`→`object` type comments, param rename; stack mechanics untouched); nfq seams (`_materialize_page_state`, `source_mas`, outgoing flush) absent from the diff; `tests/test_gui_project.py` 57 passed (nfq battery), `tests/test_history.py` green. The invariant is documented in the `apply_undo_mask` docstring (`canvas.py:972-975`). Invariant side verified by grep: strokes fire only via canvas event handlers on the current page. |

**Score:** 6/6 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `manga_ai_studio/core/mask_planes.py` | MaskPlanesSnapshot with manual_packed/erase_packed uint8 + dims; Qt-free at runtime | ✓ VERIFIED | Substantive (pack/unpack with T-08-02 length backstop, detached copy()); wired into canvas/history/main_window |
| `manga_ai_studio/core/mask_editor.py` | mask_qimage_to_packed / packed_to_mask_qimage boundary helpers | ✓ VERIFIED | Both present (`:229-255`), imported and used by canvas planes_snapshot/apply_undo_mask |
| `manga_ai_studio/gui/canvas.py` | Packed planes_snapshot + apply_undo_mask; persistent restore pixmap with bbox refresh; per-plane binary cache in recompose_mask | ✓ VERIFIED | All three present and wired; None-slot fallback + shape backstop included |
| `manga_ai_studio/gui/main_window.py` | zeros-packed _clean_plane_seed | ✓ VERIFIED | `np.zeros((h*w+7)//8)` + dims, no QImage allocation (`:4445-4469`) |
| `manga_ai_studio/core/history_manager.py` | Docstring/annotation sweep only, mechanics untouched | ✓ VERIFIED | Diff confirms type-comment/param renames only; `.copy()` duck-typing preserved |
| `tests/test_gui_mask_planes.py` + `tests/test_gui_canvas.py` | New regression tests; full suite ≥ 1322 passed, 0 failed | ✓ VERIFIED | 14+ new tests present and passing (see Behavioral Spot-Checks); suite count reconciles to 1336 collected (1322 baseline + 14 new) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| canvas.planes_snapshot | HistoryManager MASK stack | mask_qimage_to_packed → duck-typed .copy() push hook | WIRED | `_on_mask_modified` pushes `planes_snapshot()`; `.copy()` detaches all arrays |
| HistoryManager MASK stack | canvas.apply_undo_mask | unpack → packed_to_mask_qimage → set_planes | WIRED | `canvas.py:986-996`; round-trip tests pixel-equal |
| main_window._clean_plane_seed | First-stroke clean baseline | zeros-packed arrays + dims | WIRED | `test_first_stroke_seed_is_zeros_packed` + `test_first_stroke_seeds_clean_baseline_auto_untouched` |
| _restore_stamp bbox rects | Persistent pixmap display | union per move → ascontiguousarray → QPainter → setPixmap re-sync → update() | WIRED | `canvas.py:2034-2073`; cacheKey-equality test proves the refresh reaches the item |
| Plane mutation AND replacement sites | Cache invalidation → recompose cache reads | _invalidate_plane_bin_cache at all 10 sites | WIRED | Every write site instrumented: `set_image:551`, `clear:600`, `set_planes:845`, `consume:874/880`, `clear_mask:928`, dims-change `:1268` (full clears); `_dual_write_stroke:1902`, rect `:2174`, lasso `:2184` (per-plane). Grep sweep found zero un-instrumented production writes |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| recompose_mask | manual_bin/erase_bin | Live `_mask_manual`/`_mask_erase` QImages on miss; cache on hit | Yes (conversion-count test proves live conversion per mutation) | ✓ FLOWING |
| planes_snapshot | manual_packed/erase_packed | Live planes via mask_to_numpy_binary → packbits | Yes (byte-size + round-trip tests) | ✓ FLOWING |
| _refresh_restore_display_bbox | region | Live `_restore_work` sub-rect | Yes (mid-stroke pixel sampling = baseline values) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Union of Task 1+2+3 verify suites | pinned python -m pytest tests/test_gui_mask_planes.py tests/test_history.py tests/test_gui_canvas.py tests/test_gui_gap_closure.py tests/test_gui_tools_strip.py -q | 143 passed, 0 failed (34s) | ✓ PASS |
| nfq lazy-open battery | pinned python -m pytest tests/test_gui_project.py -q | 57 passed, 0 failed (38s) | ✓ PASS |
| Full suite minus documented-flake files | pinned python -m pytest -q --ignore=tests/test_gui_ocr_grab.py --deselect tests/test_gui_boxes.py::test_no_ghost_after_undo_and_scroll | 1302 passed, 0 failed (3:28, under the 4-min guard) | ✓ PASS |
| Count reconciliation | 1302 + 33 (test_gui_ocr_grab.py, collected-only) + 1 (deselected) = 1336 = 1322 baseline + 14 new | matches executor's full runs (1332+4f / 1334+2f, failures adjudicated) | ✓ PASS |
| Direct-paint bypass probe (verifier-written, deleted) | offscreen repro: set_image → set_auto_binary (populates cache) → QPainter paint on `_mask_manual` w/o invalidation → set_auto_binary → recompose | Stroke absent from composite → confirms the ONLY stale-serve path is a private-slot bypass; production `_dual_write_stroke` path freshly recomposes with the stroke | ✓ PASS (production correct) |

**Flake adjudication:** The executor's two full-suite runs failed only `test_gui_ocr_grab.py` members (Windows OS-clipboard starvation, documented in that module), `test_gui_boxes.py::test_no_ghost_after_undo_and_scroll` (viewport-grab flake), and one sfx/ocr membership flake — with a baseline worktree at pre-change commit 52252e7 reproducing the same class. My clean run passes all 1302 non-excluded tests in one shot; the excluded 34 are the two documented environmental-flake sources. No failure attributable to these changes.

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes declared or conventional for this phase. The verifier's one-off stale-cache probe (table above) substitutes for the SUMMARY's empirical claims about cache correctness and was deleted after the run.

### Requirements Coverage

Not applicable — quick task with no `requirements:` frontmatter and no REQUIREMENTS.md phase mapping. The PLAN's must_haves (6 truths, 5 artifacts, 4 key links) were used as the contract; all verified above.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| tests/test_gui_detection_boxes.py | 886-893 | `_seed_manual_stroke` paints directly on `canvas._mask_manual` (private-slot bypass, no invalidation); `test_dilation_live_redilate_grows_shrinks_keeps_strokes` still passes because its stroke-survival assert region [2:12, 2:12] overlaps the auto plane's [10:30, 10:30] at [10:12, 10:12] — the assert is masked, proven by the verifier probe | ℹ️ Info | No production impact (all production write sites are instrumented; probe confirms). Latent test-hygiene hazard of the same class the executor already fixed for `test_erase_ledger_survives_redilate` — recommend migrating this helper to `set_planes` in a future touch. No debt markers (TBD/FIXME/XXX) in any modified file |

### Deviations Review (executor's 3 — all sound, none weaken the contract)

1. **setPixmap re-sync after the bbox QPainter draw (Task 2)** — REQUIRED, not cosmetic: painting a QPixmap detaches it from the QGraphicsPixmapItem's implicit-sharing copy, so the plan's "do NOT call setPixmap per move" letter would leave the display stale. The re-sync is a shallow copy (no raster re-allocation); the full-frame fromImage rebuild still fires exactly twice per stroke (counter test). The plan's "pixmap() SAME object" behavior is correctly re-expressed as slot object identity + cacheKey sharing (PySide6 returns a fresh wrapper per pixmap() call — literal identity is unobservable).
2. **`is None` + shape-backstop cache miss check (Task 3)** — the plan's `cache.get(k) or convert` pseudocode would raise `ValueError: truth value of an array is ambiguous` on ANY cached multi-element array (including the legitimate all-zero plane); the fix is mandatory for the feature to function at all, and the shape backstop adds defense without changing semantics.
3. **Per-plane invalidation argument (Task 3)** — whole-dict clears at in-stroke mutation sites would make the required "unmutated plane converts ZERO times" behavior impossible; replacement sites all pass None (full clear). Strictly a refinement that the plan's own behavior clause demands.

### Human Verification Required

See `human_verification` frontmatter: (1) real-session RAM spot check on the large project — the goal-level outcome the byte-math contract deliberately proxies; (2) visual mid-stroke Restore display check. Everything code-level is machine-verified.

### Gaps Summary

None. All 6 must-have truths verified with passing behavioral tests (event-driven qtbot tests through the real handlers — not presence-only checks), all artifacts substantive and wired, all key links connected, no blocker anti-patterns, suite green (1302/1302 in the clean run; the only excluded tests are the two pre-existing environmental-flake sources reproduced at the pre-change baseline commit). Status is human_needed solely because the task goal's end result (no RAM climb toward OOM in a real editing session) is a performance/real-time outcome the plan itself routes to human verification.

---

_Verified: 2026-09-08T03:13:29Z_
_Verifier: Claude (gsd-verifier)_
