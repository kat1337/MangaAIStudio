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
from manga_ai_studio.gui.text_renderer import (  # noqa: E402
    char_rotates,
    layout,
    layout_vertical,
)

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
    """Auto-fit (default) starts from the box-adaptive base 14 x min(w,h)/100
    clamped [10,28] — but the clamp is a STARTING point, not a hard max
    (G-07-4): short text GROWS above it, bounded by the per-box growth cap
    min(inner_w, inner_h), never overflowing."""
    # 200x100 rect -> min dim 100 -> base 14 (the UI-SPEC reference box):
    # short text grows above the 14 px base, capped at min(inner_w, inner_h).
    r14 = layout("hello", TextStyle(), QRectF(0, 0, 200, 100))
    cap14 = min(_inner(200, 100))
    assert r14.used_font_size_px > 14.0, "growth must exceed the 14 px base"
    assert r14.used_font_size_px <= cap14 + 1e-6, (
        "growth is capped at min(inner_w, inner_h)"
    )
    assert r14.overflow is False
    # 300x300 rect -> min dim 300 -> base 42 -> the old 28 px clamp is NOT
    # a hard max: the rendered size exceeds it (bounded by the cap).
    r28 = layout("hello", TextStyle(), QRectF(0, 0, 300, 300))
    cap28 = min(_inner(300, 300))
    assert r28.used_font_size_px > 28.0, (
        "growth must exceed the old 28 px clamp max (clamp-as-max removed)"
    )
    assert r28.used_font_size_px <= cap28 + 1e-6
    assert r28.overflow is False
    # 100x40 rect -> min dim 40 -> base 5.6 -> clamped up to 10: short text
    # grows above the 10 px floor (cap = min(96, 36) = 36).
    r10 = layout("hello", TextStyle(), QRectF(0, 0, 100, 40))
    cap10 = min(_inner(100, 40))
    assert r10.used_font_size_px > 10.0, "growth must exceed the 10 px floor clamp"
    assert r10.used_font_size_px <= cap10 + 1e-6
    assert r10.overflow is False


