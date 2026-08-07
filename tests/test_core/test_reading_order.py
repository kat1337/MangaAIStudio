"""Tests for ``manga_ai_studio/core/reading_order.py`` (plan 04-02 Task 2).

This is the Phase 4 headless unit suite for the reading-order algorithm — the
pure-stdlib XY-Cut column-bucketing + per-column top-to-bottom sort, RTL for
manga / LTR for manhwa (CONTEXT D-15), with the preserve-manual conflict
policy (D-16) that keeps a user-set bubble number across a page-level re-auto
(RESEARCH Open Question 3).

Decoupling: these tests do NOT import ``PageBox``. ``assign_bubble_numbers``
reads duck-typed boxes exposing ``.box`` (with an ``xyxy``/``as_tuple`` /
``center`` accessor), ``.bubble_no``, and ``.manual_override`` — so a tiny
``FakeBox`` stands in for the real model (this plan does not depend on Plan 01
landing; the real PageBox now provides those attributes too).

Security: threat T-4-04 (tampering) is the preserve-manual conflict policy —
``assign_bubble_numbers`` MUST NOT silently overwrite a manual_override box's
bubble number (``test_manual_override_preserved`` is the regression guard).

These tests are pure stdlib; they carry the ``unit`` marker and require NO Qt
and NO model weights (headless CI).
"""

from __future__ import annotations

import types

import pytest


class FakeBox:
    """Duck-typed stand-in for a ``PageBox`` — exposes the attributes
    ``assign_bubble_numbers`` reads (``.box`` with a ``.center`` accessor,
    ``.bubble_no``, ``.manual_override``) WITHOUT importing PageBox, decoupling
    this plan from the model layer (Plan 01). Center is taken from the wrapped
    Box, which the test constructs from (cx, cy) by reversing cx=(x1+x2)//2."""

    def __init__(self, center, bubble_no=None, manual_override=False):
        cx, cy = center
        # Reconstruct an xyxy box whose .center returns (cx, cy). The vendored
        # Box.center is ((x1+x2)//2, (y1+y2)//2), so build a 1px box at (cx,cy).
        self.box = types.SimpleNamespace(center=(cx, cy), as_tuple=(cx, cy, cx, cy))
        self.bubble_no = bubble_no
        self.manual_override = manual_override


# ---------------------------------------------------------------------------
# reading_order — the permutation (column bucketing + per-column sort + RTL/LTR)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_reading_order_ltr_two_columns_top_to_bottom() -> None:
    """``reading_order`` with ``rtl=False`` buckets x=50 boxes into column 0
    and x=200 boxes into column 1, sorts each column by y ascending, orders
    columns LTR (leftmost first) → indices ``[0,1,2,3]`` (column 0: (50,10),
    (50,100); then column 1)."""
    from manga_ai_studio.core.reading_order import reading_order

    centers = [(50, 10), (50, 100), (200, 10), (200, 100)]
    order = reading_order(centers, rtl=False)
    assert order == [0, 1, 2, 3]


@pytest.mark.unit
def test_reading_order_rtl_two_columns_rightmost_first() -> None:
    """``reading_order`` with ``rtl=True`` reverses the column order so the
    RIGHTMOST column (manga) comes first → indices ``[2,3,0,1]`` (column at
    x=200 first: (200,10),(200,100); then column at x=50)."""
    from manga_ai_studio.core.reading_order import reading_order

    centers = [(50, 10), (50, 100), (200, 10), (200, 100)]
    order = reading_order(centers, rtl=True)
    assert order == [2, 3, 0, 1]


@pytest.mark.unit
def test_reading_order_single_box() -> None:
    """A single-box page returns ``[0]`` (edge case)."""
    from manga_ai_studio.core.reading_order import reading_order

    assert reading_order([(100, 100)], rtl=True) == [0]
    assert reading_order([(100, 100)], rtl=False) == [0]


