---
phase: 08-masker-selective-inpaint
reviewed: 2026-08-18T13:40:00Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - manga_ai_studio/gui/main_window.py
  - manga_ai_studio/gui/canvas.py
  - manga_ai_studio/core/detection_boxes.py
  - manga_ai_studio/core/batch_runner.py
  - tests/test_gui_gap_closure.py
  - tests/test_core/test_detection_boxes.py
  - tests/test_core/test_batch_runner.py
findings:
  critical: 0
  warning: 2
  info: 2
  total: 4
status: issues_found
---

# Phase 8: Code Review Report — gap-closure (plan 08-10)

**Reviewed:** 2026-08-18
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

This review covers the 08-10 gap-closure commits (`22fafc3..HEAD`, commits
`ec66804`..`8c4b46d`) that fix the six verified defects from
`08-VERIFICATION.md`: CR-01 (recompose consumers read `canvas.boxes_snapshot()`
instead of stale live `pagebox.box`), CR-03 (no-fit guard in
`_on_std_dev_threshold_changed` + WR-03 zero-boxes guard in
`_rederive_auto_layer`), CR-04 (new `canvas.consume_mask_display()` clears all
three planes signal-silently at both consumption sites), CR-02 (detect-mode
batch refresh uses `set_auto_binary` instead of `set_planes` with explicit
empty manual/erase), WR-01 (new headless `merge_page_boxes_for_detect()` in
detection_boxes.py; the batch worker assigns `page.boxes = merged`), and WR-02
(`_on_batch_finished` dirties `ImageFile.dirty` in detect/detect_and_clean
modes).

**The six headline defects are correctly fixed.** The diffs match the plan's
intent line-for-line: all three recompose consumers compose from
`boxes_snapshot()` (which materializes current int geometry AND carries
`mask`/`std_dev`/`inpaint_override` — canvas.py:2141-2196); the threshold slot
gains the byte-mirrored no-fit guard; the re-derive gains the `if not boxes`
guard plus the `_refit_changed_boxes`-style live write-back; the new
`consume_mask_display()` clears manual/erase/auto planes and never emits
`mask_modified` (no spurious mask-undo entry, CR-16 contract preserved); the
detect-batch restore replaces only the auto plane (live manual/erase survive);
the batch worker merges kept-user boxes before deriving and persists
`page.boxes = merged`; and detect-mode batch completion dirties the pages so
Close prompts save. Both headless suites (22 passed) and the 6 new GUI probes
all pass on the fixed code, and the probes' assertions reproduce the recorded
pre-fix failure signatures (moved-rect regressions, wiped plane, wiped
strokes).

No security vulnerabilities were introduced by the change set: the new code
adds no input surfaces, no injection sinks, no new file writes, and
`detection_boxes.py` stays headless/Qt-free (locked by a hermetic subprocess
test).

The residual findings below are **edge cases in the same root-cause family**
the plan explicitly scoped around:

1. **WR-02's dirty fix does not cover the cancel/abort path** — a canceled
   detect batch leaves already-processed pages mutated-but-clean, so Close
   still silently drops freshly detected boxes.
2. **The WR-03 guard is incomplete for the stale retained-raw case** — the
   re-derive (and the refit path) can still silently wipe the auto plane after
   a dims-preserving geometry op (e.g. a 180° rotate) because the retained
   `raw_detected_mask` is never invalidated by `_apply_geometry_op`.

Two Info items document a pre-existing stale-geometry residual in the OCR path
and imprecise over-dirtying.

## Warnings

### WR-01: WR-02 dirty-marking is skipped on batch cancel/abort/error — detected boxes still silently lost

