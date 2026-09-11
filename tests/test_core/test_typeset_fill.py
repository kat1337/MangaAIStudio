"""Styled glyph-fill tests (quick-260910-vej) — the gradient + pattern fill
brushes riding the SHARED renderer (D-01: one code path for the canvas
overlay AND the bake).

These tests pin:

- Solid regression: ``fill_type="solid"`` keeps the legacy fill pixels
  (the byte-identical path — the brush merge never runs for solid).
- Gradient math, unit-level: ``_gradient_start_end`` direction, the
  corner-to-corner span, and exact center symmetry for 0/45/90/270.
- Gradient renders: 90° blue->yellow top/bottom/mid, 0° swaps left/right,
  270° inverts, and an alpha-carrying stop fades out (white->transparent).
- Vertical continuity: a tategaki column samples ONE continuous ramp (top
  char Color A, bottom char Color B) — not per-char resets.
- Pattern: tile repetition (one tile-period apart shares the color), the
  scale control, Color A alpha as tile opacity, tile colors inside glyphs.
- Fallbacks never raise: garbage/absent/oversized tiles render solid.
- Bake parity (D-01): gradient and pattern boxes bake byte-identical to the
  direct ``layout() + paint()`` render (the test_typeset_bake pattern).

Qt-required (QPainter/QTextDocument) — runs under the pytest-qt ``qapp``
fixture like the other renderer suites.
"""

from __future__ import annotations

import base64
import math
from io import BytesIO

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PIL import Image as PILImage  # noqa: E402
from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402

pytest.importorskip("pytestqt")  # qapp fixture

import manga_ai_studio.gui.text_renderer as tr  # noqa: E402
from manga_ai_studio.core.box_model import DETECTED, PageBox  # noqa: E402
from manga_ai_studio.core.text_style import TextStyle  # noqa: E402
from manga_ai_studio.gui.text_renderer import (  # noqa: E402
    _alpha_modulated_tile,
    _decoded_scaled_tile,
    _gradient_start_end,
    _qimage_argb_to_numpy,
    bake_typeset_page,
    layout,
    numpy_to_qimage,
    paint,
    qimage_to_numpy,
    style_fill_brush,
)
from panelcleaner.structures import Box  # noqa: E402

_BLUE = "#0000ff"
_YELLOW = "#ffff00"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fill_style(**kwargs) -> TextStyle:
    """A deterministic pixel-probe style (fixed size, top-left, no outline).

    Mirrors the ``_PIXEL_STYLE`` convention from test_typeset_bake.py: the
    glyph geometry is pinned so color sampling lands where the assertions
    expect it, and the outline stays disabled so the fill pixels are
    observable.
    """
    base = dict(
        font_size_px=60.0,
        auto_fit=False,
        align_h="left",
        align_v="top",
        outline={"enabled": False, "color": "#0b0b0e", "width_px": 2.0},
    )
    base.update(kwargs)
    return TextStyle(**base)


