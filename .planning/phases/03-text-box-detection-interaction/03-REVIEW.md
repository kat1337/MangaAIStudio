---
phase: 03-text-box-detection-interaction
reviewed: 2026-07-29T00:00:00Z
depth: standard
files_reviewed: 16
files_reviewed_list:
  - manga_ai_studio/core/box_model.py
  - manga_ai_studio/core/history_manager.py
  - manga_ai_studio/core/image_file.py
  - manga_ai_studio/gui/box_item.py
  - manga_ai_studio/gui/canvas.py
  - manga_ai_studio/gui/main_window.py
  - panelcleaner/masker.py
  - panelcleaner/structures.py
  - tests/test_core/test_structures.py
  - tests/test_core/test_masker_vendor.py
  - tests/test_core/test_box_model.py
  - tests/test_core/test_history_boxes.py
  - tests/test_gui_boxes.py
  - tests/test_gui_detection_boxes.py
  - tests/test_box_persistence.py
  - tests/test_history.py
findings:
  critical: 1
  warning: 6
  info: 4
  total: 11
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-07-29T00:00:00Z
**Depth:** standard
**Files Reviewed:** 16 (8 production + 8 test)
**Status:** issues_found

## Summary

Phase 3 (text-box detection + interaction) is a well-engineered, mostly-additive
layer on the proven Phase 1/2 pipeline. The vendoring discipline (D-14) is clean
and security-safe (`json.loads` only, no eval/pickle, ost-guard works), the V5
input-validation clamp in `_build_detected_boxes` is correct (bounds-clamp +
zero-area drop), and five of the six documented Pitfalls are genuinely mitigated
in code (Pitfall 2 full-structures, Pitfall 4 monotonic stamps, Pitfall 5
`setVisible`+`setEnabled` belt-and-suspenders, Pitfall 3 snapshot detachment via
fresh-Box materialization, Pitfall 6 `int()` at every `Box`<->`QRectF` boundary).
The HistoryManager unified-timeline pop algorithm is sound, and the 10 migrated
Phase 1 `test_history.py` tests preserve the underlying behavior correctly.

**One BLOCKER dominates this review:** the BOXES undo push hook is **never
wired**. `EditorCanvas` emits `boxes_modified` on every box create / move-commit
/ resize-commit / delete, but `MainWindow` connects only `mask_modified` to
`_on_mask_modified`; there is no `_on_boxes_modified` slot, and `boxes_modified`
has zero consumers in `manga_ai_studio/`. The only `push_boxes_state` call site
is `_build_detected_boxes` (detection). Consequently **box moves, resizes, user
creates (Alt+drag), and deletes are not undoable** — directly violating CONTEXT
D-10 ("Box edits & undo"), D-11 (the unified timeline contract), D-12 ("Safety
comes from D-10/D-11" for silent delete), and UI-SPEC Surface 13 (which contracts
"box create/move/resize/delete" as undoable ops and even names them in the status
feedback copy). The existing tests do not catch this because no GUI test asserts
that a box edit produces a `history.can_undo_boxes()` True state. This must be
fixed before Phase 3 ships.

The remaining findings are robustness/quality issues: a latent
`None.copy()` crash path in the unified undo when the canvas mask is null, a
non-atomic mask-vs-boxes re-detect gate, an unguarded `assert` in the resize
path, an `on_release`-only move-commit that emits `boxes_modified` on plain
select-clicks, and a few info-level items.

## Critical Issues

### CR-01: Box edits (create/move/resize/delete) are never pushed to the BOXES undo stack — Ctrl+Z cannot undo them

**File:** `manga_ai_studio/gui/main_window.py:972` (`_wire_history_actions` — no
`boxes_modified.connect`), and `manga_ai_studio/gui/canvas.py:144,957,1168,1378,1414,1427`
(`boxes_modified` declared + emitted in 5 places with zero consumers)

**Issue:** `EditorCanvas` declares `boxes_modified = Signal()` and emits it on
every box mutation: `_commit_resize` (canvas.py:1378), `_commit_create`
(canvas.py:1414), `_remove_box` (canvas.py:1427, the Delete-key handler), the
move-commit branch of `mouseReleaseEvent` (canvas.py:957), and `set_boxes`
(canvas.py:1168). A full grep of `manga_ai_studio/` for `boxes_modified.connect`
returns nothing — the signal is **never connected to any slot**. The only
`push_boxes_state` call in the entire codebase is `_build_detected_boxes`
(main_window.py:1553), which fires solely on detection.

