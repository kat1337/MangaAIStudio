"""Unit tests for the two-stack HistoryManager (core/history_manager.py).

These exercise the MASK and IMAGE undo/redo stacks WITHOUT instantiating any
QWidget (RESEARCH Validation Architecture — D-10: core/ holds pure ops,
testable headless). Only QImage objects are constructed via the qtbot
fixture's QApplication. The two Pitfall-2 regression guards
(``test_mask_snapshot_is_copied`` and ``test_mask_pop_returns_copy``) lock the
``.copy()`` discipline on push AND pop so the history never aliases the
caller's QImage. Marked ``@pytest.mark.unit`` (no torch, no display beyond the
offscreen Qt init).

Plan 06 Task 2 ADDS the GUI wiring tests (test_mask_modified_pushes_to_history,
test_undo_mask_applies_snapshot, etc.) to this same file.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

import numpy as np  # noqa: E402
from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402

from manga_ai_studio.core.history_manager import HistoryManager  # noqa: E402
from manga_ai_studio.core.mask_editor import (  # noqa: E402
    paint_mask_stroke,
)


def _transparent_mask(size: int = 64) -> QImage:
    """Build a transparent ARGB32 QImage (mask-editing target)."""
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    return img


def _painted_mask(brush_size: int, size: int = 64) -> QImage:
    """Build a mask QImage with a single brush dot painted at (size//2, size//2).

    Each call returns a fresh QImage so subsequent mutations on the caller's
    mask do not leak between snapshots.
    """
    mask = _transparent_mask(size)
    center = QPointF(size / 2, size / 2)
    paint_mask_stroke(mask, center, center, brush_size, eraser=False)
    return mask


# ---------------------------------------------------------------------------
# Task 1 — core HistoryManager behavior (no GUI)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_mask_undo_restores_prior_state() -> None:
    """3 pushes, 3 pops — each pop returns the prior mask; 4th pop is None."""
    history = HistoryManager(limit=20)
    m1, m2, m3 = _painted_mask(5), _painted_mask(10), _painted_mask(15)
    history.push_mask_state(m1)
    history.push_mask_state(m2)
    history.push_mask_state(m3)

    # The current mask after pushing all three is conceptually m3 — pop with it.
    cur = _painted_mask(20)
    # Pop 1: returns m3 (the most-recent push).
    prev = history.pop_mask_undo(cur)
    assert prev is not None
    assert prev.pixelColor(32, 32).alpha() == m3.pixelColor(32, 32).alpha()

    # Pop 2: returns m2.
    prev = history.pop_mask_undo(prev)
    assert prev is not None
    assert prev.pixelColor(32, 32).alpha() == m2.pixelColor(32, 32).alpha()

    # Pop 3: returns m1.
    prev = history.pop_mask_undo(prev)
    assert prev is not None
    assert prev.pixelColor(32, 32).alpha() == m1.pixelColor(32, 32).alpha()

    # Pop 4: stack empty.
    prev = history.pop_mask_undo(prev)
    assert prev is None


@pytest.mark.unit
def test_mask_redo_replays() -> None:
    """After 2 undos, redo replays the 2nd then the 3rd; 3rd redo is None."""
    history = HistoryManager(limit=20)
    m1, m2, m3 = _painted_mask(5), _painted_mask(10), _painted_mask(15)
    history.push_mask_state(m1)
    history.push_mask_state(m2)
    history.push_mask_state(m3)

    # Undo twice from the current (m3-like) state — pops return m3 then m2.
    cur = _painted_mask(20)
    history.pop_mask_undo(cur)  # returns m3 (stashed into redo)
    history.pop_mask_undo(cur)  # returns m2 (stashed into redo)

    # Redo twice — replays m3 then m2 (the states we just stashed).
    nxt = history.pop_mask_redo(cur)
    assert nxt is not None
    assert nxt.pixelColor(32, 32).alpha() == m3.pixelColor(32, 32).alpha()
    nxt2 = history.pop_mask_redo(cur)
    assert nxt2 is not None
    assert nxt2.pixelColor(32, 32).alpha() == m2.pixelColor(32, 32).alpha()

    # 3rd redo is None.
    assert history.pop_mask_redo(cur) is None


@pytest.mark.unit
def test_mask_push_clears_redo() -> None:
    """A new edit after an undo invalidates the redo branch."""
    history = HistoryManager(limit=20)
    history.push_mask_state(_painted_mask(5))
    history.push_mask_state(_painted_mask(10))

    # Undo once so the redo stack gets populated.
    cur = _painted_mask(15)
    history.pop_mask_undo(cur)
    assert history.can_redo_mask()

    # Push a new state — the redo branch must be cleared.
    history.push_mask_state(_painted_mask(20))
    assert not history.can_redo_mask()
    # pop_mask_redo returns None (redo stack cleared).
    assert history.pop_mask_redo(cur) is None


@pytest.mark.unit
def test_image_undo_restores_patch() -> None:
    """2 image pushes, 2 pops — each returns the prior (x, y, patch)."""
    history = HistoryManager(limit=20)
    patch_a = np.zeros((4, 4, 3), dtype=np.uint8)
    patch_b = np.ones((4, 4, 3), dtype=np.uint8) * 255
    history.push_image_action(10, 20, patch_a)
    history.push_image_action(30, 40, patch_b)

    # Current image — pop_image_undo swaps the current region into redo and
    # returns the prior patch.
    current = np.zeros((100, 100, 3), dtype=np.uint8)
    res = history.pop_image_undo(current)
    assert res is not None
    x, y, patch = res
    assert (x, y) == (30, 40)
    assert np.array_equal(patch, patch_b)

    res2 = history.pop_image_undo(current)
    assert res2 is not None
    x2, y2, patch2 = res2
    assert (x2, y2) == (10, 20)
    assert np.array_equal(patch2, patch_a)


@pytest.mark.unit
def test_image_redo_replays() -> None:
    """After undoing both edits, redo replays the post-edit regions in order.

    The image_redo branch holds the post-edit region captured at undo time
    (the swap-in step). Redoing returns that captured region so the caller can
    re-apply the edit.
    """
    history = HistoryManager(limit=20)
    # Two edits: edit 1 at (10, 20) wrote value 50; edit 2 at (30, 40) wrote 150.
    # Each push records the PRE-edit region (zeros) so undo restores it.
    pre_edit = np.zeros((4, 4, 3), dtype=np.uint8)
    history.push_image_action(10, 20, pre_edit)
    history.push_image_action(30, 40, pre_edit)

    # The "current" image holds the post-edit state for both regions.
    current = np.zeros((100, 100, 3), dtype=np.uint8)
    current[20:24, 10:14] = 50
    current[40:44, 30:34] = 150

    # Undo both: pop swaps the current post-edit region into redo.
    history.pop_image_undo(current)
    history.pop_image_undo(current)

    # Redo replays edit 1 then edit 2 (LIFO order of the redo stack).
    res = history.pop_image_redo(current)
    assert res is not None
    x, y, patch = res
    assert (x, y) == (10, 20)
    assert np.array_equal(patch, np.full((4, 4, 3), 50, dtype=np.uint8))

    res2 = history.pop_image_redo(current)
    assert res2 is not None
    x2, y2, patch2 = res2
    assert (x2, y2) == (30, 40)
    assert np.array_equal(patch2, np.full((4, 4, 3), 150, dtype=np.uint8))


@pytest.mark.unit
def test_image_undo_swaps_current_into_redo() -> None:
    """pop_image_undo captures the CURRENT image's region into the redo stack.

    Setup: push patch_a (the pre-inpaint content of region [y:y+h, x:x+w]).
    Set the CURRENT image so its region contains a distinct value (e.g., the
    inpainted output). Undo — then redo — the redo patch must match the current
    image's region at undo time, NOT patch_a.
    """
    history = HistoryManager(limit=20)
    patch_a = np.zeros((4, 4, 3), dtype=np.uint8)
    history.push_image_action(5, 5, patch_a)

    # Current image: the region [5:9, 5:9] holds the inpainted result (value 200).
    current = np.zeros((50, 50, 3), dtype=np.uint8)
    current[5:9, 5:9] = 200

    res = history.pop_image_undo(current)
    assert res is not None
    # Undo returned patch_a (the prior content); the redo stack now holds the
    # current image's region at undo time.
    redo = history.pop_image_redo(current)
    assert redo is not None
    _rx, _ry, redo_patch = redo
    # Redo patch should match the current image's region captured at undo time.
    assert np.array_equal(redo_patch, np.full((4, 4, 3), 200, dtype=np.uint8))


@pytest.mark.unit
def test_stack_limit_drops_oldest() -> None:
    """limit=3, push 4 masks — the 4th undo returns None (oldest dropped)."""
    history = HistoryManager(limit=3)
    history.push_mask_state(_painted_mask(5))
    history.push_mask_state(_painted_mask(10))
    history.push_mask_state(_painted_mask(15))
    history.push_mask_state(_painted_mask(20))

    cur = _painted_mask(25)
    # 3 undos possible (the 4th push dropped the 1st/oldest entry).
    assert history.pop_mask_undo(cur) is not None
    assert history.pop_mask_undo(cur) is not None
    assert history.pop_mask_undo(cur) is not None
    # 4th undo: stack is empty.
    assert history.pop_mask_undo(cur) is None


@pytest.mark.unit
def test_clear_resets_all() -> None:
    """After pushes + clear, all four can_* flags are False."""
    history = HistoryManager(limit=20)
    history.push_mask_state(_painted_mask(5))
    history.push_image_action(0, 0, np.zeros((4, 4, 3), dtype=np.uint8))

    assert history.can_undo_mask()
    assert history.can_undo_image()

    history.clear()
    assert not history.can_undo_mask()
    assert not history.can_redo_mask()
    assert not history.can_undo_image()
    assert not history.can_redo_image()


@pytest.mark.unit
def test_mask_snapshot_is_copied() -> None:
    """Push .copy()-detaches: mutating the original does NOT affect the stored snapshot.

    RESEARCH Pitfall 2 regression guard for the push path.
    """
    history = HistoryManager(limit=20)
    mask = _transparent_mask(64)
    history.push_mask_state(mask)

    # Mutate the original mask in place (simulating the live canvas mask being
    # re-painted after the snapshot was taken).
    mask.fill(QColor(0, 255, 0, 255).rgba())

    # Undo with a different current mask — the returned snapshot must NOT reflect
    # the green mutation; it must be the original transparent state.
    cur = _painted_mask(40)
    prev = history.pop_mask_undo(cur)
    assert prev is not None
    # The snapshot pixel (4, 4) was transparent when pushed; the live mask was
    # since filled green. The snapshot must still be transparent (alpha == 0).
    assert prev.pixelColor(4, 4).alpha() == 0


@pytest.mark.unit
def test_mask_pop_returns_copy() -> None:
    """Pop .copy()-detaches: mutating the returned snapshot does NOT affect the internal list.

    RESEARCH Pitfall 2 regression guard for the pop path.

    Setup: push m1. pop_mask_undo returns m1.copy() and stashes current.copy()
    into the REDO stack. We mutate the returned snapshot (the caller now holds
    an alias of m1.copy()). Then we pop_mask_redo — the REDO entry (current)
    must be UNAFFECTED by our mutation of the popped snapshot, proving the
    returned snapshot was detached from BOTH the internal undo list AND the
    redo stash.
    """
    history = HistoryManager(limit=20)
    history.push_mask_state(_painted_mask(20))

    cur = _painted_mask(40)
    popped = history.pop_mask_undo(cur)
    assert popped is not None

    # Mutate the popped snapshot in place — fill with blue.
    popped.fill(QColor(0, 0, 255, 255).rgba())

    # pop_mask_redo returns the redo stash (cur.copy()). It must NOT have the
    # blue mutation (it would only be blue if the redo stash aliased `popped`).
    redo = history.pop_mask_redo(_painted_mask(40))
    assert redo is not None
    blue = QColor(0, 0, 255, 255)
    assert redo.pixelColor(0, 0) != blue


@pytest.mark.unit
def test_can_undo_flags() -> None:
    """can_undo_mask/can_undo_image track stack emptiness after each push/pop."""
    history = HistoryManager(limit=20)

    assert not history.can_undo_mask()
    assert not history.can_redo_mask()
    assert not history.can_undo_image()
    assert not history.can_redo_image()

    history.push_mask_state(_painted_mask(5))
    assert history.can_undo_mask()
    assert not history.can_redo_mask()

    cur = _painted_mask(10)
    history.pop_mask_undo(cur)
    assert not history.can_undo_mask()
    assert history.can_redo_mask()

    history.push_image_action(0, 0, np.zeros((4, 4, 3), dtype=np.uint8))
    assert history.can_undo_image()
    assert not history.can_redo_image()

    current = np.zeros((100, 100, 3), dtype=np.uint8)
    history.pop_image_undo(current)
    assert not history.can_undo_image()
    assert history.can_redo_image()
