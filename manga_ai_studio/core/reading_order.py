"""Reading-order algorithm for the Phase 4 TEXT-05 subsystem.

Returns the index permutation that sorts a page's boxes into reading order,
and assigns page-global bubble numbers (D-15/D-16) to boxes in that order.

Algorithm (RESEARCH Pattern 4 — XY-Cut column-bucketing):
1. Detect vertical column boundaries by clustering center-x values. The
   clustering tolerance is derived from the page's OWN box geometry (the
   median inter-center-x gap), NOT a fixed pixel constant — fixed tolerances
   are fragile across page sizes (RESEARCH Assumption A2, MEDIUM risk).
2. Bucket each box into a column by its center-x cluster.
3. Within each column, sort boxes TOP-TO-BOTTOM by center-y ascending.
4. Order the columns: LTR (manhwa, ``rtl=False``) keeps the leftmost column
   first; RTL (manga, ``rtl=True``) reverses so the rightmost column comes
   first. This is the single-line ``sorted(..., reverse=rtl)`` switch.

Conflict policy (D-16 preserve-manual, RESEARCH Open Question 3, threat
T-4-04): ``assign_bubble_numbers`` skips boxes with ``manual_override=True`` —
they KEEP their existing ``bubble_no`` and their override flag, and the auto
sequence leaves a visible gap where the manual number collides (UI-SPEC §17;
the user resolves the gap). The auto-numbered boxes get
``manual_override=False`` (they are auto).

Consumer contract (the duck-typed attributes this module reads on a box):
- ``box.box.center`` — ``(cx, cy)`` of the vendored ``Box``. PageBox composes
  a vendored ``Box`` whose ``.center`` property returns
  ``((x1+x2)//2, (y1+y2)//2)`` (panelcleaner/structures.py:81). This module
  reads ``getattr(b, 'box', b)`` so it also accepts a bare Box.
- ``box.bubble_no`` — written by ``assign_bubble_numbers``.
- ``box.manual_override`` — read + written by ``assign_bubble_numbers``.

Because the contract is duck-typed, this module does NOT import PageBox — it
works with any object exposing those attributes, which keeps it headless and
decoupled from the model layer.

This module is the pure-Python algorithm substrate beneath the GUI "Auto-Number
RTL/LTR" menu actions (plan 04-07). Building it first as a standalone,
headless, stdlib-only module means plan 04-07 is pure glue — no algorithm
logic in the GUI layer (RESEARCH "Don't Hand-Roll": XY-Cut is the
well-established document-layout algorithm).
"""

from __future__ import annotations

import statistics
from typing import Optional


def _column_id(cx: float, cluster_edges: list, tol: float) -> float:
    """Return the cluster-edge representative for a center-x value.

    Picks the cluster edge whose edge-x is within ``tol`` below ``cx`` (i.e.
    ``cx`` belongs to the nearest cluster whose start is at-or-below ``cx``).
    ``cluster_edges`` is the sorted list of cluster-start x values produced by
    walking the sorted unique center-x values and starting a new cluster when
    the gap to the previous exceeds ``tol``.
    """
    chosen = cluster_edges[0]
    for edge in cluster_edges:
        if edge <= cx + tol:
            chosen = edge
        else:
            break
    return chosen


