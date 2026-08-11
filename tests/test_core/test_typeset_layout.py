"""Horizontal typeset layout tests (plan 07-01 Task 1) — the shared renderer's
``layout()`` pure geometry: wrap at the inner width, H/V alignment shifts,
the overflow flag, and the Auto-fit bounded machinery (D-15, the 04-09
constants preserved at scene px).

The renderer is Qt-dependent (QFont/QTextDocument) but widget-free — these
tests run under pytest-qt's ``qapp`` fixture (offscreen), matching the
headless-testable contract of RESEARCH Pattern 1.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QRectF  # noqa: E402

from manga_ai_studio.core.text_style import TextStyle  # noqa: E402
from manga_ai_studio.gui.text_renderer import layout  # noqa: E402

# The renderer's inner-rect inset (box rect shrunk on every side).
_INNER_INSET = 2.0


def _inner(w: float, h: float) -> tuple[float, float]:
    """The inner width/height the renderer computes for a box rect."""
    return max(1.0, w - 2 * _INNER_INSET), max(1.0, h - 2 * _INNER_INSET)


# ---------------------------------------------------------------------------
# Test 5 — wrap geometry
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_wrap_produces_two_lines_for_long_string(qapp) -> None:
    """A long string in a narrow rect WRAPS at the inner width (>= 2 line rects)."""
    rect = QRectF(0, 0, 100, 50)
    result = layout("hello world " * 5, TextStyle(), rect, vertical=False)
    assert len(result.line_rects) >= 2, "long text must wrap into multiple lines"
    inner_w, _ = _inner(100, 50)
    for line_rect in result.line_rects:
        assert line_rect.width() <= inner_w + 0.5, "lines must wrap at the inner width"


@pytest.mark.unit
def test_overflow_false_when_text_fits(qapp) -> None:
    """A short text that fits reports overflow False."""
    result = layout("hello", TextStyle(), QRectF(0, 0, 100, 50), vertical=False)
    assert result.overflow is False


@pytest.mark.unit
def test_overflow_true_when_fixed_size_exceeds_inner_height(qapp) -> None:
    """A fixed-size text taller than the inner height reports overflow True."""
    style = TextStyle(font_size_px=40.0, auto_fit=False)
    rect = QRectF(0, 0, 100, 30)
    result = layout("Big text here", style, rect, vertical=False)
    assert result.overflow is True
    _, inner_h = _inner(100, 30)
    assert result.ink.height() > inner_h


# ---------------------------------------------------------------------------
# Alignment (align_h / align_v shift the ink rect)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_align_h_shifts_ink_rect(qapp) -> None:
    """align_h left/center/right shifts the ink rect's x within the inner rect."""
    style = TextStyle(font_size_px=12.0, auto_fit=False, align_h="left")
    rect = QRectF(0, 0, 200, 60)
    left_ink = layout("hello", style, rect).ink
    center_ink = layout("hello", TextStyle(font_size_px=12.0, auto_fit=False, align_h="center"), rect).ink
    right_ink = layout("hello", TextStyle(font_size_px=12.0, auto_fit=False, align_h="right"), rect).ink
    assert left_ink.left() == pytest.approx(0.0, abs=0.5)
    assert left_ink.left() < center_ink.left() < right_ink.left()
    assert right_ink.right() == pytest.approx(_inner(200, 60)[0], abs=0.5)


@pytest.mark.unit
def test_align_v_shifts_ink_rect(qapp) -> None:
    """align_v top/middle/bottom shifts the PAINT ORIGIN's y (the vertical
    offset rides the layout origin — the ink rect itself is doc-local)."""
    rect = QRectF(0, 0, 200, 60)
    top = layout("hello", TextStyle(font_size_px=12.0, auto_fit=False, align_v="top"), rect)
    middle = layout("hello", TextStyle(font_size_px=12.0, auto_fit=False, align_v="middle"), rect)
    bottom = layout("hello", TextStyle(font_size_px=12.0, auto_fit=False, align_v="bottom"), rect)
    inner_h = _inner(200, 60)[1]
    block_h = top.document.size().height()
    assert top.origin.y() == pytest.approx(_INNER_INSET, abs=0.5)
    assert middle.origin.y() == pytest.approx(
        _INNER_INSET + (inner_h - block_h) / 2.0, abs=0.5
    )
    assert bottom.origin.y() == pytest.approx(_INNER_INSET + inner_h - block_h, abs=0.5)
    assert top.origin.y() < middle.origin.y() < bottom.origin.y()


