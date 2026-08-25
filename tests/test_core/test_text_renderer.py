"""Renderer tests for the quick-260824-viq SFX features — rotation, character
spacing, and line spacing through the SHARED renderer (D-01: one code path
for the canvas overlay AND the bake).

These tests pin:

- ``layout()`` stores ``box_center == box_rect.center()`` on EVERY
  LayoutResult (empty-text, horizontal, vertical) — the pivot paint() rotates
  about (the rotation must be identical on canvas and bake).
- ``paint()`` rotates glyphs about ``box_center`` when ``rotation_deg != 0``
  (Qt positive = clockwise; the style field documents degrees clockwise).
- Letter spacing rides ``_style_font`` so measurement (``_break_lines_for``)
  and rendering (``_build_document``) share ONE font construction.
- Line spacing applies a top margin per document block after the first, so
  the overflow check + auto-fit account for it with zero extra logic.
- Vertical placements: column pitch grows by ``char_spacing_px``; the
  per-char y advance grows by ``line_spacing_px``.
- ``bake_typeset_page()`` composites rotated ink OUTSIDE the axis-aligned
  box rect (export honors rotation — D-01 canvas ≡ bake).

Qt-required (QPainter/QTextDocument) — runs under the pytest-qt ``qapp``
fixture like the other renderer suites.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QTextDocument  # noqa: E402

pytest.importorskip("pytestqt")  # qapp fixture

from manga_ai_studio.core.box_model import PageBox  # noqa: E402
from manga_ai_studio.core.text_style import TextStyle  # noqa: E402
from panelcleaner.structures import Box  # noqa: E402

from manga_ai_studio.gui.text_renderer import (  # noqa: E402
    _build_document,
    _style_font,
    _vertical_placements,
    bake_typeset_page,
    layout,
    paint,
)

_TEXT = "HELLO WORLD TYPESetting probe"


# ---------------------------------------------------------------------------
# box_center on every LayoutResult
# ---------------------------------------------------------------------------


def test_layout_stores_box_center_horizontal(qapp) -> None:
    """The horizontal path's LayoutResult.box_center == box_rect.center()."""
    rect = QRectF(50.0, 30.0, 200.0, 80.0)
    result = layout(_TEXT, TextStyle(auto_fit=False, font_size_px=12.0), rect)
    assert result.box_center == rect.center()


def test_layout_stores_box_center_vertical(qapp) -> None:
    """The vertical (tategaki) path also carries box_center."""
    rect = QRectF(10.0, 10.0, 120.0, 240.0)
    result = layout(
        "縦書きテキスト", TextStyle(vertical=True), rect, vertical=True
    )
    assert result.box_center == rect.center()


def test_layout_stores_box_center_empty_text(qapp) -> None:
    """Even the empty-text early return carries box_center."""
    rect = QRectF(5.0, 7.0, 90.0, 40.0)
    result = layout("", TextStyle(), rect)
    assert result.box_center == rect.center()


# ---------------------------------------------------------------------------
# paint() rotation about box_center
# ---------------------------------------------------------------------------


