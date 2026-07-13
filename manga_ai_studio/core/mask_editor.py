"""Pure mask-mutation ops + QImage/numpy conversions (D-10: core/ holds ops).

Per D-10 the Qt EVENT DISPATCH lives in ``gui/canvas.py``; this module holds
only pure functions of ``(QImage mask, tool, points, brush_size)`` so
``tests/test_mask_editor.py`` can exercise paint behavior without instantiating
any QWidget (RESEARCH Validation Architecture). The paint helpers, the eraser's
``CompositionMode_Clear`` dispatch, and the QPen ``RoundCap``/``RoundJoin``
brush stroke are reimplemented patterned after MangaCleaner_GPU
``frontend/canvas.py`` (mousePress/Move/Release dispatch + get_painter +
paint_mask_stroke/rect/lasso, lines 86-149) — reference-only per D-12 (the
MangaCleaner_GPU binary distribution carries no LICENSE, so it is
all-rights-reserved and cannot be vendored). The QImage<->RGBA conversion
shape follows PanelCleaner ``image_ops.convert_mask_to_rgba`` (GPL v3).

Buffer lifetime discipline (RESEARCH Pitfall 2; PATTERNS.md §Shared Pattern 5):
both numpy<->QImage bridges enforce ``.copy()`` so the numpy array owns its
data (``OWNDATA`` True) and the returned QImage detaches from the numpy buffer
before it is garbage-collected. MangaCleaner_GPU ``main_window.py:265-267`` is
the buggy reference (no ``.copy()``) that we explicitly do NOT copy.

Security:
    - ``clamp_brush_size`` clamps every integer that reaches a QPen width to
      ``[1, 300]`` (T-01-09 input-validation mitigation). The QSpinBox/QSlider
      in ``gui/tools_panel.py`` also enforce ``setMinimum(1)``/``setMaximum(300)``,
      making this the defense-in-depth guard.
"""

from __future__ import annotations

import enum

import numpy as np
from PySide6.QtCore import QRectF, QPointF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
)

# Mask paint content color — the rgba(255, 0, 0, 0.63) overlay (UI-SPEC §Color
# mask overlay token; 160/255 ~= 0.63). Fixed/semantic in Phase 1.
MASK_PAINT_COLOR = QColor(255, 0, 0, 160)
# Eraser "color" — used together with CompositionMode_Clear; Qt.transparent
# means "destination alpha goes to zero wherever we paint" (the erase path).
ERASER_PAINT_COLOR = Qt.GlobalColor.transparent

# Brush-size range + default (UI-SPEC surface 6: default 40px, range 1-300).
MIN_BRUSH_SIZE = 1
MAX_BRUSH_SIZE = 300
DEFAULT_BRUSH_SIZE = 40


class ToolMode(enum.Enum):
    """The 5 exclusive mask-editing tools (UI-SPEC surface 6).

    Move/Pan is the default (no painting). Brush/Rectangle/Lasso paint mask
    content; Eraser removes it. Differs from MangaCleaner_GPU's
    stringly-typed "NONE"/"BRUSH"/"RECT"/"LASSO" — we use an enum and treat
    Eraser as a first-class tool per UI-SPEC (not a Shift toggle alone).
    """

    MOVE = "move"
    BRUSH = "brush"
    RECTANGLE = "rectangle"
    LASSO = "lasso"
    ERASER = "eraser"


def clamp_brush_size(size: int) -> int:
    """Clamp ``size`` to ``[MIN_BRUSH_SIZE, MAX_BRUSH_SIZE]`` (T-01-09).

    Defense-in-depth: the QSpinBox/QSlider also enforce this range, but no
    unbounded integer may reach a QPen width (an oversized width blows up
    memory on large pages).
    """
    return max(MIN_BRUSH_SIZE, min(MAX_BRUSH_SIZE, int(size)))


def _get_painter(mask: QImage, eraser: bool) -> tuple[QPainter, QColor | Qt.GlobalColor]:
    """Build a QPainter on ``mask`` configured for paint or erase mode.

    Reimplemented patterned after MangaCleaner_GPU ``canvas.py:121-130``
    ``get_painter``. Erase uses ``CompositionMode_Clear`` (destination pixels
    become transparent where the source is drawn); paint uses SourceOver.
    """
    painter = QPainter(mask)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if eraser:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        color: QColor | Qt.GlobalColor = ERASER_PAINT_COLOR
    else:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        color = MASK_PAINT_COLOR
    return painter, color