# ---------------------------------------------------------------------------
# Manual size vs Auto-fit (D-15)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_manual_size_renders_at_exact_size(qapp) -> None:
    """font_size_px set + auto_fit False renders at exactly that size (no clamp)."""
    style = TextStyle(font_size_px=24.0, auto_fit=False)
    result = layout("hello", style, QRectF(0, 0, 200, 100), vertical=False)
    assert result.used_font_size_px == pytest.approx(24.0, abs=0.1)


@pytest.mark.unit
def test_auto_fit_uses_box_adaptive_base(qapp) -> None:
    """Auto-fit (default) uses the box-adaptive base 14 x min(w,h)/100, clamped [10,28]."""
    # 200x100 rect -> min dim 100 -> base 14 (the UI-SPEC reference box).
    r14 = layout("hello", TextStyle(), QRectF(0, 0, 200, 100))
    assert r14.used_font_size_px == pytest.approx(14.0, abs=0.1)
    # 300x300 rect -> min dim 300 -> base 42 -> clamped to 28.
    r28 = layout("hello", TextStyle(), QRectF(0, 0, 300, 300))
    assert r28.used_font_size_px == pytest.approx(28.0, abs=0.1)
    # 100x40 rect -> min dim 40 -> base 5.6 -> clamped up to 10.
    r10 = layout("hello", TextStyle(), QRectF(0, 0, 100, 40))
    assert r10.used_font_size_px == pytest.approx(10.0, abs=0.1)


@pytest.mark.unit
def test_auto_fit_shrinks_wrapped_text_to_fit(qapp) -> None:
    """Wrapped text taller than the inner height shrinks (bounded) until it fits."""
    style = TextStyle()
    rect = QRectF(0, 0, 200, 100)
    result = layout("word " * 40, style, rect, vertical=False)
    # The shrink loop engaged: rendered size below the 14px base.
    assert result.used_font_size_px < 14.0
    # ...and the block now fits inside the inner height (or the floor held).
    _, inner_h = _inner(200, 100)
    assert result.overflow is False or result.used_font_size_px <= 5.5


# ---------------------------------------------------------------------------
# Task 3 — Test 3: the Auto-fit floor (D-15 / UI-SPEC long-text row)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_auto_fit_floor_terminates_for_huge_text(qapp) -> None:
    """A 2000-char translation in a small box: the bounded loop TERMINATES
    (12 iters max) and never renders below the 5 px scene floor; the text
    floors (overflow reported) when it cannot fit even at the floor."""
    rect = QRectF(0, 0, 200, 60)
    result = layout("x" * 2000, TextStyle(), rect, vertical=False)
    assert result.used_font_size_px >= 5.0 - 1e-6, (
        "the loop must never render below the 5 px floor"
    )
    assert result.overflow is True, (
        "2000 chars in a 200x60 box cannot fit — the floor holds and overflow"
        " is reported (the ink rect may exceed the inner rect at the floor)"
    )
    assert result.ink.height() > 0.0


@pytest.mark.unit
def test_auto_fit_fits_long_text_within_loop_budget(qapp) -> None:
    """A long translation in a wide box fits at a size at-or-above the floor
    (the loop terminates by FIT, the ink stays inside the inner rect)."""
    rect = QRectF(0, 0, 400, 200)
    result = layout("x" * 600, TextStyle(), rect, vertical=False)
    assert result.used_font_size_px >= 5.0 - 1e-6
    assert result.overflow is False, "the text must fit in the wide box"
    _, inner_h = _inner(400, 200)
    assert result.ink.height() <= inner_h + 1e-6
