---
phase: 06-refinement-polish-deferred-fixes-full-curve-editor
reviewed: 2026-08-09T12:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - manga_ai_studio/core/image_ops.py
  - manga_ai_studio/gui/canvas.py
  - manga_ai_studio/gui/crop_dialog.py
  - manga_ai_studio/gui/curves_dialog.py
  - manga_ai_studio/gui/load_translations_dialog.py
  - manga_ai_studio/gui/main_window.py
  - manga_ai_studio/gui/resize_dialog.py
  - tests/test_core/test_image_ops.py
  - tests/test_gui_boxes.py
  - tests/test_gui_canvas.py
  - tests/test_gui_crop_tool.py
  - tests/test_gui_curves_dialog.py
  - tests/test_gui_image_dialogs.py
  - tests/test_gui_project.py
findings:
  critical: 1
  warning: 2
  info: 3
  total: 6
status: issues_found
---

# Phase 06: Code Review Report

**Reviewed:** 2026-08-09T12:00:00Z
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Phase 06 delivered the full Curves curve editor (`curve_lut`/`curves_page` in
`core/image_ops.py`, `CurveWidget` + `CurvesDialog` in `gui/curves_dialog.py`,
the Tools → Curves… wiring in `main_window.py` that superseded Levels), plus
two deferred canvas fixes (D-09 empty-state refresh on the numpy display path,
D-11 empty-hint copy) and the dialog typography fixes (14px base font).

Verification performed: full read of all 7 source files + the 7 test files;
grep audit for stale `levels_dialog`/`LevelsDialog` references (none remain —
the kept `levels_lut`/`levels_page` in `image_ops.py` are untouched per the
diff); live probes of the Qt group-exclusivity wiring and the Show Original
baseline state; full test suites for curves + image-ops pass (49 passed).

The core math (`curve_lut`, `curves_page`) is sound: last-wins dedupe,
endpoint backstops, A1 master→channel composition order, detachment and
validation are all correct and well tested. The dialogs are clean collectors
with correct clamp logic. Three defects were found: one Critical (the Curves
dialog's live preview poisons the Show Original baseline on Cancel for the
common fresh-page case, and activates the before/after compare without any
inpaint), and two Warnings (undo flash mislabels curves as "inpaint"; the new
exclusive-group tool wiring desyncs the dock/toolbar highlights on dock
clicks — probe-verified).

## Critical Issues

### CR-01: Curves dialog Cancel poisons the Show Original baseline and activates the before/after compare without an inpaint

**File:** `manga_ai_studio/gui/main_window.py:1274` (interacting with `manga_ai_studio/gui/canvas.py:742-743` and `manga_ai_studio/gui/canvas.py:769`)

**Issue:** The documented contract is "the preview never poisons the Show
Original baseline" (Pitfall 5/9, `_on_curves` docstring) — but the Cancel path
violates it for the common fresh-page case:

1. `_on_curves` opens the dialog and every control change funnels into the
   live preview via `set_image_from_numpy_preview(composed, capture_original=False)`
   (main_window.py:1267-1269) — the canvas now shows a curve-distorted frame.
2. On Cancel, the restore runs `self.canvas.set_image_from_numpy(base.copy())`
   (line 1274) — the CAPTURE-enabled path. In `_set_image_from_numpy`,
   `_original_image_numpy` is captured once **when it is `None`** (canvas.py:742-743)
   — and it is `None` for every fresh page (folder/image open resets it;
   `rebaseline_original()` is only called by the op apply path). At that moment
   the canvas displays the **last preview frame**, so that frame is stored as
   the "original".
3. Additionally, `_set_image_from_numpy` unconditionally sets
   `self._inpainted_qimage = qimg` (canvas.py:769) — the preview path included.
   So merely opening and canceling the Curves dialog makes
   `has_inpaint_result()` return True: at the next `_refresh_action_states`
   (any subsequent mask stroke, page navigation, etc.) the Show Original
   action (P) and the Preview (hold) toolbar button become enabled, and
   pressing P shows the **curve-distorted preview frame as "the original"**
   while the displayed image is the pre-dialog base — inverted before/after
   semantics, with no inpaint ever having run.

The Apply path is self-healing only because `_apply_geometry_op` calls
`rebaseline_original()` at its tail — the Cancel path has no such re-baseline.

The phase's own regression test masks this exact scenario:
`test_curves_preview_no_baseline_poison` (tests/test_gui_curves_dialog.py:724-727)
calls `window.canvas.rebaseline_original()` **before** opening the dialog, so
`_original_image_numpy` is never `None` and the capture never fires — the test
asserts the poisoned-baseline case does not exist, but never exercises it.

**Fix:** Restore through the capture-suppressed path on Cancel (and on the
apply pre-restore), and stop the preview path from claiming an inpaint result:

```python
# main_window.py, _on_curves Cancel path:
if dialog.exec() != QDialog.DialogCode.Accepted:
    self.canvas.set_image_from_numpy_preview(base.copy(), capture_original=False)
    self.canvas.rebaseline_original()  # honest D-14 baseline = pre-dialog image
    return
```

```python
# canvas.py, _set_image_from_numpy — only claim an inpaint result on the
# capture-enabled path (the preview path must not set _inpainted_qimage):
if capture_original:
    self._inpainted_qimage = qimg
```

