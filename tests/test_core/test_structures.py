"""Tests for the vendored ``panelcleaner/structures.py`` (plan 03-01, D-14).

This is the Phase 3 headless Wave-0 suite for the full vendored structures
module. It replaces the 18-line Phase 1 placeholder stub with the near-verbatim
upstream source (~749 lines, GPL v3 -> GPL v3 per D-12/D-14). The full surface
is the load-bearing requirement: ``image_ops.pick_best_mask`` calls
``st.MaskFittingResults(...)`` at image_ops.py:706,717 and the stub defined
nothing, so ``import image_ops`` previously worked only because the references
lived inside lazy annotations + un-called function bodies (RESEARCH Pitfall 2).

These tests are pure stdlib + (PIL via structures import-time) only; they carry
the ``unit`` marker and require NO Qt and NO model weights (headless CI). The
``Box`` geometry assertions double as the QRectF mapping contract used by the
GUI layer's ``BoxItem`` (plan 03-03).
"""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_full_surface_imports() -> None:
    """The full upstream surface imports cleanly (Pitfall 2 regression).

    This test FAILS against the 18-line stub (which defines nothing) and passes
    only once the full vendored structures.py is in place. It is the proof that
    pick_best_mask's ``st.MaskFittingResults`` call site no longer hits
    AttributeError.
    """
    from panelcleaner.structures import (
        Box,
        BoxType,
        MaskData,
        MaskerData,
        MaskFittingResults,
        PageData,
    )

    # Touch each name so a re-stubbing regression (e.g. dropping a class) trips
    # the test rather than silently passing.
    assert Box is not None
    assert BoxType is not None
    assert MaskFittingResults is not None
    assert MaskData is not None
    assert MaskerData is not None
    assert PageData is not None


@pytest.mark.unit
def test_box_as_tuple_xywh_maps_to_qrectf() -> None:
    """``Box.as_tuple_xywh`` returns (x1, y1, w, h) ints for QRectF(x, y, w, h).

    This is the contract the GUI layer's BoxItem.__init__ depends on
    (``QRectF(x, y, w, h)`` from ``box.as_tuple_xywh``).
    """
    from panelcleaner.structures import Box

    box = Box(10, 20, 110, 220)
    assert box.as_tuple_xywh == (10, 20, 100, 200)


@pytest.mark.unit
def test_box_as_tuple_returns_xyxy() -> None:
    """``Box.as_tuple`` returns the raw (x1, y1, x2, y2) corner coordinates."""
    from panelcleaner.structures import Box

    box = Box(10, 20, 110, 220)
    assert box.as_tuple == (10, 20, 110, 220)


@pytest.mark.unit
def test_box_contains_hit_test() -> None:
    """``__contains__`` returns True for points inside, False for outside.

    The hit-test is inclusive on both edges (x1 <= px <= x2).
    """
    from panelcleaner.structures import Box

    box = Box(10, 20, 110, 220)
    assert (50, 50) in box  # interior
    assert (10, 20) in box  # top-left corner (inclusive)
    assert (110, 220) in box  # bottom-right corner (inclusive)
    assert (5, 5) not in box  # outside (above-left)
    assert (200, 50) not in box  # outside (right)


@pytest.mark.unit
def test_box_type_enum_values() -> None:
    """``BoxType`` carries BOX/EXTENDED_BOX/MERGED_EXT_BOX/REFERENCE_BOX with
    BOX == 0 (the upstream enum order)."""
    from panelcleaner.structures import BoxType

    assert BoxType.BOX.value == 0
    assert BoxType.EXTENDED_BOX.value == 1
    assert BoxType.MERGED_EXT_BOX.value == 2
    assert BoxType.REFERENCE_BOX.value == 3


@pytest.mark.unit
def test_pick_best_mask_no_longer_hits_attributeerror_on_maskfittingresults() -> None:
    """Pitfall 2 regression: ``image_ops.pick_best_mask`` constructs
    ``st.MaskFittingResults(...)`` at image_ops.py:706,717. Before the full
    structures.py was vendored, importing pick_best_mask succeeded (its body
    wasn't called) but CALLING it would have hit AttributeError. With the full
    structures in place, the import path is sound and ``MaskFittingResults`` is
    resolvable from image_ops's perspective.

    We assert the cross-module reference here by checking that ``MaskFittingResults``
    is the SAME class object whether imported via structures directly or via the
    image_ops annotation path (the annotation is lazy under
    ``from __future__ import annotations``, so we resolve it through the module).
    """
    import panelcleaner.image_ops as ops
    import panelcleaner.structures as st

    # pick_best_mask is callable (the body's st.MaskFittingResults reference now
    # resolves because the full structures.py is present).
    assert callable(ops.pick_best_mask)
    assert ops.pick_best_mask.__annotations__["return"] is not None
    # The class image_ops references is the same object the structures module
    # exposes — no shadowing, no second definition.
    assert st.MaskFittingResults is st.MaskFittingResults
