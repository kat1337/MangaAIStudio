---
phase: 05-project-persistence-image-ops-export
plan: 10
subsystem: gui
tags: [pyside6, qaction, triggered, qfiledialog, project-persistence, gap-closure]

# Dependency graph
requires:
  - phase: 05-project-persistence-image-ops-export
    provides: 05-05 session layer (Save/Open Project, D-07/D-08/D-09), project_io.save_project (D-02)
provides:
  - G-05-1 closed: QAction.triggered zero-arg wiring for Open/Save Project actions
  - G-05-2 closed: Save As folder dialog pre-created default .mas-project folder + stray-folder cleanup
affects: [05-verify-work, 05-uat, verify-work, future GUI phases using QAction.triggered connects]

# Actuals (#2632) — pairs with the plan's `estimate` (20000 tokens) on the same scale.
actuals:
  tokens: 2916    # chars/4 over the realized diff (main_window.py + test_gui_project.py)
  tasks: 2
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "QAction.triggered connects use zero-arg lambdas so the injected checked-bool never lands in a parameterized slot"
    - "Folder-dialog defaults are pre-created on disk before QFileDialog so the native dialog cannot silently fall back to the source parent"

key-files:
  created: []
  modified:
    - manga_ai_studio/gui/main_window.py
    - tests/test_gui_project.py

key-decisions:
  - "Zero-arg lambda wrapper (not functools.partial, not a _checked param) for action_open_project/action_save_project triggered wiring"
  - "Pre-create the default .mas-project folder before QFileDialog.getExistingDirectory; best-effort rmdir cleanup only for self-created empty folders"
  - "Tests assert on the real computed default (<chapter>/<chapter>.mas-project) rather than the plan's shorthand tmp_path/chapter.mas-project"

patterns-established:
  - "Triggered-wiring audit comment at the connect site records every remaining target's argument-safety analysis"
  - "Cleanup guards: only a folder this method CREATED (created flag) and that is EMPTY (rmdir semantics) is ever removed"

requirements-completed: [PROJ-01]

coverage:
  - id: D1
    description: "Open Project… via the QAction triggered path (menu click / Ctrl+O) loads the selected manifest or page .mas without crashing (G-05-1); the checked-bool never reaches the manifest_path slot"
    requirement: PROJ-01
    verification:
      - kind: unit
        ref: "tests/test_gui_project.py#test_open_project_trigger_loads_session"
        status: pass
      - kind: unit
        ref: "tests/test_gui_project.py#test_save_project_trigger_saves_in_place"
        status: pass
    human_judgment: false
  - id: D2
    description: "Save Project As… opens the folder dialog at an EXISTING default <chapter>.mas-project folder; cancel/different-pick leave no stray self-created folder; the default pick is kept for the save (G-05-2, D-02)"
    requirement: PROJ-01
    verification:
      - kind: unit
        ref: "tests/test_gui_project.py#test_save_as_default_dir_precreated"
        status: pass
      - kind: unit
        ref: "tests/test_gui_project.py#test_save_as_cancel_cleanup"
        status: pass
      - kind: unit
        ref: "tests/test_gui_project.py#test_save_as_different_pick_cleanup"
        status: pass
    human_judgment: false
  - id: D3
    description: "Manual CR-01 repro re-run — real Ctrl+O dialog loads a session; real Save Project As dialog opens at an existing folder and writes inside it (plan's human_verify_mode: end-of-phase gate)"
    verification: []
    human_judgment: true
    rationale: "The native platform dialogs and the full click-through UX cannot be exercised by offscreen stubbed tests; the plan explicitly defers this to a human gate at end-of-phase."

# Metrics
duration: 8min
completed: 2026-08-08
status: complete
---

# Phase 05 Plan 10: G-05-1/G-05-2 Gap Closure Summary

**QAction.triggered zero-arg wiring for Open/Save Project actions (fixes the Ctrl+O AttributeError crash) + pre-created Save As default .mas-project folder with stray-folder cleanup (fixes saves leaking into the album root)**

## Performance

- **Duration:** 8 min
- **Started:** 2026-08-08T23:00:30Z
- **Completed:** 2026-08-08T23:08:32Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- **G-05-1 (blocker) closed:** `action_open_project.triggered` now connects through a zero-arg lambda, keeping the QAction checked-bool out of the `manifest_path` slot — the pre-fix code crashed at `selected.name` with `AttributeError: 'bool' object has no attribute 'name'` (main_window.py:2065). The same latent class on `action_save_project` (a bool landing in `force_as`) is closed identically. A wiring audit of every remaining `triggered.connect` target in main_window.py is documented in the line-315 comment: all targets are zero-arg methods, zero-arg lambdas, or signal-to-signal; `canvas.zoom_in/zoom_out` accept `wheel: bool = False` and are benign (triggered emits False == the default).
- **G-05-2 (major) closed:** `_choose_project_dir` pre-creates the computed `<source-parent>/<chapter-name>.mas-project` default BEFORE `QFileDialog.getExistingDirectory` — the native dialog refused the non-existent default and silently fell back to the source parent, which is exactly how saves leaked into the album root. Cancel and different-pick now remove the self-created empty folder best-effort (`rmdir` empty-dir semantics + swallowed OSError = "only if created by us and left empty"); mkdir failure falls back to the source parent so Save As works on read-only parents. `project_io.save_project` is untouched — its `exist_ok` mkdir tolerates the pre-created folder and the D-02 non-destructive overwrite contract is unchanged.
- **5 regression tests added** (TDD RED→GREEN per task): `test_open_project_trigger_loads_session`, `test_save_project_trigger_saves_in_place`, `test_save_as_default_dir_precreated`, `test_save_as_cancel_cleanup`, `test_save_as_different_pick_cleanup` — all drive the real signal path (`action.trigger()`) or the real dialog stub, so the pre-fix crash propagates out of the call and fails the test.

