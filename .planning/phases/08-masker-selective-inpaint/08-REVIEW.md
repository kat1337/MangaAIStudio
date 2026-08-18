---
phase: 08-masker-selective-inpaint
reviewed: 2026-08-18T00:00:00Z
depth: standard
files_reviewed: 31
files_reviewed_list:
  - manga_ai_studio/__main__.py
  - manga_ai_studio/config/profile_manager.py
  - manga_ai_studio/core/batch_runner.py
  - manga_ai_studio/core/box_model.py
  - manga_ai_studio/core/detection_boxes.py
  - manga_ai_studio/core/history_manager.py
  - manga_ai_studio/core/image_file.py
  - manga_ai_studio/core/image_ops.py
  - manga_ai_studio/core/mask_planes.py
  - manga_ai_studio/core/project_io.py
  - manga_ai_studio/gui/box_item.py
  - manga_ai_studio/gui/canvas.py
  - manga_ai_studio/gui/inspector_panel.py
  - manga_ai_studio/gui/main_window.py
  - manga_ai_studio/gui/tools_panel.py
  - panelcleaner/config.py
  - tests/test_box_persistence.py
  - tests/test_core/conftest.py
  - tests/test_core/test_batch_runner.py
  - tests/test_core/test_box_model.py
  - tests/test_core/test_detection_boxes.py
  - tests/test_core/test_image_ops.py
  - tests/test_core/test_masker_config_roundtrip.py
  - tests/test_core/test_masker_machinery.py
  - tests/test_core/test_project_io.py
  - tests/test_gui_batch.py
  - tests/test_gui_border_states.py
  - tests/test_gui_detection_boxes.py
  - tests/test_gui_detection_settings.py
  - tests/test_gui_inspector_override.py
  - tests/test_gui_mask_planes.py
findings:
  critical: 4
  warning: 5
  info: 4
  total: 13
status: issues_found
---

# Phase 8: Code Review Report

**Reviewed:** 2026-08-18
**Depth:** standard
**Files Reviewed:** 31
**Status:** issues_found

## Summary

Phase 8 introduces a three-plane mask model, std-dev-gated selective inpaint,
per-box override tri-state, live detection settings, and batch adoption. The
headless core (`detection_boxes.py`, `mask_planes.py`, `project_io.py`,
`image_ops.py`, `box_model.py`, `history_manager.py`) is well-guarded: V5 input
validation, buffer-detachment discipline, and tamper checks on the `.mas` load
path are consistently applied and well tested.

The defects cluster at the **GUI seams** where the new plane/override machinery
meets the pre-existing canvas data model. The central structural weakness: the
live `PageBox.box` attribute is *birth geometry* (the canvas only
re-materializes it inside `boxes_snapshot()`), and several new Phase 8 paths
read `it.pagebox` directly instead of a snapshot — after a move/resize those
consumers paste/refit mask content at the wrong (pre-move) location. Related
seams: the post-batch refresh wipes the current page's manual-stroke planes;
the mask-consumption clear after Inpaint only clears the display composite,
not the planes; and the std-dev threshold slot lacks the no-fit guard its
sibling `_recompose_boxes_auto_plane` has, letting it silently destroy the
auto plane after geometry ops. No security vulnerabilities were found (no
secrets, no eval/subprocess, no injection paths; the persistence boundary is
hardened).

## Critical Issues

### CR-01: Stale `PageBox.box` after move/resize corrupts the recomposed auto mask

**File:** `manga_ai_studio/gui/main_window.py:3064-3073, 3111-3119, 3418-3420, 3730-3744`
**Issue:** The canvas never refreshes `item.pagebox.box` after a move
(`canvas.py:1434` only `setRect`s) or resize (`canvas.py:2435, 2456`); the
current geometry is only materialized inside `canvas.boxes_snapshot()`
(`canvas.py:2150`). Phase 8's live recompose/refit consumers read the live
pageboxes directly:

- `_on_std_dev_threshold_changed` (`main_window.py:3064`) and
  `_recompose_boxes_auto_plane` (`main_window.py:3730`) call
  `compose_auto_binary`, which pastes each stored `pb.mask` at
  `(pb.box.x1, pb.box.y1)` (`detection_boxes.py:360-362`) — the *birth*
  origin.