@pytest.mark.unit
def test_reading_order_zero_boxes() -> None:
    """A zero-box page returns ``[]`` (edge case)."""
    from manga_ai_studio.core.reading_order import reading_order

    assert reading_order([], rtl=True) == []
    assert reading_order([], rtl=False) == []


@pytest.mark.unit
def test_reading_order_is_permutation_of_range() -> None:
    """The result is ALWAYS a permutation of ``range(n)`` — every box appears
    exactly once, no index out of range, no duplicates."""
    from manga_ai_studio.core.reading_order import reading_order

    centers = [(50, 10), (50, 100), (200, 10), (200, 100), (500, 50)]
    for rtl in (True, False):
        order = reading_order(centers, rtl=rtl)
        assert sorted(order) == list(range(len(centers)))


@pytest.mark.unit
def test_reading_order_column_tolerance_from_own_geometry() -> None:
    """The column tolerance is derived from the page's OWN box geometry (median
    inter-center gap), NOT a fixed pixel constant — pages of different sizes
    bucket correctly. Two clusters with a large gap between them are two
    columns even if the absolute x values are large."""
    from manga_ai_studio.core.reading_order import reading_order

    # Two clusters far apart on x, each with two boxes stacked on y. The
    # inter-cluster gap is huge relative to the within-column spacing, so they
    # MUST split into two columns regardless of absolute page size.
    centers = [(1000, 10), (1000, 100), (5000, 10), (5000, 100)]
    order_ltr = reading_order(centers, rtl=False)
    # LTR: column at x=1000 first (indices 0,1), then x=5000 (indices 2,3).
    assert order_ltr == [0, 1, 2, 3]
    order_rtl = reading_order(centers, rtl=True)
    assert order_rtl == [2, 3, 0, 1]


@pytest.mark.unit
def test_reading_order_within_column_sorted_by_y_ascending() -> None:
    """Within a column, boxes are sorted TOP-TO-BOTTOM by center-y ascending.
    Feed the column out of y-order and confirm the result reorders them."""
    from manga_ai_studio.core.reading_order import reading_order

    # Single column (all same x), given bottom-up; expect top-to-bottom order.
    centers = [(50, 300), (50, 10), (50, 200), (50, 100)]
    order = reading_order(centers, rtl=False)
    # Indices sorted by y ascending: index1(y10), index3(y100), index2(y200), index0(y300)
    assert order == [1, 3, 2, 0]


# ---------------------------------------------------------------------------
# assign_bubble_numbers — the box-level mutation (preserve-manual conflict policy)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_assign_bubble_numbers_sets_sequence_rtl() -> None:
    """``assign_bubble_numbers`` sets ``bubble_no = 1..N`` in reading order on
    non-overridden boxes (RTL: rightmost column first)."""
    from manga_ai_studio.core.reading_order import assign_bubble_numbers

    boxes = [
        FakeBox((50, 10)),   # index 0 — column 0
        FakeBox((50, 100)),  # index 1 — column 0
        FakeBox((200, 10)),  # index 2 — column 1
        FakeBox((200, 100)),  # index 3 — column 1
    ]
    count = assign_bubble_numbers(boxes, rtl=True)
    assert count == 4
    # RTL: column 1 (rightmost) first → indices 2,3 get 1,2; column 0 → 0,1 get 3,4.
    assert boxes[2].bubble_no == 1
    assert boxes[3].bubble_no == 2
    assert boxes[0].bubble_no == 3
    assert boxes[1].bubble_no == 4


@pytest.mark.unit
def test_assign_bubble_numbers_ltr() -> None:
    """LTR (manhwa): leftmost column first."""
    from manga_ai_studio.core.reading_order import assign_bubble_numbers

    boxes = [
        FakeBox((50, 10)),
        FakeBox((50, 100)),
        FakeBox((200, 10)),
        FakeBox((200, 100)),
    ]
    count = assign_bubble_numbers(boxes, rtl=False)
    assert count == 4
    # LTR: column 0 (leftmost) first → indices 0,1 get 1,2; column 1 → 2,3 get 3,4.
    assert boxes[0].bubble_no == 1
    assert boxes[1].bubble_no == 2
    assert boxes[2].bubble_no == 3
    assert boxes[3].bubble_no == 4


