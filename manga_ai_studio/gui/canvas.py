"""EditorCanvas — the image display canvas.

A ``QGraphicsView`` subclass holding a ``QGraphicsScene`` with a layered stack
(image ``QGraphicsPixmapItem`` -> mask ``QGraphicsPixmapItem``). The skeleton
only renders the image and fits it to the window; mask painting and pan/zoom
event handling land in plan 02.

The pan/zoom MECHANICS are adapted from PanelCleaner's ``image_viewer.py`` (GPL
v3, vendored per D-12) — specifically ``QImageReader.setAllocationLimit(0)``
(image_viewer.py:45) for large-page safety, ``setTransformationAnchor(
AnchorUnderMouse)`` (image_viewer.py:56), and the ``#0b0b0e`` canvas matte
(UI-SPEC §Color). The mask-editing tool surface (brush/rect/lasso/eraser) is our
own reimplementation patterned after MangaCleaner_GPU (reference-only per D-12)
and lands in plan 04.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QPainter,
    QPixmap,
    QImageReader,
)
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
)


def _disable_qimage_allocation_limit() -> None:
    """Disable Qt's default 128MB allocation cap so large manga pages load.

    Adapted from PanelCleaner ``image_viewer.py:45``. Called at module import.
    """
    QImageReader.setAllocationLimit(0)


# Apply once at import time (UI-SPEC surface 2 large-image safety).
_disable_qimage_allocation_limit()


class EditorCanvas(QGraphicsView):
    """Image display canvas.

    Scene stack: image pixmap item (bottom) -> mask pixmap item (above).
    The mask item is initialized to a transparent overlay matching the image
    size; mask content is painted in plan 04.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # Scene + layered items. Store as _scene so the inherited scene()
        # accessor (which returns the same object after setScene) is not
        # shadowed by an instance attribute.
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self.image_item = QGraphicsPixmapItem()
        self.mask_item = QGraphicsPixmapItem()
        # mask_item stacks above image_item (added after it).
        self._scene.addItem(self.image_item)
        self._scene.addItem(self.mask_item)

        # View configuration.
        self.setRenderHint(QPainter.Antialiasing)
        # Zoom toward cursor (adapted from image_viewer.py:56).
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        # Canvas matte #0b0b0e (UI-SPEC §Color, MangaCleaner_GPU canvas.py:21 token).
        self.setBackgroundBrush(QBrush(QColor(11, 11, 14)))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_image(self, pixmap: QPixmap) -> None:
        """Display ``pixmap`` on the image layer and reset the mask overlay."""
        self.image_item.setPixmap(pixmap)
        self.setSceneRect(QRectF(pixmap.rect()))

        # Initialize the mask overlay to a transparent image of the same size.
        mask = QImage(pixmap.size(), QImage.Format.Format_ARGB32)
        mask.fill(Qt.GlobalColor.transparent)
        self.mask_item.setPixmap(QPixmap.fromImage(mask))

    def clear(self) -> None:
        """Reset both image and mask layers."""
        self.image_item.setPixmap(QPixmap())
        self.mask_item.setPixmap(QPixmap())
        self.setSceneRect(QRectF())

    def fit_to_window(self) -> None:
        """Fit the image item into the viewport, preserving aspect ratio."""
        self.fitInView(self.image_item, Qt.AspectRatioMode.KeepAspectRatio)