def _render_result(result, style, size=(300, 300)) -> np.ndarray:
    """Rasterize a LayoutResult onto a fresh ARGB surface; return the alpha."""
    img = QImage(size[0], size[1], QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    try:
        paint(painter, result, style)
    finally:
        painter.end()
    arr = np.frombuffer(bytes(img.bits()), dtype=np.uint8).reshape(
        img.height(), img.width(), 4
    )
    return arr[..., 3].copy()  # alpha channel = glyph ink


def test_paint_rotation_changes_pixels_and_swaps_bbox_at_90(qapp) -> None:
    """Rotating the SAME LayoutResult by 90 deg draws DIFFERENT pixels whose
    ink bbox is the unrotated bbox swapped (w<->h, +-4px tolerance)."""
    from PySide6.QtCore import Qt

    # Box centered in the 300x300 surface (center 150,150) so neither the
    # unrotated nor the rotated ink clips at a surface edge.
    rect = QRectF(30.0, 120.0, 240.0, 60.0)
    style = TextStyle(auto_fit=False, font_size_px=16.0)
    result = layout("ROTATION PROBE", style, rect)

    alpha0 = _render_result(result, style)
    assert (alpha0 > 0).any()

    style_rot = TextStyle(auto_fit=False, font_size_px=16.0, rotation_deg=90.0)
    alpha90 = _render_result(result, style_rot)

    # Different pixels (the glyphs moved).
    assert not np.array_equal(alpha0, alpha90)

    ys0, xs0 = np.nonzero(alpha0 > 8)
    ys90, xs90 = np.nonzero(alpha90 > 8)
    assert len(xs90) > 0
    w0 = xs0.max() - xs0.min()
    h0 = ys0.max() - ys0.min()
    w90 = xs90.max() - xs90.min()
    h90 = ys90.max() - ys90.min()
    # A 90-deg rotation about the center swaps the extents.
    assert abs(w90 - h0) <= 4, (w0, h0, w90, h90)
    assert abs(h90 - w0) <= 4, (w0, h0, w90, h90)


def test_normalize_rotation_into_half_open_range(qapp) -> None:
    """paint() normalizes the angle into (-180, 180] before applying it —
    360/0 render identically, 270 == -90."""
    from manga_ai_studio.gui.text_renderer import _normalize_rotation

    assert _normalize_rotation(0.0) == 0.0
    assert _normalize_rotation(45.0) == 45.0
    assert _normalize_rotation(-180.0) == 180.0  # (-180, 180]
    assert _normalize_rotation(180.0) == 180.0
    assert _normalize_rotation(270.0) == -90.0
    assert _normalize_rotation(360.0) == 0.0
    assert _normalize_rotation(float("nan")) == 0.0
    assert _normalize_rotation(float("inf")) == 0.0


# ---------------------------------------------------------------------------
# Letter spacing — measurement == render via _style_font
# ---------------------------------------------------------------------------


def test_letter_spacing_grows_font_metrics_monotonically(qapp) -> None:
    """"_style_font applies AbsoluteSpacing so the SAME metric call the line
    breaker uses grows monotonically with char_spacing_px."""
    probe = "hello world typeset"
    fm0 = QFontMetricsF(_style_font(TextStyle(char_spacing_px=0.0), 20))
    fm8 = QFontMetricsF(_style_font(TextStyle(char_spacing_px=8.0), 20))
    a0 = fm0.horizontalAdvance(probe)
    a8 = fm8.horizontalAdvance(probe)
    assert a8 > a0
    # Monotonicity across a second step (16 > 8).
    fm16 = QFontMetricsF(_style_font(TextStyle(char_spacing_px=16.0), 20))
    assert fm16.horizontalAdvance(probe) > a8


def test_letter_spacing_grows_document_width(qapp) -> None:
    """_build_document width reflects the char spacing (render shares the
    measurement font — no divergence window)."""
    doc0 = _build_document("hello world", TextStyle(char_spacing_px=0.0), 20, 400.0)
    doc8 = _build_document("hello world", TextStyle(char_spacing_px=8.0), 20, 800.0)
    assert doc8.size().width() > doc0.size().width()


# ---------------------------------------------------------------------------
# Line spacing — block top margin
# ---------------------------------------------------------------------------


def test_line_spacing_grows_height_per_extra_line(qapp) -> None:
    """line_spacing_px=20 exceeds the 0-spacing height by ~20 px PER EXTRA
    LINE (3 lines -> 2 gaps -> ~+40 px, tolerance +-4 px for rounding)."""
    text = "first line\nsecond line\nthird line"
    doc0 = _build_document(text, TextStyle(line_spacing_px=0.0), 14, 500.0)
    doc20 = _build_document(text, TextStyle(line_spacing_px=20.0), 14, 500.0)
    delta = doc20.size().height() - doc0.size().height()
    assert abs(delta - 40.0) <= 4.0, delta


def test_line_spacing_flows_through_layout_overflow_and_geometry(qapp) -> None:
    """layout() with line spacing produces a taller document than without
    (the auto-fit / overflow checks consume doc height unchanged)."""
    rect = QRectF(0.0, 0.0, 200.0, 200.0)
    r0 = layout("alpha\nbeta\ngamma\ndelta", TextStyle(auto_fit=False, font_size_px=12.0), rect)
    r20 = layout(
        "alpha\nbeta\ngamma\ndelta",
        TextStyle(auto_fit=False, font_size_px=12.0, line_spacing_px=20.0),
        rect,
    )
    h0 = r0.document.size().height()
    h20 = r20.document.size().height()
    assert h20 > h0


# ---------------------------------------------------------------------------
# Vertical placements — column pitch + per-char advance
# ---------------------------------------------------------------------------


def test_vertical_column_pitch_grows_with_char_spacing(qapp) -> None:
    """Adjacent-column pitch grows by exactly char_spacing_px (gap between
    columns), keeping gap 0 byte-identical legacy geometry at 0."""
    text = "あ" * 12  # wraps into several columns at inner_h=100
    _, ncols0, bw0, _ = _vertical_placements(text, TextStyle(), 200.0, 100.0, 20.0)
    assert ncols0 >= 3  # the probe must actually wrap
    _, ncols1, bw1, _ = _vertical_placements(
        text, TextStyle(char_spacing_px=8.0), 200.0, 100.0, 20.0
    )
    assert ncols1 == ncols0  # spacing alone must not change wrapping here
    expected_extra = 8.0 * (ncols0 - 1)
    assert abs((bw1 - bw0) - expected_extra) <= 1e-6


def test_vertical_char_advance_grows_with_line_spacing(qapp) -> None:
    """Per-char y advance inside a column grows by line_spacing_px; wrap
    predicate accounts for it (fewer chars fit per column)."""
    text = "あ" * 10
    p0, n0, _, bh0 = _vertical_placements(text, TextStyle(), 200.0, 100.0, 20.0)
    p10, n10, _, _bh10 = _vertical_placements(
        text, TextStyle(line_spacing_px=10.0), 200.0, 100.0, 20.0
    )
    # First two chars of column 0: y-gap grew by 10.
    d0 = p0[1]["y"] - p0[0]["y"]
    d10 = p10[1]["y"] - p10[0]["y"]
    assert abs((d10 - d0) - 10.0) <= 1e-6
    # The tighter advance wraps sooner (more columns).
    assert n10 >= n0


# ---------------------------------------------------------------------------
# Bake honors rotation (export parity — D-01)
# ---------------------------------------------------------------------------


def test_bake_rotated_box_paints_outside_axis_aligned_rect(qapp) -> None:
    """A rotated styled box bakes ink OUTSIDE its axis-aligned rect but inside
    the rotated quad region (within the padded half-diagonal of the center)."""
    page = np.full((220, 260, 3), 255, dtype=np.uint8)
    pb = PageBox(
        box=Box(80, 70, 250, 130),  # axis-aligned rect x:80..250 y:70..130
        origin="user",
        payload=None,
        style=TextStyle(auto_fit=False, font_size_px=18.0, rotation_deg=45.0),
    )
    pb.set_translation("ROTATED BAKE PROBE")
    out = bake_typeset_page(page, [pb])
    changed = np.any(out != page, axis=2)
    assert changed.any()
    # Ink outside the axis-aligned rect exists (rotation pushed glyphs out).
    outside = changed.copy()
    outside[70:130, 80:250] = False
    assert outside.any(), "rotated bake left no ink outside the axis-aligned rect"
    # And all changed pixels stay within the padded rotated reach of the
    # box center (half-diagonal of the rect + a generous glyph pad).
    cx, cy = 165.0, 100.0
    reach = math.hypot(85.0, 30.0) + 60.0
    ys, xs = np.nonzero(changed)
    dist = np.hypot(xs - cx, ys - cy)
    assert dist.max() <= reach