**File:** `manga_ai_studio/gui/main_window.py:6257-6260` (`_on_batch_finished`); `6275-6321` (`_on_batch_cleanup`)
**Issue:** The dirty loop lives only in `_on_batch_finished`, which the Worker
fires exclusively on the successful `result` path
(`worker_thread.py:152-165`: on `Abort` it emits `aborted`, on exception it
emits `error`, neither emits `result`). `_on_batch_cleanup` (connected to
`aborted` **and** `finished`) never marks dirty. A user who cancels a
multi-page detect batch mid-run (`Esc` → `_cancel_batch`, a first-class
affordance) leaves every already-processed page with `page.boxes`/`auto_mask`/
`mask` mutated in memory (the loop writes each page's state before the next
loop-top abort check — `batch_runner.py:193-215` sets `page.boxes = merged`
before the *next* page's abort gate), but no `ImageFile.dirty` is set. Closing
the window then skips the Unsaved-Changes prompt and the freshly detected
boxes/masks on those pages are dropped with no warning — exactly the WR-02
data-loss class, still reachable through the cancel path.

**Fix:** Mark dirty in the mode-aware cleanup path too, so both the result and
the abort/error endpoints dirty the processed pages (`_on_batch_cleanup`
already captures `batch_mode` before resetting it). Because the summary (and
therefore `ok`) is unavailable on abort, mark every page dirty in
detect/detect_and_clean modes whenever the worker actually started — this is
conservative (a page the abort skipped never gets new state, so dirtying it
only prompts an unnecessary save prompt, never data loss) and closes the hole:

```python
def _on_batch_cleanup(self, _args) -> None:
    cancelled = self._batch_cancelled
    batch_mode = self._batch_mode
    if not cancelled:
        self._refresh_current_page_after_batch(batch_mode)
    if batch_mode in ("detect", "detect_and_clean"):
        for imf in self.image_files:
            imf.dirty = True
        self._update_title()
    self._op_running = False
    ...
```

(Alternatively, keep the loop in `_on_batch_finished` AND add it to the
`aborted`-only cleanup path; either way the abort endpoint must dirty.)

### WR-02: Stale retained raw + dims-preserving geometry op → silent auto-plane wipe via `_rederive_auto_layer`/`_refit_changed_boxes`

**File:** `manga_ai_studio/gui/main_window.py:3110-3150` (`_rederive_auto_layer`), `3421-3453` (`_refit_changed_boxes`), `1357-1358` (`_apply_geometry_op`)
**Issue:** `_apply_geometry_op` transforms the auto plane (rotate-180 →
`set_planes(None, None, new_mask_bin)` — the composite becomes the auto plane)
and rotates every box (whose `mask`/`std_dev` are deliberately reset to `None`
— `image_ops.py:144-148, 180-188`), **but never invalidates
`ImageFile.raw_detected_mask`**. The retained raw is only set by detection and
loaded by project-load (`main_window.py:4563/4586/2560`); nothing clears it on
a geometry op.

The 08-10 re-derive/refit guards check only the byte length of the packed raw
(`if len(imf.raw_detected_mask) != (h * w + 7) // 8`, lines 3116/3427), which
**passes for a 180° rotate** (and for any 90° rotate on a square page) because
the dims are preserved while the raw content is now misaligned. So the
reachable sequence is:

1. Detect (mode ON): `raw_detected_mask` retained in the original orientation.
2. Rotate 180° (Tools → Rotate, D-14 silent apply): the canvas auto plane
   holds the correctly-rotated content, per-box masks are `None`, boxes are at
   rotated positions, `raw_detected_mask` is untouched (still unrotated).
3. Nudge the dilation radius (Tools dock slider, a live D-10 parameter) →
   `_on_dilation_changed` → `_rederive_auto_layer` mode-ON:
   - zero-boxes guard passes (boxes exist);
   - dims guard passes (w·h unchanged);
   - `derive_page_mask_state(rotated_img, unrotated_raw, rotated_boxes, ...)`
     → the unrotated raw content overlaps none (or wrongly) of the rotated
     boxes → every `_fit_one_box` returns `(None, None)` → `compose_auto_binary`
     returns an all-zero binary → `set_auto_binary(empty)` **silently wipes the
     rotated auto plane, non-undoably** (settings changes push no history).

This is the same CR-03 silent-wipe class the plan closed for the threshold slot
(its `any(pb.mask is not None)` guard) but the WR-03 guard added to the
re-derive only covers the **zero-boxes** case, not the **all-no-fit /
misaligned-raw** case. The identical hazard exists in `_refit_changed_boxes`
(a box move after the rotate re-fits against the same misaligned raw).
`_recompose_boxes_auto_plane` and `_on_std_dev_threshold_changed` are safe
(pure recompose of stored fits, and their no-fit guard returns early), which
is why the CR-03 probes cannot catch this — no probe combines a dims-preserving
geometry op with a live parameter change (the plan itself notes WR-03 is
source-asserted only).

**Fix:** Invalidate the retained raw when a geometry op runs — the honest
root-cause fix that also covers `_refit_changed_boxes` and matches the 08-01
invalidation policy. In `_apply_geometry_op`, when `geometry` is True (or
whenever `transform_fn` touched image dims/geometry), clear the stale raw
(and the derived-plane slots) on the current `ImageFile`:

```python
idx = self._current_page_index()
if idx is not None and 0 <= idx < len(self.image_files):
    self.image_files[idx].auto_mask = None
    self.image_files[idx].raw_detected_mask = None  # no longer in page frame
```

As belt-and-suspenders, mirror the threshold slot's no-fit guard in
`_rederive_auto_layer` after the derive (skip `set_auto_binary` when the
derivation produced no participating fits):

```python
if not any(pb.mask is not None for pb in boxes):
    return  # every box failed the fit — do not clobber the plane with empty
```

and add a probe covering "rotate 180 → dilation nudge → auto plane retains
content" (the gap-closure suite currently has no probe for the re-derive path).

## Info

### IN-01: OCR dispatch still crops at birth geometry after a move (CR-01 root cause residual, pre-existing)

**File:** `manga_ai_studio/gui/main_window.py:5191` (`_dispatch_ocr_for_box`), `5288` (`run_ocr_all`)
**Issue:** The gap-closure plan deliberately keeps `pagebox.box` as birth
geometry (no `.box` write-back, to preserve `id(box)` routing in
`_on_ocr_finished`, `main_window.py:5384`). The single-box and OCR-All paths
pass `it.pagebox.box` into the worker, which crops
`image[y1:y2, x1:x2]` at that stale (pre-move) rect (`_run_ocr_task` /
`_run_ocr_all_task`). So after Detect + move a box, **Run OCR and OCR All
recognize the pre-move region** — the same stale-geometry family the plan
fixed for the recompose consumers was not extended to the OCR crop. Pre-existing
(reachability predates plan 08-10) and out of the six-fix scope, but it shares
the CR-01 root cause and is user-reachable.
**Fix:** Pass a materialized box into the worker instead of the live pagebox:
`self.canvas.boxes_snapshot()` for `run_ocr_all`, or a per-item
`box_item.current_box()` — and keep the identity for the result routing via
`id(it.pagebox)` (the OCR-All path already passes `id(it.pagebox)` separately,
so only the crop geometry needs to come from `current_box()`).

### IN-02: WR-02 dirty loop over-marks pages that `failed` (untouched by the batch)

**File:** `manga_ai_studio/gui/main_window.py:6257-6260`
**Issue:** `_on_batch_finished` sets `imf.dirty = True` for **every**
`ImageFile` when `ok > 0`, including pages recorded in the summary's `failed`
list (whose `page.boxes`/`mask` were never mutated) and — in the detectable
case — pages that were skipped. In the normal all-succeed case this is exact,
and over-dirtying is only conservative (it prompts a save that has nothing to
persist); it never loses data. Low impact, but the loop could be scoped to the
succeeded pages via the failed-path set for precision.
**Fix:** Set dirty only for pages whose path is not in
`{p for p, _ in summary.get("failed", [])}`:

```python
if ok > 0 and self._batch_mode in ("detect", "detect_and_clean"):
    failed_paths = {p for p, _ in summary.get("failed", [])}
    for imf in self.image_files:
        if imf.path not in failed_paths:
            imf.dirty = True
    self._update_title()
```

---

_Reviewed: 2026-08-18_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