def paint_mask_stroke(
    mask: QImage,
    p1: QPointF,
    p2: QPointF,
    brush_size: int,
    eraser: bool,
) -> None:
    """Paint a round-cap brush segment from ``p1`` to ``p2`` on ``mask``.

    ``Qt.RoundCap``/``Qt.RoundJoin`` fill the cap discs so a single click (p1
    == p2) paints a dot and consecutive segments join smoothly (UI-SPEC
    surface 6 Brush behavior). The stroke mutates ``mask`` IN PLACE.
    """
    size = clamp_brush_size(brush_size)
    painter, color = _get_painter(mask, eraser)
    painter.setPen(
        QPen(
            color,
            size,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
    )
    painter.drawLine(p1, p2)
    painter.end()


def paint_mask_rect(
    mask: QImage,
    p1: QPointF,
    p2: QPointF,
    eraser: bool,
) -> None:
    """Fill the normalized rectangle ``[p1, p2]`` into ``mask``.

    ``QRectF(p1, p2).normalized()`` handles drag-in-any-direction (the rect is
    built from the two corners regardless of which was the start). Mutates
    ``mask`` in place.
    """
    painter, color = _get_painter(mask, eraser)
    painter.fillRect(QRectF(p1, p2).normalized(), QBrush(color))
    painter.end()


def paint_mask_lasso(mask: QImage, path: QPainterPath, eraser: bool) -> None:
    """Fill the (closed) ``path`` interior into ``mask``.

    The caller is responsible for closing the path (``closeSubpath()``) before
    calling — a closed freehand lasso fills its interior; an open path fills
    the implicit closure. Mutates ``mask`` in place.
    """
    painter, color = _get_painter(mask, eraser)
    painter.fillPath(path, QBrush(color))
    painter.end()


def clear_mask(mask: QImage) -> None:
    """Reset ``mask`` to fully transparent (Edit -> Clear Mask)."""
    mask.fill(Qt.GlobalColor.transparent)


def mask_to_numpy_binary(mask: QImage) -> np.ndarray:
    """Convert ``mask`` to an ``(H, W)`` uint8 binary array (255 where painted).

    Used by plan 05's inpaint dispatch (the LaMa adapter takes an ``(H, W)``
    binary mask). The alpha channel is the mask content (painted => alpha>0);
    it is thresholded to a true binary ``0``/``255`` so the backend receives a
    crisp mask regardless of the semi-transparent paint alpha
    (``MASK_PAINT_COLOR`` uses alpha 160 ~= 0.63 for the on-canvas overlay, not
    255).

    Buffer lifetime (RESEARCH Pitfall 2; PATTERNS.md §Shared Pattern 5): the
    trailing ``.copy()`` detaches the numpy view from the QImage buffer so the
    returned array OWNS its data (``OWNDATA`` True). The regression guard
    ``test_numpy_extract_copies_buffer`` locks this.
    """
    src = mask.convertToFormat(QImage.Format.Format_RGBA8888)
    h = src.height()
    w = src.width()
    # PySide6's bits()/constBits() returns a memoryview (not the sip.voidptr
    # PyQt5 returns); materialize to bytes so numpy can consume it, then take
    # the alpha channel (index 3 in RGBA8888) as the mask content.
    arr = np.frombuffer(bytes(src.constBits()), dtype=np.uint8).reshape(h, w, 4)
    alpha = arr[:, :, 3]
    # Threshold to a true binary mask: any painted pixel (alpha>0) -> 255.
    binary = np.where(alpha > 0, np.uint8(255), np.uint8(0))
    return binary.copy().astype(np.uint8)


def numpy_binary_to_mask_qimage(arr: np.ndarray) -> QImage:
    """Convert a binary ``(H, W)`` uint8 array back to a mask QImage.

    Inverse of :func:`mask_to_numpy_binary`. Non-zero entries become the
    ``MASK_PAINT_COLOR`` (rgba(255,0,0,160)); zero entries stay transparent.
    Consumed by plan 05 to re-display masks after inpainting.

    Buffer lifetime (RESEARCH Pitfall 2): the returned ``QImage`` is
    ``.copy()``-detached so it outlives the local numpy buffer.
    """
    assert arr.dtype == np.uint8, f"expected uint8 mask, got {arr.dtype}"
    assert arr.ndim == 2, f"expected 2D mask, got {arr.ndim}D"
    h, w = arr.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    # RGBA8888 byte order: [R, G, B, A]. Red paint = R=255, A=160.
    rgba[arr > 0] = [255, 0, 0, 160]
    qimg = QImage(rgba.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
    return qimg.copy()
