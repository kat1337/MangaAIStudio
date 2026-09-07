---
phase: quick-260907-l3w
plan: 01
subsystem: project-persistence + gui
tags: [open-folder, project-detection, mas-pages, session-routing, unsaved-changes-gate]
requires: [project_io.load_project, project_io.find_sibling_manifest, MainWindow._load_project_session, MainWindow._load_folder, D-07 gate]
provides: [project_io.find_project_manifest, MainWindow._open_folder_session router, .mas page files in plain-folder sessions]
affects: [Open Folder (Ctrl+Shift+O), folder drag-drop, FileTable session swap]
tech-stack:
  added: [natsort import in core/project_io (headless-safe; already a project dependency)]
  patterns: [detect-then-route single router, corrupt-raises validation contract, build-before-swap all-or-nothing session swap]
key-files:
  created: []
  modified:
    - manga_ai_studio/core/project_io.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_core/test_project_io.py
    - tests/test_gui_project.py
decisions:
  - "Detection order fixed one level deep (direct manifest -> natsorted immediate subdirs -> None); multiple project subdirs resolve natsorted-first, no interactive chooser (documented in find_project_manifest docstring)"
  - "A discovered corrupt manifest RAISES ProjectFormatError (find_sibling_manifest precedent) — never a silent fall-through to the image route; the router surfaces the _open_project corrupt-project copy"
  - "_open_folder_session is the SINGLE router: open_folder and _on_folder_dropped both delegate; gate-once holds per route (project route = _load_project_session's internal D-07 gate; plain route = router gate before _load_folder)"
  - "Mixed image+.mas sessions: .mas-backed ImageFiles win same-path collisions (richer slot); image-backed pages keep original_verified=True and lazy-load; corrupt .mas aborts the whole open (build-before-swap)"
  - "Folder-route swap resets _project_dir/_project_name (CR-02 / T-Q3L-03) so Ctrl+S can never overwrite a previous project's manifest with .mas-folder pages"
metrics:
  duration: ~32 min
  completed: 2026-09-07
  tasks: 3
  commits: 6
actuals:
  tokens: 27700
  tasks: 3
  commits: 6
status: complete
---

# Quick Task 260907-l3w — Open Folder detects project vs plain folder Summary

Open Folder now detects whether the picked folder IS a Manga AI Studio project, CONTAINS one (immediate subdir), or is a plain folder — loading the project session, that subdir's project, or the folder's images + `.mas` page files respectively, with corrupt-manifest/corrupt-`.mas` isolation and exactly one Unsaved Changes prompt per action.

## Tasks Completed

| Task | Name | Commits | Files |
| ---- | ---- | ------- | ----- |
| 1 | project_io.find_project_manifest (headless detection) | 6edd9e2 (RED), e74ff89 (GREEN) | manga_ai_studio/core/project_io.py, tests/test_core/test_project_io.py |
| 2 | _open_folder_session router (IS / CONTAINS / corrupt) | 77ff647 (RED), 91e614d (GREEN) | manga_ai_studio/gui/main_window.py, tests/test_gui_project.py |
| 3 | _load_folder loads .mas pages (mixed, all-or-nothing) | 0d5a18d (RED), 3fb36bf (GREEN) | manga_ai_studio/gui/main_window.py, tests/test_gui_project.py |

## What Was Built

**Task 1 — `project_io.find_project_manifest(directory) -> Path | None`** (next to `find_sibling_manifest`): direct `manifest.json` validated via `load_project` and returned; else one-level natsorted immediate-subdir scan, first valid `sub/manifest.json` wins; else `None`. Malformed manifests raise `ProjectFormatError` (never skipped, never `None`); non-directory input returns `None`. Headless battery: 5 tests (direct / no-project incl. file+nonexistent paths / contains-project incl. natsort determinism `chapter_2` vs `chapter_10` / corrupt direct / corrupt subdir).

**Task 2 — `MainWindow._open_folder_session(directory)`**, the single router: manifest found -> `_load_project_session` (its internal D-07 gate is the only gate); `None` -> router gate -> `_load_folder` wrapped in `(ProjectFormatError, OSError)`; every failure surfaces `_open_project`'s corrupt-project copy (via the shared `_open_folder_corrupt_dialog`) with the session untouched and detection preceding gating (a corrupt manifest never consumes a prompt). `open_folder` slims to dialog-then-router; `_on_folder_dropped` delegates (file drops untouched). 6 tests: IS-a-project end state (identity/pages/title identical to Open Project), CONTAINS-a-project, corrupt isolation + no gate consumed, gate-once, plain-folder regression guard, folder-drop reroute.

