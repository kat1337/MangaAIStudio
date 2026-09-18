---
phase: 05
fixed_at: 2026-08-09T00:10:36-05:00
review_path: .planning/phases/05-project-persistence-image-ops-export/05-UI-REVIEW.md
iteration: 1
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
---

# Phase 5: Code Review Fix Report

**Fixed at:** 2026-08-09T00:10:36-05:00
**Source review:** `.planning/phases/05-project-persistence-image-ops-export/05-UI-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 1
- Fixed: 1
- Skipped: 0

## Fixed Issues

### Levels Apply pushes a no-op undo record (Pillar 5 FLAG, Top Fix 1)

**Files modified:** `manga_ai_studio/gui/main_window.py`, `tests/test_gui_image_dialogs.py`
**Commit:** `b376f8a`

**Applied fix:**

`_on_levels` (`main_window.py`) — before `_apply_geometry_op("levels", ...)` runs its
pre-capture (`pre_image = self.canvas.get_image_numpy()`), the canvas is now reset to the
detached pre-dialog `base` via `self.canvas.set_image_from_numpy(base.copy())` — mirroring
the existing Cancel path (`:1257`). The dialog's live previews had mutated the canvas to the
last preview frame (≈ the post-levels image), so the undo record's "before" previously equaled
the "after" and Ctrl+Z appeared to do nothing. The restore ensures `_apply_geometry_op` captures
the TRUE pre-op image; the op then writes the post-op image and re-baselines Show Original to the
post-op image (D-14), which is unaffected.

**Test extension (TDD — RED first, then GREEN):**

`test_levels_apply_pushes_one_entry` (`tests/test_gui_image_dialogs.py`) now:
1. Drives the real preview path in the fake dialog exec (`black_spin.setValue(30)` /
   `white_spin.setValue(200)` / `gamma_spin.setValue(1.0)`), so the canvas is genuinely mutated
   mid-dialog like a real user dragging the controls.
2. Adds the restore-semantics assertion: after Apply + one Ctrl+Z (`on_undo`), the canvas image
   equals the pre-dialog image byte-identical (`np.array_equal` via `get_image_numpy()`), and
   `history.can_undo()` is False (the geometry stack is empty again).

Verified RED on the pre-fix code (undo restored the leveled image `[15, 75, 135]` instead of the
pre-dialog `[40, 80, 120]`), then GREEN after the fix.

**Status:** fixed: requires human verification — the finding is bad state handling (undo
before-state capture), verified semantically by the RED→GREEN restore-semantics test plus the full
suite, but a manual Ctrl+Z sanity pass on a real image is recommended before the phase proceeds.

## Verification

- **Where verification ran:** the MAIN checkout (`.planning/config.json` sets
  `workflow.use_worktrees: false` — no isolated worktree was created, so the results are
  reproducible from the current tree).
- `pytest tests/test_gui_image_dialogs.py -x` — **7 passed** (includes the extended
  `test_levels_apply_pushes_one_entry`).
- `pytest -q` (full suite) — **552 passed, 4 warnings** (pre-existing
  `huggingface_hub.resume_download` FutureWarnings, unrelated to this fix).
- Syntax check: `ast.parse` on both modified files — OK.
- Python used: `C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe` (per environment note;
  the hermes venv on PATH was not used).

---

_Fixed: 2026-08-09T00:10:36-05:00_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_
