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

Qt-imports only (QtCore/QtGui + numpy for the bake bridge — no widget or
main-window dependencies) so the module is headless-testable under the
pytest-qt ``qapp`` fixture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
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
    outline = style.outline if isinstance(style.outline, dict) else {}
    if outline.get("enabled", True) and float(outline.get("width_px", 0.0) or 0.0) > 0:
        pen = QPen(
            _valid_color(str(outline.get("color", "#0b0b0e")), "#0b0b0e"),
            float(outline["width_px"]),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
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
# layout() — pure geometry
# ---------------------------------------------------------------------------


def layout(
    text: str, style: TextStyle, box_rect: QRectF, vertical: bool = False
) -> LayoutResult:
    """Lay out ``text`` inside ``box_rect`` per ``style`` (horizontal mode).

    The box rect is shrunk by the inner inset on every side; lines wrap at
    the inner width (engine word wrap with anywhere fallback); the engine
    applies ``align_h``; ``align_v`` offsets the block via the result's
    ``origin``. A manual size (``font_size_px`` set, ``auto_fit`` False)
    renders exactly at that size and reports ``overflow`` when the block
    exceeds the inner height. Auto-fit (the default) runs the 04-09 bounded
    loop at scene px. Empty text yields an empty result (renders nothing).

    The true tategaki vertical path lands in plan 07-03; ``vertical=True``
    currently falls back to the horizontal layout (the 07-01 default style
    is horizontal, so no production path reaches it).
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


# ---------------------------------------------------------------------------
# paint() — the shared draw path (canvas overlay AND bake)
# ---------------------------------------------------------------------------


def paint(painter: QPainter, result: LayoutResult, style: TextStyle) -> None:
    """Draw ``result`` through ``painter`` — opaque fill + outline, unclipped.

    The whole laid-out document is drawn at ``result.origin`` (the engine
    already applied wrap + horizontal alignment; the merged char format
    carries the fill and outline). No clip is ever installed (UI-SPEC A6 —
    overflow renders unclipped on both the canvas and the bake). The
    ``style`` argument keeps the plan's two-arg contract; the pixels come
    from the result's document.
    """
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.translate(result.origin)
    result.document.drawContents(painter)
    painter.restore()


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
            result = layout(text, style, QRectF(x, y, w, h), vertical=bool(style.vertical))
            paint(painter, result, style)
    finally:
        painter.end()
    return qimage_to_numpy(qimg).copy()
