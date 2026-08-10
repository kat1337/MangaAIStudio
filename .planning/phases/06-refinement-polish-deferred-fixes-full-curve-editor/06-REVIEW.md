---
phase: 06-refinement-polish-deferred-fixes-full-curve-editor
reviewed: 2026-08-09T16:30:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - manga_ai_studio/gui/main_window.py
  - manga_ai_studio/gui/canvas.py
  - tests/test_gui_curves_dialog.py
  - tests/test_gui_crop_tool.py
findings:
  critical: 1
  warning: 3
  info: 3
  total: 7
followup_findings:
  critical: 0
  warning: 1
  info: 0
  total: 1
status: issues_found
---

# Phase 06: Code Review Report

**Reviewed:** 2026-08-09T16:30:00Z (follow-up — gap closure 06-06/06-07/06-08)
**Depth:** standard
**Files Reviewed:** 4 (follow-up scope; original review covered 14)
**Status:** issues_found

## Summary

Original review (2026-08-09T12:00:00Z) flagged CR-01 (Curves Cancel poisons the
Show Original baseline + false inpaint claim), WR-01 (undo flash mislabels a
curves undo as "inpaint"), WR-02 (dock/toolbar highlight desync on dock
clicks). Gap plans 06-06 (b063388 + 8816b9c), 06-07 (50b75d6 / 09986c4 /
1b49071), and 06-08 (a4264f1 / 43a20a5 / d16afca) closed all three.

Follow-up verification performed: full read of the 4 changed files; full diff
of the gap commits (HEAD~12..HEAD); the complete curves + crop GUI suites
(49 passed); and a live offscreen probe of the real MainWindow exercising the
(0,0)-gate label path, the page-change staleness path, the dock-click sync
path, and the tool_changed re-entry path.

Verdict: all three prior findings are genuinely RESOLVED — the fixes match
the prescribed shapes, the new tests assert the exact failed behaviors, and
no regression or signal loop was introduced. One NEW Warning was found: the
WR-01 (0,0)-gate override is broader than the geometry-record shape — an
inpaint whose mask bbox starts at (0,0) (mask touching the page's top-left
pixel) pops as a single (0,0) image entry and gets mislabeled with the stale
`_last_geometry_op_name`; the stale name also survives `reset_history()`
across page changes. Probe-verified with the real MainWindow.

## Critical Issues

### CR-01: Curves dialog Cancel poisons the Show Original baseline and activates the before/after compare without an inpaint — **RESOLVED**

**File:** `manga_ai_studio/gui/main_window.py:1274` (interacting with `manga_ai_studio/gui/canvas.py:742-743` and `manga_ai_studio/gui/canvas.py:769`)

**Resolved by:** `8816b9c` (feat(06-06): capture-suppress Curves cancel restore
+ gate inpaint claim) + `b063388` (feat(06-06): capture-suppress curves apply
pre-restore).

**Verification evidence:**
- Cancel path (main_window.py:1280) now restores through
  `set_image_from_numpy_preview(base.copy(), capture_original=False)` — the
  capture-suppressed path, so `_original_image_numpy` is never captured from
  the last preview frame. The apply pre-restore (main_window.py:1294) uses
  the same suppressed path (b376f8a ordering preserved; the post-Apply
  baseline is established exclusively by `_apply_geometry_op`'s tail
  `rebaseline_original()`, main_window.py:1197).
- canvas.py:775-776 gates the inpaint-result claim on `capture_original` —
  the preview path can no longer set `_inpainted_qimage`. All capture-enabled
  callers (inpaint display, geometry-op write-back) keep the claim, so the
  pre-existing post-inpaint/geometry behavior is untouched.
- New regression test `test_curves_cancel_fresh_page_no_baseline_poison`
  (test_gui_curves_dialog.py:810-856) asserts the exact failed behavior: no
  pre-baseline at open (line 829), mid-dialog previews really mutate the
  canvas (845), Cancel restores byte-exact (847), `_original_image_numpy`
  stays None (850), `has_inpaint_result()` stays False (852), and Show
  Original (P) stays disabled after `_refresh_action_states` (856) — IN-03
  folded in. The IN-01 test gap is closed.
- Apply path correctness re-verified: `test_curves_apply_pushes_one_entry`
  still asserts the post-op re-baseline (line 704) and one-entry undo (698).

### CR-01 follow-up edge check (no new defect): pages that DID run an inpaint
before opening Curves keep a consistent state after Cancel — the restored
base equals the stored `_inpainted_qimage` and `_original_image_numpy` is
untouched, so the before/after toggle remains coherent.

