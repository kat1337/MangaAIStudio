"""The shared typeset renderer (plan 07-01 Task 1) — ONE code path for the
canvas overlay AND the bake (D-01 single visual truth, RESEARCH Pattern 1).

``layout()`` produces pure geometry (wrap at the inner width, H/V alignment,
the Auto-fit bounded loop, the overflow flag); ``paint()`` draws a laid-out
result through a ``QPainter``; ``bake_typeset_page()`` composites every box's
current-focus text onto a DETACHED copy of the page image (D-02/D-04, Pitfall
2); ``current_focus_text()`` is the D-04 content rule shared with the canvas.

Mechanism notes (verified by probe on the pinned Python 3.14.2 / PySide6
6.10.1 stack):

- Text layout uses ``QTextDocument`` (plain-text only — ASVS V5: no
  rich-text rendering of OCR/translation content) with a merged
  ``QTextCharFormat``: the opaque fill rides the foreground brush (D-01) and
  the outline rides ``setTextOutline`` (Phase 4 Pattern 3 — the single clean
  API for outlined glyphs). The plan's alternative outline mechanism
  (``QPainterPath.addText`` + ``strokePath``) crashes the interpreter on
  this stack (fast-fail 0xC0000409, probed), and ``QTextLayout``'s line
  machinery access-violates before a forced document layout — the
  QTextDocument path is the production-proven Phase 4 mechanism; the
  UI-SPEC locks the LOOK (opaque fill + outline at the styled width/color),
  not the mechanism.
- The document layout is FORCED via ``documentLayout().documentSize()``
  before any block-layout reads (reading ``lineAt()`` on an un-laid-out
  block access-violates on this stack).
- Auto-fit preserves the 04-09 machinery at SCENE px (D-15 / UI-SPEC A2):
  box-adaptive base ``14 x min(w,h)/100``, ``[10,28]`` base clamp, bounded
  shrink (12 iterations x 0.9, 5 px floor checked at the loop top — no
  iteration ever renders below the floor).
- Overflow renders UNCLIPPED (UI-SPEC A6): ``paint()`` never installs a
  clip; the bake clips only at the page edge (the image's natural bound).

Vertical (tategaki) mode (plan 07-03 Task 1 — D-11, the phase's highest-
risk decision): ``layout(vertical=True)`` returns per-char placements
(upright Han/Kana/vertical-form punctuation; halfwidth ASCII 0x21..0x7E
plus the bracket/dash set rotate 90 deg clockwise — the W3C mixed
orientation). Columns stack top-to-bottom, wrap at the inner height, and
flow right-to-left (later chars at smaller x) from the box's right inner
edge; each column is 1 em wide (the max char extent in the column), gap 0;
every char is centered within its column. ``align_h`` shifts the column
BLOCK left/center/right, ``align_v`` shifts the run top/middle/bottom
along the column axis (A3). The vertical Auto-fit variant reuses the
bounded loop (12 x 0.9, 5 px floor) on the column count
(floor(inner_w / 1 em)) and the run's vertical extent. Placements are
INNER-LOCAL coordinates (0..inner_w x 0..inner_h); paint() draws them
after translating to ``result.origin``.

Future polish (CONTEXT Deferred — render-only scope): kumimoji
punctuation compression, tate-chu-yoko digit combining
(text-combine-upright), font vertical alternates, and RTL-script runs
bottom-to-top.

Qt-imports only (QtCore/QtGui + numpy for the bake bridge — no widget or
main-window dependencies) so the module is headless-testable under the
pytest-qt ``qapp`` fixture.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from loguru import logger
from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QPainter,
    QPen,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextOption,
)

from manga_ai_studio.core.text_style import TextStyle

# ---------------------------------------------------------------------------
# Auto-fit constants (plan 04-09 machinery preserved at scene px — D-15)
# ---------------------------------------------------------------------------
_OVERLAY_INSET = 2.0  # inner margin on every side of the box rect
_OVERLAY_FONT_BASE = 14.0  # scene-px base for the UI-SPEC reference box
_OVERLAY_BOX_REF_DIM = 100.0  # the reference box min dimension
_OVERLAY_FIT_MAX_ITERS = 12  # bounded shrink loop
_OVERLAY_FIT_STEP = 0.9  # per-iteration reduction factor
_OVERLAY_FIT_FLOOR_PX = 5.0  # hard floor, checked at the loop TOP
_BASE_CLAMP_MIN = 10.0  # [10, 28] base clamp (UI-SPEC A2)
_BASE_CLAMP_MAX = 28.0
_FONT_SIZE_MIN = 1.0
_FONT_SIZE_MAX = 1024.0
_EPS = 1e-6

_ALIGN_H_TO_QT = {
    "left": Qt.AlignmentFlag.AlignLeft,
    "center": Qt.AlignmentFlag.AlignHCenter,
    "right": Qt.AlignmentFlag.AlignRight,
}

# ---------------------------------------------------------------------------
# Vertical (tategaki) classification constants (D-11 — RESEARCH Pattern 2,
# Common Operation 2, verbatim). Orientation contract:
#   - Upright:  Han/Kana + vertical-form punctuation (_ALIGN_CENTER).
#   - Rotated 90 deg clockwise: halfwidth ASCII 0x21..0x7E + the
#     bracket/dash set (W3C mixed orientation).
# ---------------------------------------------------------------------------
_ASCII_ROTATE = set(chr(i) for i in range(0x21, 0x7F))
_ROTATE_EXTRA = {
    "「",
    "」",
    "『",
    "』",
    "（",
    "）",
    "《",
    "》",
    "〈",
    "〉",
    "【",
    "】",
    "—",
    "…",
    "～",
    "-",
    "(",
    ")",
}
_ALIGN_CENTER = {"。", "．", "，", "、", "·", "：", "；", "！", "？"}


def char_rotates(ch: str) -> bool:
    """True when ``ch`` must be rotated 90 deg clockwise in vertical text.

    Halfwidth ASCII (letters/digits/ASCII punctuation, 0x21..0x7E) and the
    bracket/dash/ellipsis set rotate; Han/Kana and vertical-form punctuation
    (the ``_ALIGN_CENTER`` set) stay upright. A multi-char string (or the
    space 0x20) is False.
    """
    if len(ch) != 1:
        return False
    return ch in _ASCII_ROTATE or ch in _ROTATE_EXTRA


# ---------------------------------------------------------------------------
# Effect allocation bounds (D-14 / T-07-07 — the BallonsTranslator
# EffectRasterAllocationError policy: an oversized effect surface degrades
# to no-glow with a loguru warning, never an OOM)
# ---------------------------------------------------------------------------
_EFFECT_MAX_DIMENSION = 4096  # planner-pinned max effect surface dimension
_EFFECT_MAX_PIXELS = 64_000_000  # planner-pinned pixel budget


def effect_padding(style: TextStyle) -> float:
    """The halo/shadow/outline margin around the ink (RESEARCH Pattern 3).

    ``outline half-width + max(glow radius, shadow radius) + |max offset|``
    — only enabled effects contribute (skipped effects add nothing). Callers
    (the canvas overlay's bounding rect in plan 07-05, the effect surface
    sizing here) expand the ink by this on every side so neither the canvas
    nor the bake clips the halo (Pitfall 2 guard).
    """
    pad = 0.0
    outline = style.outline if isinstance(style.outline, dict) else {}
    if outline.get("enabled", True):
        pad += float(outline.get("width_px", 0.0) or 0.0) / 2.0
    radii: list[float] = []
    offsets: list[float] = []
    glow = style.glow if isinstance(style.glow, dict) else {}
    shadow = style.shadow if isinstance(style.shadow, dict) else {}
    if glow.get("enabled", False):
        radii.append(float(glow.get("radius_px", 0.0) or 0.0))
    if shadow.get("enabled", False):
        radii.append(float(shadow.get("radius_px", 0.0) or 0.0))
        offsets.append(abs(float(shadow.get("dx", 0.0) or 0.0)))
        offsets.append(abs(float(shadow.get("dy", 0.0) or 0.0)))
    if radii:
        pad += max(radii)
    if offsets:
        pad += max(offsets)
    return pad


@dataclass
class LayoutResult:
    """Geometry of a laid-out text block (horizontal mode).

    Attributes:
        text: The laid-out plain text (the D-04 current-focus text).
        style: The style the layout ran with.
        document: The laid-out ``QTextDocument`` (formats merged — paint()
            draws it verbatim, so canvas and bake share the exact pixels).
        line_rects: Per-line natural rects in DOCUMENT coordinates (the
            engine applies the horizontal alignment).
        ink: The union of the line rects (document coordinates).
        overflow: True when the laid-out block exceeds the box INNER height
            (fixed-size text taller than the box, or the auto-fit floor
            held). Renders unclipped (UI-SPEC A6).
        used_font_size_px: The resolved font size in scene px (the manual
            size, or the auto-fit loop's final target).
        origin: Where paint() must translate to — the box rect top-left
            plus the inner inset plus the vertical-alignment offset.
        inner_size: The inner rect the layout ran against (wrap width /
            fit height).
        vertical_placements: The per-char placement form when the layout
            ran in vertical mode: ``[{char, x, y, rotate, w, h}, ...]`` in
            INNER-LOCAL coordinates (paint() draws them after translating
            to ``origin``). Empty for the horizontal path.
    """

    text: str
    style: TextStyle
    document: QTextDocument = field(default_factory=QTextDocument)
    line_rects: list = field(default_factory=list)  # list[QRectF]
    ink: QRectF = field(default_factory=QRectF)
    overflow: bool = False
    used_font_size_px: float = 0.0
    origin: QPointF = field(default_factory=QPointF)
    inner_size: QSizeF = field(default_factory=QSizeF)
    vertical_placements: list = field(default_factory=list)  # list[dict]


# ---------------------------------------------------------------------------
# D-04 current-focus rule (shared with the canvas overlay)
# ---------------------------------------------------------------------------


def current_focus_text(pb) -> str:
    """The D-04/D-10 current-focus text: translation when present, else
    recognized, else ``""`` (a box with neither renders/bakes nothing).

    Mirrors ``BoxItem._current_focus_text`` (box_item.py:720-746) — ONE rule
    shared by the canvas overlay and the bake (D-04 WYSIWYG contract).
    Defensive against a payload that is not a real ``TextBlock`` (a bare
    marker object has no ``.text`` / ``.translation`` -> empty).
    """
    payload = pb.payload
    if payload is None:
        return ""
    translation = getattr(payload, "translation", "") or ""
    if translation:
        return translation
    t = getattr(payload, "text", None)
    if t is None:
        return ""
    if isinstance(t, list):
        return "".join(str(s) for s in t).strip()
    return str(t).strip()


# ---------------------------------------------------------------------------
# Font / document helpers
# ---------------------------------------------------------------------------


def _style_font(style: TextStyle, size_px: float) -> QFont:
    """The style's font at ``size_px`` scene px (pixel-accurate for WYSIWYG)."""
    font = QFont(style.font_family)
    font.setBold(style.bold)
    font.setItalic(style.italic)
    font.setPixelSize(max(1, int(round(size_px))))
    return font


def _valid_color(value: str, default: str) -> QColor:
    """A QColor from ``value``; an invalid string falls back to ``default``."""
    color = QColor(value)
    if not color.isValid():
        color = QColor(default)
    return color


def _outline_pen(style: TextStyle) -> QPen | None:
    """The D-14 outline pen from the style, or ``None`` when disabled/zero.

    RoundCap/RoundJoin at the style's width/color (UI-SPEC outline row:
    0..10 px / default 2; width 0 = off). ``None`` -> no outline pass.
    """
    outline = style.outline if isinstance(style.outline, dict) else {}
    if not outline.get("enabled", True):
        return None
    width = float(outline.get("width_px", 0.0) or 0.0)
    if width <= 0.0:
        return None
    return QPen(
        _valid_color(str(outline.get("color", "#0b0b0e")), "#0b0b0e"),
        width,
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )


def _build_document(
    text: str, style: TextStyle, size_px: float, inner_w: float
) -> QTextDocument:
    """Lay out ``text`` as a PLAIN document at ``size_px`` wrapped at ``inner_w``.

    The merged ``QTextCharFormat`` carries the opaque fill (D-01) and the
    outline pen (Pattern 3). The document layout is FORCED before returning
    so the caller's block-layout reads are safe on this stack.
    """
    doc = QTextDocument()
    doc.setPlainText(text)  # ASVS V5: PLAIN text only — no rich-text injection
    doc.setDocumentMargin(0.0)
    doc.setTextWidth(inner_w)
    opt = QTextOption(_ALIGN_H_TO_QT.get(style.align_h, Qt.AlignmentFlag.AlignHCenter))
    opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    doc.setDefaultTextOption(opt)

    font = _style_font(style, size_px)
    fill = _valid_color(style.color, "#e8e8ea")
    fmt = QTextCharFormat()
    fmt.setFont(font)
    fmt.setForeground(QBrush(fill))
    pen = _outline_pen(style)
    if pen is not None:
        fmt.setTextOutline(pen)
    cursor = QTextCursor(doc)
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.mergeCharFormat(fmt)

    # Force the document layout before any block-layout reads (see module
    # docstring — lineAt on an un-laid-out block access-violates here).
    doc.documentLayout().documentSize()
    return doc


def _line_rects(doc: QTextDocument) -> list:
    """Per-line natural rects from the laid-out document (engine-aligned)."""
    block = doc.firstBlock()
    layout = block.layout()
    return [layout.lineAt(i).naturalTextRect() for i in range(layout.lineCount())]


# ---------------------------------------------------------------------------
# Vertical (tategaki) layout — pure geometry (D-11, RESEARCH Pattern 2)
# ---------------------------------------------------------------------------


def _vertical_placements(
    text: str, style: TextStyle, inner_w: float, inner_h: float, size_px: float
) -> tuple[list, int, float, float]:
    """Per-char vertical placements at ``size_px`` (INNER-LOCAL coords).

    Returns ``(placements, ncols, block_w, block_h)`` where placements are
    ``[{char, x, y, rotate, w, h}, ...]`` in TEXT order (the first placement
    is the first character). Geometry rules (W3C + BallonsTranslator
    conventions):

    - The char box is the natural glyph box: ``w`` = the horizontal
      advance, ``h`` = the ink rect height. Latin/ASCII boxes are taller
      than wide (h > w); CJK boxes are square (w >= h).
    - Chars stack top-to-bottom; the per-char advance is the box HEIGHT
      (Latin: measured along its height, not its width; CJK: its width
      equals the height — square).
    - A column wraps when the next char would exceed ``inner_h``.
    - Column width = the max horizontal ink extent in the column (upright:
      ``w``; rotated: ``h`` — a rotated glyph's horizontal extent is its
      natural height) — the 1 em basis.
    - Columns flow RIGHT-TO-LEFT, flush (gap 0); the block sits per
      ``align_h`` (right = the natural tategaki origin, first column at the
      right inner edge); ``align_v`` shifts the run along the column axis.
    - Every char is centered within its column.
    """
    font = _style_font(style, size_px)
    fm = QFontMetricsF(font)
    chars = list(text)  # code points — never bytes (flagged assumption)
    if not chars:
        return [], 0, 0.0, 0.0

    # Group into columns (top-to-bottom, wrap at inner_h).
    columns: list[list[dict]] = []
    cur: list[dict] = []
    col_y = 0.0
    for ch in chars:
        br = fm.boundingRect(ch)
        w = fm.horizontalAdvance(ch)
        h = br.height()  # the ink height (CJK squares the advance; Latin is taller)
        rot = char_rotates(ch)
        extent = h if rot else w  # horizontal ink extent in the column
        if cur and col_y + h > inner_h + _EPS:
            columns.append(cur)
            cur = []
            col_y = 0.0
        cur.append({"char": ch, "w": w, "h": h, "rotate": rot, "extent": extent})
        col_y += h
    if cur:
        columns.append(cur)

    col_widths = [max(c["extent"] for c in col) for col in columns]
    block_w = float(sum(col_widths))
    block_h = float(max(sum(c["h"] for c in col) for col in columns))

    if style.align_h == "left":
        dx_block = 0.0
    elif style.align_h == "right":
        dx_block = inner_w - block_w
    else:  # center (the default)
        dx_block = (inner_w - block_w) / 2.0

    if style.align_v == "top":
        dy_block = 0.0
    elif style.align_v == "bottom":
        dy_block = inner_h - block_h
    else:  # middle (the default)
        dy_block = (inner_h - block_h) / 2.0

    placements: list[dict] = []
    x = dx_block + block_w  # the block's RIGHT edge — columns flow leftward
    for col, cw in zip(columns, col_widths):
        x -= cw
        y = dy_block
        for c in col:
            placements.append(
                {
                    "char": c["char"],
                    "x": x + (cw - c["w"]) / 2.0,
                    "y": y,
                    "rotate": c["rotate"],
                    "w": c["w"],
                    "h": c["h"],
                }
            )
            y += c["h"]
    return placements, len(columns), block_w, block_h


def layout_vertical(
    text: str,
    style: TextStyle,
    inner_w: float,
    inner_h: float,
    size_px: float | None = None,
) -> list[dict]:
    """Per-char vertical placements for ``text`` inside an inner rect.

    Pure geometry (no painting — RESEARCH A1: a future document-layout
    wrapper can consume these placements): ``[{char, x, y, rotate, w, h},
    ...]`` in INNER-LOCAL coordinates. ``size_px`` is the glyph size; when
    None the style resolves it (manual size, or the vertical Auto-fit loop:
    bounded 12 x 0.9 iterations on the column count and vertical extent,
    5 px floor — the horizontal machinery applied to vertical metrics).

    Classification and column rules: see the module docstring and
    ``char_rotates``. Future polish (CONTEXT Deferred): kumimoji
    compression, tate-chu-yoko combining, RTL-script bottom-to-top flow.
    """
    if size_px is None:
        manual = style.font_size_px is not None and not style.auto_fit
        if manual:
            size_px = min(_FONT_SIZE_MAX, max(_FONT_SIZE_MIN, float(style.font_size_px)))
        else:
            size_px = _vertical_fit_size(text, style, inner_w, inner_h)
    placements, _, _, _ = _vertical_placements(text, style, inner_w, inner_h, size_px)
    return placements


def _vertical_fit_size(
    text: str, style: TextStyle, inner_w: float, inner_h: float
) -> float:
    """The vertical Auto-fit size: the bounded loop on column count.

    Fit = the layout's column count <= floor(inner_w / 1 em) AND the run's
    vertical extent fits inner_h. Same machinery as the horizontal loop:
    box-adaptive base (the box dims = the inner dims + the constant inset),
    [10,28] clamp, 12 x 0.9 iterations, 5 px floor checked at the loop TOP
    (no iteration renders below it).
    """
    box_w = inner_w + 2.0 * _OVERLAY_INSET
    box_h = inner_h + 2.0 * _OVERLAY_INSET
    base = _OVERLAY_FONT_BASE * min(box_w, box_h) / _OVERLAY_BOX_REF_DIM
    target = min(_BASE_CLAMP_MAX, max(_BASE_CLAMP_MIN, base))
    for _ in range(_OVERLAY_FIT_MAX_ITERS):
        if target <= _OVERLAY_FIT_FLOOR_PX:
            break
        _, ncols, _, block_h = _vertical_placements(text, style, inner_w, inner_h, target)
        max_cols = max(1, int(inner_w // target))
        if ncols <= max_cols and block_h <= inner_h + _EPS:
            break
        target *= _OVERLAY_FIT_STEP
    return target


# ---------------------------------------------------------------------------
# layout() — pure geometry
# ---------------------------------------------------------------------------


def layout(
    text: str, style: TextStyle, box_rect: QRectF, vertical: bool = False
) -> LayoutResult:
    """Lay out ``text`` inside ``box_rect`` per ``style``.

    Horizontal mode (the default): the box rect is shrunk by the inner
    inset on every side; lines wrap at the inner width (engine word wrap
    with anywhere fallback); the engine applies ``align_h``; ``align_v``
    offsets the block via the result's ``origin``. A manual size
    (``font_size_px`` set, ``auto_fit`` False) renders exactly at that size
    and reports ``overflow`` when the block exceeds the inner height.
    Auto-fit (the default) runs the 04-09 bounded loop at scene px.

    Vertical mode (``vertical=True`` — plan 07-03, D-11): the result
    carries ``vertical_placements`` (per-char boxes, upright CJK / rotated
    Latin, RTL columns, wrap at the inner height, per-char centering,
    align_h/align_v block shifts — see ``layout_vertical``); ``origin`` is
    the box top-left + inset and the placements are inner-local. Empty text
    yields an empty result in both modes (renders nothing).
    """
    inner_w = max(1.0, box_rect.width() - 2.0 * _OVERLAY_INSET)
    inner_h = max(1.0, box_rect.height() - 2.0 * _OVERLAY_INSET)
    inner_size = QSizeF(inner_w, inner_h)

    if not text:
        return LayoutResult(
            text=text,
            style=style,
            origin=QPointF(
                box_rect.x() + _OVERLAY_INSET, box_rect.y() + _OVERLAY_INSET
            ),
            inner_size=inner_size,
        )

    if vertical:
        return _layout_vertical_result(text, style, box_rect, inner_w, inner_h, inner_size)

    manual = style.font_size_px is not None and not style.auto_fit
    if manual:
        size = min(_FONT_SIZE_MAX, max(_FONT_SIZE_MIN, float(style.font_size_px)))
        doc = _build_document(text, style, size, inner_w)
        overflow = doc.size().height() > inner_h + _EPS
    else:
        # Auto-fit (D-15): box-adaptive base + [10,28] clamp + bounded shrink.
        base = (
            _OVERLAY_FONT_BASE
            * min(box_rect.width(), box_rect.height())
            / _OVERLAY_BOX_REF_DIM
        )
        target = min(_BASE_CLAMP_MAX, max(_BASE_CLAMP_MIN, base))
        doc = None
        size = target
        overflow = True
        for _ in range(_OVERLAY_FIT_MAX_ITERS):
            # Floor check at the loop TOP — no iteration renders below it.
            if target <= _OVERLAY_FIT_FLOOR_PX:
                break
            candidate = _build_document(text, style, target, inner_w)
            doc, size = candidate, target
            if candidate.size().height() <= inner_h + _EPS:
                overflow = False
                break
            target *= _OVERLAY_FIT_STEP

    used_size = float(max(1, int(round(size))))
    block_h = doc.size().height()
    if style.align_v == "bottom":
        dy = inner_h - block_h
    elif style.align_v == "top":
        dy = 0.0
    else:  # middle (default)
        dy = (inner_h - block_h) / 2.0

    rects = _line_rects(doc)
    ink = QRectF()
    for r in rects:
        ink = ink.united(r)

    return LayoutResult(
        text=text,
        style=style,
        document=doc,
        line_rects=rects,
        ink=ink,
        overflow=overflow,
        used_font_size_px=used_size,
        origin=QPointF(
            box_rect.x() + _OVERLAY_INSET,
            box_rect.y() + _OVERLAY_INSET + dy,
        ),
        inner_size=inner_size,
    )


def _layout_vertical_result(
    text: str,
    style: TextStyle,
    box_rect: QRectF,
    inner_w: float,
    inner_h: float,
    inner_size: QSizeF,
) -> LayoutResult:
    """The vertical (tategaki) LayoutResult — per-char placements (D-11).

    Manual size: placements at exactly that size; overflow when the column
    BLOCK exceeds the inner rect in either dimension. Auto-fit: the bounded
    loop on column count + vertical extent (``_vertical_fit_size``);
    overflow when the final candidate still does not fit (the floor held).
    """
    manual = style.font_size_px is not None and not style.auto_fit
    if manual:
        size = min(_FONT_SIZE_MAX, max(_FONT_SIZE_MIN, float(style.font_size_px)))
        placements, _, block_w, block_h = _vertical_placements(
            text, style, inner_w, inner_h, size
        )
        overflow = block_w > inner_w + _EPS or block_h > inner_h + _EPS
        used = size
    else:
        size = _vertical_fit_size(text, style, inner_w, inner_h)
        placements, ncols, block_w, block_h = _vertical_placements(
            text, style, inner_w, inner_h, size
        )
        max_cols = max(1, int(inner_w // size))
        overflow = not (ncols <= max_cols and block_h <= inner_h + _EPS)
        used = size

    ink = QRectF()
    for p in placements:
        ink = ink.united(QRectF(p["x"], p["y"], p["w"], p["h"]))
    return LayoutResult(
        text=text,
        style=style,
        ink=ink,
        overflow=overflow,
        used_font_size_px=float(max(1, int(round(used)))),
        origin=QPointF(
            box_rect.x() + _OVERLAY_INSET, box_rect.y() + _OVERLAY_INSET
        ),
        inner_size=inner_size,
        vertical_placements=placements,
    )


# ---------------------------------------------------------------------------
# paint() — the shared draw path (canvas overlay AND bake)
# ---------------------------------------------------------------------------


def paint(painter: QPainter, result: LayoutResult, style: TextStyle) -> None:
    """Draw ``result`` through ``painter`` — effect passes, then fill+outline.

    Shared by the canvas overlay and the bake (D-01, ONE code path): the
    glow + drop-shadow silhouette passes (D-14) composite BEHIND the glyphs
    (``CompositionMode_DestinationOver``) and the fill/outline pass draws on
    top. Horizontal: the laid-out document at ``result.origin`` (engine wrap
    + alignment; the merged char format carries the opaque fill and the
    outline). Vertical: the per-char placements (upright or rotated 90 deg —
    never the whole block, D-11) drawn through per-char plain documents
    with the same merged format. No clip is ever installed (UI-SPEC A6 —
    overflow renders unclipped on both the canvas and the bake). Effects
    are skipped when disabled (the default); an oversized effect surface
    degrades to no-glow with a loguru warning (T-07-07), never an OOM.
    """
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.translate(result.origin)
    _draw_effects(painter, result, style)
    _paint_fill_pass(painter, result, style)
    painter.restore()


def _paint_fill_pass(painter: QPainter, result: LayoutResult, style: TextStyle) -> None:
    """The fill + outline pass only (no effects) — horizontal or vertical.

    Also used by the effect silhouette builder, so the halo/shadow shape is
    exactly the glyph shape the main pass draws (D-01: one shared path).
    """
    if result.vertical_placements:
        _paint_vertical(painter, result, style)
    else:
        result.document.drawContents(painter)


def _paint_vertical(painter: QPainter, result: LayoutResult, style: TextStyle) -> None:
    """Per-char vertical painting (D-11).

    Each placement's glyph is drawn centered in its box; classified runs
    rotate 90 deg clockwise around the box center (per-RUN rotation — the
    W3C mixed orientation; never the whole block). The fill and outline
    ride ONE merged ``QTextCharFormat`` on a per-char PLAIN document — the
    proven Phase 4 mechanism (``QPainterPath.addText``/``QTextLayout``
    glyph paths crash this Python 3.14.2 / PySide6 6.10.1 stack — see the
    module docstring and the 07-01 deviation note).
    """
    font = _style_font(style, result.used_font_size_px)
    fill = _valid_color(style.color, "#e8e8ea")
    pen = _outline_pen(style)
    for p in result.vertical_placements:
        doc = _char_document(p["char"], font, fill, pen)
        ntr = _doc_ink_rect(doc)
        if ntr.isNull():
            continue
        painter.save()
        painter.translate(p["x"] + p["w"] / 2.0, p["y"] + p["h"] / 2.0)
        if p["rotate"]:
            painter.rotate(90.0)
        painter.translate(-ntr.center())
        doc.drawContents(painter)
        painter.restore()


def _char_document(char: str, font: QFont, fill: QColor, pen: QPen | None) -> QTextDocument:
    """A single-char PLAIN document with the merged fill/outline format.

    The vertical per-char paint path (the layout is forced before returning
    so the ink-rect read is stack-safe).
    """
    doc = QTextDocument()
    doc.setPlainText(char)  # ASVS V5: plain text only — no rich-text injection
    doc.setDocumentMargin(0.0)
    fmt = QTextCharFormat()
    fmt.setFont(font)
    fmt.setForeground(QBrush(fill))
    if pen is not None:
        fmt.setTextOutline(pen)
    cursor = QTextCursor(doc)
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.mergeCharFormat(fmt)
    doc.documentLayout().documentSize()
    return doc


def _doc_ink_rect(doc: QTextDocument) -> QRectF:
    """The first line's natural text rect — the doc-local glyph ink."""
    block = doc.firstBlock()
    layout = block.layout()
    if layout.lineCount() == 0:
        return QRectF()
    return layout.lineAt(0).naturalTextRect()


# ---------------------------------------------------------------------------
# Effect passes — glow + drop shadow (D-14, RESEARCH Pattern 3 / Common
# Operation 5): the glyph silhouette alpha -> numpy stack blur -> colorize
# x opacity -> composited BEHIND the fill (DestinationOver) inside a
# transparent offscreen surface, which is then blitted onto the target
# painter with SourceOver — glow at zero offset, shadow at the style's
# dx/dy. The intermediate surface is what makes the effects visible over
# OPAQUE targets (the bake page, test images): DestinationOver directly
# onto an opaque destination would hide the halo under it.
# ---------------------------------------------------------------------------


def _draw_effects(painter: QPainter, result: LayoutResult, style: TextStyle) -> None:
    """The glow + shadow silhouette passes (skipped when disabled).

    One shared pass for BOTH orientations (D-01): the fill pass is rendered
    into a bounded transparent offscreen surface (the glyph silhouette),
    the blurred/colorized shadow and glow images composite under it with
    DestinationOver, and the combined surface blits onto the target painter
    with SourceOver. An oversized surface degrades to no-glow with a loguru
    warning (T-07-07) instead of OOMing — the caller then draws the fill
    alone.
    """
    glow = style.glow if isinstance(style.glow, dict) else {}
    shadow = style.shadow if isinstance(style.shadow, dict) else {}
    glow_on = bool(glow.get("enabled", False)) and float(
        glow.get("radius_px", 0.0) or 0.0
    ) > 0.0
    shadow_on = bool(shadow.get("enabled", False))
    if not glow_on and not shadow_on:
        return
    ink = result.ink
    if ink.isNull() or ink.width() <= 0.0 or ink.height() <= 0.0:
        return
    pad = effect_padding(style)
    if pad <= 0.0:
        return
    rect = ink.adjusted(-pad, -pad, pad, pad)
    surface = _new_effect_surface(rect)
    if surface is None:
        w = max(1, int(math.ceil(rect.width())))
        h = max(1, int(math.ceil(rect.height())))
        logger.warning(
            "Effect surface {}x{} exceeds the bounded allocation ({} px max "
            "dimension / {} px budget) - glow/shadow skipped",
            w,
            h,
            _EFFECT_MAX_DIMENSION,
            _EFFECT_MAX_PIXELS,
        )
        return

    # 1) The glyph silhouette: the fill pass rendered into the surface
    #    (transparent background) — the SAME code path as the main paint.
    surface_painter = QPainter(surface)
    surface_painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    surface_painter.translate(-rect.left(), -rect.top())
    _paint_fill_pass(surface_painter, result, style)
    surface_painter.end()
    alpha = _qimage_argb_to_numpy(surface)[..., 3]

    # 2) Shadow + glow UNDER the fill (DestinationOver — the surface is
    #    transparent where the fill is absent, so the halo shows through).
    surface_painter = QPainter(surface)
    surface_painter.setCompositionMode(
        QPainter.CompositionMode.CompositionMode_DestinationOver
    )
    if shadow_on:
        surface_painter.drawImage(
            QPointF(
                float(shadow.get("dx", 0.0) or 0.0), float(shadow.get("dy", 0.0) or 0.0)
            ),
            _colorize_alpha(alpha, shadow),
        )
    if glow_on:
        surface_painter.drawImage(QPointF(0.0, 0.0), _colorize_alpha(alpha, glow))
    surface_painter.end()

    # 3) The combined surface over the target (SourceOver — works on opaque
    #    targets like the bake and transparent ones like the overlay cache).
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    painter.drawImage(rect.topLeft(), surface)


def _new_effect_surface(rect: QRectF) -> QImage | None:
    """A bounded transparent ARGB surface for ``rect`` (``None`` when oversized).

    The T-07-07 allocation bound: max dimension + pixel budget; beyond it
    the caller degrades to no-glow (never an OOM).
    """
    w = max(1, int(math.ceil(rect.width())))
    h = max(1, int(math.ceil(rect.height())))
    if max(w, h) > _EFFECT_MAX_DIMENSION or w * h > _EFFECT_MAX_PIXELS:
        return None
    surface = QImage(w, h, QImage.Format.Format_ARGB32)
    surface.fill(Qt.GlobalColor.transparent)
    return surface


def _colorize_alpha(alpha: np.ndarray, effect: dict) -> QImage:
    """Blur + colorize the silhouette alpha into an ARGB effect image."""
    h, w = alpha.shape
    color = _valid_color(str(effect.get("color", "#ffffff")), "#ffffff")
    opacity = float(effect.get("opacity", 1.0) or 1.0)
    radius = float(effect.get("radius_px", 0.0) or 0.0)
    blurred = _blur_alpha(alpha, radius)
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[..., 0] = color.blue()  # ARGB32 little-endian byte order: B, G, R, A
    arr[..., 1] = color.green()
    arr[..., 2] = color.red()
    arr[..., 3] = (blurred.astype(np.float32) * opacity).astype(np.uint8)
    return _numpy_rgba_to_qimage(arr)


def _blur_alpha(alpha: np.ndarray, radius_px: float) -> np.ndarray:
    """A separable numpy stack blur of the alpha channel (O(1)/px per axis).

    Three box-blur passes give a Gaussian-ish falloff; zero padding keeps
    the halo fading to transparent OUTSIDE the silhouette. Radius 0 is the
    identity (a crisp shadow — the offset > radius contract).
    """
    if radius_px <= 0.0:
        return alpha
    radius = max(1, int(round(radius_px)))
    a = alpha.astype(np.float64) / 255.0
    for _ in range(3):
        a = _box_blur_axis(a, radius, axis=1)
        a = _box_blur_axis(a, radius, axis=0)
    return (a * 255.0).astype(np.uint8)


def _box_blur_axis(a: np.ndarray, radius: int, axis: int) -> np.ndarray:
    """One box-blur pass along ``axis`` (window 2*radius+1, zero padding).

    Cumulative sums make the cost O(1) per pixel regardless of the radius
    (the BallonsTranslator stack-blur shape, numpy-reimplemented).
    """
    k = 2 * radius + 1
    moved = np.moveaxis(a, axis, 0)
    padded = np.pad(
        moved, ((radius, radius),) + ((0, 0),) * (moved.ndim - 1), mode="constant"
    )
    c = np.cumsum(padded, axis=0)
    n = moved.shape[0]
    hi = c[k - 1 : k - 1 + n]
    lo = np.zeros_like(hi)
    lo[1:] = c[0 : n - 1]
    return np.moveaxis((hi - lo) / float(k), 0, axis)


def _qimage_argb_to_numpy(qimg: QImage) -> np.ndarray:
    """An ARGB32 ``QImage`` -> a DETACHED ``(H, W, 4)`` uint8 array.

    Byte order: B, G, R, A (ARGB32 on little-endian). 32-bit scanlines are
    4-byte aligned, so no padding handling is needed; the trailing
    ``.copy()`` detaches (Pitfall 2).
    """
    img = qimg.convertToFormat(QImage.Format.Format_ARGB32)
    h, w = img.height(), img.width()
    raw = bytes(img.bits())
    arr = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 4)
    return arr.copy()


def _numpy_rgba_to_qimage(argb: np.ndarray) -> QImage:
    """A ``(H, W, 4)`` uint8 array (B, G, R, A order) -> a DETACHED ARGB32 QImage."""
    h, w = argb.shape[:2]
    qimg = QImage(argb.data, w, h, w * 4, QImage.Format.Format_ARGB32)
    return qimg.copy()  # Pitfall 2 — detach


# ---------------------------------------------------------------------------
# numpy <-> QImage bridges (Pitfall 2 — every conversion detaches)
# ---------------------------------------------------------------------------


def numpy_to_qimage(rgb: np.ndarray) -> QImage:
    """An ``(H, W, 3)`` uint8 RGB array -> a DETACHED ``QImage`` (RGB888).

    The mandatory ``.copy()`` means painting into the returned image never
    mutates the caller's array (the bake's Pitfall 2 discipline).
    """
    h, w = rgb.shape[:2]
    qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
    return qimg.copy()


def qimage_to_numpy(qimg: QImage) -> np.ndarray:
    """A ``QImage`` -> a DETACHED ``(H, W, 3)`` uint8 RGB array.

    Handles Qt's 4-byte scanline padding (the CR-08 lesson — bytesPerLine
    can exceed ``w * 3``) and detaches with a trailing ``.copy()`` so the
    array never aliases the QImage buffer.
    """
    img = qimg.convertToFormat(QImage.Format.Format_RGB888)
    h, w = img.height(), img.width()
    bytes_per_line = img.bytesPerLine()
    raw = bytes(img.bits())
    if bytes_per_line == w * 3:
        arr = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)
    else:
        strided = np.frombuffer(raw, dtype=np.uint8, count=h * bytes_per_line)
        arr = strided.reshape(h, bytes_per_line)[:, : w * 3].reshape(h, w, 3)
    return arr.copy()


# ---------------------------------------------------------------------------
# bake_typeset_page() — the D-02/D-04 compositor
# ---------------------------------------------------------------------------


def bake_typeset_page(page_np: np.ndarray, boxes: list) -> np.ndarray:
    """Composite every box's typeset text onto a DETACHED copy of the page.

    For each box in order: the D-04 current-focus text (translation else
    recognized; neither -> nothing), the flat per-box ``TextStyle`` (defaults
    when the box has none), and the same ``layout`` + ``paint`` functions the
    canvas overlay uses — canvas ≡ bake (D-01, the Pitfall 2 guard). The
    input page is never mutated: the compositor works on a detached QImage
    copy and the result detaches again (Pitfall 2).

    Args:
        page_np: The ``(H, W, 3)`` uint8 RGB page image (the current canvas
            state — same coordinate space as ``_ocr.json``).
        boxes: The page's ``PageBox`` list.

    Returns:
        A new ``(H, W, 3)`` uint8 array with the text composited at 1:1.
    """
    qimg = numpy_to_qimage(page_np).copy()  # Pitfall 2 — never the live page
    painter = QPainter(qimg)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    try:
        for pb in boxes:
            text = current_focus_text(pb)
            if not text:
                continue
            style = pb.style if pb.style is not None else TextStyle()
            x, y, w, h = pb.box.as_tuple_xywh
            # D-13: the render vertical flag = style.vertical OR payload.vertical
            # — the SAME expression box_item.refresh_text_overlay uses, so the
            # canvas and the bake flip atomically (no divergence window).
            # NOTE: the vendored TextBlock is FALSY (defines __len__), so the
            # payload presence check MUST be `is not None` — a truthiness test
            # would silently drop the flag (probed); getattr keeps a bare
            # marker payload (a string) defensive.
            vertical = bool(
                style.vertical
                or (
                    bool(getattr(pb.payload, "vertical", False))
                    if pb.payload is not None
                    else False
                )
            )
            result = layout(text, style, QRectF(x, y, w, h), vertical=vertical)
            paint(painter, result, style)
    finally:
        painter.end()
    return qimage_to_numpy(qimg).copy()
