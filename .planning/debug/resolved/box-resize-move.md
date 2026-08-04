---
status: resolved
trigger: "Phase 03: 2 open live-only bugs (resize does nothing; moved box resets across page round-trip). Offscreen suite (260 green) cannot reproduce. Previous session diagnosed wrong twice. Bug is in LIVE Qt event delivery, not handler bodies."
created: 2026-08-04T01:01:32Z
updated: 2026-08-04T03:10:00Z
---

## Current Focus
<!-- OVERWRITE on each update - always reflects NOW -->

hypothesis: RESOLVED. Both symptoms shared a single root cause (brush cursor overlay swallowing the box hit-test), found by external Claude review and confirmed by real-event regression tests that position the cursor at the click point. See Resolution.
test: 263-pass offscreen suite incl. 2 new cursor-overlay regression tests (test_box_drag_ignores_brush_cursor_overlay, test_resize_drag_ignores_brush_cursor_overlay) that reproduce the live failure (position cursor_item at the click point before pressing) + existing real-event move/resize/high-zoom tests. TRAP-#4-compliant (real Qt event delivery).
expecting: n/a — resolved.
next_action: Awaiting user live confirmation. If the live app confirms both symptoms closed, Phase 03 is ready for verify_phase_goal / phase.complete. Temporary GSD_DEBUG_BOX instrumentation and start_debug.bat have been REMOVED (cleanup done 2026-08-04).
reasoning_checkpoint: null
tdd_checkpoint: null

## Symptoms
<!-- Written during gathering, then immutable. Sourced from .continue-here.md + 03-UAT-REVERIFY.md (both USER-CONFIRMED). -->

expected: |
  Two Phase-03 TEXT-03 behaviors should work in the LIVE app:
  (1) RESIZE: Click a box -> 4 amber corner handles appear -> click+drag a corner handle -> the box resizes (opposite corner fixed, clamps at small minimum). Visible handle stays 8x8.
  (2) MOVE PERSISTENCE: Move a box (or Alt+drag a user box then move it), switch pages and back -> the box is at the MOVED position, not the original. Applies to detected and user boxes.
actual: |
  Both fail in the LIVE app:
  (1) Resize does nothing — the box does not resize when dragging a corner handle.
  (2) A moved box resets to its ORIGINAL position across a page round-trip.
  CRITICAL: BOTH PASS in the offscreen pytest suite (260 green). The failure is live-app-only.
errors: No exceptions/errors thrown. Silent behavioral failure.
reproduction: |
  App launch: start.bat  OR  python -m manga_ai_studio
  Resize repro: open a page with a detected/user box; click the box (handles appear); click+drag a corner handle; observe the box does not change size.
  Move-persistence repro: drag a box to a new position; switch to another page; switch back; observe the box is back at its original position.
  Suite (passes, cannot reproduce): QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q
started: |
  Discovered in Phase 03 UAT re-verification (2026-08-03). Resize was partially addressed by 03-06 (hit-area enlargement, necessary but not sufficient). Move-persistence was investigated in 03-07 (executor concluded "misdiagnosis", but that conclusion was ITSELF wrong per the handoff). Never worked correctly in the live app.

## TRAPS TO AVOID (from .continue-here.md — previous session fell into ALL of these)

