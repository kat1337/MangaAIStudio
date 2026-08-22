---
phase: quick-260822-gnq-fix-box-move-auto-re-detect-annoyance-br
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - manga_ai_studio/gui/canvas.py
  - manga_ai_studio/gui/box_item.py
  - manga_ai_studio/gui/main_window.py
  - tests/test_gui_boxes.py
autonomous: true
requirements:
  - QUICK-GNQ-260822
estimate:
  tokens: 90000
  raw_tokens: 45000
  tasks: 3
  confidence: low
must_haves:
  truths:
    - Moving/resizing a box commits instantly with no re-fit, no auto-plane recompose, and no OCR work — mask/std_dev/detection info survive the move untouched.
    - A moved/resized box visibly offers a corner "re-run detection" affordance; clicking it re-fits that box and re-runs OCR once, using the box's CURRENT (post-move) geometry.
    - A freshly created box left alone ~5 s (grace cancelled by any new drag) gets exactly one automatic detection-fit + OCR dispatch; dragging before the timeout cancels it.
    - Single-box and batch OCR workers receive the live rect (BoxItem.current_box()), never the birth pagebox.box — OCR after a move recognizes the moved region.
    - Scrolling/zooming the canvas never resurrects erased or undone brush strokes (no stale viewport blit ghosts).
    - With Move/Pan active, no brush-dot circle cursor renders over the canvas.
  artifacts:
    - manga_ai_studio/gui/main_window.py (stationary-grace timer + re-run handler replacing auto-refit-on-commit)
    - manga_ai_studio/gui/box_item.py (geometry-stale marker + corner re-run affordance)
    - manga_ai_studio/gui/canvas.py (FullViewportUpdate mode + paint-tool-only cursor_item)
    - tests/test_gui_boxes.py (regression guards for all three bugs)
  key_links:
    - canvas move/resize commit -> boxes_modified -> stale-mark + timer arm (NOT refit)
    - re-run affordance click -> canvas signal -> MainWindow per-box refit + OCR(current geometry)
    - _commit_create -> timer arm (replaces the immediate ocr_requested emit)
---

<objective>
Fix three cleaning-canvas bugs: (1) moving/touching a box no longer nukes and re-runs its detection — moves become cheap, a per-box "re-run detection" affordance replaces implicit invalidation, and new/moved boxes get one automatic detection+OCR pass once they sit still for ~5 s; (2) scrolling no longer leaves phantom brush strokes on the canvas; (3) the Move/Pan tool stops showing the red brush-dot cursor. Includes the STATE.md "[Phase 08 follow-up]" OCR birth-geometry fix.

Purpose: the canvas is currently almost unusable after any box touch (synchronous full-page re-fit per micro-move), and two smaller visual defects erode trust in what is actually on the mask.
Output: patched GUI code + regression guards in tests/test_gui_boxes.py, full suite green under the pinned interpreter.
</objective>

<execution_context>
@C:/Users/Stella/.config/opencode/gsd-core/workflows/execute-plan.md
@C:/Users/Stella/.config/opencode/gsd-core/templates/summary.md
</execution_context>

<context>
@manga_ai_studio/gui/main_window.py
  - _on_boxes_modified (:3528) — push hook; currently calls _refit_changed_boxes(:3589) on EVERY commit
  - _refit_changed_boxes (:3591) — the expensive synchronous full-page re-fit; early-returns when imf.raw_detected_mask is None (:3621) which is WHY user boxes never get std_dev
  - _dispatch_ocr_for_box (:5970) — passes box_item.pagebox.box (BIRTH geometry) to the worker (:5986)
  - _run_ocr_task (:6009) — returns {"box_id": id(box_xyxy)}; _on_ocr_finished (:6163) routes by id(it.pagebox.box) == box_id (:6179)
  - run_ocr_all (:6049) — passes [it.pagebox.box ...] birth geometry but routes by id(it.pagebox) (:6083-6084)
  - _on_canvas_ocr_requested (:5956) — D-01 auto-OCR hook, gated on self._op_running
@manga_ai_studio/gui/canvas.py
  - PAINT_TOOLS set (:99); cursor_item construction (:229); _update_cursor_visuals (:1112, no tool check); wheelEvent (:1149); mouseMoveEvent cursor follow (:1445); move-commit WR-04 delta-check (:1509-1530); _commit_resize (:2469); _commit_create (:2504) — emits ocr_requested immediately (:2552); no setViewportUpdateMode call anywhere (default MinimalViewportUpdate)
@manga_ai_studio/gui/box_item.py
  - CornerHandle pattern (:214-240) — ItemIgnoresTransformations children, diagonal cursors; _box_item_at hit-test ignores visual-only overlays (canvas.py:1320)