The Phase 03-05 summary even documents this gap explicitly:
> "the BOXES push hook is NOT wired to boxes_modified — only detection + box
> edits push"

But the second clause ("+ box edits push") is false — no box edit pushes. The
documented mask-side pattern (canvas.py:951 `self.canvas.mask_modified.connect(self._refresh_action_states)` + `_on_mask_modified` → `push_mask_state`) has no boxes analog.

Concrete consequences that violate locked contracts:
- **D-12 broken:** "Delete box is immediate and silent — no confirm dialog.
  Safety comes from D-10/D-11." Delete emits `boxes_modified` (canvas.py:1427)
  but nothing pushes the pre-delete state, so a silent delete is **unrecoverable
  via Ctrl+Z**. This is exactly the data-loss scenario D-12's safety clause was
  written to prevent.
- **UI-SPEC Surface 13 broken:** the surface contracts that Ctrl+Z pops
  "box create|move|resize|delete" ops, and the `_undo_op_label` / status
  feedback copy (`"Undo: box edit"`) advertises this — but the only way a box
  op reaches the BOXES stack is via detection.
- **TEXT-03 partially broken:** "Select, move, resize, and delete text boxes on
  the canvas to correct detection errors" — the correction edits are not
  undoable, so a mis-move/mis-resize/mis-delete cannot be reverted (the user's
  only recourse is to delete and redraw, losing the detected payload).

The tests pass (246 green) only because no GUI test exercises the
"edit-a-box-then-press-Ctrl+Z" path; `test_delete_selected_box_silent` asserts
only that `boxes_modified` emitted, not that a BOXES snapshot was pushed.

**Fix:** Add an `_on_boxes_modified` handler that pushes the current snapshot,
and connect it in `_wire_history_actions` (mirroring the mask path). The
`apply_undo_boxes` restore path must NOT re-push, so guard against the restore
emission (or have the restore path not emit):

```python
# In _wire_history_actions (after the mask_modified.connect line):
self.canvas.boxes_modified.connect(self._on_boxes_modified)

def _on_boxes_modified(self) -> None:
    """boxes_modified hook: push a BOXES snapshot (the D-10 undo record).

    Mirrors _on_mask_modified. boxes_snapshot() materializes fresh int-Boxes
    (Pitfall 3 + 6), so passing the live layer is safe. Suppressed during an
    undo/redo restore so a pop does not re-push (apply_undo_boxes sets a flag).
    """
    if self.history is None or self._suppress_boxes_push:
        return
    if not self.canvas.has_boxes() and not self.history.can_undo_boxes():
        # First edit on an empty layer still pushes the "before" state so the
        # edit is undoable back to empty.
        pass
    self.history.push_boxes_state(self.canvas.boxes_snapshot())
    self._update_undo_redo_actions()
```

Then add `self._suppress_boxes_push = False` in `__init__` and set it `True`
around the `apply_undo_boxes` → `set_boxes` call in `_apply_undo_result` (since
`set_boxes` emits `boxes_modified`). Add a GUI regression test:

```python
def test_box_edit_is_undoable(qtbot, tmp_path) -> None:
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path, size=64)
    # create a user box via the canvas API, then move it, then undo
    ...
    assert window.history.can_undo_boxes()  # the move pushed a snapshot
```

## Warnings

### WR-01: Unified `undo()`/`redo()` can crash with `AttributeError: 'NoneType' .copy()` when the canvas mask is null

**File:** `manga_ai_studio/gui/main_window.py:1062-1074` (`_current_undo_state`)
and `manga_ai_studio/core/history_manager.py:140-154` (`pop_mask_undo`)

**Issue:** `_current_undo_state` returns `current_mask = None` when
`self.canvas.has_mask()` is False (main_window.py:1066-1067). It then passes that
`None` into `self.history.undo(None, current_img, current_boxes)`. If the mask
undo stack is the most-recently-stamped non-empty store, `undo()` sets
`kind == "mask"` and delegates to `pop_mask_undo(None)`, which executes
`self._mask_redo.append((self._stamp(), current_mask.copy()))` (history_manager.py:153)
→ `None.copy()` → `AttributeError`.

The same defect exists symmetrically on the `current_img` path for
`pop_image_undo` (history_manager.py:204 slices `current_img[...]`).