- `_rederive_auto_layer` (`main_window.py:3112-3115`) passes the stale boxes
  into `derive_page_mask_state`, which re-crops `cut` at the stale box
  (`detection_boxes.py:291, 295`).

`_refit_changed_boxes` correctly fits against the *snapshot* (current
geometry) but then writes only `mask`/`std_dev` back onto the live pagebox
(`main_window.py:3418-3420`), leaving `pagebox.box` stale while its mask is
cropped to the *new* geometry — a poisoned (box, mask) pair. Reproduction:
Detect (mode ON) → move a box → change the dilation radius, the std-dev
threshold, or commit any Inpaint override → the box's mask content is pasted
at its pre-move location. The misplaced composite is what Inpaint (C)
consumes, so LaMa inpaints the wrong region. Existing tests never combine a
move with a threshold/radius/override change, so this is unguarded
(`test_move_commit_refits_box_and_border` checks `current_box()` and
`std_dev` only).

**Fix:** Re-materialize the live geometry at commit time — either in
`_refit_changed_boxes`, also write `live_item.pagebox.box = fitted.box` (and
add the same write to `_commit_resize`/move-commit), or make every recompose
consumer use `self.canvas.boxes_snapshot()` instead of
`[it.pagebox for it in self.canvas._box_items]`:

```python
# main_window.py _refit_changed_boxes
for live_item, fitted in zip(self.canvas._box_items, current):
    live_item.pagebox.box = fitted.box          # keep (box, mask) consistent
    live_item.pagebox.mask = fitted.mask
    live_item.pagebox.std_dev = fitted.std_dev
```

### CR-02: Batch Detect refresh destroys the current page's manual strokes and erase ledger

**File:** `manga_ai_studio/gui/main_window.py:6392-6401`
**Issue:** `_refresh_current_page_after_batch("detect")` restores the packed
auto plane via `canvas.set_planes(empty, empty, auto_bin)` with *explicitly
empty* manual/erase planes. The dispatch-time flush
(`_flush_current_canvas_mask_to_data_model`, `main_window.py:6133-6164`) only
persists the flat composite `ImageFile.mask` — the manual/erase planes live
only on the canvas for the current page. Running Batch → Detect from a page
with hand-painted strokes therefore wipes those strokes (and the erase ledger)
from the canvas, and the next outgoing flush packs the now-empty planes back
into `ImageFile.mask_manual`/`mask_erase`, destroying any persisted copy too.
Nothing consumed the strokes (detect-mode batches never use them), no undo
entry is pushed, and the wipe directly violates the D-01/A10 "hand strokes
always survive (re-)detection" contract that the interactive
`_on_detection_finished` honors (it replaces only the auto plane via
`set_auto_binary`). The comment "batch pages have no strokes" is true only for
non-current pages; the current page is one of the batch's pages.

**Fix:** Only replace the AUTO plane in the detect refresh, leaving the live
manual/erase planes untouched:

```python
if imf.auto_mask is not None:
    page_mask = self.canvas.get_mask()
    h, w = page_mask.height(), page_mask.width()
    self.canvas.set_auto_binary(unpack_binary(imf.auto_mask, h, w))
```

### CR-03: Std-dev threshold change can silently wipe the whole auto plane (missing no-fit guard)

**File:** `manga_ai_studio/gui/main_window.py:3047-3073`
**Issue:** `_on_std_dev_threshold_changed` composes from the live boxes
without the `any(pb.mask is not None)` guard its sibling
`_recompose_boxes_auto_plane` has (`main_window.py:3733-3734`). After a
geometry op (rotate/crop/resize), `_clip_box`/`transform_box_payload`
deliberately invalidate per-box masks (`image_ops.py:177-189, 326-331`) and
`_apply_geometry_op` rebuilds the auto plane from the transformed composite
(`main_window.py:1319-1329`). On such a page, any std-dev threshold tweak
composes an EMPTY binary (`contributing == []`) and
`set_auto_binary(empty)` clobbers the transformed auto plane — a silent,
non-undoable mask loss (the slot is documented as a pure recompose). The same
hazard exists for boxes that never received a fit (e.g. a user-drawn box on a
page detected in mode OFF, then mode switched ON).

**Fix:** Mirror the sibling guard before composing:

