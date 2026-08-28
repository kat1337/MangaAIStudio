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

Mechanism note (quick-260827-0id): the outline is an OUTWARD ring around
the glyphs — a solid outline-color silhouette dilated by the FULL outline
width painted UNDER the pure fill, never a stroke riding the glyph edge
(the legacy ``QTextCharFormat.setTextOutline`` centered stroke put half the
band INSIDE the letterforms — an inline, not an outline, once widths grew
to SFX scale). The plan's original ``QPainterPath.addText`` +
``strokePath`` prescription still crashes the pinned Python 3.14.2 /
PySide6 6.10.1 stack (fast-fail 0xC0000409 — the exact 07-01 deviation),
so both passes ride the proven QTextDocument glyph mechanism. The
outward-ring semantics are locked by the pixel probes below.
"""

from __future__ import annotations

import math
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

_FILL = (232, 232, 234)  # #e8e8ea — PINNED probe fill (the FORMER app default)
_OUTLINE = (11, 11, 14)  # #0b0b0e — pinned outline stroke color
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


def _fill_bbox(arr: np.ndarray, tol: float = 30.0) -> tuple[int, int, int, int]:
    """The (x0, y0, x1, y1) bbox of fill-colored pixels (exclusive x1/y1).

    Tol 30 keeps the WHITE background out (its distance from the fill color
    is ~39) while the glyph's antialiased core stays inside.
    """
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
# A soft glow's alpha falls off fast beyond the ink (the blur collapses at
# the ink's outer boundary) — "glow color alpha > 0" is detected by the red
# channel clearly exceeding green/blue (any tint), not by full-strength red.
_tint_mask = lambda arr: (  # noqa: E731
    (arr[..., 0].astype(int) - arr[..., 1].astype(int) > 8)
    & (arr[..., 0].astype(int) - arr[..., 2].astype(int) > 8)
)


def _count_mask(arr: np.ndarray, mask: np.ndarray) -> int:
    h, w = arr.shape[:2]
    return int(np.count_nonzero(mask[:h, :w]))


def _eroded_mask(mask: np.ndarray, k: int) -> np.ndarray:
    """A bool mask eroded by ``k`` px on every side — pure-numpy shift-min.

    The minimum over all (2k+1)^2 shifted views of the mask (a pixel
    survives only when its whole k-neighborhood is set). Implemented with
    ``np.pad`` + windowed ANDs — NO scipy (not a project dependency).
    """
    h, w = mask.shape
    padded = np.pad(mask, k, mode="constant", constant_values=False)
    out = np.ones_like(mask)
    for dy in range(2 * k + 1):
        for dx in range(2 * k + 1):
            out &= padded[dy : dy + h, dx : dx + w]
    return out


# ---------------------------------------------------------------------------
# Test 1 — outline ring, horizontal
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_effects_outline_ring_horizontal(qapp) -> None:
    """Outline width 2: fill-colored pixels INSIDE the glyph, outline-colored
    pixels in a ring AROUND it; width 0 renders no outline-colored pixels.

    "I" is a straight bar — its ring is a clean flat band on all four sides
    (an 'A' apex is a point, too thin for a reliable above-glyph probe).
    """
    rect = QRectF(0, 0, 140, 100)
    style = TextStyle(
        font_size_px=48.0,
        auto_fit=False,
        color="#e8e8ea",  # pinned probe fill (former default)
        outline={"enabled": True, "color": "#0b0b0e", "width_px": 2.0},  # pinned ON
    )
    img_ring = _render("I", style, rect)
    img_plain = _render(
        "I", replace(style, outline={**style.outline, "enabled": False}), rect
    )

    # Fill pixels exist inside the glyph in BOTH renders.
    assert _count(img_ring, _FILL, 30) > 20, "fill pixels must exist inside the glyph"
    assert _count(img_plain, _FILL, 30) > 20
    # Ring present at width 2, absent at width 0.
    ring_px = _count(img_ring, _OUTLINE, 60)
    assert ring_px > 20, "an outlined glyph must show outline-colored pixels"
    assert _count(img_plain, _OUTLINE, 60) == 0, "width 0 must render NO outline pixels"

    # The ring SURROUNDS the glyph: outline pixels exist above/below/left/right
    # of the fill bbox (a ring, not a blob). The probe regions straddle the
    # bbox edge by the AA rim so the assertion holds against the ring's
    # blended boundary on either mechanism.
    x0, y0, x1, y1 = _fill_bbox(img_plain)
    assert (
        _count(_region(img_ring, x0, y0 - 2, x1, y0 + 1), _OUTLINE, 60) > 0
    ), "outline ring must appear ABOVE the glyph"
    assert (
        _count(_region(img_ring, x0, y1 - 1, x1, y1 + 2), _OUTLINE, 60) > 0
    ), "outline ring must appear BELOW the glyph"
    assert (
        _count(_region(img_ring, x0 - 2, y0, x0 + 1, y1), _OUTLINE, 60) > 0
    ), "outline ring must appear LEFT of the glyph"
    assert (
        _count(_region(img_ring, x1 - 1, y0, x1 + 2, y1), _OUTLINE, 60) > 0
    ), "outline ring must appear RIGHT of the glyph"


# ---------------------------------------------------------------------------
# Test 2 — glow halo
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_effects_glow_halo(qapp) -> None:
    """Glow on (radius 6): glow-colored pixels exist OUTSIDE the glyph's ink
    bbox within the radius band; the fill keeps its color; glow off -> none.

    A 64 px glyph keeps the strokes thick enough that the blurred halo stays
    strongly tinted (a physically-soft glow at small sizes is the D-14 LOOK,
    not a defect — the halo must still be detectable in the radius band).
    """
    rect = QRectF(0, 0, 200, 120)
    glow = {"enabled": True, "color": "#ff0000", "radius_px": 6.0, "opacity": 1.0}
    style = TextStyle(
        font_size_px=64.0,
        auto_fit=False,
        color="#e8e8ea",  # pinned probe fill (former default)
        outline={"enabled": False, "color": "#0b0b0e", "width_px": 0.0},
        glow=glow,
    )
    img_glow = _render("A", style, rect)
    img_plain = _render("A", replace(style, glow={**glow, "enabled": False}), rect)

    x0, y0, x1, y1 = _fill_bbox(img_plain)
    band = _region(img_glow, x0 - 9, y0 - 9, x1 + 9, y1 + 9)
    # The halo sits OUTSIDE the ink bbox (the radius band). (The glyph's
    # counter — 'A' has a hole — legitimately shows the glow through it, so
    # no "inside must be glow-free" assertion is made.)
    band_px = _count_mask(band, _tint_mask(band))
    assert band_px > 0, "glow pixels must exist outside the ink bbox (the radius band)"
    # Fill pixels keep the fill color (the fill composites over the halo).
    assert _count(img_glow, _FILL, 30) > 20
    # Glow OFF: no glow-tinted pixels outside the ink bbox at all.
    band_plain = _region(img_plain, x0 - 9, y0 - 9, x1 + 9, y1 + 9)
    assert _count_mask(band_plain, _tint_mask(band_plain)) == 0, (
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
        color="#e8e8ea",  # pinned probe fill (former default)
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
    assert _count(img, _FILL, 30) > 10


# ---------------------------------------------------------------------------
# Test 4 — effect padding
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_effects_padding(qapp) -> None:
    """effect_padding(style) = outline width + max(glow radius, shadow
    radius) + |max offset|; the paint output extends beyond the glyph bbox
    by roughly the padding margin (halos are not clipped). The outline term
    is the FULL width_px (quick-260827-0id): the ring reaches that far
    outside the ink."""
    style = TextStyle(
        font_size_px=24.0,
        auto_fit=False,
        color="#e8e8ea",  # pinned probe fill (former default)
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
    assert effect_padding(style) == pytest.approx(2.0 + 6.0 + 2.0), (
        "padding = full outline width (2) + max radius (6) + |max offset| (2)"
    )
    # The paint output extends beyond the glyph bbox by the expected margin:
    # with a glow-only style (no shadow interference), red glow pixels exist
    # in the band OUTSIDE the ink bbox (the bbox comes from a glow-off
    # render so the tinted rim cannot inflate it).
    rect = QRectF(0, 0, 200, 120)
    glow_style = TextStyle(
        font_size_px=64.0,
        auto_fit=False,
        color="#e8e8ea",  # pinned probe fill (former default)
        outline={"enabled": False, "color": "#0b0b0e", "width_px": 0.0},
        glow={"enabled": True, "color": "#ff0000", "radius_px": 6.0, "opacity": 1.0},
    )
    img = _render("A", glow_style, rect)
    plain = _render("A", replace(glow_style, glow={**glow_style.glow, "enabled": False}), rect)
    x0, y0, x1, y1 = _fill_bbox(plain)
    top = _region(img, x0 - 9, y0 - 9, x1 + 9, y0 - 1)
    bottom = _region(img, x0 - 9, y1 + 1, x1 + 9, y1 + 9)
    left = _region(img, x0 - 9, y0, x0 - 1, y1)
    right = _region(img, x1 + 1, y0, x1 + 9, y1)
    assert (
        _count_mask(top, _tint_mask(top))
        + _count_mask(bottom, _tint_mask(bottom))
        + _count_mask(left, _tint_mask(left))
        + _count_mask(right, _tint_mask(right))
    ) > 0, "the paint output must extend beyond the glyph bbox (the halo margin)"


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
        color="#e8e8ea",  # pinned probe fill (former default)
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
    assert _count(img, _FILL, 30) > 100, "the fill must still render"
    assert any("skipped" in str(rec).lower() for rec in sink), (
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
        color="#e8e8ea",  # pinned probe fill (former default)
        shadow=shadow,
        # pinned ON — no longer inherited from the (disabled) app default
        outline={"enabled": True, "color": "#0b0b0e", "width_px": 2.0},
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
    assert _count(img, _FILL, 30) > 20, "the vertical fill must render"


# ---------------------------------------------------------------------------
# Tests 7-9 — OUTWARD ring semantics (quick-260827-0id): the visible outline
# band is width_px DEEP OUTSIDE the plain-fill bbox and the glyph interior
# stays PURE fill at any width (the two-pass silhouette-under-fill contract;
# the legacy centered stroke rendered half the band INSIDE the letterforms —
# an inline, and let stacked neighbors chew each other's fill).
# ---------------------------------------------------------------------------


def _outline_probe_style() -> TextStyle:
    """The pinned W=8 probe style shared by the outward-ring tests."""
    return TextStyle(
        font_size_px=64.0,
        auto_fit=False,
        color="#e8e8ea",  # pinned probe fill
        outline={"enabled": True, "color": "#0b0b0e", "width_px": 8.0},
    )


def _assert_interior_pure(img_plain: np.ndarray, img_outlined: np.ndarray) -> None:
    """No outline-colored pixel deeper than ~2px inside the plain-fill body.

    Erodes the plain-fill mask by 3 px (covering the legacy 4 px inner-eat
    minus the 1 px AA fringe) and asserts ZERO outline-colored pixels remain
    in the strict interior — at ANY outline width.
    """
    eroded = _eroded_mask(_near(img_plain, _FILL, 30), 3)
    contamination = eroded & _near(img_outlined, _OUTLINE, 60)
    n = int(np.count_nonzero(contamination))
    assert n == 0, (
        "outline color must never sit deeper than the AA rim inside the "
        f"glyph interior ({n} contaminated px)"
    )


@pytest.mark.unit
def test_outline_ring_extends_outward_horizontal(qapp) -> None:
    """Width-8 outline: the [ceil(0.6*W)+1 .. floor(0.9*W)] band past each
    cardinal side of the plain-fill bbox holds outline-colored pixels.

    The band is the discriminator: the legacy centered stroke reached only
    ~W/2 = 4 px out (+ <=1 px AA), so the 6..7 px band was EMPTY; the
    outward ring reaches the full W = 8 px, so the band fills in. Offsets
    derive from W = float(outline["width_px"]) — 6..7 is the W=8 instance.
    """
    rect = QRectF(0, 0, 200, 140)
    style = _outline_probe_style()
    img_outlined = _render("I", style, rect)
    img_plain = _render(
        "I", replace(style, outline={**style.outline, "enabled": False}), rect
    )
    x0, y0, x1, y1 = _fill_bbox(img_plain)
    w = float(style.outline["width_px"])
    lo = math.ceil(0.6 * w) + 1  # 6 for W=8 — beyond the legacy ~W/2 (+AA) reach
    hi = math.floor(0.9 * w)  # 7 for W=8 — still inside the full-W outward ring
    assert lo <= hi, "probe window degenerate for this width"
    above = _region(img_outlined, x0, y0 - hi, x1, y0 - lo + 1)
    below = _region(img_outlined, x0, y1 + lo, x1, y1 + hi + 1)
    left = _region(img_outlined, x0 - hi, y0, x0 - lo + 1, y1)
    right = _region(img_outlined, x1 + lo, y0, x1 + hi + 1, y1)
    assert _count(above, _OUTLINE, 60) > 0, "ring must reach ~W px ABOVE the glyph"
    assert _count(below, _OUTLINE, 60) > 0, "ring must reach ~W px BELOW the glyph"
    assert _count(left, _OUTLINE, 60) > 0, "ring must reach ~W px LEFT of the glyph"
    assert _count(right, _OUTLINE, 60) > 0, "ring must reach ~W px RIGHT of the glyph"


@pytest.mark.unit
def test_outline_never_eats_glyph_interior(qapp) -> None:
    """Horizontal word "AAA": the glyph interior stays PURE fill — the
    global whole-document coverage of the interior-purity contract."""
    rect = QRectF(0, 0, 240, 140)
    style = _outline_probe_style()
    img_outlined = _render("AAA", style, rect)
    img_plain = _render(
        "AAA", replace(style, outline={**style.outline, "enabled": False}), rect
    )
    _assert_interior_pure(img_plain, img_outlined)


@pytest.mark.unit
def test_outline_vertical_stack_keeps_neighbor_fill_pure(qapp) -> None:
    """Vertical stack "あA": ALL silhouettes paint before ANY fill — the
    ring of the lower glyph can never chew the fill of the glyph above it
    (locks the global silhouette-then-fill ordering forever)."""
    rect = QRectF(0, 0, 160, 220)
    style = _outline_probe_style()
    img_outlined = _render("あA", style, rect, vertical=True)
    img_plain = _render(
        "あA",
        replace(style, outline={**style.outline, "enabled": False}),
        rect,
        vertical=True,
    )
    _assert_interior_pure(img_plain, img_outlined)
