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

from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPen,
    QPainterPath,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsTextItem,
)

from manga_ai_studio.core.box_model import DETECTED, USER

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
# Text-overlay style (UI-SPEC §Color text-overlay): fill rgba(232,232,234,0.85)
# translucent Text primary + outline rgba(11,11,14,0.92) 2px dark matte behind
# the glyphs (D-11 legibility halo against artwork). 14 scene px base size,
# Liberation Sans (the Phase 1 canvas-overlay font — image_viewer.py:306).
_OVERLAY_FILL = QColor.fromRgbF(232 / 255, 232 / 255, 234 / 255, 0.85)
_OVERLAY_OUTLINE = QPen(QColor.fromRgbF(11 / 255, 11 / 255, 14 / 255, 0.92), 2)
_OVERLAY_FONT = QFont("Liberation Sans", 14)  # 14 scene px (UI-SPEC §16)
# Inner margin: text inset by the border width + 2px so it never touches the
# box edge (UI-SPEC §16).
_OVERLAY_INSET = 2.0
# Bubble-badge style + geometry (UI-SPEC §17). Constant 20x14 viewport px (fits
# 1-2 digits + future 3-digit padding); 12px semibold digit; badge fill near-
# opaque black so the digit reads against any artwork.
_BADGE_W = 20.0
_BADGE_H = 14.0
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


def origin_hue(origin: str) -> str:
    """Return the hex hue for a box origin (``#5fd068`` detected / ``#f5a623`` user).

    Falls back to the detected hue for an unknown origin (defensive — the
    D-03 origin constants are the only valid values in Phase 3).
    """
    return _ORIGIN_HUES.get(origin, _ORIGIN_HUES[DETECTED])


# Half of the enlarged hit size (corner of the handle = local (4,4); the hit
# rect is centred on that point, so the local top-left is 4 - half).
_HANDLE_HIT_HALF = _HANDLE_HIT_SIZE / 2.0


def _handle_hit_rect() -> QRectF:
    """The enlarged invisible hit rect for a :class:`CornerHandle` (local coords).

    Centred on the corner point at local ``(4, 4)`` (the handle is constructed
    as ``QGraphicsRectItem(0,0,8,8)``; local ``(4,4)`` maps to the exact scene
    corner after :meth:`CornerHandle.reposition` sets ``pos = scene corner - 4``).
    """
    return QRectF(
        _HANDLE_OFFSET - _HANDLE_HIT_HALF,
        _HANDLE_OFFSET - _HANDLE_HIT_HALF,
        _HANDLE_HIT_SIZE,
        _HANDLE_HIT_SIZE,
    )