## Warnings

### WR-01: Undo/redo flash mislabels a curves undo as "Undo: inpaint" — **RESOLVED** (reported case)

**File:** `manga_ai_studio/gui/main_window.py:2937-2975` (`_undo_op_label_for_result`)

**Resolved by:** `09986c4` (feat(06-07): single-entry (0,0)-gated op-name
override) with RED gates `50b75d6` and `1b49071`.

**Verification evidence:**
- The single-entry image branch (main_window.py:2968-2974) now prefers the
  recorded op name when the popped entry is a full-frame (0,0) patch — the
  exact shape `push_geometry_state` produces (history_manager.py:435,
  `(0, 0, image_patch.copy())`).
- `test_curves_apply_pushes_one_entry` now asserts "Undo: curves" (line 721)
  and "Redo: curves" (727) — the exact failed flash. `test_single_image_pop_keeps_inpaint_label`
  (810-... 731-771) asserts the negative scope: a NON-origin bbox inpaint
  keeps the "inpaint" label while the stale op name is recorded.
- Probe-verified: curves apply → Ctrl+Z flashes "Undo: curves".

**Residual issue — see new follow-up finding FW-01 below** (the (0,0) gate
also matches ORIGIN bbox inpaints and the op-name register survives page
changes; the docstring's "Accepted limitation" documents only the
two-consecutive-geometry-ops case).

### WR-02: Tool dock button clicks desync the dock/toolbar highlights (D-10 contract) — **RESOLVED**

**File:** `manga_ai_studio/gui/main_window.py:716-767` + `manga_ai_studio/gui/main_window.py:3175-3216` (`set_active_tool`)

**Resolved by:** `43a20a5` (feat(06-08): ungroup window tool actions +
explicit sync loop), RED gate `a4264f1`, docstring truth rewrite `d16afca`.