def reading_order(box_centers_xy: "list[tuple[float, float]]", rtl: bool) -> "list[int]":
    """Return the index permutation that sorts ``box_centers_xy`` into reading
    order.

    Args:
        box_centers_xy: ``[(cx, cy), ...]`` per box (the caller computes centers
            from each box's geometry — see ``assign_bubble_numbers``).
        rtl: ``True`` for manga (right-to-left — rightmost column first);
            ``False`` for manhwa (left-to-right — leftmost column first).

    Returns:
        A permutation of ``range(n)`` such that ``[box_centers_xy[i] for i in
        result]`` is in reading order. For ``n <= 1`` returns
        ``list(range(n))``.

    The column tolerance is derived from the page's OWN geometry: the median
    of the consecutive inter-center-x gaps among the sorted unique x values,
    floored to a 40px minimum so tiny/near-coincident layouts don't fragment.
    """
    n = len(box_centers_xy)
    if n <= 1:
        return list(range(n))

    xs = sorted(cx for cx, _ in box_centers_xy)

    # Derive the column tolerance from the page's own geometry: the median
    # inter-center-x gap (RESEARCH Pattern 4 line 367). A fixed tolerance is
    # fragile across page sizes (RESEARCH Assumption A2). The 40px floor keeps
    # near-coincident layouts from fragmenting into spurious columns.
    if len(xs) > 1:
        gaps = [abs(xs[i + 1] - xs[i]) for i in range(len(xs) - 1)]
        median_gap = statistics.median(gaps)
        col_tol = max(40.0, median_gap)
    else:
        col_tol = 40.0

    # Walk the sorted unique center-x values; start a new cluster when the gap
    # Walk the sorted unique center-x values; start a new cluster when the gap
    # to the PREVIOUS element exceeds col_tol (WR-02: comparing to the previous
    # cluster START instead fragmented columns whose cumulative span exceeded
    # tol while every consecutive gap stayed within it). cluster_edges are the
    # x values that START each cluster (sorted ascending).
    unique_xs = sorted(set(xs))
    cluster_edges: list = [unique_xs[0]]
    prev = unique_xs[0]
    for x in unique_xs[1:]:
        if x - prev > col_tol:
            cluster_edges.append(x)
        prev = x
    col_index = {edge: i for i, edge in enumerate(cluster_edges)}

    # Bucket each box into its column, carrying its index + cy for the
    # within-column sort.
    columns: "dict[int, list[tuple[float, float, int]]]" = {}
    for i, (cx, cy) in enumerate(box_centers_xy):
        cid = col_index[_column_id(cx, cluster_edges, col_tol)]
        columns.setdefault(cid, []).append((cy, cx, i))

    # Order the columns: LTR keeps ascending column ids (leftmost first); RTL
    # reverses so the rightmost column comes first (RESEARCH Pattern 4 line
    # 376 — the single-line RTL/LTR switch).
    ordered_cols = sorted(columns.keys(), reverse=rtl)

    # Within each column, sort by center-y ascending (top-to-bottom).
    result: "list[int]" = []
    for cid in ordered_cols:
        for _cy, _cx, idx in sorted(columns[cid], key=lambda t: t[0]):
            result.append(idx)
    return result


def assign_bubble_numbers(boxes: list, rtl: bool = True) -> int:
    """Assign page-global bubble numbers (1..N) to ``boxes`` in reading order.

    Reads each box's center off ``getattr(b, 'box', b).center`` — the duck-typed
    vendored-Box accessor (PageBox composes a ``Box`` whose ``.center`` returns
    the integer center; panelcleaner/structures.py:81).

    Conflict policy (D-16 preserve-manual, RESEARCH Open Question 3, threat
    T-4-04): boxes with ``manual_override=True`` are SKIPPED — they keep their
    existing ``bubble_no`` AND their ``manual_override`` flag, and the auto
    sequence leaves a visible gap where the manual number collides (UI-SPEC
    §17). Auto-numbered boxes get ``manual_override = False`` (they are auto).

    Args:
        boxes: list of duck-typed boxes (each exposes ``.box.center``,
            ``.bubble_no``, ``.manual_override`` — see the module docstring).
        rtl: ``True`` (default, manga) for right-to-left column order;
            ``False`` (manhwa) for left-to-right.

    Returns:
        The count of boxes that were auto-numbered (manual-override boxes are
        excluded from both the count and the sequence).
    """
    if not boxes:
        return 0

    # Compute centers from each box's geometry. Read ``box.box`` (PageBox
    # composes a vendored Box); fall back to the box itself for a bare Box.
    centers: "list[tuple[float, float]]" = []
    for b in boxes:
        inner = getattr(b, "box", b)
        try:
            cx, cy = inner.center
        except (AttributeError, TypeError, ValueError):
            # Defensive: a box without a usable center is pushed off-page so it
            # sorts last but still gets numbered (preserve total count). This
            # is the ASVS V7 "reported not raised" discipline.
            cx, cy = (float("inf"), float("inf"))
        centers.append((cx, cy))

    order = reading_order(centers, rtl=rtl)

    next_no = 1
    auto_count = 0
    for idx in order:
        box = boxes[idx]
        # Preserve-manual conflict policy (D-16): a manual_override box keeps
        # its existing bubble_no and its flag; it is excluded from the auto
        # sequence (do NOT clear the flag, do NOT renumber).
        if getattr(box, "manual_override", False):
            continue
        box.bubble_no = next_no
        box.manual_override = False
        next_no += 1
        auto_count += 1

    return auto_count
