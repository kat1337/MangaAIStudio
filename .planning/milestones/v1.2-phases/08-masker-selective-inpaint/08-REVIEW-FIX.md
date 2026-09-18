---
phase: 08-masker-selective-inpaint
fixed_at: 2026-08-19T00:12:49Z
review_path: .planning/phases/08-masker-selective-inpaint/08-REVIEW.md
iteration: 1
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 8: Code Review Fix Report

**Fixed at:** 2026-08-19T00:12:49Z
**Source review:** `.planning/phases/08-masker-selective-inpaint/08-REVIEW.md`
**Iteration:** 1
**Gates ran in:** the main checkout (`workflow.use_worktrees = false` — no isolated worktree)

**Summary:**
- Findings in scope: 2 (WR-01, WR-02; IN-01/IN-02 explicitly out of scope)
- Fixed: 2
- Skipped: 0

## Fixed Issues

### WR-01: WR-02 dirty-marking is skipped on batch cancel/abort/error — detected boxes still silently lost

**Files modified:** `manga_ai_studio/gui/main_window.py`, `tests/test_gui_gap_closure.py`
**Commit:** `566daa1` (fix), `47e2ea6` (probe)
**Applied fix:** `_on_batch_finished`'s dirty loop runs only on the Worker's successful
`result` path; cancel emits `aborted` and exceptions emit `error` (neither emits `result`),
so `_on_batch_cleanup` (connected to BOTH `aborted` and `finished`) never dirtied. Added the
mode-aware dirty loop to `_on_batch_cleanup`: when the captured `batch_mode` is
`"detect"` or `"detect_and_clean"`, mark every `ImageFile.dirty = True` and call
`_update_title()`. Conservative over-dirtying (a page the abort skipped has no new state —
a spurious save prompt at most, never data loss). The existing `cancelled`-branch behavior
(refresh skipped when cancelled) is preserved; clean-only mode still does not dirty. A probe
(`test_detect_batch_cancel_marks_pages_dirty`) drives `_on_batch_cleanup` with
`_batch_cancelled = True` / mode `detect`, asserts every page is dirty + the title `*` appears,
and asserts clean-mode cancel does not dirty.

### WR-02: Stale retained raw + dims-preserving geometry op → silent auto-plane wipe via `_rederive_auto_layer`/`_refit_changed_boxes`

**Files modified:** `manga_ai_studio/gui/main_window.py`, `tests/test_gui_gap_closure.py`
**Commit:** `ef3d44d` (fix), `47e2ea6` (probe, RED first)
**Applied fix:** Three-part belt-and-suspenders fix:
- `_apply_geometry_op`: when the op is a geometry op (`geometry` True), the current
  `ImageFile`'s `auto_mask` and `raw_detected_mask` are cleared — the retained raw is no
  longer in the (rotated) page frame, closing the root cause that a 180°-rotate (dims
  preserved, so the re-derive dims guard passes) would re-derive the unrotated raw against
  rotated boxes into an all-no-fit empty binary that wiped the rotated auto plane
  non-undoably.
- `_rederive_auto_layer` (mode-ON): after the derive + live write-back, added the no-fit
  guard mirroring the threshold slot — `if not any(pb.mask is not None for pb in boxes):
  return` — skipping `set_auto_binary` when every box failed its fit (does not clobber the
  plane with an empty binary).
- `_refit_changed_boxes`: the geometry is equivalent (same derive → compose →
  `set_auto_binary`), so the same no-fit guard was added before `set_auto_binary`.
- Probe `test_rotate_then_dilate_nudge_keeps_auto_plane` (committed RED first at `47e2ea6`,
  failing on pre-fix code because `raw_detected_mask` was retained after the geometry op —
  the recorded 08-VERIFICATION.md signature): detects non-symmetric content, drives a
  180°-rotate through `_apply_geometry_op` directly (the real `_rotate_page` needs a full
  TextBlock payload; the headless `_blk` fixture is shape-only), asserts the raw + auto slot
  are invalidated, then runs `_rederive_auto_layer` and asserts the auto plane keeps content.
  Now GREEN post-fix.

**Verification results (3-tier):**
- **WR-01:** Tier 1 re-read of `_on_batch_cleanup` (fix text present, surroundings intact);
  suite green. Tier 3 for the logic marker (dirty flagging relies on `_batch_mode`
  capture/ordering — behavior verified by REPL-style probe, not just a syntax check).
- **WR-02:** Tier 1 re-read of all three edited sites; Tier 2 `ast.parse` of `main_window.py`
  passed; suites green.
- `tests/test_gui_gap_closure.py -x -q`: **8 passed** (7 pre-existing + WR-01 probe + WR-02
  probe).
- `tests/test_gui_gap_closure.py tests/test_gui_detection_boxes.py -q`: **40 passed**.
- Full suite not run (per commit protocol — only the targeted suites were required).

## Skipped Issues

None — both in-scope findings were fixed. (IN-01 and IN-02 were explicitly out of scope for
this fix round and were not touched.)

---

_Fixed: 2026-08-19T00:12:49Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_