**Verification evidence:**
- The six `tool_group.addAction(...)` calls are gone (grep: zero
  `tool_group.addAction` remains in main_window.py; `tool_group` holds
  exactly the panel's own six actions). The :710-715, :749-757, and :876-879
  comments were rewritten to describe the standalone-action design and now
  match the implementation.
- `set_active_tool` (3197-3216) drives the six window actions with
  `blockSignals` around `setChecked` (check the match, uncheck the other
  five) and explicitly checks the matching toolbar QToolButton.
- **Pitfall 1 double-connection check:** `tool_changed` is connected to
  `set_active_tool` exactly once (main_window.py:2573). Inside, both the
  panel sync (`tools_panel.set_active_tool`, tools_panel.py:244-265) and the
  window-action loop block signals, so no `toggled`/`tool_changed`
  re-emission occurs — no recursion. Probe-verified: a dock click + a menu
  trigger invoke `set_active_tool` exactly twice (no re-entry).
- `test_dock_button_click_syncs_dock_toolbar_and_window` (test_gui_crop_tool.py:302-354)
  asserts the exact pre-fix failure: after a dock Rectangle click the panel
  action stays checked, `active_tool()` is RECTANGLE, the window action and
  toolbar button mirror it, and a SECOND consecutive dock click (Brush)
  keeps everything in sync — the pre-fix probe's second-click total desync is
  locked. `test_toolbar_buttons_track_active_tool` locks the
  `actionGroup() is None` standalone contract (lines 264-272) and the
  programmatic/shortcut/menu paths.
- Probe-verified on the real MainWindow: toolbar uncheck propagation works
  (set_active_tool(BRUSH) then set_active_tool(MOVE) leaves exactly one
  checked toolbar button), and dock clicks keep panel/window/toolbar in sync.

## Info

### IN-01: Test gap masks CR-01 — **RESOLVED**

**File:** `tests/test_gui_curves_dialog.py:810-856`

`test_curves_cancel_fresh_page_no_baseline_poison` now exercises the
`_original_image_numpy is None` fresh-page state the original test masked
(no pre-baseline call; asserted at line 829) and asserts baseline stays None
+ no inpaint claim after Cancel.

### IN-02: CurveWidget margin clicks can move endpoints — **OPEN** (out of gap scope)

**File:** `manga_ai_studio/gui/curves_dialog.py:297-301` (`_add_point`)

Unchanged by the gap plans. Still cosmetic (a click in the 8px margin just
outside the plot's right edge nudges the white endpoint's y via the 255
clamp). Not part of the CR-01/WR-01/WR-02 closure; left as-is.

### IN-03: Cancel path leaves stale action enablement — **RESOLVED**

**File:** `manga_ai_studio/gui/main_window.py:1280`

Folded into CR-01's fix as predicted: the preview path no longer sets
`_inpainted_qimage`, so `has_inpaint_result()` stays False and Show Original
never becomes enabled on the fresh-page cancel lifecycle — asserted in
`test_curves_cancel_fresh_page_no_baseline_poison` line 856.

## Follow-up Review (gap closure)

Scope: commits b063388, 8816b9c (CR-01), 50b75d6, 09986c4, 1b49071 (WR-01),
a4264f1, 43a20a5, d16afca (WR-02) — diff HEAD~12..HEAD on the four listed
files. Full curves + crop GUI suites: 49 passed. Live probes: see each entry.

### FW-01 (WARNING): The (0,0) gate mislabels origin-bbox inpaints as the stale geometry op, and the op-name register leaks across pages

**File:** `manga_ai_studio/gui/main_window.py:2968-2974` (`_undo_op_label_for_result`) + `manga_ai_studio/gui/main_window.py:2675-2687` (`reset_history`)

**Issue:** The WR-01 override treats ANY single `("image", (0, 0, patch))`
pop as a geometry record. But the bbox-inpaint undo path pushes exactly that
shape when the mask touches the page's top-left pixel:
`_on_inpaint_finished` calls `push_image_action(x1, y1, patch)` with the
mask bbox origin (main_window.py:3846, 3861) — a mask covering the top-left
corner of a manga page (the first speech bubble is the common case) yields
`bbox = (0, 0, w, h)`, so the pop is `(0, 0, region_slice)`. With a stale
`_last_geometry_op_name` recorded, the flash mislabels the inpaint.

Additionally, `reset_history()` (called on every page change,
main_window.py:2675-2687) clears `history` and `_pre_stroke_mask` but NOT
`_last_geometry_op_name` — the stale op name crosses page boundaries, so an
origin-bbox inpaint on a page where no geometry op ever ran mislabels too.

Probe-verified with the real MainWindow (offscreen Qt): curves apply + undo
leaves `_last_geometry_op_name == "curves"`; a subsequent
`push_image_action(0, 0, ...)` (the exact shape a real origin-bbox inpaint
pushes) + undo flashes **"Undo: curves"** for an inpaint; and
`_last_geometry_op_name` survives `reset_history()`. The existing scoping
guard test `test_single_image_pop_keeps_inpaint_label` only covers the
NON-origin bbox (x=5, y=5), so this window is uncovered.

The docstring's "Accepted limitation" (main_window.py:2957-2961) documents
only the two-consecutive-image-only-geometry-ops case — not this false
positive — so the gap plan's own truth claim is incomplete.

**Fix (preferred — stamp-based):** make the geometry-record identity
authoritative in the HistoryManager instead of inferring it from the entry
shape: e.g. `push_geometry_state` records its `stamp` in a set, `undo()`/`redo()`
expose whether the popped image entry is a geometry record, and
`_undo_op_label_for_result` consults that flag. This eliminates both the
origin-bbox false positive and the stale-name case for good.

**Fix (minimal):** mirror the codebase's own full-frame discriminator
(canvas.py:599 uses `(x, y) == (0, 0)` AND patch dims vs. current frame)
and clear the register on page change:

```python
# _undo_op_label_for_result — single-entry branch:
if kind == "image" and self._last_geometry_op_name is not None:
    x, y, patch = value
    current = self.canvas.get_image_numpy()
    # Curves is the ONLY single-entry geometry record in practice (rotate/
    # crop/resize always transform mask+boxes too, history_manager.py:439-448)
    # and curves never changes page dims — so the patch is the full pre-op
    # frame, equal to the current frame. An origin bbox inpaint is a region
    # slice and fails the shape gate.
    if (
        (x, y) == (0, 0)
        and current is not None
        and patch.shape[:2] == current.shape[:2]
    ):
        return self._undo_op_label(self._last_geometry_op_name)

# reset_history — clear the cross-page-stale register:
self._last_geometry_op_name = None
```

Add a scoping-guard variant of `test_single_image_pop_keeps_inpaint_label`
at the ORIGIN (`push_image_action(0, 0, ...)`) to lock the gate, and a
page-change assertion that the name register resets.

---

_Reviewed: 2026-08-09T16:30:00Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