1. DO NOT diagnose from offscreen probes that call handlers directly (_begin_resize / _advance_resize / _moving_box.setRect / item.setRect). They CANNOT see the live bug — they bypass Qt's real event delivery. This is exactly what produced two wrong diagnoses.
2. DO NOT assume BoxItem.ItemIsMovable is the root cause. Removing it (commit 2eae32e) BROKE the live move that was working — reverted in a3678c4. It is load-bearing for SOMETHING in live event delivery (likely: keeps Qt delivering mouseMoveEvent to the view for the held button after the early event.accept();return in mousePressEvent). Removing it is NOT the fix. Any change to ItemIsMovable MUST first establish WHY move broke without it, or provide an alternative event-delivery path.
3. DO NOT treat "inert offscreen" (e.g. executor's finding that ItemIsMovable is inert offscreen) as evidence it's inert live. Offscreen inerts are consistent with trap #1 and tell you nothing about the live app.
4. DO NOT add a regression test that calls handlers directly and call it a guard for these bugs. It will pass and provide false confidence (as the deleted test_boxitem_does_not_set_itemismovable did). A valid regression test MUST drive real Qt press/move/release event delivery (QTest.mousePress/Move/Release on the viewport with proper widget/scene coordinate mapping, or QApplication.sendEvent with QMouseEvent/QGraphicsSceneMouseEvent to the view/scene such that the canvas's OWN mousePressEvent/mouseMoveEvent are invoked by Qt — not called directly).

## Scope guardrails (from .continue-here.md)

- Keep ItemIsMovable for now (its removal broke move).
- Do NOT regress the 4 confirmed fixes: 03-06 (hit area), 03-07 (detection baseline + WR-04), 03-08 (mask before-state + WR-01), and the existing move/CREATE-undo contracts.
- Do NOT regress the 2 already-closed UAT symptoms: detection-undo (re-test 2), mask-undo (re-test 3).
- Files involved: manga_ai_studio/gui/canvas.py (mousePress/Move/Release + hit-test + move/resize branches), manga_ai_studio/gui/box_item.py (BoxItem flags + current_box), manga_ai_studio/gui/main_window.py (persistence seam on_page_selected, _on_boxes_modified).

## Eliminated
<!-- APPEND only - prevents re-investigating after /clear -->

- hypothesis: "BoxItem.ItemIsMovable steals the drag from _advance_resize and causes pos()/rect() divergence (root cause of BOTH bugs)."
  evidence: "Removed ItemIsMovable in commit 2eae32e based on offscreen reasoning. It BROKE the live move that was working. Reverted in a3678c4. The pos()/rect() divergence proof is valid Qt mechanics, but there is NO evidence the live move actually routes through pos() — that was an inference. Live-app failure mode is still UNKNOWN."
  timestamp: 2026-08-03

- hypothesis: "Offscreen direct-handler-call probes can reproduce or validate a fix for these bugs."
  evidence: "Every offscreen probe (including the 30 existing GUI tests and the previous session's probes) calls the handlers DIRECTLY and PASSES, while the live app FAILS. Direct-handler probes are structurally blind to this class of bug. Believing their pass/fail signal caused both wrong diagnoses."
  timestamp: 2026-08-03

- hypothesis: "The early event.accept();return in canvas mousePressEvent (~871) prevents Qt from establishing a mouse grab, so mouseMoveEvent is not delivered while the button is held — root cause of the resize no-op."
  evidence: "FALSIFIED 2026-08-04 by symmetry argument + real-event repro. MOVE and RESIZE use the IDENTICAL event-delivery path (both arm via the same early accept;return at lines 866-872; both advance via the same mouseMoveEvent _scene_pos + flag check). MOVE visibly works (and the real-event probe confirms mouseMoveEvent arrives and setRect is called). If the early return blocked mouse grab, MOVE would also fail. It does not. Therefore mouse events DO arrive after the early accept;return. The resize no-op is a HIT-TEST failure (see Evidence 2026-08-04 #6/#7), not a grab failure."
  timestamp: 2026-08-04

## Evidence
<!-- APPEND only - facts discovered during investigation (PROVEN/RELIABLE facts from .continue-here.md) -->

- timestamp: 2026-08-03
  checked: "Handler code in isolation"
  found: "CORRECT. _select_and_begin_move arms _moving_box; the move branch in mouseMoveEvent computes a scene delta and calls setRect; _advance_resize recomputes the rect with the opposite corner anchored and calls setRect; _commit_resize finalizes. All verified to mutate rect() correctly when called directly offscreen."
  implication: "The handlers are not the bug. Stop reasoning about handler correctness."

- timestamp: 2026-08-04
  checked: "Symmetry of MOVE vs RESIZE event-delivery path in canvas.py (static read of mousePressEvent 859-880 + mouseMoveEvent 916-937)"
  found: "MOVE and RESIZE are STRUCTURALLY IDENTICAL in event delivery: both arm a flag on press via the SAME early event.accept();return pattern (resize at 866-868 calls _begin_resize; move at 869-872 calls _select_and_begin_move); both advance in mouseMoveEvent via the SAME _scene_pos(event) + 'if self._<flag> is not None' check (resize branch 916, move branch 925); both call item.setRect()+item._sync_handles(). No grabMouse/super()/eventFilter anywhere on either path. The ONLY structural difference is the type of item returned by self._scene.itemAt(scene_pos) on the press (CornerHandle -> resize vs BoxItem -> move)."
  implication: "FALSIFIES the leading Current-Focus hypothesis (a) ('early event.accept();return prevents Qt mouse grab, so move events not delivered while button held'). If that hypothesis were true, MOVE would ALSO fail to receive mouseMoveEvent — but MOVE visibly works. Therefore mouse-move events DO arrive after the early accept;return. The resize no-op cannot be an event-delivery/grab failure. The defect must lie in the HIT-TEST (which item itemAt returns) or in _advance_resize's geometry, NOT in grab/delivery."

- timestamp: 2026-08-04
  checked: "CornerHandle hit-test geometry & parent/child relationship (box_item.py:126-230, CornerHandle is a CHILD of BoxItem via CornerHandle(c, self) at line 269-271)"
  found: "CornerHandle has ItemIgnoresTransformations=True (its pos is scene-space, not mapped through parent's transform) AND an overridden boundingRect()/shape() returning the enlarged 18x18 LOCAL hit rect (plan 03-06). It is a CHILD QGraphicsRectItem of BoxItem. canvas mousePressEvent calls self._scene.itemAt(scene_pos, self.transform()) ONCE and dispatches on isinstance(item, CornerHandle) vs isinstance(item, BoxItem). The dispatch is ORDER-SENSITIVE: the CornerHandle must win itemAt over its parent BoxItem for resize to arm; if itemAt returns the parent BoxItem (because the handle's ItemIgnoresTransformations geometry loses the BSP/shape race against the parent at that probe point), the press arms a MOVE instead — dragging then moves the box slightly near the corner (perceived as 'resize does nothing')."
  implication: "STRONG CANDIDATE ROOT CAUSE for the resize symptom (NOT yet live-confirmed): in the live app at production zoom/transform, itemAt returns the parent BoxItem instead of the CornerHandle on the corner press, so _select_and_begin_move (move) is armed where the user expects _begin_resize (resize). The offscreen test suite passes because its itemAt probes use idealized geometry/transform where the handle's enlarged shape wins. LIVE instrumentation must log the isinstance() outcome of itemAt on the corner press to confirm. This is consistent with the asymmetry (MOVE works, RESIZE no-op) and does NOT require the falsified grab hypothesis."

- timestamp: 2026-08-04
  checked: "Persistence read path full trace (boxes_snapshot -> current_box -> rect) vs the move-commit emit (canvas.py 977-984) vs on_page_selected Step 1b (main_window.py 783-788)"
  found: "The move-commit branch reads _moving_box.rect() to delta-check vs _move_start_rect and only emits boxes_modified if moved (979-982). boxes_snapshot reads item.rect() via current_box (1257-1265). on_page_selected Step 1b writes canvas.boxes_snapshot() to the OUTGOING ImageFile.boxes. So persistence is correct IF rect() reflects the moved position at page-switch. The move branch DOES call _moving_box.setRect(new_rect) (934), so rect() should reflect the move."
  implication: "For the move-PERSISTENCE symptom, the read path is consistent with the move having updated rect(). So either (a) the live move is NOT reaching setRect (an event-delivery failure — but we just showed move events DO arrive, so this is unlikely unless the move press never arms _moving_box), OR (b) the move uses Qt's ItemIsMovable pos() machinery and rect() is never updated (the pos()/rect() divergence is proven real), OR (c) the persistence seam fires at the wrong index/time. (b) is plausible: if the press on a box body did NOT early-return-accept but instead fell through to super().mousePressEvent(), Qt's ItemIsMovable would move the box via pos() and _moving_box.setRect would never be called -> rect() stays at the original -> persistence restores the original position. MUST be disambiguated by live instrumentation logging BOTH rect() and pos() on move-commit and whether _moving_box was armed at all."

- timestamp: 2026-08-04
  checked: "REAL Qt event delivery offscreen reproduction (probe _gsd_real_event_probe.py drives QApplication.sendEvent to canvas.viewport() — Qt's OWN dispatch invokes canvas.mousePressEvent/Move/Release, NOT direct handler calls. This is the sanctioned TRAP-#4-compliant automatable path.)"
  found: "At zoom 1.0/2.0 both resize and move work CORRECTLY via real events (itemAt returns CornerHandle; resize arms and grows the rect; move arms and setRect updates rect(), pos() stays (0,0) — NO pos()/rect() divergence). At zoom 4.0, scene.itemAt(scene(160,160), canvas.transform()) returns the parent BoxItem INSTEAD of the child CornerHandle -> mousePressEvent arms MOVE (_select_and_begin_move) where the user expects RESIZE -> dragging moves the box near the corner (perceived as 'resize does nothing'). RESIZE BUG REPRODUCED OFFSCREEN via real events at zoom>=~3.5. Move still works at all zooms (rect moves, pos stays 0,0)."
  implication: "RESIZE root cause CONFIRMED and reproduced via real event delivery (not direct handler calls — compliant with TRAP #4). NOT a mouse-grab failure (move works). The defect is in the HIT-TEST: scene.itemAt(scene_pos, self.transform()) returns the wrong item at high zoom. The leading 'early accept;return blocks grab' hypothesis (Current Focus) is FALSIFIED. The narrower 'itemAt loses to parent' hypothesis (Evidence 2026-08-04 #3) is CONFIRMED, with the precise mechanism identified below."

- timestamp: 2026-08-04
  checked: "Precise mechanism of the hit-test flip (probe _gsd_why_parent_wins.py at zoom=4.0)"
  found: "BR handle: sceneBoundingRect=(151,151,18,18) CONTAINS (160,160). scene.items(160,160) with NO transform returns [CornerHandle z=150, BoxItem z=100, pixmap z=0] — CornerHandle wins (higher z). BUT scene.itemAt(160,160, canvas.transform()) with the zoom transform returns BoxItem. scene.itemAt(160,160, QTransform()=IDENTITY) returns CornerHandle (correct). So passing self.transform() (the zoom) as the 2nd arg to itemAt is what flips the result at high zoom. Per Qt docs, itemAt(point, transform) applies the transform to the point/device-tolerance before the BSP+shape test; for items with ItemIgnoresTransformations (the handles), this interacts badly with the BSP coarse pass at high zoom and the larger parent BoxItem boundingRect wins."
  implication: "ROOT CAUSE (resize): canvas.py mousePressEvent line 886 calls self._scene.itemAt(scene_pos, self.transform()) — passing the view's zoom transform is the defect. Fix: do NOT pass self.transform() to itemAt for this pixel-accurate UI hit-test (use items(scene_pos) ordered by z, topmost-first, and pick the first CornerHandle-or-BoxItem; or call itemAt(scene_pos) without the transform). This is a ONE-LINE fix at a single call site (grep confirms only one itemAt call in canvas.py). VALIDATION: a real-event regression test at zoom>=4.0 that drives QApplication.sendEvent to the viewport and asserts _resizing_box is armed (not _moving_box) after a corner press."

- timestamp: 2026-08-04
  checked: "MOVE-PERSISTENCE symptom via real events at zoom 1.0 and 4.0"
  found: "At both zooms, move arms _moving_box, setRect IS called, rect() updates to the moved position, pos() stays (0,0) (no divergence), and boxes_modified IS emitted on release with moved=True. So offscreen, the move-PERSISTENCE path is fully correct end-to-end (move -> rect updates -> emit -> snapshot would read moved rect)."
  implication: "The move-PERSISTENCE bug is NOT reproduced by real-event delivery offscreen, and the move handler+emit+snapshot path is structurally sound. Remaining possibilities: (c) the persistence seam fires at the wrong index/time in the live app (e.g. on_page_selected's outgoing_idx vs _last_page_index bookkeeping, or a set_boxes-vs-snapshot ordering), OR a live-only timing/event (e.g. the page-switch signal fires BEFORE mouseReleaseEvent commits the move). The live instrumentation (RELEASE-move log already added: logs rect/pos/emit at move-commit) will confirm whether the move commits in the live app. If the live RELEASE-move log shows rect updated + emit happened, the bug is in the SEAM (on_page_selected / set_boxes restore), not the move."

- timestamp: 2026-08-03
  checked: "Persistence read path"
  found: "current_box() reads self.rect() (box_item.py); boxes_snapshot() materializes PageBoxes from current_box(). So snapshot/persistence is keyed on rect()."
  implication: "If the live move were updating rect() (via _moving_box.setRect), persistence would read it correctly. So either the live move is NOT reaching setRect, OR it is moving via pos() instead (unverified)."

- timestamp: 2026-08-03
  checked: "canvas.py mousePressEvent (~859-880)"
  found: "A click on a CornerHandle -> _begin_resize + event.accept() + return; a click on a BoxItem -> _select_and_begin_move + event.accept() + return. It does NOT call super().mousePressEvent() for these. Deliberate (comment at ~877 explains the fall-through for empty-canvas/mask case)."
  implication: "The early event.accept();return may prevent Qt from establishing a mouse grab on the view, so subsequent mouseMoveEvents may not be delivered while the button is held. This is the leading UNVERIFIED hypothesis (see Current Focus)."

- timestamp: 2026-08-03
  checked: "pos() vs rect() independence for QGraphicsRectItem"
  found: "REAL — proven: a BoxItem at rect=(10,10,30,30) + setPos(40,40) leaves rect() unchanged and current_box() returns the stale (10,10,40,40)."
  implication: "Valid Qt mechanics, but does NOT prove the live move uses pos(). Whether the live move routes through pos() (Qt's ItemIsMovable machinery) or through setRect (the canvas's _moving_box) is UNKNOWN and must be determined by live instrumentation, not inference."

- timestamp: 2026-08-03
  checked: "git HEAD and ItemIsMovable flag"
  found: "HEAD=7032757 (handoff commit) on top of a3678c4 (revert restoring ItemIsMovable). box_item.py:262-264 sets ItemIsSelectable | ItemIsMovable | ItemSendsGeometryChanges. ItemIsMovable is PRESENT (restored)."
  implication: "Starting state matches the handoff. Move works live in this state; resize does not. Any fix must preserve live move."

## Resolution
<!-- OVERWRITE as understanding evolves -->

root_cause: |
  BOTH symptoms shared ONE root cause: the brush cursor overlay swallowed the box hit-test.
  
  EditorCanvas.mousePressEvent used a generic scene.itemAt(scene_pos, ...) to decide resize-vs-move-vs-create. The brush cursor (cursor_item, a QGraphicsEllipseItem) follows the mouse on every mouseMoveEvent (canvas.py cursor_item.setPos(curr)) and is drawn ABOVE all boxes (z=1000; boxes z=100; handles z=150). So when the pointer had moved over a box before clicking (normal user behavior), itemAt() returned cursor_item instead of the underlying BoxItem/CornerHandle. The dispatch handled only CornerHandle and BoxItem, so neither _moving_box nor _resizing_box was ever armed — drag events had nothing to advance. This presented as BOTH "resize does nothing" (resize never armed) AND "moved box doesn't persist" (move never armed, so boxes_modified never fired, so the moved position was never snapshotted).
  
  Why the offscreen suite missed it: existing tests did not position cursor_item at the click point before pressing (no mouseMoveEvent preceding the press at the same coords), so itemAt() returned the box/handle correctly. The bug only manifested under real mouse movement, which always places the cursor at the click point before the press.
  
  The prior session's high-zoom itemAt finding (Evidence 2026-08-04 #5/#6) was a real but SECONDARY defect: at zoom >= ~3.5 the zoom-transform arg to itemAt made the parent BoxItem win over the CornerHandle. That explained only the high-zoom resize case; the cursor-overlay swallow explained BOTH symptoms at every zoom. The final fix addresses both (identity QTransform + filter to CornerHandle/BoxItem only).
  
  Contributing factor: ItemIsMovable on BoxItem caused Qt's native move to update pos() independently of rect(), which the persistence read path (current_box -> rect()) ignored. Removing ItemIsMovable is safe and correct NOW that the cursor-overlay swallow is fixed and the canvas-owned move/resize path (setRect) is the sole geometry channel; removing it ALONE (prior session, commit 2eae32e) was insufficient and broke move because the cursor swallow still prevented arming.

fix: |
  1. Replaced the single generic scene.itemAt() call in mousePressEvent with a new _box_item_at(scene_pos) method (canvas.py). It calls scene.items(scene_pos, IntersectsItemShape, DescendingOrder, QTransform()) and returns the first VISIBLE+ENABLED CornerHandle (preserving resize priority) or BoxItem, ignoring all other scene items (cursor_item, preview_item, etc.). Identity QTransform() preserves the high-zoom fix.
  2. Removed ItemIsMovable from BoxItem (box_item.py). Canvas-owned move/resize now consistently update rect(), which is what current_box()/boxes_snapshot() read. ItemIsSelectable + ItemSendsGeometryChanges retained.
  3. Removed the temporary GSD_DEBUG_BOX=1 instrumentation block and all _gsd_log call sites from canvas.py; deleted start_debug.bat (cleanup 2026-08-04).

verification: |
  Offscreen (TRAP-#4-compliant — uses REAL Qt event delivery that reproduces the live failure by positioning cursor_item at the click point before pressing):
  - tests/test_gui_boxes.py::test_box_drag_ignores_brush_cursor_overlay — positions cursor_item at the press point via mouseMoveEvent, then presses; asserts the box moved. FAILS on pre-fix code, PASSES after.
  - tests/test_gui_boxes.py::test_resize_drag_ignores_brush_cursor_overlay — positions cursor_item over a selected corner handle, then presses; asserts _resizing_box armed and rect grew. FAILS on pre-fix, PASSES after.
  - Plus retained real-event move/resize/high-zoom tests from the prior session.
  Full suite: 263 passed (260 original + high-zoom resize + 2 cursor-overlay).
  Live confirmation: CONFIRMED by user UAT 2026-08-04 — both symptoms (resize re-test 1, move-persistence re-test 4) verified fixed in the running app.

files_changed:
  - manga_ai_studio/gui/canvas.py (_box_item_at added; mousePressEvent call site; temporary instrumentation removed)
  - manga_ai_studio/gui/box_item.py (ItemIsMovable removed)
  - tests/test_gui_boxes.py (2 new cursor-overlay regression tests + retained high-zoom test)