This is currently hard to reach because `_on_mask_modified` guards on
`has_mask()` before pushing, and `reset_history` wipes the stacks on page
switch. But it is reachable any time the mask buffer is nulled while a mask undo
entry survives (e.g. a future code path calling `canvas.clear()` without a
history reset, or a mask reset between a push and an undo). The unified handler
is new in Phase 3 and should not inherit a latent crash from the per-type pops.

**Fix:** Guard the per-type pops against a null current value, or have
`_current_undo_state` pass a fresh transparent QImage of the right size when the
canvas has no mask but the mask stack is non-empty. The simplest robust fix is in
the pops:

```python
def pop_mask_undo(self, current_mask: QImage) -> QImage | None:
    if not self._mask_undo:
        return None
    _stamp, previous = self._mask_undo.pop()
    if current_mask is not None:
        self._mask_redo.append((self._stamp(), current_mask.copy()))
    return previous.copy()
```

### WR-02: Re-detect gate is non-atomic — Cancel on the box-replace gate does not roll back the already-applied mask

**File:** `manga_ai_studio/gui/main_window.py:1466` (mask set) then
`1479-1487` (`_build_detected_boxes` → `_confirm_replace_boxes`)

**Issue:** On a page that has both an existing mask AND existing detected boxes,
`detect_text` runs the mask-replace gate first (main_window.py:1298) and, on
"Replace Mask", launches the worker. When the worker finishes,
`_on_detection_finished` unconditionally applies the **new** mask to the canvas
(line 1466) and THEN calls `_build_detected_boxes`, which may show the
box-replace gate. If the user clicks **Cancel** on the box gate
(`_confirm_replace_boxes` returns False → early return at line 1505), the boxes
are preserved but the mask has already been irreversibly replaced — the original
mask and any manual edits to it are gone, with no rollback.

UI-SPEC D-04 says the box gate "fires AFTER the existing mask-replace gate",
which the code honors, but the spec does not address the case where the user
accepts the mask replace then rejects the box replace. The result is surprising:
two independent gates that the user reasonably expects to be atomic are not.

