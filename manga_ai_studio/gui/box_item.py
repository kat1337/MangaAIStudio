"""``BoxItem`` + ``CornerHandle`` — the Phase 3 text-box component layer (plan 03-03 Task 1).

This module is the UI-SPEC §12 contract made concrete: each text box on the
canvas (detected from plan 03-04 or user-created in plan 03-03 Task 2) is a
``BoxItem``. It is a ``QGraphicsRectItem`` that **composes** a plan 03-01
``PageBox`` (D-14 — does NOT subclass the vendored ``Box``) and renders an
origin-coloured border (green detected / amber user, D-09) with a selection
affordance (2px unselected / 3px selected + hue tint fill, §12c).

The four ``CornerHandle`` children (TL/TR/BL/BR, §12b) are the resize grab
targets — 8x8 viewport px via ``ItemIgnoresTransformations`` so they are a
constant grab target at any zoom, visible ONLY on the selected box (D-08
single-select). Diagonal-resize cursors (``SizeFDiagCursor`` / ``SizeBDiagCursor``)
are Qt's native diagonal-resize affordance.

Design decisions honored:

- **D-05** (``QGraphicsRectItem`` subclass): ``BoxItem`` IS-A rect item so it
  integrates with Qt's native hit-testing, selection, and move. It is NOT a
  bare ``QGraphicsRectItem`` because we need origin-coloured rendering + the
  ``PageBox`` payload + a ``current_box()`` int-materialization helper.

- **D-08** (single-select): handles are visible only on the selected box
  (handles on all boxes is clutter). Selection drives the pen width + the
  tint fill (§12c); there is no hover colour shift (Phase 1 principle: keep
  the artwork the sole saturated surface).

- **D-09** (origin colours): detected = green ``#5fd068``; user = amber
  ``#f5a623``. Two semantic surfaces separate from the accent cyan and the
  mask-overlay red (UI-SPEC §Color).

- **D-14** (anti-pattern): ``BoxItem`` COMPOSES a ``PageBox`` (which composes
  the vendored frozen ``Box``); it does NOT subclass ``Box``. The vendored
  ``Box`` is ``@frozen`` (immutable); subclassing would break the upstream
  immutability guarantee and the diffability discipline.

- **Pitfall 6** (int at the ``Box`` <-> ``QRectF`` boundary): the on-canvas
  ``QRectF`` stays float-precise for smooth dragging, but
  :meth:`BoxItem.current_box` materializes a fresh ``Box`` with ``int()``
  coords at every snapshot/persistence boundary so downstream geometry
  (``Box.__contains__``, ``QRectF`` math, persistence) never sees floats.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from PySide6 import Shiboken
from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPen,
    QPainterPath,
    QPixmap,
    QTransform,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsTextItem,
)

from manga_ai_studio.core.box_model import DETECTED, USER
from manga_ai_studio.core.text_style import TextStyle
from manga_ai_studio.gui.text_renderer import (
    LayoutResult,
    _OVERLAY_INSET,
    _normalize_rotation,
    _qimage_argb_to_numpy,
    current_focus_text,
    effect_padding,
    layout as renderer_layout,
    paint as renderer_paint,
)

if TYPE_CHECKING:
    from manga_ai_studio.core.box_model import PageBox
    from panelcleaner.structures import Box


# Origin hues (UI-SPEC §Color). Module constants so the canvas create-box
# preview pen and the status-bar copy can reuse the exact RGB tuple.
_ORIGIN_HUES: dict[str, str] = {
    DETECTED: "#5fd068",  # green — machine-detected boxes
    USER: "#f5a623",  # amber — user-drawn boxes
}
# UI-SPEC §12a: selected fill tint is rgba(hue, 0.12). QColor alpha is 0-255;
# 31/255 ~= 0.12.
_TINT_ALPHA = 31
# UI-SPEC §Spacing exceptions: unselected stroke 2px, selected 3px.
_UNSELECTED_PEN_WIDTH = 2
_SELECTED_PEN_WIDTH = 3
# Phase 8 border-state palette (UI-SPEC §Color — the border-state contract table).
# ZERO new hex values: both override-state colours reuse existing palette
# members (Text primary ``#e8e8ea`` / Text muted ``#9a9aa2``) as semantic
# surface colours, declared the same way Phase 1 declared the mask red.
_INPAINT_FORCED_HEX = "#e8e8ea"  # near-white — "Always" (promoted)
_INPAINT_NEVER_HEX = "#9a9aa2"  # muted grey — "Never" (demoted)
# The three override states that REPLACE the origin hue with a grey (reading rule
# 2: hue = who decided; overrides are user decisions). The auto-gate states
# (will_inpaint/will_fill/gate_skipped) keep the origin hue. 08.1 adds
# forced_fill vs forced_inpaint distinction but keeps ZERO new hex — both map
# to the same near-white #e8e8ea (forced variants solid grey, never dashed).
_INPAINT_GREY_STATES = frozenset({"forced", "forced_fill", "forced_inpaint", "never"})
# 6/4 scene px dash (UI-SPEC §Spacing/§Color): dash lengths ~3x the 2px stroke
# so the pattern reads as a dash (not dots, not mush) at 100% zoom; scene units
# match how the Phase 3 border scales with zoom (the border-state high-DPI note).
_INPAINT_DASH_PATTERN = [6.0, 4.0]
# The two states that render DASHED ("C won't inpaint this box's detected
# text" — reading rule 1 encodes the outcome in pattern, never hue alone).
_INPAINT_DASHED_STATES = frozenset({"gate_skipped", "never"})
# UI-SPEC §Spacing exceptions: 8x8 viewport-px corner handle.
_HANDLE_SIZE = 8
# Invisible hit-area enlargement (UAT test 2 gap-closure, plan 03-06). The VISIBLE
# handle stays 8x8 (UI-SPEC §12b); only the invisible grab tolerance grows so a
# corner drag registers even when the click lands slightly off the exact corner
# on real artwork at production zoom. 18 gives a 9px radius (> the +-5px probe in
# the regression test) within the fix_direction's "~16-20px" range.
_HANDLE_HIT_SIZE = 18
# Handle z (above the box border z=100 — UI-SPEC §Z-order).
_HANDLE_Z = 150
# Phase 4 display-object z-order (UI-SPEC §Z-order, RESEARCH Pitfall 7). The
# overlay (z=120) sits inside the box; the badge (z=140) sits TL-outside; both
# stay below the handles (z=150) so a corner drag is never visually blocked.
_TEXT_OVERLAY_Z = 120
_BADGE_Z = 140
# Text-overlay style (UI-SPEC §Color text-overlay): the hardcoded Phase 4
# translucent look (fill rgba(232,232,234,0.85) + fixed 2px outline +
# Liberation Sans 14) is SUPERSEDED by the per-box ``TextStyle`` defaults
# (D-01 — surface 34 replaces surface 16; the values now live in
# core/text_style.py). The remaining constants are the plan 04-09 Auto-fit
# machinery (D-15), kept here as the contract record: the executable bounded
# loop moved to gui/text_renderer.py (plan 07-01 Task 1), whose copies MUST
# match these (D-01 single visual truth).
_OVERLAY_FONT_BASE = 14.0
_OVERLAY_BOX_REF_DIM = 100.0
_OVERLAY_FIT_MAX_ITERS = 12
_OVERLAY_FIT_STEP = 0.9
_OVERLAY_FIT_FLOOR_VP = 5.0
# Inner margin: text inset by the renderer's constant (imported from
# text_renderer — the single home) so the canvas overlay sits exactly where
# the bake paints (D-01).
_OVERLAY_INSET = _OVERLAY_INSET
# Bubble-badge style + geometry (UI-SPEC §17). The badge is DIGIT-SIZED (plan
# 04-10, gap closure round 3): refresh_badge measures the digit glyph line box
# after setPlainText (document margin 0; probed 16x19 px per digit at the 12pt
# semibold Liberation Sans badge font) and resizes the rect to
# digit_w + 2*_BADGE_PAD_W by digit_h + 2*_BADGE_PAD_H, so the badge always
# hugs its number (single digit ~24x23, two digits 40x23, three 56x23, four
# 72x23 viewport px). 12px semibold digit; badge fill near-opaque black so the
# digit reads against any artwork.
_BADGE_PAD_W = 4.0
_BADGE_PAD_H = 2.0
_BADGE_FILL = QColor.fromRgbF(0.0, 0.0, 0.0, 0.72)
_BADGE_DIGIT_COLOR = QColor("#e8e8ea")
_BADGE_OUTLINE_AUTO = QPen(QColor("#0b0b0e"), 2)  # matte — auto-numbered badge
_BADGE_OUTLINE_OVERRIDE = QPen(QColor("#f5a623"), 2)  # amber — manual override (D-16)
_BADGE_DIGIT_FONT = QFont("Liberation Sans", 12)
_BADGE_DIGIT_FONT.setBold(True)  # semibold weight (UI-SPEC §Typography exception)
# Badge offset from the TL corner: -badge_w-2, -badge_h-2 (UI-SPEC §17 — sits in
# the outside-northwest diagonal so it never overlaps the TL handle hit area).
_BADGE_OFFSET = 2.0
# Handle outline 1px matte (#0b0b0e) separates the handle fill from artwork.
_HANDLE_OUTLINE = QColor("#0b0b0e")
# Corner handle is centred on the corner: shift by -size/2 in both axes.
_HANDLE_OFFSET = _HANDLE_SIZE / 2.0

# quick-260822-gnq: the per-box "re-run detection" affordance (the stale-marker
# corner button). Built exactly like a CornerHandle — an ItemIgnoresTransformations
# child with a fixed viewport-px size (10x10, comparable to the 8x8 handles) at
# z=160 (above the handles' z=150 so it is never visually buried) — but amber
# (#f5a623, the user-origin hue family) with a tooltip instead of resize
# cursors: clicking it re-fits the box + re-runs OCR at its CURRENT geometry.
_REDETECT_SIZE = 10
_REDETECT_Z = 160
# Sits OUTSIDE the top-right corner (2px gap) so it never overlaps the TR
# resize handle's hit area (the badge's TL-outside precedent).
_REDETECT_OFFSET = 2.0

# quick-260824-viq: the free-angle text-rotation grab handle. Built exactly
# like a RedetectHandle — an ItemIgnoresTransformations child with a fixed
# 10x10 viewport-px circle at z=155 (above the CornerHandles' z=150, below
# the RedetectHandle's z=160) — but placed ABOVE the TOP-LEFT corner: its
# CENTER sits 18 px above parent_rect.top(), clearly separated from the TL
# CornerHandle's ~9px-radius zoom-divided hit zone (quick-260824-t64).
_ROTATE_SIZE = 10
_ROTATE_Z = 155
_ROTATE_ABOVE_TL = 18.0


class RedetectHandle(QGraphicsEllipseItem):
    """The circular "re-run detection" affordance of a geometry-stale box.

    Shown ONLY while the parent :class:`BoxItem` is marked ``geometry_stale``
    (a committed move/resize/create that has not yet been re-fitted). The
    affordance owns its left-click: ``mousePressEvent`` accepts the event and
    invokes ``activate_callback`` — wired by the canvas to
    ``EditorCanvas.box_redetect_requested`` carrying the parent BoxItem — so
    MainWindow subscribes ONCE to the canvas signal, never to per-item
    objects.

    Like :class:`CornerHandle` this is a VISUAL-ONLY overlay from the canvas
    hit-test's perspective: ``EditorCanvas._box_item_at`` only matches
    ``CornerHandle`` / ``BoxItem`` instances, so this child never arms a
    move/resize; its press reaches it through the view's fall-through path.
    """

    def __init__(self, parent: "BoxItem") -> None:
        super().__init__(0.0, 0.0, float(_REDETECT_SIZE), float(_REDETECT_SIZE), parent)
        # Constant screen size at any zoom (the CornerHandle pattern).
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True
        )
        self.setZValue(_REDETECT_Z)
        # Amber fill (user-origin hue family) + 1px matte outline for
        # separation from artwork behind it.
        self.setBrush(QBrush(QColor("#f5a623")))
        self.setPen(QPen(_HANDLE_OUTLINE, 1))
        self.setToolTip("Re-run detection (box moved)")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Hidden until the parent is marked geometry-stale.
        self.setVisible(False)
        # Callable[[], None] installed by the canvas (weak-coupling seam — the
        # item never references EditorCanvas directly).
        self.activate_callback = None

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt API casing)
        """Accept a left-click and fire the activate callback (re-run request)."""
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.activate_callback is not None
        ):
            event.accept()
            self.activate_callback()
            return
        super().mousePressEvent(event)

    def reposition(self, parent_rect: QRectF) -> None:
        """Place the affordance just OUTSIDE the parent rect's top-right corner.

        Ignores-transformations child: ``pos()`` is in scene coords (the
        CornerHandle reposition precedent). The 2px-outside placement keeps
        the TR resize handle's hit area clear.
        """
        self.setPos(
            parent_rect.right() + _REDETECT_OFFSET,
            parent_rect.top() - _REDETECT_SIZE - _REDETECT_OFFSET,
        )


class RotationHandle(QGraphicsEllipseItem):
    """The circular free-angle text-rotation grab handle (quick-260824-viq).

    Shown ONLY while the parent :class:`BoxItem` is selected AND primary
    (the same rule as the corner handles — the multi-select affordance).
    The handle owns its left-press: ``mousePressEvent`` accepts the event
    and invokes ``activate_callback(parent_item, scene_pos)`` — installed by
    the canvas to arm its rotate-drag state machine — so MainWindow never
    subscribes to per-item objects.

    Like :class:`RedetectHandle` this is a VISUAL-ONLY overlay from the
    canvas hit-test's perspective: ``EditorCanvas._box_item_at`` matches only
    ``CornerHandle`` / ``BoxItem``, so this child never arms a move/resize;
    its press reaches it through the view's fall-through path.
    """

    def __init__(self, parent: "BoxItem") -> None:
        super().__init__(0.0, 0.0, float(_ROTATE_SIZE), float(_ROTATE_SIZE), parent)
        # Constant screen size at any zoom (the CornerHandle pattern).
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True
        )
        self.setZValue(_ROTATE_Z)
        # Origin-hue fill + 1px matte outline for separation from artwork.
        self.setBrush(QBrush(QColor(origin_hue(parent.pagebox.origin))))
        self.setPen(QPen(_HANDLE_OUTLINE, 1))
        self.setToolTip("Rotate text")
        # SizeAll reads as "drag to transform" without implying resize.
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        # Hidden until the parent box is selected (+primary).
        self.setVisible(False)
        # Callable[(BoxItem, QPointF), None] installed by the canvas (the
        # weak-coupling seam — the item never references EditorCanvas).
        self.activate_callback = None

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt API casing)
        """Accept a left-click and fire the activate callback (arm rotation)."""
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.activate_callback is not None
        ):
            event.accept()
            self.activate_callback(self.parentItem(), event.scenePos())
            return
        super().mousePressEvent(event)

    def reposition(self, parent_rect: QRectF) -> None:
        """Place the handle's CENTER 18 px ABOVE the parent rect's top-left.

        Ignores-transformations child: ``pos()`` is in scene coords. The
        above-the-corner placement keeps it clear of the TL CornerHandle's
        ~9px-radius hit zone and of the TL-outside bubble badge.
        """
        half = _ROTATE_SIZE / 2.0
        self.setPos(
            parent_rect.left() - half,
            parent_rect.top() - _ROTATE_ABOVE_TL - half,
        )


def origin_hue(origin: str) -> str:
    """Return the hex hue for a box origin (``#5fd068`` detected / ``#f5a623`` user).

    Falls back to the detected hue for an unknown origin (defensive — the
    D-03 origin constants are the only valid values in Phase 3).
    """
    return _ORIGIN_HUES.get(origin, _ORIGIN_HUES[DETECTED])


# Half of the enlarged hit size (corner of the handle = local (4,4); the hit
# rect is centred on that point, so the local top-left is 4 - half). Kept for
# API compatibility — the live math lives in _handle_hit_rect(zoom) since
# quick-260824-t64 Task 2 (the zoom-divided hit rect).
_HANDLE_HIT_HALF = _HANDLE_HIT_SIZE / 2.0


def _handle_hit_rect(zoom: float = 1.0) -> QRectF:
    """The enlarged invisible hit rect for a :class:`CornerHandle` (local coords).

    Centred on the corner point at local ``(4, 4)`` (the handle is constructed
    as ``QGraphicsRectItem(0,0,8,8)``; local ``(4,4)`` maps to the exact scene
    corner after :meth:`CornerHandle.reposition` sets ``pos = scene corner - 4``).

    quick-260824-t64 Task 2: ``zoom`` divides the hit size so the zone stays
    constant in VIEWPORT px. The canvas hit-test queries
    ``items(scene_pos, ..., QTransform())`` with an IDENTITY transform, so an
    un-divided 18-unit rect was 18 SCENE px — only ~4.5 screen px at 25% zoom.
    A ``max(4.0, ...)`` floor keeps a sane minimum scene-px extent at extreme
    zoom-in; ``zoom=1.0`` (the default) reduces exactly to today's 18-unit rect.
    """
    if not isinstance(zoom, (int, float)) or zoom <= 0:
        zoom = 1.0
    half = max(4.0, _HANDLE_HIT_SIZE / zoom) / 2.0
    return QRectF(
        _HANDLE_OFFSET - half,
        _HANDLE_OFFSET - half,
        half * 2.0,
        half * 2.0,
    )


def _handle_hit_path(zoom: float = 1.0) -> QPainterPath:
    """A :class:`QPainterPath` wrapping :func:`_handle_hit_rect` (for ``shape()``)."""
    path = QPainterPath()
    path.addRect(_handle_hit_rect(zoom))
    return path


class CornerHandle(QGraphicsRectItem):
    """One of the four corner resize handles of a :class:`BoxItem` (UI-SPEC §12b).

    An 8x8 viewport-px square (``ItemIgnoresTransformations``) at z=150, a
    child of its parent ``BoxItem``. Fill is the parent's origin hue; outline
    is 1px ``#0b0b0e`` (matte) for separation from artwork behind it. Cursor
    over a TL/BR handle is ``SizeFDiagCursor``; over TR/BL is
    ``SizeBDiagCursor`` (Qt's native diagonal-resize cursors).

    Because ``ItemIgnoresTransformations`` is set, the handle's position is in
    SCENE coordinates (it does not inherit the parent's transform the way a
    normal child item does). :meth:`reposition` recomputes the scene-space
    position whenever the parent box's geometry changes or the canvas zoom
    changes (handled by the canvas subscribing to its ``zoom_changed`` signal).
    """

    def __init__(self, corner: str, parent: "BoxItem") -> None:
        super().__init__(0, 0, _HANDLE_SIZE, _HANDLE_SIZE, parent)
        self.corner = corner
        # Constant screen size at any zoom (UI-SPEC §Spacing exceptions).
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True
        )
        # Above the box border (z=100); explicit so child z stacks correctly.
        self.setZValue(_HANDLE_Z)
        # Solid hue fill + 1px matte outline (UI-SPEC §12b).
        hue = origin_hue(parent.pagebox.origin)
        self.setBrush(QBrush(QColor(hue)))
        self.setPen(QPen(_HANDLE_OUTLINE, 1))
        # Diagonal-resize cursor by corner (UI-SPEC §12b).
        if corner in ("TL", "BR"):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:  # TR / BL
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        # Hidden until the parent is selected (D-08). BoxItem._sync_handles
        # toggles this on selection change.
        self.setVisible(False)
        # quick-260824-t64 Task 2: the zoom the hit rect is divided by. The
        # canvas hit-test uses an IDENTITY transform, so the hit rect is in
        # SCENE units; dividing by the live zoom keeps the grab zone constant
        # in VIEWPORT px (~18 screen px at any zoom). Construction-time 1.0
        # matches the pre-first-signal state (zoom-1.0 behavior preserved).
        self._hit_zoom = 1.0

    def set_hit_zoom(self, zoom: float) -> None:
        """Set the zoom the invisible hit rect compensates for (quick-260824-t64).

        Guards non-positive to 1.0 (the division-safety precedent of
        ``BoxItem.apply_overlay_zoom``). ``prepareGeometryChange()`` MUST run
        because ``shape()`` / ``boundingRect()`` outputs depend on the stored
        zoom — without it the scene's stale BSP index keeps the OLD rect
        hittable after a zoom change.
        """
        if not isinstance(zoom, (int, float)) or zoom <= 0:
            zoom = 1.0
        if zoom == self._hit_zoom:
            return
        self.prepareGeometryChange()
        self._hit_zoom = float(zoom)

    def reposition(self, parent_rect: QRectF) -> None:
        """Centre this handle on its matching corner of ``parent_rect``.

        ``parent_rect`` is the parent ``BoxItem``'s scene-space rect. Because
        the handle ignores transformations, its ``pos()`` is in scene coords,
        so we place it directly at the scene-space corner (minus the half-size
        offset so the 8x8 square is centred on the corner point).
        """
        if self.corner == "TL":
            self.setPos(parent_rect.left() - _HANDLE_OFFSET, parent_rect.top() - _HANDLE_OFFSET)
        elif self.corner == "TR":
            self.setPos(parent_rect.right() - _HANDLE_OFFSET, parent_rect.top() - _HANDLE_OFFSET)
        elif self.corner == "BL":
            self.setPos(parent_rect.left() - _HANDLE_OFFSET, parent_rect.bottom() - _HANDLE_OFFSET)
        else:  # BR
            self.setPos(parent_rect.right() - _HANDLE_OFFSET, parent_rect.bottom() - _HANDLE_OFFSET)

    def shape(self) -> QPainterPath:  # noqa: D401 (Qt API casing)
        """Return a LARGER invisible hit rect than the painted 8x8 handle.

        ``QGraphicsScene.itemAt`` uses each item's ``shape()`` (a
        :class:`QPainterPath`) for the FINE hit-test, and its
        :meth:`boundingRect` for the COARSE first pass (the scene's BSP index
        only considers items whose ``boundingRect`` contains the probe point).
        The default ``QGraphicsRectItem.shape()`` returns the 8x8 painted rect
        plus the pen width, which on real artwork at production zoom is
        practically unhittable (UAT test 2): the handle is centred ON the box
        corner, so ~half of the 8x8 sits outside the box (reads as
        background/pixmap -> no-op) and the inner half overlaps the
        :class:`BoxItem` body (-> triggers a move, not a resize). ``itemAt``
        therefore returns a ``CornerHandle`` only in a ~6x6 central pocket.

        Overriding ``shape()`` to return a larger rect enlarges ONLY the hit
        area — :meth:`paint` (inherited from ``QGraphicsRectItem``) draws
        ``rect()`` (the 8x8 set in ``__init__``), NOT ``shape()`` /
        :meth:`boundingRect`, so the VISIBLE handle stays 8x8 (UI-SPEC §12b
        preserved). :meth:`boundingRect` is overridden identically because
        ``itemAt`` consults ``shape()`` ONLY for items that survived the
        ``boundingRect`` coarse pass — enlarging ``shape()`` alone has no effect
        (the probe point is filtered out before the fine test runs). The corner
        POINT of the handle is at LOCAL coord ``(4, 4)`` — the handle is
        constructed as ``QGraphicsRectItem(0,0,8,8)`` and positioned via
        :meth:`reposition` so its local origin sits at ``scene corner - 4``;
        local ``(4, 4)`` therefore maps to the exact scene corner. The hit rect
        is centred on that point.

        This is the standard Qt Graphics View technique for "fat finger" grab
        targets and is localised entirely to the handle — the canvas hit-test
        dispatch (``canvas.py:859-864``) is already correct in scene coords and
        is NOT changed; it merely consults the larger ``shape()`` via
        ``scene.itemAt``. Since quick-260824-t64 Task 2 the rect is divided by
        the live zoom (``_hit_zoom``, propagated by
        ``BoxItem.apply_overlay_zoom``) so its effective viewport-px size stays
        constant (~18 screen px at any zoom).
        """
        return _handle_hit_path(self._hit_zoom)

    def boundingRect(self) -> QRectF:  # noqa: D401 (Qt API casing)
        """Return the enlarged hit rect (matches :meth:`shape`).

        ``itemAt`` only fine-tests ``shape()`` for items whose ``boundingRect``
        already contains the probe point, so ``boundingRect`` MUST cover the
        same region as ``shape()`` or the coarse pass filters the probe out
        before ``shape()`` is consulted (verified by probe — see SUMMARY
        Deviation 1). This does NOT change the painted handle: the inherited
        :meth:`paint` draws ``rect()`` (the 8x8 from ``__init__``), not
        ``boundingRect``; the larger rect only widens the scene's repaint +
        hit-test region. Both methods use the SAME zoom-divided rect so the
        coarse and fine passes stay identical at every zoom level.
        """
        return _handle_hit_rect(self._hit_zoom)



def _measure_margin(font_px: float | None) -> int:
    """The scratch-surface safety margin S (quick-260826-09m).

    ``S = max(64, ceil(effective font px))`` — comfortably larger than any
    font-metric overshoot of the QTextDocument-derived ink rect (measured:
    ~10px above ``ink.top()`` for Mango AND Arial at 100px; tall display
    fonts visibly so). Combined with the caller's ``pad`` (the full effect
    padding), the scratch always has room for the TRUE painted extent.
    ``font_px`` is the LayoutResult's auto-fit-resolved
    ``used_font_size_px`` — already capped at 1024 upstream
    (quick-260825-wfy), bounding worst-case scratch size (T-Q09M-01).
    """
    if font_px is None or font_px <= 0.0:
        return 64
    return max(64, math.ceil(float(font_px)))


def _measured_bbox(qimg: QImage) -> tuple[int, int, int, int] | None:
    """The TRUE painted bounding box ``(bx, by, bw, bh)`` of an ARGB image.

    Measures the ALPHA channel (>0) through the renderer's shared numpy
    bridge (:func:`_qimage_argb_to_numpy` — reused, never a hand-rolled
    scan). Returns ``None`` when the surface is fully transparent.
    """
    alpha = _qimage_argb_to_numpy(qimg)[..., 3]
    ys, xs = np.nonzero(alpha > 0)
    if ys.size == 0:
        return None
    bx, by = int(xs.min()), int(ys.min())
    return bx, by, int(xs.max()) - bx + 1, int(ys.max()) - by + 1


class TypesetOverlayItem(QGraphicsItem):
    """The renderer-driven OPAQUE typeset overlay child (D-01, plan 07-01 Task 2).

    Replaces the Phase 4 translucent ``QGraphicsTextItem`` overlay (UI-SPEC
    surface 34 supersedes surface 16). The render output is a cached
    ``QPixmap`` produced by ``gui/text_renderer.layout`` + ``paint`` — the
    SAME functions the bake compositor uses, so the canvas ≡ bake (D-01
    single visual truth; the equivalence pixel test is the Pitfall 2 guard).

    The cache is re-rendered on text/style/box-size changes (via
    :meth:`set_content` from ``BoxItem.refresh_text_overlay``); a reposition
    is setPos-ONLY (:meth:`refresh_position` — the RC-1 discipline: the
    canvas calls ``_sync_handles`` on EVERY mousemove during a drag, so a
    full re-layout per mousemove is prohibited).

    The pixmap covers the MEASURED painted extent (quick-260826-09m): the
    render runs into an oversized scratch surface, the scratch's alpha
    channel is measured for the true glyph bounding box (fonts overshoot
    the QTextDocument-derived ink rect — Mango ~10px above ``ink.top()``
    at 100px), and the pixmap is cropped to that box. ``set_content``
    performs up to TWO renders per content change (a defensive retry with
    a doubled safety margin if the measurement ever touches the scratch
    border) — acceptable, because it runs only on text/style/box-size
    changes, never per-mousemove (RC-1). The item's position derives from
    the MEASURED box so placement stays pixel-equivalent to the bake
    (:meth:`refresh_position`).
    """

    def __init__(self, parent: "BoxItem") -> None:
        super().__init__(parent)
        self.setZValue(_TEXT_OVERLAY_Z)
        self._pixmap: QPixmap | None = None
        self.layout_result: LayoutResult | None = None
        # The padded ink top-left in inner-rect coordinates (used by the
        # setPos-only refresh_position). Since plan 07-08 (G-07-5) it also
        # carries the align_v dy (the box-relative origin delta), so the
        # setPos-only reposition rides the dy through every move/resize/zoom
        # without a re-layout (RC-1).
        self._ink_offset = QPointF(0.0, 0.0)
        # quick-260824-viq: the box-top-left-relative overlay position for a
        # ROTATED render (``None`` = the unrotated ``_ink_offset`` path — the
        # legacy code path must stay byte-identical at rotation 0).
        self._render_offset: QPointF | None = None
        # quick-260825-wfy: the rotation_deg currently baked INTO the cached
        # pixmap (set by the rotated branch of set_content). The live-drag
        # preview applies (live - baked) so an ALREADY-ROTATED box tracks
        # the mouse instead of double-rotating.
        self._baked_rotation: float = 0.0

    # ------------------------------------------------------------ geometry
    def boundingRect(self) -> QRectF:  # noqa: D401 (Qt API casing)
        """The cached pixmap rect (a 1x1 placeholder before the first render).

        quick-260825-wfy: during a rotation preview the item transform is
        non-identity, so the rect grows to cover the ROTATED extents (the
        base rect mapped through the same rotate-about-origin transform) —
        Qt culls repaints to boundingRect and would otherwise chop the
        previewed glyphs along straight edges. At rotation 0 this returns
        the base rect unchanged (legacy path byte-identical).
        """
        if self._pixmap is None:
            return QRectF(0.0, 0.0, 1.0, 1.0)
        base = QRectF(QPointF(0.0, 0.0), QSizeF(self._pixmap.size()))
        if abs(self.rotation()) <= 1e-6:
            return base
        origin = self.transformOriginPoint()
        t = QTransform()
        t.translate(origin.x(), origin.y())
        t.rotate(self.rotation())
        t.translate(-origin.x(), -origin.y())
        return t.mapRect(base).normalized()

    def paint(self, painter, option, widget=None) -> None:  # noqa: D401
        """Blit the cached pixmap (opaque glyphs composite over the page).

        Plan 07-06 (G-07-6): belt-and-suspenders guard behind the canvas
        graveyard (the load-bearing fix). If a paint is ever dispatched to a
        wrapper whose C++ object is gone (a teardown race that the graveyard
        makes unreachable), this no-ops BEFORE touching ``self._pixmap`` —
        a stale draw from a freed pixmap is the 0xC0000409 crash line.
        """
        if not Shiboken.isValid(self):
            return
        if self._pixmap is not None:
            painter.drawPixmap(QPointF(0.0, 0.0), self._pixmap)

    # ------------------------------------------------------------ content
    def text(self) -> str:
        """The currently rendered current-focus text (``""`` when hidden).

        API-compatible probe for the old ``QGraphicsTextItem.toPlainText()``
        so the D-04 content-rule tests keep their shape.
        """
        if self.layout_result is None:
            return ""
        return self.layout_result.text

    def pixmap(self) -> QPixmap | None:
        """The cached render pixmap (``None`` when nothing is rendered)."""
        return self._pixmap

    def set_content(
        self, text: str, style: TextStyle, box_rect: QRectF, vertical: bool = False
    ) -> None:
        """(Re)render the cached pixmap through the shared renderer.

        ``box_rect`` is the FULL box rect — the renderer applies its own
        inner inset, identical for the canvas and the bake (D-01). Empty
        text clears the cache (nothing renders).

        Plan 07-05 (D-14): the pixmap pads the ink by the renderer's FULL
        effect padding (``effect_padding`` — outline half-width + glow/
        shadow radii + offsets) so enabled effect halos never clip on the
        canvas (the 07-03 handoff: the bake never clips, the canvas now
        matches it — D-01 canvas ≡ bake).

        quick-260826-09m: the surface is now sized by MEASUREMENT, not
        analytically — pass 1 paints into an oversized scratch exactly as
        today's transform math dictates, pass 2 crops to the TRUE painted
        bounding box measured from the scratch alpha channel and derives
        ``_ink_offset`` from that box. Fonts whose glyphs overshoot the
        QTextDocument-derived ink rect (Mango) no longer clip. Up to two
        renders per content change (retry with doubled margin) — content
        changes only, never per-mousemove (RC-1).
        """
        if not text:
            self._pixmap = None
            self.layout_result = None
            self._ink_offset = QPointF(0.0, 0.0)
            self._render_offset = None
            self._baked_rotation = 0.0
            self.update()
            return
        result = renderer_layout(text, style, box_rect, vertical=vertical)
        self.layout_result = result
        pad = effect_padding(style)
        # quick-260824-viq (d): a rotated style renders through the dedicated
        # rotated-surface path (the UNROTATED path below must stay
        # byte-identical at rotation 0 — no refactor of its math).
        angle = _normalize_rotation(getattr(style, "rotation_deg", 0.0))
        if abs(angle) > 1e-6:
            self._render_rotated(result, style, box_rect, angle, pad)
            # quick-260825-wfy: the angle is now baked INTO the pixmap —
            # the live preview applies (live - this) as the delta.
            self._baked_rotation = angle
            return
        self._render_offset = None
        # Straight-through (unrotated) path: nothing is baked into the
        # pixmap — reset the tracker so a rotated->unrotated re-render can
        # never leave a stale bake behind.
        self._baked_rotation = 0.0
        ink = result.ink
        # quick-260826-09m TWO-PASS MEASURED RENDER (unrotated path): the
        # analytic ``ink + 2*pad`` surface chopped glyph overshoot for fonts
        # whose paint exceeds the QTextDocument-derived rect. Pass 1 paints
        # into a scratch inflated by the safety margin S on every side; the
        # cancel-translate keeps its exact form, only shifted by S.
        base_w = max(1, math.ceil(ink.width() + 2.0 * pad))
        base_h = max(1, math.ceil(ink.height() + 2.0 * pad))
        margin = _measure_margin(result.used_font_size_px)
        scratch = QImage(
            base_w + 2 * margin, base_h + 2 * margin,
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        scratch.fill(Qt.GlobalColor.transparent)
        painter = QPainter(scratch)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # CR-01 (07-REVIEW): ``renderer_paint`` translates by ``result.origin``
        # (the box top-left + the inner inset) ITSELF, so the pixmap painter
        # must CANCEL that translate (net zero) — otherwise the ink lands at
        # pixmap-local ``(origin.x + pad, origin.y + pad)`` inside a pixmap
        # sized to the ink rect: blank (or clipped) for any box at a non-zero
        # position (D-01 canvas ≡ bake). The S shift recentres the analytic
        # window inside the scratch; measurement below replaces it wholesale.
        painter.translate(
            -result.origin.x() - ink.left() + pad + margin,
            -result.origin.y() - ink.top() + pad + margin,
        )
        renderer_paint(painter, result, style)
        painter.end()
        bbox = _measured_bbox(scratch)
        if bbox is not None and (
            bbox[0] == 0
            or bbox[1] == 0
            or bbox[0] + bbox[2] == scratch.width()
            or bbox[1] + bbox[3] == scratch.height()
        ):
            # Defensive retry: the measured paint touches the scratch border
            # — redo pass 1 ONCE with S doubled (should never trigger with
            # adequate S). No logging; just do it.
            s = margin * 2
            scratch = QImage(
                base_w + 2 * s, base_h + 2 * s,
                QImage.Format.Format_ARGB32_Premultiplied,
            )
            scratch.fill(Qt.GlobalColor.transparent)
            painter = QPainter(scratch)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.translate(
                -result.origin.x() - ink.left() + pad + s,
                -result.origin.y() - ink.top() + pad + s,
            )
            renderer_paint(painter, result, style)
            painter.end()
            bbox = _measured_bbox(scratch) or (s, s, base_w, base_h)
            margin = s
        elif bbox is None:
            # Fully transparent paint (theoretically unreachable for
            # non-empty text): keep the analytic window centred in scratch.
            bbox = (margin, margin, base_w, base_h)
        bx, by, bw, bh = bbox
        qimg = scratch.copy(bx, by, bw, bh)
        self._pixmap = QPixmap.fromImage(qimg)
        # G-07-5 (plan 07-08): the origin-cancel translate above cancels the
        # layout origin IN FULL, but the align_v dy rides that origin (the
        # renderer offsets horizontal blocks top/middle/bottom via
        # result.origin.y). Re-add the box-relative origin delta to the ink
        # offset so the overlay sits exactly where the bake paints for
        # align_v != top (D-01 canvas ≡ bake).
        dy = result.origin.y() - box_rect.y() - _OVERLAY_INSET
        # quick-260826-09m: a scratch pixel (bx, by) equals old-surface pixel
        # (bx - S, by - S), and the old surface origin sat at box-relative
        # (ink.left() - pad, ink.top() - pad) — so the MEASURED box replaces
        # the analytic ink corner as the offset source:
        self._ink_offset = QPointF(
            ink.left() - pad + bx - margin,
            ink.top() - pad + by - margin + dy,
        )
        self.update()

    def _render_rotated(
        self,
        result: LayoutResult,
        style: TextStyle,
        box_rect: QRectF,
        angle_deg: float,
        pad: float,
    ) -> None:
        """Render a ROTATED layout into the cached pixmap (quick-260824-viq).

        The renderer's ``paint`` applies the rotation about
        ``result.box_center`` itself (Task 1), so the surface must cover the
        ROTATED padded-ink bounds and the item position must place it back at
        the exact spot the bake paints — D-01 canvas ≡ bake.

        Geometry derivation (the unrotated path is the angle->0 special
        case): with the cancel translate ``t0`` from the unrotated path, the
        pixmap-local position of doc point ``p`` after ``renderer_paint`` is
        ``t0 + C + R(p + origin - C)`` where ``C`` is the box center and
        ``R`` the rotation (``translate(C); rotate; translate(-C);
        translate(origin)`` composes with the rotation INSIDE — ``origin``
        rotates together with ``p``). The ANALYTIC surface bounding box
        comes from mapping the padded-ink corners through that expression;
        quick-260826-09m inflates that analytic box by the safety margin S
        for the scratch and then CROPS to the measured alpha bounding box,
        so glyph overshoot never clips. The item position uses the MEASURED
        box in place of the analytic min-corner in ``P = min_g - t0``
        (stored box-relative in :attr:`_render_offset` for the setPos-only
        :meth:`refresh_position`, RC-1).
        """
        ink = result.ink
        pr = QRectF(
            ink.left() - pad,
            ink.top() - pad,
            ink.width() + 2.0 * pad,
            ink.height() + 2.0 * pad,
        )
        t0x = -result.origin.x() - ink.left() + pad
        t0y = -result.origin.y() - ink.top() + pad
        c = result.box_center
        rad = math.radians(angle_deg)
        cos_a, sin_a = math.cos(rad), math.sin(rad)

        def _g(px: float, py: float) -> tuple[float, float]:
            """Pixmap-local position of doc point ``(px, py)`` pre-shift."""
            vx = px + result.origin.x() - c.x()
            vy = py + result.origin.y() - c.y()
            return (
                t0x + c.x() + vx * cos_a - vy * sin_a,
                t0y + c.y() + vx * sin_a + vy * cos_a,
            )

        # ANALYTIC surface bounds: map the padded-ink corners through _g.
        xs: list[float] = []
        ys: list[float] = []
        for corner in (
            pr.topLeft(),
            pr.topRight(),
            pr.bottomRight(),
            pr.bottomLeft(),
        ):
            gx, gy = _g(corner.x(), corner.y())
            xs.append(gx)
            ys.append(gy)
        left, top = min(xs), min(ys)
        w = max(1, math.ceil(max(xs) - left))
        h = max(1, math.ceil(max(ys) - top))
        # quick-260826-09m: inflate the analytic box by the safety margin S
        # for the scratch (corner mapping through _g UNCHANGED), render with
        # the same formula anchored at the inflated corner, measure the TRUE
        # painted extent from the scratch alpha, crop. One defensive retry
        # with S doubled on border contact.
        margin = _measure_margin(result.used_font_size_px)

        def _render_scratch(
            s: int,
        ) -> tuple[QImage, tuple[int, int, int, int] | None, int]:
            lp, tp = left - s, top - s
            scratch = QImage(
                w + 2 * s, h + 2 * s, QImage.Format.Format_ARGB32_Premultiplied
            )
            scratch.fill(Qt.GlobalColor.transparent)
            painter = QPainter(scratch)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            # Shift the composed local coords (_g = t0 + paint-output) into
            # the INFLATED surface: translate by t0 - (left', top'). At
            # angle 0 this still reduces to the legacy cancel translate
            # shifted by S.
            painter.translate(t0x - lp, t0y - tp)
            renderer_paint(painter, result, style)  # rotates about box_center
            painter.end()
            return scratch, _measured_bbox(scratch), s

        scratch, bbox, s_used = _render_scratch(margin)
        if bbox is not None and (
            bbox[0] == 0
            or bbox[1] == 0
            or bbox[0] + bbox[2] == scratch.width()
            or bbox[1] + bbox[3] == scratch.height()
        ):
            scratch, bbox, s_used = _render_scratch(margin * 2)
        if bbox is None:
            # Fully transparent paint (defensive): keep the analytic window.
            bx, by, bw, bh = s_used, s_used, w, h
        else:
            bx, by, bw, bh = bbox
        qimg = scratch.copy(bx, by, bw, bh)
        self._pixmap = QPixmap.fromImage(qimg)
        # Item position P = measured composed min-corner - t0, stored
        # relative to the box top-left. A scratch pixel (bx, by) sits at
        # composed-local (left' + bx, top' + by) where left'/top' are the
        # INFLATED analytic corners of the LAST rendered scratch.
        lp_final, tp_final = left - s_used, top - s_used
        px = lp_final + bx - t0x - box_rect.x()
        py = tp_final + by - t0y - box_rect.y()
        self._render_offset = QPointF(px, py)
        self.update()

    def refresh_position(self, box_rect: QRectF, inset: float) -> None:
        """Reposition the overlay inside ``box_rect`` — setPos ONLY (RC-1).

        Uses the geometry cached by the last :meth:`set_content`; never
        re-layouts. Called from ``BoxItem._reposition_text_overlay`` on
        every move/resize/zoom/selection change (per-mousemove). A rotated
        render uses the cached :attr:`_render_offset`; rotation 0 keeps the
        legacy byte-identical formula.
        """
        if self._render_offset is not None:
            self.setPos(box_rect.x() + self._render_offset.x(), box_rect.y() + self._render_offset.y())
            return
        self.setPos(
            box_rect.x() + inset + self._ink_offset.x(),
            box_rect.y() + inset + self._ink_offset.y(),
        )


class BoxItem(QGraphicsRectItem):
    """A text box on the canvas — origin-coloured ``QGraphicsRectItem`` (D-05).

    Composes a plan 03-01 ``PageBox`` (the data model — box/origin/payload +
    the D-15 seam). Renders an origin-coloured border (green detected / amber
    user, D-09) with a selection affordance: 2px unselected / 3px selected +
    a hue tint fill when selected (UI-SPEC §12c). The four corner resize
    handles (§12b) are visible ONLY on the selected box (D-08 single-select);
    plan 07-02 (D-09) extends that to the PRIMARY box only when the canvas
    installs its is-primary provider (multi-select — handles on the group
    anchor, UI-SPEC §32).

    ``ItemIsSelectable`` provides native selection.  Movement is deliberately
    owned by :class:`EditorCanvas`: it updates ``rect()`` during a drag, which
    is also the geometry materialized for persistence.  Do not set
    ``ItemIsMovable`` here — Qt would instead update ``pos()`` independently
    of ``rect()``, and can steal a corner-handle drag from the canvas resize
    state machine. Qt's default dashed selection outline is suppressed
    (UI-SPEC §12a "disable Qt's default dashed selection outline") — the
    origin-coloured solid border is the sole selection signal plus the handles
    + tint.
    """

    def __init__(self, pagebox: "PageBox", parent: QGraphicsItem | None = None) -> None:
        # Box.as_tuple_xywh returns (x, y, w, h) — exactly the QRectF ctor order.
        x, y, w, h = pagebox.box.as_tuple_xywh
        super().__init__(QRectF(x, y, w, h), parent)
        # The model (box/origin/payload + D-15 seam). The vendored Box is
        # @frozen (immutable) — NEVER mutated; we re-materialize from the live
        # rect via current_box() at snapshot boundaries (Pitfall 6).
        self.pagebox = pagebox
        # Above mask_item, below preview_item z=900 / cursor z=1000
        # (UI-SPEC §Z-order).
        self.setZValue(100)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        # SizeAllCursor over the box body = the move affordance (UI-SPEC §12c).
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        # Four corner handles — children, z=150 (UI-SPEC §12b). Visible only
        # on the selected box (_sync_handles toggles visibility).
        self.handles: dict[str, CornerHandle] = {
            c: CornerHandle(c, self) for c in ("TL", "TR", "BL", "BR")
        }
        # Phase 4 display-object children (D-09). A text overlay (z=120) + a
        # bubble-number badge (z=140) — both children of this BoxItem so they
        # inherit its visibility (the box-layer toggle Shift+M hides the whole
        # box incl. text + badges; the text-overlay toggle T hides ONLY the
        # text children, D-12). The overlay is the renderer-driven OPAQUE
        # typeset item (D-01, plan 07-01 — surface 34 supersedes the Phase 4
        # translucent QGraphicsTextItem); the badge ignores transformations
        # so it stays constant viewport px at any zoom (digit-sized since
        # plan 04-10, like the handles).
        self._text_overlay = TypesetOverlayItem(self)
        self._text_overlay_visible = True  # T toggle state (D-12)
        # Stored zoom (plan 04-08 RC-2/RC-3 heritage). The scene-px sizing
        # contract (Pattern 1 note) supersedes the §16 viewport-px clamp for
        # opaque text: the overlay renders at the style's scene-px size and
        # scales with the canvas zoom like the artwork itself, so a zoom
        # change does NOT re-layout. Set BEFORE the first
        # refresh_text_overlay() so a fresh box renders the zoom-1 style.
        self._overlay_zoom = 1.0
        # The badge = a background rect + a digit text child, both ignoring
        # transformations (constant viewport px). Digit is a child of the rect
        # so it inherits the rect's position/visibility. The initial 1x1 rect
        # is never rendered with a number — refresh_badge (below) sizes the
        # rect from the digit measurement (plan 04-10) and hides the badge
        # while bubble_no is None.
        self._badge = QGraphicsRectItem(0.0, 0.0, 1.0, 1.0, self)
        self._badge.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True
        )
        self._badge.setZValue(_BADGE_Z)
        self._badge.setBrush(QBrush(_BADGE_FILL))
        self._badge.setPen(_BADGE_OUTLINE_AUTO)
        self._badge.setVisible(False)  # shown by refresh_badge
        self._badge_digit = QGraphicsTextItem(self._badge)
        self._badge_digit.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True
        )
        self._badge_digit.setDefaultTextColor(_BADGE_DIGIT_COLOR)
        self._badge_digit.setFont(_BADGE_DIGIT_FONT)
        # Measurement basis: the tight glyph line box — with the default
        # QTextDocument margin (4.0) the bounding rect is inflated by 8px per
        # axis (probed: '1' is 24x27 at margin 4 vs 16x19 at margin 0), which
        # would over-size the badge (plan 04-10).
        self._badge_digit.document().setDocumentMargin(0.0)
        # The centered position is computed dynamically by refresh_badge from
        # the measured digit size (plan 04-10).
        self._badge_digit.setPos(0.0, 0.0)
        # Plan 04-05 edit-mode state (UI-SPEC §15, D-07): while the inline
        # editor is active the box cannot be moved or resized. The canvas's
        # mouse-press dispatch guard is the PRIMARY disable; this flag + the
        # handles' mouse acceptance are the item-level belt-and-suspenders.
        self._edit_mode = False
        # Restore target for the handles' mouse acceptance (captured at
        # construction so set_edit_mode(False) restores exactly what Qt gave
        # the handles by default).
        self._handle_rest_buttons = self.handles["TL"].acceptedMouseButtons()
        # quick-260822-gnq: ephemeral geometry-stale marker + the corner
        # re-run affordance (RedetectHandle, z=160). View state ONLY — never
        # persisted to .mas/project files. The canvas installs
        # ``activate_callback`` wiring (box_redetect_requested) at creation.
        self._geometry_stale = False
        self._redetect = RedetectHandle(self)
        # quick-260824-viq: the free-angle text-rotation handle (z=155).
        # Integrated into the SAME visibility machinery as the corner
        # handles (selected AND primary) via _sync_handles /
        # _sync_handles_for_state; the canvas installs its activate
        # callback (the rotate-drag arming seam) per item.
        self._rotation_handle = RotationHandle(self)
        # quick-260824-viq: the rotation handle's default acceptance (captured
        # for the set_edit_mode restore, mirroring the corner handles).
        self._rotation_rest_buttons = self._rotation_handle.acceptedMouseButtons()
        # Plan 07-02 (D-09): WEAKREF to the owning canvas, installed by
        # ``set_primary_owner``. ``_sync_handles_for_state`` asks it whether
        # THIS item is the selection PRIMARY (the last-clicked box): corner
        # handles render on the primary only — a selected non-primary member
        # keeps its handles hidden (UI-SPEC §32). A weakref (not a lambda or a
        # strong canvas reference) keeps the item free of a reference cycle —
        # a cycle stalls Python GC of the canvas and breaks Qt teardown
        # ordering (crash probe).
        self._primary_owner = None
        # Phase 8 inpaint border-state dimension (plan 08-06). None = no refresh
        # yet — renders the Phase 3 look (backward-compat default). State strings
        # come from PageBox.inpaint_state (08-01) via the 08-07 refresh
        # helper; BoxItem never computes the gate itself.
        self._inpaint_state: str | None = None
        self._apply_origin_pen()
        self._sync_handles()
        # Render the display-object children from the current payload/bubble_no
        # (a box created with text already on it shows the overlay at once).
        self.refresh_text_overlay()
        self.refresh_badge()

    # ------------------------------------------------------------- rendering
    def _inpaint_pen_color(self, base_hue: str) -> QColor:
        """The border colour for the current inpaint state (UI-SPEC §Color).

        ``forced_*``/``never`` REPLACE the origin hue with the reused palette
        greys — an override state means the user decided, so the hue switches
        from "the auto gate decided" (origin hue) to "the user's override
        decided" (near-white forced-in / muted grey forced-out, reading rule 2).
        Auto states (``will_inpaint``/``will_fill``/``gate_skipped``/``None``)
        keep the origin hue (the auto-gate surface). 08.1 keeps ZERO new hex:
        both forced variants map to #e8e8ea, never to #9a9aa2.
        """
        if self._inpaint_state in _INPAINT_GREY_STATES:
            # Grey set covers all forced variants + never; distinguish only never
            # vs forced family (both forced variants share the near-white).
            if self._inpaint_state == "never":
                return QColor(_INPAINT_NEVER_HEX)
            return QColor(_INPAINT_FORCED_HEX)
        return QColor(base_hue)

    def _apply_origin_pen(self) -> None:
        """Set the pen (2px/3px state colour) and brush (NoBrush/tint) by selection.

        UI-SPEC §12c + the Phase 8 border-state contract: unselected = 2px
        state colour + transparent fill; selected = 3px state colour + the same
        colour at ``rgba(., 0.12)`` tint. The state adds the stroke-style
        dimension (solid = will inpaint / dashed = won't) and the hue-or-grey
        decider dimenension (origin hue = auto gate, greys = user override),
        then the existing width/tint logic applies on top. The border is the
        sole selection signal (plus handles + tint) — Qt's default dashed
        outline is suppressed because we set our own pen here (no ``QStyleOption``
        flag).
        """
        hue = origin_hue(self.pagebox.origin)
        pen_color = self._inpaint_pen_color(hue)
        selected = self.isSelected()
        width = _SELECTED_PEN_WIDTH if selected else _UNSELECTED_PEN_WIDTH
        pen = QPen(pen_color, width)
        if self._inpaint_state in _INPAINT_DASHED_STATES:
            pen.setStyle(Qt.PenStyle.CustomDashLine)
            pen.setDashPattern(_INPAINT_DASH_PATTERN)
        else:  # will_inpaint / forced / None — solid (the phase 3 look)
            pen.setStyle(Qt.PenStyle.SolidLine)
        self.setPen(pen)
        if selected:
            tint = QColor(pen_color)
            tint.setAlpha(_TINT_ALPHA)
            self.setBrush(QBrush(tint))
        else:
            self.setBrush(Qt.BrushStyle.NoBrush)

    def set_inpaint_state(self, state: str | None) -> None:
        """Set the inpaint border-state dimension (plan 08-06, UI-SPEC §37).

        ``state`` is one of the ``PageBox.inpaint_state`` returns
        (08-01 — the SINGLE derivation site; this method never computes the
        gate itself): ``"will_inpaint"`` / ``"gate_skipped"`` / ``"forced"`` /
        ``"never"``, or ``None`` to reset to the Phase 3 look (the
        backward-compat default before any refresh call). The sole caller is
        ``MainWindow.refresh_box_inpaint_states`` (plan 08-07).

        Stores the state then re-derives the pen through the SAME paths
        ``itemChange`` uses (``_apply_origin_pen`` unselected /
        ``_apply_look_for`` selected) so the ItemSelectedChange re-apply hook
        (:meth:`itemChange`) keeps working with zero changes — a selection
        change always re-renders with the CURRENT state. One item repaint,
        negligible cost (PATTERNS file 6 — event-driven state -> pen).
        """
        self._inpaint_state = state
        if self.isSelected():
            self._apply_look_for(True)
        else:
            self._apply_origin_pen()
        self.update()

    def set_primary_owner(self, owner) -> None:
        """Install the owning canvas WEAKREF (D-09, plan 07-02).

        ``_sync_handles_for_state`` (which has no canvas context) consults the
        owner to show corner handles on the PRIMARY box only. ``owner`` is a
        ``weakref.ref`` to the canvas — the item never holds the canvas
        strongly (reference-cycle discipline).
        """
        self._primary_owner = owner

    # ------------------------------------------- geometry-stale marker (gnq)
    @property
    def geometry_stale(self) -> bool:
        """True iff this box's on-canvas geometry changed since its last fit.

        quick-260822-gnq: a committed move/resize/create marks the box stale
        INSTEAD of triggering an immediate re-fit (the old refit-on-commit
        annoyance). The marker drives the amber corner affordance; it is
        cleared when the user clicks the affordance, which runs the explicit
        re-fit + OCR pass. quick-260824-pqn: the affordance appears while the
        box is geometry-stale (moved/resized); click to re-run detection+OCR
        — there is no automatic trigger path anymore. Ephemeral view state —
        never persisted.
        """
        return self._geometry_stale

    @geometry_stale.setter
    def geometry_stale(self, value: bool) -> None:
        self._geometry_stale = bool(value)
        # Visibility tracks ONLY the marker — children inherit the parent's
        # visibility, so hiding the box layer (Shift+M) hides the affordance
        # with the box automatically.
        self._redetect.setVisible(self._geometry_stale)
        self._reposition_redetect()

    def set_redetect_callback(self, callback) -> None:
        """Install the affordance click callback (canvas -> signal wiring).

        ``callback`` is invoked with NO arguments on a left-click of the
        re-run affordance; the canvas installs a closure that emits
        ``box_redetect_requested`` carrying THIS item.
        """
        self._redetect.activate_callback = callback

    def _reposition_redetect(self) -> None:
        """Track the live rect (called from _sync_handles / the setter)."""
        self._redetect.reposition(self.rect())

    def _sync_handles(self, primary: bool | None = None) -> None:
        """Show + reposition handles on the selected box (D-08/D-09).

        Called on init, on selection change (via :meth:`itemChange`), and from
        the canvas when the box geometry changes (move/resize commit) or the
        zoom changes (``zoom_changed`` subscription). ``ItemIgnoresTransformations``
        keeps each handle 8x8 viewport px regardless of zoom — only its position
        is recomputed.

        ``primary`` (plan 07-02): the multi-select affordance — corner handles
        render on the PRIMARY box only (UI-SPEC §32). None -> visible iff
        selected (the Phase 3 single-select contract, byte-identical for N=1);
        bool -> visible iff selected AND primary.

        Also refreshes the bubble badge and repositions the text overlay so
        both track the box through move/resize/zoom (the badge sits TL-outside
        the box rect; the overlay sits inside it — both must move whenever the
        rect does). Mirrors how handles reposition on zoom.
        """
        selected = self.isSelected()
        show = selected if primary is None else (selected and primary)
        rect = self.rect()
        for handle in self.handles.values():
            handle.setVisible(show)
            handle.reposition(rect)
        # quick-260824-viq: the rotation handle rides the SAME visibility
        # rule as the corner handles (selected AND primary).
        self._rotation_handle.setVisible(show)
        self._rotation_handle.reposition(rect)
        # quick-260822-gnq: keep the stale-marker affordance on the live rect.
        self._reposition_redetect()
        self.refresh_badge()
        self._reposition_text_overlay()

    def itemChange(  # noqa: N802 (Qt API casing)
        self, change: QGraphicsItem.GraphicsItemChange, value
    ):
        """Sync pen + handles on selection state change (UI-SPEC §12a/§12c).

        ``ItemSelectedChange`` fires BEFORE the selection flag flips, so the
        incoming ``value`` is the new selected state (a bool). We re-apply the
        origin pen and reposition the handles so the look updates the instant
        selection changes — without relying on Qt's default dashed outline
        (which we suppress by always setting our own pen).
        """
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            # value is the prospective new selection state (bool). Apply the
            # look for that state directly — the flag has not flipped yet, so
            # isSelected() still reports the OLD state and cannot be relied on.
            selected = bool(value)
            self._apply_look_for(selected)
            self._sync_handles_for_state(selected)
        return super().itemChange(change, value)

    def _apply_look_for(self, selected: bool) -> None:
        """Apply pen/brush for a given selection state without mutating flags.

        Used by :meth:`itemChange` where the flag has not flipped yet. Mirrors
        :meth:`_apply_origin_pen` and consumes the Phase 8 ``_inpaint_state``
        identically (the state's hue-or-grey + solid-or-dashed at the
        state's width, with the selection tint on top).
        """
        hue = origin_hue(self.pagebox.origin)
        pen_color = self._inpaint_pen_color(hue)
        width = _SELECTED_PEN_WIDTH if selected else _UNSELECTED_PEN_WIDTH
        pen = QPen(pen_color, width)
        if self._inpaint_state in _INPAINT_DASHED_STATES:
            pen.setStyle(Qt.PenStyle.CustomDashLine)
            pen.setDashPattern(_INPAINT_DASH_PATTERN)
        else:  # will_inpaint / forced / None — solid (the phase 3 look)
            pen.setStyle(Qt.PenStyle.SolidLine)
        self.setPen(pen)
        if selected:
            tint = QColor(pen_color)
            tint.setAlpha(_TINT_ALPHA)
            self.setBrush(QBrush(tint))
        else:
            self.setBrush(Qt.BrushStyle.NoBrush)

    def _sync_handles_for_state(self, selected: bool) -> None:
        """Reposition handles and toggle visibility for a given selection state.

        Also repositions the text overlay: selection changes the pen width
        (2px unselected / 3px selected, UI-SPEC §12c), which changes the
        overlay inset (``pen_w/2``), so the inset stays exact on selection
        change. ``itemChange`` calls ``_apply_look_for`` BEFORE this, so the
        pen already reflects the new state here.

        Plan 07-02 (D-09): when the canvas installed its primary-owner
        weakref (``set_primary_owner``), handles render on the PRIMARY box
        only — a selected non-primary member keeps its handles hidden (the
        multi-select affordance, UI-SPEC §32). An owner answer of None means
        the canvas tracks no primary yet (direct ``setSelected`` paths —
        tests, create-commit, double-click edit), so the Phase 3 selected-
        based behavior applies.
        """
        rect = self.rect()
        show = selected
        if selected and self._primary_owner is not None:
            canvas = self._primary_owner()
            if canvas is not None:
                primary = canvas._is_primary_provider(self)
                if primary is not None:
                    show = bool(primary)
        for handle in self.handles.values():
            handle.setVisible(show)
            handle.reposition(rect)
        # quick-260824-viq: the rotation handle rides the SAME visibility
        # rule as the corner handles (selected AND primary).
        self._rotation_handle.setVisible(show)
        self._rotation_handle.reposition(rect)
        # quick-260822-gnq: keep the stale-marker affordance on the live rect.
        self._reposition_redetect()
        self._reposition_text_overlay()

    # --------------------------------------------- Phase 4 display-object children
    def refresh_text_overlay(self) -> None:
        """Re-render the text overlay from the current payload + style (D-01).

        The overlay shows the **current-focus** text per the D-10 rule
        (translation when present, else recognized text — delegated to
        ``gui/text_renderer.current_focus_text``, the ONE rule the bake
        shares, D-04). A box with no recognized text renders nothing (the
        overlay is hidden).

        The render goes through the shared renderer (``layout`` + ``paint``
        into the overlay's cached pixmap) at the box's flat per-box
        ``TextStyle`` (defaults when the box has none — D-06 flat). The text
        stays PLAIN throughout (the renderer uses plain documents — ASVS V5).

        Honours :attr:`_text_overlay_visible` (the T toggle, D-12): if the text
        layer is off the overlay is hidden even when the box carries text.
        """
        text = self._current_focus_text()
        style = self.pagebox.style if self.pagebox.style is not None else TextStyle()
        # G-07-1: the render vertical flag is bool(style.vertical) ONLY —
        # the box payload's `vertical` field is pure export metadata (the
        # detector's CTD orientation), never a render instruction. The SAME
        # single expression text_renderer.bake_typeset_page and
        # main_window._style_rendered_size use, so the canvas, the bake, and
        # the size probe flip atomically (no divergence window); the
        # Inspector checkbox writes style.vertical.
        vertical = bool(style.vertical)
        # Pass the FULL box rect — the renderer applies its own inner inset
        # (identical for canvas and bake, D-01).
        self._text_overlay.set_content(
            text, style, self.rect(), vertical=vertical
        )
        self._reposition_text_overlay()
        self._text_overlay.setVisible(bool(text) and self._text_overlay_visible)

    def _reposition_text_overlay(self) -> None:
        """Reposition the text overlay inside the box rect — setPos ONLY (RC-1).

        Pure geometry sync: no text/document rebuild. Called from
        :meth:`_sync_handles` / :meth:`_sync_handles_for_state` on every
        move/resize/zoom/selection change (the canvas calls ``_sync_handles``
        on EVERY ``mouseMoveEvent`` during a drag — canvas.py:1022-1023 — so a
        full re-layout per mousemove would be wasteful). The inset is the
        renderer's constant (the same inner geometry the bake paints).
        """
        self._text_overlay.refresh_position(self.rect(), _OVERLAY_INSET)

    def _overlay_inset(self) -> float:
        """The legacy overlay inset formula (border half-width + 2px margin).

        Kept for API compatibility — the renderer-driven overlay positions
        with the renderer's own ``_OVERLAY_INSET`` (the D-01 single visual
        truth: the canvas must sit exactly where the bake paints). The
        border-width term belongs to the box chrome, which the bake never
        draws.
        """
        return self.pen().widthF() / 2.0 + _OVERLAY_INSET

    def apply_overlay_zoom(self, zoom: float) -> None:
        """Store the canvas zoom (plan 04-08 heritage) without re-layouting.

        The scene-px sizing contract (Pattern 1 note) supersedes the §16
        viewport-px font clamp + ``2/zoom`` outline for OPAQUE text: the
        overlay renders at the style's scene-px size and scales with the
        canvas zoom like the artwork itself — a zoom change must NOT re-derive
        the style (WYSIWYG, D-01). The stored zoom remains for API
        compatibility with the canvas ``zoom_changed`` slot (canvas.py:1790).

        Defensive guard: a non-positive zoom falls back to 1.0 (the old
        division safety — kept for the stored value's invariants).
        """
        if zoom <= 0:
            zoom = 1.0
        self._overlay_zoom = zoom
        # quick-260824-t64 Task 2: propagate to the corner handles so their
        # hit rects stay ~18 VIEWPORT px at any zoom. The canvas zoom_changed
        # slot calls this on every wheel/reset/fit-to-window/page-load, so
        # handles always carry the live zoom while visible (unselected handles
        # are invisible and thus unhittable — lazily corrected at next sync).
        for handle in self.handles.values():
            handle.set_hit_zoom(zoom)

    def refresh_badge(self) -> None:
        """Re-render the bubble-number badge (D-15/D-16, UI-SPEC §17).

        Hidden when ``pagebox.bubble_no`` is None. Otherwise DIGIT-SIZED (plan
        04-10): the digit text is set FIRST, measured via its LOCAL bounding
        rect (document margin 0 = the tight glyph line box, so the badge hugs
        its number instead of clipping like the old fixed 20x14 rect), and the
        badge rect is resized to digit_w + 2x4 by digit_h + 2x2 padding with
        the digit re-centered. Then shown at the **TL corner, OUTSIDE the box
        rect** (offset ``(-badge_w-2, -badge_h-2)`` computed from the ACTUAL
        badge size) so it never overlaps the TL handle hit area (RESEARCH
        Pitfall 7). If the outside position would clip off-canvas at the page
        TL edge, the badge flips to inside-top-left (inset 2px) per UI-SPEC
        §17. The border pen is amber (``#f5a623``) for a manual-override badge
        (D-16), matte (``#0b0b0e``) for an auto-numbered one.
        """
        if self.pagebox.bubble_no is None:
            self._badge.setVisible(False)
            return
        # Measure + size + center FIRST, then place — the placement reads the
        # ACTUAL badge size (one source of truth with the setRect above, so
        # the TL-outside offset and the edge-flip decision always match the
        # rendered geometry). The digit's LOCAL bounding rect is viewport px
        # (the badge/digit ignore transformations) — never sceneBoundingRect
        # on the ignores-transformations child.
        self._badge_digit.setPlainText(str(self.pagebox.bubble_no))
        dbr = self._badge_digit.boundingRect()
        # Floor the measured size (degenerate-measurement guard, T-4-16g — a
        # zero/negative rect must not produce an invalid badge rect, mirroring
        # the T-4-13g floor discipline).
        dw = max(1.0, dbr.width())
        dh = max(1.0, dbr.height())
        bw = dw + 2.0 * _BADGE_PAD_W
        bh = dh + 2.0 * _BADGE_PAD_H
        self._badge.setRect(0.0, 0.0, bw, bh)
        self._badge_digit.setPos((bw - dw) / 2.0, (bh - dh) / 2.0)
        # Position at the TL corner, OUTSIDE the box rect (UI-SPEC §17). The
        # badge ignores transformations, so pos() is in SCENE coords; use the
        # scene-space rect so a moved/resized box keeps the badge tracking.
        rect = self.sceneBoundingRect()
        bx = rect.left() - bw - _BADGE_OFFSET
        by = rect.top() - bh - _BADGE_OFFSET
        # Edge-flip: if the outside position would clip off the page TL edge,
        # flip to inside-top-left (inset 2px). sceneRect reflects the image
        # bounds (set_image -> setSceneRect); falls back to no-flip when the
        # scene has no rect (defensive — a parent-less item has no scene).
        scene = self.scene()
        if scene is not None:
            sr = scene.sceneRect()
            if not sr.isNull() and (bx < sr.left() or by < sr.top()):
                bx = rect.left() + _BADGE_OFFSET
                by = rect.top() + _BADGE_OFFSET
        self._badge.setPos(bx, by)
        # Border pen: amber for manual override, matte for auto (D-16).
        if self.pagebox.manual_override:
            self._badge.setPen(_BADGE_OUTLINE_OVERRIDE)
        else:
            self._badge.setPen(_BADGE_OUTLINE_AUTO)
        self._badge.setVisible(True)

    def set_text_overlay_visible(self, visible: bool) -> None:
        """Show/hide the text-overlay child (the T toggle, D-12).

        Independent of the box-layer visibility (Shift+M): hiding the text layer
        leaves the box borders + badges visible. The box-layer toggle routes
        through ``setVisible`` on the whole BoxItem (which hides ALL children
        incl. the overlay); this method only flips the text-overlay child so the
        border + badge stay visible. Stores the flag so a subsequent
        :meth:`refresh_text_overlay` re-applies it.
        """
        self._text_overlay_visible = visible
        # Only show the overlay if it actually has text (refresh enforces the
        # empty-box-no-overlay contract); otherwise just hide.
        if visible:
            self.refresh_text_overlay()
        else:
            self._text_overlay.setVisible(False)

    # ------------------------------------------- rotation preview (viq)
    def preview_rotation(self, angle_deg: float) -> None:
        """LIVE-drag-only lightweight rotation of the text overlay (viq).

        Applies a pure QGraphicsItem rotation to the overlay child about the
        BOX CENTER (expressed in overlay-local coordinates via the transform
        origin point). NO re-layout, NO re-render — the per-mousemove
        discipline (RC-1); the caller follows a committed angle with
        :meth:`refresh_text_overlay` to bake it into the cached pixmap.

        quick-260825-wfy: when the cached pixmap ALREADY carries a committed
        rotation (baked by ``_render_rotated``), only the DELTA
        (``angle_deg - _baked_rotation``) is applied — applying the absolute
        live angle on a baked pixmap double-rotates (start + live) and snaps
        on release.
        """
        overlay = self._text_overlay
        center = self.rect().center()
        pos = overlay.pos()
        delta = _normalize_rotation(angle_deg - overlay._baked_rotation)
        # boundingRect depends on the rotation — Qt must be told BEFORE the
        # transform changes so it repaints the enlarged extents (wfy).
        overlay.prepareGeometryChange()
        overlay.setTransformOriginPoint(
            center.x() - pos.x(), center.y() - pos.y()
        )
        overlay.setRotation(delta)
        overlay.update()

    def clear_preview_rotation(self) -> None:
        """Reset the live-drag preview rotation (the commit path re-renders).

        After clear the item transform is identity: the pixmap's own baked
        rotation shows through untouched. prepareGeometryChange fires first
        so Qt releases the enlarged preview boundingRect (wfy)."""
        overlay = self._text_overlay
        overlay.prepareGeometryChange()
        overlay.setRotation(0.0)
        overlay.setTransformOriginPoint(0.0, 0.0)

    # ------------------------------------------- inline-editor edit-mode hooks
    def enter_edit_mode(self) -> None:
        """Enter edit mode: disable move/resize interaction (UI-SPEC §15, D-07).

        Thin wrapper the canvas calls when opening the inline editor (plan
        04-05). The box STAYS selected while editing; the corner handles stay
        VISIBLE (the box is still selected, §15) but are not interactive until
        :meth:`exit_edit_mode` restores them.
        """
        self.set_edit_mode(True)

    def exit_edit_mode(self) -> None:
        """Exit edit mode: restore move/resize interaction (UI-SPEC §15)."""
        self.set_edit_mode(False)

    def set_edit_mode(self, active: bool) -> None:
        """Enable/disable move/resize interaction while the inline editor is active.

        The canvas's mouse-press dispatch guard (``canvas.mousePressEvent``,
        plan 04-05) is the PRIMARY disable — it commits the editor + consumes
        any press before the box hit-test dispatch can run (D-07). This method
        is the item-level belt-and-suspenders: the corner handles drop their
        mouse acceptance while editing so a direct handle press cannot arm a
        resize even on a super() fall-through path.
        """
        self._edit_mode = active
        for handle in self.handles.values():
            if active:
                handle.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            else:
                handle.setAcceptedMouseButtons(self._handle_rest_buttons)
        # quick-260824-viq: the rotation handle joins the edit-mode
        # acceptance stripping (a direct handle press must not arm a rotate
        # drag while the inline editor is open).
        if active:
            self._rotation_handle.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        else:
            self._rotation_handle.setAcceptedMouseButtons(
                self._rotation_rest_buttons
            )

    def _current_focus_text(self) -> str:
        """Return the D-10 current-focus text: translation when present, else recognized.

        Empty string when the box carries neither (the overlay stays hidden).
        Delegates to ``gui/text_renderer.current_focus_text`` — the ONE rule
        shared with the bake compositor (D-04 WYSIWYG contract).
        """
        return current_focus_text(self.pagebox)

    # --------------------------------------------------- snapshot materialization
    def current_box(self) -> "Box":
        """Materialize a fresh vendored ``Box`` with int coords from the live rect.

        Pitfall 6 (int at the ``Box`` <-> ``QRectF`` boundary): the on-canvas
        rect stays float-precise for smooth dragging, but every snapshot /
        persistence boundary materializes ints via ``int()``. This is what
        ``EditorCanvas.boxes_snapshot()`` calls per item (the Pitfall-3
        detachment boundary — fresh materialization at call-time, no live-item
        references).
        """
        from panelcleaner.structures import Box

        r = self.rect()
        x1 = int(r.x())
        y1 = int(r.y())
        x2 = int(r.x() + r.width())
        y2 = int(r.y() + r.height())
        return Box(x1, y1, x2, y2)
