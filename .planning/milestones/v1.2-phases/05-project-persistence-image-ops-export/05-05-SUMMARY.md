---
phase: 05-project-persistence-image-ops-export
plan: 05
subsystem: gui, persistence
tags: [pyqt, pyside6, project-io, session-persistence, dirty-tracking, qsettings]

# Dependency graph
requires:
  - phase: 05-project-persistence-image-ops-export
    provides: core/project_io .mas container + manifest (plan 05-01); geometry-op undo record (plan 05-04)
provides:
  - "Save/Open Project session layer: File-menu Save Project… (Ctrl+S) / Save Project As… (Ctrl+Shift+S) / Open Project… (Ctrl+O) / Recent Projects (QSettings, max 8)"
  - "D-07 dirty tracking (title '*' suffix) + Unsaved Changes [Save][Discard][Cancel] gate on Quit / window close / Open Project / Open Image / Open Folder"
  - "D-08 session rebuild from a manifest (mask/boxes/text/current-image restore via the D-11 seam) + D-09 chapter-climb dialog"
  - "D-06 missing-original navigation fallback: embedded image renders on navigation, no 'Couldn't open file' dialog"
affects: [05-image-ops, 05-06, 05-07, 05-08, phase-06]

# Actuals (#2632) — pairs with the plan's estimate (30000 estimateTokens).
actuals:
  tokens: 19714    # chars/4 over the realized diff (78854 chars)
  tasks: 3
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "D-11 seam reuse for session save/restore (outgoing _last_page_index rule, .copy() at every boundary)"
    - "Spontaneous-only closeEvent gating: window-manager closes prompt; programmatic closes (Quit handler, host teardown) never re-prompt"

key-files:
  created:
    - tests/test_gui_project.py
  modified:
    - manga_ai_studio/gui/main_window.py
    - manga_ai_studio/core/image_file.py
    - tests/test_gui_canvas.py
    - tests/test_gui_batch.py

key-decisions:
  - "closeEvent gates only SPONTANEOUS closes; the Quit action runs the gate in _on_quit before its programmatic close() — preserves D-07 on X/Alt+F4/Quit while programmatic closes (host teardown) never pop the dialog"
  - "The Unsaved-Changes gate lives inside _load_project_session/_load_single_page_mas (not literally before the Open Project… dialog) so chapter-climb + recent entries share it without double-prompting after Discard"
  - "Session rebuild bypasses _set_pages: ImageFiles are built with restored state and the sidebar is populated directly (a _set_pages rebuild would drop masks/boxes/current_image and auto-load placeholder paths via set_image_from_path)"
  - "Save-side per-page image source extends RESEARCH A3 with the embedded current_image as last resort (portable re-save with missing originals must not fail)"

patterns-established:
  - "Session layer = save-side flush (_snapshot_current_page, Pitfall 7 outgoing index) → core/project_io (only disk boundary) → load-side rebuild with build-then-swap (previous session byte-identical on failure)"
  - "Recent Projects mirrors Recent Files exactly (QSettings key 'recentProjects', standalone QMenu, property-flagged entries for _op_running gating)"

requirements-completed: [PROJ-01]