## Task Commits

Each task was committed atomically (TDD: test → fix per task):

1. **Task 1: Fix Open Project… triggered-bool crash + harden the same wiring class (G-05-1)**
   - `0b583c0` (test: RED — trigger-wiring regression tests; `test_open_project_trigger_loads_session` failed with the exact G-05-1 AttributeError)
   - `cd41905` (fix: GREEN — zero-arg lambdas at lines 315/339 + wiring audit comment)
2. **Task 2: Save Project As… pre-create the default .mas-project folder before the dialog (G-05-2)**
   - `6a45863` (test: RED — save-as default-dir tests; `test_save_as_default_dir_precreated` failed with a non-existent dialog default)
   - `6ea1f1a` (feat: GREEN — `_choose_project_dir` pre-creation + `_discard_stray_project_dir` cleanup)

## Files Created/Modified

- `manga_ai_studio/gui/main_window.py` - Zero-arg lambda wiring for `action_open_project`/`action_save_project` triggered connects (with the full wiring-audit comment); `_choose_project_dir` pre-creates the default folder, handles the mkdir-failure fallback, and cleans up self-created unused folders via the new `_discard_stray_project_dir` helper.
- `tests/test_gui_project.py` - 5 new regression tests in a plan 05-10 section using the module's existing helpers (`_make_window`, `_stub_dir_dialog`, `_stub_open_dialog`, `_dirty`, `_save_as`).

## Decisions Made

- **Zero-arg lambda over functools.partial / `_checked` parameter** (per plan): PySide6 drops the emitted bool for a zero-arg Python callable; `partial` would still inject the argument, and a `_checked` param on `_open_project` would contaminate the public dialog-driven path. The D-09 recent-opener closures already absorb `_checked` and are left unchanged.
- **Pre-create before dialog, clean up after** (per plan): `mkdir(exist_ok=True)` before `getExistingDirectory`, then best-effort `rmdir` on cancel/different-pick — only ever removes empty directories this method created itself; the default pick keeps the folder for the save.
- **Test paths assert the real computed default** — the plan's test sketches used `tmp_path/chapter.mas-project`, but the method's logic (`<source-parent>/<chapter-name>.mas-project`) computes `<chapter>/<chapter>.mas-project` for a chapter session; assertions were corrected to the real path so the pre-creation and cleanup checks are non-vacuous.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test assertions pointed at the wrong default-path**

- **Found during:** Task 2 GREEN (after the implementation edit)
- **Issue:** The three `save_as` tests asserted on `tmp_path/chapter.mas-project`, but `_choose_project_dir` computes `<source-parent>/<chapter-name>.mas-project` — for a 2-page chapter session loaded from `tmp_path/chapter` that is `tmp_path/chapter/chapter.mas-project`. The pre-created dir existed (GREEN was working) but the assertion checked a path the method never creates, so `test_save_as_default_dir_precreated` kept failing and the two cleanup tests would have been vacuous.
- **Fix:** Corrected the three tests' expected default to `chapter / "chapter.mas-project"` (the real computed default per the plan's own behavior description). No production-code change was needed.
- **Files modified:** tests/test_gui_project.py
- **Verification:** `-k "save_as"` → 3 passed; the captured dialog dir argument is asserted `.is_dir()` and the cleanup assertions are now non-vacuous.
- **Committed in:** `6ea1f1a` (Task 2 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Test-only correction; no production behavior change, no scope creep. All plan must-haves met.

## Issues Encountered

- **Flaky full-suite run:** the first `python -m pytest -q` run reported `test_run_ocr_selected_dispatches_worker_not_inline` failed (a pre-existing timing-sensitive async OCR worker test with a 5s `qtbot.waitUntil` timeout — unrelated to this plan's files). It passes in isolation AND on the immediate full-suite re-run (**551 passed, 0 failed**). Documented as a load flake, not a regression; out of scope per the scope boundary (no fix applied).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Both UAT gaps G-05-1 and G-05-2 are closed with regression tests; the full suite is green (551 passed, 0 failed on the final run).
- The plan's manual CR-01 repro (Ctrl+O loads a session; Save Project As… dialog opens at an existing `<chapter>.mas-project` folder and saves inside it) remains as the end-of-phase human gate for 05-verify-work / 05-UAT re-run.
- Follow-up observation for the verifier: the async OCR worker test in `tests/test_gui_boxes.py` (line 2795) is timing-sensitive under full-suite load — worth a timeout tolerance review in a future plan if it flakes again.

---
*Phase: 05-project-persistence-image-ops-export*
*Completed: 2026-08-08*

## Self-Check: PASSED

- Files verified on disk: `manga_ai_studio/gui/main_window.py`, `tests/test_gui_project.py`, `.planning/phases/05-project-persistence-image-ops-export/05-10-SUMMARY.md`
- Commits verified in git history: `0b583c0` (test RED), `cd41905` (fix GREEN), `6a45863` (test RED), `6ea1f1a` (feat GREEN), `09cbfb4` (docs: plan metadata)
- Full suite final run: 551 passed, 0 failed
