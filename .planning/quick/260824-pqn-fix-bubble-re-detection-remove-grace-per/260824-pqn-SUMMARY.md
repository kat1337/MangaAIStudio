---
phase: quick-260824-pqn
plan: 01
subsystem: project-persistence + box-interaction
tags: [save-project, json-serialization, numpy-payload, redetect, geometry-stale, grace-removal]
requires:
  - pagebox_to_json/json_to_pagebox seam (project_io.py)
  - _mark_geometry_changed / _redetect_single_box engine (main_window.py)
  - box_redetect_requested signal (canvas.py)
provides:
  - JSON-safe detected-payload serialization (ndarray line polygons -> plain ints)
  - loud save-failure path for unexpected pre-write exceptions
  - manual-only stale-gated re-detection (zero automatic trigger paths)
affects: [save/load round-trip, box move/resize UX, OCR dispatch]
tech-stack:
  added: []
  patterns:
    - int()-coercion at the model->JSON boundary (T-QKN-01)
    - whole-pre-write-phase try/except with WR-01 stray-folder cleanup (T-QKN-02/03)
key-files:
  created: []
  modified:
    - manga_ai_studio/core/project_io.py
    - manga_ai_studio/gui/main_window.py
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/box_item.py
    - manga_ai_studio/gui/inspector_panel.py
    - tests/test_core/test_project_io.py
    - tests/test_gui_project.py
    - tests/test_gui_boxes.py
    - tests/test_gui_detection_boxes.py
decisions:
  - payload text fields serialize via null-safe str() (None stays null — str(None) would fabricate the string "None")
  - font_size coercion is lazy (_json_font_size) so a payload-less PageBox still serializes without AttributeError
  - test_edited_box_not_auto_reocred rewritten to trigger via the affordance click instead of being deleted — preserves T-QG-03 coverage after the timer died
  - name hoisted to a safe default before the save try-block so the except-path dialog title can never NameError
metrics:
  duration: ~30 min
  completed: 2026-08-24
status: complete
actuals:
  tokens: 13400   # chars/4 over the realized diff (53.6k chars)
  tasks: 3
  commits: 4
---

# Phase quick-260824-pqn Plan 01: Fix bubble re-detection + Save Project serialization Summary

**One-liner:** Detected-box payloads (raw ndarray line polygons) now serialize JSON-safely so Save Project actually writes files with loud failures, and bubble re-detection is manual-only behind the geometry-stale corner affordance — the ~5 s stationary-grace auto-dispatch machinery is gone entirely.

## What Was Done

### Task 1 — JSON-safe payloads + loud save failures (TDD)
- **RED:** 4 failing tests — core round-trip of a `TextBlock([10,10,100,100], [np.array(..., np.int32)])` payload through `pagebox_to_json` + `json.dumps` (+ edge cases: empty lines, np.float64 coords, payload None), a GUI end-to-end save-with-detected-payload test, and a simulated mid-build RuntimeError test. All failed exactly as the plan predicted (`TypeError: Object of type ndarray is not JSON serializable`; silent Qt-slot death).
- **GREEN:** `pagebox_to_json` now serializes every payload field as plain data — xyxy/lines via nested `int()` coercion (handles ndarray quads AND plain lists), `vertical` via `bool()`, text fields via null-safe `str()`, `font_size` via int-with--1-fallback. `json_to_pagebox` untouched (its load-side coercion already accepts both forms).
- `_save_project` wraps the ENTIRE pre-write phase (snapshot flush → folder dialog → name derivation → `build_page_entries` loop) in try/except Exception: loguru `logger.error(exc_info=True)` + the same "Couldn't save '{name}'." critical dialog + stray-default-folder cleanup. The bespoke duplicate-stem / empty-page_files / OSError branches keep their copy.

### Task 2 — Remove the grace machinery; gate redetect on staleness
- Deleted: `STATIONARY_GRACE_MS`, `_stationary_timer`, `_on_stationary_grace_timeout` (including the vk7 edit-session deferral — nothing left to defer), the `box_interaction_started` Signal + its three `.emit()` sites in canvas drag handlers.
- `_mark_geometry_changed` keeps only the stale-marking loop (no timer arm, no `changed` flag).
- `_on_box_redetect_requested` gates on `getattr(box_item, "geometry_stale", False)` — clicks on non-stale bubbles are no-ops.
- Docstrings refreshed across main_window/canvas/box_item/inspector_panel; QTimer import retained (status-revert timer uses it).

### Task 3 — Test overhaul; full suite green
- Deleted the grace-dispatch battery + all vk7 deferral tests (~220 lines of removed-behavior premises).
- Added stale-gate counterparts: commit-move marks stale and dispatches nothing; affordance click no-op when not stale; click when stale runs exactly one refit + OCR and clears stale.
- Rewrote `test_edited_box_not_auto_reocred` → `test_edited_box_not_reocred_on_redetect` (affordance-click trigger) preserving the D-04/T-QG-03 edited-text gate.

## Verification

- Task 1: `pytest tests/test_core/test_project_io.py tests/test_gui_project.py` — 59 passed
- Task 2: `pytest tests/test_gui_canvas.py tests/test_gui_detection_boxes.py` — 68 passed + `rg` confirms zero grace identifiers in gui sources
- Task 3 / full suite (pinned interpreter `C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe`): **1085 passed, 0 failed** in 187 s

## Deviations from Plan

None material — plan executed as written. Two micro-adjustments within task scope:
1. Payload text/language/translation use a **null-safe** `str()` wrapper instead of bare `str(...)` — bare `str` would turn a None into the literal string `"None"` on disk.
2. `test_alt_drag_draw_release_defers_ocr_to_grace` was rewritten (not deleted outright) as `test_alt_drag_draw_release_emits_no_ocr_requested` — its no-instant-dispatch assertion is still live behavior worth guarding.

## Commits

| Commit | Type | Description |
|--------|------|-------------|
| 8bf9101 | test | Failing numpy-payload serialization + loud-save-failure regressions (RED) |
| 0ab564f | feat | JSON-safe detected-payload serialization + loud save failures |
| c629b67 | feat | Remove stationary-grace machinery; manual re-detect gated on geometry_stale |
| 51e3f62 | test | Replace grace-era tests with stale-gate counterparts |

## Self-Check: PASSED

- All 5 production files + 4 test files exist and are committed (`git status` clean for code dirs).
- All 4 commit hashes verified in `git log`.
- Full suite green under the pinned interpreter (1085 passed).
