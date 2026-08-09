---
phase: 05-project-persistence-image-ops-export
reviewed: 2026-08-08T23:40:00Z
depth: quick
files_reviewed: 2
files_reviewed_list:
  - manga_ai_studio/gui/main_window.py
  - tests/test_gui_project.py
findings:
  critical: 0
  warning: 1
  info: 3
  total: 4
status: issues_found
---

# Phase 05: Code Review Report — Fix 2 (G-05-1 / G-05-2 gap closure)

**Reviewed:** 2026-08-08T23:40:00Z
**Depth:** quick (two focused fixes, verified with offscreen Qt probes)
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Both fixes were verified CORRECT against the stated root causes — including an empirical offscreen-Qt probe that reproduces the exact pre-fix defect mechanics:

- **G-05-1 verified:** a bound-method direct connect (`triggered.connect(self._open_project)`) receives the emitted checked bool in the `manifest_path` slot (`manifest_path=False`), confirming the reported `AttributeError` at `selected.name`. The new zero-arg lambdas (main_window.py:327, 355) drop the bool (probe: slot invoked with `None` default). The wiring-audit claims also check out against `canvas.py` (`toggle_mask_overlay`/`zoom_reset`/`fit_to_window` are zero-arg; `zoom_in`/`zoom_out` take `wheel: bool = False` — benign).
- **G-05-2 verified:** `_choose_project_dir` (main_window.py:1865-1909) pre-creates the default folder before the dialog, and the cleanup guards are sound: `created` flag limits `rmdir` to folders the method itself created; `rmdir` semantics (empty-only) plus swallowed OSError mean a populated or pre-existing folder is never touched; the OSError fallback correctly resets `default` and leaves `created=False`.
- **Tests:** exactly 2 `trigger`-named and 3 `save_as`-named tests, no `-k` filter collisions; `action_open_project` is enabled in a fresh window (gates on `_op_running=False` only, `_refresh_action_states` runs in `__init__` at line 246), so the signal-path tests are stable; `test_save_project_trigger_saves_in_place` correctly catches a future regression (bool into `force_as` → dialog stub call count becomes non-zero).
- No secrets, no dangerous functions, no empty catches, no debug artifacts in the changed code. `_discard_stray_project_dir` and the mkdir failure path both log (no silent swallows).
- **Environment note:** the suite could not be re-run in this environment — the venv's `xdg` package (pyxdg 0.27) shadows the top-level `XDG_CONFIG_HOME`/`XDG_CACHE_HOME` API that `panelcleaner/cli_utils.py` requires, breaking `tests/conftest.py` at import. This is pre-existing environment breakage unrelated to this diff (the plan's final run reports 551 passed). Fix behavior was instead verified with isolated offscreen Qt probes (see Summary above).

One behavioral regression was found: the new pre-creation leaks a stray empty folder when the save aborts *after* the dialog accepts the default (see WR-01).

## Warnings

### WR-01: Stray pre-created folder survives a save that aborts after the dialog accepts the default

**File:** `manga_ai_studio/gui/main_window.py:1905-1909` (pick-keeps-folder path) + `:2031-2068` (`_save_project` abort branches)

**Issue:** `_choose_project_dir` keeps the pre-created folder when `picked == default` ("the save populates it"), but two of `_save_project`'s abort paths run BEFORE any write: the duplicate-stems abort (WR-03, line 2036) and the no-resolvable-source abort (WR-02, line 2054). Pre-fix, those aborts left nothing on disk (the folder was only created by `project_io.save_project`'s `mkdir` at write time). Post-fix, they leave an empty `<chapter>.mas-project` folder behind — a regression against the plan's own must-have ("A cancelled or redirected Save As leaves no stray empty .mas-project folder behind"). The dialog-cancel and different-pick paths are covered and tested; the dialog-accept-then-abort path is not.

**Fix:** Have `_choose_project_dir` report whether it created the folder, and clean up on the abort branches:

```python
# in _choose_project_dir: return (picked, created) instead of picked
return picked, created

# in _save_project:
project_dir, created_default = self._choose_project_dir()  # or stash on self
if project_dir is None:
    return False
...
# in the duplicate-stem and no-page abort branches (before `return False`),
# and in the `except OSError` branch of save_project:
if created_default:
    self._discard_stray_project_dir(project_dir)
```

## Info

### IN-01: Wiring-audit comment cites pre-edit line numbers

**File:** `manga_ai_studio/gui/main_window.py:318-326`

**Issue:** The audit comment references "tool actions 696-735, rotate actions 758-774", "543/546", and "2414" — all pre-edit numbers; the insertions at lines 315 and 355 shifted them (+12/+16). The audit content is accurate, but the citations now point at the wrong lines.

**Fix:** Refresh the cited line numbers to post-edit values (708-747, 770-786, 555/558, 2426) or drop the numbers and keep only the target names.

### IN-02: Two new `_choose_project_dir` branches are untested

**File:** `manga_ai_studio/gui/main_window.py:1884-1894` (mkdir-OSError fallback); tests cover only the happy path (`tests/test_gui_project.py:797-853`)

**Issue:** The mkdir-failure fallback (read-only parent → dialog opens at source parent with `created=False`) and the single-page-session default (`<image-stem>.mas-project`) have no regression tests. Both are behavioral branches of the fix that could regress silently (the single-page case was part of the G-05-2 leak — saves landing in the album root).

**Fix:** Add two small tests: one stubbing `Path.mkdir` to raise `OSError` and asserting the dialog default falls back to the source parent with no cleanup attempt; one single-page session asserting the pre-created default exists and the cleanup guard holds.

### IN-03: Open-trigger test relies on an implicit precondition

**File:** `tests/test_gui_project.py:742-769`

**Issue:** `window2.action_open_project.trigger()` only emits because the action is enabled in a page-less window (`_refresh_action_states` gates it on `_op_running` alone). Verified empirically that `QAction.trigger()` on a DISABLED action emits nothing — if a future change gates Open Project on `page_open`, this test fails in a confusing way (session never loads). It would still fail loudly (the image_files assertions catch it), but the failure mode would be opaque.

**Fix:** Add an explicit precondition assertion at the top of the test:
```python
assert window2.action_open_project.isEnabled()
```

---

_Reviewed: 2026-08-08T23:40:00Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: quick_

**Status line: issues_found — 0 critical, 1 warning, 3 info. Both gap-closure fixes (G-05-1, G-05-2) are functionally correct and empirically verified; WR-01 (stray folder on post-dialog save abort) is a minor behavioral regression introduced by the fix that should be addressed before merge.**
