"""EditorCanvas — the image display canvas.

A ``QGraphicsView`` subclass holding a ``QGraphicsScene`` with a layered stack
(image ``QGraphicsPixmapItem`` -> mask ``QGraphicsPixmapItem`` -> empty-state
overlay text). Plan 01 built the skeleton (image + mask item stack, anchor,
matte, allocation-limit reset); this plan adds the pan/zoom mechanics, an
empty-state overlay, and image path/size validation.

The pan/zoom MECHANICS are adapted from PanelCleaner's ``image_viewer.py`` (GPL
v3, vendored per D-12) — specifically ``QImageReader.setAllocationLimit(0)``
(image_viewer.py:45) for large-page safety, ``setTransformationAnchor(
AnchorUnderMouse)`` (image_viewer.py:56), ``ZOOM_TICK_FACTOR = 1.25``
(image_viewer.py:14), the half-step wheel zoom (image_viewer.py:144-154), the
100x max / half-viewport min clamp (image_viewer.py:221-255), and the
pixel-accurate smoothing toggle (image_viewer.py:116). The mask-editing tool
surface (brush/rect/lasso/eraser) is our own reimplementation patterned after
MangaCleaner_GPU (reference-only per D-12) and lands in plan 04.

Security:
    - ``validate_image_path`` calls ``Path.resolve()`` and enforces a suffix
      allowlist (T-01-02 path-traversal mitigation).
    - ``validate_image_size`` rejects images larger than 10000x10000 px
      (T-01-03 large-image DoS mitigation).
    - ``set_image_from_path`` calls ``QImage.copy()`` to detach the load buffer
      from the transient ``QImage(path)`` (RESEARCH Pitfall 2).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QImageReader,
    QPainter,
    QPixmap,
    QTransform,
)
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)


# Maximum zoom factor (image_viewer.py:233 clamps at 100).
MAX_ZOOM_FACTOR = 100.0
# Each Ctrl+ +/- step multiplies the zoom by this factor. Ctrl+wheel uses the
# square root (half-step) for finer control (image_viewer.py:14, 144-154).
ZOOM_TICK_FACTOR = 1.25
# Images larger than this on either axis are rejected (T-01-03 DoS mitigation).
MAX_IMAGE_DIMENSION = 10000
# Accepted image suffixes (T-01-02 suffix allowlist).
ALLOWED_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp"})


def _disable_qimage_allocation_limit() -> None:
    """Disable Qt's default 128MB allocation cap so large manga pages load.

    Adapted from PanelCleaner ``image_viewer.py:45``. Called at module import.
    """
    QImageReader.setAllocationLimit(0)


# Apply once at import time (UI-SPEC surface 2 large-image safety).
_disable_qimage_allocation_limit()


def validate_image_path(path: Path) -> bool:
    """Return True iff ``path`` resolves and has an allowed image suffix.

    T-01-02 mitigation: every file-open path (folder scan, drag-drop, recent
    files) flows through this check. ``Path.resolve()`` normalizes ``..``
    segments and resolves symlinks; the suffix allowlist rejects anything that
    is not a supported raster image.
    """
    try:
        resolved = path.resolve()
    except (OSError, ValueError):
        return False
    return resolved.suffix.lower() in ALLOWED_IMAGE_SUFFIXES


class EditorCanvas(QGraphicsView):
    """Image display canvas.

    Scene stack: image pixmap item (bottom) -> mask pixmap item (above) ->
    empty-state text overlay (top, hidden when an image is loaded). The mask
    item is initialized to a transparent overlay matching the image size; mask
    content is painted in plan 04.
    """

    # Emitted whenever the zoom factor changes (UI-SPEC surface 1 status bar).
    zoom_changed = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # Scene + layered items. Store as _scene so the inherited scene()
        # accessor (which returns the same object after setScene) is not
        # shadowed by an instance attribute (plan 01 deviation #3).
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self.image_item = QGraphicsPixmapItem()
        self.mask_item = QGraphicsPixmapItem()
        # mask_item stacks above image_item (added after it).
        self._scene.addItem(self.image_item)
        self._scene.addItem(self.mask_item)

        # Empty-state overlay (UI-SPEC §Surface 9 / §Copywriting). A top-most
        # text item shown only when no image is loaded.
        self._empty_heading = QGraphicsTextItem("No page open")
        self._empty_body = QGraphicsTextItem(
            "Open a single image or a folder of images to begin cleaning."
        )
        self._empty_hint = QGraphicsTextItem(
            "File \u2192 Open Image\u2026 (Ctrl+O)   \u00b7   or drag files here"
        )
        for item in (self._empty_heading, self._empty_body, self._empty_hint):
            item.setDefaultTextColor(QColor("#9a9aa2"))
            item.setZValue(2000)
            self._scene.addItem(item)
        # Heading is larger + semibold (UI-SPEC typography: 16px/600).
        heading_font = QFont("Segoe UI", 13)
        heading_font.setWeight(QFont.Weight.DemiBold)
        self._empty_heading.setFont(heading_font)
        # Body 14px regular.
        self._empty_body.setFont(QFont("Segoe UI", 11))
        # Hint 12px accent.
        hint_font = QFont("Segoe UI", 10)
        self._empty_hint.setFont(hint_font)
        self._empty_hint.setDefaultTextColor(QColor("#00d4ff"))

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

        # Zoom/pan state (image_viewer.py:47-57, 221-260).
        self.zoom_factor = 1.0
        # min zoom is computed dynamically (half viewport) inside zoom().
        self._panning = False
        self._last_pan_pos = QPointF()
        self._space_held = False
        self._cursor_overridden = False

        # Mask overlay visibility state (plan 03). The mask_item starts
        # transparent with no content; set_mask populates + shows it.
        self._mask_visible = False

        # Show the empty state on a fresh canvas.
        self._update_empty_state()

    # ----------------------------------------------------------------- image I/O
    def set_image(self, pixmap: QPixmap) -> None:
        """Display ``pixmap`` on the image layer and reset the mask overlay."""
        self.image_item.setPixmap(pixmap)
        self.setSceneRect(QRectF(pixmap.rect()))

        # Initialize the mask overlay to a transparent image of the same size.
        mask = QImage(pixmap.size(), QImage.Format.Format_ARGB32)
        mask.fill(Qt.GlobalColor.transparent)
        self.mask_item.setPixmap(QPixmap.fromImage(mask))

        self._update_empty_state()

    def set_image_from_path(self, path: Path) -> bool:
        """Validate, load, and display the image at ``path``.

        Returns True on success, False if the path failed validation or the
        image could not be read (the caller is expected to show the UI-SPEC
        "file unreadable" dialog on False).

        Security: runs ``validate_image_path`` (T-01-02) and
        ``validate_image_size`` (T-01-03), and detaches the load buffer via
        ``QImage.copy()`` (RESEARCH Pitfall 2).
        """
        if not validate_image_path(path):
            return False

        image = QImage(str(path.resolve()))
        if image.isNull():
            return False
        if not self.validate_image_size(image.width(), image.height()):
            return False
        # Detach the buffer so the pixel data outlives the transient load
        # (RESEARCH Pitfall 2 — QImage lifetime crashes).
        image = image.copy()
        self.set_image(QPixmap.fromImage(image))
        return True

    def clear(self) -> None:
        """Reset both image and mask layers."""
        self.image_item.setPixmap(QPixmap())
        self.mask_item.setPixmap(QPixmap())
        self.setSceneRect(QRectF())
        self.zoom_factor = 1.0
        self._mask_visible = False
        self.setTransform(QTransform())
        self._update_empty_state()

    # ------------------------------------------------------------- mask layer
    def set_mask(self, mask_qimage: QImage) -> None:
        """Composite a detection mask onto the mask overlay layer.

        The mask ``QImage`` is a grayscale or binary heatmap (H, W) from the
        detection adapter. This method tints the non-zero regions with the
        UI-SPEC mask overlay color ``rgba(255, 0, 0, 0.63)``
        (``QColor(255, 0, 0, 160)`` — 160/255 ~= 0.63) and shows the mask_item
        (UI-SPEC §Color mask overlay token).

        QImage buffer discipline (RESEARCH Pitfall 2, PATTERNS.md §Shared
        Pattern 5): ``mask_qimage.copy()`` defensively detaches any numpy
        buffer the producer attached before reaching this method, and the
        output tinted array is ``QImage.copy()``-detached before it becomes a
        pixmap, so the pixel data outlives both source arrays.
        """
        # Defensive copy — detach any numpy/shared buffer (RESEARCH Pitfall 2).
        mask_qimage = mask_qimage.copy()
        w = mask_qimage.width()
        h = mask_qimage.height()
        if w == 0 or h == 0:
            return

        # Convert to ARGB32 so pixel layout is uniform BGRA in memory (Qt's
        # native byte order on little-endian: bytes are B, G, R, A).
        src = mask_qimage.convertToFormat(QImage.Format.Format_ARGB32)
        # constBits() returns a memoryview in PySide6; materialize to bytes so
        # numpy can consume it (RESEARCH Pitfall 2 — buffer must outlive the
        # QImage, and .copy() above already detached the source).
        arr = np.frombuffer(bytes(src.constBits()), dtype=np.uint8).reshape(h, w, 4)
        # For a grayscale-converted ARGB32 source the R/G/B channels are equal;
        # treat any pixel with a non-zero red channel as a mask pixel.
        mask_pixels = arr[:, :, 2] > 0  # R channel (BGRA byte order)

        # Build the tinted overlay array directly (fast on large pages).
        # Qt ARGB32 on little-endian stores pixels in BGRA byte order, so the
        # array indices are [B, G, R, A]. Red overlay = B=0, G=0, R=255, A=160.
        out = np.zeros((h, w, 4), dtype=np.uint8)
        out[mask_pixels] = [0, 0, 255, 160]  # BGRA: red @ alpha 160/255~=0.63
        # Attach to a QImage and copy-detach so the array may be GC'd.
        tinted = QImage(out.data, w, h, w * 4, QImage.Format.Format_ARGB32)
        self.mask_item.setPixmap(QPixmap.fromImage(tinted.copy()))
        self.mask_item.setVisible(True)
        self._mask_visible = True

    def toggle_mask_overlay(self) -> None:
        """Flip the mask overlay visibility (View -> Toggle Mask Overlay, M)."""
        visible = not self.mask_item.isVisible()
        self.mask_item.setVisible(visible)
        self._mask_visible = visible

    def has_mask(self) -> bool:
        """Return True iff the mask layer has a non-null pixmap."""
        return not self.mask_item.pixmap().isNull()

    def clear_mask(self) -> None:
        """Clear the mask overlay to transparent (Edit -> Clear Mask, plan 04)."""
        if self.image_item.pixmap().isNull():
            self.mask_item.setPixmap(QPixmap())
        else:
            mask = QImage(self.image_item.pixmap().size(), QImage.Format.Format_ARGB32)
            mask.fill(Qt.GlobalColor.transparent)
            self.mask_item.setPixmap(QPixmap.fromImage(mask))
        self._mask_visible = False

    # -------------------------------------------------------------- validation
    def validate_image_size(self, width: int, height: int) -> bool:
        """Return False if the image exceeds the max dimension (T-01-03)."""
        return width <= MAX_IMAGE_DIMENSION and height <= MAX_IMAGE_DIMENSION

    # --------------------------------------------------------------- zoom/pan
    def update_smoothing(self) -> None:
        """Toggle SmoothPixmapTransform at the 1x boundary.

        Above 1x the pixels are magnified and smoothing would blur them; below
        or at 1x smoothing produces a clean downscale. Adapted from
        ``image_viewer.py:116``.
        """
        if self.zoom_factor > 1:
            self.setRenderHint(QPainter.SmoothPixmapTransform, False)
        else:
            self.setRenderHint(QPainter.SmoothPixmapTransform, True)

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt API casing)
        """Ctrl+wheel = zoom (half-step); Shift+wheel = horizontal; else pan.

        Adapted from ``image_viewer.py:125-142``.
        """
        if Qt.KeyboardModifier.ControlModifier & event.modifiers():
            if event.angleDelta().y() > 0:
                self.zoom_in(wheel=True)
            else:
                self.zoom_out(wheel=True)
        elif Qt.KeyboardModifier.ShiftModifier & event.modifiers():
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - event.angleDelta().y()
            )
        else:
            super().wheelEvent(event)

    def zoom_in(self, wheel: bool = False) -> None:
        """Zoom in by a full step, or a half-step on Ctrl+wheel.

        Adapted from ``image_viewer.py:144-148``.
        """
        self.zoom(ZOOM_TICK_FACTOR**0.5 if wheel else ZOOM_TICK_FACTOR)

    def zoom_out(self, wheel: bool = False) -> None:
        """Zoom out by a full step, or a half-step on Ctrl+wheel.

        Adapted from ``image_viewer.py:150-154``.
        """
        self.zoom(1 / (ZOOM_TICK_FACTOR**0.5) if wheel else 1 / ZOOM_TICK_FACTOR)

    def zoom(self, factor: float, *, suppress_signals: bool = False) -> None:
        """Apply a zoom ``factor`` to the current zoom, clamped to the bounds.

        Max 100x; min = half the viewport (the image must stay at least half the
        viewport on both axes when zooming out). Adapted from
        ``image_viewer.py:221-255``.
        """
        proposed = min(self.zoom_factor * factor, MAX_ZOOM_FACTOR)

        current_width = self.image_item.pixmap().width()
        current_height = self.image_item.pixmap().height()
        proposed_width = current_width * proposed
        proposed_height = current_height * proposed
        view_width = self.viewport().width()
        view_height = self.viewport().height()

        # Don't zoom out further if it's getting too small (half-viewport min).
        if (
            proposed_width < view_width / 2
            and proposed_height < view_height / 2
            and factor < 1
        ):
            return

        self.zoom_factor = proposed
        self.update_smoothing()
        self.setTransform(QTransform().scale(self.zoom_factor, self.zoom_factor))

        if not suppress_signals:
            self.zoom_changed.emit(self.zoom_factor)

    def zoom_reset(self) -> None:
        """Reset to 100% (Actual Size, Ctrl+1). Adapted from image_viewer.py:156."""
        self.zoom_factor = 1.0
        self.setTransform(QTransform().scale(self.zoom_factor, self.zoom_factor))
        self.update_smoothing()
        self.zoom_changed.emit(self.zoom_factor)

    def actual_size(self) -> None:
        """Alias for :meth:`zoom_reset` (UI-SPEC surface 1 View menu name)."""
        self.zoom_reset()

    def fit_to_window(self) -> None:
        """Fit the image item into the viewport, preserving aspect ratio.

        Resets ``zoom_factor`` to the resulting fit scale so the smoothing
        toggle and status bar reflect reality. Combines the skeleton's
        ``fit_to_window`` with ``image_viewer.py:160-171`` zoom_fit logic.
        """
        pixmap = self.image_item.pixmap()
        if pixmap.isNull():
            return
        self.fitInView(self.image_item, Qt.AspectRatioMode.KeepAspectRatio)
        # Derive the resulting scale from the active transform so zoom_factor
        # stays in sync (image_viewer.py:160-171 computes it directly; here we
        # read it back from the fitInView-applied transform).
        transform = self.transform()
        # fitInView sets a uniform scale on m11/m22 for KeepAspectRatio.
        self.zoom_factor = transform.m11()
        self.update_smoothing()
        self.zoom_changed.emit(self.zoom_factor)

    def zoom_fit(self) -> None:
        """Alias for :meth:`fit_to_window` (image_viewer.py:160 name)."""
        self.fit_to_window()

    # -------------------------------------------------------------------- pan
    def mousePressEvent(self, event) -> None:  # noqa: N802
        """Begin pan on middle button OR Space+left button (UI-SPEC surface 2)."""
        middle = event.button() == Qt.MouseButton.MiddleButton
        space_left = self._space_held and event.button() == Qt.MouseButton.LeftButton
        if middle or space_left:
            self._panning = True
            self._last_pan_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._cursor_overridden = True
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        """Scroll by the drag delta while panning."""
        if self._panning:
            delta = event.position() - self._last_pan_pos
            self._last_pan_pos = event.position()
            self.horizontalScrollBar().setValue(
                int(self.horizontalScrollBar().value() - delta.x())
            )
            self.verticalScrollBar().setValue(
                int(self.verticalScrollBar().value() - delta.y())
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        """End pan and restore the cursor."""
        if self._panning and event.button() in (
            Qt.MouseButton.MiddleButton,
            Qt.MouseButton.LeftButton,
        ):
            self._panning = False
            if self._space_held:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.unsetCursor()
                self._cursor_overridden = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Track Space for Space+left-drag pan (UI-SPEC surface 2)."""
        if event.key() == Qt.Key.Key_Space and not self._space_held:
            self._space_held = True
            if not self._panning:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                self._cursor_overridden = True
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # noqa: N802
        """Clear the Space-pan flag on release."""
        if event.key() == Qt.Key.Key_Space and self._space_held:
            self._space_held = False
            if not self._panning:
                self.unsetCursor()
                self._cursor_overridden = False
            event.accept()
            return
        super().keyReleaseEvent(event)

    # ----------------------------------------------------------- empty state
    def _update_empty_state(self) -> None:
        """Show/hide the empty-state overlay depending on image presence.

        Centers the three text blocks vertically with 48px (2xl) spacing per
        UI-SPEC §Surface 9.
        """
        empty = self.image_item.pixmap().isNull()
        self._empty_heading.setVisible(empty)
        self._empty_body.setVisible(empty)
        self._empty_hint.setVisible(empty)
        if not empty:
            return
        # Center horizontally over the viewport; stack vertically with spacing.
        view_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        cx = view_rect.center().x()
        top = view_rect.top() + 48.0
        for i, item in enumerate(
            (self._empty_heading, self._empty_body, self._empty_hint)
        ):
            item.setPos(
                cx - item.boundingRect().width() / 2,
                top + i * 48.0,
            )