Add a regression test variant of `test_curves_preview_no_baseline_poison`
that does **not** pre-baseline (fresh page, `_original_image_numpy is None`),
then cancels and asserts `_original_image_numpy` stays None and
`has_inpaint_result()` stays False.

## Warnings

### WR-01: Undo/redo flash mislabels a curves undo as "Undo: inpaint"

**File:** `manga_ai_studio/gui/main_window.py:2936-2941` (`_undo_op_label_for_result`)

**Issue:** A curves op pushes an image-ONLY geometry record
(`push_geometry_state(pre_image, mask_qimage=None, boxes=None)` — curves is
geometry-free, D-15), so `history.undo()` returns a one-element list
`[("image", ...)]`. `_undo_op_label_for_result` only consults the recorded
op name (`_last_geometry_op_name`, set by `_record_geometry_op_name("curves")`)
when `len(result) > 1`; a single-element result resolves via
`_undo_op_label("image")` → **"inpaint"** (line 2910). Ctrl+Z after applying
Curves therefore flashes "Undo: inpaint" and Ctrl+Shift+Z flashes
"Redo: inpaint" — violating the UI-SPEC surface 28 copy contract, which this
phase explicitly extended with the `curves` op name. The existing tests assert
the restored image but never the flash text, so this is uncovered.

**Fix:** Resolve the label from the recorded geometry-op name for the popped
record regardless of result length. The robust approach is stamp-based —
report whether the pop matched a geometry record from the HistoryManager —
or, minimally, prefer `_last_geometry_op_name` when the popped image entry is
a full-frame `(0, 0)` patch (the geometry-record shape):

```python
def _undo_op_label_for_result(self, result) -> str:
    if len(result) > 1:
        return self._undo_op_label(self._last_geometry_op_name or "edit")
    kind, value = result[0]
    # A geometry record that touched only the image store (curves) pops as a
    # single image entry — label it by the recorded op name, not "inpaint".
    if kind == "image" and self._last_geometry_op_name:
        x, y, _patch = value
        if (x, y) == (0, 0):
            return self._undo_op_label(self._last_geometry_op_name)
    return self._undo_op_label(kind)
```

### WR-02: Tool dock button clicks desync the dock/toolbar highlights (D-10 contract)

**File:** `manga_ai_studio/gui/main_window.py:714-769` + `manga_ai_studio/gui/main_window.py:3140-3158` (`set_active_tool`)

**Issue:** Phase 06 made the six window tool actions checkable members of the
ToolsPanel's exclusive `QActionGroup` (which already holds the panel's own six
actions) so toolbar buttons would mirror the dock. The group now contains 12
mirrored checkable actions, and the `set_active_tool` re-check cascade fights
the group's exclusivity. Probe-verified with the real MainWindow
(offscreen Qt):

- After a user click on the dock's Rectangle button
  (`tools_panel.action_rectangle.trigger()`): the panel's own action ends up
  **unchecked** (`panel action_rectangle.isChecked() == False`), the window
  action + toolbar button checked, and `tools_panel.active_tool()` falls back
  to **`ToolMode.MOVE`** — the dock button loses its highlight and the panel
  reports the wrong tool.
- After a second dock click (Brush): **no** action or toolbar button is
  checked anywhere (`window/panel/toolbar` all False) — the highlight state is
  permanently desynced until a `set_active_tool`-driven path (shortcut, menu)
  runs.

The canvas tool itself is still set correctly (functionality works), but the
D-10 sync contract this change was meant to enforce is broken for the most
common entry path (clicking the dock). The phase's tests only exercise
`set_active_tool`/shortcuts/menu triggers, never a dock-button click, so the
desync is uncovered.

**Fix:** Do not add the window actions to the panel's exclusive group.
Mirror-checked states are already achieved by `set_active_tool`'s explicit
sync (`tools_panel.set_active_tool` + the toolbar loop); keep the window
actions standalone (checkable, ungrouped) and let the toolbar loop drive their
checked state, or (preferred) have both the dock buttons and the toolbar
buttons share the SAME actions and drop the duplicated panel action set.

## Info

### IN-01: Test gap masks CR-01

**File:** `tests/test_gui_curves_dialog.py:724-727`

`test_curves_preview_no_baseline_poison` calls `rebaseline_original()` before
opening the dialog, so it never exercises the `_original_image_numpy is None`
fresh-page state where the Cancel capture poisons the baseline. Add a variant
without the pre-baseline (see CR-01's fix).

### IN-02: CurveWidget margin clicks can move endpoints

**File:** `manga_ai_studio/gui/curves_dialog.py:297-301` (`_add_point`)

A click in the 8px margin outside the plot square maps to unit coordinates
outside [0,255] (e.g. x≈256 at the right margin); `_add_point` clamps x to
255, which hits the white endpoint and moves its y. Clicking just outside the
plot's right edge therefore nudges the white point. Cosmetic, but the hit-test
could reject out-of-plot positions (`widget_to_unit` result outside
[0,255]² → ignore the press) for precision.

### IN-03: Cancel path leaves stale action enablement

**File:** `manga_ai_studio/gui/main_window.py:1271-1275`

`_on_curves` does not call `_refresh_action_states()` after the Cancel
restore, so the (now enabled-by-preview) Show Original / Preview-hold state is
only corrected on the next unrelated refresh. Folded into CR-01's fix (the
preview path no longer sets `_inpainted_qimage`, so this becomes moot).

---

_Reviewed: 2026-08-09T12:00:00Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
