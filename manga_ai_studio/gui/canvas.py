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
    QPainterPath,
    QPen,
    QPixmap,
    QTransform,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)

from manga_ai_studio.core.mask_editor import (
    DEFAULT_BRUSH_SIZE,
    MASK_PAINT_COLOR,
    ToolMode,
    clamp_brush_size,
    paint_mask_lasso,
    paint_mask_rect,
    paint_mask_stroke,
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
    # Emitted ONCE per completed mask-editing stroke (mouseRelease), NOT per
    # mouseMove. The plan-06 history/undo manager consumes this to snapshot the
    # mask (UI-SPEC surface 8).
    mask_modified = Signal()

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

        # Mask-editing overlay items (plan 04). preview_item holds the
        # dashed-cyan rect/lasso drag preview (z=900); cursor_item is the
        # brush-size outline circle that follows the pointer (z=1000, above
        # everything). Reimplemented patterned after MangaCleaner_GPU
        # canvas.py:31-42 (D-12 reference-only).
        self.preview_item = QGraphicsPathItem()
        self.preview_item.setPen(
            QPen(QColor(0, 212, 255, 200), 2, Qt.PenStyle.DashLine)
        )
        self.preview_item.setZValue(900)
        self._scene.addItem(self.preview_item)

        self.cursor_item = QGraphicsEllipseItem()
        self.cursor_item.setZValue(1000)
        self._scene.addItem(self.cursor_item)

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

        # Mask-editing tool state (plan 04). The editable mask QImage is held
        # in self._mask (distinct from mask_item, the QGraphicsPixmapItem that
        # DISPLAYS it). current_tool drives the mouse-event dispatch;
        # is_eraser_modifier is the transient Shift toggle on Brush (UI-SPEC
        # surface 6 modifier).
        self.current_tool = ToolMode.MOVE
        self.brush_size = DEFAULT_BRUSH_SIZE
        self.is_eraser_modifier = False
        self._mask: QImage | None = None  # set in set_image / set_mask
        self._is_painting = False
        self._last_pt = QPointF()
        self._start_pt = QPointF()
        self._lasso_path = QPainterPath()

        # Inpaint preview state (plan 05, UI-SPEC surface 7). _original_image_numpy
        # holds the pre-inpaint image (for the before/after toggle);
        # _inpainted_qimage is the displayed (inpainted) image; _showing_original
        # tracks which side of the toggle is currently displayed. All three reset
        # on set_image/clear (a new page clears the inpaint history).
        self._original_image_numpy: np.ndarray | None = None
        self._inpainted_qimage: QImage | None = None
        self._showing_original = False
        # Cursor follows the pointer even without a held button.
        self.setMouseTracking(True)
        self._update_cursor_visuals()

        # Show the empty state on a fresh canvas.
        self._update_empty_state()

    # ----------------------------------------------------------------- image I/O
    def set_image(self, pixmap: QPixmap) -> None:
        """Display ``pixmap`` on the image layer and reset the mask overlay."""
        self.image_item.setPixmap(pixmap)
        self.setSceneRect(QRectF(pixmap.rect()))

        # Initialize the editable mask QImage to a transparent image of the
        # same size (plan 04: self._mask is the painting target).
        mask = QImage(pixmap.size(), QImage.Format.Format_ARGB32)
        mask.fill(Qt.GlobalColor.transparent)
        self._mask = mask
        self.mask_item.setPixmap(QPixmap.fromImage(mask))
        self.mask_item.setVisible(True)
        self._mask_visible = True

        # A new page clears the inpaint preview history (plan 05 UI-SPEC surface 7).
        self._original_image_numpy = None
        self._inpainted_qimage = None
        self._showing_original = False

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
        self._mask = None
        self._original_image_numpy = None
        self._inpainted_qimage = None
        self._showing_original = False
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
        tinted = tinted.copy()
        # Store as the editable mask (plan 04): subsequent brush/eraser strokes
        # compose onto this same QImage in place (RESEARCH Pitfall 4 — mutate,
        # do not reallocate per mouse-move).
        self._mask = tinted
        self.mask_item.setPixmap(QPixmap.fromImage(tinted))
        self.mask_item.setVisible(True)
        self._mask_visible = True

    def toggle_mask_overlay(self) -> None:
        """Flip the mask overlay visibility (View -> Toggle Mask Overlay, M)."""
        visible = not self.mask_item.isVisible()
        self.mask_item.setVisible(visible)
        self._mask_visible = visible

    def has_mask(self) -> bool:
        """Return True iff the editable mask has content (a non-null QImage)."""
        return self._mask is not None and not self._mask.isNull()

    def has_mask_content(self) -> bool:
        """Return True iff the mask has any painted (non-transparent) pixels.

        Distinct from :meth:`has_mask` (which is True whenever a mask QImage
        exists, including the fresh transparent initialization after
        ``set_image``). Used by plan 05's Inpaint gate: running LaMa on an
        empty mask is a wasted model load, so the Inpaint action requires
        actual painted content.
        """
        if self._mask is None or self._mask.isNull():
            return False
        # Cheap content check: convert to RGBA8888 and scan the alpha channel
        # for any non-zero pixel. A fully-transparent mask has no content.
        src = self._mask.convertToFormat(QImage.Format.Format_RGBA8888)
        arr = np.frombuffer(
            bytes(src.constBits()), dtype=np.uint8
        ).reshape(src.height(), src.width(), 4)
        return bool((arr[:, :, 3] > 0).any())

    def clear_mask(self) -> None:
        """Clear the editable mask to transparent (Edit -> Clear Mask, plan 04).

        Mutates ``self._mask`` in place and refreshes the display (no new QImage
        is allocated — RESEARCH Pitfall 4).
        """
        if self._mask is None or self._mask.isNull():
            return
        self._mask.fill(Qt.GlobalColor.transparent)
        self.update_mask_display()
        self.mask_modified.emit()

    def get_mask(self) -> QImage | None:
        """Return the editable mask QImage (None when no page is loaded).

        Consumed by plan 05's inpaint dispatch and plan 06's history manager.
        """
        return self._mask

    def update_mask_display(self) -> None:
        """Refresh mask_item from the editable ``self._mask`` QImage.

        Called after every brush/rect/lasso/erase mutation (RESEARCH Pitfall 4
        — mutate the existing QImage in place, then refresh the pixmap; no new
        QImage is allocated per mouse-move).

        Pure display refresh: does NOT emit ``mask_modified`` (the
        plan-04 stroke-commit emission lives in ``_end_paint`` / ``clear_mask``,
        and the plan-06 undo-application path must NOT re-push onto the
        history stack — see :meth:`apply_undo_mask`).
        """
        if self._mask is None or self._mask.isNull():
            return
        self.mask_item.setPixmap(QPixmap.fromImage(self._mask))

    # ------------------------------------------------------- undo application
    def apply_undo_mask(self, mask_qimage: QImage) -> None:
        """Restore a mask snapshot from the history (plan 06, UI-SPEC surface 8).

        Replaces the editable ``self._mask`` with ``mask_qimage.copy()`` (the
        ``.copy()`` detaches from the history's internal copy so subsequent
        strokes do not mutate the history entry) and refreshes the display
        WITHOUT emitting ``mask_modified`` — undo must NOT re-push onto the
        stack (``test_undo_does_not_repush`` is the regression guard;
        UI-SPEC surface 8 prohibition).
        """
        if mask_qimage is None or mask_qimage.isNull():
            return
        # Detach from the history's internal list so a stroke mutation of
        # self._mask cannot corrupt the history entry.
        self._mask = mask_qimage.copy()
        self.mask_item.setPixmap(QPixmap.fromImage(self._mask))
        self.mask_item.setVisible(True)
        self._mask_visible = True

    def apply_undo_image(self, x: int, y: int, patch_np: np.ndarray) -> None:
        """Composite a numpy patch into the displayed image (plan 06 undo).

        Used by image-undo/redo (Ctrl+Z/Ctrl+Shift+Z): the popped ``(x, y,
        patch)`` from :class:`HistoryManager` is written into the current
        image's ``[y:y+h, x:x+w]`` region. Bounds-checked (T-01-15): a patch
        that extends beyond the current image is clipped to the image rect;
        an empty/zero-size patch is a no-op.

        Buffer lifetime (RESEARCH Pitfall 2): the patch is written into the
        ``set_image_from_numpy``-built QImage, which is ``.copy()``-detached
        before storage (Pitfall-2 guard ``test_inpaint_result_display_uses_copy``
        locks this on the display path).

        Does NOT emit ``mask_modified`` (image undo is unrelated to the mask
        signal — UI-SPEC surface 8).
        """
        if patch_np is None:
            return
        current = self.get_image_numpy()
        if current is None:
            return
        h_img, w_img = current.shape[:2]
        ph, pw = patch_np.shape[:2]
        if ph == 0 or pw == 0:
            return
        # Bounds check (T-01-15): clip the patch + destination rect to the
        # current image so a stale history entry after a crop cannot corrupt
        # the image array (a Phase 5 concern; defensive now).
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(w_img, x0 + pw)
        y1 = min(h_img, y0 + ph)
        if x1 <= x0 or y1 <= y0:
            return  # fully out of bounds — no-op
        # Source sub-rect matching the clipped destination.
        sx0 = x0 - int(x)
        sy0 = y0 - int(y)
        sub = patch_np[sy0 : sy0 + (y1 - y0), sx0 : sx0 + (x1 - x0)]
        current[y0:y1, x0:x1] = sub
        # set_image_from_numpy replaces the whole image; pass no bbox so the
        # full updated numpy is stored (the .copy() discipline is inside that
        # method).
        self.set_image_from_numpy(current)

    # -------------------------------------------------- inpaint numpy bridge
    def get_image_numpy(self) -> np.ndarray | None:
        """Return the displayed image as an ``(H, W, 3)`` uint8 RGB numpy array.

        Consumed by plan 05's inpaint dispatch: the worker thread receives this
        array (NOT a QImage/QPixmap) and hands it to ``TorchLamaModel.inpaint``
        (RESEARCH Pitfall 3 — never pass Qt objects into a worker thread).

        Returns None when no image is loaded. Buffer lifetime (RESEARCH Pitfall
        2, PATTERNS.md §Shared Pattern 5): the trailing ``.copy()`` detaches the
        array from the QImage buffer before the local ``qimg`` is garbage-
        collected. ``test_inpaint_result_display_uses_copy`` is the regression
        guard (mutating the returned array must not change the displayed image).
        """
        qpix = self.image_item.pixmap()
        if qpix.isNull():
            return None
        qimg = qpix.toImage().convertToFormat(QImage.Format.Format_RGB888)
        ptr = qimg.bits()
        if ptr is None:
            return None
        h, w = qimg.height(), qimg.width()
        bytes_per_line = qimg.bytesPerLine()
        # Qt pads each scanline to 4-byte alignment, so bytes_per_line can be
        # strictly greater than w*3 (e.g. a 1497px-wide RGB888 image is 4491
        # bytes/row but Qt allocates 4492). Reshaping the raw buffer directly
        # as (H, W, 3) fails for any width where w*3 is not a multiple of 4
        # (CR-08, surfaced by a real 2081x1497 manga page). PySide6's bits()
        # returns a memoryview; materialize to bytes, then take exactly w*3
        # bytes per row and skip the padding tail.
        raw = bytes(ptr)
        if bytes_per_line == w * 3:
            # Fast path: no padding (width*3 already 4-aligned).
            arr = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)
        else:
            # Strided path: slice the unpadded row content and let numpy copy
            # it into a contiguous (H, W, 3) array.
            strided = np.frombuffer(raw, dtype=np.uint8, count=h * bytes_per_line)
            arr = strided.reshape(h, bytes_per_line)[:, : w * 3].reshape(h, w, 3)
        # MANDATORY .copy() — detach from the QImage buffer before qimg GCs.
        return arr.copy()

    def set_image_from_numpy(
        self, rgb: np.ndarray, bbox: tuple[int, int, int, int] | None = None
    ) -> QImage:
        """Replace the image layer with ``rgb`` (or composite the ``bbox`` region).

        Used by plan 05's inpaint result display. Input validation (T-01-13):
        ``rgb`` must be a ``(H, W, 3)`` uint8 array — a malformed worker result
        raises ValueError instead of constructing a corrupt QImage.

        When ``bbox`` (x, y, w, h) is provided, only that region is composited
        into the existing image so non-masked pixels are untouched (avoids
        full-image replacement artifacts); otherwise the whole image is replaced.
        The original image numpy is captured BEFORE overwriting so the
        before/after preview toggle works.

        Buffer lifetime (RESEARCH Pitfall 2, PATTERNS.md §Shared Pattern 5): the
        QImage built from the numpy buffer is ``.copy()``-detached BEFORE
        storage in image_item. This EXPLICITLY fixes the MangaCleaner_GPU
        ``main_window.py:245`` bug (which built ``QImage(rgba.data, ...)`` without
        ``.copy()`` and caused intermittent segfaults). The Pitfall-2 regression
        guard ``test_inpaint_result_display_uses_copy`` locks this.
        """
        if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
            raise ValueError(
                f"expected (H,W,3) uint8 RGB array, got shape={rgb.shape} dtype={rgb.dtype}"
            )

        # Capture the pre-inpaint image for the before/after toggle (once per
        # inpaint op; a second inpaint extends, not resets, the original).
        if self._original_image_numpy is None:
            self._original_image_numpy = self.get_image_numpy()

        full_rgb = rgb
        if bbox is not None and self._original_image_numpy is not None:
            # Composite only the bbox region into the existing image numpy.
            x, y, w, h = bbox
            base = self._original_image_numpy
            if base is not None and base.shape[:2] == (rgb.shape[0], rgb.shape[1]):
                base = base.copy()
                base[y : y + h, x : x + w] = rgb[y : y + h, x : x + w]
                full_rgb = base

        h, w = full_rgb.shape[:2]
        qimg = QImage(full_rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
        # CRITICAL: .copy() detaches the QImage from the numpy buffer before
        # storage. Without this the QImage points at a buffer that GCs and
        # causes intermittent segfaults (RESEARCH Pitfall 2; MangaCleaner_GPU
        # main_window.py:245 omits this — the buggy reference we do NOT copy).
        qimg = qimg.copy()
        self.image_item.setPixmap(QPixmap.fromImage(qimg))
        if (w, h) != (self.sceneRect().width(), self.sceneRect().height()):
            self.setSceneRect(QRectF(0, 0, w, h))
        self._inpainted_qimage = qimg
        # If currently showing the original preview, the new result replaces the
        # stored inpainted image but the display stays on original until toggled.
        return qimg

    def show_original(self, show: bool) -> None:
        """Toggle between the original (pre-inpaint) and the inpainted image.

        UI-SPEC surface 7 before/after compare: ``show=True`` displays the
        original, ``show=False`` restores the inpainted result. No-op when the
        corresponding side is unavailable (no inpaint result yet).
        """
        self._showing_original = show
        if show and self._original_image_numpy is not None:
            arr = self._original_image_numpy
            h, w = arr.shape[:2]
            qimg = QImage(arr.data, w, h, w * 3, QImage.Format.Format_RGB888)
            # .copy() before display (RESEARCH Pitfall 2 — the original numpy is
            # held on self, but copy-detach keeps the QImage robust to the array
            # being replaced by a subsequent inpaint op).
            qimg = qimg.copy()
            self.image_item.setPixmap(QPixmap.fromImage(qimg))
        elif not show and self._inpainted_qimage is not None:
            self.image_item.setPixmap(QPixmap.fromImage(self._inpainted_qimage))

    def has_inpaint_result(self) -> bool:
        """Return True iff an inpaint result is stored (drives the preview enable)."""
        return self._inpainted_qimage is not None

    # ------------------------------------------------------------- tool state
    def set_tool(self, tool: ToolMode) -> None:
        """Set the active mask-editing tool (UI-SPEC surface 6).

        Resets the Shift eraser-modifier (it is transient — only Brush+Shift
        means erase).
        """
        self.current_tool = tool
        self.is_eraser_modifier = False
        self._update_cursor_visuals()

    def set_brush_size(self, size: int) -> None:
        """Set the brush size, clamped to [1, 300] (T-01-09)."""
        self.brush_size = clamp_brush_size(size)
        self._update_cursor_visuals()

    def _effective_eraser(self) -> bool:
        """True iff the next stroke should erase.

        The Eraser tool always erases; Brush erases while Shift is held (the
        transient modifier per UI-SPEC surface 6). Rectangle/Lasso paint/erase
        based on this flag too (a Shift+Rect drag is an erase-rect).
        """
        return self.current_tool == ToolMode.ERASER or (
            self.current_tool == ToolMode.BRUSH and self.is_eraser_modifier
        )

    def _update_cursor_visuals(self) -> None:
        """Set the cursor circle color/size from the active tool + brush size.

        Eraser mode -> cyan (QColor(0,212,255,...)); paint mode -> red
        (QColor(255,0,0,...)). The rect is centered on the cursor origin
        (setPos in mouseMoveEvent). Reimplemented patterned after
        MangaCleaner_GPU canvas.py:54-63 (D-12 reference-only).
        """
        if self._effective_eraser():
            pen = QPen(QColor(0, 212, 255, 200), 1)
            brush = QBrush(QColor(0, 212, 255, 60))
        else:
            pen = QPen(QColor(255, 0, 0, 200), 1)
            brush = QBrush(QColor(255, 0, 0, 60))
        self.cursor_item.setPen(pen)
        self.cursor_item.setBrush(brush)
        r = self.brush_size / 2
        self.cursor_item.setRect(-r, -r, self.brush_size, self.brush_size)

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

    # ------------------------------------------------------- pan + tool dispatch
    def mousePressEvent(self, event) -> None:  # noqa: N802
        """Route left-button to the active tool; middle/Space+left pans.

        Pan (middle button OR Space+left) takes priority. Otherwise a left
        click with a non-MOVE tool active (and a mask present) starts a
        stroke/rect/lasso; everything else falls through to the base
        QGraphicsView (item selection, scrollbar click, etc.).
        """
        middle = event.button() == Qt.MouseButton.MiddleButton
        space_left = self._space_held and event.button() == Qt.MouseButton.LeftButton
        if middle or space_left:
            self._panning = True
            self._last_pan_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._cursor_overridden = True
            event.accept()
            return

        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.current_tool != ToolMode.MOVE
            and self._mask is not None
            and not self._mask.isNull()
        ):
            self._begin_paint(event)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        """Pan when panning; advance the active stroke; else track the cursor.

        The cursor circle follows the pointer in every mode (setMouseTracking
        is on). While painting, BRUSH/ERASER strokes, RECTANGLE previews, and
        LASSO path previews are updated here.
        """
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

        curr = self._scene_pos(event)
        self.cursor_item.setPos(curr)

        if self._is_painting:
            self._advance_paint(curr)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        """End pan OR commit the active stroke (emits mask_modified once)."""
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

        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._is_painting
        ):
            self._end_paint(event)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ----------------------------------------------------------- paint helpers
    def _scene_pos(self, event) -> QPointF:
        """Map a mouse event's viewport position to scene coordinates.

        ``QGraphicsView.mapToScene`` takes a ``QPoint`` (int), but
        ``QMouseEvent.position()`` returns a ``QPointF`` (float); convert via
        ``toPoint()`` then back to ``QPointF`` so painting lands at sub-pixel-
        accurate scene coordinates regardless of zoom/pan.
        """
        return QPointF(self.mapToScene(event.position().toPoint()))

    def _begin_paint(self, event) -> None:
        """Start a stroke/rect/lasso on left-press (UI-SPEC surface 6)."""
        self._is_painting = True
        start = self._scene_pos(event)
        self._start_pt = start
        self._last_pt = start
        eraser = self._effective_eraser()
        if self.current_tool == ToolMode.LASSO:
            self._lasso_path = QPainterPath()
            self._lasso_path.moveTo(start)
        elif self.current_tool in (ToolMode.BRUSH, ToolMode.ERASER):
            # A click paints a single dot: stroke from the point to itself
            # (RoundCap fills the cap disc).
            paint_mask_stroke(self._mask, start, start, self.brush_size, eraser)
            self.update_mask_display()

    def _advance_paint(self, curr: QPointF) -> None:
        """Advance the in-progress stroke/preview (called on mouseMove)."""
        eraser = self._effective_eraser()
        if self.current_tool in (ToolMode.BRUSH, ToolMode.ERASER):
            paint_mask_stroke(self._mask, self._last_pt, curr, self.brush_size, eraser)
            self._last_pt = curr
            self.update_mask_display()
        elif self.current_tool == ToolMode.RECTANGLE:
            path = QPainterPath()
            path.addRect(QRectF(self._start_pt, curr).normalized())
            self.preview_item.setPath(path)
        elif self.current_tool == ToolMode.LASSO:
            self._lasso_path.lineTo(curr)
            self.preview_item.setPath(self._lasso_path)

    def _end_paint(self, event) -> None:
        """Commit the stroke on left-release (emits mask_modified ONCE)."""
        curr = self._scene_pos(event)
        eraser = self._effective_eraser()
        if self.current_tool == ToolMode.RECTANGLE:
            paint_mask_rect(self._mask, self._start_pt, curr, eraser)
            self.update_mask_display()
        elif self.current_tool == ToolMode.LASSO:
            self._lasso_path.closeSubpath()
            paint_mask_lasso(self._mask, self._lasso_path, eraser)
            self.update_mask_display()
        self._is_painting = False
        self.preview_item.setPath(QPainterPath())  # clear the dashed preview
        # Single emission per completed stroke — the plan-06 history hook.
        self.mask_modified.emit()

    # ----------------------------------------------------------- keyboard
    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Track Space for pan; Shift toggles Brush<->Eraser (UI-SPEC surface 6).

        Keys we do not explicitly handle are passed to ``event.ignore()`` (NOT
        ``super().keyPressEvent()``) so the event propagates up to the
        MainWindow and its application-wide ``QShortcut`` bindings (Ctrl+Z /
        Ctrl+Shift+Z / Alt+Z / Alt+Shift+Z undo/redo) can fire. The QGraphicsView
        base class accepts unhandled keys, which was shadowing those shortcuts
        when the canvas had focus (CR-09).
        """
        if event.key() == Qt.Key.Key_Space and not self._space_held:
            self._space_held = True
            if not self._panning:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                self._cursor_overridden = True
            event.accept()
            return
        # Shift toggles Brush<->Eraser transiently (does not consume the event).
        # NOTE: Qt delivers the Shift KeyPress with modifiers() == NoModifier
        # (modifiers reflect state BEFORE the press), so we key off event.key()
        # rather than event.modifiers() for the Shift press/release detection.
        if (
            event.key() == Qt.Key.Key_Shift
            and self.current_tool == ToolMode.BRUSH
            and not self.is_eraser_modifier
        ):
            self.is_eraser_modifier = True
            self._update_cursor_visuals()
            # Fall through: still ignore() so modifier-combo shortcuts
            # (Ctrl+Shift+Z) are not shadowed when the canvas has focus.
        # Ignore (do NOT accept) so parent widgets / QShortcuts see the event.
        # Calling super().keyPressEvent(event) here lets QGraphicsView accept
        # the key, which swallows Ctrl+Z/Ctrl+Shift+Z before the MainWindow's
        # undo/redo QShortcuts can fire (CR-09).
        event.ignore()

    def keyReleaseEvent(self, event) -> None:  # noqa: N802
        """Clear the Space-pan flag; Shift release restores Brush from Eraser."""
        if event.key() == Qt.Key.Key_Space and self._space_held:
            self._space_held = False
            if not self._panning:
                self.unsetCursor()
                self._cursor_overridden = False
            event.accept()
            return
        # Shift release ends the transient eraser modifier (only when the
        # active tool is Brush — see keyPressEvent for the modifiers() caveat).
        if (
            event.key() == Qt.Key.Key_Shift
            and self.current_tool == ToolMode.BRUSH
            and self.is_eraser_modifier
        ):
            self.is_eraser_modifier = False
            self._update_cursor_visuals()
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
