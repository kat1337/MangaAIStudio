---
phase: 05-project-persistence-image-ops-export
fixed_at: 2026-08-08T23:26:00Z
review_path: 05-REVIEW-FIX2.md
iteration: 1
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
---

# Phase 05: Code Review Fix Report — Fix 2 (WR-01)

**Fixed at:** 2026-08-08T23:26:00Z
**Source review:** `.planning/phases/05-project-persistence-image-ops-export/05-REVIEW-FIX2.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 1 (WR-01 — the single Warning; Info findings out of scope per `fix_scope: critical_warning`)
- Fixed: 1
- Skipped: 0

## Fixed Issues

### WR-01: Stray pre-created folder survives a save that aborts after the dialog accepts the default

**Files modified:** `manga_ai_studio/gui/main_window.py`, `tests/test_gui_project.py`
**Commit:** `afec543`
**Applied fix:**

- `_choose_project_dir` now returns `(picked, created)` instead of `picked` (and `(None, created)` on cancel) — `created` reports whether THIS call pre-created the default `.mas-project` folder. The existing rmdir cleanup on dialog-cancel / different-pick is unchanged.
- `_save_project` captures the flag (`created_default = False` before the dialog branch, so an in-place save into an existing project dir never attempts cleanup) and, when the folder was self-created, best-effort-removes it via the existing `_discard_stray_project_dir` in all three abort/failure branches that run before/at the write:
  1. the duplicate-stem abort (WR-03),
  2. the no-resolvable-source abort (WR-02),
  3. the `except OSError` branch of `project_io.save_project` (T-05-12).
- Cleanup is `rmdir`-based (empty-directories-only, OSError swallowed + debug-logged), so a folder the user populated or that pre-existed with content is never touched.
- Tests: the three existing `save_as` tests were adjusted for the tuple return (and now also assert `created is True`); a new regression test `test_save_as_abort_removes_stray_default` covers the abort path: a session with duplicate stems (`page.png` + `page.jpg`), dialog picks the pre-created default, the save aborts, and the stray empty folder is gone. Empirically verified RED on the pre-fix `main_window.py` (folder survives) and GREEN on the fix.

**Verification (ran in the MAIN checkout — `workflow.use_worktrees` is `false`, no worktree used):**
- Syntax: `ast.parse` on both modified files — OK.
- Affected tests: `python.exe -m pytest tests/test_gui_project.py -q -k "trigger or save_as"` → **6 passed, 16 deselected** (both `trigger` tests, all 3 existing `save_as` tests, and the new `test_save_as_abort_removes_stray_default`).
- Full suite: `python.exe -m pytest -q` → **552 passed, 0 failed** in 61.70s (551-test baseline + 1 new test). Run with `C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe` per the environment note (the `xdg` shadowing issue reported in the review does not affect this interpreter).

## Skipped Issues

None — the single in-scope finding (WR-01) was fixed. IN-01/IN-02/IN-03 are Info findings and were out of scope for this run.

---

_Fixed: 2026-08-08T23:26:00Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_
