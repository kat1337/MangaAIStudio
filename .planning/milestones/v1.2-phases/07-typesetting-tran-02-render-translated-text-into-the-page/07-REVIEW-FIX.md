---
phase: 07-typesetting-tran-02-render-translated-text-into-the-page
fixed_at: 2026-08-12T00:16:12Z
review_path: .planning/phases/07-typesetting-tran-02-render-translated-text-into-the-page/07-REVIEW-GAPS.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 07 Gap-Closure: Code Review Fix Report

**Fixed at:** 2026-08-12T00:16:12Z
**Source review:** `.planning/phases/07-typesetting-tran-02-render-translated-text-into-the-page/07-REVIEW-GAPS.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 3 (all WARNING — WR-01, WR-02, WR-03)
- Fixed: 3
- Skipped: 0

## Fixed Issues

### WR-01: Editable QFontComboBox commits free-typed text — spurious undo entries + arbitrary families

**Files modified:** `manga_ai_studio/gui/inspector_panel.py`, `tests/test_gui_inspector_styling.py`
**Commit:** `25ee1d3`
**Applied fix:** Gated the font commit on real membership per the review's prescription (no
`setEditable(False)` — the "Mixed" sentinel display depends on the editable line edit):

- `_emit_style_font_if_changed` now rejects any family with
  `self.font_combo.findText(family) == -1` — the editable line edit's per-keystroke
  `currentTextChanged` emissions (probed: "A", "Ar", "Ari") flow into the gate and are dropped
  unless the typed text exactly matches an installed family (T-07-18 "never free text"). The
  existing equality-vs-loaded WR-01 guard still runs after the membership gate.
- `_on_default_font_clicked` rides the same gate, so the Set-as-Default click can no longer
  persist a free-typed garbage family into the QSettings store; the docstring's "never free
  text" claim is now true.
- The gate is applied against the combo's (proxied) view model — `findText` was probed to
  return the exact family row when visible (the G-07-2 filter only hides non-matching rows, so
  a picked dropdown row always passes; a free-typed hidden family is conservatively rejected).

**Regression test:** `test_font_free_text_never_commits` — typing "Ari" and a full garbage
string commit nothing; a click on the garbage family emits nothing; an exact match of an
installed family (`QFontDatabase.families()`) commits once and the click emits it.

### WR-02: G-07-7 align guard — re-picking the Mixed sentinel pushes a no-op undo entry

**Files modified:** `manga_ai_studio/gui/inspector_panel.py`, `tests/test_gui_inspector_styling.py`
**Commit:** `9095ca1`
**Applied fix:** In `_emit_style_align_if_changed`, after the per-axis Mixed→None translation,
skip the emission when BOTH axes map to `None` (`if h_model is None and v_model is None:
return`) — a both-None commit carries nothing to apply (`_replace_align` skips None axes), so
emitting it would only push a before==after BOXES undo entry + refresh through
`MainWindow._inspector_style_commit`. The per-axis loaded-comparison guard and the Mixed
sentinel behavior (leading Mixed item, per-axis None mapping) are unchanged — the 07-09 tests
stay green.

**Regression test:** `test_align_sentinel_repick_after_commit_no_op` — after an H→"Left"
per-axis commit on a both-Mixed selection and the consumer reload (loaded = ("Left", "Mixed")),
re-picking the "Mixed" sentinel on H translates to (None, None) and fires nothing; a real
per-axis change still commits. Note: `_select_combo` clears the "Mixed" item on the uniform
axis during the reload, so the test arranges the review's WR-02 widget state (combo offering
the sentinel) explicitly to pin the guard itself — the guard is defense-in-depth at the API
level and guarantees no no-op commit can ever fire through any path.

### WR-03: Graveyard release timer can fire against an invalidated canvas at teardown

**Files modified:** `manga_ai_studio/gui/canvas.py`, `tests/test_gui_boxes.py`
**Commit:** `2fc2d9c`
**Applied fix:** Added `from PySide6 import Shiboken` to canvas.py (box_item.py already imports
it) and guarded `_release_graveyard` with the paint-path belt-and-suspenders pattern: `if not
Shiboken.isValid(self): return` — when the wrapper was invalidated at teardown while a batch was
still pending, the timer callback skips the release entirely (no `RuntimeError` from inside the
event loop, no mutation of the dead wrapper). The alive path is byte-identical to before: reset
`_graveyard_pending` + clear the batch.

**Regression test:** `test_graveyard_release_against_invalidated_wrapper_safe` (probe-level) —
with a pending batch, `Shiboken.delete(canvas)`, then the direct callback AND the real
`QTimer.singleShot(0, ...)` timer path against the invalidated wrapper: no raise, and the dead
wrapper's attributes stay untouched (`_graveyard_pending is True`, graveyard intact). Verified
RED pre-fix (the guard-less code mutated the dead wrapper's state) and GREEN post-fix; the alive
path is re-pinned with `_remove_box` (weakref alive through the pending flush, dead after
`processEvents()` — the 07-06 lifetime contract).

## Verification

All runs used the pinned interpreter
`C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe` in the **main checkout** — the
project's `workflow.use_worktrees` is `false` (#2825), so no isolated worktree was created and
every result is reproducible from the current tree.

- Per-fix targeted runs: `tests/test_gui_inspector_styling.py` (21 passed after WR-01/WR-02),
  `tests/test_gui_boxes.py` (201 passed after WR-03, incl. the RED→GREEN guard check for WR-03).
- Full suite (requirement 3): **717 passed, 0 failed** in 124.82s — baseline 714 + 3 new
  regression tests.
- Tier 2 syntax checks (`ast.parse`) passed for all four modified files.

---

_Fixed: 2026-08-12T00:16:12Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_