# Coverage metadata (#1602) — one entry per shipped deliverable.
coverage:
  - id: D1
    description: "Save Project… writes a valid <chapter>.mas-project folder end-to-end (manifest + per-page .mas, sidebar order), with no-changes flash on clean sessions, disabled-with-no-page gating, and the dirty-'*' title"
    requirement: PROJ-01
    verification:
      - kind: integration
        ref: "tests/test_gui_project.py#test_save_project_writes_project_folder"
        status: pass
      - kind: integration
        ref: "tests/test_gui_project.py#test_save_clean_session_no_changes_flash"
        status: pass
      - kind: integration
        ref: "tests/test_gui_project.py#test_dirty_title_suffix"
        status: pass
    human_judgment: false
  - id: D2
    description: "Open Project… rebuilds the session from a manifest (sidebar order, mask/boxes/text restore, EVERY page's embedded image decoded into current_image, fresh undo), with the D-09 chapter-climb dialog, corrupt-file isolation, and the D-06 verified-original flag both branches"
    requirement: PROJ-01
    verification:
      - kind: integration
        ref: "tests/test_gui_project.py#test_open_project_restores_session"
        status: pass
      - kind: integration
        ref: "tests/test_gui_project.py#test_open_project_populates_all_current_images"
        status: pass
      - kind: integration
        ref: "tests/test_gui_project.py#test_open_page_mas_with_sibling_prompt"
        status: pass
      - kind: integration
        ref: "tests/test_gui_project.py#test_open_corrupt_project_keeps_session"
        status: pass
      - kind: integration
        ref: "tests/test_gui_project.py#test_open_verified_original_flag"
        status: pass
      - kind: integration
        ref: "tests/test_gui_project.py#test_page_navigation_uses_embedded_image_for_missing_original"
        status: pass
    human_judgment: false
  - id: D3
    description: "Unsaved Changes [Save][Discard][Cancel] gate (single-click, one-shot) on Quit / spontaneous window close / Open Project / Open Image / Open Folder; Recent Projects menu (max 8, Clear Menu, empty item); _op_running action gating"
    requirement: PROJ-01
    verification:
      - kind: integration
        ref: "tests/test_gui_project.py#test_unsaved_changes_prompt_save_discard_cancel"
        status: pass
      - kind: integration
        ref: "tests/test_gui_project.py#test_recent_projects_menu"
        status: pass
      - kind: integration
        ref: "tests/test_gui_project.py#test_menu_gating_during_op"
        status: pass
      - kind: integration
        ref: "tests/test_gui_project.py#test_folder_open_sets_original_verified"
        status: pass
    human_judgment: false
  - id: D4
    description: "Ctrl+O collision resolved: exactly one action binds Ctrl+O (Open Project…); Open Image… keeps its action but lost the binding (Pitfall 8)"
    requirement: PROJ-01
    verification:
      - kind: other
        ref: "grep -v '^#' manga_ai_studio/gui/main_window.py | grep -c 'Ctrl+O' == 1"
        status: pass
      - kind: integration
        ref: "tests/test_gui_project.py#test_ctrl_o_opens_project_not_image"
        status: pass
    human_judgment: false

# Metrics
duration: 110min
completed: 2026-08-08
status: complete
---

# Phase 05 Plan 05: Project Persistence Session Layer Summary

**Save/Open Project session layer (PROJ-01 D-07/D-08/D-09): Save Project… flushes the live canvas through the Phase 2 D-11 seam into core/project_io's .mas-project format; Open Project… rebuilds the session from a manifest with per-page mask/boxes/text/embedded-image restore, the D-09 chapter-climb dialog, D-06 original re-verification with the embedded-image navigation fallback, dirty-`*` title tracking, the Unsaved Changes [Save][Discard][Cancel] gate, and QSettings Recent Projects**

## Performance

- **Duration:** 1h 50m
- **Started:** 2026-08-08T20:00Z (15:00 local)
- **Completed:** 2026-08-08T21:50Z (16:50 local)
- **Tasks:** 3 (tracer + 2 auto)
- **Files modified:** 5 (2 source, 3 test)

## Accomplishments

- Save Project… (Ctrl+S) / Save Project As… (Ctrl+Shift+S): D-11-seam flush (`_snapshot_current_page` — outgoing `_last_page_index`, mask `.copy()`, boxes snapshot, canvas numpy into the new `ImageFile.current_image` slot), per-page image source resolution (cleaned → source → embedded, RESEARCH A3 + portable fallback), `build_page_entries` → `save_project`, save-failure dialog (T-05-12), dirty cleared + "Saved project …" flash
- Open Project… (Ctrl+O) with the Open Image… binding removed (Pitfall 8 — exactly ONE Ctrl+O binding): manifest/page-.mas routing, Chapter Detected prompt ([Open Project] / [Open Page Only] / Esc cancels entirely via a hidden EscapeRole button), corrupt/newer-version → corrupt-project dialog with the previous session byte-identical (build-then-swap, T-05-13)
- D-08 session rebuild: sidebar in manifest order, mask/boxes/text/translation restored via the D-11 seam (`.copy()` on both boundaries), EVERY page's embedded image decoded into `current_image` (the 05-08 batch dims fallback), fresh undo history (D-05)
- D-06: `original_verified` per the sha256 rule; unverified pages render their embedded image on navigation — the placeholder path never reaches `set_image_from_path`, no "Couldn't open file" dialog (resume-work contract); normal folder/image opens set `original_verified=True`
- D-07: dirty tracking wired to `mask_modified`/`boxes_modified`/inpaint-finish (restore paths excluded via `_suppress_boxes_push`); title `Manga AI Studio — {project} — {page}*`; Unsaved Changes gate on Quit, spontaneous window close, Open Project/Image/Folder; Recent Projects (max 8, QSettings `recentProjects`, Clear Menu, empty item) with `_op_running` gating
- Tests: 15 new pytest-qt tests in `tests/test_gui_project.py`; 2 pre-existing tests updated to the superseded Phase-1 contract; full suite green at **515 passed / 0 failed**