**Task 3 — `_load_folder` gains `.mas` page files**: flat `.mas` collection joins the image scan; no-`.mas` folders keep the byte-identical `_set_pages` route; otherwise build-before-swap (image-backed `original_verified=True` slots; `.mas`-backed via `load_page_file` + `parse_page_entries` + `_build_image_file_from_parsed`, exceptions propagating to the router), natsorted combined session, folder-identity swap mirroring `_load_project_session`'s tail (`_project_dir`/`_project_name` reset, dirty cleared, first page displayed embedded or lazy). Same-path collisions: `.mas`-backed wins. 3 tests: manifest-less `.mas` folder session, mixed image+`.mas` single session (both first-page backings), corrupt `.mas` all-or-nothing abort with gate-once held.

## Verification Results

- `tests/test_core/test_project_io.py`: **44 passed** (39 pre-existing + 5 new, strict superset)
- `tests/test_gui_project.py`: **49 passed** (43 pre-existing + 6 new)
- `tests/test_gui_project.py + tests/test_gui_batch.py`: **68 passed** (batch/toolbar open-folder tests unaffected)
- Full suite (pinned interpreter): **1292 passed, 1 failed** — the single failure is `tests/test_gui_boxes.py::test_no_ghost_after_undo_and_scroll`, the pre-existing environmental flake (see Deferred Issues). 1278 baseline + 14 new = 1292: strict superset, no regressions.

## TDD Gate Compliance

All 3 tasks followed RED -> GREEN with separate commits: `test(...)` commit then `feat(...)` commit per task (verified in git log above). RED runs confirmed genuine failures (ImportError for Task 1; routing/mas assertions failing against old behavior for Tasks 2-3).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test contract] Mixed-session test's natsort ordering assertion was wrong**
- **Found during:** Task 3 GREEN
- **Issue:** The test assumed a `zzz_extra.png` inside the opened folder would sort after the `.mas` pages whose paths resolve to original refs in the SEED folder — but all `chapter.mas-project/*` paths natsort before `chapter/*` paths (the `.` in the dir name sorts before the path separator), and image-backed pages carry no embedded image until lazily displayed (two over-assertions).
- **Fix:** Rewrote the second window of the mixed test to delete page_01's original so its path falls back to `page_01.mas` INSIDE the opened folder (a genuine `.mas`-backed first page), and asserted the lazy-load contract (`current_image is None` until displayed) for image-backed slots instead of embedded images. No production code change.
- **Files modified:** tests/test_gui_project.py
- **Commit:** 3fb36bf

**2. [Rule 3 - Fixture] `_make_project_on_disk` seed folder name**
- **Found during:** Task 2 GREEN
- **Issue:** The helper seeded pages in `seed-pages-2`; the save-side name derivation uses the SOURCE folder name, so the manifest name (and restored title) read `seed-pages-2`, not `chapter`.
- **Fix:** Seed folder renamed to `chapter` (matching the established recipes in the file). Test-fixture-only; production save behavior untouched.
- **Files modified:** tests/test_gui_project.py
- **Commit:** 91e614d

Otherwise the plan executed as written — router shape, gate placement, detection order, corrupt contracts, and the `_load_folder` tail all match the Design section.

## Deferred Issues

- `tests/test_gui_boxes.py::test_no_ghost_after_undo_and_scroll` (unrelated module, pre-existing): intermittently fails under full-suite load with the stroke-invisible assertion (`green() == 206`, background beige) — a Qt viewport-grab timing flake. Verified flip-flopping at the PRE-TASK baseline commit e1c0c43 in a throwaway worktree (2 fail / 7 pass across interleaved runs) and flip-flopping in this tree in the same time windows; passes in isolation and at file level (228/228) in this tree. Zero code paths from this task are involved (pure canvas test; no folder/project IO). Out of scope per the scope boundary; the full-suite bar "strict superset, no new failures" is met. Worth a follow-up: stabilize the grab (retry window or deterministic update drain).

## Known Stubs

None — no stubs, placeholders, or unwired data paths were introduced.

## Threat Model Follow-Through

- T-Q3L-01 (mitigated): every discovered manifest validates through the existing `load_project` pipeline — no new parsing code; malformed raises abort the action with the corrupt-project dialog.
- T-Q3L-02 (accepted): one-level scan, human-initiated; same cost profile as `find_sibling_manifest`.
- T-Q3L-03 (mitigated): the folder-route swap resets `_project_dir`/`_project_name`; regression-guarded by the manifest-less `.mas` folder test asserting both are `None`.

## Self-Check: PASSED

- Files exist: manga_ai_studio/core/project_io.py, manga_ai_studio/gui/main_window.py, tests/test_core/test_project_io.py, tests/test_gui_project.py (all committed)
- Commits verified in git log: 6edd9e2, e74ff89, 77ff647, 91e614d, 0d5a18d, 3fb36bf
- New tests: 14 (5 + 6 + 3); suite total moved 1278 -> 1292 passed