```python
current_boxes = [it.pagebox for it in self.canvas._box_items]
if not current_boxes:
    return
if not any(pb.mask is not None for pb in current_boxes):
    return  # no fit data to derive from (post-geometry invalidation)
```

### CR-04: Inpaint/batch-clean mask consumption clears only the display composite — planes resurrect the consumed overlay

**File:** `manga_ai_studio/gui/main_window.py:4990-4993, 6420-6423`
**Issue:** The CR-16 "clear the consumed mask" logic fills the composite
`QImage` transparent (`canvas_mask.fill(Qt.GlobalColor.transparent)` +
`update_mask_display()`), which under the Phase 8 plane model edits only the
*display*. `self._mask_manual`, `self._mask_erase`, and `self._auto_bin` keep
their content, and every later `recompose_mask()` rebuilds the composite from
the planes (`canvas.py:1604-1610`): the consumed overlay reappears as soon as
the user paints one more stroke, undoes a stroke, or switches pages (the
outgoing flush packs the content-bearing planes, and Step 4's
`has_mask_planes()` restore recomposes them — `main_window.py:1762-1778,
1858-1888`). A resurrected overlay over the already-cleaned region causes a
re-run of Inpaint (C) to re-process the cleaned area — exactly the regression
CR-16 was written to prevent. (The batch-clean branch is safe only when
`cleaned.exists()` triggers `set_image_from_path`, which re-seeds the planes.)

**Fix:** Clear the planes (signal-silently) instead of the composite, e.g. in
`EditorCanvas`:

```python
def consume_mask_display(self) -> None:
    """Clear all three planes without emitting mask_modified (consumption)."""
    if self._mask_manual is not None and not self._mask_manual.isNull():
        self._mask_manual.fill(Qt.GlobalColor.transparent)
    if self._mask_erase is not None and not self._mask_erase.isNull():
        self._mask_erase.fill(Qt.GlobalColor.transparent)
    self._auto_bin = None
    self.recompose_mask()
```

and call that from both consumption sites.

## Warnings

### WR-01: Batch detect silently deletes USER boxes on every page (no D-03 merge in the worker)

**File:** `manga_ai_studio/core/batch_runner.py:187, 202`
**Issue:** The interactive path preserves user-drawn boxes on re-detect
(`_build_detected_boxes`, D-03 replace-detected-keep-user,
`main_window.py:4603-4611`). The batch loop builds *only* detected boxes
(`build_detected_pageboxes`) and assigns `page.boxes = boxes`, overwriting any
persisted user boxes on non-current pages with no gate, no merge, and no
notification. A user who hand-drew boxes on other pages loses them by running
Batch → Detect. (The headless no-D-04-gate decision is documented, but the
keep-user half of D-03 was dropped with it.)

**Fix:** Merge persisted USER boxes into the batch result per page:

```python
user_pbs = [pb for pb in (page.boxes or []) if pb.origin == USER]
boxes = user_pbs + build_detected_pageboxes(blk_list, img_w, img_h)
```

### WR-02: Batch detect never marks pages dirty — close loses detected boxes without a prompt

**File:** `manga_ai_studio/gui/main_window.py:6197-6226`
**Issue:** `_on_detection_finished` explicitly calls `_set_session_dirty()`
after the interactive detect (`main_window.py:4539`), but the batch path
(`_on_batch_finished` / `_on_batch_cleanup`) sets no `ImageFile.dirty`, and
the refresh's `set_boxes` runs under `_suppress_boxes_push` which also
suppresses the dirty hook (`main_window.py:2103-2104`). After a detect-only
batch (whose only output is in-memory boxes/masks), closing the window skips
the unsaved-changes prompt and all detected state is lost.

**Fix:** In `_on_batch_cleanup` (or `_on_batch_finished`), mark the touched
pages dirty: `for imf in self.image_files: imf.dirty = True` for detect /
detect_and_clean modes (or at least the current page in the refresh).

### WR-03: Dilation change in mode ON with zero boxes wipes the auto plane (inconsistent with the threshold slot)