@pytest.mark.unit
def test_auto_fit_grows_short_text_to_fit(qapp) -> None:
    """G-07-4: short text in a large box renders ABOVE the old 28 px clamp max
    — auto-fit fills the box (big enough to be legible), bounded by the
    per-box growth cap min(inner_w, inner_h), never overflowing."""
    result = layout("hello", TextStyle(), QRectF(0, 0, 300, 300))
    inner_w, inner_h = _inner(300, 300)
    assert result.used_font_size_px > 28.0, (
        "auto-fit must grow short text beyond the old 28 px clamp max"
    )
    assert result.used_font_size_px <= min(inner_w, inner_h) + 1e-6, (
        "growth is capped at min(inner_w, inner_h)"
    )
    assert result.overflow is False


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
    (the loop terminates by FIT, the ink stays inside the inner rect).

    NOTE (quick-260823-hge re-derivation, RESEARCH pitfall 7): the text is
    space-separated words — a single 600-char unbreakable Latin RUN can no
    longer be accepted as a mid-loop fit (the ordering fix rejects
    Latin-split candidates down to the 5 px floor); the unavoidable-split
    floor escape is pinned by test_auto_fit_floor_escapes_with_honest_overflow.
    """
    rect = QRectF(0, 0, 400, 200)
    result = layout(" ".join(["word"] * 150), TextStyle(), rect, vertical=False)
    assert result.used_font_size_px >= 5.0 - 1e-6
    assert result.overflow is False, "the text must fit in the wide box"
    _, inner_h = _inner(400, 200)
    assert result.ink.height() <= inner_h + 1e-6


# ===========================================================================
# Vertical (tategaki) geometry — plan 07-03 Task 1 (D-11)
#
# Contract under test (RESEARCH Pattern 2 / Common Operation 2, UI-SPEC
# surface 34): placements are INNER-LOCAL coordinates (0..inner_w x
# 0..inner_h, the box rect shrunk by the renderer inset on every side).
# Columns stack top-to-bottom and flow right-to-left; column width = the
# max char extent in the column (1 em basis); each char is centered within
# its column; align_h shifts the column BLOCK left/center/right, align_v
# shifts the run top/middle/bottom along the column axis (A3).
# ===========================================================================


def _assert_upright(p: dict) -> None:
    assert p["rotate"] is False, f"upright char {p['char']!r} must not rotate"


# ---------------------------------------------------------------------------
# Test 1 — orientation classification (the D-11 correctness contract)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_vertical_classification(qapp) -> None:
    """G-07-1 (user override): Latin letters/digits stay UPRIGHT (one letter
    above the other — the override of the W3C rotated-Latin convention);
    halfwidth ASCII punctuation + brackets/dashes rotate 90 deg; CJK/kana
    and vertical-form punctuation stay upright."""
    # Letters and digits (0-9, A-Z, a-z) — UPRIGHT (G-07-1).
    ascii_upright = (
        [chr(i) for i in range(0x30, 0x3A)]
        + [chr(i) for i in range(0x41, 0x5B)]
        + [chr(i) for i in range(0x61, 0x7B)]
    )
    for ch in ascii_upright:
        assert char_rotates(ch) is False, (
            f"{ch!r} (0x{ord(ch):02X}) must stay upright (G-07-1)"
        )
    # Halfwidth ASCII punctuation (0x21..0x7E minus letters/digits) rotates.
    ascii_rotate = [
        chr(i)
        for i in range(0x21, 0x7F)
        if not (0x30 <= i <= 0x39 or 0x41 <= i <= 0x5A or 0x61 <= i <= 0x7A)
    ]
    assert ascii_rotate, "the punctuation-only rotate set must be non-empty"
    for ch in ascii_rotate:
        assert char_rotates(ch) is True, f"{ch!r} (0x{ord(ch):02X}) must rotate"
    # Bracket/dash/ellipsis set (fullwidth + halfwidth).
    extra_rotate = "「」『』（）《》〈〉【】—…～-()"
    for ch in extra_rotate:
        assert char_rotates(ch) is True, f"{ch!r} must rotate"
    # Upright: CJK, kana, and vertical-form punctuation.
    upright = "あ漢字がアカん。．，、·：；！？"
    for ch in upright:
        assert char_rotates(ch) is False, f"{ch!r} must stay upright"
    # The space (0x20) is NOT halfwidth ASCII (0x21..0x7E) — stays upright.
    assert char_rotates(" ") is False
    assert char_rotates("") is False


# ---------------------------------------------------------------------------
# Test 2 — RTL column flow (later chars at smaller x; first column at the
# right inner edge)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_vertical_rtl_column_flow(qapp) -> None:
    """Columns advance right-to-left: a later char of a wrapped line sits at
    a STRICTLY smaller x; the first column starts at the box's right inner
    edge (align_h right — the natural tategaki origin)."""
    style = TextStyle(font_size_px=14.0, auto_fit=False, align_h="right")
    inner_w, inner_h = 96.0, 20.0  # one char per column -> every pair wraps
    placements = layout_vertical("あいうえおかきくけこ", style, inner_w, inner_h)
    assert len(placements) == 10
    # First column at the right inner edge (inner-local coords).
    assert placements[0]["x"] == pytest.approx(inner_w - placements[0]["w"], abs=1.5)
    # RTL pinned by test, not prose: strictly decreasing x across wraps.
    for i in range(1, len(placements)):
        assert placements[i]["x"] < placements[i - 1]["x"], (
            f"char {i} must sit LEFT of char {i - 1} (RTL column flow)"
        )


@pytest.mark.unit
def test_vertical_layout_result_carries_placements(qapp) -> None:
    """layout(vertical=True) returns the vertical placement form in
    LayoutResult (origin = box top-left + inset; placements inner-local)."""
    style = TextStyle(font_size_px=14.0, auto_fit=False, align_h="right")
    result = layout("あいうえお", style, QRectF(0, 0, 100, 24), vertical=True)
    assert len(result.vertical_placements) == 5
    assert result.origin.x() == pytest.approx(_INNER_INSET, abs=0.5)
    assert result.origin.y() == pytest.approx(_INNER_INSET, abs=0.5)
    assert result.ink.width() > 0.0 and result.ink.height() > 0.0
    # RTL flow holds through the LayoutResult form too.
    assert result.vertical_placements[1]["x"] < result.vertical_placements[0]["x"]


# ---------------------------------------------------------------------------
# Test 3 — wrap at the inner height
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_vertical_wrap_at_height(qapp) -> None:
    """Characters beyond inner_h start a new column (at the top, left of the
    previous column); nothing is placed beyond the left inner edge."""
    style = TextStyle(font_size_px=14.0, auto_fit=False, align_v="top")
    inner_w, inner_h = 96.0, 36.0  # 2 chars per column -> 3 columns for 5 chars
    placements = layout_vertical("あいうえお", style, inner_w, inner_h)
    assert placements[0]["y"] == pytest.approx(0.0, abs=0.5)
    # Same-column stacking: advance = the char box height.
    assert placements[1]["y"] == pytest.approx(
        placements[0]["y"] + placements[0]["h"], abs=0.5
    )
    # Beyond inner_h -> a NEW column at the top.
    assert placements[2]["y"] == pytest.approx(placements[0]["y"], abs=0.5)
    assert placements[2]["x"] < placements[0]["x"]
    # Nothing placed beyond the left inner edge (x >= 0).
    assert min(p["x"] for p in placements) >= -0.5
    # Columns never exceed inner_h (each column's bottom stays inside).
    assert placements[0]["y"] + placements[0]["h"] <= inner_h + 0.5
    assert placements[1]["y"] + placements[1]["h"] <= inner_h + 0.5


# ---------------------------------------------------------------------------
# Test 4 — rotated advance (Latin height not width; CJK width)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_vertical_rotated_advance(qapp) -> None:
    """G-07-1 (user override): Latin letters/digits place UPRIGHT — the
    column extent is the char WIDTH (one letter above the other); a rotated
    punctuation sample keeps the height > width + height-based-advance
    assertions; CJK unchanged.

    NOTE: the plan's literal "square-ish (w >= h - tolerance)" for upright
    Latin does not hold on the real font stack — the Qt line-box height
    (15.62 px) exceeds the advance width (A: 9.33 px) at 14 px, so upright
    Latin is NEVER square-ish (07-03's CJK square assertion, 14 x 14, is the
    only square geometry). The upright-vs-rotated observable IS the column
    extent: upright chars contribute their WIDTH (extent = w -> the placed
    box sits flush at the column's left edge, x == 0 with align_h left),
    rotated chars contribute their HEIGHT (extent = h -> centered in a
    height-wide column, x offset beyond the glyph's own width).
    """
    style = TextStyle(font_size_px=14.0, auto_fit=False, align_h="left")

    # Upright Latin letters/digits: rotate False + width-based column extent.
    for ch in ("A", "1"):
        p = layout_vertical(ch, style, 96.0, 96.0)[0]
        _assert_upright(p)
        assert p["x"] == pytest.approx(0.0, abs=0.5), (
            f"upright {ch!r}: the column extent is the char WIDTH (x=0), "
            "not its height"
        )

    # Stacked A over 1: the vertical advance is the box HEIGHT.
    stack = layout_vertical("A1", style, 96.0, 96.0)
    assert stack[1]["y"] == pytest.approx(
        stack[0]["y"] + stack[0]["h"], abs=0.5
    )

    # Rotated punctuation: extent = the char HEIGHT -> the column is
    # height-wide, so the placed box centers with x offset beyond its width.
    bang = layout_vertical("!", style, 96.0, 96.0)[0]
    assert bang["rotate"] is True, "halfwidth ASCII punctuation ('!') rotates"
    assert bang["h"] > bang["w"], "rotated '!' placed height must exceed its width"
    assert bang["x"] > bang["w"], (
        "a rotated char centers in a HEIGHT-wide column (x offset beyond "
        "its own width)"
    )

    # The advance after a rotated char is measured along the HEIGHT, not the
    # width; the CJK char stays upright + square-ish (unchanged).
    mix = layout_vertical("!漢", style, 96.0, 96.0)
    kan = mix[1]
    assert mix[1]["y"] == pytest.approx(
        mix[0]["y"] + mix[0]["h"], abs=0.5
    )
    assert mix[1]["y"] > mix[0]["y"] + mix[0]["w"], (
        "the advance after a rotated char is measured along the HEIGHT, "
        "not the width"
    )
    _assert_upright(kan)
    assert kan["w"] >= kan["h"] - 1.5, "CJK char must be square-ish (width >= height)"


# ---------------------------------------------------------------------------
# Test 5 — per-char centering + align_h / align_v block shifts (A3)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_vertical_centering_and_alignment(qapp) -> None:
    """Each char is centered within its 1 em column; align_h shifts the
    column BLOCK's x; align_v shifts the run along the column axis."""
    inner_w, inner_h = 96.0, 96.0
    # Centering: a mixed column ("あ" wide + "A" narrow) shares ONE center.
    style = TextStyle(font_size_px=14.0, auto_fit=False, align_h="left", align_v="top")
    placements = layout_vertical("あA", style, inner_w, inner_h)
    c0 = placements[0]["x"] + placements[0]["w"] / 2.0
    c1 = placements[1]["x"] + placements[1]["w"] / 2.0
    assert c0 == pytest.approx(c1, abs=0.5), "both chars share the column center"
    assert placements[0]["x"] >= 0.0
    # align_h: left hugs the left edge, right hugs the right edge, center in between.
    left = layout_vertical(
        "あ", TextStyle(font_size_px=14.0, auto_fit=False, align_h="left"), inner_w, inner_h
    )
    center = layout_vertical(
        "あ", TextStyle(font_size_px=14.0, auto_fit=False, align_h="center"), inner_w, inner_h
    )
    right = layout_vertical(
        "あ", TextStyle(font_size_px=14.0, auto_fit=False, align_h="right"), inner_w, inner_h
    )
    w = left[0]["w"]
    assert left[0]["x"] == pytest.approx(0.0, abs=0.5)
    assert right[0]["x"] == pytest.approx(inner_w - w, abs=1.5)
    assert center[0]["x"] == pytest.approx((inner_w - w) / 2.0, abs=1.5)
    assert left[0]["x"] < center[0]["x"] < right[0]["x"]
    # align_v: top at 0, bottom at inner_h - block height, middle in between.
    top = layout_vertical(
        "あああ", TextStyle(font_size_px=14.0, auto_fit=False, align_v="top"), inner_w, inner_h
    )
    middle = layout_vertical(
        "あああ", TextStyle(font_size_px=14.0, auto_fit=False, align_v="middle"), inner_w, inner_h
    )
    bottom = layout_vertical(
        "あああ", TextStyle(font_size_px=14.0, auto_fit=False, align_v="bottom"), inner_w, inner_h
    )
    block_h = top[0]["h"] * 3.0
    assert top[0]["y"] == pytest.approx(0.0, abs=0.5)
    assert bottom[0]["y"] == pytest.approx(inner_h - block_h, abs=1.5)
    assert middle[0]["y"] == pytest.approx((inner_h - block_h) / 2.0, abs=1.5)
    assert top[0]["y"] < middle[0]["y"] < bottom[0]["y"]


# ---------------------------------------------------------------------------
# Test 6 — vertical Auto-fit (column count + vertical extent, A8 floor)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_vertical_auto_fit(qapp) -> None:
    """The vertical fit loop operates on the column count (floor(inner_w /
    1 em)) and the run's vertical extent; short text GROWS above the base
    (G-07-4, capped at min(inner_w, inner_h)); a long text floors at 5 px
    like the horizontal loop (A8)."""
    # 5 CJK chars in a 200x100 box: 1 column at the 14 px base -> fits, and
    # the grow phase enlarges it above the base (capped, no overflow).
    result = layout("あ" * 5, TextStyle(), QRectF(0, 0, 200, 100), vertical=True)
    inner_w, inner_h = _inner(200, 100)
    assert result.used_font_size_px > 14.0, (
        "the vertical Auto-fit must grow short text above the 14 px base"
    )
    assert result.used_font_size_px <= min(inner_w, inner_h) + 1e-6, (
        "vertical growth is capped at min(inner_w, inner_h)"
    )
    assert result.overflow is False
    assert len(result.vertical_placements) == 5
    # 2000 chars in a 200x60 box: the bounded loop terminates and never
    # renders below the 5 px floor; the text floors (overflow reported).
    result = layout("あ" * 2000, TextStyle(), QRectF(0, 0, 200, 60), vertical=True)
    assert result.used_font_size_px >= 5.0 - 1e-6, (
        "the vertical loop must never render below the 5 px floor"
    )
    assert result.overflow is True, (
        "2000 chars cannot fit even at the floor — overflow must be reported"
    )
    assert len(result.vertical_placements) > 0


# ---------------------------------------------------------------------------
# Test 7 — code-point indexing (flagged assumption: encoding)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_vertical_code_point_indexing(qapp) -> None:
    """Text indexes by Python str code points — never bytes or UTF-16 units:
    every character (incl. a surrogate-pair CJK char) yields exactly one
    placement, in order, with no truncation."""
    style = TextStyle(font_size_px=14.0, auto_fit=False)
    # "𠮷" is ONE code point (U+20BB7) = 2 UTF-16 units — must be 1 placement.
    placements = layout_vertical("漢A𠮷字", style, 96.0, 96.0)
    assert len(placements) == 4
    assert [p["char"] for p in placements] == ["漢", "A", "𠮷", "字"]
    # Mixed multi-byte + ASCII: the ASCII char is a single placement too.
    placements = layout_vertical("日本語ABC", style, 96.0, 96.0)
    assert len(placements) == 6
    assert placements[3]["char"] == "A"


# ===========================================================================
# Owned line breaking — quick-260822-wvf Task 2 regression tests
#
# layout() pre-breaks lines via core/text_wrap (contraction/punctuation
# atoms + balancing) and renders them as explicit \n in a NoWrap document,
# on BOTH the manual and the auto-fit path. These tests inspect the laid-out
# document's line texts (platform-robust property assertions — never
# hard-coded pixel positions, per the STATE.md platform lesson).
# ===========================================================================


def _doc_line_texts(result) -> list[str]:
    """The laid-out document's per-line texts across ALL blocks (the owned
    breaker renders pre-broken lines as explicit \\n — one QTextDocument
    block each; block layout is forced by _build_document)."""
    plain = result.document.toPlainText()
    texts: list[str] = []
    block = result.document.firstBlock()
    while block.isValid():
        lo = block.layout()
        for i in range(lo.lineCount()):
            line = lo.lineAt(i)
            texts.append(plain[line.textStart() : line.textStart() + line.textLength()])
        block = block.next()
    return texts if texts else plain.split("\n")


@pytest.mark.unit
def test_layout_never_splits_contraction(qapp) -> None:
    """(a) "I can't believe it": no committed line ends in "can" or starts
    with "'t" — the contraction rides one atom (manual-size path)."""
    style = TextStyle(font_size_px=14.0, auto_fit=False)
    rect = QRectF(0, 0, 90, 120)  # narrow: forces wrapping
    for mode_style in (style, TextStyle()):  # manual AND auto-fit paths
        result = layout("I can't believe it", mode_style, rect, vertical=False)
        lines = _doc_line_texts(result)
        assert len(lines) >= 2, "narrow box must wrap"
        for line in lines:
            assert not line.rstrip().endswith("can"), (
                f"line {line!r} splits the can't contraction"
            )
            assert not line.lstrip().startswith("'t"), (
                f"line {line!r} starts with a contraction fragment"
            )


@pytest.mark.unit
def test_layout_never_splits_dont_contraction(qapp) -> None:
    """(b) "don't stop believing": same contraction contract through the
    auto-fit path — no "don" / "t"-fragment lines."""
    rect = QRectF(0, 0, 80, 100)
    result = layout("don't stop believing", TextStyle(), rect, vertical=False)
    lines = _doc_line_texts(result)
    assert len(lines) >= 2
    for line in lines:
        stripped = line.strip()
        assert not stripped.endswith("don"), f"line {line!r} splits don't"
        assert stripped not in ("t", "n't", "'t"), (
            f"line {line!r} is a contraction fragment"
        )


@pytest.mark.unit
def test_layout_never_starts_line_with_punctuation(qapp) -> None:
    """(c) "Are you free ?": the glued 'free ?' atom wraps whole — no line
    starts with '?' (both render paths)."""
    rect = QRectF(0, 0, 90, 120)
    for mode_style in (TextStyle(font_size_px=14.0, auto_fit=False), TextStyle()):
        result = layout("Are you free ?", mode_style, rect, vertical=False)
        lines = _doc_line_texts(result)
        assert len(lines) >= 2
        for line in lines:
            assert not line.lstrip().startswith("?"), (
                f"line {line!r} starts with glued punctuation"
            )


@pytest.mark.unit
def test_layout_lines_balance_no_orphan_last_line(qapp) -> None:
    """Balancing smoke: multi-word text that wraps into exactly two lines
    never leaves a one-short-word orphan last line when both words fit on
    either line — range/property-based, no pixel positions."""
    rect = QRectF(0, 0, 200, 200)
    result = layout("good grief charlie brown", TextStyle(), rect, vertical=False)
    lines = [ln.strip() for ln in _doc_line_texts(result)]
    lines = [ln for ln in lines if ln]
    if len(lines) == 2:
        first_words, last_words = lines[0].split(), lines[-1].split()
        # A balanced 2+2 split must beat a greedy 3+1 orphan.
        assert len(last_words) > 1 or len(first_words) <= 1, (
            f"orphan last line {lines!r}: balanced alternative existed"
        )


# ===========================================================================
# Multi-block geometry + hard-newline regressions (quick-260822-wvf
# follow-up): explicit \n creates one QTextDocument block per source line.
# naturalTextRect is BLOCK-LOCAL — without translating by the block's
# document offset every rect reported y=0 and ALL lines stacked/overlapped
# (bubbles rendered a single clipped line). And tokenize_atoms used to
# flatten author newlines into spaces.
# ===========================================================================


@pytest.mark.unit
def test_layout_multiblock_line_rects_do_not_stack(qapp) -> None:
    """Each hard-line renders at its own y — rects strictly increasing."""
    for style in (TextStyle(font_size_px=14.0, auto_fit=False), TextStyle()):
        result = layout("Ah!\nIt's Sukoya-san", style, QRectF(0, 0, 120, 200))
        ys = [r.y() for r in result.line_rects]
        assert len(ys) >= 2, f"expected multiple lines, got {ys}"
        assert ys == sorted(ys) and len(set(ys)) == len(ys), f"stacked: {ys}"
        # ink spans the full multi-line block (not a collapsed single line)
        assert result.ink.height() > 20


@pytest.mark.unit
def test_layout_preserves_manual_newlines(qapp) -> None:
    """Author \\n breaks are never merged away, even in a huge box where
    everything would fit on one greedy line."""
    result = layout(
        "Ah!\nIt's Sukoya-san",
        TextStyle(font_size_px=14.0, auto_fit=False),
        QRectF(0, 0, 600, 200),
    )
    assert "\n" in result.document.toPlainText()
    texts = [ln.strip() for ln in _doc_line_texts(result)]
    assert "Ah!" in texts


# ===========================================================================
# Auto-fit ordering fix (quick-260823-hge Task 2): a candidate whose owned
# break had to split a LATIN word is a FAILED FIT, not a result — the loop
# shrinks before ever accepting it. Only the 5 px floor escapes (accepting
# whatever it gets, overflow honest). Manual size keeps today's semantics.
# ===========================================================================


@pytest.mark.unit
def test_auto_fit_rejects_latin_split_shrinks_instead(qapp) -> None:
    """Narrow-box 'Herta!': the old loop accepted the char-split 'Hert'/'a!'
    layout AT the oversized base size (vertical-only fit test). The fixed
    loop treats the split candidate as not-fitting and lands on a STRICTLY
    SMALLER font where 'Herta!' sits whole (or hyphenated at worst) — never
    a dash-less mid-word split above the floor."""
    rect = QRectF(0, 0, 36, 160)  # inner_w = 32 — 'Herta!' overflows at 14 px
    result = layout("Herta!", TextStyle(), rect, vertical=False)
    # The shrink loop engaged: accepted size strictly below the 14 px base.
    assert 5.0 <= result.used_font_size_px < 14.0, (
        f"expected a shrunken font below the base, got "
        f"{result.used_font_size_px}"
    )
    texts = [ln.strip() for ln in _doc_line_texts(result) if ln.strip()]
    # No dash-less mid-word split above the floor: either the whole word on
    # one line, or a properly hyphenated prefix ending in '-'.
    assert any(t == "Herta!" or t.endswith("-") for t in texts), (
        f"'Herta!' was split without a hyphen dash: {texts!r}"
    )


@pytest.mark.unit
def test_auto_fit_floor_escapes_with_honest_overflow(qapp) -> None:
    """Text that cannot avoid splitting even at the 5 px floor still yields
    a LayoutResult (the floor deadlock escape) — never an exception or an
    empty document."""
    rect = QRectF(0, 0, 60, 60)
    text = "supercalifragilisticexpialidocious " * 6
    result = layout(text, TextStyle(), rect, vertical=False)
    assert result.used_font_size_px >= 5.0 - 1e-6, (
        "the loop must never render below the 5 px floor"
    )
    assert result.overflow is True, (
        "unavoidable Latin splits at the floor report honest overflow"
    )
    assert result.ink.height() > 0.0
    assert result.document.toPlainText().strip(), "document must not be empty"


@pytest.mark.unit
def test_manual_size_keeps_vertical_only_overflow_contract(qapp) -> None:
    """Manual-size path: author intent wins — owned breaks (hyphenated when
    needed) render at the chosen size and overflow stays VERTICALLY
    computed (the split-latin rejection applies only to the auto-fit
    predicate)."""
    style = TextStyle(font_size_px=16.0, auto_fit=False)
    rect = QRectF(0, 0, 34, 300)  # 'Herta!' cannot fit whole at 16 px
    result = layout("Herta!", style, rect, vertical=False)
    assert result.used_font_size_px == pytest.approx(16.0, abs=0.1)
    texts = [ln.strip() for ln in _doc_line_texts(result) if ln.strip()]
    assert len(texts) >= 2, "narrow manual box must wrap/hyphenate"
    _, inner_h = _inner(34, 300)
    assert result.overflow == (result.document.size().height() > inner_h + 0.5), (
        "manual overflow must remain the vertical-only honesty contract"
    )
