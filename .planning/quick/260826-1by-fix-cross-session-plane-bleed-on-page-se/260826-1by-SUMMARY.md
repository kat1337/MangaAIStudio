---
phase: quick-260826-1by
plan: 01
subsystem: gui
tags: [mask-planes, d11-seam, session-swap, corruption-guard, qt]
requires:
  - D-11 per-page mask/plane persistence seam (on_page_selected)
  - core/mask_planes.py pack_binary/unpack_binary
provides:
  - None-resetting session swaps (_set_pages, _load_project_session, _load_single_page_mas)
  - _plane_dims_match contamination guard on all outgoing persistence sites
  - _safe_unpack ValueError backstop on the six display-path restore sites
affects: [batch dispatch flush, save-side snapshot]
tech-stack:
  added: []
  patterns:
    - dims-agreement guard returns False only on measurable mismatch (unknown sides keep legacy behavior)
    - corrupt-blob degradation to "no plane" instead of slot-level crash
key-files:
  created:
    - .planning/quick/260826-1by-fix-cross-session-plane-bleed-on-page-se/260826-1by-SUMMARY.md
  modified:
    - manga_ai_studio/gui/main_window.py
    - tests/test_gui_project.py
decisions:
  - Loaders reset _last_page_index to None BEFORE the swap is observable and re-establish index 0 after _display_page_state — plan's literal "None only" regressed Show Original gating (test_show_original_gating caught it); both seam protection and gating now hold.
  - _plane_dims_match gates Step 1b boxes snapshot too (plan-instructed — same stale-index failure mode).
  - _flush_current_canvas_mask_to_data_model got the composite-write gate even though it packs no planes (plan named the site; a mismatched canvas must not flush anywhere).
metrics:
  duration: ~35 min active (two runs; first run returned empty after context gathering only)
  completed: 2026-08-26
  tasks: 3
  commits: 3
status: complete
actuals:
  tokens: 2400 # chars/4 over realized diff (241+/29- in 2 files)
  tasks: 3
  commits: 3
---

# Quick Task 260826-1by Summary

**Objective:** Kill cross-session plane bleed — `on_page_selected` persisting outgoing canvas planes into the WRONG page's `ImageFile` after a session swap (wrong-dims packed blobs + repeated `ValueError` crash loop killing text-box restoration).

**One-liner:** Session swaps retire `_last_page_index` before the new list is observable, outgoing persistence refuses canvas-vs-page dimension mismatches, and corrupt plane blobs degrade to "no plane" with text boxes intact.

## Tasks Completed

| Task | Name | Commit | Result |
| ---- | ---- | ------ | ------ |
| 1 | Session-swap hygiene (`_last_page_index` reset on every image_files swap) | `3f25965` | All three swap sites reset to `None`; existing suite green after loader sequencing fix |
| 2 | Dimension guard on outgoing persistence + unpack restore backstop | `721704b` | `_plane_dims_match` + `_safe_unpack` helpers; guards at on_page_selected Step 1/1b, `_snapshot_current_page`, `_flush_current_canvas_mask_to_data_model`; six display-path unpack sites wrapped |
| 3 | Regression tests (TDD: RED verified against base, then GREEN) | `e05a71b` | 3 tests added; RED proven at base `bbc6a4c`, GREEN in tree; full suite 1162 collected |

## Verification

