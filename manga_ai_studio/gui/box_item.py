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
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
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
# Handle z (above the box border z=100 — UI-SPEC §Z-order).
_HANDLE_Z = 150
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


class BoxItem(QGraphicsRectItem):
    """A text box on the canvas — origin-coloured ``QGraphicsRectItem`` (D-05).

    Composes a plan 03-01 ``PageBox`` (the data model — box/origin/payload +
    the D-15 seam). Renders an origin-coloured border (green detected / amber
    user, D-09) with a selection affordance: 2px unselected / 3px selected +
    a hue tint fill when selected (UI-SPEC §12c). The four corner resize
    handles (§12b) are visible ONLY on the selected box (D-08 single-select).

    Flags ``ItemIsSelectable | ItemIsMovable | ItemSendsGeometryChanges`` give
    native Qt selection/move + the geometry-change hook the canvas uses to
    commit box moves to the BOXES undo stack (plan 03-05). Qt's default dashed
    selection outline is suppressed (UI-SPEC §12a "disable Qt's default dashed
    selection outline") — the origin-coloured solid border is the sole
    selection signal plus the handles + tint.
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
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        # SizeAllCursor over the box body = the move affordance (UI-SPEC §12c).
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        # Four corner handles — children, z=150 (UI-SPEC §12b). Visible only
        # on the selected box (_sync_handles toggles visibility).
        self.handles: dict[str, CornerHandle] = {
            c: CornerHandle(c, self) for c in ("TL", "TR", "BL", "BR")
        }
        self._apply_origin_pen()
        self._sync_handles()

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
        """
        selected = self.isSelected()
        rect = self.rect()
        for handle in self.handles.values():
            handle.setVisible(selected)
            handle.reposition(rect)

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
        """Reposition handles and toggle visibility for a given selection state."""
        rect = self.rect()
        for handle in self.handles.values():
            handle.setVisible(selected)
            handle.reposition(rect)

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