**File:** `manga_ai_studio/gui/main_window.py:3075-3119`
**Issue:** `_rederive_auto_layer` mode-ON branch has no `if not boxes:
return` guard: with zero boxes, `derive_page_mask_state` builds an empty box
union, the cut is empty, and `set_auto_binary` receives an all-zero binary —
destroying existing auto content (e.g. a mode-OFF detection's full-heatmap
layer after the user switches Detect Boxes on) just by nudging the radius
slider. The threshold slot guards exactly this case (`if not current_boxes:
return`, line 3065-3066). The two live slots should agree.

**Fix:** Add `if not boxes: return` (or a documented deliberate wipe +
border-status message) in the mode-ON branch of `_rederive_auto_layer`.

### WR-04: `set_masker_values` silently clamps out-of-range profile values — UI display and active profile desync

**File:** `manga_ai_studio/gui/tools_panel.py:586-627`
**Issue:** The widgets clamp to their own ranges (dilation 0-10, std-dev
0-100 with 1 decimal, growth steps 0-50, ...). `MaskerConfig` fields are not
bounded the same way (`mask_max_standard_deviation` has no upper bound;
`mask_growth_steps` `GreaterZero`). A hand-edited profile INI with e.g.
`mask_dilation_radius = 15` or `mask_max_standard_deviation = 200` displays
as 10 / 100.0 while the profile (authoritative for the gate and batch) keeps
15 / 200 — the user sees one setting and the app applies another until a
control is touched.

**Fix:** After `setValue`, read back the clamped widget values and write them
into the `masker_conf` (still inside the `blockSignals` scope), or expand
widget ranges to match `MaskerConfig.fix()` bounds and normalize the profile
on load.

### WR-05: `_save_masker_profile`'s error handling is dead — failed persists are silent

**File:** `manga_ai_studio/config/profile_manager.py:31-39` and `manga_ai_studio/gui/main_window.py:2995-3007`; `panelcleaner/config.py:986-1008`
**Issue:** `Profile.safe_write` catches *all* exceptions internally and
returns a bool; it never raises `OSError`. `ProfileManager.save_profile`
ignores the return value, so `_save_masker_profile`'s `except OSError` branch
is unreachable and a read-only config dir produces no user-visible signal —
the user believes their detection settings persisted when they did not.

**Fix:** Propagate the outcome: have `save_profile` return the bool (or raise
on False), and in `_save_masker_profile` surface a status-bar warning when
the write fails.

## Info

### IN-01: Dead code — `ToolsPanel._on_tool_triggered` is never connected

**File:** `manga_ai_studio/gui/tools_panel.py:308-311`
**Issue:** The `group.triggered` path was superseded by the per-action
`toggled` connection (:230-231); `_on_tool_triggered` is unreachable.
**Fix:** Delete the method (or connect it and drop the toggled path).

### IN-02: Redundant local `import numpy as np` shadows the module-level import

**File:** `manga_ai_studio/gui/main_window.py:4352, 4484, 5204, 5298`
**Issue:** `numpy as np` is already imported at line 38; the four function-
local re-imports are noise that hides the real dependency surface.
**Fix:** Remove the local imports.

### IN-03: Duplicate Inspector reload in `_on_inspector_inpaint_committed`

**File:** `manga_ai_studio/gui/main_window.py:3710`
**Issue:** `boxes_modified.emit(before)` triggers `_on_boxes_modified`, which
already ends with `self._on_canvas_selection_changed()` (line 3343); the
explicit call at line 3710 re-populates the panel a second time per commit.
Harmless (population is signal-blocked) but doubles the work on every
override commit.
**Fix:** Drop the trailing `self._on_canvas_selection_changed()` from the
commit handler.

### IN-04: `json_to_pagebox` does not validate `origin`

**File:** `manga_ai_studio/core/project_io.py:270-278, 342-344`
**Issue:** `std_dev`/`inpaint_override`/`mask` are structurally validated on
load, but `origin` is passed through unvalidated — a crafted `.mas` can
inject an arbitrary string that flows into `PageBox.origin`,
`_ORIGIN_HUES.get(origin, ...)` fallbacks, and `set_boxes` origin-splitting.
Not exploitable (no injection sink; downstream falls back to detected hues),
but inconsistent with the T-08-08 stance applied to the sibling fields.
**Fix:** `if origin not in ("detected", "user"): raise ProjectFormatError(...)`.

---

_Reviewed: 2026-08-18_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