## Task Commits

Each task was committed atomically:

1. **Task 1 (TRACER): Save Project… end-to-end** - `ba25bb8` (feat)
2. **Task 2: Open Project… session rebuild + chapter-climb + corrupt handling** - `f3a82fd` (feat)
3. **Task 3: Unsaved Changes gate + Recent Projects + action gating** - `e50dbb2` (feat)

**Plan metadata (to follow):** `docs(05-05)` — final commit includes this SUMMARY + STATE/ROADMAP/REQUIREMENTS updates. Plus `cb7f6c2` (style: Task-1 grep-gate docstring reword).

## Files Created/Modified

- `manga_ai_studio/gui/main_window.py` - File menu per UI-SPEC surface 21; `_save_project`/`_save_project_as`/`_open_project`/`_load_project_session`/`_load_single_page_mas`/`_confirm_chapter_climb`/`_confirm_discard_changes`/`_snapshot_current_page`/`_set_session_dirty`/`_session_dirty`/`_update_title`/`_add_recent_project`/`_refresh_recent_projects_menu`/`_on_quit`/spontaneous-gated `closeEvent`; on_page_selected Step-3 fallback + Step-5 title; `_set_pages` original_verified wiring; `_refresh_action_states` gating
- `manga_ai_studio/core/image_file.py` - `ImageFile.current_image: np.ndarray | None = None` runtime save-time capture slot
- `tests/test_gui_project.py` (NEW) - 15 pytest-qt tests (save/clean-flash/disabled/Ctrl+O/title; open-restore/all-current-images/sibling-prompt/corrupt-isolation/verified-flag/navigation-fallback; gate one-shot semantics/recent-cap/gating/original-verified)
- `tests/test_gui_canvas.py` - `test_open_image_action` updated to the D-07 contract (no Ctrl+O binding; exactly one action binds it)
- `tests/test_gui_batch.py` - `test_file_menu_internal_order` updated to the UI-SPEC surface-21 order

## Decisions Made

- **Spontaneous-only closeEvent gating**: the gate runs on window-manager closes (X/Alt+F4) inside `closeEvent` and on the Quit action inside `_on_quit` (its `close()` is programmatic). The initial always-gate `closeEvent` made pytest-qt's teardown `close()` of a dirty test window pop a REAL modal dialog — the full-suite hang. App-visible D-07 semantics are unchanged: X/Alt+F4/Quit each prompt exactly once; programmatic closes never re-prompt. The user confirmed the real-app dialog closes on a single click.
- **Gate placement in `_load_project_session`/`_load_single_page_mas`** rather than literally before the Open Project… dialog: the two load entry points are shared by the dialog flow, the chapter-climb, and Recent Projects — one gate location, no double-prompt after Discard.
- **Session rebuild bypasses `_set_pages`**: ImageFiles are constructed with restored mask/boxes/current_image and the sidebar is populated directly; `_set_pages` would rebuild fresh ImageFiles (dropping restored state) and auto-select via `on_page_selected` (running `set_image_from_path` on placeholder paths — the exact bug the fallback exists to prevent).
- **Save-side image source = cleaned → source path → embedded `current_image`**: extends RESEARCH A3 so re-saving a portable project (originals missing) embeds the last-known image instead of failing.
- **Chapter-climb Esc semantics**: a hidden Cancel button with `setEscapeButton` absorbs Esc so `clickedButton()` is None — Esc cancels the action entirely (UI-SPEC §22), never silently opening the page or chapter.
- Recent Projects follows the Recent Files machinery exactly (QSettings, cap 8, standalone QMenu, property-flagged entries for op-gating).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] closeEvent re-entrancy with programmatic closes (test-suite hang)**
- **Found during:** Task 3 verification (full-suite runs hung; root-caused to pytest-qt teardown)
- **Issue:** The plan's "gate on window close" wired into a plain `closeEvent` also fired for PROGRAMMATIC `close()` calls. pytest-qt's `_close_widgets` teardown calls `w.close()` on every registered widget; with pre-existing tests leaving sessions dirty (box seeds / mask strokes now legitimately mark dirty via the new `_set_session_dirty` hook), teardown popped a REAL modal Unsaved Changes dialog and the suite hung indefinitely.
- **Fix:** `closeEvent` consults the gate only for `event.spontaneous()` closes; the Quit action runs the gate in `_on_quit` before its programmatic `close()`. D-07 coverage (Quit, window close, Open Project/Image/Folder) is unchanged; single-click one-shot semantics confirmed by the user.
- **Files modified:** manga_ai_studio/gui/main_window.py
- **Verification:** full suite green (515 passed); `test_unsaved_changes_prompt_save_discard_cancel` covers Quit, spontaneous close, and no-prompt-on-programmatic-close
- **Committed in:** e50dbb2

