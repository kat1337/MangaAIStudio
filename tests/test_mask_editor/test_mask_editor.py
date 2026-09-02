"""Unit tests for the pure mask-mutation ops (core/mask_editor.py).

These exercise paint behavior WITHOUT instantiating any QWidget (RESEARCH
Validation Architecture — D-10: core/ holds pure ops, testable headless). Only
QImage objects are constructed via the qtbot fixture's QApplication. Marked
``@pytest.mark.unit`` (no torch, no display beyond the offscreen Qt init).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

import numpy as np  # noqa: E402
from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainterPath  # noqa: E402

from manga_ai_studio.core.mask_editor import (  # noqa: E402
    DEFAULT_BRUSH_SIZE,
    MAX_BRUSH_SIZE,
    MASK_PAINT_COLOR,
    MIN_BRUSH_SIZE,
    ToolMode,
    clamp_brush_size,
    clear_mask,
    mask_to_numpy_binary,
    numpy_binary_to_mask_qimage,
    paint_mask_lasso,
    paint_mask_rect,
    paint_mask_stroke,
)


def _transparent_mask(size: int = 100) -> QImage:
    """Build a transparent ARGB32 QImage for painting tests."""
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    return img


# ---------------------------------------------------------------------------
# ToolMode + constants
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_tool_mode_has_eight_members() -> None:
    """ToolMode exposes MOVE/BRUSH/RECTANGLE/LASSO/ERASER/RESTORE/CROP/
    OCR_GRAB.

    Crop is the 6th tool (D-11, plan 05-07); Restore is the 7th
    (quick-260828-l3l); OCR Grab is the 8th (quick-260901-wmn) — the
    Phase 3 "no 6th tool" stance is superseded by D-11.
    """
    names = {m.name for m in ToolMode}
    assert names == {
        "MOVE",
        "BRUSH",
        "RECTANGLE",
        "LASSO",
        "ERASER",
        "RESTORE",
        "CROP",
        "OCR_GRAB",
    }


@pytest.mark.unit
def test_mask_paint_color_is_red_63_percent_alpha() -> None:
    """MASK_PAINT_COLOR is the rgba(255,0,0,0.63) overlay (160/255 ~= 0.63)."""
    assert MASK_PAINT_COLOR.red() == 255
    assert MASK_PAINT_COLOR.green() == 0
    assert MASK_PAINT_COLOR.blue() == 0
    assert MASK_PAINT_COLOR.alpha() == 160


@pytest.mark.unit
def test_brush_size_constants_match_ui_spec() -> None:
    """MIN=1, MAX=300, DEFAULT=40 (UI-SPEC surface 6)."""
    assert MIN_BRUSH_SIZE == 1
    assert MAX_BRUSH_SIZE == 300
    assert DEFAULT_BRUSH_SIZE == 40


# ---------------------------------------------------------------------------
# clamp_brush_size (Test 8)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_clamp_brush_size() -> None:
    """clamp_brush_size clamps to [1, 300] and passes in-range values through."""
    assert clamp_brush_size(0) == 1
    assert clamp_brush_size(301) == 300
    assert clamp_brush_size(40) == 40
    assert clamp_brush_size(1) == 1
    assert clamp_brush_size(300) == 300
    # Coerces non-int to int first.
    assert clamp_brush_size(40.7) == 40


# ---------------------------------------------------------------------------
# Test 1 + 2: brush stroke
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_brush_paint_draws_red_stroke() -> None:
    """A horizontal stroke leaves an opaque-red band crossing the start row."""
    img = _transparent_mask(100)
    paint_mask_stroke(img, QPointF(10, 10), QPointF(90, 10), brush_size=10, eraser=False)
    # The stroke runs along row 10; a pixel on that row should be painted.
    px = img.pixelColor(50, 10)
    assert px.alpha() > 0
    assert px.red() > 0
    # A pixel well outside the stroke stays transparent.
    assert img.pixelColor(50, 80).alpha() == 0


@pytest.mark.unit
def test_brush_paint_uses_round_cap() -> None:
    """RoundCap fills the cap discs at both endpoints."""
    img = _transparent_mask(100)
    paint_mask_stroke(img, QPointF(10, 10), QPointF(90, 10), brush_size=10, eraser=False)
    # The cap disc at each endpoint paints the endpoint pixel itself.
    assert img.pixelColor(10, 10).alpha() > 0
    assert img.pixelColor(90, 10).alpha() > 0


@pytest.mark.unit
def test_brush_stroke_paint_color_is_red() -> None:
    """The painted pixel matches MASK_PAINT_COLOR (red, alpha 160)."""
    img = _transparent_mask(100)
    paint_mask_stroke(img, QPointF(10, 10), QPointF(90, 10), brush_size=10, eraser=False)
    px = img.pixelColor(50, 10)
    assert px.red() == 255
    assert px.alpha() == 160


@pytest.mark.unit
def test_brush_stroke_clamps_oversized_brush_size() -> None:
    """An oversized brush_size is clamped to MAX (no exception, no overflow)."""
    img = _transparent_mask(100)
    paint_mask_stroke(img, QPointF(40, 50), QPointF(60, 50), brush_size=9999, eraser=False)
    # The clamped stroke (width 300) covers the center pixel.
    assert img.pixelColor(50, 50).alpha() > 0


# ---------------------------------------------------------------------------
# Test 3: rectangle fill
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_rect_fill() -> None:
    """paint_mask_rect fills the normalized rectangle with red."""
    img = _transparent_mask(100)
    paint_mask_rect(img, QPointF(20, 20), QPointF(80, 80), eraser=False)
    # Interior pixel painted.
    interior = img.pixelColor(50, 50)
    assert interior.alpha() > 0
    assert interior.red() == 255
    # Exterior pixel not painted.
    assert img.pixelColor(10, 10).alpha() == 0


@pytest.mark.unit
def test_rect_fill_normalizes_drag_direction() -> None:
    """Dragging bottom-right to top-left still fills the same rectangle."""
    img = _transparent_mask(100)
    paint_mask_rect(img, QPointF(80, 80), QPointF(20, 20), eraser=False)
    assert img.pixelColor(50, 50).alpha() > 0
    assert img.pixelColor(10, 10).alpha() == 0


# ---------------------------------------------------------------------------
# Test 4: lasso fill
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_lasso_fill() -> None:
    """paint_mask_lasso closes + fills a triangle path interior."""
    img = _transparent_mask(100)
    path = QPainterPath()
    path.moveTo(50, 10)
    path.lineTo(90, 90)
    path.lineTo(10, 90)
    path.closeSubpath()
    paint_mask_lasso(img, path, eraser=False)
    # An interior pixel of the triangle (near the centroid) is painted.
    interior = img.pixelColor(50, 65)
    assert interior.alpha() > 0
    # An exterior pixel (top-left corner, outside the triangle) is not.
    assert img.pixelColor(5, 5).alpha() == 0


# ---------------------------------------------------------------------------
# Test 5: eraser (CompositionMode_Clear)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_eraser_clears() -> None:
    """Stroking with eraser=True clears the stroked region to alpha 0."""
    img = _transparent_mask(100)
    # Pre-paint a horizontal red band.
    paint_mask_stroke(img, QPointF(10, 50), QPointF(90, 50), brush_size=20, eraser=False)
    assert img.pixelColor(50, 50).alpha() > 0
    # Erase over the same region.
    paint_mask_stroke(img, QPointF(10, 50), QPointF(90, 50), brush_size=20, eraser=True)
    assert img.pixelColor(50, 50).alpha() == 0


@pytest.mark.unit
def test_eraser_clears_rect_region() -> None:
    """paint_mask_rect with eraser=True clears the rectangle."""
    img = _transparent_mask(100)
    paint_mask_rect(img, QPointF(10, 10), QPointF(90, 90), eraser=False)
    assert img.pixelColor(50, 50).alpha() > 0
    paint_mask_rect(img, QPointF(30, 30), QPointF(70, 70), eraser=True)
    assert img.pixelColor(50, 50).alpha() == 0
    # The ring outside the erase rect stays painted.
    assert img.pixelColor(15, 15).alpha() > 0


@pytest.mark.unit
def test_clear_mask_resets_to_transparent() -> None:
    """clear_mask resets the whole mask to alpha 0."""
    img = _transparent_mask(100)
    paint_mask_rect(img, QPointF(10, 10), QPointF(90, 90), eraser=False)
    assert img.pixelColor(50, 50).alpha() > 0
    clear_mask(img)
    assert img.pixelColor(50, 50).alpha() == 0


# ---------------------------------------------------------------------------
# Test 6 + 7: QImage <-> numpy round-trip + buffer-lifetime guard
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_mask_to_numpy_binary_round_trip() -> None:
    """mask_to_numpy_binary -> numpy_binary_to_mask_qimage round-trips paint."""
    img = _transparent_mask(100)
    paint_mask_rect(img, QPointF(20, 20), QPointF(80, 80), eraser=False)
    binary = mask_to_numpy_binary(img)
    assert binary.shape == (100, 100)
    assert binary.dtype == np.uint8
    # Painted interior is 255; exterior is 0.
    assert binary[50, 50] == 255
    assert binary[5, 5] == 0

    rebuilt = numpy_binary_to_mask_qimage(binary)
    # The rebuilt QImage paints the same region non-transparent.
    assert rebuilt.pixelColor(50, 50).alpha() > 0
    assert rebuilt.pixelColor(50, 50).red() == 255
    assert rebuilt.pixelColor(5, 5).alpha() == 0


@pytest.mark.unit
def test_numpy_extract_copies_buffer() -> None:
    """mask_to_numpy_binary returns an array that OWNS its data (Pitfall 2).

    Regression guard for RESEARCH Pitfall 2 / PATTERNS.md §Shared Pattern 5:
    the returned array must be detached from the QImage buffer so it outlives
    the QImage. ``OWNDATA`` True is the proof.
    """
    img = _transparent_mask(20)
    paint_mask_rect(img, QPointF(2, 2), QPointF(18, 18), eraser=False)
    binary = mask_to_numpy_binary(img)
    assert binary.flags["OWNDATA"] is True


@pytest.mark.unit
def test_numpy_binary_to_mask_qimage_returns_detached_qimage() -> None:
    """The returned QImage survives the numpy buffer being GC'd (Pitfall 2)."""
    import gc

    binary = np.zeros((20, 20), dtype=np.uint8)
    binary[5:15, 5:15] = 255
    rebuilt = numpy_binary_to_mask_qimage(binary)
    # Drop the source array reference and collect; the QImage must still paint.
    del binary
    gc.collect()
    assert rebuilt.pixelColor(10, 10).alpha() > 0


@pytest.mark.unit
def test_numpy_binary_to_mask_qimage_rejects_non_uint8() -> None:
    """A non-uint8 mask is rejected (input-validation guard)."""
    arr = np.zeros((10, 10), dtype=np.float32)
    with pytest.raises(AssertionError):
        numpy_binary_to_mask_qimage(arr)