def _render_np(
    text: str,
    style: TextStyle,
    box_w: int = 200,
    box_h: int = 200,
    vertical: bool = False,
) -> np.ndarray:
    """Render ``text`` through the shared layout+paint into a transparent
    ARGB32 surface, returning the DETACHED BGRA numpy array."""
    rect = QRectF(0, 0, box_w, box_h)
    result = layout(text, style, rect, vertical=vertical)
    img = QImage(box_w, box_h, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    paint(painter, result, style)
    painter.end()
    return _qimage_argb_to_numpy(img)


def _ink_mask(arr: np.ndarray, min_alpha: int = 240) -> np.ndarray:
    """The strongly-opaque glyph pixels (antialiasing edges excluded)."""
    return arr[..., 3] >= min_alpha


def _median_rgb(arr: np.ndarray, mask: np.ndarray) -> tuple[float, float, float]:
    """Median (B, G, R) over the masked pixels — antialiasing-robust."""
    pixels = arr[mask]
    assert pixels.size, "the mask must select ink pixels"
    return tuple(float(np.median(pixels[:, i])) for i in range(3))


def _tile_png_b64(w: int = 8, h: int = 8) -> str:
    """A real two-color PNG tile: top half red, bottom half green (opaque)."""
    img = PILImage.new("RGBA", (w, h), (255, 0, 0, 255))
    for y in range(h // 2, h):
        for x in range(w):
            img.putpixel((x, y), (0, 255, 0, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _is_red(px) -> bool:
    return px[2] > 180 and px[1] < 100  # B, G, R


def _is_green(px) -> bool:
    return px[1] > 180 and px[2] < 100  # B, G, R


def _fill_rect_np(style: TextStyle, w: int = 32, h: int = 32) -> np.ndarray:
    """Fill a rect with the style's fill brush directly (deterministic tiling
    probe — no glyph geometry in the way)."""
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.fillRect(QRectF(0, 0, w, h), style_fill_brush(style, QRectF(0, 0, w, h)))
    painter.end()
    return _qimage_argb_to_numpy(img)


# ---------------------------------------------------------------------------
# Solid regression — the legacy path stays byte-identical
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_solid_fill_renders_legacy_color_pixels(qapp) -> None:
    """A ``fill_type="solid"`` style renders the SAME dominant glyph pixels
    as a legacy style — the shared path is untouched for solid (the brush
    merge in _build_document never runs)."""
    explicit = _fill_style(color="#e8e8ea", fill_type="solid")
    legacy = _fill_style(color="#e8e8ea")  # fill_type defaults to "solid"
    arr = _render_np("Hi", explicit)
    assert np.array_equal(arr, _render_np("Hi", legacy))

    mask = _ink_mask(arr)
    b, g, r = _median_rgb(arr, mask)
    assert (round(b), round(g), round(r)) == (234, 232, 232), (
        "the solid fill must render the plain color verbatim"
    )


# ---------------------------------------------------------------------------
# Gradient math, unit-level (the factory's start/end geometry)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_gradient_start_end_directions_and_symmetry() -> None:
    """Direction, corner-to-corner span, and center symmetry for the
    canonical angles: 0° left->right, 90° top->bottom, 270° inverted,
    45° diagonal — start+end == 2*center at EVERY angle."""
    rect = QRectF(0.0, 0.0, 100.0, 50.0)
    cx, cy = 50.0, 25.0

    s0, e0 = _gradient_start_end(rect, 0.0)
    assert (s0.x(), s0.y()) == pytest.approx((0.0, 25.0))
    assert (e0.x(), e0.y()) == pytest.approx((100.0, 25.0))  # left->right

    s90, e90 = _gradient_start_end(rect, 90.0)
    assert (s90.x(), s90.y()) == pytest.approx((50.0, 0.0))
    assert (e90.x(), e90.y()) == pytest.approx((50.0, 50.0))  # top->bottom

    s270, e270 = _gradient_start_end(rect, 270.0)
    assert (s270.x(), s270.y()) == pytest.approx((50.0, 50.0))  # inverted
    assert (e270.x(), e270.y()) == pytest.approx((50.0, 0.0))

    s45, e45 = _gradient_start_end(rect, 45.0)
    assert e45.x() > s45.x() and e45.y() > s45.y()  # down-right diagonal
    # Corner-to-corner span: the bbox's far corners project onto the ramp's
    # exact endpoints (the projection of the bbox onto the direction is
    # w*|cos| + h*|sin|, half on each side of the center).
    d45x, d45y = math.cos(math.radians(45.0)), math.sin(math.radians(45.0))
    r45 = (100.0 * d45x + 50.0 * d45y) / 2.0
    proj_start = (s45.x() - cx) * d45x + (s45.y() - cy) * d45y
    proj_end = (e45.x() - cx) * d45x + (e45.y() - cy) * d45y
    assert proj_start == pytest.approx(-r45)
    assert proj_end == pytest.approx(r45)

    for start, end in ((s0, e0), (s90, e90), (s270, e270), (s45, e45)):
        assert start.x() + end.x() == pytest.approx(2.0 * cx)
        assert start.y() + end.y() == pytest.approx(2.0 * cy)


# ---------------------------------------------------------------------------
# Gradient renders (pixel-level through the shared paint path)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_gradient_render_90_top_blue_bottom_yellow(qapp) -> None:
    """A 90° blue->yellow gradient samples blue at the glyph top, yellow at
    the bottom, and an interpolated mix in the middle."""
    style = _fill_style(color=_BLUE, fill_type="gradient", fill_color_b=_YELLOW)
    arr = _render_np("I", style, box_w=120, box_h=120)
    mask = _ink_mask(arr)
    rows = np.where(mask.any(axis=1))[0]
    top, bottom = int(rows.min()), int(rows.max())
    mid = (top + bottom) // 2

    bt, gt, rt = _median_rgb(arr[top : top + 4], mask[top : top + 4])
    bb, gb, rb = _median_rgb(arr[bottom - 3 : bottom + 1], mask[bottom - 3 : bottom + 1])
    bm, gm, rm = _median_rgb(arr[mid - 1 : mid + 2], mask[mid - 1 : mid + 2])

    assert bt > 150 and rt < 100, f"top must be blue-ish, got B={bt} R={rt}"
    assert rb > 150 and bb < 100, f"bottom must be yellow-ish, got R={rb} B={bb}"
    assert 80 < bm < 180 and 80 < rm < 180, (
        f"the middle must be interpolated, got B={bm} R={rm}"
    )


@pytest.mark.unit
def test_gradient_render_0_deg_swaps_left_right(qapp) -> None:
    """0° = left->right: Color A (blue) on the left, Color B (yellow) on the
    right — the horizontal mirror of the 90° render. A wide run samples the
    ramp (the ramp spans the full doc text width)."""
    style = _fill_style(
        color=_BLUE,
        fill_type="gradient",
        fill_color_b=_YELLOW,
        fill_angle_deg=0.0,
    )
    arr = _render_np("HIHIHI", style, box_w=120, box_h=140)
    mask = _ink_mask(arr)
    cols = np.where(mask.any(axis=0))[0]
    left, right = int(cols.min()), int(cols.max())
    middle = (left + right) // 2

    bl, gl, rl = _median_rgb(arr[:, left : left + 6], mask[:, left : left + 6])
    br, gr, rr = _median_rgb(
        arr[:, right - 5 : right + 1], mask[:, right - 5 : right + 1]
    )
    bmid, gmid, rmid = _median_rgb(
        arr[:, middle - 2 : middle + 3], mask[:, middle - 2 : middle + 3]
    )

    assert bl > 150 and rl < 100, f"left must be blue-ish, got B={bl} R={rl}"
    assert rr > 150 and br < 100, f"right must be yellow-ish, got R={rr} B={br}"
    assert 80 < bmid < 180 and 80 < rmid < 180, (
        f"the middle must be interpolated, got B={bmid} R={rmid}"
    )


@pytest.mark.unit
def test_gradient_render_270_inverts(qapp) -> None:
    """270° runs bottom->top: Color A (blue) at the BOTTOM, Color B (yellow)
    at the top — the inverted ramp."""
    style = _fill_style(
        color=_BLUE,
        fill_type="gradient",
        fill_color_b=_YELLOW,
        fill_angle_deg=270.0,
    )
    arr = _render_np("I", style, box_w=120, box_h=120)
    # Verify the angle survived the model round-trip (270 within 0..360).
    assert tr.TextStyle.from_dict(style.to_dict()).fill_angle_deg == 270.0
    mask = _ink_mask(arr)
    rows = np.where(mask.any(axis=1))[0]
    top, bottom = int(rows.min()), int(rows.max())

    bt, gt, rt = _median_rgb(arr[top : top + 4], mask[top : top + 4])
    bb, gb, rb = _median_rgb(arr[bottom - 3 : bottom + 1], mask[bottom - 3 : bottom + 1])
    assert rt > 150 and bt < 100, f"top must be yellow-ish, got R={rt} B={bt}"
    assert bb > 150 and rb < 100, f"bottom must be blue-ish, got B={bb} R={rb}"


@pytest.mark.unit
def test_gradient_alpha_stop_fades_out(qapp) -> None:
    """An alpha-carrying stop (Color A = #00ffffff, fully transparent) fades
    the glyph out toward that end — near-zero alpha at the top, opaque at
    the bottom (the white->transparent fade-out use case, LOCKED)."""
    style = _fill_style(
        color="#00ffffff", fill_type="gradient", fill_color_b="#ffffff00"
    )
    arr = _render_np("I", style, box_w=120, box_h=120)
    mask = arr[..., 3] > 0  # ANY glyph pixel — the fade needs the low tail
    rows = np.where(mask.any(axis=1))[0]
    top, bottom = int(rows.min()), int(rows.max())
    top_alphas = arr[top : top + 4, ..., 3][mask[top : top + 4]]
    bottom_alphas = arr[bottom - 3 : bottom + 1, ..., 3][mask[bottom - 3 : bottom + 1]]
    assert float(np.median(top_alphas)) < 100, (
        "the transparent stop must fade the top glyphs to near-zero alpha"
    )
    assert float(np.median(bottom_alphas)) > 180, (
        "the opaque stop must keep the bottom glyphs near-opaque"
    )


# ---------------------------------------------------------------------------
# Vertical continuity — ONE continuous ramp across the column
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_vertical_column_carries_one_continuous_gradient(qapp) -> None:
    """A tategaki column of 3 upright chars with a 90° gradient: the TOP char
    samples Color A and the BOTTOM char samples Color B — the per-char
    offset mapping works (a per-char reset would give every char the same
    top-A-to-bottom-B ramp and fail this)."""
    style = _fill_style(
        color=_BLUE,
        fill_type="gradient",
        fill_color_b=_YELLOW,
        font_size_px=44.0,
    )
    arr = _render_np("abc", style, box_w=120, box_h=300, vertical=True)
    mask = _ink_mask(arr)
    rows = np.where(mask.any(axis=1))[0]
    top, bottom = int(rows.min()), int(rows.max())
    span = bottom - top
    # Top third vs bottom third of the column (each char owns ~1/3).
    b_top, g_top, r_top = _median_rgb(
        arr[top : top + span // 3], mask[top : top + span // 3]
    )
    b_bot, g_bot, r_bot = _median_rgb(
        arr[bottom - span // 3 : bottom + 1], mask[bottom - span // 3 : bottom + 1]
    )
    assert b_top - r_top > 60, (
        f"the top char must lean Color A (blue), got B={b_top} R={r_top}"
    )
    assert r_bot - b_bot > 60, (
        f"the bottom char must lean Color B (yellow), got R={r_bot} B={b_bot}"
    )


# ---------------------------------------------------------------------------
# Pattern — tiling, scale, alpha modulation, glyph presence
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pattern_brush_tiles_repeats_and_scales(qapp) -> None:
    """The pattern brush tiles the decoded tile with a true period (a sample
    one tile-period apart shares the color) and ``pattern_scale`` zooms the
    period (scale=2 differs from scale=1 at the same point)."""
    b64 = _tile_png_b64(8, 8)  # top half red / bottom half green
    s1 = _fill_style(fill_type="pattern", pattern_tile_b64=b64, pattern_scale=1.0)
    s2 = _fill_style(fill_type="pattern", pattern_tile_b64=b64, pattern_scale=2.0)

    a1 = _fill_rect_np(s1)
    # Period 8: (x, y) and (x, y+8) share the exact pixel.
    assert np.array_equal(a1[1, 1], a1[9, 1]), "the tile must repeat with period 8"
    assert _is_red(a1[1, 1]) and _is_green(a1[5, 1]), (
        "the tile colors must appear in order (red top, green bottom)"
    )

    a2 = _fill_rect_np(s2)
    assert np.array_equal(a2[1, 1], a2[17, 1]), "scale=2 must double the period"
    # Row 9 (col 1): row 9 % 8 = 1 -> red at scale=1; row 9 of the zoomed
    # 16px tile maps to source row ~4.25 -> green at scale=2.
    assert _is_red(a1[9, 1]) and _is_green(a2[9, 1]), (
        "pattern_scale=2 must visibly change the tiling at the same point"
    )


@pytest.mark.unit
def test_pattern_alpha_modulation_from_color_a(qapp) -> None:
    """The LOCKED single-opacity-control rule: the tile is drawn with Color
    A's alpha — tile alpha 255 x Color A alpha 128 -> sampled alpha ~128."""
    b64 = _tile_png_b64(8, 8)
    style = _fill_style(color="#80ff0000", fill_type="pattern", pattern_tile_b64=b64)
    arr = _fill_rect_np(style)
    alphas = arr[arr[..., 3] > 0][..., 3]
    assert alphas.size
    assert abs(float(np.median(alphas)) - 128) <= 1, (
        "the tile alpha must equal Color A's alpha (128)"
    )

    # Unit-level: the modulation helper multiplies alpha and leaves RGB.
    scaled = _decoded_scaled_tile(
        _fill_style(fill_type="pattern", pattern_tile_b64=b64)
    )
    modulated = _qimage_argb_to_numpy(
        _alpha_modulated_tile(scaled, tr.QColor("#80ff0000"))
    )
    original = _qimage_argb_to_numpy(scaled)
    assert (modulated[..., :3] == original[..., :3]).all()
    assert abs(float(np.median(modulated[..., 3])) - 128) <= 1


@pytest.mark.unit
def test_pattern_renders_tile_colors_inside_glyphs(qapp) -> None:
    """A pattern-filled glyph contains BOTH tile colors (the tile is clipped
    to the glyphs, and the tiling survives the QTextCharFormat brush)."""
    b64 = _tile_png_b64(8, 8)
    style = _fill_style(fill_type="pattern", pattern_tile_b64=b64)
    arr = _render_np("H", style, box_w=120, box_h=120)
    mask = _ink_mask(arr)
    pixels = arr[mask]
    reds = sum(1 for px in pixels if _is_red(px))
    greens = sum(1 for px in pixels if _is_green(px))
    assert reds > 0 and greens > 0, (
        "both tile colors must be visible inside the glyph ink"
    )


@pytest.mark.unit
def test_decoded_tile_is_cached_and_bounded(qapp) -> None:
    """T-vej-02: the decoded+scaled tile is cached (the same QImage object is
    returned for a repeated decode) and the cache stays bounded."""
    b64 = _tile_png_b64(4, 4)
    style = _fill_style(fill_type="pattern", pattern_tile_b64=b64)
    first = _decoded_scaled_tile(style)
    second = _decoded_scaled_tile(style)
    assert first is second, "repeated decodes must hit the cache"

    tr._tile_cache.clear()
    for i in range(12):
        _decoded_scaled_tile(
            _fill_style(fill_type="pattern", pattern_tile_b64=_tile_png_b64(4, 4 + i))
        )
    assert len(tr._tile_cache) <= tr._TILE_CACHE_MAX, (
        "the decode cache must stay bounded (evict-oldest)"
    )


# ---------------------------------------------------------------------------
# Fallbacks — never crash, degrade to solid Color A
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pattern_fallbacks_render_solid_without_raising(qapp) -> None:
    """Garbage b64 and an absent tile both render SOLID Color A — no
    exception anywhere (T-vej-01)."""
    solid = _fill_style(color="#ff00ff")
    solid_arr = _render_np("Hi", solid)

    garbage = _fill_style(
        color="#ff00ff", fill_type="pattern", pattern_tile_b64="!!!not-base64!!!"
    )
    assert np.array_equal(_render_np("Hi", garbage), solid_arr)

    none_tile = _fill_style(color="#ff00ff", fill_type="pattern")
    assert np.array_equal(_render_np("Hi", none_tile), solid_arr)


@pytest.mark.unit
def test_pattern_oversized_tile_guard_falls_back_to_solid(
    qapp, monkeypatch
) -> None:
    """T-vej-01: a decoded tile whose max dimension exceeds the guard renders
    solid Color A with a warning — never an unbounded allocation (the guard
    threshold is monkeypatched small so no mega-surface is ever decoded)."""
    monkeypatch.setattr(tr, "_TILE_DECODE_MAX_DIMENSION", 4)
    b64 = _tile_png_b64(8, 8)  # 8x8 > the patched 4px guard
    style = _fill_style(color="#ff00ff", fill_type="pattern", pattern_tile_b64=b64)
    solid_arr = _render_np("Hi", _fill_style(color="#ff00ff"))
    assert _decoded_scaled_tile(style) is None
    assert np.array_equal(_render_np("Hi", style), solid_arr)


# ---------------------------------------------------------------------------
# Bake parity (D-01) — gradient and pattern bake ≡ direct render
# ---------------------------------------------------------------------------


def _page_and_fill_boxes():
    """A synthetic page with one gradient box and one pattern box."""
    page = np.full((160, 120, 3), (30, 40, 50), dtype=np.uint8)
    gradient_pb = PageBox(
        box=Box(2, 2, 62, 62),
        origin=DETECTED,
        style=_fill_style(color=_BLUE, fill_type="gradient", fill_color_b=_YELLOW),
    )
    gradient_pb.set_recognized_text("Hi")
    pattern_pb = PageBox(
        box=Box(66, 10, 116, 60),
        origin=DETECTED,
        style=_fill_style(
            fill_type="pattern", pattern_tile_b64=_tile_png_b64(8, 8)
        ),
    )
    pattern_pb.set_recognized_text("OK")
    return page, [gradient_pb, pattern_pb]


@pytest.mark.unit
def test_bake_equals_direct_render_for_gradient_and_pattern(qapp) -> None:
    """D-01 bake parity: ``bake_typeset_page`` on a gradient box + a pattern
    box is byte-identical to the direct ``layout() + paint()`` render —
    canvas ≡ bake is structural for BOTH new fill types."""
    from manga_ai_studio.gui.text_renderer import current_focus_text

    page, boxes = _page_and_fill_boxes()
    baked = bake_typeset_page(page, boxes)

    qimg = numpy_to_qimage(page).copy()
    painter = QPainter(qimg)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    for pb in boxes:
        text = current_focus_text(pb)
        x, y, w, h = pb.box.as_tuple_xywh
        result = layout(text, pb.style, QRectF(x, y, w, h), vertical=False)
        paint(painter, result, pb.style)
    painter.end()
    direct = qimage_to_numpy(qimg)

    assert np.array_equal(baked, direct), (
        "the bake must produce identical pixels to the direct shared-path "
        "render for gradient and pattern fills (D-01)"
    )
    # And the fills actually landed (not a vacuous equality on empty pages).
    region = baked[2:62, 2:62]
    assert ((region != page[2:62, 2:62]).any(axis=2)).any(), (
        "the gradient box must visibly alter the page"
    )