- **RED gate:** all three new tests fail against pre-fix code for exactly the predicted reasons (stale seam index `1` observed mid-swap; sentinel slots overwritten with a foreign 450-byte blob; raw `ValueError` escaping `_display_page_state`). Verified via throwaway git worktree at `bbc6a4c`, removed afterwards.
- **GREEN:** `tests/test_gui_project.py` 28 passed; Task-2 verify set (test_gui_project + test_gui_batch + test_box_persistence) 66 passed.
- **Full suite (pinned interpreter `3.14.2`):** `1161 passed, 1 failed, 1162 total`. The single failure (`tests/test_gui_boxes.py::test_no_ghost_after_undo_and_scroll`) is pre-existing and environment-dependent — it fails identically at base `bbc6a4c` (verified), touches no MainWindow code, and sits outside this task's scope. Prior recorded baseline 1159 passed + these 3 new tests = 1162 total ✓ strict superset.
- **Grep checks:** every `self.image_files =` site (1883 / 3042 / 3086) sits in a swap block resetting `_last_page_index = None`; both display paths (`on_page_selected`, `_display_page_state`) call `unpack_binary` only via `_safe_unpack`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Loader reset-to-None regressed Show Original gating**
- **Found during:** Task 1 verify (`test_show_original_gating` failed)
- **Issue:** Plan step 2/3 said change `self._last_page_index = 0` → `None` in `_load_project_session` / `_load_single_page_mas`. But `_refresh_action_states` reads `_last_page_index` as `gating_idx` to disable Show Original for unverified originals — `None` silently skipped that check, leaving Show Original wrongly enabled after opening an unverified-original project.
- **Fix:** Reset to `None` BEFORE the swapped-in list becomes observable (seam protection during the vulnerable window), then re-establish `_last_page_index = 0` right after `_display_page_state(page_files[0])` + history reset — at which point the canvas legitimately holds page 0's own restored state, so seam persistence for post-open edits AND the gating read both work.
- **Files modified:** manga_ai_studio/gui/main_window.py
- **Commit:** 3f25965

**2. [Transient, not a defect] test_gui_batch timeout flake**
- **Observed once** mid-suite under `-x`: `test_batch_detect_restores_current_page_mask_on_canvas` hit a 5s `qtbot.waitUntil` timeout. Passed deterministically in isolation and in two full reruns of the 66-test verify set. My guards are synchronous GUI-thread checks and cannot block the worker pool.

**3. [Out-of-scope discovery] Pre-existing failure in unrelated file**
- `tests/test_gui_boxes.py::test_no_ghost_after_undo_and_scroll` fails identically at base `bbc6a4c` and in isolation (viewport pixel-grab red-tint assertion, G=206). Environment-dependent rendering behavior, untouched file, zero MainWindow involvement. Not fixed per scope-boundary discipline — flagging for follow-up as its own investigation.

## TDD Gate Compliance

Plan-level type is not `tdd`, but Task 3 carries `tdd="true"`. Because the plan orders fix-tasks (1–2) before the test task (3) with atomic per-task verifies, the literal write-tests-first sequence was impossible without breaking Task 1/2 verifies. Compromise executed: fixes committed first, tests written second, RED honestly demonstrated retroactively against base commit `bbc6a4c` in a disposable worktree (all three failed with the predicted root behaviors), then GREEN confirmed in-tree. Gate sequence present: `feat(721704b)` → `test(e05a71b)`; no refactor needed.

## Known Stubs

None.

## Threat Mitigations Delivered

| Threat | Mitigation | Where |
| ------ | ---------- | ----- |
| T-Q1B-01 Tampering (wrong-page plane packing) | `_plane_dims_match` guard skips ALL Step-1 writes (composite mask + 3 planes + boxes snapshot) on dims mismatch, loguru warning names page + both dim pairs | main_window.py: on_page_selected, _snapshot_current_page, _flush_current_canvas_mask_to_data_model |
| T-Q1B-02 Tampering (corrupt packed blobs) | `_safe_unpack` catches ValueError per plane, logs slot + both lengths, degrades to None — six display-path sites wrapped; batch-derived sites left alone (validated upstream, plan scope discipline) | main_window.py: on_page_selected ×3, _display_page_state ×3 |
| T-Q1B-03 DoS (frozen-index crash loop) | `None` reset breaks the write-crash cycle at every swap; backstop removes the crash itself | main_window.py: all swap sites |

## Self-Check: PASSED

- `manga_ai_studio/gui/main_window.py` modified ✓ (guards present, greps verified)
- `tests/test_gui_project.py` modified ✓ (+120 lines, 3 new tests)
- Commits exist: 3f25965 ✓, 721704b ✓, e05a71b ✓ (git log)
- SUMMARY exists at requested path ✓