@.planning/STATE.md — "[Phase 08 follow-up]" entry: OCR crop dispatch passes birth geometry; fix should pass per-item current_box()/boxes_snapshot() geometry while keeping id-routing intact
@tests/test_gui_boxes.py — established GUI test conventions (pytest.importorskip("PySide6"), qtbot fixture, @pytest.mark.gui)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Decouple box move/resize from re-detect; add per-box re-run affordance + 5 s stationary auto-detect/OCR; fix OCR birth-geometry dispatch</name>
  <files>manga_ai_studio/gui/main_window.py, manga_ai_studio/gui/box_item.py, manga_ai_studio/gui/canvas.py</files>
  <action>
All changes honor the CR-01 invariant: never write .box onto a live PageBox; geometry materializes exclusively via BoxItem.current_box() / canvas.boxes_snapshot().

**Stop refit-on-commit (the annoyance core):**
1. In MainWindow._on_boxes_modified, REMOVE the trailing `self._refit_changed_boxes(before_snapshot)` call. Replace it with a new `self._mark_geometry_changed(before_snapshot)` that mirrors _refit_changed_boxes' change-detection prologue verbatim (guards: history None / _suppress_boxes_push / no page / raw_detected_mask irrelevant now; compute `current = canvas.boxes_snapshot()`, `before_tuples` from the payload, changed = current tuples absent from before_tuples — this covers moved, resized AND newly created boxes).
2. _mark_geometry_changed marks each changed BoxItem geometry-stale (see BoxItem changes below), then arms/restarts ONE MainWindow-owned singleshot QTimer (module constant STATIONARY_GRACE_MS = 5000). Do NOT refit, do NOT recompose, do NOT touch masks/std_dev/auto-binary in this path — a move must cost only a setRect + undo push + Inspector reload.
3. Keep the existing `_refit_changed_boxes` method body intact (it is the re-run engine; its docstring's "recompute-on-commit" claim must be updated to "explicit/stationary recompute").

**Cancel-on-interaction:** the canvas must tell MainWindow when a box interaction STARTS so the grace timer cancels mid-grace (desired: "cancelled if actively being dragged"). Add `box_interaction_started = Signal()` to EditorCanvas; emit it from _begin_resize, _select_and_begin_move, and _begin_create_box (the existing arming sites that already capture _boxes_interaction_start_snapshot). MainWindow connects it to `timer.stop()`. Arming the timer again happens naturally via the next boxes_modified commit.

**BoxItem stale marker + re-run affordance:**
4. Add a `geometry_stale` property (default False) + setter on BoxItem. When True: render a small circular re-run affordance child item at the box's TOP-RIGHT corner, built exactly like CornerHandle (child QGraphicsRectItem/EllipseItem, ItemIgnoresTransformations, fixed viewport px size comparable to the 8x8 handles, z above handles' _HANDLE_Z, visible only when geometry_stale AND the layer is visible). Use a distinct fill (suggest amber #f5a623 family to match user-origin hue) with a re-detect glyph or tooltip "Re-run detection (box moved)". Reposition it in _sync_handles so it tracks the live rect. Exclude it from canvas._box_item_at's interactive-item search the same way cursor_item/preview_item are excluded (visual-only overlay).
5. The affordance handles its own left-click: its mousePressEvent accepts the event and emits a new `EditorCanvas.box_redetect_requested = Signal(object)` carrying the parent BoxItem. Wire it in canvas (connect child -> canvas signal) so MainWindow subscribes once to the canvas signal, not to per-item objects.

**MainWindow re-run + stationary handlers (shared engine):**
6. `_on_box_redetect_requested(box_item)`: guard `if self._op_running: return`; clear that item's geometry_stale; run the refit for it (call _refit_changed_boxes with a before-snapshot whose before_tuples EXCLUDE that item's current tuple — i.e. force the changed-set to just that box; the derivation is idempotent per page so refitting all is acceptable and already the documented contract) then `self._dispatch_ocr_for_box(box_item)`.
7. `_on_stationary_grace_timeout()`: guard `self._op_running`; collect all geometry_stale items; for each: clear stale, refit (same engine as #6), and dispatch OCR once per box. If the page has no retained raw_detected_mask, the refit engine's existing early-return stands (silent no-op — honest: no raw to fit against) but the OCR dispatch STILL runs, so a fresh user box finally gets text; document this asymmetry in the docstring.
8. In EditorCanvas._commit_create: DELETE the immediate `self.ocr_requested.emit(item)` (D-01 instant-dispatch is superseded by the grace period) and let the normal boxes_modified commit flow arm the timer via _mark_geometry_changed (the new box IS a changed tuple). Keep the `ocr_requested` signal declared (do not rip out the plumbing) so nothing else breaks; note the semantic change in its docstring comment. The D-04 edited-text confirm gate does NOT apply to these auto dispatches (freshly moved boxes keep their text; OCR re-recognition of a MOVED box with hand-edited text must NOT silently overwrite — so in BOTH handlers #6/#7, skip the OCR leg when `pagebox.has_recognized_text() and pagebox.edited`, mirroring _on_canvas_ocr_requested's sibling gate in run_ocr_selected).

**OCR birth-geometry fix (STATE.md Phase 08 follow-up):**
9. `_dispatch_ocr_for_box`: build the worker args as `Worker(self._run_ocr_task, path, box_item.current_box(), model)` PLUS a routing id that survives the geometry change: pass `id(box_item.pagebox)` as an extra arg and have _run_ocr_task echo THAT as box_id (change the return dict's box_id source from `id(box_xyxy)` to the passed-in routing param). Update `_on_ocr_finished`'s lookup to `id(it.pagebox) == box_id`. Never route on identity of the geometry object anymore — a fresh current_box() Box per dispatch makes the old `id(it.pagebox.box)` contract impossible.
10. `run_ocr_all`: change the geometry list to `[it.current_box() for it in empty_boxes]` (routing list `[id(it.pagebox) ...]` is already correct — verify _on_ocr_all_finished routes on pagebox id and leave it).

Do NOT touch history_manager.py, box_model.py persistence fields, or the save/load paths — the stale marker is ephemeral view state, never persisted.
  </action>
  <verify>
    <automated>& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_boxes.py -x -q</automated>
  </verify>
  <done>A committed move emits boxes_modified but leaves pagebox.mask/std_dev and the auto binary byte-identical; the moved box shows the corner affordance; clicking it (or letting the 5 s timer fire with the interval monkeypatched short in tests) triggers exactly one refit + one OCR dispatch carrying the POST-move rect; a created box dispatches nothing at release but dispatches once after the grace period; starting a second drag inside the grace window cancels the pending dispatch; edited-text boxes are never silently re-OCRed.</done>
</task>

<task type="auto">
  <name>Task 2: Kill the brush-stroke scroll ghost and the Move-tool brush-dot cursor</name>
  <files>manga_ai_studio/gui/canvas.py</files>
  <action>
**Bug 2 (ghost):** the view runs on the default MinimalViewportUpdate scroll-blit path; stale viewport pixels from a just-committed/undone stroke survive scrollContentsBy's blit and only get flushed when an unrelated item update repaints that region (hence "brushing over it again makes it disappear"). Fix in EditorCanvas.__init__ (near the matte/render-hint setup around :339): `self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)`. Accept the repaint-cost tradeoff (documented in a one-line comment citing the ghost defect) — correctness over blit optimization for this canvas size. Do NOT add scattered viewport().update() band-aids in wheelEvent/scroll handlers; the single mode change is the fix.

**Bug 3 (cursor):** in _update_cursor_visuals, first line: `visible = self.current_tool in PAINT_TOOLS` then `self.cursor_item.setVisible(visible)` and early-return from the pen/brush work when not visible. PAINT_TOOLS already exists at canvas.py:99 (BRUSH, RECTANGLE, LASSO, ERASER) — MOVE and CROP get no circle. set_tool (:1094) and the brush-size/tool-color slots already funnel through _update_cursor_visuals, so visibility now tracks tool switches everywhere with zero additional call sites. Check __init__ ordering: _update_cursor_visuals runs at :405 with the default MOVE tool, so the circle is hidden from first paint. Leave the Space-held / middle-button pan ClosedHandCursor behavior untouched.
  </action>
  <verify>
    <automated>& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_canvas.py tests/test_gui_boxes.py -x -q</automated>
  </verify>
  <done>After set_tool(ToolMode.MOVE) the cursor ellipse reports invisible and no red/cyan dot renders while tracking the pointer across the canvas; switching to Brush restores it; after a stroke is undone (apply_undo_mask) followed by a synthetic wheel scroll/zoom, a viewport grab contains no residual stroke pixels (the ghost regression guard).</done>
</task>

<task type="auto">
  <name>Task 3: Regression suite — new guards in test_gui_boxes.py + full pinned-interpreter run</name>
  <files>tests/test_gui_boxes.py</files>
  <action>
Extend tests/test_gui_boxes.py following its existing header conventions (pytest.importorskip("PySide6"), qtbot fixture, @pytest.mark.gui). Add these guards:

1. test_move_commit_does_not_refit: load a canvas with a fitted box (seed pagebox.mask/std_dev + a raw_detected_mask-shaped ImageFile is unnecessary — monkeypatch MainWindow._refit_changed_boxes with a sentinel recorder instead), drag a box via the canvas move path (or call the commit path directly with a real before-snapshot), assert boxes_modified fired AND the sentinel recorded ZERO refit calls AND the box's geometry_stale flag is True.
2. test_stationary_grace_dispatches_once: monkeypatch STATIONARY_GRACE_MS to ~50 ms and stub _dispatch_ocr_for_box + _refit_changed_boxes with recorders; commit a move; qtbot.waitUntil the recorders each hold exactly 1 entry; wait a further grace window and assert still exactly 1 (no repeat firing).
3. test_drag_cancels_pending_grace: arm the timer via a commit, then emit canvas.box_interaction_started before the timeout; advance past the original deadline; assert both recorders are empty.
4. test_create_defers_detection_to_grace: draw-and-release a new box (>8x8); assert NO immediate dispatch (recorders empty right after release) and exactly one OCR + one refit after the shortened grace.
5. test_redetect_affordance_click_refits_with_current_geometry: move a box, invoke the affordance handler (emit canvas.box_redetect_requested with the item), assert the OCR recorder received a Box equal to item.current_box() (post-move coords) and not the birth pagebox.box.
6. test_edited_box_not_auto_reocred: seed a moved box with has_recognized_text()+edited; fire the stationary path; assert refit ran but the OCR recorder stayed empty.
7. test_cursor_hidden_for_move_and_crop / visible for paint tools: set_tool across all six ToolModes, assert cursor_item.isVisible() matches membership in {BRUSH, RECTANGLE, LASSO, ERASER}.
8. test_no_ghost_after_undo_and_scroll: paint a stroke programmatically (paint_mask_stroke into the mask + update_mask_display), restore a clean snapshot via apply_undo_mask, send a QWheelEvent (plain scroll and a Ctrl+wheel zoom variant) through wheelEvent, then grab() the viewport and assert the stroke's center pixel shows no mask-overlay red — assert canvas.viewportUpdateMode() == FullViewportUpdate alongside as the structural guarantee.

Keep each test hermetic: no model loads, no network — always stub the dispatch/refit engines at the MainWindow seam. Then run the FULL suite with the pinned interpreter (never bare python/pytest — AGENTS.md).
  </action>
  <verify>
    <automated>& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q</automated>
  </verify>
  <done>All eight new guards pass; the full suite is green (baseline 552 passed at Phase 5 close — expect ≥560 passed, 0 failed) under C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| GUI thread -> QThreadPool worker | OCR geometry Box crosses the thread boundary |
| Timer callback -> op dispatch | delayed auto-dispatch can pile up with running ops |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-QG-01 | Tampering/Integrity | _on_ocr_finished id-routing | high | mitigate | Route on id(it.pagebox) with the routing id passed through the worker and echoed back — never on the geometry object's identity (a fresh current_box() per dispatch would orphan the old id(it.pagebox.box) contract) |
| T-QG-02 | Denial of Service | stationary timer + re-run handler | medium | mitigate | Both handlers gate on self._op_running and clear the stale flag before dispatch, so rapid move-fire cannot enqueue overlapping workers (T-4-14 precedent) |
| T-QG-03 | Repudiation | auto-OCR overwriting hand-edited text | medium | mitigate | Skip the OCR leg when has_recognized_text() and edited (mirrors run_ocr_selected's D-04 confirm gate); silent overwrite remains correct only for never-recognized boxes |
| T-QG-04 | Information Disclosure | ephemeral geometry_stale flag | low | accept | View-local marker, never persisted to .mas/project files; no data leaves the process |
</threat_model>

<verification>
- Pinned interpreter only: & "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q → all green.
- Manual smoke (optional, after suite): open a page, Detect, drag a box — no stall; corner affordance appears; click it → std-dev/border refresh; draw a new box and wait 5 s → text appears; scroll after undoing a stroke → no ghost; Move tool shows no dot cursor.
</verification>

<success_criteria>
- Box move/resize commit performs zero refit/recompose work and preserves mask/std_dev/detection info.
- Per-box re-run affordance works on moved/resized boxes with post-move geometry; stationary ~5 s grace gives new/idle boxes exactly one auto detection-fit + OCR, cancellable by resuming a drag.
- OCR single + batch workers receive live rects (STATE.md Phase 08 follow-up closed); routing survives via id(pagebox).
- No brush ghost on scroll/zoom; Move/Pan shows no brush-dot cursor.
- Full suite green under the pinned interpreter with new regression guards locking all behaviors.
</success_criteria>

<output>
Create `.planning/quick/260822-gnq-fix-box-move-auto-re-detect-annoyance-br/260822-gnq-SUMMARY.md` when done
</output>
