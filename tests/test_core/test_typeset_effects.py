"""Effects pixel tests (plan 07-03 Task 2, D-14) — outline, outer glow, and
drop shadow rendered through ``gui/text_renderer.paint``.

The renderer is the ONE shared draw path for the canvas overlay AND the bake
(D-01), so these QImage pixel assertions lock the LOOK both surfaces will
produce: an outline ring around the glyphs, a soft glow halo BEHIND them,
a drop shadow at the style's offset, the effect padding that keeps halos
from being clipped, and the BOUNDED effect allocation that degrades to
no-glow instead of OOMing (T-07-07).

Pixels are asserted with color-distance tolerance (antialiasing blurs the
exact ink edges) — never exact equality at edges.

Mechanism note: the plan's Task-2 letter prescribes ``QPainterPath.addText``
+ ``strokePath`` for the outline; that API crashes the pinned Python 3.14.2
/ PySide6 6.10.1 stack (fast-fail 0xC0000409 — the exact 07-01 deviation),
so the outline rides the proven ``QTextCharFormat.setTextOutline`` path
(horizontal: the layout document; vertical: per-char documents) — same
LOOK, locked by the pixel assertions below.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from loguru import logger as _loguru_logger

pytest.importorskip("PySide6")

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402

from manga_ai_studio.core.text_style import TextStyle  # noqa: E402
from manga_ai_studio.gui.text_renderer import (  # noqa: E402
    effect_padding,
    layout,
    paint,
    qimage_to_numpy,
)

_FILL = (232, 232, 234)  # #e8e8ea — the default opaque fill
_OUTLINE = (11, 11, 14)  # #0b0b0e — the default outline
_WHITE = (255, 255, 255)


def _render(text: str, style: TextStyle, rect: QRectF, vertical: bool = False) -> np.ndarray:
    """Render ``text`` with ``style`` into a white (H, W, 3) RGB array."""
    return _render_result(layout(text, style, rect, vertical=vertical), rect)


def _render_result(result, rect: QRectF) -> np.ndarray:
    """Render a laid-out result into a white (H, W, 3) RGB array."""
    img = QImage(int(rect.width()), int(rect.height()), QImage.Format.Format_RGB32)
    img.fill(Qt.GlobalColor.white)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    paint(painter, result, result.style)
    painter.end()
    return qimage_to_numpy(img)


def _near(arr: np.ndarray, rgb: tuple, tol: float) -> np.ndarray:
    """A bool mask of pixels within ``tol`` (Euclidean color distance) of ``rgb``."""
    d = np.sqrt(np.sum((arr.astype(np.float64) - np.array(rgb)) ** 2, axis=-1))
    return d <= tol


def _count(arr: np.ndarray, rgb: tuple, tol: float) -> int:
    return int(np.count_nonzero(_near(arr, rgb, tol)))


def _region(arr: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> np.ndarray:
    """Clamped rectangular sub-array (x0 <= x < x1, y0 <= y < y1)."""
    h, w = arr.shape[:2]
    x0, x1 = max(0, x0), min(w, x1)
    y0, y1 = max(0, y0), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        return arr[0:0, 0:0]
    return arr[y0:y1, x0:x1]


def _fill_bbox(arr: np.ndarray, tol: float = 40.0) -> tuple[int, int, int, int]:
    """The (x0, y0, x1, y1) bbox of fill-colored pixels (exclusive x1/y1)."""
    mask = _near(arr, _FILL, tol)
    ys, xs = np.nonzero(mask)
    assert len(xs) > 0, "no fill pixels found — the glyph did not render"
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


_red = lambda arr: (arr[..., 0].astype(int) > 150)  # noqa: E731
_red_mask = lambda arr: _red(arr) & (arr[..., 0].astype(int) - arr[..., 1].astype(int) > 60) & (  # noqa: E731
    arr[..., 0].astype(int) - arr[..., 2].astype(int) > 60
)
_black_mask = lambda arr: (  # noqa: E731
    (arr[..., 0] < 40) & (arr[..., 1] < 40) & (arr[..., 2] < 40)
)


def _count_mask(arr: np.ndarray, mask: np.ndarray) -> int:
    h, w = arr.shape[:2]
    return int(np.count_nonzero(mask[:h, :w]))


# ---------------------------------------------------------------------------
# Test 1 — outline ring, horizontal
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_effects_outline_ring_horizontal(qapp) -> None:
    """Outline width 2: fill-colored pixels INSIDE the glyph, outline-colored
    pixels in a ring AROUND it; width 0 renders no outline-colored pixels."""
    rect = QRectF(0, 0, 120, 60)
    style = TextStyle(font_size_px=24.0, auto_fit=False)
    img_ring = _render("A", style, rect)  # outline defaults ON at 2 px
    img_plain = _render(
        "A", replace(style, outline={**style.outline, "enabled": False}), rect
    )

    # Fill pixels exist inside the glyph in BOTH renders.
    assert _count(img_ring, _FILL, 40) > 20, "fill pixels must exist inside the glyph"
    assert _count(img_plain, _FILL, 40) > 20
    # Ring present at width 2, absent at width 0.
    ring_px = _count(img_ring, _OUTLINE, 60)
    assert ring_px > 20, "an outlined glyph must show outline-colored pixels"
    assert _count(img_plain, _OUTLINE, 60) == 0, "width 0 must render NO outline pixels"

    # The ring SURROUNDS the glyph: outline pixels exist above/below/left/right
    # of the fill bbox (a ring, not a blob).
    x0, y0, x1, y1 = _fill_bbox(img_plain)
    assert (
        _count(_region(img_ring, x0, y0 - 4, x1, y0 - 1), _OUTLINE, 60) > 0
    ), "outline ring must appear ABOVE the glyph"
    assert (
        _count(_region(img_ring, x0, y1 + 1, x1, y1 + 4), _OUTLINE, 60) > 0
    ), "outline ring must appear BELOW the glyph"
    assert (
        _count(_region(img_ring, x0 - 4, y0, x0 - 1, y1), _OUTLINE, 60) > 0
    ), "outline ring must appear LEFT of the glyph"
    assert (
        _count(_region(img_ring, x1 + 1, y0, x1 + 4, y1), _OUTLINE, 60) > 0
    ), "outline ring must appear RIGHT of the glyph"


# ---------------------------------------------------------------------------
# Test 2 — glow halo
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_effects_glow_halo(qapp) -> None:
    """Glow on (radius 6): glow-colored pixels exist OUTSIDE the glyph's ink
    bbox within the radius band; the fill keeps its color; glow off -> none."""
    rect = QRectF(0, 0, 120, 60)
    glow = {"enabled": True, "color": "#ff0000", "radius_px": 6.0, "opacity": 1.0}
    style = TextStyle(
        font_size_px=24.0,
        auto_fit=False,
        outline={"enabled": False, "color": "#0b0b0e", "width_px": 0.0},
        glow=glow,
    )
    img_glow = _render("A", style, rect)
    img_plain = _render("A", replace(style, glow={**glow, "enabled": False}), rect)

    x0, y0, x1, y1 = _fill_bbox(img_plain)
    band = _region(img_glow, x0 - 9, y0 - 9, x1 + 9, y1 + 9)
    inner = _region(img_glow, x0 + 2, y0 + 2, x1 - 2, y1 - 2)
    # The halo sits OUTSIDE the ink bbox (band minus the glyph's own region).
    band_px = _count_mask(band, _red_mask(band))
    inner_px = _count_mask(inner, _red_mask(inner))
    assert band_px > 0, "glow pixels must exist outside the ink bbox (the radius band)"
    assert inner_px == 0, "the glyph's own region must not be glow-red"
    # Fill pixels keep the fill color (the fill composites over the halo).
    assert _count(img_glow, _FILL, 40) > 20
    # Glow OFF: no glow-colored pixels outside the ink bbox at all.
    band_plain = _region(img_plain, x0 - 9, y0 - 9, x1 + 9, y1 + 9)
    assert _count_mask(band_plain, _red_mask(band_plain)) == 0, (
        "glow off must render NO pixels outside the ink bbox"
    )


# ---------------------------------------------------------------------------
# Test 3 — shadow offset
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_effects_shadow_offset(qapp) -> None:
    """Shadow on (offset 4,4 > radius 0): silhouette pixels appear at the
    glyph position + (4,4); NO silhouette pixels at the un-offset position
    (the offset exceeds the radius, so the shadow never blurs back)."""
    rect = QRectF(0, 0, 120, 60)
    shadow = {
        "enabled": True,
        "color": "#000000",
        "radius_px": 0.0,
        "dx": 4.0,
        "dy": 4.0,
        "opacity": 1.0,
    }
    style = TextStyle(
        font_size_px=24.0,
        auto_fit=False,
        outline={"enabled": False, "color": "#0b0b0e", "width_px": 0.0},
        shadow=shadow,
    )
    # "I" is a thin glyph: an offset of 4 px fully clears the ink column, so
    # the un-offset position contains no shadow pixels (offset > radius).
    img = _render("I", style, rect)
    x0, y0, x1, y1 = _fill_bbox(img)

    shifted = _region(img, x0 + 4, y0 + 4, x1 + 4, y1 + 4)
    assert _count_mask(shifted, _black_mask(shifted)) > 20, (
        "silhouette pixels must appear at the glyph position + (dx, dy)"
    )
    unshifted = _region(img, x0, y0, x1, y1)
    assert _count_mask(unshifted, _black_mask(unshifted)) == 0, (
        "with offset > radius, no silhouette pixels at the un-offset position"
    )
    # The glyph itself still renders its fill.
    assert _count(img, _FILL, 40) > 10


# ---------------------------------------------------------------------------
# Test 4 — effect padding
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_effects_padding(qapp) -> None:
    """effect_padding(style) = outline half-width + max(glow radius, shadow
    radius) + |max offset|; the paint output extends beyond the glyph bbox
    by roughly the padding margin (halos are not clipped)."""
    style = TextStyle(
        font_size_px=24.0,
        auto_fit=False,
        outline={"enabled": True, "color": "#0b0b0e", "width_px": 2.0},
        glow={"enabled": True, "color": "#ff0000", "radius_px": 6.0, "opacity": 1.0},
        shadow={
            "enabled": True,
            "color": "#000000",
            "radius_px": 4.0,
            "dx": 2.0,
            "dy": 2.0,
            "opacity": 1.0,
        },
    )
    assert effect_padding(style) == pytest.approx(1.0 + 6.0 + 2.0), (
        "padding = outline half-width (1) + max radius (6) + |max offset| (2)"
    )
    # The paint output extends beyond the glyph bbox: red glow pixels exist
    # at roughly the radius distance from the ink (4..8 px band).
    rect = QRectF(0, 0, 120, 60)
    img = _render("A", style, rect)
    x0, y0, x1, y1 = _fill_bbox(img)
    band = _region(img, x0 - 9, y0 - 9, x1 + 9, y1 + 9)
    outer = _region(img, x0 - 9, y0 - 9, x1 + 9, y1 + 9)
    far = _region(img, x0 + 4, y0 + 4, x1 - 4, y1 - 4)
    assert _count_mask(band, _red_mask(band)) > 0
    assert _count_mask(outer, _red_mask(outer)) > 0
    assert _count_mask(far, _red_mask(far)) == 0


# ---------------------------------------------------------------------------
# Test 5 — bounded allocation degrade (T-07-07)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_effects_allocation_bounded_degrade(qapp) -> None:
    """A pathological glow radius on a full-page rect degrades to NO glow:
    the paint succeeds, a loguru warning is emitted, and the fill still
    renders — never an exception or an OOM."""
    glow = {"enabled": True, "color": "#ff0000", "radius_px": 500.0, "opacity": 1.0}
    style = TextStyle(
        font_size_px=200.0,
        auto_fit=False,
        align_h="left",
        align_v="top",
        outline={"enabled": False, "color": "#0b0b0e", "width_px": 0.0},
        glow=glow,
    )
    rect = QRectF(0, 0, 4000, 3000)  # the ink spans the full width -> 5000+ px surface

    sink: list = []
    sink_id = _loguru_logger.add(sink.append)
    try:
        img = _render("A" * 200, style, rect)  # must NOT raise
    finally:
        _loguru_logger.remove(sink_id)

    # Degrade: no glow pixels anywhere, but the glyph fill still renders.
    assert _count_mask(img, _red_mask(img)) == 0, (
        "an oversized effect surface must degrade to NO glow"
    )
    assert _count(img, _FILL, 40) > 100, "the fill must still render"
    assert any("skipped" in str(rec["message"]).lower() for rec in sink), (
        "the degrade path must emit a loguru warning"
    )


# ---------------------------------------------------------------------------
# Test 6 — vertical composition (one pass path serves both orientations)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_effects_vertical_composition(qapp) -> None:
    """A vertical layout with a rotated Latin run renders the outline around
    the glyphs AND the shadow at +dx/+dy — the same passes serve both
    orientations (D-01, one shared code path)."""
    shadow = {
        "enabled": True,
        "color": "#ff0000",
        "radius_px": 2.0,
        "dx": 3.0,
        "dy": 3.0,
        "opacity": 1.0,
    }
    style = TextStyle(
        font_size_px=24.0,
        auto_fit=False,
        align_h="center",
        align_v="middle",
        vertical=True,
        shadow=shadow,
        # outline defaults ON at 2 px #0b0b0e
    )
    rect = QRectF(0, 0, 160, 100)
    img = _render("あA", style, rect, vertical=True)

    # The vertical per-char pass draws the outline (dark) + fill + shadow.
    assert _count(img, _OUTLINE, 60) > 10, (
        "the vertical path must render the outline around the glyphs"
    )
    assert _count_mask(img, _red_mask(img)) > 0, (
        "the vertical path must render the shadow at +dx/+dy"
    )
    assert _count(img, _FILL, 40) > 20, "the vertical fill must render"
