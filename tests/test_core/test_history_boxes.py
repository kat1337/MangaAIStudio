"""Tests for the BOXES stack + unified-timeline pop (plan 03-02, D-10/D-11).

Phase 3 adds the third logical stack (BOXES) to ``HistoryManager`` alongside
Phase 1's MASK and IMAGE stacks, plus the unified-timeline ``undo()``/``redo()``
that pops the most-recent-by-stamp across all three stores (D-11). The
monotonic integer stamp counter (Pitfall 4) is what makes the unified timeline
deterministic — wall-clock would skew across threads and produce wrong pop
order.

These tests are headless: they construct ``HistoryManager`` directly and use
simple list-of-tuples inputs for the BOXES snapshot (the BOXES stack is generic
over the snapshot shape — it does not require real ``BoxItem``/``QRectF``
objects to test the stack mechanics; the BoxItem/QRectF materialization is
exercised in plan 03-03's GUI tests). The two MRI-style regression guards:

- ``test_boxes_snapshot_is_detached`` (Pitfall 3): the stored snapshot must not
  alias the caller's list or its items — mirrors Phase 1's
  ``test_mask_snapshot_is_copied``.
- ``test_unified_undo_pops_most_recent_by_stamp`` (Pitfall 4): the merged pop
  pops the store whose tail entry carries the highest stamp, in stamp order.

Marked ``@pytest.mark.unit`` (no torch, no display beyond the offscreen Qt
init that ``QImage`` needs).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402

from manga_ai_studio.core.history_manager import HistoryManager  # noqa: E402


# ---------------------------------------------------------------------------
# Headless QImage helpers (inline — no shared conftest for these; mirror
# tests/test_history.py's _transparent_mask/_painted_mask shape but keep this
# file Qt-light: only transparent masks are needed for the stamp/pop logic).
# ---------------------------------------------------------------------------


def _transparent_mask(size: int = 8) -> QImage:
    """Build a transparent ARGB32 QImage (the simplest non-trivial QImage)."""
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    return img


def _snapshot(spec):
    """Build a simple boxes-snapshot list of (box, origin, payload) tuples.

    The BOXES stack is generic over the snapshot shape — these tests use plain
    tuples so no ``BoxItem``/``QRectF`` machinery is needed to exercise the
    stack mechanics. ``box`` is a placeholder int id, ``origin`` a string
    (e.g. 'detected'/'manual'), ``payload`` an arbitrary dict (the
    op-type/OCR text the caller attaches at its discretion — D-10: op-type
    lives inside each record's metadata, NOT as separate per-type lists).
    """
    return [(idx, origin, payload) for idx, origin, payload in spec]


# ---------------------------------------------------------------------------
# BOXES stack mechanics (D-10)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_push_boxes_state_stores_snapshot_and_clears_redo() -> None:
    """push_boxes_state appends to _boxes_undo and clears _boxes_redo."""
    history = HistoryManager(limit=20)
    snap = _snapshot([(1, "detected", {"text": "a"})])

    history.push_boxes_state(snap)

    assert history.can_undo_boxes()
    assert history._boxes_undo[-1][1] is not None
    # The stored snapshot matches the pushed one (value-wise).
    _, stored = history._boxes_undo[-1]
    assert stored == snap


@pytest.mark.unit
def test_push_boxes_state_clears_redo() -> None:
    """A new boxes push after an undo invalidates the redo branch."""
    history = HistoryManager(limit=20)
    history.push_boxes_state(_snapshot([(1, "detected", None)]))
    # Undo once so the redo stack is populated.
    history.pop_boxes_undo(_snapshot([(99, "current", None)]))
    assert history.can_redo_boxes()

    # A new push must clear the redo branch.
    history.push_boxes_state(_snapshot([(2, "manual", None)]))
    assert not history.can_redo_boxes()


@pytest.mark.unit
def test_pop_boxes_undo_returns_previous_and_stashes_current_into_redo() -> None:
    """pop_boxes_undo returns the prior snapshot and stashes the current."""
    history = HistoryManager(limit=20)
    snap1 = _snapshot([(1, "detected", None)])
    snap2 = _snapshot([(2, "detected", None)])
    history.push_boxes_state(snap1)
    history.push_boxes_state(snap2)

    current = _snapshot([(99, "current", None)])
    prev = history.pop_boxes_undo(current)
    assert prev == snap2  # most-recent first (LIFO)

    # The redo branch now holds the current snapshot.
    assert history.can_redo_boxes()
    redo = history.pop_boxes_redo(_snapshot([(99, "current", None)]))
    assert redo == current


@pytest.mark.unit
def test_pop_boxes_redo_reverses_undo() -> None:
    """After an undo, pop_boxes_redo returns the snapshot that was current."""
    history = HistoryManager(limit=20)
    snap = _snapshot([(1, "detected", None)])
    history.push_boxes_state(snap)
    current = _snapshot([(7, "current", None)])

    history.pop_boxes_undo(current)
    assert history.can_redo_boxes()
    assert not history.can_undo_boxes()

    redo = history.pop_boxes_redo(_snapshot([(7, "current", None)]))
    assert redo == current
    assert not history.can_redo_boxes()
    assert history.can_undo_boxes()  # the snap is back on the undo stack


@pytest.mark.unit
def test_pop_boxes_undo_empty_returns_none() -> None:
    """pop_boxes_undo on an empty stack returns None (no exception)."""
    history = HistoryManager(limit=20)
    assert history.pop_boxes_undo([]) is None
    assert history.pop_boxes_redo([]) is None


@pytest.mark.unit
def test_boxes_overflow_drops_oldest() -> None:
    """limit=2, push 3 boxes snapshots — the oldest is dropped (T-01-16)."""
    history = HistoryManager(limit=2)
    history.push_boxes_state(_snapshot([(1, "detected", None)]))
    history.push_boxes_state(_snapshot([(2, "detected", None)]))
    history.push_boxes_state(_snapshot([(3, "detected", None)]))

    # Only 2 undos possible (the 1st/oldest was dropped).
    assert history.pop_boxes_undo([]) is not None
    assert history.pop_boxes_undo([]) is not None
    assert history.pop_boxes_undo([]) is None


# ---------------------------------------------------------------------------
# Unified-timeline pop (D-11) — the ONE genuinely new algorithm
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_unified_undo_pops_most_recent_by_stamp() -> None:
    """undo() pops the store whose tail entry has the highest stamp.

    Pitfall 4: the monotonic integer stamp gives a total order across all
    three stores. Construct a scenario: push mask (stamp 1), push image
    (stamp 2), push boxes (stamp 3). undo returns ('boxes', ...), then
    ('image', ...), then ('mask', ...).

    NOTE: the unified pop delegates to the per-type pop methods, which need a
    real current value for whichever store they pop (they snapshot current
    into the opposite stack). Passing None only works when boxes is the
    popped store; here mask/image may be popped, so we pass real stand-ins.
    """
    import numpy as np

    history = HistoryManager(limit=20)
    history.push_mask_state(_transparent_mask())    # stamp 1
    history.push_image_action(0, 0, _zero_patch())  # stamp 2
    history.push_boxes_state(_snapshot([(1, "detected", None)]))  # stamp 3

    assert history.can_undo()

    cur_mask = _transparent_mask()
    cur_img = np.zeros((4, 4, 3), dtype=np.uint8)
    kind1, _v1 = history.undo(cur_mask, cur_img, [])
    assert kind1 == "boxes"

    kind2, _v2 = history.undo(cur_mask, cur_img, [])
    assert kind2 == "image"

    kind3, _v3 = history.undo(cur_mask, cur_img, [])
    assert kind3 == "mask"


@pytest.mark.unit
def test_unified_undo_all_empty_returns_none() -> None:
    """undo() returns None when all three undo lists are empty.

    When nothing is on any undo list, no per-type pop is invoked, so passing
    None for the current values is safe (the unified pop returns before
    delegating).
    """
    history = HistoryManager(limit=20)
    assert history.undo(None, None, []) is None


@pytest.mark.unit
def test_unified_redo_mirrors_undo() -> None:
    """redo() pops the most-recent-by-stamp across the REDO lists."""
    import numpy as np

    history = HistoryManager(limit=20)
    # Push mask (stamp 1) then boxes (stamp 2); undo both -> both land on redo.
    history.push_mask_state(_transparent_mask())
    history.push_boxes_state(_snapshot([(1, "detected", None)]))

    cur_mask = _transparent_mask()
    history.undo(cur_mask, cur_img_stand_in(), [])  # pops boxes -> redo
    history.undo(cur_mask, cur_img_stand_in(), [])  # pops mask -> redo

    assert history.can_redo()
    # Redo pops in stamp order: the most-recent redo stamp first (mask, stamped
    # at the 2nd undo, has the higher stamp).
    kind1, _v1 = history.redo(cur_mask, cur_img_stand_in(), [])
    assert kind1 == "mask"
    kind2, _v2 = history.redo(cur_mask, cur_img_stand_in(), [])
    assert kind2 == "boxes"
    assert history.redo(cur_mask, cur_img_stand_in(), []) is None


@pytest.mark.unit
def test_can_undo_can_redo_reflect_union() -> None:
    """can_undo() is True iff any of the three undo lists is non-empty; same redo."""
    history = HistoryManager(limit=20)
    assert not history.can_undo()
    assert not history.can_redo()

    history.push_mask_state(_transparent_mask())
    assert history.can_undo()
    assert not history.can_redo()

    history.undo(_transparent_mask(), cur_img_stand_in(), [])
    assert not history.can_undo()
    assert history.can_redo()


# ---------------------------------------------------------------------------
# Pitfall 3 — snapshot detachment regression guard
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_boxes_snapshot_is_detached() -> None:
    """Mutating the input list (or its items) after push does NOT change the stored snapshot.

    RESEARCH Pitfall 3 regression guard for the BOXES push path (mirrors Phase
    1's ``test_mask_snapshot_is_copied``). The stored snapshot must be an
    independent copy of the caller's list — a live BoxItem's QRectF mutates
    during drag, so a reference would alias and the history would silently
    track the drag instead of the snapshot at push-time.
    """
    history = HistoryManager(limit=20)
    # Use a list with a mutable sub-object (a dict payload) so we can mutate
    # BOTH the container (append/remove) AND a nested mutable.
    payload = {"text": "original"}
    snap = [(1, "detected", payload)]
    history.push_boxes_state(snap)

    # Mutate the caller's list (append a new item) AND the nested payload.
    snap.append((2, "manual", {"text": "new"}))
    payload["text"] = "mutated"

    _, stored = history._boxes_undo[-1]
    # The stored snapshot must NOT reflect the appended item.
    assert len(stored) == 1
    assert stored[0][0] == 1
    # The nested payload dict must NOT reflect the mutation — the snapshot
    # materialized fresh items (the caller's dict is not aliased).
    assert stored[0][2] == {"text": "original"}


# ---------------------------------------------------------------------------
# clear() — all six lists (Pitfall 4 + D-10)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_clear_resets_all_six_lists() -> None:
    """clear() empties mask/image/boxes undo AND redo (all six lists)."""
    history = HistoryManager(limit=20)
    history.push_mask_state(_transparent_mask())
    history.push_image_action(0, 0, _zero_patch())
    history.push_boxes_state(_snapshot([(1, "detected", None)]))

    assert history.can_undo()

    history.clear()
    assert not history.can_undo()
    assert not history.can_redo()
    # Per-type flags also reflect the clear.
    assert not history.can_undo_mask()
    assert not history.can_redo_mask()
    assert not history.can_undo_image()
    assert not history.can_redo_image()
    assert not history.can_undo_boxes()
    assert not history.can_redo_boxes()


# ---------------------------------------------------------------------------
# Pitfall 4 — monotonic integer stamps (no wall-clock)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_stamps_are_monotonic_integers() -> None:
    """Every push stamps a strictly-increasing integer (Pitfall 4).

    Wall-clock/time.monotonic skews across threads; the monotonic integer
    counter gives a deterministic total order. This test pins the shape:
    stamps are ints, and the three stores' tail stamps reflect push order.
    """
    history = HistoryManager(limit=20)
    history.push_mask_state(_transparent_mask())    # stamp 1
    history.push_image_action(0, 0, _zero_patch())  # stamp 2
    history.push_boxes_state(_snapshot([(1, "x", None)]))  # stamp 3

    mask_stamp = history._mask_undo[-1][0]
    image_stamp = history._image_undo[-1][0]
    boxes_stamp = history._boxes_undo[-1][0]

    assert isinstance(mask_stamp, int)
    assert isinstance(image_stamp, int)
    assert isinstance(boxes_stamp, int)
    assert mask_stamp < image_stamp < boxes_stamp


def _zero_patch(size: int = 4):
    """A small zero-valued numpy patch (the image-stack payload shape)."""
    import numpy as np

    return np.zeros((size, size, 3), dtype=np.uint8)


def cur_img_stand_in():
    """A small current-image array for the unified pop's image-swap step.

    The unified pop delegates to ``pop_image_undo`` when image is the popped
    store, which slices ``current[y:y+h, x:x+w]`` to snapshot into redo. The
    push in the unified-undo tests is at (0, 0) with a 4x4 patch, so a 4x4
    current image is large enough.
    """
    import numpy as np

    return np.zeros((4, 4, 3), dtype=np.uint8)