**Fix:** Either (a) capture the pre-detection mask before the worker starts and
restore it if the box gate is cancelled, or (b) reword the box-replace dialog to
make clear the mask is already replaced ("The mask has been replaced. Replace the
detected text boxes too?"), or (c) move the box-gate check into `detect_text`
before the worker launches (querying `canvas.box_origin_counts()` up front) so
both gates fire before any state mutation. Option (c) is cleanest and matches the
mask gate's pre-worker placement.

### WR-03: Unguarded `assert isinstance(item, BoxItem)` in `_begin_resize` can crash production

**File:** `manga_ai_studio/gui/canvas.py:1359`

**Issue:** `_begin_resize` does `assert isinstance(item, BoxItem), "CornerHandle
must be parented to a BoxItem"`. Assertions are stripped under `python -O`. More
importantly, if a `CornerHandle` is ever orphaned (e.g. its parent was removed
from the scene mid-drag, or a future code path reparents a handle),
`handle.parentItem()` returns `None` and the assert either crashes (debug) or the
next line `self._resize_start_rect = QRectF(item.rect())` raises
`AttributeError: 'NoneType' object has no attribute 'rect'`. The hit-test that
routes here (`isinstance(item, CornerHandle)`) guarantees a CornerHandle, but its
parent is an assumption.

**Fix:** Replace the assert with a real guard:
```python
item = handle.parentItem()
if not isinstance(item, BoxItem):
    return  # orphaned handle — ignore the press
```

### WR-04: A plain box-select click (no drag) emits `boxes_modified` and would push a redundant no-op snapshot

**File:** `manga_ai_studio/gui/canvas.py:954-958` (move-commit branch)

**Issue:** `_select_and_begin_move` always sets `self._moving_box = item` on
press (canvas.py:1346). In `mouseReleaseEvent`, the move-commit branch fires
whenever `_moving_box is not None` — including the case where the user clicked a
box to select it without dragging. On release it emits `boxes_modified`. Today
this is harmless because nothing consumes the signal (see CR-01), but once CR-01
is fixed, this would push a redundant BOXES snapshot whose "before" and "after"
states are identical (a no-op edit consuming a history slot and disabling redo).
The same applies to a resize that didn't move the cursor.

**Fix:** Track whether the box actually moved during the drag and only emit on a
real change:
```python
# in _select_and_begin_move, record the start rect:
self._move_start_rect = QRectF(item.rect())
# in the move-commit branch:
if self._moving_box is not None:
    moved = self._moving_box.rect() != self._move_start_rect
    self._moving_box = None
    if moved:
        self.boxes_modified.emit()
    event.accept()
    return
```
Apply the same delta-check to `_commit_resize` (compare against
`_resize_start_rect`).

### WR-05: `apply_undo_boxes` restore path emits `boxes_modified` which will re-push once CR-01 is fixed (history corruption)

**File:** `manga_ai_studio/gui/main_window.py:1126-1143` (`apply_undo_boxes`)
and `manga_ai_studio/gui/canvas.py:1168` (`set_boxes` emits `boxes_modified`)

**Issue:** `apply_undo_boxes` rebuilds the layer via `self.canvas.set_boxes(...)`
(canvas.py:1143 → set_boxes). `set_boxes` emits `boxes_modified` at its tail
(canvas.py:1168). The docstring at main_window.py:1131-1135 acknowledges this and
claims "the BOXES push hook is NOT wired to boxes_modified" as the safety
property — but that property is exactly the CR-01 bug. The moment CR-01 is fixed
by wiring `boxes_modified` → `_on_boxes_modified`, every undo/redo of a boxes op
will fire `set_boxes` → `boxes_modified` → `push_boxes_state`, pushing the
just-restored state back onto the undo stack and clearing redo. This destroys
redo capability for boxes and corrupts the timeline. The summary's reasoning
("never a pure restore") is built on the bug it needs to defend against.

**Fix:** This is resolved by the `_suppress_boxes_push` flag described in the
CR-01 fix (set True around the `apply_undo_boxes` → `set_boxes` call). Flagging
separately because it is a distinct trap that must be handled as part of the
CR-01 fix, not after.

### WR-06: `set_boxes` does not clear stale interaction state (`_moving_box`/`_resizing_box`/`_creating_box`) — dangling references to removed items

**File:** `manga_ai_studio/gui/canvas.py:1148-1168` (`set_boxes`)

**Issue:** `set_boxes` removes all current `_box_items` from the scene and
rebuilds the list, but does not reset the interaction-state flags. If
`set_boxes` is called while a drag is in progress (e.g. an undo-restore or a
page-switch triggered by a signal during a drag, or detection firing while a
user is mid-resize), `self._moving_box` / `self._resizing_box` can still
reference a now-removed `BoxItem`. The next `mouseMoveEvent` would then call
`item.setRect(...)` / `item._sync_handles()` on a detached item — at best a
no-op (the item is no longer in the scene), at worst a Qt warning or a state
where the release handler emits `boxes_modified` against a stale reference.

**Fix:** Reset the interaction flags at the top of `set_boxes`:
```python
def set_boxes(self, user_pageboxes, detected_pageboxes) -> None:
    # Abort any in-flight box interaction (the items are about to be removed).
    self._resizing_box = None
    self._moving_box = None
    self._creating_box = False
    self._restore_preview_pen()
    for item in self._box_items:
        self._scene.removeItem(item)
    self._box_items = []
    ...
```

## Info

### IN-01: `_idle_status_text` returns `""` when a page is open with no boxes, leaving the status bar blank after the transient message reverts

**File:** `manga_ai_studio/gui/main_window.py:1146-1156` (`_idle_status_text`)

**Issue:** When a page is open and `has_boxes()` is False, `_idle_status_text`
returns `""`. After an undo that removes the last box, `_revert_status_bar`
sets `status_bar_left.setText("")`, leaving the left status field blank rather
than showing a neutral idle message. Minor UX inconsistency (Phase 1 showed
coordinates/zoom in that field per UI-SPEC §Typography "Mono / Status ... status-
bar center (coords + zoom)"). The box-count copy is documented as overwriting
the idle status only "when ≥1 box exists," so blank is arguably spec-compliant,
but a fallback ("Ready" or the zoom text) would be friendlier.

**Fix:** Return a sensible default (e.g. the existing idle status text) instead
of `""`, or document that an empty string is intentional.

### IN-02: `Box.__contains__` uses inclusive `<=` on both edges, so `Box(0,0,10,10)` claims to contain `(10,10)` — the corner one pixel outside the conventional right/bottom edge

**File:** `panelcleaner/structures.py:54-62` (vendored, near-verbatim upstream)

**Issue:** `__contains__` is `self.x1 <= x <= self.x2 and self.y1 <= y <=
self.y2`. For a `Box(0,0,10,10)` (which `as_tuple_xywh` reports as 10×10), the
point `(10,10)` is reported as inside. This is the vendored upstream behavior
(intentional, near-verbatim per D-12), and Phase 3 does not rely on
`__contains__` for hit-testing (it uses `scene.itemAt`), so this is informational
only. Flagging because the RESEARCH "hit-test" claim (`Box.__contains__`) would
be off-by-one if any future code uses it for pixel-accurate containment.

**Fix:** None required for Phase 3 (vendored verbatim per D-12). Note for any
future consumer: treat `Box` containment as inclusive on all four edges (half-
open would be `x < x2`).

### IN-03: `_confirm_replace_boxes` body copy is split across two adjacent string literals — renders correctly but defeats source grep

**File:** `manga_ai_studio/gui/main_window.py:1581-1584`

**Issue:** The D-04 dialog body is `"Replace the detected text boxes with a new
detection? Boxes you" " drew yourself are kept. Undo is available via Ctrl+Z."`
— two adjacent literals that Python concatenates at runtime to the exact UI-SPEC
copy. The 03-04 summary documents this explicitly, so it is not a bug, but any
future auditor grepping for `"Boxes you drew yourself are kept"` will find
nothing in the raw source. This cost review time.

**Fix:** Join into a single string literal for grep-ability, or add a comment
flagging the split.

### IN-04: `current_box()` truncates toward zero via `int()` on potentially-negative float coords from a dragged rect

**File:** `manga_ai_studio/gui/box_item.py:280-285` (`current_box`)

**Issue:** `current_box` materializes `Box(int(r.x()), int(r.y()), int(r.x() +
r.width()), int(r.y() + r.height()))`. Python `int()` truncates toward zero, so
a rect dragged to negative scene coords (e.g. x = -0.7) becomes `int(-0.7) = 0`
rather than `-1` (`floor`). A box dragged partly off-canvas to the upper-left
would snapshot a slightly larger box than the on-screen rect (the negative edge
is rounded up to 0). In practice boxes are clamped to image bounds only at the
detection V5 boundary, not during user drags, so a user can drag a box off the
top-left edge and snapshot a subtly wrong bbox. Magnitude is sub-pixel and
benign for undo/persistence, but inconsistent with the `floor`-style rounding
Pitfall 6 implies.

**Fix:** Use `int(round(...))` or `int(math.floor(...))` consistently at the
materialization boundary if sub-pixel accuracy matters; otherwise document that
`int()` truncation is intentional.

---

## Pitfall Compliance Audit

| Pitfall | Status | Evidence |
|---------|--------|----------|
| **P1** ost-import guard | HONORED | `masker.py:31-33` `try/except ImportError: ost = None`; verified `ost == None` at runtime |
| **P2** full structures.py | HONORED | `panelcleaner/structures.py` 764 lines; `MaskFittingResults` present; import smoke passes |
| **P3** snapshot detachment | HONORED | `boxes_snapshot()` materializes fresh `PageBox(box=item.current_box())` per item (canvas.py:1204-1215); `_materialize_snapshot` deep-copies tuples (history_manager.py:227-251); regression guard `test_boxes_snapshot_detached` |
| **P4** monotonic stamps | HONORED | `_seq` integer counter (history_manager.py:102,113-122); zero wall-clock calls; unified pop compares tail stamps |
| **P5** hidden-layer disable | HONORED | dispatch guards on `box_layer.isVisible()` (canvas.py:843); `set_box_overlay_visible` calls both `setVisible` + `setEnabled` (canvas.py:1175-1180); regression guard `test_hidden_layer_no_box_hit_falls_through_to_mask` |
| **P6** int at Box<->QRectF | HONORED | `current_box()` uses `int()` (box_item.py:281-284); `textblock_to_box` uses `int()` (box_model.py:105-106); `_commit_create` builds `Box(int(...))` (canvas.py:1407). (See IN-04 for a truncation-direction nuance.) |

**Pitfall NOT covered by code (only by the broken hook):** the D-10/D-11/D-12
undo safety that Pitfalls 3/4/6 exist to support is defeated by CR-01 — the
detached, stamped, int-materialized BOXES snapshots are produced by
`boxes_snapshot()` but never pushed on box edits, so the discipline is moot for
the user-facing edit operations.

---

_Reviewed: 2026-07-29T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