def _handle_hit_path() -> QPainterPath:
    """A :class:`QPainterPath` wrapping :func:`_handle_hit_rect` (for ``shape()``)."""
    path = QPainterPath()
    path.addRect(_handle_hit_rect())
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
        ``scene.itemAt``.
        """
        return _handle_hit_path()

    def boundingRect(self) -> QRectF:  # noqa: D401 (Qt API casing)
        """Return the enlarged hit rect (matches :meth:`shape`).

        ``itemAt`` only fine-tests ``shape()`` for items whose ``boundingRect``
        already contains the probe point, so ``boundingRect`` MUST cover the
        same region as ``shape()`` or the coarse pass filters the probe out
        before ``shape()`` is consulted (verified by probe — see SUMMARY
        Deviation 1). This does NOT change the painted handle: the inherited
        :meth:`paint` draws ``rect()`` (the 8x8 from ``__init__``), not
        ``boundingRect``; the larger rect only widens the scene's repaint +
        hit-test region.
        """
        return _handle_hit_rect()



class BoxItem(QGraphicsRectItem):
    """A text box on the canvas — origin-coloured ``QGraphicsRectItem`` (D-05).

    Composes a plan 03-01 ``PageBox`` (the data model — box/origin/payload +
    the D-15 seam). Renders an origin-coloured border (green detected / amber
    user, D-09) with a selection affordance: 2px unselected / 3px selected +
    a hue tint fill when selected (UI-SPEC §12c). The four corner resize
    handles (§12b) are visible ONLY on the selected box (D-08 single-select).

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
        # text children, D-12). The overlay is PLAIN text (ASVS V5 — never
        # setHtml on OCR output); the badge ignores transformations so it stays
        # a constant 20x14 viewport px at any zoom (like the handles).
        self._text_overlay = QGraphicsTextItem(self)
        self._text_overlay.setZValue(_TEXT_OVERLAY_Z)
        self._text_overlay.setFont(_OVERLAY_FONT)
        self._text_overlay.setVisible(False)  # shown by refresh_text_overlay
        self._text_overlay_visible = True  # T toggle state (D-12)
        # The badge = a background rect + a digit text child, both ignoring
        # transformations (constant viewport px). Digit is a child of the rect
        # so it inherits the rect's position/visibility.
        self._badge = QGraphicsRectItem(0.0, 0.0, _BADGE_W, _BADGE_H, self)
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
        # Centre the digit inside the badge rect.
        self._badge_digit.setPos(3.0, -1.0)
        # Plan 04-05 edit-mode state (UI-SPEC §15, D-07): while the inline
        # editor is active the box cannot be moved or resized. The canvas's
        # mouse-press dispatch guard is the PRIMARY disable; this flag + the
        # handles' mouse acceptance are the item-level belt-and-suspenders.
        self._edit_mode = False
        # Restore target for the handles' mouse acceptance (captured at
        # construction so set_edit_mode(False) restores exactly what Qt gave
        # the handles by default).
        self._handle_rest_buttons = self.handles["TL"].acceptedMouseButtons()
        self._apply_origin_pen()
        self._sync_handles()
        # Render the display-object children from the current payload/bubble_no
        # (a box created with text already on it shows the overlay at once).
        self.refresh_text_overlay()
        self.refresh_badge()

    # ------------------------------------------------------------- rendering
    def _apply_origin_pen(self) -> None:
        """Set the pen (2px/3px origin hue) and brush (NoBrush/tint) by selection.

        UI-SPEC §12c: unselected = 2px solid hue + transparent fill; selected =
        3px solid hue + ``rgba(hue, 0.12)`` tint. The border is the sole
        selection signal (plus handles + tint) — Qt's default dashed outline
        is suppressed because we set our own pen here (no ``QStyleOption`` flag).
        """
        hue = origin_hue(self.pagebox.origin)
        selected = self.isSelected()
        width = _SELECTED_PEN_WIDTH if selected else _UNSELECTED_PEN_WIDTH
        self.setPen(QPen(QColor(hue), width))
        if selected:
            tint = QColor(hue)
            tint.setAlpha(_TINT_ALPHA)
            self.setBrush(QBrush(tint))
        else:
            self.setBrush(Qt.BrushStyle.NoBrush)

    def _sync_handles(self) -> None:
        """Show + reposition handles only on the selected box (D-08).

        Called on init, on selection change (via :meth:`itemChange`), and from
        the canvas when the box geometry changes (move/resize commit) or the
        zoom changes (``zoom_changed`` subscription). ``ItemIgnoresTransformations``
        keeps each handle 8x8 viewport px regardless of zoom — only its position
        is recomputed.

        Also refreshes the bubble badge and repositions the text overlay so
        both track the box through move/resize/zoom (the badge sits TL-outside
        the box rect; the overlay sits inside it — both must move whenever the
        rect does). Mirrors how handles reposition on zoom.
        """
        selected = self.isSelected()
        rect = self.rect()
        for handle in self.handles.values():
            handle.setVisible(selected)
            handle.reposition(rect)
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

        Used by :meth:`itemChange` where the flag has not flipped yet.
        """
        hue = origin_hue(self.pagebox.origin)
        width = _SELECTED_PEN_WIDTH if selected else _UNSELECTED_PEN_WIDTH
        self.setPen(QPen(QColor(hue), width))
        if selected:
            tint = QColor(hue)
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
        """
        rect = self.rect()
        for handle in self.handles.values():
            handle.setVisible(selected)
            handle.reposition(rect)
        self._reposition_text_overlay()

    # --------------------------------------------- Phase 4 display-object children
    def refresh_text_overlay(self) -> None:
        """Re-render the text overlay from the current payload (D-09/D-10/D-11).

        The overlay shows the **current-focus** text per the D-10 rule:
        translation when present, else recognized text. A box with no
        recognized text renders nothing (the overlay is hidden). The document
        is PLAIN text (ASVS V5 — never ``setHtml`` on OCR output, T-4-07) styled
        via ``QTextCharFormat.setTextOutline`` (RESEARCH Pattern 3 — the single
        clean API for outlined glyphs; no multi-pass QPainter).

        Honours :attr:`_text_overlay_visible` (the T toggle, D-12): if the text
        layer is off the overlay is hidden even when the box carries text.
        """
        text = self._current_focus_text()
        if not text:
            self._text_overlay.setVisible(False)
            return
        # Build the outlined run via QTextCharFormat on the document. setPlainText
        # first (PLAIN text — no rich-text injection), then merge the outline +
        # fill format onto the whole document (RESEARCH Pattern 3 — set the
        # outline + foreground on ONE format, then mergeCharFormat over the
        # document so every run carries both).
        self._text_overlay.setPlainText(text)
        doc = self._text_overlay.document()
        fmt = QTextCharFormat()
        fmt.setFont(_OVERLAY_FONT)
        fmt.setTextOutline(_OVERLAY_OUTLINE)
        fmt.setForeground(QBrush(_OVERLAY_FILL))
        cursor = QTextCursor(doc)
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.mergeCharFormat(fmt)
        # Geometry sync is delegated to the setPos-only _reposition_text_overlay
        # (RC-1, plan 04-08) so _sync_handles can reuse it per-mousemove without
        # rebuilding the document. The visible-state line stays here.
        self._reposition_text_overlay()
        self._text_overlay.setVisible(self._text_overlay_visible)

    def _reposition_text_overlay(self) -> None:
        """Reposition the text overlay inside the box rect — setPos ONLY (RC-1).

        Pure geometry sync: no text/document rebuild. Called from
        :meth:`_sync_handles` / :meth:`_sync_handles_for_state` on every
        move/resize/zoom/selection change (the canvas calls ``_sync_handles``
        on EVERY ``mouseMoveEvent`` during a drag — canvas.py:1022-1023 — so a
        full document rebuild per mousemove would be wasteful). Positions the
        overlay inset by the border width + 2px so the text never touches the
        border (UI-SPEC §16).
        """
        pen_w = self.pen().widthF() / 2.0
        inset = pen_w + _OVERLAY_INSET
        self._text_overlay.setPos(self.rect().x() + inset, self.rect().y() + inset)

    def refresh_badge(self) -> None:
        """Re-render the bubble-number badge (D-15/D-16, UI-SPEC §17).

        Hidden when ``pagebox.bubble_no`` is None. Otherwise shown at the
        **TL corner, OUTSIDE the box rect** (offset ``(-badge_w-2, -badge_h-2)``)
        so it never overlaps the TL handle hit area (RESEARCH Pitfall 7). If the
        outside position would clip off-canvas at the page TL edge, the badge
        flips to inside-top-left (inset 2px) per UI-SPEC §17. The border pen is
        amber (``#f5a623``) for a manual-override badge (D-16), matte
        (``#0b0b0e``) for an auto-numbered one.
        """
        if self.pagebox.bubble_no is None:
            self._badge.setVisible(False)
            return
        # Position at the TL corner, OUTSIDE the box rect (UI-SPEC §17). The
        # badge ignores transformations, so pos() is in SCENE coords; use the
        # scene-space rect so a moved/resized box keeps the badge tracking.
        rect = self.sceneBoundingRect()
        bx = rect.left() - _BADGE_W - _BADGE_OFFSET
        by = rect.top() - _BADGE_H - _BADGE_OFFSET
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
        self._badge_digit.setPlainText(str(self.pagebox.bubble_no))
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

    def _current_focus_text(self) -> str:
        """Return the D-10 current-focus text: translation when present, else recognized.

        Empty string when the box carries neither (the overlay stays hidden).
        Translation wins when it is a non-empty string; recognized text is read
        directly off ``payload.text`` (str/list aware — joined + stripped for a
        list). The returned text is a plain ``str`` (no list shape leaks to the
        overlay document).

        Defensive against a payload that is not a real ``TextBlock``: a bare
        marker object (e.g. the ``payload="p"`` duck-typed fake some tests /
        callers pass) has no ``.text`` / ``.translation`` attributes, so both
        branches yield empty and the overlay stays hidden. Production always
        carries either ``None`` or a real ``TextBlock``.
        """
        payload = self.pagebox.payload
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