**2. [Rule 3 - Blocking] Pre-existing tests asserted the superseded Phase-1 contract**
- **Found during:** Task 1 acceptance (full-suite gate)
- **Issue:** `tests/test_gui_canvas.py::test_open_image_action` asserted Open Image binds Ctrl+O (removed by D-07/Pitfall 8) and `tests/test_gui_batch.py::test_file_menu_internal_order` asserted the old File-menu order — both fail under the plan's own contract.
- **Fix:** Updated both to the new contract (exactly one Ctrl+O binding on Open Project…; UI-SPEC surface-21 menu order).
- **Files modified:** tests/test_gui_canvas.py, tests/test_gui_batch.py
- **Verification:** full suite green
- **Committed in:** ba25bb8

**3. [Rule 2 - Missing Critical] Save-side embedded-image fallback for portable projects**
- **Found during:** Task 1 (`_page_image_source` design)
- **Issue:** RESEARCH A3 (cleaned → source file) has no source for a re-opened portable project whose originals are missing — a re-save would fail reading `imf.path` (a placeholder .mas path).
- **Fix:** `_page_image_source` falls back to the embedded `current_image` (populated for every page at load) before skipping the page; a page with no source at all is skipped with a loguru warning.
- **Files modified:** manga_ai_studio/gui/main_window.py
- **Verification:** covered by the open-side tests' save→delete-original→reopen flows; full suite green
- **Committed in:** ba25bb8

### Plan-fidelity Notes (implementation details, no behavior deviation)

- Task 1's `_open_project` menu wiring carried a transitional no-op slot; the full D-08/D-09 body landed in Task 2 (same plan, next task — not a shipped stub).
- The plan's Task-1 grep gate (`grep -c 'Ctrl+O' == 1`) required reworded docstrings in Task 2/3 (`cb7f6c2`).
- The QSettings `recentProjects` key is isolated to throwaway INI files in tests so the user's real registry is never polluted.

---

**Total deviations:** 3 auto-fixed (2 blocking, 1 missing-critical) + 0 architectural.
**Impact on plan:** All auto-fixes necessary for correctness and for the plan's own "full suite green" acceptance gate. No scope creep.

## Issues Encountered

- Full-suite hangs during Task 3 verification were root-caused to the closeEvent/teardown interaction above (fixed; see deviation 1). The remaining "I/O operation on closed file" loguru noise at interpreter shutdown comes from a manga-ocr background thread logging after pytest's capture closes — pre-existing environmental noise, exit code 0, not caused by this plan.
- The plan-time baseline (462/461/1) has grown: at execution the suite was 500 passing; after this plan it is **515 passed / 0 failed** (a strict superset).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The resumable-workspace core (PROJ-01 session layer) is complete: Save/Open round-trip, chapter-climb, dirty gate, Recent Projects — all tested.
- Ready for plan 05-06 (image ops consume the session's `current_image`/`original_verified` for Show Original gating and re-baseline) and 05-08 (batch export reads per-page `current_image` dims — populated for EVERY page at project load).
- PROJ-01 declared by later plans (05-06/05-08) will complete the requirement; `requirements.ready-ids` reports PROJ-01 ready for this plan's declaration.

## Self-Check: PASSED

- All 6 claimed files exist on disk (5 source/test files + this SUMMARY).
- All 4 plan commits exist in git history: ba25bb8, f3a82fd, e50dbb2, cb7f6c2.
- Full suite re-run after the final commit: **515 passed / 0 failed** (exit 0).

---
*Phase: 05-project-persistence-image-ops-export*
*Completed: 2026-08-08*