@pytest.mark.unit
def test_assign_bubble_numbers_non_overridden_get_false() -> None:
    """Non-overridden boxes are auto-numbered and get ``manual_override=False``
    (they are auto)."""
    from manga_ai_studio.core.reading_order import assign_bubble_numbers

    boxes = [FakeBox((50, 10)), FakeBox((200, 10))]
    assign_bubble_numbers(boxes, rtl=False)
    for b in boxes:
        assert b.manual_override is False


@pytest.mark.unit
def test_manual_override_preserved() -> None:
    """D-16 preserve-manual conflict policy (threat T-4-04): a box with
    ``manual_override=True`` KEEPS its existing ``bubble_no`` and is EXCLUDED
    from the auto sequence — the auto-numbering skips it, leaving a visible
    gap the user resolves (UI-SPEC §17). ``manual_override`` is NOT cleared."""
    from manga_ai_studio.core.reading_order import assign_bubble_numbers

    boxes = [
        FakeBox((50, 10), bubble_no=5, manual_override=True),  # manual — keep 5
        FakeBox((50, 100)),  # auto
        FakeBox((200, 10)),  # auto
        FakeBox((200, 100)),  # auto
    ]
    count = assign_bubble_numbers(boxes, rtl=False)
    assert count == 3  # 3 boxes auto-numbered (the manual one excluded)
    # The manual box keeps its number AND its override flag.
    assert boxes[0].bubble_no == 5
    assert boxes[0].manual_override is True
    # Auto boxes are numbered 1,2,3 in reading order (LTR: col0 first).
    # Reading order LTR over the 4 centers: indices [0(skip),1,2,3].
    # Auto sequence assigns 1->idx1, 2->idx2, 3->idx3.
    assert boxes[1].bubble_no == 1
    assert boxes[2].bubble_no == 2
    assert boxes[3].bubble_no == 3


@pytest.mark.unit
def test_assign_bubble_numbers_does_not_clear_override() -> None:
    """``assign_bubble_numbers`` MUST NOT clear ``manual_override`` on an
    overridden box (it stays True), and MUST NOT renumber it."""
    from manga_ai_studio.core.reading_order import assign_bubble_numbers

    boxes = [FakeBox((50, 10), bubble_no=99, manual_override=True)]
    count = assign_bubble_numbers(boxes, rtl=True)
    assert count == 0  # the one box is manual → 0 auto-numbered
    assert boxes[0].bubble_no == 99
    assert boxes[0].manual_override is True


@pytest.mark.unit
def test_assign_bubble_numbers_empty_no_op() -> None:
    """Empty boxes list is a no-op returning 0."""
    from manga_ai_studio.core.reading_order import assign_bubble_numbers

    assert assign_bubble_numbers([], rtl=True) == 0
    assert assign_bubble_numbers([], rtl=False) == 0


@pytest.mark.unit
def test_assign_bubble_numbers_reads_box_center() -> None:
    """``assign_bubble_numbers`` reads each box's center off ``box.box`` (the
    duck-typed vendored-Box accessor) — it works with a FakeBox whose
    ``.box.center`` is the (cx, cy). Confirms the consumer contract: the center
    is read from ``box.box``, not ``box`` directly (PageBox composes a Box)."""
    from manga_ai_studio.core.reading_order import assign_bubble_numbers

    b = FakeBox((50, 10))
    # The center the algorithm will read.
    assert b.box.center == (50, 10)
    assign_bubble_numbers([b], rtl=True)
    assert b.bubble_no == 1


# ---------------------------------------------------------------------------
# Purity contract (headless, no Qt)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_reading_order_is_pure_no_qt() -> None:
    """The module is pure stdlib (no Qt) so it is headless-testable and CI
    safe. Importing it must not require a QApplication."""
    from manga_ai_studio.core import reading_order

    assert callable(reading_order.reading_order)
    assert callable(reading_order.assign_bubble_numbers)
